#!/usr/bin/env bash
# Resolve a GitHub review thread
# Usage: ./resolve-thread.sh <pr_number> <thread_id> [message]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/github-api.sh"

PR_NUMBER="${1:-}"
THREAD_ID="${2:-}"
MESSAGE="${3:-Fixed}"

if [[ -z "$PR_NUMBER" || -z "$THREAD_ID" ]]; then
  echo "Usage: $0 <pr_number> <thread_id> [message]" >&2
  exit 1
fi

WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
THREADS_FILE="$WORKSPACE_DIR/threads.json"
API_CAPS_FILE="$WORKSPACE_DIR/api-capabilities.txt"

# Check if state is initialized
if [[ ! -f "$THREADS_FILE" || ! -f "$API_CAPS_FILE" ]]; then
  echo "⚠️  PR state not initialized. Run init-pr-state.sh first." >&2
  exit 1
fi

# Get comment ID for this thread
COMMENT_ID=$(jq -r "select(.threadId == \"$THREAD_ID\") | .commentId" "$THREADS_FILE")

if [[ -z "$COMMENT_ID" || "$COMMENT_ID" == "null" ]]; then
  echo "❌ Thread ID not found: $THREAD_ID" >&2
  exit 1
fi

# Check if threaded replies are available
CAPABILITY=$(cat "$API_CAPS_FILE")

if [[ "$CAPABILITY" == "enabled" ]]; then
  echo "Adding threaded reply: $MESSAGE"
  if try_threaded_reply "$PR_NUMBER" "$COMMENT_ID" "$MESSAGE"; then
    echo "✅ Threaded reply added"
  else
    echo "⚠️  Threaded reply failed, falling back to direct resolution"
  fi
fi

# Resolve the thread
echo "Resolving thread..."
resolve_thread "$THREAD_ID"
echo "✅ Thread resolved: $THREAD_ID"
