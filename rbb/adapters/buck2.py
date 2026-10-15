"""Buck2 with Reindeer-managed third-party crates and a local REAPI cache.

`sync` overlays a generated Buck2 project on the Cargo workspace (rbb/gen/buck2.py),
then vendors and buckifies third-party crates with Reindeer whenever the generated
third-party manifest changes. `test` runs `buck2 test //...`, the recommended CI
command: Buck2 itself decides what is affected by a change, so the same command is
used with and without a base commit.

Actions execute locally and read/write the bazel-remote action cache. Buck2 never
serves test *runs* from the cache in this mode (rust_test does not opt into test
execution caching), so each `test` reruns every test binary; compiles and links are
cached.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .. import cargo_meta
from ..gen import buck2 as gen
from ..gen import common
from .base import Adapter, TestRun, rm

# buck2_client/src/commands/test.rs prints, on stderr:
#   Tests finished: [Listing Fail N. ]Pass N. Fail N. Timeout N. Fatal N. Skip N. Omit N.
#   Infra Failure N. Build failure N
_SUMMARY = re.compile(
    r"Tests finished: (?:Listing Fail (\d+)\. )?Pass (\d+)\. Fail (\d+)\. Timeout (\d+)\. "
    r"Fatal (\d+)\. Skip (\d+)\. Omit (\d+)\. Infra Failure (\d+)\. Build failure (\d+)")
# buck2_client_ctx/src/subscribers/simpleconsole.rs (printed with --console=simple).
_STATS = re.compile(r"Commands: (\d+) \(cached: (\d+), remote: (\d+), local: (\d+)\)")
_HITS = re.compile(r"Cache hits: (\d+)%")

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

STATE_FILE = ".rbb-buck2-state.json"


def parse_test_summary(text: str) -> dict:
    """Counts from the last `Tests finished:` line of a `buck2 test` log."""
    text = _ANSI.sub("", text)
    ms = list(_SUMMARY.finditer(text))
    if not ms:
        return {}
    m = ms[-1]
    vals = [int(g) if g is not None else 0 for g in m.groups()]
    keys = ["listing_failed", "passed", "failed", "timed_out", "fatal", "skipped", "omitted",
            "infra_failure", "build_failures"]
    out = dict(zip(keys, vals))
    out["unit"] = "test-binary"   # the OSS runner reports one result per test target
    out["executed"] = out["passed"] + out["failed"] + out["timed_out"] + out["fatal"]
    return out


def parse_action_stats(text: str) -> dict:
    text = _ANSI.sub("", text)
    ms = list(_STATS.finditer(text))
    if not ms:
        return {}
    total, cached, remote, local = (int(x) for x in ms[-1].groups())
    out = {"actions": total, "hits": cached, "misses": remote + local,
           "remote": remote, "local": local}
    h = list(_HITS.finditer(text))
    if h:
        out["hit_percent"] = int(h[-1].group(1))
    return out


def _third_party_hash(files: dict[str, str], rust_version: str) -> str:
    """Everything Reindeer's vendor + buckify output depends on."""
    h = hashlib.sha256(rust_version.encode())
    for rel in sorted(files):
        if rel.startswith(gen.THIRD_PARTY + "/") and rel != gen.LOCK_SEED_PATH:
            h.update(f"\0{rel}\0{files[rel]}".encode())
    return h.hexdigest()


