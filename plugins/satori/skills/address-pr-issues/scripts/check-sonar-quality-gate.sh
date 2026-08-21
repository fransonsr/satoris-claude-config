#!/usr/bin/env bash
# Check SonarQube quality gate status for a PR
# Usage: ./check-sonar-quality-gate.sh <pr_number>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/sonar-api.sh"

PR_NUMBER="${1:-}"

if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <pr_number>" >&2
  exit 1
fi

WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
mkdir -p "$WORKSPACE_DIR"

QUALITY_GATE_FILE="$WORKSPACE_DIR/quality-gate.json"

echo "Fetching SonarQube quality gate status for PR #$PR_NUMBER..."
get_quality_gate_status "$PR_NUMBER" > "$QUALITY_GATE_FILE"

echo ""
# format_quality_gate_status returns 1 for ERROR / 2 for UNKNOWN status as its normal signal,
# not a script failure — under set -e a bare call would kill the script here, before the STATUS
# check below ever runs, so a FAILED gate would print "Quality Gate: FAILED" and then silently
# exit without ever fetching the blocking issues that caused it.
format_quality_gate_status "$QUALITY_GATE_FILE" || true

# Also fetch issues if quality gate failed
STATUS=$(jq -r '.projectStatus.status' "$QUALITY_GATE_FILE" 2>/dev/null)
if [[ "$STATUS" == "ERROR" ]]; then
  echo ""
  echo "Fetching blocking issues..."
  ISSUES_FILE="$WORKSPACE_DIR/sonar-issues.json"
  get_pr_issues "$PR_NUMBER" "HIGH" > "$ISSUES_FILE"
  format_issues "$ISSUES_FILE"
fi
