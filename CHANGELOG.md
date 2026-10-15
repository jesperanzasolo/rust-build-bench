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
