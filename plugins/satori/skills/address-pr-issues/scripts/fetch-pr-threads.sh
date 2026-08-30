#!/usr/bin/env bash
# Fetch and display PR review threads
# Usage: ./fetch-pr-threads.sh <pr_number> [--unresolved-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/github-api.sh"

PR_NUMBER="${1:-}"
UNRESOLVED_ONLY="${2:-}"

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number> [--unresolved-only]" >&2
  exit 1
fi

WORKSPACE_DIR="$(pr_workspace_dir "$PR_NUMBER")"
THREADS_FILE="$WORKSPACE_DIR/threads.json"

# Check if threads are cached
if [[ ! -f "$THREADS_FILE" ]]; then
  echo "⚠️  No cached threads found. Run init-pr-state.sh first." >&2
  exit 1
fi

# Display threads
if [[ "$UNRESOLVED_ONLY" == "--unresolved-only" ]]; then
  echo "Unresolved Copilot Threads:"
  echo ""
  jq -r 'select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]") | select(.isResolved == false) |
    "Thread ID: \(.threadId)\nFile: \(.path):\(.line)\nSummary: \(.bodySummary)\nResolved: \(.isResolved)\n"' "$THREADS_FILE"
else
  echo "All Copilot Threads:"
  echo ""
  jq -r 'select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]") |
    "Thread ID: \(.threadId)\nFile: \(.path):\(.line)\nSummary: \(.bodySummary)\nResolved: \(.isResolved)\n"' "$THREADS_FILE"
fi

# Summary
TOTAL=$(jq -s 'map(select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]")) | length' "$THREADS_FILE")
RESOLVED=$(jq -s 'map(select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]") | select(.isResolved == true)) | length' "$THREADS_FILE")
UNRESOLVED=$(jq -s 'map(select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]") | select(.isResolved == false)) | length' "$THREADS_FILE")

echo ""
echo "Summary: $RESOLVED/$TOTAL resolved, $UNRESOLVED unresolved"