class Buck2Adapter(Adapter):
    name = "buck2"
    family = "hermetic"
    services = ("bazel-remote",)
    generated_paths = (
        "buck-out/",
        ".buckconfig",
        ".buckroot",
        "**/BUCK",
        "BUCK",
        "toolchains/",
        "third-party/",
        STATE_FILE,
    )

    def __init__(self, ctx):
        super().__init__(ctx)
        self.coverage: dict = {}

    # -- environment ------------------------------------------------------------
    def env(self) -> dict[str, str]:
        return {}

    def versions(self) -> dict[str, str]:
        c = self.ctx
        return {
            "buck2": c.capture(["buck2", "--version"]).strip(),
            # reindeer has no --version flag; record the pinned tag it was installed from.
            "reindeer": str((c.versions_cfg.get("reindeer") or {}).get("version", "unknown")),
            "rustc": c.capture(["rustc", "--version"]).strip(),
            "cargo": c.capture(["cargo", "--version"]).strip(),
        }

    def _endpoint(self) -> str | None:
        s = self.ctx.services
        return s.endpoints.get("bazel-remote-grpc") if s else None

    # -- config generation ------------------------------------------------------
    def sync(self) -> None:
        ctx = self.ctx
        ws_root = ctx.paths.ws
        ws = cargo_meta.load(ws_root, env=ctx.base_env(), extra_args=ctx.corpus.metadata_args)
        rust_version = common.rust_version(ws_root, env=ctx.base_env())
        host_triple = self._host_triple()
        host_cfg = ctx.capture(["rustc", "--print", "cfg", "--target", host_triple])
        tp_dir = ws_root / gen.THIRD_PARTY

        cc_tools = self._cc_tools()

        def generate():
            return gen.generate(ws, ctx.corpus, rust_version, self._endpoint(),
                                host_triple=host_triple, host_cfg_text=host_cfg,
                                vendor_extra_srcs=gen.scan_vendor_includes(tp_dir / "vendor"),
                                cc_tools=cc_tools)

        files, coverage = generate()
        lock_seed = files.pop(gen.LOCK_SEED_PATH, None)

        state_path = ws_root / STATE_FILE
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        tp_hash = _third_party_hash(files, rust_version)

        # Remove BUCK files generated for a previous commit that no longer apply.
        for old in state.get("files", []):
            if old not in files and old.endswith("BUCK") and not old.startswith(gen.THIRD_PARTY):
                rm(ws_root / old)
        for rel, text in files.items():
            p = ws_root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists() or p.read_text() != text:
                p.write_text(text)

        if state.get("third_party_hash") != tp_hash or not (tp_dir / "BUCK").exists():
            # Seed Reindeer's resolve with the workspace lockfile so versions match.
            if lock_seed is not None:
                (tp_dir / "Cargo.lock").write_text(lock_seed)
            # Stale fixups (crates that left the graph) would be reported as unused.
            fix_dir = tp_dir / "fixups"
            if fix_dir.exists():
                for d in sorted(fix_dir.iterdir()):
                    if f"{gen.THIRD_PARTY}/fixups/{d.name}/fixups.toml" not in files:
                        rm(d)
            reindeer = ["reindeer", "--third-party-dir", str(tp_dir)]
            r = ctx.run(reindeer + ["vendor"], scenario="sync", step="reindeer-vendor", env=self.env())
            if not r.ok:
                raise RuntimeError(f"reindeer vendor failed, see {r.log_path}")
            # Vendoring can change which files crates include; regenerate their fixups.
            files, coverage = generate()
            files.pop(gen.LOCK_SEED_PATH, None)
            for rel, text in files.items():
                if "/fixups/" in rel:
                    p = ws_root / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    if not p.exists() or p.read_text() != text:
                        p.write_text(text)
            tp_hash = _third_party_hash(files, rust_version)
            r = ctx.run(reindeer + ["buckify"], scenario="sync", step="reindeer-buckify", env=self.env())
            if not r.ok:
                raise RuntimeError(f"reindeer buckify failed, see {r.log_path}")
            mism = gen.lock_version_mismatches(ws, (tp_dir / "Cargo.lock").read_text())
            coverage["third_party_version_mismatches"] = mism
            state["third_party_hash"] = tp_hash
            state["third_party_version_mismatches"] = mism
        else:
            coverage["third_party_version_mismatches"] = state.get("third_party_version_mismatches", [])
        state["files"] = sorted(files)
        state_path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        self.coverage = coverage

    def _cc_tools(self) -> dict[str, str]:
        """Absolute paths of the system C toolchain on PATH (see toolchains/BUCK)."""
        import shutil
        path = self.ctx.base_env()["PATH"]
        out = {}
        for key, exe in (("archiver", "ar"), ("compiler", "gcc"), ("cxx_compiler", "g++"),
                         ("linker", "g++")):
            found = shutil.which(exe, path=path)
            if found:
                out[key] = found
        return out

    def _host_triple(self) -> str:
        out = self.ctx.capture(["rustc", "-vV"])
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
        return gen.DEFAULT_HOST_TRIPLE

    # -- execution ----------------------------------------------------------------
    def test_argv(self) -> list[str]:
        return ["buck2", "test", "--console=simple", "--keep-going", "//...",
                "--exclude", gen.INNER_TEST_LABEL]

    def test(self, *, scenario, step, base, head) -> TestRun:
        # The same command for every scenario: Buck2 computes what changed from file
        # contents and its own (in-memory and remote) caches, not from a git base.
        r = self.ctx.run(self.test_argv(), scenario=scenario, step=step, env=self.env())
        text = Path(r.log_path).read_text(errors="replace") if r.log_path else ""
        counts = parse_test_summary(text)
        return TestRun(commands=[r], counts=counts, cache=parse_action_stats(text))

    def wipe_local(self) -> None:
        ws = self.ctx.paths.ws
        self.ctx.capture(["buck2", "kill"], cwd=ws, env=self.env(), check=False)
        rm(ws / "buck-out")
        # third-party/vendor is a download cache (like CARGO_HOME) and survives.

    def wipe_all(self) -> None:
        self.wipe_local()
        if self.ctx.services:
            self.ctx.services.reset("bazel-remote")

    def state_dirs(self) -> dict[str, Path]:
        ws = self.ctx.paths.ws
        return {"buck-out": ws / "buck-out", "vendor": ws / gen.THIRD_PARTY / "vendor"}
