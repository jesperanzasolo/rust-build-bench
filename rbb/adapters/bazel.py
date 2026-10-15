"""Bazel + rules_rust (Bzlmod), configured the way the rules_rust docs recommend.

* `sync` generates MODULE.bazel / BUILD.bazel files from `cargo metadata` (see
  rbb/gen/bazel.py) and pins crate_universe's `cargo-bazel-lock.json` (a repin,
  exactly what a rules_rust user runs after editing Cargo.toml). Untimed.
* `test` is `bazel test //...` for every scenario: Bazel's action cache, its
  remote cache (a local bazel-remote, REAPI over gRPC) and its test-result cache
  decide what reruns. There is no separate "affected" computation.
* Downloads (toolchains, crates) go to a repository cache under `shared`, which
  survives every wipe by methodology, as a CI cache of downloads would.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from .. import cargo_meta
from ..gen import bazel as gen
from ..gen.common import rust_version as corpus_rust_version
from .base import Adapter, TestRun, rm

_EXECUTED = re.compile(r"Executed (\d+) out of (\d+) tests?: (.*)")
_STATUS = re.compile(r"^(//\S+|@\S+)\s+(\(cached\)\s+)?(FAILED TO BUILD|PASSED|FAILED|FLAKY|TIMEOUT|"
                     r"NO STATUS|INCOMPLETE|SKIPPED)\b", re.M)
_HOST_TRIPLE = "x86_64-unknown-linux-gnu"


class BazelAdapter(Adapter):
    name = "bazel"
    family = "hermetic"
    services = ("bazel-remote",)
    generated_paths = (
        "MODULE.bazel", "MODULE.bazel.lock", ".bazelversion", ".bazelrc", ".bazelignore",
        "BUILD.bazel", "**/BUILD.bazel", gen.LAUNCHER_SCRIPT, gen.CARGO_BAZEL_LOCKFILE,
        "bazel-*",
    )

    def __init__(self, ctx):
        super().__init__(ctx)
        self.coverage: dict = {}

    # -- paths ------------------------------------------------------------------
    def _output_user_root(self) -> Path:
        return self.ctx.paths.work / "bazel-root"

    def _repo_cache(self) -> Path:
        return self.ctx.paths.shared / "bazel-repo-cache"

    def _bazelisk_home(self) -> Path:
        return self.ctx.paths.shared / "bazelisk"

    def _endpoint(self) -> str | None:
        s = self.ctx.services
        return s.endpoints.get("bazel-remote-grpc") if s else None

    # -- lifecycle ----------------------------------------------------------------
    def env(self) -> dict[str, str]:
        return {
            "USE_BAZEL_VERSION": str(self.ctx.versions_cfg["bazel"]["version"]),
            "BAZELISK_HOME": str(self._bazelisk_home()),
        }

    def versions(self) -> dict[str, str]:
        c = self.ctx
        out = c.capture(["bazel", "--version"], env=self.env()).strip()
        # `bazel version` (bazelisk) prints "Bazelisk version: vX" before the server's info.
        bazelisk = c.capture(["bazel", "version"], env=self.env(), check=False)
        v = {
            "bazel": out,
            "rules_rust": str(c.versions_cfg["rules_rust"]["version"]),
            "rustc": corpus_rust_version(c.paths.ws, env=c.base_env()),
        }
        m = re.search(r"Bazelisk version: (\S+)", bazelisk)
        if m:
            v["bazelisk"] = m.group(1)
        return v

    def _rust_sha256s(self, version: str) -> dict[str, str]:
        """sha256 of every toolchain archive rules_rust downloads.

        rules_rust only ships hashes for Rust releases older than itself. A download
        without a hash is not stored in Bazel's (content-addressed) repository cache,
        so it would be repeated after every wipe. The official `.sha256` files from
        static.rust-lang.org are fetched once and kept under `shared`."""
        cache = self.ctx.paths.shared / f"rust-dist-sha256-{version}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        out = {}
        for key in gen.rust_dist_keys(version, [_HOST_TRIPLE]):
            url = f"https://static.rust-lang.org/dist/{key}.sha256"
            with urllib.request.urlopen(url, timeout=60) as r:
                out[key] = r.read().decode().split()[0]
        cache.write_text(json.dumps(out, indent=1, sort_keys=True))
        return out

    def sync(self) -> None:
        ctx = self.ctx
        ws_path = ctx.paths.ws
        ws = cargo_meta.load(ws_path, env=ctx.base_env(), extra_args=ctx.corpus.metadata_args)
        default_ws = None
        if ctx.corpus.metadata_args:
            default_ws = cargo_meta.load(ws_path, env=ctx.base_env())
        rv = corpus_rust_version(ws_path, env=ctx.base_env())
        files, coverage = gen.generate(
            ws, ctx.corpus,
            rust_version=rv,
            rules_rust_version=str(ctx.versions_cfg["rules_rust"]["version"]),
            remote_cache=self._endpoint(),
            output_user_root=str(self._output_user_root()),
            repository_cache=str(self._repo_cache()),
            bazel_version=str(ctx.versions_cfg["bazel"]["version"]),
            rust_sha256s=self._rust_sha256s(rv),
            test_env=gen.default_test_env(ctx.base_env()),
            default_ws=default_ws,
        )
        for rel, text in files.items():
            p = ws_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists() or p.read_text() != text:
                p.write_text(text)
        (ws_path / gen.LAUNCHER_SCRIPT).chmod(0o755)
        lock = ws_path / gen.CARGO_BAZEL_LOCKFILE
        if not lock.exists():
            lock.write_text("")
        # Re-pin crate_universe for this commit (what `CARGO_BAZEL_REPIN=1` is for).
        r = ctx.run(["bazel", "query", f"@{gen.CRATES_REPO}//:all", "--output=label"],
                    scenario="sync", step="bazel-repin",
                    env={**self.env(), "CARGO_BAZEL_REPIN": "true"})
        if not r.ok:
            raise RuntimeError(f"bazel crate_universe repin failed; see {r.log_path}")
        # Evaluate the extensions once more in the steady-state environment (no
        # CARGO_BAZEL_REPIN), so the timed run does not pay for the env change.
        ctx.run(["bazel", "query", f"@{gen.CRATES_REPO}//:all", "--output=label"],
                scenario="sync", step="bazel-warm", env=self.env())
        self.coverage = coverage
        (ctx.paths.logs / "bazel-coverage.json").write_text(json.dumps(coverage, indent=1, sort_keys=True))

    def test(self, *, scenario, step, base, head) -> TestRun:
        # Identical for base=None and a base: Bazel's caches decide what reruns.
        r = self.ctx.run(["bazel", "test", "//..."], scenario=scenario, step=step, env=self.env())
        return TestRun(commands=[r], counts=parse_bazel_test_counts(r.log_path))

    def wipe_local(self) -> None:
        root = self._output_user_root()
        if root.exists():
            self.ctx.capture(["bazel", "shutdown"], env=self.env(), check=False)
        # Bazel makes parts of the output tree read-only.
        if root.exists():
            self.ctx.capture(["chmod", "-R", "u+w", str(root)], check=False)
        rm(root)
        for p in self.ctx.paths.ws.glob("bazel-*"):
            if p.is_symlink():
                p.unlink()

    def wipe_all(self) -> None:
        self.wipe_local()
        if self.ctx.services:
            self.ctx.services.reset("bazel-remote")

    def state_dirs(self) -> dict[str, Path]:
        return {"bazel-output-user-root": self._output_user_root(),
                "bazel-repository-cache": self._repo_cache()}


def parse_bazel_test_counts(log_path: str | None) -> dict:
    if not log_path or not Path(log_path).exists():
        return {}
    text = Path(log_path).read_text(errors="replace")
    # Only the last invocation in the log counts (logs are appended to).
    start = text.rfind("\n$ (cd ")
    if start >= 0:
        text = text[start:]
    out: dict = {"unit": "test_target"}
    m = None
    for m in _EXECUTED.finditer(text):
        pass
    statuses: dict[str, int] = {}
    cached = 0
    for s in _STATUS.finditer(text):
        key = s.group(3).lower().replace(" ", "_")
        statuses[key] = statuses.get(key, 0) + 1
        if s.group(2):
            cached += 1
    if m is not None:
        out["executed"] = int(m.group(1))
        out["total"] = int(m.group(2))
    elif statuses:
        out["executed"] = sum(statuses.values()) - cached
        out["total"] = sum(statuses.values())
    else:
        return {}
    out["cached"] = cached
    out.update(statuses)
    return out
