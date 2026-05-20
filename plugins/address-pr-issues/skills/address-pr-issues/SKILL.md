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
- **Step 3.5 (NEW)**: Conditionally spawn adversarial reviewer agent
- Agent probes: "What else can be null? empty? malformed?"
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

## Workflow Overview

1. **Fetch Issues**: Read Copilot PR comments and SonarQube analysis
2. **Assess Complexity**: Determine if adversarial review agent needed (NEW)
3. **Prioritize**: Categorize issues by severity and present questionable ones to user
4. **Plan**: Create implementation plan using TDD principles
5. **Execute**: Fix issues using xp-pair for complex changes
6. **Validate**: Run local sonar-scanner to catch new issues before committing
7. **Iterate**: Repeat steps 5-6 until no new blocking issues appear
8. **Resolve Conversations**: Mark fixed GitHub threads as resolved with brief explanations
9. **Commit & Push**: Commit changes and push to PR branch
10. **Monitor**: Check for new Copilot comments triggered by the commit (wait ~5-10 min)
11. **Repeat**: If new significant issues appear, return to step 5

**IMPORTANT**: This is an **iterative process**. Expect multiple rounds:
- Fixing code often introduces new SonarQube issues (e.g., extracted methods should be static)
- Copilot analysis happens **after each commit**, potentially adding new suggestions
- Local `sonar-scanner` is CRITICAL to catch issues before CI/CD (saves 30+ min per iteration)
- **Resolve conversations BEFORE pushing** to keep PR clean and show reviewers what's been addressed
- **Adversarial review** (NEW): For complex bugs with edge cases, spawn reviewer agent to challenge completeness BEFORE implementing fixes (reduces rounds from 5+ to 1-2)

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
- `check-sonar-quality-gate.sh <pr_number>` - Check quality gate + fetch issues
- `resolve-thread.sh <pr_number> <thread_id> [message]` - Resolve single thread with reply
- `resolve-threads-bulk.sh <pr_number> [options]` - Resolve multiple threads at once (NEW)
- `commit-pr-fixes.sh <pr_number>` - Generate structured commit with round tracking

**Hybrid Approach**: Use scripts for repetitive operations, inline commands for one-off tasks.

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

# Get PR details
gh pr view $PR_NUMBER --json number,title,headRefName,baseRefName,url
```

### Initialize State Management (AUTOMATED)

**Use script** (recommended - saves tokens):
```bash
./scripts/init-pr-state.sh $PR_NUMBER
```

**Manual approach** (for debugging or customization):
```bash
# Setup workspace directory for this PR
WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"
mkdir -p "$WORKSPACE_DIR"

# Register cleanup trap
trap "rm -rf $WORKSPACE_DIR" EXIT

# Initialize round tracking
ROUND_FILE="$WORKSPACE_DIR/round.txt"
if [ -f "$ROUND_FILE" ]; then
  ROUND=$(($(cat $ROUND_FILE) + 1))
  echo "📍 Continuing workflow - Round $ROUND"
else
  ROUND=1
  echo "📍 Starting workflow - Round $ROUND"
fi
echo $ROUND > $ROUND_FILE

# Cache thread metadata for reuse (uses lib/github-api.sh functions)
THREADS_FILE="$WORKSPACE_DIR/threads.json"
source "./scripts/lib/github-api.sh"
fetch_pr_threads "$PR_NUMBER" "$THREADS_FILE"

COPILOT_COUNT=$(jq -s 'map(select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]")) | length' "$THREADS_FILE")
echo "✅ Cached $COPILOT_COUNT Copilot threads"

# Test API capabilities (threaded replies)
API_CAPS_FILE="$WORKSPACE_DIR/api-capabilities.txt"
CAPABILITY=$(test_threaded_reply_api "$THREADS_FILE")
echo "$CAPABILITY" > "$API_CAPS_FILE"

