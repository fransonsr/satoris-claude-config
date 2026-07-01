#!/usr/bin/env bash
# Classify cached PR threads into silent / already-resolved / keep buckets (SKILL.md Step 1.6).
# Deterministic — no LLM judgment needed. Writes `bucket` and `labels` fields back into
# threads.json so downstream steps (resolve-threads-bulk.sh, Step 3 triage) can filter by them.
#
# Usage: ./classify-threads.sh <pr_number> <pr_author>

set -euo pipefail

PR_NUMBER="${1:-}"
PR_AUTHOR="${2:-}"

if [[ -z "$PR_NUMBER" || -z "$PR_AUTHOR" ]]; then
  echo "Usage: $0 <pr_number> <pr_author>" >&2
  echo "  <pr_author> = the PR author's login, e.g. from: gh pr view N --json author -q .author.login" >&2
  exit 1
fi

WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
THREADS_FILE="$WORKSPACE_DIR/threads.json"

if [[ ! -f "$THREADS_FILE" ]]; then
  echo "⚠️  No cached threads found. Run init-pr-state.sh first." >&2
  exit 1
fi

# "Purely complimentary" definition (SKILL.md Step 1.6): none of a question mark, a trigger
# word, a file/line reference, or conditional language. Any one present -> substantive.
#
# Two hardenings beyond the SKILL.md definition, both because this is an executable filter with
# no human judgment fallback (a false positive here means a real comment is auto-resolved with
# nobody looking at it):
# 1. Trigger list expanded with common critique/necessity words ("should", "needs", "missing",
#    "wrong", "bug", etc.) — the original list is action-verb-only and misses phrasing like
#    "this should validate input", which contains no listed verb but is clearly substantive.
# 2. Word-count guard: genuine compliments ("LGTM", "Nice work", "👍") are almost always short.
#    Cap complimentary classification at 8 words as an independent second signal.
# Both err toward the safe side (more threads land in `keep`, not fewer) — and any thread
# resolved via the silent bucket still surfaces in Step 6's accountability closeout table, so a
# misclassification is visible, not silently lost.
jq -c --arg prAuthor "$PR_AUTHOR" '
def is_complimentary(text):
  (
    (text | test("\\?"))
    or (text | test("\\b(add|remove|change|fix|update|rename|refactor|replace|consider|check|verify|ensure|move|revert|should|shouldn.t|needs?|missing|must|wrong|incorrect|bug|issue|problem|broken|fails?|failing)\\b"; "i"))
    or (text | test("\\b(but|however|though|although|unless)\\b"; "i"))
    or (text | test("[A-Za-z0-9_/.-]+\\.[A-Za-z0-9]{1,6}:[0-9]+|\\bline[s]?\\s+[0-9]+\\b"; "i"))
    or ((text | [scan("\\S+")] | length) > 8)
  ) | not;

. as $t
| ($t.lastCommentAuthor // $t.author) as $lastAuthor
| ($t.lastCommentBody // $t.bodyFull // "") as $lastText
| is_complimentary($lastText) as $complimentary
| if ($t.isResolved == true) and ($lastAuthor == $prAuthor or $complimentary) then
    $t + {bucket: "already_resolved", labels: []}
  elif ($t.isResolved == false) and $complimentary then
    $t + {bucket: "silent", labels: []}
  else
    $t + {bucket: "keep", labels: (
        (if ($t.isOutdated == true) and ($t.isResolved == false) then ["outdated"] else [] end)
        + (if ($t.isResolved == true) and ($lastAuthor != $prAuthor) and ($complimentary | not) then ["resolved_new_activity"] else [] end)
      )}
  end
' "$THREADS_FILE" > "${THREADS_FILE}.tmp" && mv "${THREADS_FILE}.tmp" "$THREADS_FILE"

SILENT=$(jq -s 'map(select(.bucket == "silent")) | length' "$THREADS_FILE")
ALREADY_RESOLVED=$(jq -s 'map(select(.bucket == "already_resolved")) | length' "$THREADS_FILE")
KEEP=$(jq -s 'map(select(.bucket == "keep")) | length' "$THREADS_FILE")

echo "$SILENT silent threads handled, $ALREADY_RESOLVED already-resolved skipped — $KEEP substantive threads to triage."
echo ""
echo "Silent thread IDs (react + resolve, no user prompt):"
jq -r 'select(.bucket == "silent") | .threadId' "$THREADS_FILE"
