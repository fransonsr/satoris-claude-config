---
name: address-pr-issues
description: Systematically address GitHub Copilot and SonarQube issues on pull requests with comprehensive tests. Reads PR comments, prioritizes issues, implements fixes, and resolves conversations.
argument-hint: [pr-number]
---

# Address PR Issues

Comprehensive workflow to address code quality issues from GitHub Copilot and SonarQube on pull requests with proper test coverage.

## Key Improvement (2026-04-17)

**Problem**: Reactive fixing leads to cascading bugs across 5+ rounds
- Round 1: Fix reported bug X
- Round 2: Copilot finds related bug Y
- Round 3: Copilot finds related bug Z
- Result: Multiple commits, long cycle times, incomplete fixes

**Solution**: Adversarial review agent challenges completeness BEFORE implementing
- **Step 2 (NEW)**: Assess if issues involve cascading edge cases
- **Step 3.5 (NEW)**: Conditionally delegate to `/adversarial-review` (one round) — parallel
  per-class agents sweep all known Copilot issue pattern classes, cascade-sweep within each
  class, then pause for human disposition before applying git-guardrailed fixes
- Forces comprehensive analysis and testing upfront
- **Result**: 5 rounds → 1-2 rounds (80% reduction)

**When to Use**:
- Privacy/security critical code (data leaks, filtering)
- Defensive programming (null checks, conservative cleanup)
- Cascading bug patterns (fixing X reveals Y reveals Z)
- Complex edge case logic with multiple conditions

**When to Skip**:
- Simple style fixes (formatting, comments)
- Obvious bugs with clear solutions
- Low complexity, no edge case risk

## ⚠️ CRITICAL: Use Automation Scripts First

**Token Efficiency**: Scripts save 80-85% tokens (25k-37.5k per 15-round PR)

**ALWAYS use scripts for repetitive operations** - they are in the skill's `scripts/` directory:

| Operation | Script / lib function | Token Savings |
|-----------|----------------------|---------------|
| Initialize state, cache threads | `./scripts/init-pr-state.sh <pr_number>` | ~5k tokens |
| View threads | `./scripts/fetch-pr-threads.sh <pr_number> --unresolved-only` | ~3k tokens |
| Classify silent/already-resolved/keep buckets | `./scripts/classify-threads.sh <pr_number> <pr_author>` | ~2k tokens |
| Resolve one thread (+ optional reply) | `./scripts/resolve-thread.sh <pr_number> <thread_id> [message]` | ~1k tokens |
| Resolve threads in bulk | `./scripts/resolve-threads-bulk.sh <pr_number> --threads '...'` | ~2k tokens |
| React to a comment (👍) | `react_to_comment()` in `lib/github-api.sh` | ~1k tokens |
| Check quality gate + blocking issues | `./scripts/check-sonar-quality-gate.sh <pr_number>` | ~3k tokens |
| Poll Sonar analysis completion | `wait_for_analysis()` in `lib/sonar-api.sh` | ~1k tokens |
| Commit changes | `./scripts/commit-pr-fixes.sh <pr_number> [directional_count]` | ~2k tokens |