TEST_COMMENT_ID=$(jq -r '.[0].commentId // empty' "$THREADS_FILE")
if [ -n "$TEST_COMMENT_ID" ]; then
  if gh api repos/{owner}/{repo}/pulls/comments/$TEST_COMMENT_ID/replies \
      -f body="test" 2>&1 | grep -q "404"; then
    echo "threaded_replies_disabled" > "$API_CAPS_FILE"
    echo "⚠️  Threaded replies API not available - will use direct thread resolution"
  else
    echo "threaded_replies_enabled" > "$API_CAPS_FILE"
    # Delete test reply
    gh api repos/{owner}/{repo}/pulls/comments/$TEST_COMMENT_ID/replies --method DELETE 2>/dev/null || true
  fi
fi

# Initialize fix tracking
FIXES_FILE="$WORKSPACE_DIR/fixes.json"
if [ ! -f "$FIXES_FILE" ]; then
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
```

**State Files Created**:
- `$WORKSPACE_DIR/round.txt` - Current round number (auto-incremented)
- `$WORKSPACE_DIR/threads.json` - Cached thread metadata (avoids re-fetching)
- `$WORKSPACE_DIR/api-capabilities.txt` - API feature detection results
- `$WORKSPACE_DIR/fixes.json` - Fix history per round
- `$WORKSPACE_DIR/checklist.json` - Pre-commit checklist state

**Benefits**:
- Faster workflow (no redundant API calls)
- Accurate round tracking in commit messages
- Progress tracking across iterations
- Graceful API capability detection

### Query Cached Threads (AUTOMATED)

**Use script** (recommended):
```bash
# Display unresolved threads with summary
./scripts/fetch-pr-threads.sh $PR_NUMBER --unresolved-only
```

**Manual jq queries** (for custom filtering):
```bash
# Get unresolved Copilot threads
jq -r 'select(.author == "copilot-pull-request-reviewer" or .author == "github-advanced-security[bot]") | select(.isResolved == false)' "$THREADS_FILE" | jq -s .

# Count resolved vs unresolved
TOTAL=$(jq -s length "$THREADS_FILE")
RESOLVED=$(jq 'select(.isResolved == true)' "$THREADS_FILE" | jq -s length)
UNRESOLVED=$(jq 'select(.isResolved == false)' "$THREADS_FILE" | jq -s length)

echo "Thread Status: $RESOLVED/$TOTAL resolved, $UNRESOLVED unresolved"
```

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

### Decision: Use Adversarial Agent?

**YES - Spawn reviewer agent**:
```
Issues involve: Privacy filtering + null checks + conservative cleanup
→ High risk of cascading edge cases
→ Spawn adversarial reviewer to challenge completeness BEFORE implementing
```

**NO - Proceed directly**:
```
Issues are: Simple style fixes, obvious bugs with clear solutions
→ Low complexity, no edge case risk
→ Fix directly without agent overhead
```

### Fetch SonarQube Issues (AUTOMATED)

**Use script** (recommended - checks quality gate + fetches blocking issues):
```bash
./scripts/check-sonar-quality-gate.sh $PR_NUMBER
```

**Manual API calls** (for custom queries):
```bash
# Ensure sonar-project.properties exists
if [ ! -f "sonar-project.properties" ]; then
    echo "⚠️  No sonar-project.properties found. Creating from template..."
    # Create or copy from reference repository
fi

# Use library function (DRY)
source "./scripts/lib/sonar-api.sh"
get_quality_gate_status "$PR_NUMBER" > quality-gate.json
format_quality_gate_status quality-gate.json

# Or manual curl (if customization needed)
PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)
SONAR_HOST=$(grep "^sonar.host.url=" sonar-project.properties | cut -d= -f2)

curl -s -u "$SONAR_TOKEN:" \
  "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&pullRequest=$PR_NUMBER&resolved=false" \
  | jq '.issues[] | {key, message, severity, type, component, line, status}'
```

**SonarQube API endpoints** (via `lib/sonar-api.sh`):
- `get_quality_gate_status` - Quality gate for PR
- `get_pr_issues` - Issues by severity
- `wait_for_analysis` - Poll for analysis completion

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

For any MEDIUM or LOW severity issues, or issues you're uncertain about:

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

Should I address these? (yes/no/selective)
```

