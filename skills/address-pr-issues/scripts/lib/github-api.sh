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

  gh api graphql -f query='
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100) {
            nodes {
              id
              isResolved
              comments(first: 10) {
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
            }
          }
        }
      }
    }
  ' -F owner="$REPO_OWNER" -F repo="$REPO_NAME" -F pr="$pr_number" \
    | jq '.data.repository.pullRequest.reviewThreads.nodes[] | {
      threadId: .id,
      commentId: .comments.nodes[0].databaseId,
      author: .comments.nodes[0].author.login,
      isResolved,
      path: .comments.nodes[0].path,
      line: .comments.nodes[0].line,
      bodySummary: (.comments.nodes[0].body | split("\n")[0] | .[0:100]),
      bodyFull: .comments.nodes[0].body,
      createdAt: .comments.nodes[0].createdAt
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
