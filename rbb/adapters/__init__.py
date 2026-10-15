"""Registry of benchmarked tools.

To add a tool: write an Adapter subclass (see base.py and CONTRIBUTING.md), add it
here, and add its pinned binaries to tools/versions.toml and rbb/install.py NEEDS.
"""

from __future__ import annotations

import importlib

ADAPTERS = {
    "cargo": ("rbb.adapters.cargo", "CargoAdapter"),
    "cargo-sccache": ("rbb.adapters.cargo", "CargoSccacheAdapter"),
    "cargo-rail": ("rbb.adapters.cargo_rail", "CargoRailAdapter"),
    "moon": ("rbb.adapters.moon", "MoonAdapter"),
    "bazel": ("rbb.adapters.bazel", "BazelAdapter"),
    "buck2": ("rbb.adapters.buck2", "Buck2Adapter"),
}


def get(name: str):
    if name not in ADAPTERS:
        raise SystemExit(f"unknown tool {name!r}; known: {', '.join(ADAPTERS)}")
    mod, cls = ADAPTERS[name]
    return getattr(importlib.import_module(mod), cls)
