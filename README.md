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
[rust-analyzer](https://github.com/rust-lang/rust-analyzer), each replayed over 10
real merged pull requests.

## Latest results (run 2026-10-15, preliminary)

Average PR CI time per commit on a fresh runner with a shared cache (5 real
commits per repo, 8 vCPU runner). Lower is better.

| Tool | ruff | rust-analyzer | Stale results? |
|---|---|---|---|
| Cargo + nextest (baseline) | 303 s | 159 s | none |
| Cargo + sccache | **198 s** (-35%) | 118 s (-25%) | none |
| cargo-rail | 209 s (-31%) | **104 s** (-34%) | none |
| moon | did not finish | 194 s (+22%) | none |
| Bazel + rules_rust | 152 s (-50%)\* | 55 s\* | none |
| Buck2 + Reindeer | 168 s (-45%)\* | could not build | none |

\* Not like-for-like. Under the auto-generated configs Bazel fails a ruff test that
runs `cargo build` itself and skips 14 of 43 rust-analyzer test targets; Buck2 fails
one ruff test binary intermittently.

- **sccache is the cheapest big win:** one wrapper setting (`RUSTC_WRAPPER=sccache`), a quarter to a third off PR CI.
- **cargo-rail wins on deep crate graphs** and makes no-op runs near-instant
  (1.4 s against 102 s on ruff), but on ruff its planner selects nearly every test.
- **Bazel and Buck2 are faster on ruff mainly because they cache test results**,
  at the cost of generated build files for every crate and about 2x the disk.
- **No tool ever served a stale test result** (correctness canary).

Caveats: one run per tool, so differences under ~15% may be noise; hermetic configs
are generated, not expert-tuned; the shared cache has no network latency, which
favours Bazel and Buck2. Full tables: [results/2026-10-15/REPORT.md](results/2026-10-15/REPORT.md);
gaps and reruns: [NOTES.md](results/2026-10-15/NOTES.md).

## About

- **What is measured, and why:** [METHODOLOGY.md](METHODOLOGY.md) (normative)
- **Results:** [`results/`](results/), one directory per published run, each with a
  `REPORT.md`, raw per-step records, logs and full provenance
- **Adding a tool or corpus:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Headline metric

Wall time of PR CI on an **ephemeral runner with a shared remote cache**, over the
last 5 commits of each window ("replay-fresh"). A tool qualifies only if it passes
the **correctness canary**: a synthetic upstream change that must make a downstream
test fail, on a warm machine and on a fresh one.

## Reproduce

Requirements: Linux x86_64, Python 3.12+, git, rustup, internet access. One
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
