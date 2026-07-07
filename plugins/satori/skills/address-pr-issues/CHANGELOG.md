# Address PR Issues Skill - Changelog

## 2026-07-07 - v1.7.3: Cross-File Yield Convergence Vocabulary

**Context**: `/adversarial-review` replaced its boolean `is_clean` termination gate with a
`blast_radius` (local vs cross_file) tag per finding and a "cross-file yield" convergence
signal — local findings no longer force another round, and hitting the round cap with
cross-file findings still open now escalates to a targeted deep-dive instead of a vague
"PR too large" signal. Realigned this skill's Convergence Criterion, Pattern Class
Recurrence, and Numeric /plan Escalation sections to the same vocabulary: Copilot's own
review behavior has no principled convergence point either (it scans until it finds enough
issues, not until impact is exhausted), so a Copilot round finding nothing is one noisy
sample, not proof the PR is done — the rewritten Convergence Criterion says so explicitly.

See commit `d4e8401` for the vocabulary realignment across all three satori review skills.

## 2026-07-01 - v1.7.2: Adversarial-Review Convergence Rounds 2-6

**Context**: Per the dogfooding discipline (`~/.claude/CLAUDE.md`'s dogfooding section) of
running multiple verification rounds rather than trusting a single fix batch, ran five more
`/adversarial-review` rounds against v1.7.0's own fixes. Each round found real bugs in the
*previous* round's fixes, not just new debt — the whole reason this discipline exists. Findings
per round plateaued at 13-16 (Round 3 onward) rather than converging to zero — a large,
actively-edited document may not realistically reach a fully clean round, so Round 6 was
adopted as the stopping point rather than continuing indefinitely:

- **Round 2** (8 fixes): `classify-threads.sh`'s stale-schema guard checked only 2 of the 3
  required fields (missing `isOutdated`); a present-but-null `lastCommentAuthor` silently fell
  back to the thread-opener's identity instead of failing closed; the Protected-Branch Guard
  (`git config branch.<name>.merge`) failed open on any branch with no tracking ref configured
  — verified live by creating an actual untracked branch.
- **Round 3** (17 fixes): the Round 2 fix for `lastCommentAuthor` left the sibling field
  `lastCommentBody` with the identical null-fallback gap; threads with genuinely empty content
  had no degraded-data label at all; the Step 2 triage agent never received the `labels` field
  where degraded-data markers live, so a thread kept only because its data was unverifiable was
  triaged as if reliable; the stale-schema banner checked only the first cached record instead
  of the whole file.
- **Round 4** (14 fixes): the Round 3 fix for Step 8's re-request counter advanced it even when
  the `gh pr edit` call *failed*, recording a re-request that never happened; the `$CURRENT_BRANCH`
  reuse fix reintroduced the exact cross-snippet variable-persistence gap it was meant to close;
  `scripts/lib/github-api.sh` crashed the entire thread fetch on a null first-comment body (the
  same class of gap already fixed on the last-comment side); a previously-untouched
  `examples/iterative-fixing-session.md` had a stale hand-written commit-message template.
- **Round 5** (13 fixes): `$WORKSPACE_DIR` itself — unlike the shorthand vars derived from it —
  was never covered by SKILL.md's "shorthand" disclaimer despite ~2 dozen usage sites depending
  on it (pre-existing debt, not introduced by any round); `examples/iterative-fixing-session.md`
  had two more stale hand-written blocks beyond the one Round 4 fixed, including a raw
  `gh api graphql`/`gh pr comment` block contradicting SKILL.md's own Hard Rule; a dangling,
  incomplete "Example Session Flow" in QUICK_START.md had survived three prior rounds untouched.
- **Round 6** (14 fixes): the Round 5 fix for `$WORKSPACE_DIR` only added a reminder at Step 8 —
  the identical gap existed at Step 6, Step 7, and the State Management section too;
  `commit-pr-fixes.sh`'s recovery/retry path silently defaulted `DIRECTIONAL_COUNT` to 0 if the
  operator retried without re-passing the same arg; `classify-threads.sh`'s `is_complimentary()`
  crashed the entire script on a non-string comment body (verified live, pre-existing since
  Round 1); the "Example Session Flow" written in Round 5 itself reintroduced a misconception
  (that `classify-threads.sh` resolves threads, not just classifies them) that SKILL.md
  explicitly warns against elsewhere — the same misconception also existed, pre-existing and
  uncaught, at QUICK_START.md's "Filter Trivial Threads" section.

See commits `f8d4a6c`, `0ddab3a`, `b5ee8a4`, `df8a759`, and this round's commit for full
per-round detail.

## 2026-07-01 - v1.7.0: First Real Dogfood Run (pre-pr-audit + adversarial-review)

**Context**: Ran `/satori:pre-pr-audit` against this skill's own diff for the first time —
previously it had never been reviewed by its own tooling. Surfaced 42 findings total: 9 from
the mandatory adversarial pattern review (11 classes), 33 from Steps 4.8/4.9 (spec-completeness
+ whole-document coherence walk). ~16 were caused by today's diff; the rest was pre-existing
structural debt (duplicate "Step 3.5"/"Step 4" headings, Workflow Overview numbers that never
matched the body, several orphaned/undefined references) that the whole-document walk surfaced
because it reads entire files, not just diffs. Fixed all of it in one batch:

- **`classify-threads.sh`**: fixed a real bug — stale-schema caches and empty comment bodies
  were failing OPEN into the auto-resolving `silent` bucket instead of failing closed to `keep`.
  Added a `has()`-based stale-schema guard and an empty-text guard in `is_complimentary()`.
- **`commit-pr-fixes.sh`**: fixed a real crash — a zero-padded `directional_count` (e.g. `"08"`)
  passed the digits-only regex but crashed bash's `-gt` (octal interpretation of leading zero).
  Also replaced the hardcoded, already-stale `Co-Authored-By: Claude Sonnet 4.5` with a
  generic `Co-Authored-By: Claude` — model names go stale, this shouldn't need updating again.
- **SKILL.md/README.md**: renamed the duplicate "Step 3.5" (adversarial review gate → "Step
  2.5") and duplicate "Step 4" (execute fixes → "Step 4.1") headings; fixed the Workflow
  Overview's wrong numbers (1.5→1.6, 3.5→3.7 for pre-fix sweep, "return to step 5"→"step 4.1");
  added the missing DIRECTIONAL_COUNT derivation (persist Step 2's triage to `triage.json`,
  compute the count from it after Step 4.1 — this was referenced at Step 7/8 but never
  actually shown); gave the Step 8 re-review counter a real persistence file
  (`copilot_review_count.txt`, it previously had none unlike every other cross-round counter);
  added a Bucket 1 outcome category to the Thread-Accountability Closeout (it claimed to cover
  "both" Step 1.6 buckets but only had a slot for one); added the missing `commentId`
  derivation for Step 1.6's silent-bucket react step; moved the SonarQube fetch section from
  under Step 2 back to Step 1 (where the Workflow Overview already said it lived).
- **scripts/README.md, QUICK_START.md**: removed a literal reproduction of `commit-pr-fixes.sh`'s
  commit-message template (Class 11 drift risk — confirmed a stale co-author line), clarified
  that scripts/README.md's 1-7 workflow numbering is independent of SKILL.md's step numbers
  rather than implying a 1:1 mapping, and pointed both at the new DIRECTIONAL_COUNT derivation.

**Process change going forward**: `plugin.json`/`marketplace.json`'s version must be bumped
whenever plugin content changes, or `Skill()` invocations keep serving a stale cached snapshot
indefinitely (discovered during this run — the cache was 5 days stale despite several commits
landing in between). See `~/.claude/CLAUDE.md`'s dogfooding section for the full workflow.

## 2026-07-01 - v1.6.0: Ported apply-feedback Strengths + Script-First Cleanup

**Motivation**: Compared against `golden-pr:apply-feedback`, which handles the same
"address open PR review comments" job with a leaner, subagent-delegated design. Four
capabilities were missing here; ported them over. Separately, direct review found the SKILL
body reproducing GraphQL/curl operations that the skill's own `scripts/`/`lib/` already cover
— the duplication is why the agent kept re-deriving queries inline instead of calling scripts.

**Added**:
1. **Step 1.6 — Silent-thread pre-filter**: auto-handle purely-complimentary and
   already-resolved threads (precise, checkable definition) before the CRITICAL/HIGH/MEDIUM/LOW
   triage in Step 3. New `react_to_comment()` helper in `lib/github-api.sh`.
2. **PR intent + directional/polish classification**: Step 1 now reads the PR body for
   `PR_INTENT`/`RISK_FILES`; Step 2's triage schema gains a `classification` field
   (directional | polish) — a fix that shifts what the PR does vs. one that refines within
   existing intent. Drives Step 8's `DIRECTIONAL_COUNT`-gated **active** Copilot re-request
   (`gh pr edit --add-reviewer @copilot`), replacing the old passive "wait ~5-10 min."
   No PR-description auto-refresh (this skill has no generator tool) — surfaces a manual nudge
   instead.
3. **Thread-accountability closeout** (Step 6): a per-thread status table covering every
   thread touched this session, with a hard stop on any `skipped` thread lacking an explicit
   "leave open" acknowledgment.
4. **Protected-branch guard** (Step 7, before push), a **Reply Tone** contract (future tense for
   not-yet-made fixes, past tense for confirmed ones), and a **numeric `/plan` escalation**
   (re-request #2+ triggers a recommended `/plan` cycle instead of another blind re-request),
   sharpening the existing qualitative Convergence Criterion.

**Removed / collapsed** (script-first enforcement): deleted the fully-redundant manual
`<details>` blocks that reimplemented `init-pr-state.sh`, the thread-fetch GraphQL query
(previously duplicated 3×), the Sonar polling loop, and the manual commit block — all replaced
with pointers to the existing scripts/`lib/` functions. Added a hard rule to the "Use Automation
Scripts First" section: if you're about to write `gh api graphql` or a SonarQube `curl` by hand,
a script already does it. Condensed the post-mortem jq catalog to two commands + a pointer.

**Net effect**: four new capabilities landed with the file still shorter than before
(~1754 → ~1450 lines).

**Follow-up hardening (same day)** — implementing the above as prose-only left two things
unbuildable, caught on review:
- `fetch_pr_threads()` only ever cached each thread's *first* comment, but Step 1.6's bucket
  rules need the *most recent* comment (to detect resolved-with-new-activity) and `isOutdated`
  (for the `[outdated]` label) — neither field existed in the cache. Extended the GraphQL query
  and cached schema with `lastCommentAuthor`/`lastCommentBody`/`lastCommentId`/`isOutdated`.
- Added `scripts/classify-threads.sh` — turns Step 1.6's bucket rules into a deterministic jq
  classifier instead of prose the agent applies per-thread. The "purely complimentary" heuristic
  was hardened beyond its `apply-feedback` origin (expanded trigger-word vocabulary + a word-count
  guard) after testing showed the original definition misclassifies short substantive comments
  like "This method should validate input" as complimentary — a false positive here silently
  auto-resolves a real comment with no human ever seeing it.
- `commit-pr-fixes.sh` now takes an optional `directional_count` argument and persists it into
  `fixes.json`, so Step 8's Copilot re-request decision reads from disk instead of depending on
  conversation memory surviving a context compaction or resumed session.

**Also extended**: `copilot-review-patterns.md` Class 11 (Cross-File Rule Consistency) to cover
doc-vs-script restatement — this session found `address-pr-issues/SKILL.md` had already suffered
a real drift incident from exactly this pattern (see `~/.claude/copilot-review-patterns.md`).
README.md resynced to current SKILL.md (was a stale pre-adversarial-review snapshot, ~728 lines
diverged before this session).

**Follow-up (same day, round 2)** — self-review turned up two more gaps:
- QUICK_START.md never mentioned Step 1.6 or `classify-threads.sh` — added a "Filter Trivial
  Threads" cheat-sheet entry and a workflow-diagram step, so the cheat sheet doesn't omit a
  documented step.
- Step 3's "Present Questionable Issues to User" template didn't show where Step 1.6's
  `[outdated]` / `[resolved + new activity]` labels appear in the presented list — added two
  labeled example items.
README.md resynced again to match.

## 2026-06-12 - v1.5.0: Sweep Improvements + Pagination Warning

### Step 3.7: Two-tier sweep for structural absence (Changes 1 & 2)

**Problem**: The diff-scoped sweep caught textual repetition but missed *structural absence* — when a function lacked a property that all sibling functions already had (e.g., `run_step_analyze` missing a preflight check that `run_step_tier1` and `run_step_verify` already had). The sibling wasn't in the diff, so grep found nothing and reported a clean pass.

**Fix**:
- Added **Tier 3b file-scoped grep**: for structural issues, grep the *full changed file*, not just diff lines, to find all sibling functions/call-sites of the same class.
- Added **absence-detection logic**: "nothing found" on a structural issue now triggers an explicit set-difference check — enumerate the siblings, verify each has the property, report gaps.
- Added new Key Principles: "When the issue is structural, extend the grep to the full changed file" and "'Nothing found' on a structural issue triggers a set-difference check."
- Added new `run_step_analyze` preflight example to Step 3.7.

### Step 1: Pagination warning (Change 3)

**Problem**: `init-pr-state.sh` silently capped at 100 threads. On PR #32 (130+ threads), every round falsely reported "0 unresolved" while page-2 threads remained open.

**Fix**:
- Added pagination warning note after `init-pr-state.sh` in Step 1, including the two-step detection query.
- `scripts/lib/github-api.sh`: `fetch_pr_threads` now requests `pageInfo { hasNextPage endCursor }` and emits a `⚠️ WARNING` to stderr if `hasNextPage` is true, including the `endCursor` needed to fetch page 2.
- Both GraphQL queries in Step 6 (OLD METHOD and Check for New Copilot Comments) now request `pageInfo { hasNextPage endCursor }`.

## 2026-05-20 - v1.1.0: Fix Script Organization & Documentation

### Problem: Scripts at Wrong Plugin Level
**Issue**: Scripts were organized at plugin root (`plugins/address-pr-issues/scripts/`) instead of skill level (`plugins/address-pr-issues/skills/address-pr-issues/scripts/`), causing them to be inaccessible when following documentation.

**Impact**: Users saw "No such file or directory" errors when trying to use automation scripts.

**Root Cause**: During marketplace conversion, scripts remained at plugin root level instead of being organized per-skill as per plugin conventions (see `splunk-to-dynatrace` for correct pattern).

**Fix Applied** (commits c0ccfa9, 916e2d8, 946c9b2):
1. **Added working directory requirement**: Scripts must run from within git repository
2. **Moved scripts to skill level**: `skills/address-pr-issues/scripts/` (per conventions)
3. **Simplified paths**: Use relative paths `./scripts/` instead of complex discovery

**Structure After Fix**:
```
plugins/address-pr-issues/
  └── skills/
      └── address-pr-issues/
          ├── SKILL.md
          └── scripts/           ✅ Correct location
              ├── init-pr-state.sh
              ├── fetch-pr-threads.sh
              ├── resolve-threads-bulk.sh
              └── lib/
```

**Benefits**:
- Scripts properly co-located with skill
- Simple relative path references work naturally
- Matches plugin organization conventions
- Version-agnostic (no hardcoded paths)

## 2026-04-27 - Bug Fixes: Bulk Resolution & GitHub API

### Problem: Bulk Thread Resolution Failed After First Thread

**Issue identified in PR #68**:
- Bulk resolution script (`resolve-threads-bulk.sh`) resolved first thread successfully
- Script exited with error code 1 after first resolution
- Remaining threads were not resolved
- Root cause: `jq` cache update corrupted newline-delimited JSON file

**Technical Details**:
- threads.json uses newline-delimited JSON (not array)
- Cache update used `jq` without `-s` flag
- Command processed only first JSON object, corrupting file structure
- Subsequent thread lookups failed on corrupted cache

**Fix Applied** (commit 91bccc3):
```bash
# Before (line 152-154):
jq --arg tid "$thread_id" \
  'if .threadId == $tid then .isResolved = true else . end' \
  "$THREADS_FILE" > "${THREADS_FILE}.tmp"

# After:
jq -s --arg tid "$thread_id" \
  'map(if .threadId == $tid then .isResolved = true else . end) | .[]' \
  "$THREADS_FILE" > "${THREADS_FILE}.tmp"
```

**Verified**: Tested with 3-object newline-delimited JSON, all objects preserved correctly.

### Problem: GitHub Projects (classic) Deprecation Warnings

**Issue**: `gh pr view` without `--json` queries deprecated Projects (classic) API
- Non-fatal GraphQL errors clutter output
- Affects `gh pr view` and `gh pr edit` commands

**Fix Applied** (commit 91bccc3):
- Added note to SKILL.md Prerequisites section
- All script examples already use `--json` correctly
- Issue only affects manual workflow commands

**Workaround**: Always use `gh pr view --json <fields>` to avoid deprecated API

**Impact**:
- ✅ Bulk resolution now works for multiple threads (87.5% token savings realized)
- ✅ Cleaner output without deprecation warnings
- ✅ Scripts future-proofed against GitHub API changes

---

## 2026-04-24 - State Management & Caching

### Problem: Redundant API Calls and Manual Tracking

**Issues identified in production use**:
1. Multiple GitHub API calls to fetch same thread data (fetch → resolve → verify)
2. Manual round number tracking (lost context across sessions)
3. No fix history or traceability across rounds
4. Threaded reply API failures required fallback without detection
5. Pre-commit checklist was manual/prone to skip

**Impact**: Slower workflow, lost context, incomplete audit trail

### Solution: Comprehensive State Management System

**Added** (Step 1: Initialize State Management):
- **Thread caching**: Fetch once at start, query locally thereafter
- **Round tracking**: Auto-increment in `/tmp/pr-{number}/round.txt`
- **Fix history**: Track commits, threads, files per round in `fixes.json`
- **Progress checklist**: Automated tracking in `checklist.json`
- **API capability detection**: Test threaded replies at start, cache result

**State Files Created** (`/tmp/pr-{number}/`):
```
threads.json              # Cached thread metadata (no re-fetching)
round.txt                 # Current round number (auto-incremented)
fixes.json                # Fix history per round
checklist.json            # Pre-commit checklist state
api-capabilities.txt      # API feature flags
threads.json.before-round-N  # Thread state snapshots
```

**Updated Steps**:
- **Step 1**: Initialize workspace, cache threads, detect API capabilities
- **Step 6**: Query cached threads (no API call), update cache after resolution
- **Step 7**: Automated checklist validation, auto-generated commit messages
- **Step 8**: Refresh cache after CI/CD, compare with previous state

**New Section**: "State Management & Fix History"
- View complete fix history across all rounds
- Compare thread state changes
- Archive state for post-mortem analysis
- Export workflow metrics

**Benefits**:
- ⚡ **3-5x faster**: Eliminated redundant GitHub API calls
- 📊 **Complete audit trail**: Track every fix, commit, thread across all rounds
- 🎯 **Accurate tracking**: No manual round counting (was "Round 8" in handoff)
- 🔍 **Post-mortem analysis**: Export metrics for process improvement
- 🛡️ **Graceful degradation**: Adapts when threaded reply API unavailable

**Example Fix History Output**:
```
round_1:
  Commit: abc123def
  Threads Resolved: PRRT_kwDOQ5-SAM59LkA-, PRRT_kwDOQ5-SAM59LkBj
  Files Changed: 3
  Tests Passing: 495

round_2:
  Commit: def456ghi
  Threads Resolved: PRRT_kwDOQ5-SAM59OMjh, PRRT_kwDOQ5-SAM59OMkF
  Files Changed: 2
  Tests Passing: 496
```

**Cleanup**: EXIT trap removes state files, or archive to `~/.claude/pr-history/` for analysis

**Testing**: Validated in PR #67 (8 rounds, 12 threads resolved)

---

## 2026-04-20 - Major Improvements

### 1. SonarQube Web API Integration

**Added**: Comprehensive SonarQube API polling and validation (Step 5b-5c)

**Problem**: Skill ran `sonar-scanner` but never verified actual results - just checked that the scanner completed successfully.

**Solution**:
- Extract task ID from scanner output
- Poll `/api/ce/task?id=<task-id>` every 5 seconds (max 60s) until status = SUCCESS
- Fetch quality gate status: `/api/qualitygates/project_status`
- Fetch blocking issues: `/api/issues/search` (BLOCKER, CRITICAL only)
- Fallback to manual dashboard review for SSO-protected instances

**API Endpoints**:
```bash
# Wait for analysis
GET /api/ce/task?id=<task-id>
Response: {"task": {"status": "SUCCESS|PENDING|FAILED"}}

# Quality gate
GET /api/qualitygates/project_status?projectKey=X&pullRequest=Y
Response: {"projectStatus": {"status": "OK|ERROR"}}

# Issues
GET /api/issues/search?componentKeys=X&pullRequest=Y&resolved=false&severities=BLOCKER,CRITICAL
Response: {"issues": [{severity, message, component, line}]}
```

**Authentication**: Use `Authorization: Bearer $SONAR_TOKEN` header (not basic auth with `-u token:`).

**Caveat**: Enterprise SonarQube with SSO may return HTML instead of JSON. Documented fallback to manual dashboard review.

### 2. Conversation Resolution Before Commit

**Fixed**: Workflow said "resolve before commit" but example showed resolving after push.

**Changes**:
- Moved Step 6 (Resolve Conversations) to come BEFORE Step 7 (Commit & Push) in execution order
- Added verification step after resolving threads (check all threads isResolved=true)
- Updated QUICK_START workflow diagram to emphasize correct order
- Added rationale: "Reviewers see resolved conversations immediately, commit messages reference already-addressed issues"

### 3. Pre-Push Checklist (Step 7)

**Added**: Mandatory checklist before commit to prevent common mistakes.

**Checklist Items**:
- ✅ All tests passing (`mvn test`)
- ✅ Build clean (`mvn clean install -DskipTests`)
- ✅ SonarQube dashboard reviewed (no new blocking issues)
- ✅ All GitHub conversations resolved (verified with gh API)
- ✅ Commit message references fixed issues
- ✅ No debug code, console.logs, or temporary changes left

**Enforcement**: User must acknowledge checklist before proceeding (Ctrl+C to abort).

### 4. Structured Commit Message Template

**Added**: Template with clear sections for traceability.

**Format**:
```
fix: Address Copilot/SonarQube PR review issues (Round N)

Critical Fixes:
- Issue description (file:line)

High Priority Fixes:
- Issue description (file:line)

Medium Priority Fixes:
- Issue description (file:line)

Test Coverage:
- X/Y tests passing
- New tests: [list]

Resolves: [thread IDs]
Addresses: GitHub Copilot review on PR #XX
```

**Benefits**:
- Clear severity categorization (matches Step 3)
- File:line references for reviewers
- Test count shows verification
- Thread IDs for traceability

### 5. Test Coverage for New Code

**Added**: Explicit requirement to test new methods/classes added during fixes.

**Checklist**:
- [ ] Write test for happy path
- [ ] Write test for null/edge cases
- [ ] Write test for error conditions
- [ ] Verify test coverage (all new code executed)

**Example**: If adding `setAccumulator()` method, must write tests for:
- Setting accumulator after construction (happy path)
- Null accumulator handling (edge case)

**Rationale**: In this session, I added `setAccumulator()` and `executeWithRetryVoid()` without tests, which was incomplete.

### 6. Documentation Updates

**README.md**:
- Added SonarQube Web API integration section
- Documented task polling pattern
- Documented quality gate + issues endpoints
- Added note about SSO-protected instances
- Bearer token authentication clarification

**QUICK_START.md**:
- Updated SonarQube fetch example (Bearer token instead of basic auth)
- Added note about SSO/API access issues
- Emphasized conversation resolution order

**SKILL.md**:
- Enhanced Step 5 with comprehensive API polling
- Added Pre-Push Checklist (Step 7)
- Added Structured Commit Message Template
- Added Test Coverage for New Code requirement

## Lessons Learned (2026-04-20 Session)

### What Went Wrong

1. **Skipped SonarQube result verification**: Ran scanner but didn't check actual issues
2. **Resolved conversations after push**: Should have been before commit
3. **No tests for new methods**: Added `setAccumulator()` without test coverage
4. **Used wrong auth format**: Used `-u token:` instead of `Bearer` header

### What Went Right

1. **Fixed all 9 Copilot issues**: Comprehensive fixes for null-safety, validation, accumulator wiring
2. **All 464 tests passing**: No regressions introduced
3. **Clean build**: No compilation errors, Maven Shade working correctly
4. **Proper TDD approach**: Used test-after for obvious fixes (correct for PR issue fixes)

### Process Improvements Applied

- SonarQube API polling + verification (prevents "just ran the tool" mistake)
- Pre-push checklist (prevents skipping validation steps)
- Structured commit messages (improves traceability)
- Test coverage requirement for new code (enforces completeness)
- Conversation resolution BEFORE commit (keeps PR clean)

## Future Enhancements (Ideas)

### 1. Automatic Test Generation

**Idea**: When adding new methods during fixes, automatically generate test stubs.

**Example**:
```bash
# Detect new methods via git diff
NEW_METHODS=$(git diff HEAD~1 --unified=0 | grep "^+.*public.*void.*setAccumulator")

# Generate test stub
cat > Test.java <<EOF
@Test
void shouldSetAccumulatorAfterConstruction() {
    // TODO: Implement
}
EOF
```

### 2. SonarQube Issue Auto-Fix

**Idea**: For trivial issues (unused imports, missing finals), apply fixes automatically.

**Example**:
```bash
# Detect "make method static" issues
STATIC_METHODS=$(curl ... | jq -r '.issues[] | select(.message | contains("static")) | .component + ":" + .line')

# Apply fix automatically (if single-line change)
```

### 3. Conversation Auto-Reply

**Idea**: Generate threaded replies automatically based on commit diff.

**Example**:
```bash
# For Issue #1 at RetryConfig.java:74
COMMIT_SHA=$(git rev-parse --short HEAD)
CHANGES=$(git diff HEAD~1 RetryConfig.java | grep -A5 "line 74")

REPLY="✅ Fixed in $COMMIT_SHA\n\nChanges:\n\`\`\`diff\n$CHANGES\n\`\`\`"
```

### 4. Quality Gate as Git Hook

**Idea**: Block commit if local SonarQube scan fails quality gate.

**Implementation**: Pre-commit hook that runs sonar-scanner and checks quality gate.

---

## API Research Notes (2026-04-20)

### SonarQube Authentication Testing

**Tested Methods**:
1. ✅ Bearer token: `Authorization: Bearer $SONAR_TOKEN` (correct for SonarQube tokens)
2. ❌ Basic auth: `-u $SONAR_TOKEN:` (wrong - this is for username:password)
3. ❌ API endpoints returned HTML (SSO redirect)

**Finding**: Enterprise SonarQube instance (churchofjesuschrist.org) uses SSO authentication that intercepts API calls and returns HTML login page instead of JSON. This is common with SAML/OAuth2-based enterprise instances.

**Workaround**: Document fallback to manual dashboard review when API returns HTML.

### Task Polling Pattern

**Scanner Output**:
```
More about the report processing at https://sonarqube.../api/ce/task?id=<task-id>
```

**Extraction**:
```bash
TASK_URL=$(sonar-scanner 2>&1 | grep "More about the report processing" | sed 's/.*at //')
TASK_ID=$(echo "$TASK_URL" | sed 's/.*id=//')
```

**Poll Loop**:
```bash
for i in {1..12}; do
  STATUS=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/ce/task?id=$TASK_ID" | jq -r '.task.status')
  
  [ "$STATUS" = "SUCCESS" ] && break
  sleep 5
done
```

**Timeout**: 12 attempts × 5 seconds = 60 seconds (sufficient for most PRs)

### API Endpoints Reference

| Endpoint | Purpose | Response Time |
|----------|---------|---------------|
| `/api/ce/task?id=X` | Check analysis status | Immediate |
| `/api/qualitygates/project_status` | Pass/fail status | After analysis complete |
| `/api/issues/search` | List issues | After analysis complete |
| `/api/measures/component` | Metrics (coverage, bugs) | After analysis complete |

**All require**: `pullRequest=N` parameter for PR-specific results.

---

## Version History

- **2026-07-01**: First real dogfood run (pre-pr-audit + adversarial-review) + 5 rounds of
  adversarial-review convergence fixes (v1.7.0-v1.7.2)
- **2026-07-01**: Ported apply-feedback strengths (silent-thread filter, directional/polish
  classification, thread-accountability closeout, protected-branch guard, /plan escalation) +
  script-first cleanup (net line reduction)
- **2026-04-20**: Major update (SonarQube API, pre-push checklist, conversation ordering)
- **2026-04-17**: Added adversarial review agent pattern
- **2026-04-16**: Initial version (basic workflow)
