#!/usr/bin/env bash
# query.sh — find-references / go-to-definition against the current repo's SCIP index.
# Wraps scip_query.py, auto-resolving --index from repo context so the caller only
# supplies the actual query.
#
# Usage:
#   query.sh at <file>:<line>:<col>
#   query.sh symbol <substring>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

REPO_ROOT="$(scip_repo_root)"
INDEX_PATH="$(scip_index_path "$REPO_ROOT")"

if [[ ! -f "$INDEX_PATH" ]]; then
  echo "No SCIP index found for $(basename "$REPO_ROOT") — run the 'run' operation first." >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/scip_query.py" --index "$INDEX_PATH" "$@"
