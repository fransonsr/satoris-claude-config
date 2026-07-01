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
# Strip leading zeros now that the digits-only check has passed — bash's arithmetic/test
# operators treat a leading-zero numeral as octal, so "08"/"09" would otherwise crash
# `-gt`/`(( ))` below with "value too great for base" despite passing the regex above.
DIRECTIONAL_COUNT=$((10#$DIRECTIONAL_COUNT))

WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
ROUND_FILE="$WORKSPACE_DIR/round.txt"
FIXES_FILE="$WORKSPACE_DIR/fixes.json"

# Check if state is initialized
if [[ ! -f "$ROUND_FILE" ]]; then
  echo "⚠️  PR state not initialized. Run init-pr-state.sh first." >&2
  exit 1
fi

# fixes.json may not exist yet on this PR's first round — initialize it rather than letting
# the tracking-write jq below fail on a missing file only after the commit has already happened.
[[ -f "$FIXES_FILE" ]] || echo '{}' > "$FIXES_FILE"

ROUND=$(cat "$ROUND_FILE")

if git diff --cached --quiet; then
  # Nothing staged. Two cases: (a) genuinely nothing to commit yet, or (b) this round's commit
  # already succeeded on a prior run of this script and only the fixes.json tracking write
  # failed afterward — a bare re-run would otherwise hit "nothing to commit" and abort without
  # ever retrying the tracking write. Recover case (b) by tracking the existing HEAD instead.
  if git log -1 --format=%s 2>/dev/null | grep -qF "Round ${ROUND})"; then
    echo "ℹ️  Nothing staged, but HEAD is already this round's commit — recovering fixes.json tracking for it instead of creating a new commit."
    COMMIT_SHA=$(git rev-parse HEAD)
    CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | jq -R . | jq -s .)
  else
    echo "⚠️  Nothing staged to commit, and HEAD is not this round's commit. Stage your fixes with 'git add' first." >&2
    exit 1
  fi
else
  COMMIT_MSG="fix: Address PR #${PR_NUMBER} review feedback (Round ${ROUND})

Co-Authored-By: Claude <noreply@anthropic.com>"

  echo "Commit message:"
  echo "---"
  echo "$COMMIT_MSG"
  echo "---"
  echo ""

  read -p "Create commit with this message? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Commit cancelled"
    exit 1
  fi

  git commit -m "$COMMIT_MSG"
  echo "✅ Commit created"
  COMMIT_SHA=$(git rev-parse HEAD)
  CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD | jq -R . | jq -s .)
fi

# Update fix tracking. If this fails, the commit above has ALREADY happened — say so loudly
# rather than letting `set -e` exit on a bare jq error that leaves the operator unsure whether
# the commit itself succeeded.
if ! jq --arg round "$ROUND" --arg sha "$COMMIT_SHA" --argjson files "$CHANGED_FILES" \
     --argjson directionalCount "$DIRECTIONAL_COUNT" \
    '. + {($round): {commit: $sha, files: $files, directional_count: $directionalCount, timestamp: now|todate}}' \
    "$FIXES_FILE" > "$FIXES_FILE.tmp"; then
  echo "🛑 Commit $COMMIT_SHA succeeded, but updating $FIXES_FILE failed — directional_count for round $ROUND was NOT persisted. Step 8 will read 0 and may skip the Copilot re-request. Re-run this script to retry the tracking write; it will recover using the existing commit instead of erroring on 'nothing to commit'." >&2
  rm -f "$FIXES_FILE.tmp"
  exit 1
fi
mv "$FIXES_FILE.tmp" "$FIXES_FILE"

if [[ "$DIRECTIONAL_COUNT" -gt 0 ]]; then
  echo "✅ Recorded $DIRECTIONAL_COUNT directional fix(es) this round. Step 8 will re-request Copilot review unless the re-review cap (review #3+) has already been reached, in which case it escalates to /plan instead."
fi

echo "✅ Fix tracking updated"
