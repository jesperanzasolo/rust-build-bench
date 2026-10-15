"""Loading of bench.toml, corpora/*.toml and tools/versions.toml."""

from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclasses.dataclass
class Canary:
    upstream: str | None = None     # workspace lib crate whose const the canary reads
    downstream: str | None = None   # crate that gets tests/rbb_canary.rs


@dataclasses.dataclass
class Corpus:
    name: str
    kind: str                        # "git" or "synthetic"
    repo: str | None
    commit: str | None               # tip of the replay window (full SHA)
    replay_commits: int
    exclude_packages: list[str]
    skip_tests: list[str]            # libtest `--skip` substrings, applied by every tool
    env: dict[str, str]
    canary: Canary
    synthetic: dict                  # parameters for the synthetic generator
    extra_data: dict[str, list[str]] # package -> extra repo-relative globs it reads (Bazel/Buck2)
    cargo_args: list[str]            # appended to every cargo test invocation, e.g. --all-features
    metadata_args: list[str]         # appended to `cargo metadata` for generators
    description: str = ""

    @property
    def id(self) -> str:
        return self.name


@dataclasses.dataclass
class Bench:
    scenarios: list[str]
    noop_samples: int
    cold_samples: int
    step_timeout_s: int
    canary: bool


def load_bench(path: Path | None = None) -> Bench:
    data = tomllib.loads((path or REPO_ROOT / "bench.toml").read_text())
    b = data.get("bench", {})
    return Bench(
        scenarios=b.get("scenarios", ["cold", "noop", "replay-warm", "replay-fresh", "canary"]),
        noop_samples=int(b.get("noop_samples", 3)),
        cold_samples=int(b.get("cold_samples", 1)),
        step_timeout_s=int(b.get("step_timeout_s", 3 * 3600)),
        canary=bool(b.get("canary", True)),
    )


def load_corpus(name_or_path: str) -> Corpus:
    p = Path(name_or_path)
    if not p.exists():
        p = REPO_ROOT / "corpora" / f"{name_or_path}.toml"
    d = tomllib.loads(p.read_text())
    c = d.get("canary", {})
    return Corpus(
        name=d["name"],
        kind=d.get("kind", "git"),
        repo=d.get("repo"),
        commit=d.get("commit"),
        replay_commits=int(d.get("replay_commits", 10)),
        exclude_packages=list(d.get("exclude_packages", [])),
        skip_tests=list(d.get("skip_tests", [])),
        env={k: str(v) for k, v in d.get("env", {}).items()},
        canary=Canary(upstream=c.get("upstream"), downstream=c.get("downstream")),
        synthetic=d.get("synthetic", {}),
        extra_data={k: list(v) for k, v in d.get("extra_data", {}).items()},
        cargo_args=list(d.get("cargo_args", [])),
        metadata_args=list(d.get("metadata_args", [])),
        description=d.get("description", ""),
    )


def load_tool_versions(path: Path | None = None) -> dict:
    return tomllib.loads((path or REPO_ROOT / "tools" / "versions.toml").read_text())
