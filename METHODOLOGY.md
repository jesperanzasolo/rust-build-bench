# Methodology

This document is normative. If the code and this document disagree, the code has a
bug. Changes to anything here are listed in [CHANGELOG.md](CHANGELOG.md) and
invalidate comparisons with earlier runs.

## Question

How much CI time and compute does each tool save on a real Rust monorepo, for the
work CI actually does on every pull request, **without ever reporting a stale test
result**? A pre-registered rule then turns the answer into one decision: adopt the
best existing Cargo-native tool, or build a new one.

## Tools

| Tool | Family | What it is configured to do |
|---|---|---|
| `cargo` | baseline | `cargo nextest run --workspace` on every commit. No caching beyond Cargo's own `target/`. |
| `cargo-sccache` | baseline | Same, with `RUSTC_WRAPPER=sccache` and a shared sccache directory. |
| `cargo-rail` | cargo-native | `cargo rail plan` selects affected work; nextest runs exactly the plan's `cargo.test` selection; verified compiler-result reuse enrolled with `cargo rail cache setup`; planning evidence recorded per commit as its docs prescribe for CI. |
| `moon` | cargo-native | One `test` task per crate (`cargo nextest run -p <crate>`) with transitive workspace inputs; `moon ci` with `--base/--head`; REAPI remote cache. |
| `bazel` | hermetic | rules_rust + crate_universe, Bzlmod; BUILD files generated from `cargo metadata`; `bazel test //...`; REAPI remote cache. |
| `buck2` | hermetic | Prelude Rust rules + Reindeer for third-party crates; BUCK files generated from `cargo metadata`; `buck2 test //...`; REAPI remote cache (local execution). |

Every tool is configured the way its own documentation recommends for CI. Where a
tool needs configuration that does not exist in the corpus (moon, Bazel, Buck2),
the harness generates it from `cargo metadata`, deterministically, and the generated
files are kept with the results. Maintainers of each tool are invited to review and
improve their adapter (see [CONTRIBUTING.md](CONTRIBUTING.md)); improvements are
applied to the next run, never retroactively to published numbers.

Versions are pinned in [`tools/versions.toml`](tools/versions.toml). The sha256 of
every installed executable is recorded in each result's `provenance.json`.

## Corpora

| Corpus | Why it is included |
|---|---|
| [`ruff`](corpora/ruff.toml) | 55 crates, ~350 third-party crates, heavy snapshot and fixture tests, build scripts, a proc-macro crate. Representative of a large product monorepo. |
| [`rust-analyzer`](corpora/rust-analyzer.toml) | 45 crates with a deep dependency chain (`hir-*` to `ide-*`) and thousands of fast unit tests. Stresses invalidation precision. |
| [`ripgrep`](corpora/ripgrep.toml) | Smoke test only. Never published. |

Each corpus is pinned to a commit. The **replay window** is the N first-parent
commits ending at that commit: N real merged pull requests, in order, exactly as
CI on the default branch saw them. No synthetic edits are used for timing.

Test scope is identical for every tool and comes from the corpus file: the same
crates, the same feature flags (e.g. ruff's CI uses `--all-features`), the same
skipped tests. Host tools the corpus' tests call (e.g. `uv` for ruff) are pinned
and placed first on `PATH` for every tool, including inside Bazel's test sandbox.

## Scenarios

Run in this order for each (corpus, tool) on a dedicated machine:

1. **cold**: all local state and shared caches deleted; full test suite at the first
   commit of the window. A new CI cache or new developer machine.
2. **noop**: the same commit again, nothing changed (median of 3). Fixed overhead.
3. **replay-warm**: for each commit of the window, keep all local state and run the
   tool's change-based test command for the previous commit to this one. A sticky CI
   runner or a developer machine.
4. **replay-fresh** (headline metric): shared caches reset, then seeded by one
   untimed build of the commit before the measured range. For each of the last 10
   commits: delete all local state, check out, run. Each run fills the shared cache
   for the next one, as post-merge CI on main would. An ephemeral CI runner with a
   remote cache.
5. **canary**: correctness, below.

"Local state" is what a fresh CI runner does not have: `target/`, `bazel-out`,
`buck-out`, daemons, moon's local cache. "Shared caches" are what CI restores or
reaches over the network: the REAPI cache server, the sccache directory,
cargo-rail's result store and planning evidence. Download caches (Cargo registry,
Bazel repository cache, vendored crates, toolchains) are always kept, for every
tool, because every real CI setup caches them and they are not what is measured.

