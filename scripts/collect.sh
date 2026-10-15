#!/usr/bin/env bash
# Publish results to a branch: run/<run-id>/<name>.
# Logs are gzipped; results.jsonl and provenance.json stay plain text.
#
#   scripts/collect.sh <run-id> <tool|all>
set -euo pipefail
RUN_ID=${1:?run id}
NAME=${2:?tool or all}
cd "$(dirname "$0")/.."
pattern="*/$NAME/*"
[ "$NAME" = all ] && pattern="*"
find "results/$RUN_ID" -path "$pattern" -name '*.log' -print0 | xargs -0 -r gzip -9 -f
for f in results/"$RUN_ID".*.console.log; do
  [ -e "$f" ] || continue
  case "$NAME" in all) ;; *) [[ "$f" == *".$NAME.console.log" ]] || continue ;; esac
  gzip -9 -f "$f" && mv "$f.gz" "results/$RUN_ID/"
done
branch="run/$RUN_ID/$NAME"
git checkout -q -B "$branch"
git add -f "results/$RUN_ID"
git -c commit.gpgsign=false commit -q -m "results: $RUN_ID $NAME" || true
git push -q -f origin "$branch"
git checkout -q main
echo "pushed $branch"
