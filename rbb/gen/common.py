"""Helpers shared by the hermetic (Bazel, Buck2) config generators."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from ..cargo_meta import Package, Workspace
from ..measure import capture

_INCLUDE_RE = re.compile(r'include(?:_str|_bytes)?!\s*\(\s*(?:concat!\s*\(\s*env!\s*\(\s*"CARGO_MANIFEST_DIR"\s*\)\s*,\s*)?"([^"]+)"')


def rust_version(ws_root: Path, env: dict | None = None) -> str:
    """The exact Rust version the corpus builds with (from rust-toolchain(.toml))."""
    for name in ("rust-toolchain.toml", "rust-toolchain"):
        f = ws_root / name
        if not f.exists():
            continue
        text = f.read_text()
        try:
            chan = tomllib.loads(text).get("toolchain", {}).get("channel")
        except tomllib.TOMLDecodeError:
            chan = text.strip()
        if chan and re.fullmatch(r"\d+\.\d+(\.\d+)?", chan):
            return chan if chan.count(".") == 2 else chan + ".0"
    out = capture(["rustc", "--version"], cwd=ws_root, env=env)
    return out.split()[1]


def files_read_outside_package(ws: Workspace, pkg: Package) -> list[str]:
    """Repo-relative paths (files or dirs) that `include*!` macros in `pkg` read from
    outside the package directory. Hermetic build systems need these declared."""
    root = ws.root
    pkg_dir = (root / pkg.dir).resolve()
    out: set[str] = set()
    for dirpath, _dirs, files in os.walk(pkg_dir):
        if "/target" in dirpath or "/.git" in dirpath:
            continue
        for fn in files:
            if not fn.endswith(".rs"):
                continue
            path = Path(dirpath) / fn
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for m in _INCLUDE_RE.finditer(text):
                rel = m.group(1)
                if "CARGO_MANIFEST_DIR" in m.group(0):
                    base = pkg_dir
                    rel = rel.lstrip("/")
                else:
                    base = path.parent
                target = (base / rel).resolve()
                try:
                    target.relative_to(pkg_dir)
                    continue  # inside the package: already covered by package globs
                except ValueError:
                    pass
                try:
                    out.add(str(target.relative_to(root.resolve())).replace(os.sep, "/"))
                except ValueError:
                    continue  # outside the repo entirely; cannot be declared
    return sorted(out)


def owning_package(ws: Workspace, repo_rel_path: str) -> Package | None:
    """The workspace package whose directory contains `repo_rel_path`, if any."""
    best = None
    for p in ws.packages.values():
        d = p.dir.rstrip("/") + "/"
        if p.dir != "." and (repo_rel_path + "/").startswith(d):
            if best is None or len(p.dir) > len(best.dir):
                best = p
    return best


def canary_runtime_note() -> str:
    return ("Tests may read fixtures at run time relative to CARGO_MANIFEST_DIR; hermetic "
            "generators must ship each package's files as test data.")