## Step 3.5: Spawn Adversarial Reviewer (Conditional)

**If Step 2 assessment indicates high complexity**, spawn reviewer agent BEFORE implementing fixes.

### Adversarial Review Agent Pattern

**Agent Role**: Challenge completeness, probe edge cases, demand comprehensive tests

**Agent Prompt Template**:
```
You are an adversarial code reviewer. Your job is to challenge the proposed fixes for completeness BEFORE implementation.

Context: We're fixing [describe issues - e.g., "null handling bugs in privacy-critical persona filtering"]

Code Section: [file paths and line numbers]

Proposed Fixes: [brief summary of intended changes]

Your Task:
1. **Challenge Missing Edge Cases**
   - What can be null that isn't being checked?
   - What can be empty that isn't being validated?
   - What combinations are missing? (null + empty, valid + invalid)
   
2. **Probe Related Bugs**
   - If fixing null persona refs, what about null resource URIs?
   - If checking persona IDs, what about relationship IDs?
   - Are similar patterns buggy elsewhere in this file?

3. **Demand Comprehensive Tests**
   - List ALL scenarios that must be tested (not just reported issues)
   - Include: null, empty, malformed, duplicates, combinations
   - Require: happy path + edge cases + error paths

4. **Question Design**
   - Is this a proper fix or a patch?
   - Should logic be extracted/simplified?
   - Is conservative approach applied consistently?

Output Format:
## Edge Cases to Test
- [scenario 1]
- [scenario 2]
...

## Related Bugs to Check
- [potential bug 1]
- [potential bug 2]
...

## Design Questions
- [question 1]
- [question 2]
...

Be thorough and skeptical. Force comprehensive analysis BEFORE coding.
```

### When to Skip Adversarial Review

**Skip agent if**:
- Simple style fixes (comments, formatting, imports)
- Obvious bugs with clear, isolated fixes
- No edge case risk (CRUD operations, straightforward logic)
- Time-sensitive hotfix (fix now, comprehensive tests later)

### Example: Adversarial Review in Action

**Without Agent** (5 rounds):
```
Round 1: Fix substring matching bug
Round 2: Fix null persona refs (Copilot found)
Round 3: Fix empty persona IDs (Copilot found)
Round 4: Fix size mismatch logic (Copilot found)
Round 5: Fix null resource URIs (Copilot found)
```

**With Agent** (1 round):
```
Agent: "You're fixing substring matching - what else can go wrong?
        - Null persona refs? Add test.
        - Null resource URIs? Add test.
        - Empty persona IDs? Add test.
        - Duplicate IDs in Set? Add test.
        
        Show me size mismatch logic - can it handle duplicates?
        No? Fix that too."

[Implement ALL fixes + tests in one commit]
→ Copilot finds only style issues in next round
```

**Result**: 80% reduction in rounds, better code quality, faster delivery

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

## Step 4: Execute Fixes (Iterative Loop)

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
PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)
SONAR_HOST=$(grep "^sonar.host.url=" sonar-project.properties | cut -d= -f2)

# Poll task status (max 12 attempts = 60 seconds)
echo "⏳ Waiting for SonarQube server processing..."
for i in {1..12}; do
  STATUS=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/ce/task?id=$TASK_ID" 2>/dev/null | jq -r '.task.status' 2>/dev/null)
  
  if [ "$STATUS" = "SUCCESS" ]; then
    echo "✅ Analysis complete"
    break
  elif [ "$STATUS" = "FAILED" ]; then
    echo "❌ Analysis failed - check dashboard"
    break
  fi
  
  echo "   Processing... ($i/12)"
  sleep 5
done
```

**Note**: Some enterprise SonarQube instances use SSO that blocks API access. If the poll fails, proceed to manual dashboard review.

### Step 5c: Review Results

**Option A: API Access Available** (preferred):
```bash
# Fetch quality gate status
QG_STATUS=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "$SONAR_HOST/api/qualitygates/project_status?projectKey=$PROJECT_KEY&pullRequest=$PR_NUMBER" \
  | jq -r '.projectStatus.status')

