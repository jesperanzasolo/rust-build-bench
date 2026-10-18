"""A small, typed view over `cargo metadata` used by every config generator.

Generators (moon, Bazel, Buck2) must agree on what the workspace *is*, so they all
read it through this module instead of parsing Cargo.toml themselves.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from .measure import capture


@dataclasses.dataclass
class Target:
    name: str
    kinds: list[str]
    src_path: str          # repo-relative
    edition: str
    test: bool             # participates in `cargo test`
    required_features: list[str]

    @property
    def crate_name(self) -> str:
        return self.name.replace("-", "_")


@dataclasses.dataclass
class Dep:
    package: str           # package name of the dependency
    crate_name: str        # name the code uses (after `package =` renames)
    kinds: set[str]        # {"normal", "dev", "build"}
    is_proc_macro: bool
    version: str = ""      # resolved version of the dependency


@dataclasses.dataclass
class Package:
    name: str
    version: str
    dir: str               # repo-relative directory of Cargo.toml
    manifest: str          # repo-relative Cargo.toml path
    edition: str
    lib: Target | None
    bins: list[Target]
    tests: list[Target]    # integration tests (tests/*.rs)
    build_script: Target | None
    features: list[str]    # features resolved for a workspace-wide build
    ws_deps: list[Dep]     # first-party (workspace member) dependencies
    ext_deps: list[Dep]    # third-party dependencies (resolved)
    links: str | None

    @property
    def is_proc_macro(self) -> bool:
        return bool(self.lib and "proc-macro" in self.lib.kinds)

    @property
    def lib_crate_name(self) -> str:
        return self.lib.crate_name if self.lib else self.name.replace("-", "_")

    def ws_deps_of(self, *kinds: str) -> list[Dep]:
        return [d for d in self.ws_deps if d.kinds & set(kinds)]


@dataclasses.dataclass
class Workspace:
    root: Path
    packages: dict[str, Package]
    raw: dict

    def members(self) -> list[Package]:
        return sorted(self.packages.values(), key=lambda p: p.dir)

    def registry_shadowed(self) -> set[str]:
        """Members whose name is also a third-party package in the resolve (e.g.
        rust-analyzer's `lib/la-arena`, also pulled from crates.io by a dependency).
        crate_universe 0.74 keys such a crate by name and version and drops the
        member from its per-package dependency map."""
        members = set(self.raw.get("workspace_members", []))
        third = {p["name"] for p in self.raw.get("packages", []) if p["id"] not in members}
        return {n for n in self.packages if n in third}

    def reverse_deps(self) -> dict[str, set[str]]:
        rev: dict[str, set[str]] = {n: set() for n in self.packages}
        for p in self.packages.values():
            for d in p.ws_deps:
                rev.setdefault(d.package, set()).add(p.name)
        return rev

    def transitive_ws_deps(self, name: str, kinds=("normal", "build", "dev")) -> set[str]:
        """All workspace packages whose sources can affect `name`'s tests."""
        seen: set[str] = set()
        stack = [d.package for d in self.packages[name].ws_deps if d.kinds & set(kinds)]
        while stack:
            n = stack.pop()
            if n in seen or n not in self.packages:
                continue
            seen.add(n)
            # Only normal/build edges of dependencies matter transitively.
            stack.extend(d.package for d in self.packages[n].ws_deps if d.kinds & {"normal", "build"})
        seen.discard(name)
        return seen

    def transitive_dependents(self, name: str) -> set[str]:
        rev = self.reverse_deps()
        seen: set[str] = set()
        stack = list(rev.get(name, ()))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(rev.get(n, ()))
        return seen


def _rel(root: Path, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def load(root: str | Path, *, cargo: str = "cargo", offline: bool = False,
         env: dict | None = None, exclude: set[str] | None = None,
         extra_args: list[str] | None = None) -> Workspace:
    root = Path(root).resolve()
    argv = [cargo, "metadata", "--format-version", "1", "--locked", *(extra_args or [])]
    if offline:
        argv.append("--offline")
    raw = json.loads(capture(argv, cwd=root, env=env))
    return from_metadata(raw, root, exclude=exclude)


def from_metadata(raw: dict, root: Path, exclude: set[str] | None = None) -> Workspace:
    exclude = exclude or set()
    by_id = {p["id"]: p for p in raw["packages"]}
    members = set(raw["workspace_members"])
    nodes = {n["id"]: n for n in (raw.get("resolve") or {}).get("nodes", [])}
    packages: dict[str, Package] = {}
    for pid in sorted(members):
        p = by_id[pid]
        if p["name"] in exclude:
            continue
        mdir = Path(p["manifest_path"]).parent
        lib = bins = tests = build = None
        bins, tests = [], []
        for t in p["targets"]:
            tgt = Target(
                name=t["name"], kinds=t["kind"], src_path=_rel(root, t["src_path"]),
                edition=t.get("edition", p.get("edition", "2021")),
                test=t.get("test", True), required_features=t.get("required-features", []) or [],
            )
            k = set(t["kind"])
            if k & {"lib", "rlib", "proc-macro", "cdylib", "staticlib", "dylib"}:
                lib = tgt
            elif "bin" in k:
                bins.append(tgt)
            elif "test" in k:
                tests.append(tgt)
            elif "custom-build" in k:
                build = tgt
        node = nodes.get(pid, {})
        ws_deps, ext_deps = [], []
        for d in node.get("deps", []):
            dp = by_id.get(d["pkg"])
            if dp is None:
                continue
            kinds = {(dk.get("kind") or "normal") for dk in d.get("dep_kinds", [])} or {"normal"}
            is_pm = any("proc-macro" in t["kind"] for t in dp["targets"])
            dep = Dep(package=dp["name"], crate_name=d["name"], kinds=kinds, is_proc_macro=is_pm,
                      version=dp["version"])
            if d["pkg"] in members:
                if dp["name"] not in exclude and dp["name"] != p["name"]:
                    ws_deps.append(dep)
            else:
                ext_deps.append(dep)
        packages[p["name"]] = Package(
            name=p["name"], version=p["version"], dir=_rel(root, str(mdir)) or ".",
            manifest=_rel(root, p["manifest_path"]), edition=p.get("edition", "2021"),
            lib=lib, bins=bins, tests=tests, build_script=build,
            features=sorted(node.get("features", [])), ws_deps=ws_deps, ext_deps=ext_deps,
            links=p.get("links"),
        )
    return Workspace(root=root, packages=packages, raw=raw)
