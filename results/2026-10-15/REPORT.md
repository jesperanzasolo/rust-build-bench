# Results: 2026-10-15

## Decision

- **ruff:** **Use cargo-sccache**. No eligible hermetic tool to compare against.
- **rust-analyzer:** **Use cargo-sccache**. No eligible hermetic tool to compare against.

Overall: **use** (rule in METHODOLOGY.md, pre-registered threshold 20%).

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-sccache` | 298.5 | 64.6 | 197.5 / 203.2 / 987.9 | 159.4 / 1,522.1 | pass | 10.8 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo-sccache` | 6,480.1 | 8,668.8 | 0/0 | 0.0 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-sccache` | 109.7 | 37.8 | 123.1 / 140.2 / 591.5 | 88.9 / 838.0 | pass | 12.0 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo-sccache` | 2,787.1 | 3,769.7 | 5/10 | 0.0 | - |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