if [ "$QG_STATUS" = "OK" ]; then
  echo "✅ Quality gate: PASSED"
elif [ "$QG_STATUS" = "ERROR" ]; then
  echo "❌ Quality gate: FAILED"
  
  # Fetch blocking issues
  curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&pullRequest=$PR_NUMBER&resolved=false&severities=BLOCKER,CRITICAL" \
    | jq -r '.issues[] | "  - [\(.severity)] \(.message) (\(.component):\(.line))"'
  
  echo ""
  echo "Fix blocking issues before committing"
  exit 1
else
  echo "⚠️  Could not determine quality gate status (likely SSO-protected API)"
  echo "   Proceed to manual dashboard review below"
fi
```

**Option B: Manual Dashboard Review** (fallback for SSO-protected instances):
```bash
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  CRITICAL: Review SonarQube Dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   URL: $SONAR_HOST/dashboard?id=$PROJECT_KEY&pullRequest=$PR_NUMBER"
echo ""
echo "   Wait 30-60 seconds for analysis, then verify:"
echo "   - ✅ Quality Gate: PASSED"
echo "   - ✅ No new BLOCKER or CRITICAL issues"
echo "   - ✅ Coverage acceptable (no significant drop)"
echo "   - ✅ Security hotspots reviewed"
echo ""
read -p "Press Enter after dashboard review confirms no blocking issues..."
echo ""
```

**If new issues found**: Fix them before committing (iterate Step 4-5).

## Step 6: Resolve Conversations (BEFORE Commit)

**CRITICAL**: Resolve GitHub conversations BEFORE pushing commit. This keeps the PR clean and shows reviewers what you've addressed.

**REQUIRED**: You MUST resolve review threads. This is not optional - it's a core part of the workflow.

### Resolve Fixed Issues (AUTOMATED)

**Use bulk script** (recommended - resolve multiple threads at once):
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

**Use single-thread script** (when different messages needed):
```bash
# Resolve thread with optional message (tries threaded reply, falls back to direct resolution)
./scripts/resolve-thread.sh $PR_NUMBER "$THREAD_ID" "Fixed: Added null check for persona refs"

# Multiple threads with different messages (loop)
for thread_id in "$THREAD_ID_1" "$THREAD_ID_2" "$THREAD_ID_3"; do
  ./scripts/resolve-thread.sh $PR_NUMBER "$thread_id" "Fixed specific issue"
done
```

**Manual approach** (for customization):

#### Option A: Threaded Reply + Resolve (Preferred)

```bash
# Use library function (handles capability detection)
source "./scripts/lib/github-api.sh"

if try_threaded_reply "$COMMENT_ID" "✅ Fixed: Added null check"; then
  echo "Reply added"
fi

resolve_thread "$THREAD_ID"
```

#### Option B: Direct API calls (maximum control)

```bash
# Step 1: Add threaded reply explaining the fix
gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
  -f body="✅ Fixed: [brief explanation]

Details: [what you changed and why]
Will be included in next commit."

# Step 2: Resolve the review thread
gh api graphql -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
      thread { id isResolved }
    }
  }
' -f threadId="$THREAD_ID"
```

**Key points**:
- ❌ Top-level comments alone are NOT sufficient - threads must be resolved
- ✅ Script automatically detects threaded reply capability and adapts
- ✅ Resolve threads even if you can't add threaded replies

### Document Won't-Fix Decisions

For issues you're not fixing:

```bash
# Try to reply to the specific thread (if API works)
gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
  -f body="Won't fix: [reason]

Rationale: [explanation - e.g., outside PR scope, style preference, etc.]
See CLAUDE.md section X for context."

# ALWAYS resolve the thread (mark as acknowledged) - REQUIRED
gh api graphql -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
      thread { id isResolved }
    }
  }
