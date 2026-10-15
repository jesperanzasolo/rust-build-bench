# Changelog

Protocol, tool-version and adapter changes. Each published run records the harness
commit it used, so any result can be traced to the exact state described here.

## Unreleased

- Initial protocol: scenarios cold, noop, replay-warm (20 commits), replay-fresh
  (10 commits), canary (warm and fresh).
- Tools: cargo + nextest 0.9.148, sccache 0.18.0, cargo-rail 0.31.1, moon 2.6.2,
  Bazel 9.3.0 + rules_rust 0.74.0, Buck2 2026-10-15 + Reindeer v2026.10.12.00,
  bazel-remote 2.6.3 as the shared REAPI cache.
- Corpora: ruff @ d1e1b1f6, rust-analyzer @ dd5ed69d, ripgrep @ 3fce3b5b (smoke).
- Decision rule: hermetic tool must beat the best Cargo-native tool by more than
  20% on replay-fresh total time to justify building a new tool.
