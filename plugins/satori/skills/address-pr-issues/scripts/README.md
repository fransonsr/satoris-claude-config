# PR Workflow Automation Scripts

Reusable scripts to reduce token costs in the `address-pr-issues` skill by eliminating repetitive command generation.

## System Requirements

**IMPORTANT**: These scripts assume a Linux/Unix-like environment with the following tools:

### Required
- **OS**: Linux, macOS, or WSL (Windows Subsystem for Linux)
- **Shell**: `bash` >= 4.0
- **GitHub CLI**: `gh` (authenticated with `gh auth login`)
- **JSON Processor**: `jq` (for parsing JSON responses)
- **HTTP Client**: `curl` (for SonarQube API calls)
- **Git**: Standard git CLI (for repository operations)

### Optional
- **SonarQube Token**: `SONAR_TOKEN` environment variable (required for SonarQube operations)
- **sonar-project.properties**: In repository root (required for SonarQube operations)

### Installation Quick Start

```bash
# Ubuntu/Debian
sudo apt-get install jq curl gh

# macOS (Homebrew)
brew install jq curl gh

# Verify installations
jq --version
gh --version
curl --version

# Authenticate GitHub CLI
gh auth login
```

**Windows Users**: Install WSL (Windows Subsystem for Linux) first, then install tools within WSL.

## Working Directory Requirement

**CRITICAL**: All scripts must be executed from within the git repository you're working on. The scripts use `git remote get-url origin` to determine the GitHub owner/repo, so they will fail with `ERROR: Not in a git repository with origin remote` if run from outside the repository.

```bash
# ❌ WRONG - Running from home directory or wrong location
cd ~
./init-pr-state.sh 68  # FAILS: "ERROR: Not in a git repository"

# ✅ CORRECT - Running from within the target repository
cd /path/to/your/repository
git remote -v  # Verify origin points to correct GitHub repo
./init-pr-state.sh 68  # WORKS
```

**For Claude Code agents**: Always `cd` into the repository directory before invoking any script.

## Overview

These scripts provide a **hybrid automation approach**:
- **Library functions** (`lib/`) handle GitHub/SonarQube API calls
- **Wrapper scripts** provide CLI interfaces for common workflows
- **Skill integration** uses scripts for repetitive operations, inline commands for one-off tasks

**Expected Token Savings**: 80-85% reduction (25k-37.5k tokens per 15-round PR workflow)

## Scripts

### State Management

#### `init-pr-state.sh <pr_number>`
Initialize PR workflow state (run once per PR, or when starting new round).

Creates workspace in `/tmp/pr-<number>/`:
- `round.txt` - Round tracking (auto-increments)
- `threads.json` - Cached PR review threads
- `api-capabilities.txt` - Threaded reply capability detection
- `fixes.json` - Fix history per round
- `checklist.json` - Pre-commit checklist

**Example**:
```bash
./init-pr-state.sh 68
# Output:
# 📍 Initializing PR workflow state for PR #68
#    Continuing workflow - Round 3
#    ✅ Cached 5 Copilot threads
#    ✅ Threaded replies enabled
```

### GitHub Operations

#### `fetch-pr-threads.sh <pr_number> [--unresolved-only]`
Display cached PR review threads (Copilot/GitHub Advanced Security).

**Example**:
```bash
./fetch-pr-threads.sh 68 --unresolved-only
# Output:
# Unresolved Copilot Threads:
#
# Thread ID: PRRT_kwDO...
# File: src/main/java/Foo.java:42
# Summary: Consider extracting this method for better testability
# Resolved: false
#
# Summary: 2/5 resolved, 3 unresolved
```

#### `classify-threads.sh <pr_number> <pr_author>` (NEW)
Deterministically bucket cached threads into `already_resolved` / `silent` / `keep` (SKILL.md
Step 1.6), writing `bucket` and `labels` fields back into `threads.json`. No LLM judgment —
a fixed heuristic on the most recent comment's text (question mark / trigger word / file-line
reference / conditional language / word count).

**Example**:
```bash
./classify-threads.sh 68 octocat
```
Prints one summary line with the silent/already-resolved/substantive counts, followed by the
list of silent thread IDs to react-and-resolve. Read the script itself for the exact wording —
don't rely on a copy pasted here, it will drift.