' -f threadId="$THREAD_ID"
```

**Resolving threads is MANDATORY** - it signals to reviewers that you've acknowledged and addressed each issue.

### Get Thread IDs and Comment IDs (Using Cache)

**NEW**: Use cached thread data instead of re-fetching:

```bash
# Get unresolved threads from cache (fast, no API call)
jq -r 'select(.isResolved == false)' "$THREADS_FILE" | jq -s .

# Example: Resolve a specific thread
THREAD_ID=$(jq -r 'select(.path == "FullExportJob.java" and .line == 186) | .threadId' "$THREADS_FILE")
COMMENT_ID=$(jq -r 'select(.path == "FullExportJob.java" and .line == 186) | .commentId' "$THREADS_FILE")

# Check API capabilities before attempting threaded reply
if grep -q "threaded_replies_enabled" "$API_CAPS_FILE" 2>/dev/null; then
  # Option A: Try threaded reply first
  gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
    -f body="✅ Fixed: [explanation]" || {
    # Fallback to direct resolution if reply fails
    gh api graphql -f query='
      mutation($threadId: ID!) {
        resolveReviewThread(input: {threadId: $threadId}) {
          thread { id isResolved }
        }
      }
    ' -f threadId="$THREAD_ID"
  }
else
  # Option B: Direct resolution (no threaded reply support)
  gh api graphql -f query='
    mutation($threadId: ID!) {
      resolveReviewThread(input: {threadId: $threadId}) {
        thread { id isResolved }
      }
    }
  ' -f threadId="$THREAD_ID"
fi

# Update cache to mark thread as resolved
jq --arg tid "$THREAD_ID" 'if .threadId == $tid then .isResolved = true else . end' "$THREADS_FILE" > "${THREADS_FILE}.tmp" && mv "${THREADS_FILE}.tmp" "$THREADS_FILE"
```

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

### OLD METHOD (For Reference)

If you need to re-fetch threads (e.g., after new Copilot comments):

```bash
# Fetch all unresolved threads with comment IDs
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
                body
                path
                line
              }
            }
          }
        }
      }
    }
  }
' -F owner='{owner}' -F repo='{repo}' -F pr=$PR_NUMBER \
  | jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | {
    threadId: .id,
    commentId: .comments.nodes[0].databaseId,
    body: .comments.nodes[0].body,
    path: .comments.nodes[0].path,
    line: .comments.nodes[0].line
  }'
```

**Important fields**:
- `threadId` (GraphQL ID) - Used for resolving the thread
- `commentId` (Database ID) - Used for replying to the review comment
- First comment in thread is usually the Copilot issue

**Why resolve threads?**
- **Shows reviewers you've addressed each issue** - they can see at a glance what's been fixed
- **Cleaner PR interface** - resolved threads collapse, reducing clutter
- **Clear audit trail** - documents that each concern was considered
- **Better git history** - commits can reference resolved issues

**Why resolve BEFORE commit?**
- Cleaner workflow: Fix → Resolve → Commit → Push
- Reviewers see resolved threads immediately after your push
- Easier to track progress during iterations

**Summary**: Resolving threads is REQUIRED. If threaded replies fail, fall back to resolving threads + optional top-level comment.

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

**Use script** (recommended - auto-generates message with round tracking):
```bash
# Stage changes first
git add <files>

# Generate commit and update fix tracking
./scripts/commit-pr-fixes.sh $PR_NUMBER
```

**Manual approach** (for customization):
```bash
# Collect resolved thread IDs from cache
RESOLVED_THREADS=$(jq -r 'select(.isResolved == true) | .threadId' "$THREADS_FILE" | tr '\n' ', ' | sed 's/,$//')

# Get changed files
CHANGED_FILES=$(git diff --cached --name-only)

