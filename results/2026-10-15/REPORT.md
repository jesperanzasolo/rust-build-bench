# Results: 2026-10-15

## Decision

- **ruff:** **Use cargo-sccache**. No eligible hermetic tool to compare against.
  - Not eligible: `bazel`: cold run failed where the Cargo baseline passed every step
  - Not eligible: `buck2`: cold run failed where the Cargo baseline passed every step
  - Not eligible: `moon`: canary failed: warm-K1=clean, warm-K2=failed-without-canary-output, warm-K3=clean, fresh-K2=failed-without-canary-output
- **rust-analyzer:** **Use cargo-rail**. No eligible hermetic tool to compare against.
  - Not eligible: `bazel`: canary failed: 
  - Not eligible: `moon`: canary failed: 

Overall: **use** (rule in METHODOLOGY.md, pre-registered threshold 20%).

> rust-analyzer: the Cargo baseline failed 20 non-canary step(s), so the corpus has failing or flaky tests. Failures are reported per tool but do not affect eligibility.

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `moon` | 1.9 | 0.1 | 0.2 / 0.3 / 1.1 | 0.1 / 1.5 | FAIL | 0.0 GiB |
| `bazel` | 449.3 | 7.9 | 183.5 / 260.0 / 759.9 | 197.0 / 1,784.1 | pass | 20.7 GiB |
| `buck2` | 454.7 | 35.7 | 222.4 / 237.5 / 838.1 | 182.0 / 1,787.5 | pass | 24.3 GiB |
| `cargo-sccache` | 298.5 | 64.6 | 197.5 / 203.2 / 987.9 | 159.4 / 1,522.1 | pass | 10.8 GiB |
| `cargo-rail` | 366.6 | 1.4 | 244.8 / 296.5 / 1,045.7 | 224.9 / 2,056.6 | pass | 15.5 GiB |
| `cargo` | 349.5 | 102.2 | 296.3 / 325.0 / 1,513.8 | 220.8 / 2,106.2 | pass | 9.5 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | 4,777.1 | 10,675.8 | 5/10 | 146.9 | - |
| `buck2` | 5,599.4 | 11,252.3 | 2/5 | 47.5 | - |
| `cargo` | 10,232.7 | 12,137.4 | 0/0 | 0.0 | - |
| `cargo-rail` | 6,597.7 | 11,805.3 | 0/0 | 0.0 | 9.5 |
| `cargo-sccache` | 6,480.1 | 8,668.8 | 0/0 | 0.0 | - |
| `moon` | 1.3 | 2.1 | 5/10 | 4.0 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-rail` | 145.0 | 0.7 | 126.2 / 140.4 / 522.4 | 94.6 / 809.9 | pass | 20.8 GiB |
| `cargo-sccache` | 109.7 | 37.8 | 123.1 / 140.2 / 591.5 | 88.9 / 838.0 | pass | 12.0 GiB |
| `cargo` | 127.4 | 44.5 | 165.3 / 184.9 / 793.6 | 93.1 / 1,001.2 | pass | 11.2 GiB |
| `bazel` | 136.1 | 4.3 | n/a / n/a / n/a | 54.3 / 452.2 | n/a | 13.3 GiB |
| `moon` | 280.5 | 0.3 | n/a / n/a / n/a | 159.2 / 1,365.7 | n/a | 15.4 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | n/a | 2,422.2 | 0/10 | 55.4 | - |
| `cargo` | 4,499.5 | 5,124.7 | 5/10 | 0.0 | - |
| `cargo-rail` | 2,385.6 | 3,780.1 | 5/10 | 0.0 | 314.2 |
| `cargo-sccache` | 2,787.1 | 3,769.7 | 5/10 | 0.0 | - |
| `moon` | n/a | 4,529.2 | 0/10 | 1.9 | - |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
