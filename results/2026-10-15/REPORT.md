# Results: 2026-10-15

## Decision

- **ruff:** **Inconclusive**. no eligible Cargo-native tool
- **rust-analyzer:** **Inconclusive**. no eligible Cargo-native tool
  - Not eligible: `bazel`: canary failed: 

Overall: **inconclusive** (rule in METHODOLOGY.md, pre-registered threshold 20%).

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `bazel` | 449.3 | 7.9 | 183.5 / 260.0 / 759.9 | 197.0 / 1,784.1 | pass | 20.7 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | 4,777.1 | 10,675.8 | 5/10 | 146.9 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `bazel` | 136.1 | 4.3 | n/a / n/a / n/a | 54.3 / 452.2 | n/a | 13.3 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | n/a | 2,422.2 | 0/10 | 55.4 | - |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