# Build simple commit message (round tracking from $WORKSPACE_DIR/round.txt)
ROUND=$(cat "$WORKSPACE_DIR/round.txt")
git commit -m "fix: Address PR #${PR_NUMBER} review feedback (Round ${ROUND})

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Record fix in history
COMMIT_SHA=$(git rev-parse HEAD)
jq --arg round "$ROUND" \
   --arg commit "$COMMIT_SHA" \
   --argjson files "$(echo "$CHANGED_FILES" | jq -R . | jq -s .)" \
   '.[$round] = {
     commit: $commit,
     files: $files,
     timestamp: (now|todate)
   }' "$FIXES_FILE" > "${FIXES_FILE}.tmp" && mv "${FIXES_FILE}.tmp" "$FIXES_FILE"

echo "✅ Recorded Round $ROUND fixes in $FIXES_FILE"

# Push to PR branch
git push origin $(git branch --show-current)
```

**Benefits**:
- **Auto-incremented round numbers** (no manual tracking)
- **Thread IDs automatically collected** from cache
- **Fix history persisted** for post-mortem analysis
- **Commit SHA tracked** for traceability

**Commit Message Template Explained**:
- **Round $ROUND**: Auto-incremented from state file
- **Critical/High/Medium**: Match severity categories from Step 3
- **file:line**: Help reviewers locate changes
- **Test Coverage**: Auto-counted from test output
- **Resolves**: Auto-generated from resolved threads in cache

## Step 8: Monitor for New Copilot Comments

**IMPORTANT**: After pushing, Copilot may analyze the new commit and add MORE comments.

### Wait for CI/CD to Complete

```bash
# Check CI/CD status (typically 15-30 minutes)
gh run watch

# OR: Check manually after waiting
gh run list --branch $(git branch --show-current) --limit 1
```

### Check for New Copilot Comments (Update Cache)

**NEW**: Refresh cached thread data after CI/CD completes:

```bash
# Save current state for comparison
cp "$THREADS_FILE" "${THREADS_FILE}.before-round-${ROUND}"

# Re-fetch threads after CI/CD completes
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
' -F owner='{owner}' -F repo='{repo}' -F pr=$PR_NUMBER \
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
  }' > "$THREADS_FILE"

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
├─ Critical/High → Fix immediately (Step 4 again)
├─ Medium → User decides: fix now or later
└─ Low → Document and defer to future PR/ticket
```

### Example: Post-Commit Iteration

```bash
# Pushed commit fixing 5 issues
git push origin feature/my-branch

# Wait 30 minutes, CI/CD completes
# Copilot adds 2 NEW comments:
#   1. "Consider using early returns" (MEDIUM)
#   2. "Add unit test for edge case" (LOW)

# Decision: Fix #1 now (improves readability), defer #2 (already have tests)
[Implement early returns...]
mvn test && sonar-scanner
git commit -m "refactor: Use early returns per Copilot suggestion"
git push
```

**Pro tip**: Limit to **2-3 post-commit iterations** maximum. Diminishing returns after that.

**Note**: After post-commit fixes, repeat Step 6 (resolve new conversations) before pushing again.

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

## State Management & Fix History (NEW)

### View Fix History

After completing multiple rounds, view the complete fix history:

```bash
# View all fixes across all rounds
cat "$FIXES_FILE"

# Pretty-print fix history
jq -r 'to_entries[] | "
\(.key):
  Commit: \(.value.commit)
  Threads Resolved: \(.value.threads_resolved | join(", "))
  Files Changed: \(.value.files_changed | length)
  Tests Passing: \(.value.tests_passing)
"' "$FIXES_FILE"

# Example output:
# round_1:
#   Commit: abc123def
#   Threads Resolved: PRRT_kwDOQ5-SAM59LkA-, PRRT_kwDOQ5-SAM59LkBj
#   Files Changed: 3
#   Tests Passing: 495
# 
# round_2:
#   Commit: def456ghi
#   Threads Resolved: PRRT_kwDOQ5-SAM59OMjh, PRRT_kwDOQ5-SAM59OMkF
#   Files Changed: 2
#   Tests Passing: 496
```

### View Thread History

Compare thread state across rounds:

```bash
# View original thread state (Round 1)
cat "$WORKSPACE_DIR/threads.json.before-round-1"