### Shared caches

Bazel, Buck2 and moon talk to the same REAPI server implementation
([bazel-remote](https://github.com/buchgr/bazel-remote)) on the same machine, so
none of them gets a network advantage. cargo-rail's remote store only accepts
AWS S3, Cloudflare R2 or Azure endpoints, so it is given its persisted local result
store instead, which is the same zero-latency case. sccache uses a local directory.
Real remote caches add latency and bandwidth limits; every tool here is measured
at that best case, which favours tools with larger cached artifacts. Sizes of all
caches are reported so the trade-off is visible.

## Correctness canary

On top of the last commit the harness creates three commits:

- **K1** adds `pub const RBB_CANARY: u32 = 1` to an upstream crate, and to a direct
  dependent a new integration test that panics with `RBB_CANARY_MISMATCH` unless
  the constant is 1. Expected: pass.
- **K2** changes the constant to 2. Expected: **fail**, with the panic message in the
  tool's output, proving the dependent test was rebuilt and actually executed.
- **K3** changes it back to 1. Expected: pass.

K1 to K3 run with warm local state; K2 is then run again on a fresh runner (local
state deleted, shared cache kept). A tool that reports K2 as passing, in either
mode, served a stale result. **A tool with any canary failure is not eligible in the
decision**, whatever its speed: a cache that hides failures is worse than no cache.

## Measurements

Per timed step: wall time of the tool's commands; machine-wide CPU seconds and peak
memory (machine-wide because Bazel and Buck2 do their work in daemons the harness
does not spawn); exit code; tool-reported test and cache counts; untimed config
generation (`sync_s`, reported separately as an adoption cost); bytes of every
state directory and cache after each scenario.

Untimed: checkout, config generation, wiping state, the replay-fresh seed build.

Timed work a tool needs in the PR job is part of its step, even if it is not a
test: planning, analysis, project-graph construction, cache uploads. Work a tool's
documentation assigns to the post-merge default-branch job instead (cargo-rail's
planning-evidence recording) is measured and reported separately as
`post_merge_s`, not added to PR time.

## Machines

One run of one tool owns one machine: same shape for all tools (Namespace devbox
`M`: 8 vCPU, 16 GiB, Ubuntu 24.04, x86_64), nothing else running. Each machine runs
a fixed CPU calibration workload first; it is reported with the results so noisy
machines can be spotted. Numbers are not normalised by it.

## Decision rule (pre-registered)

For each corpus:

1. Drop ineligible tools: any canary failure, or (when the `cargo` baseline passes
   every non-canary step, i.e. the corpus has no failing or flaky tests) a cold run
   that fails.
2. **B** = the eligible baseline or Cargo-native tool with the lowest replay-fresh
   total time. **H** = the eligible hermetic tool with the lowest replay-fresh
   total time.
3. If H is more than **20%** faster than B: **Build yourself**. A hermetic build
   system shows PR-CI headroom that no Cargo-native tool captures, and a
   Cargo-native tool that captures it without a build-system migration has room to
   exist. The gap is the target.
4. Otherwise: **Use B**.

If the two corpora disagree, the overall verdict is "mixed" and both are reported.
The threshold and the metric were fixed before any full run.

## Known limitations

- Each tool is run in one reasonable configuration. Expert tuning can change
  results; adapters are open to improvement for future runs.
- The local REAPI server is a best case for remote caching (no network latency).
- Hermetic tools need generated configuration that the corpus does not maintain;
  some tests that only work under Cargo (e.g. a test that runs `cargo build`) fail
  there and are reported, not hidden.
- Bazel and Buck2 report test results per test binary, nextest per test case; counts
  are reported in each tool's own unit and are not compared directly.
- Single run per configuration for long scenarios; variance is estimated from the
  noop samples and the replay distribution, not from repeated full runs.
