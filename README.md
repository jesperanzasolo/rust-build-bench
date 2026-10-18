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

## Latest results (run 2026-10-18)

Average PR CI time per commit on a fresh runner with a shared cache (5 real
commits per repo). GitHub's standard 4 vCPU runners, one machine per tool and repo.
Lower is better. Every tool ran the full test set and passed the correctness canary.

| Tool | ruff | rust-analyzer |
|---|---|---|
| Cargo + nextest (baseline) | 793 s | 238 s |
| Cargo + sccache | 717 s (-10%) | **168 s** (-30%) |
| cargo-rail | 410 s (-48%) | 261 s (+9%) |
| moon | 390 s (-51%) | 330 s (+38%) |
| Bazel + rules_rust | **265 s** (-67%) | 230 s (-3%) |
| Buck2 + Reindeer | 383 s (-52%) | 260 s (+9%) |

- **No single winner.** On ruff, where most commits touch a crate many others depend
  on, the tools that skip work (Bazel's cached test results, moon's and cargo-rail's
  change-based selection) win big. On rust-analyzer, plain compile caching (sccache)
  wins and the others barely beat Cargo or trail it.
- **Bazel's edge is cached test results:** on ruff it reused 48 to 82 of 82 test
  targets per commit, and a no-change run took 1 s (Cargo: 239 s).
- **moon, set up properly, is the best Cargo-native tool on ruff**, mostly because it
  ran only the affected crates' tests (10 to 44 of 55 per code commit).
- **Decision rule:** ruff says "build" (Bazel 32% ahead of moon) but that is inside
  the hardware noise; rust-analyzer says "use sccache". See the notes.

Caveats: one run per tool; GitHub gave jobs different CPU models (up to 26% apart on
four cores), which alone moves the ruff gap from 32% to 17%; hermetic configs are
generated, not expert-tuned; the shared cache has no network latency. Full tables:
[results/2026-10-18/REPORT.md](results/2026-10-18/REPORT.md); notes:
[NOTES.md](results/2026-10-18/NOTES.md). The earlier run, before the setup fixes,
is in [results/2026-10-15](results/2026-10-15/).

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
