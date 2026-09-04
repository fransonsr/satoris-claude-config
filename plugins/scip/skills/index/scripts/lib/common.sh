#!/usr/bin/env bash
# common.sh — shared repo-context resolution for the scip skill's scripts. Source, don't execute.
#
# Every scip operation is scoped to "whatever repo the current working directory is inside" —
# these three functions are the single place that scoping is resolved, so setup/index/status/
# cleanup/query all agree on where a repo's index lives.

scip_repo_root() {
  local root
  if ! root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    echo "Not inside a git repository — cd into the repo you want to index first." >&2
    return 1
  fi
  echo "$root"
}

scip_cache_dir() {
  local repo_root="$1"
  echo "$HOME/.cache/scip/$(basename "$repo_root")"
}

scip_index_path() {
  local repo_root="$1"
  echo "$(scip_cache_dir "$repo_root")/index.scip"
}

# GNU stat (`-c`) on Linux, BSD stat (`-f`) on macOS — only one of the two will succeed.
scip_mtime_epoch() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"
}
