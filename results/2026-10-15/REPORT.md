# Results: 2026-10-15

## Decision

- **ruff:** **Inconclusive**. no eligible Cargo-native tool
  - Not eligible: `moon`: canary failed: warm-K1=clean, warm-K2=failed-without-canary-output, warm-K3=clean, fresh-K2=failed-without-canary-output
- **rust-analyzer:** **Inconclusive**. no eligible Cargo-native tool
  - Not eligible: `moon`: canary failed: 

Overall: **inconclusive** (rule in METHODOLOGY.md, pre-registered threshold 20%).

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `moon` | 1.9 | 0.1 | 0.2 / 0.3 / 1.1 | 0.1 / 1.5 | FAIL | 0.0 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `moon` | 1.3 | 2.1 | 5/10 | 4.0 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `moon` | 280.5 | 0.3 | n/a / n/a / n/a | 159.2 / 1,365.7 | n/a | 15.4 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `moon` | n/a | 4,529.2 | 0/10 | 1.9 | - |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
