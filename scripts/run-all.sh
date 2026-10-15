#!/usr/bin/env bash
# Run every tool on every corpus, one after another, on this machine, publishing
# results after each (corpus, tool) so a lost machine loses at most one pair.
#
#   scripts/run-all.sh <run-id> [corpora] [tools]
set -uo pipefail
RUN_ID=${1:?run id}
CORPORA=${2:-ruff,rust-analyzer}
TOOLS=${3:-cargo,cargo-sccache,cargo-rail,moon,bazel,buck2}
cd "$(dirname "$0")/.."
IFS=, read -ra corpora <<<"$CORPORA"
for c in "${corpora[@]}"; do
  RBB_PUBLISH=1 ./run.sh "$RUN_ID" "$c" "$TOOLS" bench.toml
done
echo "ALL DONE"
