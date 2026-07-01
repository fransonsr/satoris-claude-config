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
# Hardenings beyond the SKILL.md definition, all because this is an executable filter with no
# human judgment fallback (a false positive here means a real comment is auto-resolved with
# nobody looking at it) — fail CLOSED (route to `keep`) on any degraded/ambiguous input, never
# fail open into the auto-resolving `silent` bucket:
# 1. Trigger list expanded with common critique/necessity words ("should", "needs", "missing",
#    "wrong", "bug", etc.) — the original list is action-verb-only and misses phrasing like
#    "this should validate input", which contains no listed verb but is clearly substantive.
# 2. Word-count guard: genuine compliments ("LGTM", "Nice work", "👍") are almost always short.
#    Cap complimentary classification at 8 words as an independent second signal.
# 3. Empty/missing latest-comment text is NOT treated as complimentary — an unresolvable body
#    (both lastCommentBody and bodyFull null/blank) must not silently auto-resolve.
# 4. A stale-schema cache (written before lastCommentAuthor/lastCommentBody/isOutdated existed)
#    is detected via `has()` on ALL THREE fields and routed straight to `keep`, not silently
#    classified on the FIRST comment's data as if it were the latest activity. (Round 2 fix:
#    the jq guard below previously checked only 2 of these 3 fields, disagreeing with this
#    comment and the warning banner below it — a record missing only `isOutdated` slipped
#    through un-guarded. Now all three are checked in both places.)
# 5. A present-but-null `lastCommentAuthor` (GitHub returns `author: null` for deleted/
#    suspended/anonymized accounts — a real API case, not hypothetical) is treated the same as
#    "unknown," not silently swapped for the thread-opener's identity via `//` fallback — that
#    fallback compared the wrong two people (last commenter vs. first commenter) and could
#    misclassify a genuinely-reopened thread as already-resolved.
# All of these err toward the safe side (more threads land in `keep`, not fewer) — and any
# thread resolved via the silent bucket still surfaces in Step 6's accountability closeout
# table, so a misclassification is visible, not silently lost.
FIRST_RECORD=$(head -n 1 "$THREADS_FILE" 2>/dev/null || echo '{}')
if ! echo "$FIRST_RECORD" | jq -e 'has("lastCommentAuthor") and has("lastCommentBody") and has("isOutdated")' > /dev/null 2>&1; then
  echo "⚠️  threads.json predates the lastComment*/isOutdated schema — re-run init-pr-state.sh to refresh the cache. Routing all threads to 'keep' until then (no auto-resolve on stale data)." >&2
fi

jq -c --arg prAuthor "$PR_AUTHOR" '
def is_complimentary(text):
  (
    (text | length) == 0
    or (text | test("\\?"))
    or (text | test("\\b(add|remove|change|fix|update|rename|refactor|replace|consider|check|verify|ensure|move|revert|should|shouldn.t|needs?|missing|must|wrong|incorrect|bug|issue|problem|broken|fails?|failing)\\b"; "i"))
    or (text | test("\\b(but|however|though|although|unless)\\b"; "i"))
    or (text | test("[A-Za-z0-9_/.-]+\\.[A-Za-z0-9]{1,6}:[0-9]+|\\bline[s]?\\s+[0-9]+\\b"; "i"))
    or ((text | [scan("\\S+")] | length) > 8)
  ) | not;

. as $t
| ((($t | has("lastCommentAuthor")) and ($t | has("lastCommentBody")) and ($t | has("isOutdated"))) | not) as $staleSchema
| ($t.lastCommentAuthor == null) as $lastAuthorUnknown
| ($t.lastCommentBody // $t.bodyFull // "") as $lastText
| is_complimentary($lastText) as $complimentary
| if $staleSchema then
    $t + {bucket: "keep", labels: ["stale_cache_schema"]}
  elif $lastAuthorUnknown then
    $t + {bucket: "keep", labels: ["last_author_unknown"]}
  elif ($t.isResolved == true) and ($t.lastCommentAuthor == $prAuthor or $complimentary) then
    $t + {bucket: "already_resolved", labels: []}
  elif ($t.isResolved == false) and $complimentary then
    $t + {bucket: "silent", labels: []}
  else
    $t + {bucket: "keep", labels: (
        (if ($t.isOutdated == true) and ($t.isResolved == false) then ["outdated"] else [] end)
        + (if ($t.isResolved == true) and ($t.lastCommentAuthor != $prAuthor) and ($complimentary | not) then ["resolved_new_activity"] else [] end)
      )}
  end
' "$THREADS_FILE" > "${THREADS_FILE}.tmp" && mv "${THREADS_FILE}.tmp" "$THREADS_FILE"

SILENT=$(jq -s 'map(select(.bucket == "silent")) | length' "$THREADS_FILE")
ALREADY_RESOLVED=$(jq -s 'map(select(.bucket == "already_resolved")) | length' "$THREADS_FILE")
KEEP=$(jq -s 'map(select(.bucket == "keep")) | length' "$THREADS_FILE")
DEGRADED=$(jq -s 'map(select(.labels == ["stale_cache_schema"] or .labels == ["last_author_unknown"])) | length' "$THREADS_FILE")

echo "$SILENT silent threads identified (react + resolve pending), $ALREADY_RESOLVED already-resolved skipped — $KEEP substantive threads to triage."
if [[ "$DEGRADED" -gt 0 ]]; then
  echo "⚠️  $DEGRADED of the $KEEP 'substantive' threads were routed to keep only because their data was degraded (stale schema or unknown last-comment author), not because classification found real content — no content classification actually ran on them."
fi
echo ""
echo "Silent thread IDs (react + resolve, no user prompt):"
jq -r 'select(.bucket == "silent") | .threadId' "$THREADS_FILE"
