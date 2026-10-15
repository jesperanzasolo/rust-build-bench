#!/usr/bin/env bash
# Publish results to a branch, run/<run-id>/<name>, from a temporary worktree so
# the main checkout (and a run in progress) is never touched. Logs are copied
# gzipped; results.jsonl and provenance.json stay plain text. Safe to repeat.
#
#   scripts/collect.sh <run-id> <tool|all>
set -euo pipefail
RUN_ID=${1:?run id}
NAME=${2:?tool or all}
cd "$(dirname "$0")/.."
root=$PWD
tmp=$(mktemp -d)
trap 'git -C "$root" worktree remove --force "$tmp" >/dev/null 2>&1 || true' EXIT
git worktree add -q --detach "$tmp" HEAD
branch="run/$RUN_ID/$NAME"
git -C "$tmp" checkout -q -B "$branch"
dest="$tmp/results/$RUN_ID"
mkdir -p "$dest"
src="results/$RUN_ID"
if [ "$NAME" = all ]; then
  (cd "$src" && find . -type f -print0) > "$tmp/.files"
else
  (cd "$src" && find . -type f -path "*/$NAME/*" -print0; find . -maxdepth 1 -type f -name "job-$NAME.log" -print0) > "$tmp/.files"
fi
while IFS= read -r -d '' f; do
  mkdir -p "$dest/$(dirname "$f")"
  case "$f" in
    *.log) gzip -9 -c "$src/$f" > "$dest/$f.gz" ;;
    *) cp "$src/$f" "$dest/$f" ;;
  esac
done < "$tmp/.files"
for f in results/"$RUN_ID".*.console.log; do
  [ -e "$f" ] || continue
  case "$NAME" in all) ;; *) [[ "$f" == *".$NAME.console.log" ]] || continue ;; esac
  gzip -9 -c "$f" > "$dest/$(basename "$f").gz"
done
rm -f "$tmp/.files"
git -C "$tmp" add -f "results/$RUN_ID"
git -C "$tmp" -c commit.gpgsign=false commit -q -m "results: $RUN_ID $NAME" || true
git -C "$tmp" push -q -f origin "$branch"
echo "pushed $branch"
