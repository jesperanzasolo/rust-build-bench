"""Install the pinned tools from tools/versions.toml into one bin directory.

Every executable's sha256 is recorded in tools/installed.json next to the bin dir,
and copied into each run's provenance, so a published number can always be traced
to the exact bytes that produced it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .config import load_tool_versions

# Tools each benchmarked adapter needs (plus what every adapter needs).
COMMON = ["cargo-nextest", "uv"]
NEEDS = {
    "cargo": [],
    "cargo-sccache": ["sccache"],
    "cargo-rail": ["cargo-rail"],
    "moon": ["moon", "bazel-remote"],
    "bazel": ["bazelisk", "bazel-remote"],
    "buck2": ["buck2", "reindeer", "bazel-remote"],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    print(f"  fetch {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "rust-build-bench"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _chmod_x(p: Path) -> None:
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find(root: Path, name: str) -> Path:
    for dirpath, _dirs, files in os.walk(root):
        if name in files:
            return Path(dirpath) / name
    raise FileNotFoundError(f"{name} not found in archive")


def install_one(name: str, spec: dict, bin_dir: Path, opt_dir: Path) -> dict[str, str]:
    ver = str(spec.get("version", ""))
    fmt = spec.get("format")
    bins = spec.get("binaries", [name])
    installed: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        if "cargo_install" in spec:
            ci = spec["cargo_install"]
            root = opt_dir / f"{name}-{ver}"
            # A fresh machine may have rustup but no default toolchain; build the
            # tool with an explicit stable toolchain (not the corpus' toolchain).
            subprocess.run(["rustup", "toolchain", "install", "stable", "--profile", "minimal",
                            "--no-self-update"], check=True)
            subprocess.run(["cargo", "+stable", "install", "--locked", "--git", ci["git"], "--tag",
                            ci["tag"].format(version=ver), ci["crate"], "--root", str(root)], check=True)
            for b in bins:
                _link(root / "bin" / b, bin_dir / b)
                installed[b] = sha256(root / "bin" / b)
            return installed
        if "installer" in spec:
            script = td / "install.sh"
            _download(spec["installer"], script)
            root = opt_dir / f"{name}-{ver}"
            env = {**os.environ, "MOON_INSTALL_DIR": str(root / "bin")}
            subprocess.run(["bash", str(script), ver], check=True, env=env)
            for b in bins:
                _link(root / "bin" / b, bin_dir / b)
                installed[b] = sha256(root / "bin" / b)
            return installed
        url = spec["url"].format(version=ver)
        archive = td / Path(url).name
        _download(url, archive)
        if "sums_url" in spec:
            sums = td / "SHA256SUMS"
            _download(spec["sums_url"].format(version=ver), sums)
            want = {l.split()[-1].lstrip("*"): l.split()[0] for l in sums.read_text().splitlines() if l.strip()}
            got = sha256(archive)
            if want.get(archive.name) != got:
                raise RuntimeError(f"{name}: checksum mismatch for {archive.name}")
        if fmt == "bin":
            out = bin_dir / spec.get("rename", bins[0])
            shutil.copy(archive, out)
            _chmod_x(out)
            installed[out.name] = sha256(out)
            return installed
        if fmt == "zst":
            out = bin_dir / spec.get("rename", bins[0])
            subprocess.run(["zstd", "-q", "-d", "-f", str(archive), "-o", str(out)], check=True)
            _chmod_x(out)
            installed[out.name] = sha256(out)
            return installed
        extract = td / "x"
        extract.mkdir()
        if fmt == "tar.gz":
            with tarfile.open(archive) as t:
                t.extractall(extract, filter="data")
        elif fmt == "zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(extract)
            for p in extract.rglob("*"):
                if p.is_file() and not p.suffix:
                    _chmod_x(p)
        else:
            raise ValueError(f"{name}: unknown format {fmt}")
        if spec.get("keep_dir"):
            # Components must stay together (cargo-rail finds them beside itself).
            root = opt_dir / f"{name}-{ver}"
            shutil.rmtree(root, ignore_errors=True)
            src = _find(extract, bins[0]).parent
            shutil.copytree(src, root, symlinks=True)
            for b in bins:
                _chmod_x(root / b)
                _link(root / b, bin_dir / b)
                installed[b] = sha256(root / b)
            return installed
        for b in bins:
            out = bin_dir / b
            shutil.copy(_find(extract, b), out)
            _chmod_x(out)
            installed[b] = sha256(out)
    return installed


def _link(target: Path, link: Path) -> None:
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target)


def install(tools: list[str], prefix: Path) -> dict:
    cfg = load_tool_versions()
    bin_dir, opt_dir = prefix / "bin", prefix / "opt"
    bin_dir.mkdir(parents=True, exist_ok=True)
    opt_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = prefix / "installed.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    wanted: list[str] = list(COMMON)
    for t in tools:
        if t not in NEEDS:
            raise SystemExit(f"unknown tool {t!r}; known: {', '.join(NEEDS)}")
        wanted += NEEDS[t]
    for name in dict.fromkeys(wanted):
        spec = cfg[name]
        key = f"{name}@{spec.get('version')}"
        if key in manifest:
            continue
        print(f"installing {key}", flush=True)
        manifest[key] = install_one(name, spec, bin_dir, opt_dir)
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def ensure_toolchain(version: str, components: list[str]) -> None:
    """Install the corpus' Rust toolchain via rustup, shared by every tool."""
    args = ["rustup", "toolchain", "install", version, "--profile", "minimal", "--no-self-update"]
    for c in components:
        args += ["--component", c]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    install(sys.argv[2:] or list(NEEDS), Path(sys.argv[1]))
