# Results

One directory per published run: `results/<run-id>/`.

- `REPORT.md`: tables and the decision for that run.
- `summary.json`: the same, machine-readable.
- `<corpus>/<tool>/results.jsonl`: one record per step (schema `rbb.result/v1`).
- `<corpus>/<tool>/provenance.json`: harness commit, tool versions and binary
  hashes, corpus, replay window, machine, calibration.
- `<corpus>/<tool>/logs/`: full output of every command.

Smoke runs (`smoke-*`) validate orchestration and are not published.

Results are licensed CC BY 4.0.
