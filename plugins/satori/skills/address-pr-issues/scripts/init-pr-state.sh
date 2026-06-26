#!/usr/bin/env bash
# Initialize PR workflow state management
# Usage: ./init-pr-state.sh <pr_number>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/github-api.sh"
source "$SCRIPT_DIR/lib/sonar-api.sh"

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number>" >&2
  exit 1
fi

# Setup workspace directory for this PR
WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
mkdir -p "$WORKSPACE_DIR"

echo "📍 Initializing PR workflow state for PR #$PR_NUMBER"

# Initialize round tracking
ROUND_FILE="$WORKSPACE_DIR/round.txt"
if [[ -f "$ROUND_FILE" ]]; then
  ROUND=$(($(cat "$ROUND_FILE") + 1))
  echo "   Continuing workflow - Round $ROUND"
else
  ROUND=1
  echo "   Starting workflow - Round $ROUND"
fi
echo "$ROUND" > "$ROUND_FILE"

# Cache thread metadata for reuse
THREADS_FILE="$WORKSPACE_DIR/threads.json"
echo "   Fetching PR threads..."
fetch_pr_threads "$PR_NUMBER" "$THREADS_FILE"

COPILOT_COUNT=$(jq -s 'map(select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]")) | length' "$THREADS_FILE")
echo "   ✅ Cached $COPILOT_COUNT Copilot threads"

# Test API capabilities (threaded replies)
API_CAPS_FILE="$WORKSPACE_DIR/api-capabilities.txt"
echo "   Testing API capabilities..."
CAPABILITY=$(test_threaded_reply_api "$THREADS_FILE")
echo "$CAPABILITY" > "$API_CAPS_FILE"

if [[ "$CAPABILITY" == "enabled" ]]; then
  echo "   ✅ Threaded replies enabled"
else
  echo "   ⚠️  Threaded replies disabled - will use direct resolution"
fi

# Initialize fix tracking
FIXES_FILE="$WORKSPACE_DIR/fixes.json"
if [[ ! -f "$FIXES_FILE" ]]; then
  echo '{}' > "$FIXES_FILE"
fi

# Initialize checklist
CHECKLIST_FILE="$WORKSPACE_DIR/checklist.json"
cat > "$CHECKLIST_FILE" <<EOF
{
  "tests_passing": false,
  "build_clean": false,
  "sonar_reviewed": false,
  "threads_resolved": false,
  "commit_ready": false
}
EOF

echo ""
echo "✅ Workspace initialized: $WORKSPACE_DIR"
echo ""
echo "Workspace files:"
echo "  - round.txt: Round $ROUND"
echo "  - threads.json: $COPILOT_COUNT Copilot threads"
echo "  - api-capabilities.txt: Threaded replies $CAPABILITY"
echo "  - fixes.json: Fix tracking initialized"
echo "  - checklist.json: Pre-commit checklist initialized"
