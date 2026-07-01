#!/usr/bin/env bash
# Generate structured commit message for PR fixes
# Usage: ./commit-pr-fixes.sh <pr_number> [directional_count]
#
# <directional_count> (default 0) is the number of directional-classified fixes applied this
# round (SKILL.md Step 2/8) — persisted to fixes.json so Step 8's Copilot re-request decision
# survives a context compaction or a resumed session, instead of depending on conversation memory.

set -euo pipefail

PR_NUMBER="${1:-}"
DIRECTIONAL_COUNT="${2:-0}"

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number> [directional_count]" >&2
  exit 1
fi

if ! [[ "$DIRECTIONAL_COUNT" =~ ^[0-9]+$ ]]; then
  echo "⚠️  directional_count must be a non-negative integer, got: $DIRECTIONAL_COUNT" >&2
  exit 1
fi

WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
ROUND_FILE="$WORKSPACE_DIR/round.txt"

# Check if state is initialized
if [[ ! -f "$ROUND_FILE" ]]; then
  echo "⚠️  PR state not initialized. Run init-pr-state.sh first." >&2
  exit 1
fi

ROUND=$(cat "$ROUND_FILE")

# Generate commit message
COMMIT_MSG="fix: Address PR #${PR_NUMBER} review feedback (Round ${ROUND})

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

echo "Commit message:"
echo "---"
echo "$COMMIT_MSG"
echo "---"
echo ""

# Ask for confirmation
read -p "Create commit with this message? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  git commit -m "$COMMIT_MSG"
  echo "✅ Commit created"

  # Update fix tracking
  FIXES_FILE="$WORKSPACE_DIR/fixes.json"
  COMMIT_SHA=$(git rev-parse HEAD)
  CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | jq -R . | jq -s .)

  jq --arg round "$ROUND" --arg sha "$COMMIT_SHA" --argjson files "$CHANGED_FILES" \
     --argjson directionalCount "$DIRECTIONAL_COUNT" \
    '. + {($round): {commit: $sha, files: $files, directional_count: $directionalCount, timestamp: now|todate}}' \
    "$FIXES_FILE" > "$FIXES_FILE.tmp"
  mv "$FIXES_FILE.tmp" "$FIXES_FILE"

  if [[ "$DIRECTIONAL_COUNT" -gt 0 ]]; then
    echo "✅ Recorded $DIRECTIONAL_COUNT directional fix(es) — Step 8 should re-request Copilot review"
  fi

  echo "✅ Fix tracking updated"
else
  echo "❌ Commit cancelled"
  exit 1
fi