**Requires**: `threads.json` entries with `lastCommentAuthor`/`lastCommentBody`/`isOutdated` —
present if cached via `init-pr-state.sh` (which calls the current `fetch_pr_threads()`). Re-run
`init-pr-state.sh` if a cache predates this schema.

#### `resolve-thread.sh <pr_number> <thread_id> [message]`
Resolve a single GitHub review thread (with optional threaded reply if API available).

**Example**:
```bash
./resolve-thread.sh 68 PRRT_kwDO... "Fixed in commit abc123"
# Output:
# Adding threaded reply: Fixed in commit abc123
# ✅ Threaded reply added
# Resolving thread...
# ✅ Thread resolved: PRRT_kwDO...
```

#### `resolve-threads-bulk.sh <pr_number> [options]` (NEW)
Resolve multiple GitHub review threads at once.

**Implementation**: Python script (`.py`) with bash wrapper for compatibility. Uses batched GraphQL mutations for efficiency.

**Options**:
- `--threads <id1,id2,...>` - Resolve specific thread IDs (comma-separated)
- `--file <path>` - Read thread IDs from file (one per line)
- `--filter-path <pattern>` - Resolve threads where file path matches pattern
- `--filter-line <start-end>` - Resolve threads in line range (e.g., 200-300)
- `--all-unresolved` - Resolve ALL unresolved threads
- `--message <msg>` - Message for all resolutions (default: 'Fixed')

**Examples**:
```bash
# Resolve all threads in a specific file
./resolve-threads-bulk.sh 68 \
  --filter-path 'FullExportJobIntegrationTest.java' \
  --message 'Fixed integration test setup'

# Resolve specific threads
./resolve-threads-bulk.sh 68 \
  --threads 'PRRT_abc,PRRT_def,PRRT_ghi' \
  --message 'Fixed null handling'

# Resolve all threads in line range
./resolve-threads-bulk.sh 68 \
  --filter-line 200-300 \
  --message 'Fixed validation logic'

# Resolve ALL unresolved threads (use carefully!)
./resolve-threads-bulk.sh 68 \
  --all-unresolved \
  --message 'Addressed all review feedback'

# Output:
# 📍 Resolving 5 thread(s) with message: "Fixed integration test setup"
#
#   Resolving: FullExportJobIntegrationTest.java:234 ... ✅
#   Resolving: FullExportJobIntegrationTest.java:253 ... ✅
#   Resolving: FullExportJobIntegrationTest.java:261 ... ✅
#   Resolving: FullExportJobIntegrationTest.java:288 ... ✅
#   Resolving: FullExportJobIntegrationTest.java:320 ... ✅
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ✅ Resolved: 5 thread(s)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### SonarQube Operations

#### `check-sonar-quality-gate.sh <pr_number>`
Check SonarQube quality gate status and fetch blocking issues if failed.

**Example**:
```bash
./check-sonar-quality-gate.sh 68
# Output:
# Fetching SonarQube quality gate status for PR #68...
#
# ✅ Quality Gate: PASSED
```

### Workflow Automation

#### `commit-pr-fixes.sh <pr_number> [directional_count]`
Generate structured commit message with round tracking. `directional_count` (default 0) is
persisted into `fixes.json` so Step 8 can read back how many directional-classified fixes
landed this round without depending on conversation memory.

**Example** (see `commit-pr-fixes.sh` itself for the exact commit-message template and
confirmation/tracking output — not reproduced verbatim here, so this example can't drift from
the script per Class 11):
```bash
./commit-pr-fixes.sh 68 2
```
Prints the generated commit message, prompts for confirmation, creates the commit, updates
`fixes.json`, and — when `directional_count > 0` — a line describing what Step 8 will do with
that count (re-request, skip because already re-requested this round, or escalate to `/plan`).

## Library Functions

Located in `lib/`:

### `github-api.sh`
- `get_repo_info()` - Extract owner/repo from git remote
- `fetch_pr_threads()` - Fetch and cache PR threads, including each thread's first *and* most
  recent comment (`lastCommentAuthor`/`lastCommentBody`/`lastCommentId`) and `isOutdated` —
  needed by `classify-threads.sh`
- `resolve_thread()` - Resolve a review thread
- `try_threaded_reply()` - Add threaded reply (if API available)
- `add_pr_comment()` - Add top-level PR comment
- `react_to_comment()` - React to a comment (default 👍) — used for silent-bucket threads
- `test_threaded_reply_api()` - Test threaded reply capability

### `sonar-api.sh`
- `get_sonar_config()` - Parse `sonar-project.properties`
- `get_quality_gate_status()` - Get quality gate for PR
- `get_pr_issues()` - Get issues by severity
- `format_quality_gate_status()` - Display-friendly quality gate
- `format_issues()` - Display-friendly issue list
- `wait_for_analysis()` - Poll for analysis completion

## Typical Workflow

Follows the same activity sequence as SKILL.md — **resolve threads before committing**, not
after — using this script-focused 1-7 numbering, which is independent of SKILL.md's own step
numbers (1, 1.6, 2, 2.5, 3, 3.5, 3.7, 3.8, 4, 4.1, 4.5, 5, 6, 7, 8, 9); don't try to map them 1:1.

```bash
# 1. Initialize state (run once per PR or round)
./init-pr-state.sh 68

