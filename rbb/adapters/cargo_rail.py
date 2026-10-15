"""cargo-rail: affected planning (`cargo rail plan`) + verified compiler result reuse.

Configured as its docs recommend for CI:
  * the cache is enrolled once per machine with `cargo rail cache setup`,
  * planning evidence is recorded on each commit after its test run and passed to
    the plan of the next commit (docs/planning.md, "Transfer evidence in CI"),
  * nextest executes exactly the `cargo_args` selection of the `cargo.test` work item.

Remote L2 storage only accepts real AWS S3 / R2 / Azure endpoints, so the shared
cache in the fresh-runner scenario is the persisted local L1 store instead. That is
the same zero-network-latency upper bound every other tool gets from the local
bazel-remote server (see METHODOLOGY.md, "Shared caches").
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .base import TestRun, parse_nextest_counts, rm
from .cargo import CargoAdapter


class CargoRailAdapter(CargoAdapter):
    name = "cargo-rail"
    family = "cargo-native"
    generated_paths = ("target/", ".rbb/")

    def _evidence_dir(self) -> Path:
        return self.ctx.paths.shared / "cargo-rail-evidence"

    def versions(self) -> dict[str, str]:
        v = super().versions()
        v["cargo-rail"] = self.ctx.capture(["cargo", "rail", "--version"]).strip()
        return v

    def setup(self) -> None:
        # Enrol this checkout in the compiler cache (writes the global rustc wrapper
        # into CARGO_HOME, which lives under `shared`). `cache ready` proves one cold
        # miss and one warm restore and installs rustc-dev when needed.
        # Budget matches the REAPI server's (100 GiB) so neither side evicts first.
        r = self.ctx.run(["cargo", "rail", "cache", "setup", "--max-size", "100GiB"],
                         scenario="setup", step="cache-setup")
        if not r.ok:
            raise RuntimeError(f"cargo rail cache setup failed; see {r.log_path}")
        r = self.ctx.run(["cargo", "rail", "cache", "ready"], scenario="setup", step="cache-ready")
        if not r.ok:
            raise RuntimeError(f"cargo rail cache ready failed; see {r.log_path}")

    def _status(self) -> dict:
        out = self.ctx.capture(["cargo", "rail", "cache", "status", "--scope", "local", "--json"], check=False)
        try:
            return json.loads(out)
        except Exception:
            return {}

    def _selection(self, cargo_args: list[str]) -> list[str]:
        """Apply the corpus' package exclusions to the planner's selection."""
        excluded = set(self.ctx.corpus.exclude_packages)
        out: list[str] = []
        i = 0
        while i < len(cargo_args):
            a = cargo_args[i]
            if a in ("-p", "--package") and i + 1 < len(cargo_args):
                if cargo_args[i + 1] not in excluded:
                    out += [a, cargo_args[i + 1]]
                i += 2
                continue
            out.append(a)
            i += 1
        if "--workspace" in out:
            out += self.exclude_args()
        return out

    def test(self, *, scenario, step, base, head) -> TestRun:
        ctx = self.ctx
        cmds = []
        if base is None:
            selection = ["--workspace", *self.exclude_args()]
            plan_info = {"mode": "all"}
        else:
            plan_file = ctx.paths.work / "plans" / f"{step}.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            argv = ["cargo", "rail", "plan", "--from", base, "--to", head, "--json"]
            ev = self._evidence_dir() / f"{base}.json"
            if ev.exists():
                argv += ["--evidence", str(ev)]
            r = ctx.run(f"{shlex.join(argv)} > {shlex.quote(str(plan_file))}",
                        scenario=scenario, step=step, shell=True)
            cmds.append(r)
            if not r.ok:
                return TestRun(commands=cmds)
            plan = json.loads(plan_file.read_text())
            required = plan.get("required", [])
            plan_info = {"mode": "plan", "required": required, "evidence": ev.exists()}
            if "cargo.test" not in required:
                return TestRun(commands=cmds, skipped=True, counts={"plan": plan_info})
            scope = plan["work"]["cargo.test"]["scope"]["selection"]
            selection = self._selection(list(scope["cargo_args"]))
        before = self._status()
        r = ctx.run(self.nextest_argv(selection), scenario=scenario, step=step, env=self.env())
        cmds.append(r)
        # Record planning evidence for this commit, as the docs prescribe for the
        # default branch, so the next commit's plan can narrow precisely.
        ev_out = self._evidence_dir() / f"{head}.json"
        ev_out.parent.mkdir(parents=True, exist_ok=True)
        rec = ctx.run(["cargo", "rail", "plan", "evidence", "--work", "cargo.test",
                       "--output", str(ev_out), "--", "test", "--workspace", "--locked", "--no-run",
                       *self.ctx.corpus.cargo_args, *self.exclude_args()],
                      scenario=scenario, step=step, env=self.env())
        # Not appended to `cmds`: per cargo-rail's docs the evidence is recorded by the
        # default-branch (post-merge) job, not by the PR job being timed. Its cost is
        # reported separately as `post_merge_s`. Failing to record evidence only
        # widens the next plan, so it never fails the step.
        after = self._status()
        counts = parse_nextest_counts(r.log_path)
        counts["plan"] = plan_info
        counts["post_merge_s"] = round(rec.wall_s, 3)
        counts["post_merge_ok"] = rec.ok
        return TestRun(commands=cmds, counts=counts, cache=_delta(before, after))

    def wipe_local(self) -> None:
        # A fresh runner has an empty target dir. The L1 store survives, standing in
        # for the shared cache (cargo clean also leaves it intact by design).
        rm(self.ctx.paths.ws / "target")

    def wipe_all(self) -> None:
        self.wipe_local()
        self.ctx.capture(["cargo", "rail", "cache", "clean", "--scope", "local"], check=False)
        rm(self._evidence_dir())
        # Per the docs, a cleaned local store must be re-enrolled before it is used
        # again; without this every compile reports `local_cache_unavailable`.
        self.setup()

    def state_dirs(self):
        return {"target": self.ctx.paths.ws / "target", "evidence": self._evidence_dir()}


def _delta(before: dict, after: dict) -> dict:
    """Best-effort diff of numeric counters in `cache status --json`."""
    out = {}

    def walk(a, b, prefix=""):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in b:
                walk(a.get(k), b[k], f"{prefix}{k}.")
        elif isinstance(b, (int, float)) and isinstance(a, (int, float)) and not isinstance(b, bool):
            if b != a and any(t in prefix for t in ("hit", "miss", "bypass", "restor")):
                out[prefix.rstrip(".")] = b - a

    walk(before, after)
    return out
