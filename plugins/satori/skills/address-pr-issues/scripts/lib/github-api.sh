#!/usr/bin/env bash
# GitHub API helper functions for PR workflow

set -euo pipefail

# Get repository owner and name from git remote
get_repo_info() {
  local remote_url
  remote_url=$(git remote get-url origin 2>/dev/null || echo "")

  if [[ -z "$remote_url" ]]; then
    echo "ERROR: Not in a git repository with origin remote" >&2
    return 1
  fi

  # Extract owner/repo from various git URL formats
  # SSH: git@github.com:owner/repo.git
  # HTTPS: https://github.com/owner/repo.git
  if [[ "$remote_url" =~ github\.com[:/]([^/]+)/([^/]+)(\.git)?$ ]]; then
    REPO_OWNER="${BASH_REMATCH[1]}"
    REPO_NAME="${BASH_REMATCH[2]}"
    REPO_NAME="${REPO_NAME%.git}"  # Remove .git suffix if present
  else
    echo "ERROR: Could not parse GitHub repository from: $remote_url" >&2
    return 1
  fi
}

# Fetch PR threads and cache to file
# Usage: fetch_pr_threads <pr_number> <output_file>
fetch_pr_threads() {
  local pr_number="$1"
  local output_file="$2"

  get_repo_info || return 1

  local raw_response
  raw_response=$(gh api graphql -f query='
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              isResolved
              isOutdated
              firstComment: comments(first: 1) {
                nodes {
                  id
                  databaseId
                  author { login }
                  body
                  path
                  line
                  createdAt
                }
              }
              lastComment: comments(last: 1) {
                nodes {
                  databaseId
                  author { login }
                  body
                  createdAt
                }
              }
            }
          }
        }
      }
    }
  ' -F owner="$REPO_OWNER" -F repo="$REPO_NAME" -F pr="$pr_number")

  # Warn if there are more threads than the 100-thread page can hold
  local has_next_page
  has_next_page=$(echo "$raw_response" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
  if [[ "$has_next_page" == "true" ]]; then
    local end_cursor
    end_cursor=$(echo "$raw_response" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
    echo "⚠️  WARNING: PR has more than 100 review threads — page 2 not fetched." >&2
    echo "   Threads on page 2+ are NOT included in threads.json." >&2
    echo "   To fetch page 2, use endCursor: $end_cursor" >&2
    echo "   See Step 1 pagination note in SKILL.md for the full query." >&2
  fi

  # `firstComment`/`lastComment` fields are used (rather than a single `comments` list) so the
  # cache captures both the original review comment (for replying/resolving) and the most recent
  # activity (for Step 1.6's silent-thread classification) without over-fetching every comment in
  # a long thread.
  echo "$raw_response" \
    | jq -c '.data.repository.pullRequest.reviewThreads.nodes[] | {
      threadId: .id,
      commentId: .firstComment.nodes[0].databaseId,
      author: .firstComment.nodes[0].author.login,
      isResolved,
      isOutdated,
      path: .firstComment.nodes[0].path,
      line: .firstComment.nodes[0].line,
      bodySummary: (.firstComment.nodes[0].body | split("\n")[0] | .[0:100]),
      bodyFull: .firstComment.nodes[0].body,
      createdAt: .firstComment.nodes[0].createdAt,
      lastCommentId: .lastComment.nodes[0].databaseId,
      lastCommentAuthor: .lastComment.nodes[0].author.login,
      lastCommentBody: .lastComment.nodes[0].body
    }' > "$output_file"
}

# Resolve a review thread
# Usage: resolve_thread <thread_id>
resolve_thread() {
  local thread_id="$1"

  gh api graphql -f query='
    mutation($threadId: ID!) {
      resolveReviewThread(input: {threadId: $threadId}) {
        thread { id isResolved }
      }
    }
  ' -f threadId="$thread_id" > /dev/null
}

# Try to add a threaded reply to a review comment
# Returns 0 if successful, 1 if API not available
# Usage: try_threaded_reply <comment_id> <body>
try_threaded_reply() {
  local comment_id="$1"
  local body="$2"

  get_repo_info || return 1

  if gh api "repos/$REPO_OWNER/$REPO_NAME/pulls/comments/$comment_id/replies" \
      -f body="$body" 2>&1 | grep -q "404"; then
    return 1  # API not available
  fi

  return 0  # Success
}

# Add a top-level comment to a PR
# Usage: add_pr_comment <pr_number> <body>
add_pr_comment() {
  local pr_number="$1"
  local body="$2"

  gh pr comment "$pr_number" --body "$body"
}

# React to a review comment (e.g. to silently ack a purely complimentary thread)
# Usage: react_to_comment <comment_id> [content]  (content defaults to "+1")
react_to_comment() {
  local comment_id="$1"
  local content="${2:-+1}"

  get_repo_info || return 1

  gh api --method POST \
    "repos/$REPO_OWNER/$REPO_NAME/pulls/comments/$comment_id/reactions" \
    -f content="$content" > /dev/null
}

# Test if threaded reply API is available
# Usage: test_threaded_reply_api <threads_file>
# Returns: Writes "enabled" or "disabled" to stdout
test_threaded_reply_api() {
  local threads_file="$1"

  get_repo_info || return 1

  local test_comment_id
  test_comment_id=$(jq -r '.[0].commentId // empty' "$threads_file" 2>/dev/null)

  if [[ -z "$test_comment_id" ]]; then
    echo "disabled"
    return 0
  fi

  if gh api "repos/$REPO_OWNER/$REPO_NAME/pulls/comments/$test_comment_id/replies" \
      -f body="test" 2>&1 | grep -q "404"; then
    echo "disabled"
  else
    # Delete test reply
    gh api "repos/$REPO_OWNER/$REPO_NAME/pulls/comments/$test_comment_id/replies" \
        --method DELETE 2>/dev/null || true
    echo "enabled"
  fi
}
