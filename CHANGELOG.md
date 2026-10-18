# Changelog

Protocol, tool-version and adapter changes. Each published run records the harness
commit it used, so any result can be traced to the exact state described here.

## Unreleased

- Initial protocol: scenarios cold, noop, replay-warm (10 commits), replay-fresh
  (last 5 commits), canary (warm and fresh). Sized so a full run finishes in about
  an hour per tool on an 8 vCPU runner; all tools run in parallel.
- Tools: cargo + nextest 0.9.148, sccache 0.18.0, cargo-rail 0.31.1, moon 2.6.2,
  Bazel 9.3.0 + rules_rust 0.74.0, Buck2 2026-10-15 + Reindeer v2026.10.12.00,
  bazel-remote 2.6.3 as the shared REAPI cache.
- Corpora: ruff @ d1e1b1f6, rust-analyzer @ dd5ed69d, ripgrep @ 3fce3b5b (smoke).
- Decision rule: hermetic tool must beat the best Cargo-native tool by more than
  20% on replay-fresh total time to justify building a new tool.

## After run 2026-10-15

Setup fixes found by run 2026-10-15; every tool is re-run on one harness commit.
- moon: each crate's test task runs `cargo nextest run --workspace -E 'package(=<crate>)'`,
  so all tasks share one build; `-p <crate>` re-resolved features per crate and
  rebuilt shared dependencies task after task.
- Bazel: explicit third-party deps for workspace members that share a name with a
  crates.io crate (crate_universe drops them); real `CARGO_MANIFEST_DIR` for every
  crate; tests keep `RUSTUP_HOME` and `CARGO_HOME`; the test launcher handles bin
  names with `-` and sets `CARGO_WORKSPACE_DIR` for expect-test.
- Buck2: `include*!` fixups are written per vendored version.
- Test scope: corpus `skip_binaries`; ruff skips `ruff_annotate_snippets/examples`
  and `ty_server/e2e`; rust-analyzer skips `xtask`, `smol_str/tidy`,
  `test_format_document*` and `self_hosting_parsing`, for every tool.
- Decision rule: a tool that runs a different test set on the cold run is not
  eligible (checked automatically; replaces the hand-written exclusion).

## Run 2026-10-15 (first published run)

Fixes made during the run (affected pairs re-run from scratch, see the run's NOTES.md):
- Wipes delete read-only trees (Bazel output base) and fail loudly; full wipes reset
  every declared shared-cache service.
- cargo-rail: re-enrol the cache after a full wipe; evidence recording reported as
  post-merge work; 100 GiB local budget to match the REAPI server.
- moon: `moon exec` for full runs; project relationships exclude dev-dependencies.
- Bazel: no convenience symlinks, `.bazelignore`, PATH passed to tests.
- Buck2: Reindeer built with an explicit toolchain; vendor dir re-included when the
  corpus ignores `vendor/`.
- Checkout removes stale generated per-crate config files.
- Report: documented exclusions, verdict without them, hermetic sensitivity.
