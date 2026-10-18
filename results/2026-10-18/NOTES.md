# Run 2026-10-18: notes

Second published run, after fixing the moon, Bazel and Buck2 setups found wanting
in run 2026-10-15 (see [CHANGELOG.md](../../CHANGELOG.md), "After run 2026-10-15").
Protocol: `bench.toml`, unchanged (cold, 3 no-op samples, 10 warm replay commits,
5 fresh-runner commits, warm and fresh canary).

## Harness and machines

- **One harness commit for every pair:** `e2a8307`. Each job ran from branch
  `bench/2026-10-18` (commit `db8a661`), which adds only `bench-run.env`; that is
  the `harness_commit` in each `provenance.json`.
- **GitHub-hosted runners**, `ubuntu-24.04` standard (4 vCPU, 16 GiB), one job per
  (tool, corpus) pair, all 12 in parallel. Namespace runners were unavailable.
- **CPU models differ between jobs.** GitHub assigns AMD EPYC 7763, EPYC 9V45,
  EPYC 9V74 or Intel Xeon 6973P machines; their calibration differs by up to 38%
  single-core and 26% on four cores. The report lists the CPU and calibration for
  every pair and shows the decision gap with times scaled by calibration.
- **Not comparable with run 2026-10-15** (8 vCPU Namespace runners, before the
  setup fixes). Compare tools within this run only.

## Test scope and correctness

- Every tool ran the full test set on the cold run: 9,293 tests on ruff and 8,208 on
  rust-analyzer for the Cargo-based tools (identical counts), and every defined test
  target for Bazel and Buck2 (82 on ruff, 53 on rust-analyzer). The automatic
  test-set check found nothing.
- Every tool passed the correctness canary on both corpora, warm and fresh.
- The Cargo baseline passed every non-canary step on both corpora, so a failing
  cold run would have made a tool ineligible. No cold run failed.

## Failures (flaky timing tests, not counted against any tool)

| Pair | Step | Test | Cause |
|---|---|---|---|
| rust-analyzer / bazel | replay-warm c10 | `ide::syntax_highlighting_not_quadratic` | asserts linear scaling from timings; noisy on a loaded 4 vCPU runner |
| rust-analyzer / moon | replay-warm c09, replay-fresh c10 | `rust-analyzer::slow-tests completes_items_from_standard_library` | hit nextest's slow-test timeout while moon ran several crates' tests at once |

## Decision, and why it is not conclusive on ruff

- **Pre-registered rule:** ruff **build** (Bazel 32% faster than moon on fresh-runner
  PR CI); rust-analyzer **use cargo-sccache** (Bazel 38% slower). Overall: mixed.
- **ruff is inside the hardware noise.** Bazel ran on a 9V45, moon on a Xeon 6973P
  that is 22% slower on the four-core calibration. Scaled by that calibration, the
  gap is 17%, under the 20% threshold. A verdict that flips under this scaling is
  not one to act on. A rerun on a single CPU model is needed to settle ruff.
- **rust-analyzer is robust:** sccache leads under raw and scaled times.

## What changed from run 2026-10-15

- **Bazel's rust-analyzer lead is gone.** It now runs all 53 test targets (29 of 57
  before) and is 38% slower than sccache. The old 48% lead came from running less.
- **moon went from slowest to best Cargo-native tool on ruff** (390 s per PR). Its
  tasks now share one build, it reuses cached task results, and its affected set is
  narrower than cargo-rail's: on ruff's code commits it ran 10 to 44 of 55 crates'
  tests, where cargo-rail selected every test on every code commit.
- **sccache and cargo-rail gained much less on 4 vCPU than on 8.** On ruff, sccache
  is only 10% faster than Cargo (35% on 8 vCPU): with 445 of 486 compiles from cache,
  the ~41 workspace crates a commit invalidates dominate on 4 cores. On
  rust-analyzer, cargo-rail is 9% slower than Cargo although it runs fewer tests;
  both its compile and its test phases are much slower than on 8 vCPU. Different
  CPU models per job make the size of this effect uncertain.

## Gaps

- One run per pair; differences under ~15% may be noise, and CPU models differ.
- Hermetic configs are generated, not expert-tuned; the shared cache is on the
  same machine (no network latency).