# 2. Filter out trivial threads, then check what's substantive
PR_AUTHOR=$(gh pr view 68 --json author -q .author.login)
./classify-threads.sh 68 "$PR_AUTHOR"
./fetch-pr-threads.sh 68 --unresolved-only
./check-sonar-quality-gate.sh 68

# 3. Make fixes (in IDE/Claude)
# ...

# 4. Resolve threads FIRST (BULK - much faster!)
./resolve-threads-bulk.sh 68 \
  --filter-path 'FullExportJobIntegrationTest.java' \
  --message 'Fixed integration test setup'

# OR resolve individually if different messages needed
./resolve-thread.sh 68 PRRT_kwDO... "Fixed resource leak"
./resolve-thread.sh 68 PRRT_kwDO... "Added null check"

# 5. THEN commit — pass DIRECTIONAL_COUNT, derived per SKILL.md's "Derive DIRECTIONAL_COUNT"
# subsection (end of the Execute Fixes step) from Step 2's persisted triage.json
./commit-pr-fixes.sh 68 2

# 6. Push (after the protected-branch guard — see SKILL.md's Pre-Push Checklist & Commit step),
# then re-request Copilot review if DIRECTIONAL_COUNT >= 1 (see SKILL.md's Re-Request Review
# step) instead of just waiting
git push

# 7. Next round (if needed)
./init-pr-state.sh 68  # Auto-increments round number
```

## Integration with address-pr-issues Skill

**Hybrid Approach**:
- Use **scripts** for repetitive operations (state init, thread fetching, resolution)
- Use **inline commands** for one-off tasks (specific jq queries, custom analysis)
- Skill decides when to use each based on context

**Token Savings Analysis** (15-round PR):
- **Before**: 30k-45k tokens (2k-3k per round for bash commands)
- **After**: 5k-7.5k tokens (script invocations only)
- **Savings**: 25k-37.5k tokens (80-85%)

## Troubleshooting

### Common Issues

**`gh: command not found`**
```bash
# Install GitHub CLI
# macOS: brew install gh
# Ubuntu: sudo apt-get install gh
# Then authenticate: gh auth login
```

**`jq: command not found`**
```bash
# Install jq
# macOS: brew install jq
# Ubuntu: sudo apt-get install jq
```

**`SONAR_TOKEN not set`**
```bash
# Export token in your shell profile (~/.bashrc or ~/.zshrc)
export SONAR_TOKEN="your-token-here"

# Or set temporarily
SONAR_TOKEN="your-token" ./check-sonar-quality-gate.sh 68
```

**`Not in a git repository`**
```bash
# Ensure you're in a repository directory
cd /path/to/repository
git remote -v  # Should show origin
```

**Permission denied executing script**
```bash
# Make scripts executable
chmod +x ~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/address-pr-issues/scripts/*.sh
chmod +x ~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/address-pr-issues/scripts/lib/*.sh
```

## Technical Notes

- All scripts use `set -euo pipefail` for safety (fail fast on errors)
- State files are temporary (`/tmp/pr-<number>/`), cleaned on session end
- Scripts validate prerequisites (git repo, authentication, state files)
- Error messages go to stderr, data to stdout (pipe-friendly)
- Scripts are idempotent where possible (safe to re-run)