**🚨 Hard rule**: If you are about to write `gh api graphql`, a `curl` to SonarQube, or a
resolve/reply/fetch/react mutation by hand, **STOP**. A wrapper script or `lib/` function in the
table above already does it. Read the function in `lib/github-api.sh` or `lib/sonar-api.sh`
instead of re-deriving the query. The only inline API calls permitted anywhere in this skill are
the documented one-offs called out explicitly where they appear (page-2 pagination fallback,
SonarQube won't-fix transition, `sonar-scanner` itself) — everything else routes through a script.

**Only use manual commands for**:
- The specific one-off operations named above (not covered by any script)
- Debugging script failures
- Understanding what scripts do internally (read the code)

**Why this matters**: A 15-round PR using manual commands consumes 40k-50k tokens. The same PR using scripts consumes 8k-12k tokens. Scripts make the workflow sustainable and efficient.

## Workflow Overview

1. **Fetch Issues**: Read Copilot PR comments, PR description (for intent/risk scope), and SonarQube analysis
1.6. **Silent-thread pre-filter (NEW)**: Auto-handle purely-complimentary and already-resolved threads before triage
2. **Assess Complexity**: Determine if adversarial review agent needed
2.5. **Adversarial Review Gate (MANDATORY CHECK)**: Decide, per Step 2.5's criteria, whether this round's issues warrant delegating to `/adversarial-review` before fixes are planned
3. **Prioritize**: Categorize issues by severity and present questionable ones to user
3.5. **Adversarial Review (Delegated)**: When the Step 2.5 gate says yes, run `/adversarial-review --rounds 1` against this round's changes before proceeding to fixes
3.7. **Pre-fix sweep**: For each confirmed issue class, grep the PR's touched files for the same pattern — fix all instances in this round, not just the flagged one
4. **Plan & Execute**: Create implementation plan and fix issues using TDD / xp-pair for complex changes
4.5. **Post-fix sweep**: Re-sweep fixes for cascading issues they may have introduced — add any hits to this round before committing
5. **Validate**: Run local sonar-scanner to catch new issues before committing
6. **Resolve Conversations**: Mark fixed GitHub threads as resolved, reconcile every thread's disposition (NEW)
7. **Commit & Push**: Protected-branch check, then commit and push to PR branch
8. **Monitor**: Classify each fix as directional or polish; actively re-request Copilot review when any fix was directional (NEW — no more passive waiting)
9. **Repeat**: If new significant issues appear, return to step 4; if this is the 3rd+ Copilot review, recommend a `/plan` cycle instead of another blind re-request

**IMPORTANT**: This is an **iterative process**. Expect multiple rounds:
- Fixing code often introduces new SonarQube issues (e.g., extracted methods should be static)
- Copilot analysis happens **after each commit**, potentially adding new suggestions
- Local `sonar-scanner` is CRITICAL to catch issues before CI/CD (saves 30+ min per iteration)
- **Resolve conversations BEFORE pushing** to keep PR clean and show reviewers what's been addressed
- **Adversarial review**: For complex bugs with edge cases, spawn reviewer agent to challenge completeness BEFORE implementing fixes (reduces rounds from 5+ to 1-2)
- **Directional vs. polish (NEW)**: not every fix warrants a fresh Copilot review — only fixes that shift what the PR does

## Key Features (2026-04-24 Update)

**State Management & Caching**:
- ✅ **Thread caching**: Fetch once, query locally (no redundant API calls)
- ✅ **Round tracking**: Auto-increment round numbers in commit messages
- ✅ **Fix history**: Track commits, threads, files changed per round
- ✅ **Progress checklist**: Automated pre-commit validation
- ✅ **API capability detection**: Test threaded replies, adapt gracefully

**Benefits**:
- **Faster workflow**: Cache eliminates 3-5 redundant GitHub API calls per session
- **Better traceability**: Complete audit trail of fixes across all rounds
- **Accurate round tracking**: No manual counting (was "Round 8" in handoff doc)
- **Post-mortem analysis**: Export metrics for process improvement
- **Graceful degradation**: Adapts when threaded reply API unavailable

**State Files** (stored in `/tmp/pr-{number}/`):
- `threads.json` - Cached thread metadata
- `round.txt` - Current round number
- `fixes.json` - Fix history per round
- `checklist.json` - Pre-commit checklist state
- `api-capabilities.txt` - API feature flags

**Auto-cleanup**: State files removed via EXIT trap or archived for analysis

## Automation Scripts (NEW - 2026-04-27)

**Token Optimization**: Reusable bash scripts reduce token costs by 80-85% (25k-37.5k tokens saved per 15-round PR).

**Location**: `scripts/` directory (see `scripts/README.md` for full documentation)

**Library Functions**: `scripts/lib/github-api.sh`, `scripts/lib/sonar-api.sh`

**Wrapper Scripts**:
- `init-pr-state.sh <pr_number>` - Initialize workflow state (run once per PR/round)
- `fetch-pr-threads.sh <pr_number> [--unresolved-only]` - Display cached threads
- `classify-threads.sh <pr_number> <pr_author>` - Bucket threads into silent/already-resolved/keep (NEW)
- `check-sonar-quality-gate.sh <pr_number>` - Check quality gate + fetch issues
- `resolve-thread.sh <pr_number> <thread_id> [message]` - Resolve single thread with reply
- `resolve-threads-bulk.sh <pr_number> [options]` - Resolve multiple threads at once
- `commit-pr-fixes.sh <pr_number> [directional_count]` - Generate structured commit with round tracking; records directional_count for Step 8 (NEW arg)

**Hybrid Approach**: Use scripts for repetitive operations; inline commands are reserved for the
specific one-off tasks named in the Hard Rule above — not a general escape hatch.

## Prerequisites

- **CRITICAL**: All scripts must be run from within the target git repository directory (scripts use `git remote get-url origin` to determine owner/repo)
- GitHub CLI (`gh`) authenticated
- SonarQube token in `SONAR_TOKEN` environment variable
- `sonar-scanner` installed locally
- `sonar-project.properties` configured (created if missing)
- Automation scripts (bundled with plugin - see Script Path Setup below)

**Important**: Always use `gh pr view --json <fields>` instead of `gh pr view` alone to avoid GitHub Projects (classic) deprecation warnings. The `--json` flag queries only the modern GraphQL API.

## Note on Script Paths

Scripts are bundled with this skill in the `scripts/` subdirectory. In the examples below, `./scripts/` refers to scripts relative to this skill's installation directory. Claude Code agents will automatically resolve these paths when executing the skill.

## Step 1: Gather PR Information

### Get PR Number and Details

```bash
# If no PR number provided, get current branch's PR
PR_NUMBER="${args:-$(gh pr view --json number -q .number)}"

# Get PR details, including body (needed for intent/risk scope below) and author
# (PR_AUTHOR — needed for Step 1.6's silent-thread classification)
gh pr view $PR_NUMBER --json number,title,headRefName,baseRefName,url,body,author
PR_AUTHOR=$(gh pr view $PR_NUMBER --json author -q .author.login)
```

**Clean working tree**: before making any changes, check `git status --porcelain`. If it
returns output, confirm with the user whether that's expected in-progress work before continuing
— don't start fixing on top of uncommitted changes you didn't make.

### Extract PR Intent and Risk Scope (NEW)

From the fetched `body`, extract:
- `PR_INTENT` — a 1-2 sentence summary of what the PR is supposed to do
- `RISK_FILES` — file paths or function names listed under `## Risk Assessment` /
  `## Review Hotspots` / `### High Priority Review Areas`, if present

If the body is absent or has no such sections, treat `RISK_FILES` as empty and `PR_INTENT` as
unknown — this is a normal case, not an error. `PR_INTENT` feeds two later steps: the Step 3.5
adversarial-review Intent Brief, and the directional/polish classification in Step 2.

### Initialize State Management (AUTOMATED)

⚠️ **USE SCRIPT** (saves ~5k tokens):
```bash
./scripts/init-pr-state.sh $PR_NUMBER
```

> **Pagination note**: The init script fetches at most 100 threads. If the PR has
> approached or exceeded 100 review comments, there may be additional threads on page 2
> that the script does not see — it will falsely report "0 unresolved" while threads
> remain open. The script will warn you if `hasNextPage` is true. If you see that warning,
> fetch page 2 manually:
>
> ```bash
> # Step 1: Check whether page 2 exists
> gh api graphql -f query='
> query($owner:String!, $repo:String!, $pr:Int!) {
>   repository(owner:$owner, name:$repo) {
>     pullRequest(number:$pr) {
>       reviewThreads(first:100) {
>         pageInfo { hasNextPage endCursor }
>       }
>     }
>   }
> }' -F owner=OWNER -F repo=REPO -F pr=NUMBER \
>   | jq '.data.repository.pullRequest.reviewThreads.pageInfo'
> ```
>
> If `hasNextPage` is true, re-run the unresolved-thread query with
> `-F cursor='<endCursor>'` and `reviewThreads(first:100, after:$cursor)` to fetch the
> next page, then merge the results into `threads.json`.

**If the script fails**, don't hand-roll its logic — read what it does instead:
`./scripts/init-pr-state.sh` itself, and the functions it calls in `scripts/lib/github-api.sh`
(`fetch_pr_threads`, `test_threaded_reply_api`). Fix the script or its inputs, then re-run it.

**State Files Created**:
- `$WORKSPACE_DIR/round.txt` - Current round number (auto-incremented)
- `$WORKSPACE_DIR/threads.json` - Cached thread metadata (avoids re-fetching)
- `$WORKSPACE_DIR/api-capabilities.txt` - API feature detection results
- `$WORKSPACE_DIR/fixes.json` - Fix history per round
- `$WORKSPACE_DIR/checklist.json` - Pre-commit checklist state
- `$WORKSPACE_DIR/triage.json` - Step 2's persisted triage results (written in Step 2)
- `$WORKSPACE_DIR/copilot_review_count.txt` - Re-review counter (written in Step 8)

**Shorthand used throughout this doc**: `$THREADS_FILE`, `$CHECKLIST_FILE`, `$FIXES_FILE`, and
`$ROUND` are not exported by any script — they're shorthand for
`$WORKSPACE_DIR/threads.json`, `$WORKSPACE_DIR/checklist.json`, `$WORKSPACE_DIR/fixes.json`, and
`$(cat "$WORKSPACE_DIR/round.txt")` respectively. Set them yourself before running a snippet that
uses them, e.g. `THREADS_FILE="$WORKSPACE_DIR/threads.json"`.

**Benefits**:
- Faster workflow (no redundant API calls)
- Accurate round tracking in commit messages
- Progress tracking across iterations
- Graceful API capability detection

### Query Cached Threads (AUTOMATED)

⚠️ **USE SCRIPT** (saves ~3k tokens):
```bash
# Display unresolved threads with summary
./scripts/fetch-pr-threads.sh $PR_NUMBER --unresolved-only
```

**For custom filtering** beyond what the script's flags support, query `$THREADS_FILE` directly
with `jq` rather than adding a new script flag for a one-off — the cache is plain JSON.

### Fetch SonarQube Issues (AUTOMATED)

⚠️ **USE SCRIPT** (saves ~3k tokens - checks quality gate + fetches blocking issues):
```bash
./scripts/check-sonar-quality-gate.sh $PR_NUMBER
```

**If `sonar-project.properties` is missing**, see "Handle Missing sonar-project.properties" in
Tips and Best Practices below. **For custom queries** beyond what the script covers, use the
`lib/sonar-api.sh` functions directly (`get_quality_gate_status`, `get_pr_issues`,
`wait_for_analysis`) rather than a fresh `curl` — read the library file for their signatures.

## Step 1.6: Silent-Thread Pre-Filter (NEW)

Before any thread reaches the CRITICAL/HIGH/MEDIUM/LOW triage in Step 3, auto-handle threads
that carry no substantive feedback — avoids spending triage effort, or a user prompt, on a 👍
or "LGTM". This bucketing is a **deterministic classification, not an LLM judgment call** — run
the script, don't apply the rule by hand per thread:

⚠️ **USE SCRIPT**:
```bash
./scripts/classify-threads.sh $PR_NUMBER "$PR_AUTHOR"
```

It writes `bucket` (`already_resolved | silent | keep`) and `labels` fields into each cached
thread and prints the silent-thread IDs. See `classify-threads.sh` itself for the exact
"purely complimentary" heuristic (question mark / trigger word / file-line reference /
conditional language / word count) — it's the same rule described in `apply-feedback`'s
triage agent, hardened with an expanded trigger vocabulary and a length guard since this runs
with no human fallback (a false positive silently resolves a real comment).

### Bucket 1 — Already Resolved (skip entirely, no action)

`isResolved == true` AND (the most recent comment is from the PR author OR is purely
complimentary). Take no action — re-resolving or re-reacting wastes API calls and clutters the
PR timeline for no benefit.

### Bucket 2 — Silent (auto-handle, no user prompt)

`isResolved == false` AND the most recent comment is purely complimentary. `classify-threads.sh`
only *classifies* these threads — it does not react or resolve them itself. For each thread ID
it prints, derive the `commentId` (needed by `react_to_comment()`, unlike `resolve-thread.sh`
which takes the `threadId` directly) from the cache, then react and resolve:
```bash
COMMENT_ID=$(jq -r --arg tid "$THREAD_ID" 'select(.threadId == $tid) | .commentId' "$THREADS_FILE")
# react_to_comment() is a lib/github-api.sh function, not a standalone script — source it first:
source "./scripts/lib/github-api.sh" && react_to_comment "$COMMENT_ID"
./scripts/resolve-thread.sh $PR_NUMBER "$THREAD_ID"
```

### Bucket 3 — Keep (flows into Step 3)

Everything else: unresolved threads with substantive feedback, resolved threads with new
non-complimentary activity from someone other than the PR author (`labels: ["resolved_new_activity"]`),
and outdated unresolved threads (`labels: ["outdated"]`). Carry these labels into the Step 3
presentation as `[resolved + new activity]` / `[outdated]` so nothing is silently missed.

The script's own summary line (`N silent threads identified (react + resolve pending), M
already-resolved skipped — K substantive threads to triage.`) is what to show the user before
moving to Step 2.

**If the script isn't available or a thread's cache predates it** (missing `lastCommentAuthor`/
`isOutdated` fields — added when `fetch_pr_threads()` was extended for this step), re-run
`./scripts/init-pr-state.sh $PR_NUMBER` first to refresh the cache with the current schema.

## Step 2: Assess Complexity & Edge Case Risk (NEW)

**CRITICAL**: Before jumping to fixes, assess if issues involve cascading edge cases that require adversarial review.

### Indicators for Adversarial Review Agent

**Spawn reviewer agent if issues include**:

1. **Privacy/Security Critical Code**
   - Data leaks, access control, authentication
   - Conservative fail-safe patterns (e.g., "remove all relationships if can't verify")
   - Filtering sensitive data (PII, restricted records)

2. **Defensive Programming Patterns**
   - Null checks, empty checks, boundary validation
   - Malformed data handling
   - Error recovery logic

3. **Cascading Bug Pattern** (strongest indicator)
   - Round 1 fixes null persona refs → Round 2 finds null resource URIs
   - Related edge cases in same code section
   - Pattern: fixing X reveals Y, fixing Y reveals Z

4. **Complex Edge Case Logic**
   - Multiple nested conditions
   - Set operations (filtering, intersection, difference)
   - Conservative cleanup (remove ALL if ANY fails)

### Quick Assessment Questions

Before implementing fixes, ask:

1. **What can be null?** (object, field, nested field, collection element)
2. **What can be empty?** (string, collection, optional)
3. **What can be malformed?** (invalid format, out of bounds, unexpected values)
4. **What combinations exist?** (null + empty, valid + invalid, etc.)
5. **Are there similar patterns elsewhere?** (same bug in other methods?)

### Parallel Issue Triage (Workflow)

Triage only Step 1.6's Bucket 3 ("keep") threads — Buckets 1 and 2 were already disposed of
without a triage agent:
```bash
jq 'select(.bucket == "keep")' "$THREADS_FILE"
```
Triage these in parallel, one agent per issue, using the `Workflow` tool (Claude Code's
multi-agent orchestration primitive — spawns one agent per item concurrently and returns each
agent's structured result). This offloads assessment from the implementation session's context;
only the structured results return, not the full per-issue analysis work.

Spawn one agent per issue via `Workflow`. Each agent receives the thread body, file path, line number, the relevant code section (read from disk), and `PR_INTENT`/`RISK_FILES` from Step 1.

Each agent returns:
```json
{
  "issue_id": "thread_id",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "complexity_indicators": ["null handling", "collections", "type resolution"],
  "proposed_fix": "brief description of the fix",
  "cascading_risk": true,
  "classification": "directional|polish",
  "notes": "any context about related bugs or edge cases"
}
```

**`classification`** (NEW) is a separate axis from `severity` — it answers "does fixing this
change what the PR does?", not "how bad is it":
- **directional** — the fix shifts the PR's intent: someone reading the current PR description
  would now be wrong about something that matters after this change. A BLOCKER-severity Sonar fix
  can be polish; a LOW-severity Copilot suggestion can be directional. Judge by the nature of the
  fix, not its severity label.
- **polish** — the fix refines within the existing intent (wording, naming, minor guards,
  formatting, tests) without changing what the PR does.
- When ambiguous, classify as `polish` — the directional bar is high.

**Persist the merged triage results** to `$WORKSPACE_DIR/triage.json` (an array of the per-issue
JSON objects above, keyed by `issue_id`) before moving on — this is what Step 4.1 reads back to
compute `DIRECTIONAL_COUNT`, so it survives a context compaction the same way `threads.json`/
`fixes.json` do.

Use the merged triage results to drive Step 3 categorization and the Step 2.5 adversarial review
decision. **`DIRECTIONAL_COUNT`** is the count of `directional`-classified issues actually fixed
this round — not everything triaged. An issue the user deferred or declined in Step 3 doesn't
count, since nothing about the PR changed for it. See "Derive DIRECTIONAL_COUNT" at the end of
Step 4.1 for the concrete computation.

### Step 2.5: Adversarial Review Gate (MANDATORY CHECK)

**⚠️ STOP: Do not skip this step without completing the checklist.**

Before deciding whether to use adversarial review, answer these questions:

#### Complexity Indicators (check all that apply)

**Code Characteristics:**
- [ ] Multiple execution paths (if/else, loops, recursion)
- [ ] String manipulation or parsing
- [ ] Collections (iteration, filtering, mapping, grouping)
- [ ] Inheritance or type resolution
- [ ] Null handling or defensive checks
- [ ] Cross-class or cross-module interactions
- [ ] Error handling or exception propagation

**Edge Case Enumeration:**
Can you enumerate ALL edge cases right now? (Requires at least 3 specific cases)
- Happy path: _________________
- Edge case 1: _________________
- Edge case 2: _________________
- Edge case 3: _________________

**Confidence Check:**
Would you bet that Copilot review finds zero logic issues (not style) in your implementation?
- [ ] Yes - high confidence
- [ ] No - uncertain

#### Decision Rules

**MUST spawn adversarial reviewer if:**
- 2 or more complexity indicators checked
- Cannot enumerate at least 3 specific edge cases
- Not confident Copilot finds zero issues

**MAY skip adversarial review ONLY if ALL of these are true:**
- 0-1 complexity indicators
- Can enumerate 3+ edge cases
- Confident in implementation
- Changes are one of:
  - Pure style/formatting (whitespace, imports, comments)
  - Simple constants or configuration
  - Documentation-only
  - Renaming via IDE refactoring

#### When Skipping (Rare)

If you decide to skip, document your reasoning:

```
Skipping adversarial review because:
- Complexity indicators: [X checked]
- Edge cases enumerated: [list]
- Change type: [specific reason]
```

**Show this reasoning to the user** so they can override if needed.

#### Things That SEEM Simple But AREN'T

These patterns consistently hide edge cases - always use adversarial review:
- Prefix/suffix stripping (What about: nested? qualified? super.?)
- Name matching (What about: collisions? shadowing? packages? imports?)
- Type resolution (What about: wildcards? fully-qualified? ambiguous?)
- Null checks (What about: empty? combinations? parent fields?)
- String splitting (What about: delimiters in data? edge counts? escaping?)
- HashMap/Set operations (What about: iteration order? duplicates? collisions?)

## Step 3: Categorize and Prioritize Issues

### Issue Severity Matrix

**CRITICAL** (Must fix):
- Security vulnerabilities (SQL injection, XSS, etc.)
- Null pointer dereferences with high confidence
- Resource leaks (unclosed streams, connections)
- Data loss risks
- Logic errors that break functionality

**HIGH** (Should fix):
- Code smells affecting maintainability
- Performance issues (inefficient algorithms)
- Test coverage gaps for critical paths
- Deprecated API usage with known issues

**MEDIUM** (Consider fixing):
- Style violations in new code
- Minor refactoring opportunities
- Documentation gaps
- Test coverage for edge cases

**LOW** (Discuss with user):
- Stylistic preferences
- Over-engineering suggestions
- Legacy code issues (not touched in this PR)
- Debatable design patterns

### Present Questionable Issues to User

For any MEDIUM or LOW severity issues, or issues you're uncertain about. Carry forward any
`[outdated]` / `[resolved + new activity]` label from Step 1.6's Bucket 3 in the item header,
right after the severity tag:

```
I found the following issues that need your input:

1. **[MEDIUM] SonarQube**: Extract method with 15 lines (Copilot suggests 10 max)
   - File: `BulkExportJob.java:145-160`
   - Impact: Readability improvement, not functional
   - **Decision needed**: Fix now or defer?

2. **[LOW] Copilot**: Use `var` for local variable type inference
   - File: `RecordProcessor.java:78`
   - Impact: Style only
   - **Decision needed**: Apply or ignore?

3. **[MEDIUM] Copilot [resolved + new activity]**: Reviewer reopened concern about retry logic
   - File: `RetryHandler.java:52`
   - Impact: Thread was marked resolved, but a new non-complimentary comment followed
   - **Decision needed**: Address the new comment or confirm it's already covered?

4. **[LOW] Copilot [outdated]**: Suggestion predates a later commit in this PR
   - File: `ExportJob.java:210`
   - Impact: The flagged line may have already changed since this comment was posted
   - **Decision needed**: Still applicable, or safe to resolve as stale?

Should I address these? (yes/no/selective)
```

## Step 3.5: Adversarial Review (Delegated to /adversarial-review)

**If the Step 2.5 gate above indicates adversarial review is warranted**, delegate to the
`/adversarial-review` skill BEFORE implementing fixes. The gate decides *whether* to run;
this step describes *how*.

### Construct the Intent Brief (~200 words)

Before invoking, compose the Intent Brief from the PR context — what the PR does, the key
design decisions already made, what was deferred, and any accepted risks. Start from
`PR_INTENT` and `RISK_FILES` (extracted in Step 1) and expand with anything the triage in
Step 2 surfaced. This is the most important input: without it, fix agents cannot distinguish
"intentional design choice" from "bug to fix."

### Invoke with rounds=1

This step runs on the diff of an already-open PR's fix round — a single sweep is the right
cost/coverage trade-off:

```
Skill(adversarial-review, args="--rounds 1 --base-branch <base-branch> --intent-brief \"<intent-brief text>\"")
```

The `/adversarial-review` skill runs one round of parallel per-class agents, returns findings
for review-pause (Step 3's categorize-and-prioritize loop serves as the disposition point),
applies approved fixes under git guardrails (PROHIBITED: git reset, rebase, commit, stash,
restore; PERMITTED: Edit/Write, read-only bash, git diff/status), then returns a summary.

Use the returned findings to drive the implementation step (Step 4/4.1) and the
commit-and-push step (Step 7).

### When to Skip (Rare — the gate decides)

The Step 2.5 gate above lists the conditions. When skipping, document the reasoning (gate
checklist result) so the user can override. The examples below show the value of the agent:

**Without adversarial review** (5 rounds):
```
Round 1: Fix substring matching bug
Round 2: Fix null persona refs (Copilot found)
Round 3: Fix empty persona IDs (Copilot found)
Round 4: Fix size mismatch logic (Copilot found)
Round 5: Fix null resource URIs (Copilot found)
```

**With adversarial review** (1 round):
- Parallel agents sweep all known pattern classes in one shot
- Cascade sweep finds null persona refs AND resource URIs AND empty IDs in the first pass
- Approved fixes applied in one commit
- Copilot finds only style issues in the next round

**Result**: ~80% reduction in rounds, better code quality, faster delivery

## Step 3.7: Similar-Pattern Sweep (Mandatory)

**Always run this step** — even if the sweep finds nothing, the cost is a grep; the payoff when it hits is eliminating an entire issue class in one commit instead of being surprised next round.

### What to Do

For each confirmed issue class from Step 3:

1. **Abstract the pattern** — identify the class of issue, not just the literal string.
   - Too literal: `"except json.JSONDecodeError"`
   - Right level: `"single-exception catch missing OSError"`

2. **Run a two-tier grep**:

   **Tier 3a — Diff-scoped grep** (textual repetition): scope to changed lines only.
   ```bash
   git diff --name-only | xargs grep -n "<pattern>"
   ```

   **Tier 3b — File-scoped grep** (structural absence): when the issue involves a property
   that *all members of a set* should share (e.g., all `run_step_*` functions, all
   `cmd_*` functions, all JSON-read sites), grep the *full changed file*, not just diff
   lines. The sibling that's missing the property is often not in the diff.
   ```bash
   grep -n "<sibling-class-pattern>" <changed-file>
   # Then check each hit for the missing property
   ```

3. **Evaluate hits** — for each result not already in the fix list:
   - Is this the same anti-pattern, or superficially similar?
   - Would fixing it belong in this commit's logical scope?
   - If yes: add to fix list at the same severity as the original finding.

4. **On "nothing found" for structural issues** — a zero result on a diff-scoped grep
   does not mean the issue class is absent from the file. For absence-of-pattern issues
   (missing preflight checks, fallback paths, guard conditions), enumerate the set:
   "What other functions/call-sites of this class exist in the file?" Check each for the
   property. Report any gaps at the same severity as the original finding.

5. **Merge into the working fix list** — de-duplicate and carry forward into Step 3.8's decision summary.

### Output for Step 3.8

For each issue class swept, report one of:
- **Hits found**: "Found the same pattern in N additional location(s) — fixing all of them eliminates this issue class rather than surfacing it again next round"
- **Nothing found (textual)**: "Sweep complete — no other instances of this pattern in the PR's changed files"
- **Gap found (structural)**: "Diff-scoped grep found nothing, but file-scoped check found N sibling(s) also missing this property — adding to fix list"

### Examples

```
Issue flagged: fleet_state.py _load_fleet_state catches JSONDecodeError but not OSError

Sweep pattern: single-exception catch missing companion error type
Tier 3a grep: git diff --name-only | xargs grep -n "except json\."

  fleet_state.py:88 — already in fix list (the original finding)

Result: No additional hits — only one catch site in the changed files.

---

Issue flagged: fleet_runner.py ignores return code from cmd_set_merged

Sweep pattern: return code from state-mutation command calls not captured or checked
Tier 3a grep: git diff --name-only | xargs grep -n "cmd_set_merged\|cmd_advance\|cmd_block\|cmd_unblock"

  fleet_runner.py:719 — already in fix list
  fleet_runner.py:831 — NOT in fix list: rc = cmd_advance(...) assigned but never checked

Adding fleet_runner.py:831 to fix list (same severity: medium).
→ Fixing both sites in one commit; issue class fully addressed.

---

Issue flagged: run_step_analyze missing shutil.which("mvn") preflight

Sweep pattern: run_step_* functions that call mvn lack preflight check
Tier 3a grep: git diff --name-only | xargs grep -n "shutil.which"
  → Nothing found in diff

Tier 3b structural check: grep full file for all run_step_* functions
  grep -n "^def run_step_" fleet_runner.py
  → run_step_discover (no mvn — no gap), run_step_analyze (no preflight ← GAP),
    run_step_tier1 (has preflight), run_step_verify (has preflight)

Adding run_step_analyze preflight to fix list (same severity: high).
→ Issue class fully addressed in one commit.
```

### Key Principles

- **Sweep is mandatory, not conditional.** Single-file typo fixes are a no-op — fast and safe to run anyway.
- **Scope is the PR's changed files**, not the full repo. False positives from unrelated code are noise.
- **When the issue is structural** (a property that all members of a function/call-site class should share), extend the grep to the *full changed file*, not just the diff. The sibling that's missing the property is likely not in the diff.
- **"Nothing found" on a structural issue triggers a set-difference check**, not a clean pass. Enumerate the siblings; the absence is the finding.
- **If the sweep surfaces a new instance that, when fixed, would introduce a Sonar finding**, that Sonar finding belongs in this commit too. The sweep never creates new rounds — it widens the current one.

## Step 3.8: Show Decision Summary to User

Before implementing, present your process decisions to the user:

```
📋 **Implementation Approach**

**Complexity Assessment:**
- Risk factors: [count] 
  - [list checked items]
- Edge cases identified: [count]
  - [list enumerated cases]

**Process Decisions:**
- Test approach: [Test-First | Test-After]
  - Reason: [why this choice]
- Adversarial review: [Yes | Skipped]
  - Reason: [why this choice]
- XP Pair: [Yes | No]
  - Reason: [why this choice]

**If skipping recommended process steps, I need your approval.**

Proceed? (yes/no/use more process)
```

This makes decisions visible and gives user a chance to correct before work starts.

## Step 4: Create Implementation Plan

Based on confirmed issues, create a plan using TDD principles:

### Assess Complexity & TDD Approach

**Complexity Assessment**:
- **Simple** (< 20 lines, obvious fix): Handle directly with test-after
- **Moderate** (20-100 lines, clear design): Handle directly, choose test-first OR test-after based on clarity
- **Complex** (> 100 lines OR unclear design): Use xp-pair skill

**TDD Decision** (per CLAUDE.md):
- **Test-First**: When design needs thinking through
  - Complex algorithms or business logic
  - Unclear requirements or edge cases
  - Behavior changes to critical code paths
- **Test-After**: When design is obvious
  - Simple CRUD operations
  - Obvious bug fixes with known solutions
  - Straightforward refactoring
  - Simple validation logic

**Always Required**: Tests must exist (happy path + edge cases + errors), but test-first is not mandatory

### Plan Structure

```
## Implementation Plan: Address PR Issues

### Issues to Fix
1. [CRITICAL] Null pointer dereference in `RecordProcessor.process()`
2. [HIGH] Unclosed `BufferedReader` in `FileParser.parse()`
3. [MEDIUM] Extract method for complex validation logic

### Approach & Testing Strategy

**TDD Approach Selection** (per CLAUDE.md):
- **Test-First**: Use when design needs thinking through (complex algorithms, unclear requirements)
- **Test-After**: Use when fix is obvious (bugs with clear solutions, simple refactoring)
- **Always**: Tests are required, but not necessarily test-first

**Issue 1**: Null pointer dereference (OBVIOUS FIX → Test-After)
- Implement: Add null check with `Objects.requireNonNull()`
- Test: Write test with null input (should throw IllegalArgumentException)
- Verify: Existing behavior unchanged

**Issue 2**: Resource leak (OBVIOUS FIX → Test-After)
- Implement: Use try-with-resources
- Test: Verify file handle cleanup
- Refactor: Extract file reading logic if needed

**Issue 3**: Extract method (REFACTORING → Test-After)
- Refactor: Extract `validateRecordFormat()` method
- Verify: Run existing tests (should pass, pure refactoring)
- Add tests: If edge cases not covered

### Validation
- Unit tests for all changes
- Integration test to verify no regressions
- Local sonar-scanner before commit
```

## Step 4.1: Execute Fixes (Iterative Loop)

**CRITICAL**: This step is typically executed **2-4 times** before committing. Each fix may introduce new issues.

### Iteration Pattern

```
┌─────────────────────────────────────┐
│ 1. Implement fix for issue(s)      │
│ 2. Run unit tests (mvn test)       │
│ 3. Run sonar-scanner locally        │
│ 4. New issues found?                │
│    ├─ Yes → Loop back to step 1    │
│    └─ No  → Proceed to commit       │
└─────────────────────────────────────┘
```

### For Simple Fixes (Direct Implementation)

```bash
# Iteration 1: Fix initial issues
[Make changes using test-first OR test-after as appropriate...]

# Run tests (verify your changes work)
mvn test -pl <module>

# Build and scan locally (CRITICAL - catches issues before CI/CD)
mvn clean install -DskipTests
sonar-scanner

# ⚠️  New issues found! (e.g., "method should be static")
# → Go to Iteration 2

# Iteration 2: Fix new issues
[Make changes and add/update tests as needed...]
mvn test -pl <module>
sonar-scanner

# ✅ No new blocking issues, all tests pass
# → Ready to commit
```

**Test Coverage Requirements** (per CLAUDE.md):
- Happy path (expected inputs/outputs)
- Edge cases (boundary conditions, empty/null inputs)
- Error paths (invalid inputs, exceptions)
- Regression coverage for bugs

**Tests must exist, but test-first is optional** - use judgment based on complexity.

**For Each New Method/Class Added** (not just fixes):
- [ ] Write test for happy path
- [ ] Write test for null/edge cases  
- [ ] Write test for error conditions
- [ ] Verify test coverage (all new code executed by tests)

**Example**: If you add a `setAccumulator()` method:
```java
@Test
void shouldSetAccumulatorAfterConstruction() {
    // Test that accumulator can be set
}

@Test
void shouldHandleNullAccumulator() {
    // Test that null is acceptable
}
```

### For Complex Fixes (Use xp-pair)

**When to use xp-pair**:
- Complex refactoring (>100 lines OR unclear design)
- Multiple valid design approaches need discussion
- High-risk code requiring design oversight

**Example**:
```
I'll use xp-pair for Issue 1 (significant refactoring with unclear best approach):

[Invoke xp-pair skill with specific task]

Task: Extract and refactor complex validation logic in RecordProcessor
Acceptance Criteria:
- [ ] Extract validation into separate, testable methods
- [ ] Maintain existing behavior (all tests pass)
- [ ] Improve readability and maintainability
- [ ] No new SonarQube issues introduced
- [ ] Tests cover happy path + edge cases + errors
```

**Note**: For simpler issues (obvious bugs, straightforward refactoring), handle directly without xp-pair.

### Mandate Test-First for Critical Bugs

**For privacy/security/logic bugs** (especially those flagged by adversarial reviewer):
- **Always use test-first TDD** (RED-GREEN-REFACTOR)
- Forces thinking through edge cases
- RED phase reveals incomplete understanding
- GREEN phase confirms fix handles ALL scenarios
- REFACTOR phase improves design

**Example**:
```
# Issue: Null resource URI handling (privacy-critical)

# RED: Write test that exposes the bug
@Test
void shouldRemoveRelationshipsWithNullResourceUri() {
    // Test fails: relationships with null URIs are retained (privacy leak)
}

# GREEN: Minimal fix to pass test
if (persona1Id.isEmpty() || persona2Id.isEmpty()) {
    return true; // Remove relationships with invalid URIs
}

# REFACTOR: Improve clarity, add JavaDoc, extract if needed
```

### Separate Style from Logic Commits

**Commit Strategy**:
- **Commit 1**: Style fixes only (RED prefixes, whitespace, imports)
  - Fast to review
  - No test changes needed
  - Low risk
  
- **Commit 2**: Critical bugs with comprehensive tests
  - Complete edge case coverage
  - Multiple test scenarios per bug
  - High confidence in correctness

**Rationale**: Separating concerns makes PR easier to review and reduces noise in critical commits

### Derive DIRECTIONAL_COUNT (before moving to Step 4.5)

Now that this round's fixes are implemented, compute `DIRECTIONAL_COUNT` — needed by Step 7's
commit and Step 8's re-request decision. It's the count of `triage.json` entries classified
`directional` whose issues you actually fixed this round (not deferred, not declined, not
won't-fixed):

```bash
# List the issue_ids you actually fixed this round, one per line, e.g.:
FIXED_IDS="thread_abc thread_def"

DIRECTIONAL_COUNT=$(jq --arg ids "$FIXED_IDS" '
  [.[] | select(.classification == "directional") | select(.issue_id as $id | ($ids | split(" ")) | index($id))] | length
' "$WORKSPACE_DIR/triage.json")
```

If you didn't persist `triage.json` in Step 2 (e.g. a small round with only 1-2 issues, triaged
inline instead of via `Workflow`), tally by hand against the fix list you just completed instead
of skipping this — `DIRECTIONAL_COUNT` must have a real value before Step 7.

## Step 4.5: Post-Fix Cascade Sweep (MANDATORY)

After applying all fixes from this round but **before committing**, re-sweep the PR's changed
files to check whether the fixes themselves introduced new cascading issues.

**Why**: A fix that adds a null check, restructures a branch, or extracts a method can expose
a sibling callsite that was previously unreachable, or can introduce the same defensive-guard
or control-flow pattern in a new location without the matching safeguard.

### What to Sweep

For each fix applied this round, ask:
- **New code paths introduced**: Did the fix add a branch, a helper method, or a fallback
  that itself needs a null guard, a returncode check, or an error handler?
- **Sibling callsites now exposed**: Did fixing one callsite reveal that a neighboring
  callsite (not in the original diff) now has the same gap?
- **Structural consistency**: If the fix adds a pattern (e.g., `isinstance` guard, `try/except
  (OSError, UnicodeDecodeError)`), is that pattern now present at every peer callsite in the
  same file?

### How to Run

Same two-tier grep as Step 3.7, but targeted at code **introduced or modified by the fixes**:

```bash
# Tier A — what changed since before the fixes (the fixes themselves)
git diff HEAD -- <changed files>

# Tier B — structural check: if the fix adds a pattern, enumerate all peer sites
grep -n "<pattern from fix>" <changed file> | grep -v "<already fixed>"
```

### Example

```
Fix applied: added stdout fallback to git fetch failure path in run_step_sync_repos.
Pattern introduced: when stderr is empty, fall back to stdout then "(no output)".

Tier A (git diff HEAD):
  +        if not fetch_detail:
  +            fetch_detail = (
  +                "; ".join(...stdout...) or "(no output)"
  +            )

Tier B (structural check — enumerate all peer callsites in the same function):
  grep -n "returncode != 0" fleet_runner.py
  → Lines 502, 529, 559, 630, 684, 719 — all subprocess failure paths in run_step_sync_repos

  Check each for the new pattern:
  → Line 502 (fetch):   ✅ just fixed
  → Line 529 (sym_ref): uses conditional suffix — different shape, gap not present
  → Line 559 (status):  ❌ missing stdout fallback — add to fix list
  → Line 630 (ahead):   ❌ missing — add
  → Line 684 (ff-only): ❌ missing — add
  → Line 719 (behind):  ❌ missing — add

Result: 4 additional fix sites found. Fix all in this commit; class fully addressed.
Without this sweep, each site would have surfaced as a separate Copilot round.
```

Report any new findings immediately — **add them to this round's fix list** rather than
deferring to the next round. The goal is to exit each round fully clean on the fix's own
footprint, not to create a chain of follow-up rounds.

If the post-fix sweep finds nothing, state it explicitly: "Post-fix sweep complete — no new
cascading issues introduced by this round's fixes."

## Step 5: Validate Changes Locally

**CRITICAL**: Before pushing, run local SonarQube scan AND verify results:

### Step 5a: Run SonarQube Scanner

```bash
# Full build first (SonarQube needs compiled classes)
mvn clean install -DskipTests

# Run SonarQube analysis and capture task URL
SCANNER_OUTPUT=$(sonar-scanner 2>&1 | tee /dev/tty)
TASK_URL=$(echo "$SCANNER_OUTPUT" | grep "More about the report processing" | sed 's/.*at //')
TASK_ID=$(echo "$TASK_URL" | sed 's/.*id=//')

echo ""
echo "✅ Scanner completed - Task ID: $TASK_ID"
```

### Step 5b: Wait for Server Processing

**IMPORTANT**: The local scan only uploads data - server-side analysis takes 30-60 seconds.

```bash
source "./scripts/lib/sonar-api.sh"
wait_for_analysis "$TASK_ID"
```

**Note**: Some enterprise SonarQube instances use SSO that blocks API access. If `wait_for_analysis`
times out or errors, proceed to manual dashboard review (Option B below).

### Step 5c: Review Results

**Option A: API Access Available** (preferred) — use the same script as Step 2's fetch:
```bash
./scripts/check-sonar-quality-gate.sh $PR_NUMBER
```
It fetches the quality gate status and, if it failed, the blocking (BLOCKER/CRITICAL-equivalent)
issues. If it reports FAILED, fix the listed issues before committing.

**Option B: Manual Dashboard Review** (fallback for SSO-protected instances): open
`$SONAR_HOST/dashboard?id=$PROJECT_KEY&pullRequest=$PR_NUMBER`, wait 30-60 seconds for analysis,
and verify: Quality Gate passed, no new BLOCKER/CRITICAL issues, coverage acceptable, security
hotspots reviewed.

**If new issues found**: Fix them before committing (iterate Step 4-5).

## Step 6: Resolve Conversations (BEFORE Commit)

**CRITICAL**: Resolve GitHub conversations BEFORE pushing commit. This keeps the PR clean and shows reviewers what you've addressed.

**REQUIRED**: You MUST resolve review threads. This is not optional - it's a core part of the workflow.

### Resolve Fixed Issues (AUTOMATED)

⚠️ **USE BULK SCRIPT** (saves ~2k tokens - resolve multiple threads at once):
```bash
# Resolve all threads in a specific file
./scripts/resolve-threads-bulk.sh $PR_NUMBER \
  --filter-path 'FullExportJobIntegrationTest.java' \
  --message 'Fixed integration test setup'

# Resolve specific threads
./scripts/resolve-threads-bulk.sh $PR_NUMBER \
  --threads 'THREAD_ID_1,THREAD_ID_2,THREAD_ID_3' \
  --message 'Fixed null handling'

# Resolve all unresolved threads (use carefully!)
./scripts/resolve-threads-bulk.sh $PR_NUMBER \
  --all-unresolved \
  --message 'Addressed all review feedback'
```

⚠️ **USE SINGLE-THREAD SCRIPT** (when different messages needed for each thread):
```bash
# Resolve thread with optional message (tries threaded reply, falls back to direct resolution)
./scripts/resolve-thread.sh $PR_NUMBER "$THREAD_ID" "Fixed: Added null check for persona refs"

# Multiple threads with different messages (loop)
for thread_id in "$THREAD_ID_1" "$THREAD_ID_2" "$THREAD_ID_3"; do
  ./scripts/resolve-thread.sh $PR_NUMBER "$thread_id" "Fixed specific issue"
done
```

**If the bulk/single script doesn't cover your case** (e.g. one-off custom logic), use the
underlying `lib/github-api.sh` functions directly — `try_threaded_reply` and `resolve_thread` —
rather than writing a fresh `gh api graphql` mutation. They already handle capability detection
(falling back to direct resolution when threaded replies are unavailable) and cache updates.

### Document Won't-Fix Decisions

For issues you're not fixing, resolve with a reason instead of leaving the thread open:

```bash
./scripts/resolve-thread.sh $PR_NUMBER "$THREAD_ID" "Won't fix: [reason] — [rationale, e.g. outside PR scope, style preference]"
```

**Resolving threads is MANDATORY** — it signals to reviewers that you've acknowledged and
addressed each issue, whether by fixing it or explaining why not.

### Look Up a Thread's IDs from Cache

`THREADS_FILE` is a plain JSON cache — query it with `jq` for a specific thread's IDs, then hand
them to the resolve script (no need to re-fetch or re-derive the fetch/resolve logic):

```bash
THREAD_ID=$(jq -r 'select(.path == "FullExportJob.java" and .line == 186) | .threadId' "$THREADS_FILE")
./scripts/resolve-thread.sh $PR_NUMBER "$THREAD_ID" "Fixed: added null check for persona refs"
```

`resolve-thread.sh` updates `$THREADS_FILE` itself after a successful resolution — no separate
cache-update step needed.

### Update Checklist

```bash
# Mark threads resolved in checklist
jq '.threads_resolved = true' "$CHECKLIST_FILE" > "${CHECKLIST_FILE}.tmp" && mv "${CHECKLIST_FILE}.tmp" "$CHECKLIST_FILE"

# Verify all items complete
if jq -e 'all(.[]; . == true)' "$CHECKLIST_FILE" > /dev/null; then
  echo "✅ Pre-commit checklist complete"
  jq '.commit_ready = true' "$CHECKLIST_FILE" > "${CHECKLIST_FILE}.tmp" && mv "${CHECKLIST_FILE}.tmp" "$CHECKLIST_FILE"
else
  echo "⚠️  Checklist incomplete:"
  jq -r 'to_entries[] | select(.value == false) | "  - \(.key)"' "$CHECKLIST_FILE"
fi
```

**Re-fetching threads** (e.g. after new Copilot comments land): re-run
`./scripts/init-pr-state.sh $PR_NUMBER` — it re-caches threads and auto-increments the round.
Don't hand-write the fetch query; it's the same one `fetch_pr_threads()` already runs.

**Why resolve threads, and why before commit?** Shows reviewers what's addressed, keeps the PR
interface clean (resolved threads collapse), creates an audit trail, and lets your commit
message reference already-resolved issues instead of the reverse order (fix → resolve → commit →
push, not commit → push → resolve).

### Reply Tone (NEW)

Write replies as a teammate — casual, direct. No "delve", no "certainly", no "great point".

Use **future tense** when acknowledging a fix that hasn't been made yet:
  Bad: "Fixed the null check."
  Good: "I'll fix that in a follow-up."

Use **past tense** when confirming a fix you just made:
  Good: "Good catch — added a null check before the map call."
  Good: "This is intentional — we want to fall through to the default handler here."

### Thread-Accountability Closeout (NEW)

Before moving to Step 7, reconcile **every** thread this session touched — both of Step 1.6's
skip-buckets (not just Silent) and everything triaged in Step 3. Build a one-line-per-thread
status table:

- `already-resolved-skip` — Step 1.6's Bucket 1; no action was needed or taken. List via
  `jq -r 'select(.bucket == "already_resolved") | .threadId' "$THREADS_FILE"`
- `resolved-silent` — handled in Step 1.6's Bucket 2 (Silent)
- `replied-and-resolved` — fixed or explained in Step 4.1/6
- `won't-fix-resolved` — documented won't-fix + resolved above
- `skipped` — user chose to skip during Step 3.8 approval
- `adjusted` — user reworded the reply or change; treat as replied-and-resolved

Format: `file:line — outcome`.

**Hard stop**: for each `skipped` thread, pause and ask the user to explicitly confirm "leave
open" or provide a reply now. Do not proceed to Step 7 until every skipped thread has either an
explicit acknowledgment or a posted reply. The principle: a thread the user has seen and chosen
to leave open is fine; a thread that fell off the workflow without anyone noticing is not.

Only run the full table when there's more than a trivial number of threads — for a single-digit
round, a one-line summary (`Handled: N already-resolved, M silent, P replied, K won't-fix, all
threads accounted for.`) is enough.

## Step 7: Pre-Push Checklist & Commit

### Pre-Push Checklist (MANDATORY - Automated)

**NEW**: Use checklist state file to track progress:

```bash
# Update checklist as you complete each step
update_checklist() {
  local key=$1
  local value=$2
  jq --arg k "$key" --argjson v "$value" '.[$k] = $v' "$CHECKLIST_FILE" > "${CHECKLIST_FILE}.tmp" && mv "${CHECKLIST_FILE}.tmp" "$CHECKLIST_FILE"
}

# Mark tests passing
mvn test -pl <module> && update_checklist "tests_passing" true

# Mark build clean
mvn clean install -DskipTests && update_checklist "build_clean" true

# Mark SonarQube reviewed (after manual dashboard check)
update_checklist "sonar_reviewed" true

# Mark threads resolved (after resolving all threads)
update_checklist "threads_resolved" true

# Display checklist status
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Pre-Push Checklist (Round $ROUND)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
jq -r 'to_entries[] | "[\(if .value then "✅" else "❌" end)] \(.key)"' "$CHECKLIST_FILE"
echo ""

# Verify all items complete
if jq -e 'all(.[]; . == true)' "$CHECKLIST_FILE" > /dev/null; then
  echo "✅ All checklist items complete - ready to commit"
  update_checklist "commit_ready" true
else
  echo "⚠️  Incomplete items - cannot commit yet"
  exit 1
fi
```

**If ANY item fails** → STOP, fix it, update checklist.

### Commit with Structured Message (AUTOMATED)

⚠️ **USE SCRIPT** (saves ~2k tokens - auto-generates message with round tracking, records fix
history):
```bash
# Stage changes first
git add <files>

# Generate commit; pass DIRECTIONAL_COUNT (from Step 2/4's classification) so it's persisted to
# fixes.json — Step 8 reads it back from disk instead of relying on conversation memory
./scripts/commit-pr-fixes.sh $PR_NUMBER "$DIRECTIONAL_COUNT"
```

**For heavy customization** beyond what the script covers, read `commit-pr-fixes.sh` itself
rather than reimplementing its commit-message and `fixes.json` bookkeeping inline.

### Protected-Branch Guard (NEW — before push)

**Before pushing**, verify the current branch is not `master`/`main` directly by name — do NOT
use `git config branch.<name>.merge` to infer this: it reads the branch's configured upstream
merge ref, which is empty (and the command exits non-zero) on any branch that has no explicit
tracking ref configured, e.g. one created with `git checkout -b` and never pushed with `-u`. On
such a branch this check silently fails open, matching neither `refs/heads/master` nor
`refs/heads/main`, and falls through to an unguarded push. Compare the branch name directly
instead, which has no such gap:
```bash
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" == "master" || "$CURRENT_BRANCH" == "main" ]]; then
  echo "🛑 STOP: current branch is '$CURRENT_BRANCH' — refusing to push directly to a protected branch." >&2
  exit 1
fi
```
Otherwise:
```bash
git push
```

## Step 8: Re-Request Review & Monitor for New Comments

### Active Copilot Re-Request (NEW — replaces passive waiting)

Read `DIRECTIONAL_COUNT` back from `fixes.json` for the round just committed (persisted by
`commit-pr-fixes.sh` in Step 7) rather than trusting conversation memory — this survives a
context compaction or a resumed session:
```bash
DIRECTIONAL_COUNT=$(jq -r --arg round "$ROUND" '.[$round].directional_count // 0' "$FIXES_FILE")
```

- **If `DIRECTIONAL_COUNT >= 1`**: at least one fix shifted what the PR does — but check the
  re-review count **first**, before re-requesting. Re-requesting unconditionally on every
  directional round is exactly the "just keep fixing what Copilot flags" anti-pattern the
  Convergence Criterion below warns against — the gate belongs here, at the point of the
  action it gates, not several sections later where it's easy to skip in practice:
  ```bash
  COUNT_FILE="$WORKSPACE_DIR/copilot_review_count.txt"
  # Initialize to 1 on first use — the PR's automatic review on open counts as review #1
  [[ -f "$COUNT_FILE" ]] || echo 1 > "$COUNT_FILE"
  ```
  - **If `$(cat "$COUNT_FILE") -ge 2`** (this re-request would be review #3 or beyond): **stop**
    — do not re-request. Follow "Numeric /plan Escalation" under Convergence Criterion below:
    draft an actual `/plan` prompt naming this PR's recurring themes and wait for the user.
  - **Otherwise**, actively re-request review — don't wait for Copilot to notice the push on
    its own:
    ```bash
    gh pr edit $PR_NUMBER --add-reviewer @copilot
    ```
    Use exact spelling `@copilot`; no REST fallback. If it fails (422 / user-not-found), tell
    the user: "Copilot re-review couldn't be triggered via CLI — use the 'Re-request review'
    button next to Copilot in the Reviewers panel."

    Then increment the counter (same file, same pattern as `round.txt`, so it survives a
    context compaction like every other cross-round counter in this doc):
    ```bash
    echo $(( $(cat "$COUNT_FILE") + 1 )) > "$COUNT_FILE"
    ```

  `address-pr-issues` has no PR-description-generation tool, so unlike a fully automated
  refresh, surface a one-line manual nudge: "N directional fix(es) this round — consider
  updating the PR description before merge."

- **If `DIRECTIONAL_COUNT == 0`**: every fix this round was polish (style, naming, tests, minor
  guards) — skip the re-request and state so: "No directional fixes this round — not
  re-requesting Copilot review."

### Wait for CI/CD to Complete

```bash
# Check CI/CD status (typically 15-30 minutes)
gh run watch

# OR: Check manually after waiting
gh run list --branch $(git branch --show-current) --limit 1
```

### Check for New Copilot Comments (Update Cache)

Refresh cached thread data after CI/CD completes, then diff against the pre-round snapshot to
find what's new — the fetch itself is a script call, not a hand-written query:

```bash
# Save current state for comparison
cp "$THREADS_FILE" "${THREADS_FILE}.before-round-${ROUND}"

# Re-fetch (also auto-increments round; use fetch-pr-threads.sh instead if you only need
# to view rather than advance the round)
./scripts/init-pr-state.sh $PR_NUMBER

# Compare with previous state to detect new threads
NEW_THREADS=$(jq -s '.[0] - .[1]' "$THREADS_FILE" "${THREADS_FILE}.before-round-${ROUND}" | jq 'select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]")')
# Look for new unresolved threads or comments added to existing threads
```

**If new comments found**:
- Evaluate severity (same prioritization matrix)
- **Minor issues** (style, suggestions): Consider batch-fixing later
- **Significant issues** (bugs, security): Loop back to Step 4

**Decision tree**:
```
New Copilot comments after commit?
├─ Same class as a prior round's fix → Sweep gap (see "Pattern Class Recurrence" below)
├─ Critical/High (new class) → Fix immediately (Step 4.1 again)
├─ Medium → User decides: fix now or later
└─ Low / all won't-fix → Converging (see "Convergence Criterion" below)
```

**Note**: After any fix round, repeat Step 6 (resolve new conversations) before pushing again.

### Pattern Class Recurrence

When Copilot finds more instances of a pattern class already fixed this PR, the cause is a
sweep that was too narrow — not a new concern requiring adversarial review.

**How to recognize it**: The new thread describes the same structural gap (missing fallback,
missing guard, missing validation) at a different callsite, and a prior commit message shows
you already fixed that gap elsewhere.

**Response** (do NOT re-run adversarial review — the class is already known):

1. **Identify the class** from the prior round's commit message or fix notes.
2. **Widen the grep scope** — scope expands with each recurrence:
   - First encounter → PR's changed files only
   - Recurrence → full file containing the changed code
   - Second recurrence → full function family across all files in the PR
3. **Enumerate ALL peer callsites** of the same type (e.g., every `returncode != 0` block,
   every `run_step_*` function, every JSON-read site) and check each against the missing property.
4. **Fix all remaining instances in one commit.** Use a message like
   `sweep: exhaust [class name]` rather than `fix: Round N` — this is gap-closing, not a new
   round of findings.
5. **Run Step 4.5 post-fix sweep** to confirm exhaustion before pushing.
6. **State the outcome**: "Pattern class exhausted — N total sites fixed across M rounds."

**Example**: Copilot flags `git rev-list` failure path missing stdout fallback (Round 3),
after you already fixed `git fetch` in Round 1. Widen from PR-changed-files to full file.
Enumerate all `returncode != 0` blocks. Find 4 remaining sites. Fix all; class is closed.

### Convergence Criterion

Stop iterating when a round produces only issues you are choosing not to fix. Signs that
the PR has converged:

- Every new thread is style-only, doc-wording, or a design choice you disagree with.
- No new bug classes have appeared since the last two rounds.
- Your Step 2.5 gate would rate every new thread as "skip adversarial review."
- The thread severity trend is declining (Critical/High → Medium → Low → doc-only).

When converged: document won't-fix rationale on each remaining thread, resolve all threads,
and present the PR to the user as ready for merge review. Do not keep iterating hoping
Copilot will eventually stop — the convergence criterion ends the loop, not a round cap.

### Numeric /plan Escalation (NEW)

In addition to the qualitative signs above, Step 8's re-request gate (see "Active Copilot
Re-Request") checks `$WORKSPACE_DIR/copilot_review_count.txt` inline, at the point of the
re-request decision itself, rather than deferring the check here: `-ge 2` means the pending
re-request would be review #3 or beyond, and Step 8 stops before sending it. When that happens,
recommend a `/plan` cycle instead: draft the actual `/plan` prompt — not a placeholder — naming
this PR's recurring themes (e.g. "error handling across rounds," "repeated null-check gaps in
the export module"), with thread IDs and affected scope where available. Present it to the user
and wait for their response before continuing. This turns "just keep fixing what Copilot flags"
into a deliberate checkpoint once a PR has clearly outgrown reactive rounds.

## SonarQube Issue Resolution

### For Fixed Issues

**SonarQube auto-detects fixes** after CI/CD analysis completes:
```bash
# No manual action needed - issues disappear from PR automatically
# Just wait for CI/CD build to finish and SonarQube to re-analyze
```

### For Won't-Fix Issues
```bash
# Mark as won't fix with comment
curl -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/issues/do_transition" \
  -d "issue=$ISSUE_KEY" \
  -d "transition=wontfix"

curl -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/issues/add_comment" \
  -d "issue=$ISSUE_KEY" \
  -d "text=Intentional: [reason]"
```

## State Management & Fix History

`$FIXES_FILE` (per-round commit/files history) and `$THREADS_FILE.before-round-N` snapshots
(saved in Step 8) are plain JSON — query them with `jq` for whatever view you need. Two
starting points:

```bash
# Full fix history across all rounds
cat "$FIXES_FILE"

# Rounds + threads resolved + files changed, one line per round
jq -r 'to_entries[] | "\(.key): \(.value.threads_resolved | length) threads, \(.value.files_changed | length) files"' "$FIXES_FILE"
```

**Cleanup after merge**: `rm -rf "/tmp/pr-${PR_NUMBER}"`, or archive it first with
`mv "/tmp/pr-${PR_NUMBER}" "$HOME/.claude/pr-history/pr-${PR_NUMBER}-$(date +%Y%m%d)"` if you
want it for a later post-mortem.

## Tips and Best Practices

### Don't Use `gh pr comment` for Fix Replies

`gh pr comment` posts a **top-level** PR comment, not a threaded reply — it doesn't resolve
anything and reviewers won't see it attached to the flagged line. Always resolve via
`resolve-thread.sh` / `resolve-threads-bulk.sh` (Step 6), which handle the threaded-reply-plus-
resolve sequence correctly, in the fix → resolve → commit → push order described there.

### Anticipate Further Issues

See **Step 3.7 — Similar-Pattern Sweep**: mandatory grep of all PR-touched files for each confirmed issue class before any fix is implemented. This handles the "batch related issues" concern automatically.

### Lessons from Real-World Usage

**Case Study: PR #63 - 5 Rounds → Could Have Been 1**

**What Happened**:
- Round 1: Fixed substring matching bug
- Round 2: Fixed null persona refs (Copilot flagged)
- Round 3: Fixed empty persona IDs (Copilot flagged)
- Round 4: Fixed size mismatch logic (Copilot flagged)
- Round 5: Fixed null resource URIs (Copilot flagged)

**Root Cause**: Reactive fixing (fix reported issues) instead of proactive analysis (fix ALL related issues)

**What Should Have Happened**:
1. **Step 2 Assessment**: Detected cascading edge case pattern (privacy-critical filtering)
2. **Spawn Adversarial Reviewer**: Challenge completeness before coding
3. **Agent Forces Analysis**:
   - "You're checking persona IDs - what can be null?" (persona ref, resource URI, ID itself)
   - "What can be empty?" (empty string, empty collection)
   - "What can cause size mismatches?" (null IDs, duplicate IDs)
   - "Show me tests for ALL scenarios"
4. **Implement Once**: All edge cases covered in Round 1
5. **Result**: 1 logic commit + 1 style commit = 2 rounds total

**Key Insight**: Adversarial review would have saved 3 rounds and caught 80% of issues upfront

**When to Learn from This**:
- Privacy/security critical code
- Defensive programming (null checks, conservative cleanup)
- Pattern of related bugs in same code section
- Complex edge case logic with multiple conditions

### Update Skill Over Time

As you use this skill, note improvements:
- Common issue patterns (create templates)
- Frequently used API endpoints (add shortcuts)
- Edge cases (document in this file)

**Suggest updates** to the skill if you find:
- Repeated manual steps (automate them)
- Missing error handling
- Better ways to prioritize issues

### Handle Missing sonar-project.properties

If the repository lacks SonarQube configuration:

1. **Check for reference repository** in the same org
2. **Copy template** or create minimal config:

```properties
# sonar-project.properties
sonar.host.url=https://sonarqube.churchofjesuschrist.org/
sonar.projectKey=fs-eng_${repo-name}_maven-build
sonar.projectName=${repo-name}
sonar.projectVersion=1.0
sonar.sources=src/main/java
sonar.tests=src/test/java
sonar.java.source=17
sonar.java.binaries=target/classes
sonar.sourceEncoding=UTF-8
```

3. **Extract project key from SonarQube PR comment** (if available):
   - Look for SonarQube bot comment on PR
   - Parse project key from dashboard URL

## Troubleshooting

### GitHub API Rate Limits

If you hit rate limits:
```bash
gh api rate_limit
```

Wait or use personal access token with higher limits.

### SonarQube Authentication Issues

Verify token:
```bash
curl -u "$SONAR_TOKEN:" "$SONAR_HOST/api/authentication/validate"
```

Expected: `{"valid":true}`

### Thread Resolution Not Working

Ensure you have write permissions on the repository:
```bash
gh api repos/{owner}/{repo}/collaborators/{username}/permission
```

### Local SonarQube Scan Fails

Common issues:
- Missing compiled classes: Run `mvn clean install` first
- Incorrect paths in `sonar-project.properties`
- Java version mismatch: Check `sonar.java.source` setting

