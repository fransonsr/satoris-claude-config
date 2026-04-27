#!/usr/bin/env bash
# Generate structured commit message for PR fixes
# Usage: ./commit-pr-fixes.sh <pr_number>

set -euo pipefail

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number>" >&2
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
    '. + {($round): {commit: $sha, files: $files, timestamp: now|todate}}' \
    "$FIXES_FILE" > "$FIXES_FILE.tmp"
  mv "$FIXES_FILE.tmp" "$FIXES_FILE"

  echo "✅ Fix tracking updated"
else
  echo "❌ Commit cancelled"
  exit 1
fi
