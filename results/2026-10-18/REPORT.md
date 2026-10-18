# Results: 2026-10-18

## Decision

- **ruff:** **Build yourself**. bazel is 32% faster than moon on replay-fresh PR CI. A Cargo-native tool that captures that gap without a build-system migration has room to exist.
- **rust-analyzer:** **Use cargo-sccache**. No hermetic tool beats cargo-sccache by more than 20% on replay-fresh PR CI (best: bazel, -38%).

Overall: **mixed** (rule in METHODOLOGY.md, pre-registered threshold 20%).

> **ruff: inconclusive.** The tools ran on different CPU models; scaled by CPU calibration the gap is +17% instead of +32%, the other side of the 20% threshold. Rerun on one CPU model before acting on it (see Machines).

Sensitivity, ruff: fresh-runner gap to `moon` if counted: `bazel` +32%; `buck2` +2%.

Sensitivity, rust-analyzer: fresh-runner gap to `cargo-sccache` if counted: `bazel` -38%; `buck2` -55%.

## ruff

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `bazel` | 751.7 | 1.0 | 326.6 / 494.0 / 1,327.2 | 302.8 / 2,821.9 | pass | 20.0 GiB |
| `buck2` | 1,027.4 | 109.9 | 405.3 / 662.0 / 1,917.4 | 391.4 / 3,782.5 | pass | 23.7 GiB |
| `moon` | 553.8 | 0.5 | 480.7 / 545.8 / 1,947.9 | 265.9 / 2,467.8 | pass | 9.4 GiB |
| `cargo-rail` | 664.5 | 1.2 | 501.7 / 553.8 / 2,048.9 | 349.1 / 3,231.2 | pass | 15.5 GiB |
| `cargo-sccache` | 854.1 | 245.6 | 743.6 / 751.1 / 3,583.0 | 512.1 / 4,951.6 | pass | 10.4 GiB |
| `cargo` | 794.3 | 238.6 | 792.6 / 796.4 / 3,966.6 | 482.4 / 4,668.9 | pass | 9.2 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | 4,996.5 | 10,549.9 | 0/0 | 116.2 | - |
| `buck2` | 7,421.0 | 14,520.7 | 0/0 | 64.3 | - |
| `cargo` | 15,535.6 | 17,618.2 | 0/0 | 0.0 | - |
| `cargo-rail` | 7,597.0 | 11,746.6 | 0/0 | 0.0 | 4.9 |
| `cargo-sccache` | 14,067.7 | 18,628.5 | 0/0 | 0.0 | - |
| `moon` | 7,609.4 | 9,119.4 | 0/0 | 3.8 | - |

## rust-analyzer

| Tool | Cold (s) | No-op (s) | PR, fresh runner: median / p90 / total (s) | PR, warm: median / total (s) | Canary | Max state |
|---|---|---|---|---|---|---|
| `cargo-sccache` | 191.5 | 77.1 | 177.0 / 181.2 / 837.8 | 134.4 / 1,306.8 | pass | 12.0 GiB |
| `bazel` | 439.6 | 2.9 | 276.7 / 294.5 / 1,152.5 | 188.2 / 1,814.2 | pass | 13.6 GiB |
| `cargo` | 224.3 | 84.5 | 245.2 / 251.2 / 1,191.9 | 142.6 / 1,486.7 | pass | 11.2 GiB |
| `buck2` | 369.0 | 87.5 | 292.6 / 309.1 / 1,302.4 | 208.0 / 2,096.1 | pass | 19.5 GiB |
| `cargo-rail` | 395.2 | 0.7 | 307.3 / 357.2 / 1,304.6 | 246.0 / 2,101.7 | pass | 20.8 GiB |
| `moon` | 289.2 | 0.6 | 371.8 / 383.6 / 1,648.6 | 189.8 / 1,959.1 | pass | 11.3 GiB |

| Tool | Fresh CPU total (s) | Warm CPU total (s) | Failed steps (fresh/warm) | Config sync total (s) | Post-merge work, fresh (s) |
|---|---|---|---|---|---|
| `bazel` | 3,910.4 | 6,308.8 | 0/1 | 288.7 | - |
| `buck2` | 4,411.9 | 7,301.6 | 0/0 | 38.3 | - |
| `cargo` | 4,533.6 | 5,361.8 | 0/0 | 0.0 | - |
| `cargo-rail` | 4,448.6 | 7,147.5 | 0/0 | 0.0 | 683.6 |
| `cargo-sccache` | 3,131.1 | 4,628.3 | 0/0 | 0.0 | - |
| `moon` | 5,432.5 | 6,376.5 | 1/1 | 3.4 | - |

## Machines

### Machines, ruff

| Tool | CPU | Calibration, 1 core (s) | Calibration, 4 cores (s) |
|---|---|---|---|
| `bazel` | AMD EPYC 9V45 96-Core Processor | 0.491 | 0.351 |
| `buck2` | AMD EPYC 7763 64-Core Processor | 0.677 | 0.399 |
| `cargo` | AMD EPYC 7763 64-Core Processor | 0.676 | 0.398 |
| `cargo-rail` | AMD EPYC 9V45 96-Core Processor | 0.507 | 0.344 |
| `cargo-sccache` | AMD EPYC 7763 64-Core Processor | 0.677 | 0.4 |
| `moon` | Intel(R) Xeon(R) 6973P-C | 0.529 | 0.428 |

> ruff: tools ran on 3 different CPU models. Scaled to the slowest machine by 4-core calibration, `bazel` vs `moon` is +17% (raw: +32%). Treat a verdict whose gap changes side of the threshold under this scaling as inconclusive.

### Machines, rust-analyzer

| Tool | CPU | Calibration, 1 core (s) | Calibration, 4 cores (s) |
|---|---|---|---|
| `bazel` | AMD EPYC 7763 64-Core Processor | 0.677 | 0.432 |
| `buck2` | AMD EPYC 7763 64-Core Processor | 0.677 | 0.4 |
| `cargo` | AMD EPYC 9V74 80-Core Processor | 0.592 | 0.357 |
| `cargo-rail` | AMD EPYC 7763 64-Core Processor | 0.677 | 0.399 |
| `cargo-sccache` | AMD EPYC 9V45 96-Core Processor | 0.521 | 0.365 |
| `moon` | AMD EPYC 7763 64-Core Processor | 0.678 | 0.401 |

> rust-analyzer: tools ran on 3 different CPU models. Scaled to the slowest machine by 4-core calibration, `bazel` vs `cargo-sccache` is -16% (raw: -38%). Treat a verdict whose gap changes side of the threshold under this scaling as inconclusive.

Raw per-step records: `**/results.jsonl`. Provenance: `**/provenance.json`.
