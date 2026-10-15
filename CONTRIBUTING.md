# Contributing

## Ground rules

- **Fairness first.** Each tool is configured the way its own documentation
  recommends for CI. If you maintain or know a tool well and its adapter is not
  how you would run it, open a PR: that is the most valuable contribution.
- **No retroactive changes.** Published results are never edited. Improvements
  apply to the next run, and the CHANGELOG records what changed.
- **Same test scope for everyone.** Adapters may change *how* tests run, never
  *which* tests run. Scope comes from the corpus file.
- **Pinned everything.** New tools need an exact version, a download URL and,
  where the project publishes them, checksums.

## Adding a tool

1. Write `rbb/adapters/<tool>.py` implementing `Adapter` (see the docstring in
   `rbb/adapters/base.py`): `versions`, `sync`, `test`, `wipe_local`, `wipe_all`,
   `state_dirs`, and optionally `setup`, `env`, `services`.
   - `test(base, head)` runs the tool's recommended CI command for a change from
     `base` to `head`; `base=None` means test everything.
   - `wipe_local` must delete exactly what a fresh CI runner would not have, and
     nothing it would (download caches, shared/remote caches).
2. Register it in `rbb/adapters/__init__.py`, pin its binaries in
   `tools/versions.toml` and list them in `rbb/install.py` (`NEEDS`).
3. Add unit tests under `tests/` for any config generation.
4. Run the smoke protocol: `./run.sh smoke ripgrep <tool> bench-smoke.toml`. All
   canary verdicts must pass.

## Adding a corpus

A corpus is a TOML file in `corpora/`: repository, pinned commit, window size, the
test scope its own CI uses (`cargo_args`, `env`, `skip_tests`), the canary crate
pair, and `extra_data` for runtime file reads that cross crate boundaries (needed
only by hermetic tools). Good corpora are public, widely known, test-heavy Cargo
workspaces whose own CI runs on Linux.

## Development

```bash
python3 -m unittest discover -s tests -t .
python3 -m rbb list
```

The harness uses only the Python standard library so it can run on any CI image
without an install step.
