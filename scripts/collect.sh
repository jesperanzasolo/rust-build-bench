#!/usr/bin/env bash
# Publish one machine's results to its own branch: run/<run-id>/<tool>.
# Logs are gzipped; results.jsonl and provenance.json stay plain text.
#
#   scripts/collect.sh <run-id> <tool>
set -euo pipefail
RUN_ID=${1:?run id}
TOOL=${2:?tool}
cd "$(dirname "$0")/.."
find "results/$RUN_ID" -path "*/$TOOL/*" -name '*.log' -print0 | xargs -0 -r gzip -9 -f
for f in results/"$RUN_ID".*."$TOOL".console.log; do
  [ -e "$f" ] && gzip -9 -f "$f" && mv "$f.gz" "results/$RUN_ID/"
done
branch="run/$RUN_ID/$TOOL"
git checkout -q -B "$branch"
git add -f "results/$RUN_ID"
git -c commit.gpgsign=false commit -q -m "results: $RUN_ID $TOOL" || true
git push -q -f origin "$branch"
echo "pushed $branch"
