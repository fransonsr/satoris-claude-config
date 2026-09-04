#!/usr/bin/env bash
# cleanup.sh — remove the cached SCIP index for the current repo. Only ever touches
# ~/.cache/scip/<repo>/ — never the repo's own working tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

REPO_ROOT="$(scip_repo_root)"
CACHE_DIR="$(scip_cache_dir "$REPO_ROOT")"

if [[ ! -d "$CACHE_DIR" ]]; then
  echo "No cached index for $(basename "$REPO_ROOT") — nothing to clean up."
  exit 0
fi

rm -rf "$CACHE_DIR"
echo "Removed $CACHE_DIR"
