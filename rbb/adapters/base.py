"""The adapter contract every benchmarked tool implements.

A tool adapter answers exactly five questions:

1. ``sync``       - Bring the tool's configuration up to date for the checked-out
                    commit (generate BUILD files, moon.yml, ...). Untimed, but its
                    duration is recorded as ``sync_s`` so adoption cost stays visible.
2. ``test``       - Run the tool's *recommended CI test command* for a change from
                    ``base`` to ``head``. ``base=None`` means "test everything".
                    This is the timed operation.
3. ``wipe_local`` - Delete per-machine build state, as a fresh CI runner would have.
                    Shared caches (remote cache, downloads) survive.
4. ``wipe_all``   - Delete everything, including shared caches. Used for cold runs.
5. ``versions``   - Report exact versions of every executable involved.

Adapters must not change what is tested. The test scope (packages, skipped tests)
comes from the corpus config and is identical for every tool.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
from pathlib import Path

from ..config import Bench, Corpus
from ..measure import CmdResult, capture, run


@dataclasses.dataclass
class Paths:
    work: Path        # per (run, corpus, tool) scratch root
    ws: Path          # the corpus checkout the tool operates on
    shared: Path      # survives wipe_local: remote-cache data, download caches
    logs: Path
    tools_bin: Path   # where installed tool binaries live (on PATH)


class Context:
    """Everything an adapter needs, and nothing it doesn't."""

    def __init__(self, *, corpus: Corpus, bench: Bench, tool: str, run_id: str,
                 paths: Paths, versions_cfg: dict, services: "Services | None" = None):
        self.corpus = corpus
        self.bench = bench
        self.tool = tool
        self.run_id = run_id
        self.paths = paths
        self.versions_cfg = versions_cfg
        self.services = services
        for p in (paths.work, paths.shared, paths.logs, paths.shared / "cargo-home"):
            p.mkdir(parents=True, exist_ok=True)

    # The environment shared by every tool. Tool-specific additions come from
    # Adapter.env(). CARGO_HOME lives under `shared` so registry downloads survive
    # wipe_local for every Cargo-driven tool alike.
    def base_env(self) -> dict[str, str]:
        env = {
            "CARGO_HOME": str(self.paths.shared / "cargo-home"),
            "CARGO_TERM_COLOR": "never",
            "CARGO_INCREMENTAL": "0",          # CI convention; applied to every tool
            "CARGO_NET_RETRY": "10",
            "RUST_BACKTRACE": "0",
            "NO_COLOR": "1",
            "CI": "true",
            "PATH": f"{self.paths.tools_bin}:{self.paths.shared / 'cargo-home' / 'bin'}:{os.environ.get('PATH', '')}",
        }
        # rustup must stay global (toolchains are downloads, shared across tools).
        if "RUSTUP_HOME" in os.environ:
            env["RUSTUP_HOME"] = os.environ["RUSTUP_HOME"]
        env.update(self.corpus.env)
        return env

    def log_path(self, scenario: str, step: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", step)
        return self.paths.logs / scenario / f"{safe}.log"

    def run(self, argv, *, scenario: str, step: str, env: dict | None = None,
            cwd: Path | None = None, shell: bool = False, timeout_s: float | None = None) -> CmdResult:
        full = self.base_env()
        if env:
            full.update(env)
        return run(argv, cwd=cwd or self.paths.ws, env=full, log_path=self.log_path(scenario, step),
                   timeout_s=timeout_s or self.bench.step_timeout_s, shell=shell)

    def capture(self, argv, *, env: dict | None = None, cwd: Path | None = None, check: bool = True) -> str:
        full = self.base_env()
        if env:
            full.update(env)
        return capture(argv, cwd=cwd or self.paths.ws, env=full, check=check)


@dataclasses.dataclass
class TestRun:
    """Result of one timed `test` invocation (possibly several commands)."""
    commands: list[CmdResult]
    counts: dict = dataclasses.field(default_factory=dict)   # tool-reported work counts
    cache: dict = dataclasses.field(default_factory=dict)    # tool-reported cache stats
    skipped: bool = False   # tool decided nothing needed to run

    @property
    def exit_code(self) -> int:
        for c in self.commands:
            if not c.ok:
                return c.exit_code if c.exit_code != 0 else 124
        return 0

    @property
    def wall_s(self) -> float:
        return sum(c.wall_s for c in self.commands)

    @property
    def cpu_s(self) -> float | None:
        vals = [c.cpu_s for c in self.commands]
        return None if any(v is None for v in vals) else sum(vals)

    @property
    def peak_mem_bytes(self) -> int | None:
        vals = [c.peak_mem_bytes for c in self.commands if c.peak_mem_bytes is not None]
        return max(vals) if vals else None


class Adapter:
    name: str = "abstract"
    family: str = "cargo-native"         # or "hermetic"
    services: tuple[str, ...] = ()       # e.g. ("bazel-remote",)
    # Paths (relative to the checkout) the adapter creates and that must never be
    # seen as source changes. Added to .git/info/exclude.
    generated_paths: tuple[str, ...] = ("target/",)

    def __init__(self, ctx: Context):
        self.ctx = ctx

    # -- lifecycle -------------------------------------------------------------
    def versions(self) -> dict[str, str]:
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        return {}

    def setup(self) -> None:
        """One-time, untimed setup on a fresh machine (e.g. enrol a cache)."""

    def sync(self) -> None:
        """Regenerate tool configuration for the current checkout. Untimed."""

    def test(self, *, scenario: str, step: str, base: str | None, head: str) -> TestRun:
        raise NotImplementedError

    def wipe_local(self) -> None:
        rm(self.ctx.paths.ws / "target")

    def wipe_all(self) -> None:
        self.wipe_local()

    def state_dirs(self) -> dict[str, Path]:
        return {"target": self.ctx.paths.ws / "target"}

    # -- helpers shared by adapters -------------------------------------------
    def skip_args(self) -> list[str]:
        out: list[str] = []
        for s in self.ctx.corpus.skip_tests:
            out += ["--skip", s]
        return out

    def exclude_args(self) -> list[str]:
        out: list[str] = []
        for p in self.ctx.corpus.exclude_packages:
            out += ["--exclude", p]
        return out


class Services:
    """Long-running helpers shared by tools, e.g. a local REAPI cache server."""

    def __init__(self):
        self.procs: dict[str, object] = {}
        self.endpoints: dict[str, str] = {}

    def stop_all(self) -> None:
        import signal
        for p in self.procs.values():
            try:
                p.send_signal(signal.SIGTERM)
                p.wait(timeout=20)
            except Exception:
                pass
        self.procs.clear()


def rm(path: Path) -> None:
    """Delete a file or tree, including read-only trees (Bazel writes its output
    base read-only). Raises if anything is left: a wipe that silently keeps state
    would make cold and fresh-runner numbers look better than they are."""
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if not path.exists():
        return

    def onexc(func, p, _exc):
        parent = os.path.dirname(p)
        for target in (parent, p):
            try:
                os.chmod(target, 0o700)
            except OSError:
                pass
        func(p)

    shutil.rmtree(path, onexc=onexc)
    if path.exists():
        raise RuntimeError(f"failed to delete {path}")


_NEXTEST_SUMMARY = re.compile(
    r"Summary \[\s*([\d.]+)s\]\s+(\d+) tests? run:\s+(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) skipped)?")


def parse_nextest_counts(log_path: str | None) -> dict:
    """Sum every nextest summary line in a log (moon runs nextest once per crate)."""
    if not log_path or not Path(log_path).exists():
        return {}
    text = Path(log_path).read_text(errors="replace")
    run_n = passed = failed = skipped = 0
    found = False
    for m in _NEXTEST_SUMMARY.finditer(text):
        found = True
        run_n += int(m.group(2))
        passed += int(m.group(3))
        failed += int(m.group(4) or 0)
        skipped += int(m.group(5) or 0)
    if not found:
        return {}
    return {"unit": "test", "executed": run_n, "passed": passed, "failed": failed, "skipped": skipped}
