#!/usr/bin/env bash
# index.sh — build (or rebuild) the SCIP index for the current repo. Backs both the
# skill's "run" and "refresh" operations — they are the same operation under two names,
# since scip-java has no incremental/watch mode: every call is a full rebuild.
#
# Deliberately no module-scoping flags (-pl/-am) — validated unnecessary on both a
# single-module repo and a 6-module Maven reactor. Only add scoping if the plain
# invocation genuinely fails on a real repo, and say so explicitly if it does.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if ! command -v scip-java >/dev/null 2>&1; then
  echo "scip-java not found on PATH — run the 'setup' operation first." >&2
  exit 1
fi

REPO_ROOT="$(scip_repo_root)"
CACHE_DIR="$(scip_cache_dir "$REPO_ROOT")"
INDEX_PATH="$(scip_index_path "$REPO_ROOT")"

mkdir -p "$CACHE_DIR"

# Note whether an index already exists, and from when — deliberately not deleted up
# front. A genuine scip-java/build crash (nonzero exit) aborts the script right here via
# `set -e`, before either check below ever runs, so any previously valid index survives
# that failure mode untouched. The checks below instead catch the *other* failure mode
# this script exists for: scip-java exiting 0 having done nothing.
PREVIOUS_MTIME=""
if [[ -f "$INDEX_PATH" ]]; then
  PREVIOUS_MTIME="$(scip_mtime_epoch "$INDEX_PATH")"
fi

echo "Indexing $(basename "$REPO_ROOT")..."
echo "(this runs a full build under the hood — e.g. 'mvn clean verify -DskipTests' — not a fast operation)"
( cd "$REPO_ROOT" && scip-java index --output "$INDEX_PATH" )

if [[ ! -f "$INDEX_PATH" ]]; then
  echo "" >&2
  echo "scip-java exited 0 but did not write an index to $INDEX_PATH — indexing silently failed." >&2
  echo "This usually means scip-java's automatic build-tool configuration never took effect for this" >&2
  echo "repo — see SKILL.md's Known Constraints section for confirmed causes and workarounds." >&2
  exit 1
fi

if [[ -n "$PREVIOUS_MTIME" ]] && [[ "$(scip_mtime_epoch "$INDEX_PATH")" == "$PREVIOUS_MTIME" ]]; then
  echo "" >&2
  echo "scip-java exited 0 but left $INDEX_PATH unchanged from a prior run — indexing silently" >&2
  echo "failed this time (the file on disk is stale, not fresh). See SKILL.md's Known Constraints" >&2
  echo "section for confirmed causes and workarounds." >&2
  exit 1
fi

echo ""
echo "Index written to $INDEX_PATH"
