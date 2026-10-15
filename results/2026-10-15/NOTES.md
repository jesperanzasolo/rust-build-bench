# Run 2026-10-15: notes

First published run. Protocol: `bench.toml` (cold, 3 no-op samples, 10 warm
replay commits, 5 fresh-runner commits, warm and fresh canary). One Namespace
`standard-8` runner (8 vCPU AMD EPYC, 16 GiB) per tool and corpus job. CPU
calibration across all machines was within ±10% (see each `provenance.json`).

## Harness commits

Bugs found during the run were fixed and the affected (corpus, tool) pairs re-run
from scratch. No result was edited.

| Pair | Harness commit | Why |
|---|---|---|
| ruff and rust-analyzer: cargo, cargo-sccache, cargo-rail; ruff: bazel | `db5190b` | original run |
| ruff: buck2 | `02dfcab` | re-run: Reindeer install needed an explicit toolchain |
| rust-analyzer: bazel, moon | `31751f6` | re-run: stale generated config broke checkout when a crate was added in the window |

## Gaps

- **ruff / moon:** did not finish within budget; no result. The original moon run
  hit a project-graph cycle (Cargo allows dev-dependency cycles, moon does not).
  The re-run with the fixed adapter (harness `c499514`) was cancelled after about
  3 hours, against a budget of about 1 hour per tool, still inside the ruff pair.
  The adapter runs `cargo nextest run -p <crate>` once per crate, and all 55 tasks
  serialise on one Cargo `target/` lock. This cannot change the ruff decision:
  moon could at best displace cargo-sccache as the best Cargo-native tool, and it
  was the slowest Cargo-native tool on rust-analyzer. rust-analyzer / moon ran
  with the earlier adapter, whose only difference is project-graph edges for
  dev-dependencies (no cycle in that corpus).
- **rust-analyzer / buck2:** no result. Reindeer rejected an auto-generated fixup
  (`fixups/embedded-io/fixups.toml`: "README.md matches no files") on both
  attempts. Counted as an integration failure, not timed.
- **rust-analyzer / bazel:** excluded from the decision (`exclusions.toml`): 14 of
  43 test targets do not build or pass under the generated config, so its times
  are for less work. Shown in the tables and the sensitivity line.
- **ruff, hermetic tools:** Bazel fails `ruff_annotate_snippets:examples_test`
  (the test runs `cargo build` itself) and intermittently `ty_server:e2e_test`;
  Buck2 fails one test binary intermittently. The Cargo baseline passed every
  step, so under the pre-registered rule both are ineligible. Their gaps are in
  the sensitivity line.
- **rust-analyzer:** 6 tests fail under every tool (environment-dependent); the
  rule does not use cold-run failures for this corpus.
