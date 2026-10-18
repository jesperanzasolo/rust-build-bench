"""Runs every scenario of the protocol for one (corpus, tool) pair.

Scenario definitions (also in METHODOLOGY.md, which is normative):

cold          Empty everything (local state and shared caches). Check out c0, run
              the full test suite. Measures first-ever CI run / new machine.
noop          Same commit again, nothing changed. Measures fixed overhead.
replay-warm   For each commit c1..cN of the window, keep all local state (sticky
              CI runner or developer machine) and run the tool's recommended
              change-based test command for c(i-1)..ci.
replay-fresh  Ephemeral CI runner with shared caches. Shared caches are reset and
              seeded by building c(k-1) (untimed, recorded as `seed`); then for
              each commit ck..cN: wipe local state, check out, run. Each step's
              run populates the shared cache, as post-merge CI on main would.
canary        Correctness. Three synthetic commits on top of cN change a constant
              in an upstream crate that a downstream test asserts on. The tool must
              report the middle commit as failing (warm, and again on a fresh runner).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import time
import tomllib
from pathlib import Path

from . import RESULT_SCHEMA, __version__, adapters, cargo_meta
from .adapters.base import Adapter, Context, Paths, TestRun
from .config import REPO_ROOT, Bench, Corpus, load_tool_versions
from .corpus import (canary_verdict, checkout, clone_for_tool, ensure_mirror, git,
                     make_canary_commits, replay_window)
from .install import ensure_toolchain
from .measure import capture, dir_size_bytes
from .services import LocalServices


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def corpus_rust_version(mirror: Path, corpus: Corpus) -> str:
    if corpus.env.get("RUSTUP_TOOLCHAIN"):
        return corpus.env["RUSTUP_TOOLCHAIN"]
    for name in ("rust-toolchain.toml", "rust-toolchain"):
        text = capture(["git", "-C", str(mirror), "show", f"{corpus.commit}:{name}"], check=False)
        if text.strip():
            try:
                return tomllib.loads(text)["toolchain"]["channel"]
            except Exception:
                return text.strip()
    raise RuntimeError(f"{corpus.name}: no pinned toolchain; set env.RUSTUP_TOOLCHAIN in the corpus file")


def machine_info() -> dict:
    info = {"platform": platform.platform(), "python": platform.python_version(),
            "nproc": os.cpu_count()}
    try:
        cpu = Path("/proc/cpuinfo").read_text()
        info["cpu_model"] = next((l.split(":", 1)[1].strip() for l in cpu.splitlines()
                                  if l.startswith("model name")), None)
        mem = Path("/proc/meminfo").read_text().splitlines()[0]
        info["mem_total_kib"] = int(mem.split()[1])
    except OSError:
        pass
    info["hostname_hash"] = hashlib.sha256(platform.node().encode()).hexdigest()[:12]
    return info


def calibrate() -> dict:
    """A fixed CPU workload, so results from different machines can be compared
    for noise. Not used to normalise numbers; reported alongside them."""
    t0 = time.perf_counter()
    h = hashlib.sha256()
    block = b"\0" * (1 << 20)
    for _ in range(1024):
        h.update(block)
    single = time.perf_counter() - t0
    n = os.cpu_count() or 1
    t0 = time.perf_counter()
    procs = [subprocess.Popen(["python3", "-c",
                               "import hashlib;h=hashlib.sha256();b=b'\\0'*(1<<20)\n"
                               "for _ in range(512): h.update(b)"]) for _ in range(n)]
    for p in procs:
        p.wait()
    parallel = time.perf_counter() - t0
    return {"sha256_1GiB_single_s": round(single, 3), f"sha256_512MiB_x{n}_parallel_s": round(parallel, 3)}


@dataclasses.dataclass
class Runner:
    corpus: Corpus
    tool: str
    bench: Bench
    run_id: str
    work_root: Path
    out_dir: Path
    tools_prefix: Path
    only: list[str] | None = None

    def __post_init__(self):
        self.versions_cfg = load_tool_versions()
        base = self.work_root / self.run_id / self.corpus.name / self.tool
        self.paths = Paths(work=base / "work", ws=base / "ws", shared=base / "shared",
                           logs=self.out_dir / "logs", tools_bin=self.tools_prefix / "bin")
        self.services = LocalServices(self.paths.shared / "services", self.paths.logs / "services",
                                      self.paths.tools_bin)
        self.ctx = Context(corpus=self.corpus, bench=self.bench, tool=self.tool, run_id=self.run_id,
                           paths=self.paths, versions_cfg=self.versions_cfg, services=self.services)
        self.adapter: Adapter = adapters.get(self.tool)(self.ctx)
        self.results_path = self.out_dir / "results.jsonl"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # -- recording --------------------------------------------------------------
    def emit(self, scenario: str, step: str, *, commit: str, base: str | None, run: TestRun | None,
             sync_s: float | None = None, extra: dict | None = None) -> dict:
        rec = {
            "schema": RESULT_SCHEMA, "run_id": self.run_id, "corpus": self.corpus.name,
            "tool": self.tool, "family": self.adapter.family, "scenario": scenario, "step": step,
            "commit": commit, "base": base, "ts": _now(), "sync_s": sync_s,
        }
        if run is not None:
            rec.update({
                "exit_code": run.exit_code, "wall_s": round(run.wall_s, 3),
                "cpu_s": None if run.cpu_s is None else round(run.cpu_s, 2),
                "peak_mem_bytes": run.peak_mem_bytes, "skipped": run.skipped,
                "counts": run.counts, "cache": run.cache,
                "commands": [{"argv": c.argv, "exit_code": c.exit_code, "wall_s": round(c.wall_s, 3),
                              "log": os.path.relpath(c.log_path, self.out_dir) if c.log_path else None,
                              "timed_out": c.timed_out}
                             for c in run.commands],
            })
        if extra:
            rec.update(extra)
        with open(self.results_path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        status = "-" if run is None else f"exit={run.exit_code} wall={run.wall_s:.1f}s"
        print(f"[{self.corpus.name}/{self.tool}] {scenario:12s} {step:10s} {commit[:10]} {status}", flush=True)
        return rec

    def state_sizes(self) -> dict:
        sizes = {k: dir_size_bytes(v) for k, v in self.adapter.state_dirs().items()}
        for s in self.adapter.services:
            sizes[f"service:{s}"] = self.services.size_bytes(s)
        return sizes

    # -- steps --------------------------------------------------------------------
    def _sync(self) -> float:
        t0 = time.perf_counter()
        self.adapter.sync()
        return time.perf_counter() - t0

    def _step(self, scenario: str, step: str, *, base: str | None, head: str, extra: dict | None = None) -> dict:
        # One fresh log per step, so a step's log holds exactly that step's commands.
        self.ctx.log_path(scenario, step).unlink(missing_ok=True)
        checkout(self.paths.ws, head)
        sync_s = self._sync()
        run = self.adapter.test(scenario=scenario, step=step, base=base, head=head)
        if extra and "coverage" in extra:
            # Known only after sync generated the config: how many test targets the
            # tool defines, so the report can check it ran all of them.
            cov = getattr(self.adapter, "coverage", None) or {}
            extra = {**extra, "coverage": {"test_targets": cov.get("test_targets")} if cov else None}
        return self.emit(scenario, step, commit=head, base=base, run=run, sync_s=round(sync_s, 3), extra=extra)

    # -- protocol -----------------------------------------------------------------
    def run(self) -> None:
        mirrors = self.work_root / "mirrors"
        mirror = ensure_mirror(self.corpus, mirrors)
        commits = replay_window(mirror, self.corpus)
        rust = corpus_rust_version(mirror, self.corpus)
        ensure_toolchain(rust, self.corpus.toolchain_components)
        clone_for_tool(mirror, self.paths.ws, self.adapter.generated_paths)
        checkout(self.paths.ws, commits[0])
        for s in self.adapter.services:
            self.services.start(s)
        try:
            self._provenance(commits, rust)
            self.adapter.setup()
            scen = [s for s in self.bench.scenarios if not self.only or s in self.only]
            for s in scen:
                getattr(self, "scenario_" + s.replace("-", "_"))(commits)
                self.emit(s, "state", commit=git(self.paths.ws, "rev-parse", "HEAD"), base=None, run=None,
                          extra={"state_bytes": self.state_sizes()})
        finally:
            self.services.stop_all()
            try:
                self.adapter.wipe_local()   # stops daemons (bazel, buck2, sccache)
            except Exception:
                pass
            if not os.environ.get("RBB_KEEP_WORK"):
                # Build state is large and every result is already in out_dir.
                from .adapters.base import rm
                try:
                    rm(self.work_root / self.run_id / self.corpus.name / self.tool)
                except Exception as e:
                    print(f"warning: could not delete work dir: {e}", flush=True)

    def scenario_cold(self, commits: list[str]) -> None:
        for i in range(self.bench.cold_samples):
            self.adapter.wipe_all()
            self._step("cold", f"s{i}", base=None, head=commits[0], extra={"coverage": None})

    def scenario_noop(self, commits: list[str]) -> None:
        head = git(self.paths.ws, "rev-parse", "HEAD")
        for i in range(self.bench.noop_samples):
            self._step("noop", f"s{i}", base=head, head=head)

    def scenario_replay_warm(self, commits: list[str]) -> None:
        n = self.bench.warm_commits or (len(commits) - 1)
        start = len(commits) - 1 - n
        # Bring local state to the window start without timing it (cold already did
        # this when the window starts at c0).
        if git(self.paths.ws, "rev-parse", "HEAD") != commits[start]:
            self._step("replay-warm", "seed", base=None, head=commits[start])
        for i in range(start + 1, len(commits)):
            self._step("replay-warm", f"c{i:02d}", base=commits[i - 1], head=commits[i],
                       extra={"files_changed": _nfiles(self.paths.ws, commits[i - 1], commits[i])})

    def scenario_replay_fresh(self, commits: list[str]) -> None:
        n = self.bench.fresh_commits or (len(commits) - 1)
        start = len(commits) - 1 - n
        self.adapter.wipe_all()
        self._step("replay-fresh", "seed", base=None, head=commits[start])
        for i in range(start + 1, len(commits)):
            self.adapter.wipe_local()
            self._step("replay-fresh", f"c{i:02d}", base=commits[i - 1], head=commits[i],
                       extra={"files_changed": _nfiles(self.paths.ws, commits[i - 1], commits[i])})

    def scenario_canary(self, commits: list[str]) -> None:
        ws = self.paths.ws
        checkout(ws, commits[-1])
        meta = cargo_meta.load(ws, env=self.ctx.base_env(), extra_args=self.corpus.metadata_args)
        dirs = {n: p.dir for n, p in meta.packages.items()}
        libs = {n: p.lib_crate_name for n, p in meta.packages.items()}
        steps = make_canary_commits(ws, self.corpus, dirs, libs)
        prev = commits[-1]
        for st in steps:
            rec = self._step("canary", f"warm-{st.label}", base=prev, head=st.commit)
            self._verdict(rec, st.expect_failure)
            prev = st.commit
        k1, k2 = steps[0], steps[1]
        self.adapter.wipe_local()
        rec = self._step("canary", "fresh-K2", base=k1.commit, head=k2.commit)
        self._verdict(rec, True)

    def _verdict(self, rec: dict, expect_failure: bool) -> None:
        text, seen = "", set()
        for c in rec.get("commands", []):
            if c.get("log"):
                p = self.out_dir / c["log"]
                if p.exists() and str(p) not in seen:
                    seen.add(str(p))
                    text += p.read_text(errors="replace")
        v = canary_verdict(text, rec["exit_code"], expect_failure)
        self.emit("canary", rec["step"] + ":verdict", commit=rec["commit"], base=rec["base"], run=None,
                  extra={"canary": v, "expect_failure": expect_failure})

    # -- provenance ---------------------------------------------------------------
    def _provenance(self, commits: list[str], rust: str) -> None:
        installed = self.tools_prefix / "installed.json"
        harness_sha = capture(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=False).strip()
        dirty = bool(capture(["git", "status", "--porcelain"], cwd=REPO_ROOT, check=False).strip())
        prov = {
            "schema": "rbb.provenance/v1", "run_id": self.run_id, "harness_version": __version__,
            "harness_commit": harness_sha, "harness_dirty": dirty, "started": _now(),
            "corpus": dataclasses.asdict(self.corpus), "replay_window": commits,
            "rust_toolchain": rust, "bench": dataclasses.asdict(self.bench), "tool": self.tool,
            "tool_versions": self.adapter.versions(),
            "pinned_versions": self.versions_cfg,
            "installed_binaries": json.loads(installed.read_text()) if installed.exists() else {},
            "machine": machine_info(), "calibration": calibrate(),
        }
        (self.out_dir / "provenance.json").write_text(json.dumps(prov, indent=1, sort_keys=True))


def _nfiles(ws: Path, a: str, b: str) -> int:
    return len([l for l in git(ws, "diff", "--name-only", f"{a}..{b}").splitlines() if l])
