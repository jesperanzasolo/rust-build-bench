"""Baselines: plain Cargo + nextest, and Cargo + nextest + sccache.

`cargo` is the "no tool" reference: every commit runs the whole test suite with a
persistent target directory where the scenario allows it. It also produces the
correctness oracle (see rbb/scenarios.py).
"""

from __future__ import annotations

from .base import Adapter, TestRun, parse_nextest_counts, rm


class CargoAdapter(Adapter):
    name = "cargo"
    family = "baseline"

    def versions(self) -> dict[str, str]:
        c = self.ctx
        return {
            "cargo": c.capture(["cargo", "--version"]).strip(),
            "rustc": c.capture(["rustc", "--version"]).strip(),
            "cargo-nextest": c.capture(["cargo", "nextest", "--version"]).splitlines()[0].strip(),
        }

    def nextest_argv(self, selection: list[str] | None = None) -> list[str]:
        sel = selection if selection is not None else ["--workspace", *self.exclude_args()]
        argv = ["cargo", "nextest", "run", "--locked", "--no-fail-fast", "--no-tests=pass",
                *self.ctx.corpus.cargo_args, *sel]
        skips = self.skip_args()
        if skips:
            argv += ["--", *skips]
        return argv

    def test(self, *, scenario, step, base, head) -> TestRun:
        r = self.ctx.run(self.nextest_argv(), scenario=scenario, step=step, env=self.env())
        return TestRun(commands=[r], counts=parse_nextest_counts(r.log_path))


class CargoSccacheAdapter(CargoAdapter):
    """Cargo + nextest with sccache. The sccache directory is a *shared* cache:
    it survives wipe_local, which is how CI uses it (restored from a cache)."""

    name = "cargo-sccache"

    def _dir(self):
        return self.ctx.paths.shared / "sccache"

    def env(self) -> dict[str, str]:
        return {
            "RUSTC_WRAPPER": "sccache",
            "SCCACHE_DIR": str(self._dir()),
            "SCCACHE_CACHE_SIZE": "50G",
            "SCCACHE_IDLE_TIMEOUT": "0",
        }

    def versions(self) -> dict[str, str]:
        v = super().versions()
        v["sccache"] = self.ctx.capture(["sccache", "--version"]).strip()
        return v

    def test(self, *, scenario, step, base, head) -> TestRun:
        self.ctx.capture(["sccache", "--zero-stats"], env=self.env(), check=False)
        run = super().test(scenario=scenario, step=step, base=base, head=head)
        stats = self.ctx.capture(["sccache", "--show-stats", "--stats-format", "json"],
                                 env=self.env(), check=False)
        try:
            import json
            s = json.loads(stats)["stats"]
            run.cache = {
                "requests": s.get("compile_requests"),
                "hits": sum((s.get("cache_hits") or {}).get("counts", {}).values()),
                "misses": sum((s.get("cache_misses") or {}).get("counts", {}).values()),
            }
        except Exception:
            pass
        return run

    def wipe_local(self) -> None:
        super().wipe_local()
        self.ctx.capture(["sccache", "--stop-server"], env=self.env(), check=False)

    def wipe_all(self) -> None:
        self.wipe_local()
        rm(self._dir())

    def state_dirs(self):
        d = super().state_dirs()
        d["sccache"] = self._dir()
        return d
