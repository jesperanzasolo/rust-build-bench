# Results: 2026-10-15

## Decision

- **ruff:** **Use cargo**. No eligible hermetic tool to compare against.
- **rust-analyzer:** **Use cargo**. No eligible hermetic tool to compare against.

Overall: **use** (rule in METHODOLOGY.md, pre-registered threshold 20%).

> rust-analyzer: the Cargo baseline failed 20 non-canary step(s), so the corpus has failing or flaky tests. Failures are reported per tool but do not affect eligibility.

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo` | 349.5 | 102.2 | 296.3 / 325.0 / 1,513.8 | 220.8 / 2,106.2 | pass | 9.5 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo` | 10,232.7 | 12,137.4 | 0/0 | 0.0 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo` | 127.4 | 44.5 | 165.3 / 184.9 / 793.6 | 93.1 / 1,001.2 | pass | 11.2 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `cargo` | 4,499.5 | 5,124.7 | 5/10 | 0.0 | - |

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
