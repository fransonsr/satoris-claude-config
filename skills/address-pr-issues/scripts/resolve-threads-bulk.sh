#!/usr/bin/env bash
# Resolve multiple GitHub review threads at once
# Usage: ./resolve-threads-bulk.sh <pr_number> [options]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/github-api.sh"

PR_NUMBER="${1:-}"
shift || true

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number> [options]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --threads <id1,id2,...>     Resolve specific thread IDs (comma-separated)" >&2
  echo "  --file <path>               Read thread IDs from file (one per line)" >&2
  echo "  --filter-path <pattern>     Resolve threads where file path matches pattern" >&2
  echo "  --filter-line <start-end>   Resolve threads in line range (e.g., 200-300)" >&2
  echo "  --all-unresolved            Resolve ALL unresolved threads" >&2
  echo "  --message <msg>             Message for all resolutions (default: 'Fixed')" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  # Resolve specific threads" >&2
  echo "  $0 68 --threads 'PRRT_abc,PRRT_def' --message 'Fixed integration tests'" >&2
  echo "" >&2
  echo "  # Resolve all threads in a file" >&2
  echo "  $0 68 --filter-path 'FullExportJobIntegrationTest.java' --message 'Fixed tests'" >&2
  echo "" >&2
  echo "  # Resolve all unresolved threads" >&2
  echo "  $0 68 --all-unresolved --message 'Addressed all review feedback'" >&2
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

# Parse options
THREAD_IDS=""
FILE_PATH=""
FILTER_PATH=""
FILTER_LINE=""
ALL_UNRESOLVED=false
MESSAGE="Fixed"

while [[ $# -gt 0 ]]; do
  case $1 in
    --threads)
      THREAD_IDS="$2"
      shift 2
      ;;
    --file)
      FILE_PATH="$2"
      shift 2
      ;;
    --filter-path)
      FILTER_PATH="$2"
      shift 2
      ;;
    --filter-line)
      FILTER_LINE="$2"
      shift 2
      ;;
    --all-unresolved)
      ALL_UNRESOLVED=true
      shift
      ;;
    --message)
      MESSAGE="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Build thread ID list based on options
THREADS_TO_RESOLVE=()

if [[ -n "$THREAD_IDS" ]]; then
  # Split comma-separated IDs
  IFS=',' read -ra THREADS_TO_RESOLVE <<< "$THREAD_IDS"
elif [[ -n "$FILE_PATH" ]]; then
  # Read from file
  if [[ ! -f "$FILE_PATH" ]]; then
    echo "❌ File not found: $FILE_PATH" >&2
    exit 1
  fi
  mapfile -t THREADS_TO_RESOLVE < "$FILE_PATH"
elif [[ -n "$FILTER_PATH" ]]; then
  # Filter by file path
  mapfile -t THREADS_TO_RESOLVE < <(jq -r "select(.isResolved == false) | select(.path | contains(\"$FILTER_PATH\")) | .threadId" "$THREADS_FILE")
elif [[ -n "$FILTER_LINE" ]]; then
  # Filter by line range
  if [[ ! "$FILTER_LINE" =~ ^([0-9]+)-([0-9]+)$ ]]; then
    echo "❌ Invalid line range format. Use: start-end (e.g., 200-300)" >&2
    exit 1
  fi
  START_LINE="${BASH_REMATCH[1]}"
  END_LINE="${BASH_REMATCH[2]}"
  mapfile -t THREADS_TO_RESOLVE < <(jq -r "select(.isResolved == false) | select(.line >= $START_LINE and .line <= $END_LINE) | .threadId" "$THREADS_FILE")
elif [[ "$ALL_UNRESOLVED" == true ]]; then
  # Resolve all unresolved threads
  mapfile -t THREADS_TO_RESOLVE < <(jq -r 'select(.isResolved == false) | .threadId' "$THREADS_FILE")
else
  echo "❌ No threads specified. Use --threads, --file, --filter-path, --filter-line, or --all-unresolved" >&2
  exit 1
fi

# Check if any threads found
if [[ ${#THREADS_TO_RESOLVE[@]} -eq 0 ]]; then
  echo "⚠️  No threads to resolve (filter matched zero threads)" >&2
  exit 0
fi

echo "📍 Resolving ${#THREADS_TO_RESOLVE[@]} thread(s) with message: \"$MESSAGE\""
echo ""

# Resolve each thread
RESOLVED_COUNT=0
FAILED_COUNT=0

for thread_id in "${THREADS_TO_RESOLVE[@]}"; do
  # Trim whitespace
  thread_id=$(echo "$thread_id" | xargs)

  if [[ -z "$thread_id" ]]; then
    continue
  fi

  # Get thread details for display
  THREAD_PATH=$(jq -r "select(.threadId == \"$thread_id\") | .path" "$THREADS_FILE")
  THREAD_LINE=$(jq -r "select(.threadId == \"$thread_id\") | .line" "$THREADS_FILE")

  echo -n "  Resolving: $THREAD_PATH:$THREAD_LINE ... "

  if resolve_thread "$thread_id" 2>/dev/null; then
    echo "✅"
    ((RESOLVED_COUNT++))

    # Update cache to mark thread as resolved
    jq --arg tid "$thread_id" \
      'if .threadId == $tid then .isResolved = true else . end' \
      "$THREADS_FILE" > "${THREADS_FILE}.tmp" && mv "${THREADS_FILE}.tmp" "$THREADS_FILE"
  else
    echo "❌ (failed)"
    ((FAILED_COUNT++))
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Resolved: $RESOLVED_COUNT thread(s)"
if [[ $FAILED_COUNT -gt 0 ]]; then
  echo "❌ Failed: $FAILED_COUNT thread(s)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
