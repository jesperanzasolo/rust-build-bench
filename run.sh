#!/usr/bin/env bash
# Run the benchmark on a dedicated Linux x86_64 machine.
#
#   ./run.sh <run-id> <corpus>[,<corpus>...] <tool>[,<tool>...] [bench.toml]
#
# Example (one machine per tool is the recommended layout):
#   ./run.sh 2026-10-15 ruff,rust-analyzer cargo-rail
#
# Results land in results/<run-id>/<corpus>/<tool>/. Nothing else on the machine
# may run while this runs (see METHODOLOGY.md, "Machines").
set -euo pipefail

RUN_ID=${1:?run id}
CORPORA=${2:?corpora}
TOOLS=${3:?tools}
BENCH=${4:-bench.toml}

cd "$(dirname "$0")"
export RBB_TOOLS=${RBB_TOOLS:-$HOME/.rbb-tools}
export RBB_WORK=${RBB_WORK:-$HOME/rbb-work}

if ! command -v zstd >/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y -qq zstd >/dev/null
fi
command -v rustup >/dev/null || { echo "rustup is required" >&2; exit 2; }

IFS=, read -ra corpora <<<"$CORPORA"
IFS=, read -ra tools <<<"$TOOLS"

python3 -m rbb install --prefix "$RBB_TOOLS" "${tools[@]}"

status=0
for c in "${corpora[@]}"; do
  for t in "${tools[@]}"; do
    echo "=== $c / $t ==="
    mkdir -p "results/$RUN_ID"
    if ! python3 -m rbb run --run-id "$RUN_ID" --corpus "$c" --tool "$t" --bench "$BENCH" \
        2>&1 | tee -a "results/$RUN_ID.$c.$t.console.log"; then
      echo "!!! $c / $t failed" >&2
      status=1
    fi
    if [ -n "${RBB_PUBLISH:-}" ]; then scripts/collect.sh "$RUN_ID" "${RBB_PUBLISH_NAME:-all}" || true; fi
  done
done
python3 -m rbb report "results/$RUN_ID" || true
exit $status