# View current thread state
cat "$THREADS_FILE"

# Count resolved threads per round
for i in {1..10}; do
  if [ -f "$WORKSPACE_DIR/threads.json.before-round-$i" ]; then
    RESOLVED=$(jq 'select(.isResolved == true)' "$WORKSPACE_DIR/threads.json.before-round-$i" | jq -s length)
    echo "After Round $i: $RESOLVED threads resolved"
  fi
done
```

### Cleanup State Files

After PR is merged, clean up state files:

```bash
# Manual cleanup (if trap didn't execute)
rm -rf "/tmp/pr-${PR_NUMBER}"

# OR: Archive for post-mortem analysis
ARCHIVE_DIR="$HOME/.claude/pr-history"
mkdir -p "$ARCHIVE_DIR"
mv "/tmp/pr-${PR_NUMBER}" "$ARCHIVE_DIR/pr-${PR_NUMBER}-$(date +%Y%m%d)"

echo "✅ Archived PR #${PR_NUMBER} state to $ARCHIVE_DIR"
```

### Post-Mortem Analysis

After completing the PR, analyze the workflow:

```bash
# Count total rounds
TOTAL_ROUNDS=$(jq 'keys | length' "$FIXES_FILE")

# Count total threads resolved
TOTAL_THREADS=$(jq '[.[].threads_resolved[]] | length' "$FIXES_FILE")

# List all commits
jq -r '.[].commit' "$FIXES_FILE"

# Calculate efficiency metrics
echo "PR #${PR_NUMBER} Workflow Summary:"
echo "  Total Rounds: $TOTAL_ROUNDS"
echo "  Total Threads Resolved: $TOTAL_THREADS"
echo "  Average Threads/Round: $((TOTAL_THREADS / TOTAL_ROUNDS))"
echo ""
echo "Round Breakdown:"
jq -r 'to_entries[] | "\(.key): \(.value.threads_resolved | length) threads, \(.value.files_changed | length) files"' "$FIXES_FILE"
```

**Benefits of State Management**:
- **Traceability**: Full audit trail of all fixes
- **Performance Analysis**: Identify bottlenecks (which rounds took longest)
- **Learning**: Understand patterns (which types of issues cascade)
- **Documentation**: Export fix history for handoff docs or post-mortems

## Tips and Best Practices

### Resolve Conversations Before Pushing (Critical!)

**Always resolve GitHub threads BEFORE committing**:
- ✅ Cleaner workflow: Fix → Resolve → Commit → Push
- ✅ Reviewers see resolved conversations immediately
- ✅ Commit messages reference already-addressed issues
- ✅ Easier to track progress across iterations

**Bad workflow** ❌:
```bash
git commit && git push  # Push first
# Now resolve conversations  # Too late!

# OR using wrong API:
gh pr comment $PR --body "Fixed"  # ❌ Top-level comment, not threaded!
```

**Good workflow** ✅:
```bash
# Fix issues
[make changes, run tests, sonar-scanner...]

# Resolve conversations FIRST (threaded replies!)
gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
  -f body="✅ Fixed..."
gh api graphql -f query='mutation...'

# THEN commit and push
git commit -m "fix: Address issues (threads #1, #2 resolved)"
git push
```

**Key API distinction**:
- ❌ `gh pr comment` → Top-level PR comment (not threaded)
- ✅ `gh api .../pulls/comments/$ID/replies` → Threaded reply to specific review comment

### Anticipate Further Issues

When making changes, think ahead:
- Will this introduce new SonarQube warnings?
- Does Copilot flag similar patterns elsewhere?
- Should I apply this fix consistently across the file?

**Run local scans** to catch issues before CI/CD:
```bash
# After each significant change
sonar-scanner -Dsonar.analysis.mode=preview

# Review console output for new issues
```

### Batch Related Issues

Group similar issues in one commit:
- All null checks together
- All resource leaks together
- All style fixes together

**Rationale**: Easier to review, clearer git history

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

