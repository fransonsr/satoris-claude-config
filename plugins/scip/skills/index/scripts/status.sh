#!/usr/bin/env bash
# status.sh — report SCIP index state for the current repo. Read-only: never builds an
# index, never touches the network.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

REPO_ROOT="$(scip_repo_root)"
INDEX_PATH="$(scip_index_path "$REPO_ROOT")"

if [[ ! -f "$INDEX_PATH" ]]; then
  echo "No SCIP index found for $(basename "$REPO_ROOT")."
  echo "Expected at: $INDEX_PATH"
  echo "Run the 'run' operation to build one."
  exit 0
fi

SIZE="$(du -h "$INDEX_PATH" | cut -f1)"
MTIME_EPOCH="$(scip_mtime_epoch "$INDEX_PATH")"
NOW_EPOCH="$(date +%s)"
AGE_SECONDS=$(( NOW_EPOCH - MTIME_EPOCH ))
BUILT_AT="$(date -d "@$MTIME_EPOCH" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$MTIME_EPOCH" '+%Y-%m-%d %H:%M:%S')"

echo "Index: $INDEX_PATH"
echo "Size: $SIZE"
echo "Built: $BUILT_AT ($((AGE_SECONDS / 3600))h $(((AGE_SECONDS % 3600) / 60))m ago)"
echo ""

if command -v scip >/dev/null 2>&1; then
  scip stats --from "$INDEX_PATH"
else
  echo "('scip' not found on PATH — skipping stats; run 'setup' to install it)"
fi
