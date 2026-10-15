# rust-build-bench

A reproducible, tool-agnostic benchmark of Rust monorepo build and test tooling:
how much pull-request CI time each tool saves on real workspaces, and whether it
ever reports a stale test result.

| Tool | Family |
|---|---|
| Cargo + nextest (baseline), Cargo + sccache | baseline |
| [cargo-rail](https://github.com/loadingalias/cargo-rail) | Cargo-native |
| [moon](https://moonrepo.dev) | Cargo-native task runner |
| [Bazel](https://bazel.build) + [rules_rust](https://github.com/bazelbuild/rules_rust) | hermetic |
| [Buck2](https://buck2.build) + [Reindeer](https://github.com/facebookincubator/reindeer) | hermetic |

Corpora: [ruff](https://github.com/astral-sh/ruff) and
[rust-analyzer](https://github.com/rust-lang/rust-analyzer), each replayed over 20
real merged pull requests.

- **What is measured, and why:** [METHODOLOGY.md](METHODOLOGY.md) (normative)
- **Results:** [`results/`](results/), one directory per published run, each with a
  `REPORT.md`, raw per-step records, logs and full provenance
- **Adding a tool or corpus:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Headline metric

Wall time of PR CI on an **ephemeral runner with a shared remote cache**, over the
last 10 commits of each window ("replay-fresh"). A tool qualifies only if it passes
the **correctness canary**: a synthetic upstream change that must make a downstream
test fail, on a warm machine and on a fresh one.

## Reproduce

Requirements: Linux x86_64, Python 3.11+, git, rustup, internet access. One
dedicated machine per tool (all the same shape); nothing else running.

```bash
git clone https://github.com/jesperanzasolo/rust-build-bench
cd rust-build-bench
./run.sh my-run ruff,rust-analyzer cargo          # one tool per machine
# ... the same on other machines for cargo-sccache, cargo-rail, moon, bazel, buck2
python3 -m rbb report results/my-run              # after collecting results/ dirs
```

`./run.sh <run-id> ripgrep <tools> bench-smoke.toml` runs a ~15 minute smoke test
that validates the setup. Smoke numbers are not comparable and never published.

## Layout

```
bench.toml            protocol parameters (scenarios, sample counts, window sizes)
corpora/*.toml        pinned corpora: repo, commit, test scope, canary crates
tools/versions.toml   pinned tool versions and download URLs
rbb/                  the harness (Python standard library only)
  adapters/           one adapter per tool; the contract is in adapters/base.py
  gen/                config generators (moon, Bazel, Buck2) from `cargo metadata`
  runner.py           scenarios;  corpus.py  checkout, replay window, canary
  report.py           aggregation and the pre-registered decision rule
results/<run-id>/     published runs (CC BY 4.0)
```

## License

Code: MIT OR Apache-2.0. Published results and reports: CC BY 4.0.
