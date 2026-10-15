# Results: 2026-10-15

## Decision

- **ruff:** **Use cargo-rail**. No eligible hermetic tool to compare against.
- **rust-analyzer:** **Use cargo-rail**. No eligible hermetic tool to compare against.

Overall: **use** (rule in METHODOLOGY.md, pre-registered threshold 20%).

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-rail` | 366.6 | 1.4 | 244.8 / 296.5 / 1,045.7 | 224.9 / 2,056.6 | pass | 15.5 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo-rail` | 6,597.7 | 11,805.3 | 0/0 | 0.0 | 9.5 |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-rail` | 145.0 | 0.7 | 126.2 / 140.4 / 522.4 | 94.6 / 809.9 | pass | 20.8 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo-rail` | 2,385.6 | 3,780.1 | 5/10 | 0.0 | 314.2 |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
