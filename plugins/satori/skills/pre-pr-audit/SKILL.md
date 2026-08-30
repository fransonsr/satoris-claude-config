---
name: pre-pr-audit
description: Proactive code quality audit before creating a pull request - runs a mandatory multi-round adversarial pattern review plus pattern matching and optional SonarQube analysis to identify resource leaks, edge case gaps, test coverage issues, and code quality problems. Automatically fixes issues when possible. Use this skill whenever the user is about to create a PR, push code, or wants to check code quality before committing. Also use when they mention "before PR", "pre-commit check", "quality check", or "catch issues early".
---

# Pre-PR Code Quality Audit

Catch Copilot and SonarQube issues **before** creating a PR by running defensive programming checks and optional static analysis on changed files.

## When to Use This Skill

✅ **BEFORE creating PR** (proactive):
- User says "ready to create PR", "before I push", "check my code", "quality check"
- User asks to "catch issues early", "avoid PR feedback", "pre-commit review"
- After implementing a feature but before committing
- This skill predicts what Copilot will flag BEFORE you push
- **Self-check (NEW)**: run this even if the user never says a trigger phrase, and even if this
  skill already ran earlier for the current tree (compare the same audited-tree hash **and base
  branch** Step 8 below derives — HEAD plus any uncommitted tracked changes via `git stash
  create`, falling back to `git rev-parse HEAD^{tree}` only when the tree is already clean, plus a
  fingerprint of untracked files, plus `$BASE_BRANCH` (derived the same way Step 1 below does —
  this self-check only applies once Step 1 has already run at least once in the current session)
  — against the marker Step 8 writes at
  `"$(git rev-parse --git-dir)/pre-pr-audit-last-audit"`; skip only if **both** the tree and the
  base branch match **and** the recorded outcome is `CLEAN` — re-run on any other outcome, if the
  tree has changed, or if the base branch differs). A plain `HEAD^{tree}` comparison is NOT
  sufficient on its own: this skill routinely audits uncommitted work, and `HEAD^{tree}` alone
  can't distinguish that from a later, different set of uncommitted edits made over the same
  commit — nor does it (or `git stash create`) see untracked, never-`git add`ed files.
  Before invoking `gh pr create` for a change, run
  `/address-pr-issues`' own Step 2.5 checklist against it (Complexity Indicators + Decision
  Rules — don't hand-copy a subset here; the two lists have drifted before and cite-by-name
  avoids that). Run this skill proactively whenever Step 2.5's own **MUST spawn** rule fires (2+
  complexity indicators checked, OR cannot enumerate 3+ specific edge cases, OR not confident
  Copilot finds zero issues) — a change complex enough to warrant it doesn't stop being complex
  just because nobody named it. Skip only when Step 2.5's own **MAY skip** rule is fully
  satisfied (0-1 indicators AND 3+ edge cases enumerable AND confident AND the change is pure
  style/config/docs/rename) — keep this narrow so routine, low-complexity changes don't trigger it.

❌ **AFTER creating PR** (reactive):
- Use `/address-pr-issues` instead
- That skill handles existing Copilot comments and SonarQube issues
- Different workflows for different stages

## Workflow Overview

1. **Determine base branch** (auto-detect or ask)
2. **Identify changed files** (git diff against base branch)
3. **Load project patterns** (from CLAUDE.md if present)
4. **Adversarial pattern review** (MANDATORY — invokes /adversarial-review to a terminal outcome,
   parallel per-class agents — runs BEFORE the batch below, never concurrently; see Step 4)
5. **Run pattern-based, consistency, Maven, spec-completeness, and coherence-walk checks** (parallel `Workflow` batch, once adversarial-review is done touching the tree)
6. **Report findings** with severity and recommendations, offer to fix
7. **Validate fixes** (tests + optional SonarQube)
8. **Final summary**, record the audited tree + outcome marker

## Step 1: Determine Base Branch

Ask the user which branch to compare against, or auto-detect — same resolution
`adversarial-review`'s own Setup Step 3 uses, so both halves of this audit agree on scope. **If the
user names a branch, set `BASE_BRANCH_ARG` to that value before running this step; leave it unset
otherwise** — the block below checks for it and uses it directly, skipping auto-detection
entirely, mirroring `adversarial-review`'s own override handling exactly (auto-detect is the
fallback for when no override was given, not a check that runs regardless of one):

```bash
if [ -n "$BASE_BRANCH_ARG" ]; then
  BASE_BRANCH="$BASE_BRANCH_ARG"
  BASE_SOURCE="arg"
else
  # NOT `@{u}` (the current branch's OWN upstream) — once this branch is pushed with -u, that
  # resolves to the branch itself, making BASE_BRANCH == CURRENT_BRANCH and every diff empty.
  BASE_BRANCH=$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null)
  BASE_SOURCE="gh-pr"
  if [ -z "$BASE_BRANCH" ]; then
    BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's#.*/##')
    BASE_SOURCE="origin-head"
  fi

  # Fallback to common names — remote-tracking refs, not local refs/heads/*: every downstream diff
  # uses an origin/-prefixed range, and a shallow clone, a worktree checked out to only the feature
  # branch, or a CI runner can have origin/main or origin/master without a local main/master branch.
  if [ -z "$BASE_BRANCH" ]; then
    if git show-ref --verify --quiet refs/remotes/origin/main; then
      BASE_BRANCH="main"
    elif git show-ref --verify --quiet refs/remotes/origin/master; then
      BASE_BRANCH="master"
    else
      echo "Cannot detect base branch — tell me which branch to compare against" >&2
      exit 1
    fi
    BASE_SOURCE="origin-fallback"
  fi
fi
echo "BASE_BRANCH=$BASE_BRANCH (resolved via $BASE_SOURCE)"

# A resolved name is not the same as one that actually exists on origin — fail loudly here instead
# of letting a later git command's fatal error get silently swallowed downstream.
if ! git rev-parse --verify --quiet "origin/$BASE_BRANCH^{commit}" >/dev/null; then
  # NOT a bare `git fetch origin $BASE_BRANCH` — verified that in a restricted-refspec clone
  # (shallow, --single-branch, a CI runner checked out to only the feature branch) the bare form
  # fetches into FETCH_HEAD only and does NOT create refs/remotes/origin/$BASE_BRANCH.
  echo "🛑 origin/$BASE_BRANCH does not exist locally (resolved via $BASE_SOURCE) — never fetched? remote not named 'origin'? base branch renamed? Run 'git fetch origin $BASE_BRANCH:refs/remotes/origin/$BASE_BRANCH' (the explicit-refspec form — a bare 'git fetch origin $BASE_BRANCH' does not create the remote-tracking ref in a restricted-refspec clone) or supply the correct branch." >&2
  exit 1
fi

# Persist AFTER validation, not before — a persisted-but-invalid value would let Step 2's read-back
# proceed with something already proven broken. Both fields (BASE_BRANCH and BASE_SOURCE): Step 8's
# error messages need to say which resolution path produced the value, the same way this step's do.
# Persist immediately — Step 8 reads this back several fenced blocks later, and shell variables do
# NOT survive across this document's separate bash invocations (same reason Step 4.7's
# ADVERSARIAL_OUTCOME/TESTS_GREEN are persisted to disk rather than trusted as shell state).
printf '%s %s\n' "$BASE_BRANCH" "$BASE_SOURCE" > "$(git rev-parse --git-dir)/pre-pr-audit-base-branch"
```

## Step 2: Get Changed Files

Diff against the merge-base with `origin/$BASE_BRANCH`, not a three-dot commit range — this skill
audits work that is often still uncommitted ("After implementing a feature but before
committing"), and a three-dot range (`origin/$BASE_BRANCH...HEAD`) diffs commit-to-commit, so it
can never see uncommitted changes. `/adversarial-review`'s own Setup Step 3/4 (invoked at Step 4.7
below) resolves and pins the same kind of value as `$MERGE_BASE`, so both halves of this audit
agree on scope:

```bash
# Re-derive if this is a new shell/session — $BASE_BRANCH/$BASE_SOURCE don't persist from Step 1's
# invocation any more than $ADVERSARIAL_OUTCOME/$TESTS_GREEN do across their own separate blocks.
if [ -z "$BASE_BRANCH" ]; then
  BASE_BRANCH_FILE="$(git rev-parse --git-dir)/pre-pr-audit-base-branch"
  if [ ! -f "$BASE_BRANCH_FILE" ]; then
    echo "🛑 \$BASE_BRANCH is unset and $BASE_BRANCH_FILE not found — re-run Step 1 before this step." >&2
    exit 1
  fi
  read -r BASE_BRANCH BASE_SOURCE < "$BASE_BRANCH_FILE"
fi
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BASE_BRANCH" = "$CURRENT_BRANCH" ]; then
  echo "🛑 BASE_BRANCH and CURRENT_BRANCH are both '$BASE_BRANCH' (resolved via $BASE_SOURCE) — refusing to audit an empty diff. Supply the correct branch above." >&2
  exit 1
fi
MB_ERR=$(git merge-base "origin/$BASE_BRANCH" HEAD 2>&1); MB_RC=$?
if [ "$MB_RC" -eq 1 ]; then
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD found no common ancestor (shallow clone? unrelated histories? run 'git fetch --unshallow origin $BASE_BRANCH') — no diff range can be computed." >&2
  exit 1
elif [ "$MB_RC" -ne 0 ]; then
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD failed (exit $MB_RC): $MB_ERR" >&2
  exit 1
fi
MERGE_BASE="$MB_ERR"
if [ -z "$MERGE_BASE" ]; then
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD returned nothing — no diff range can be computed." >&2
  exit 1
fi
DIFF_RC=0
git diff --quiet "$MERGE_BASE" || DIFF_RC=$?
# `git diff`/`git ls-files` only see TRACKED content — a change consisting solely of new,
# never-`git add`ed files (this skill's own "after implementing a feature but before committing"
# trigger) makes the tracked-diff exit 0 even though real content exists. Union in untracked files
# before deciding the diff is empty.
UNTRACKED_FILES=$(git ls-files --others --exclude-standard)
if [ "$DIFF_RC" -eq 0 ] && [ -z "$UNTRACKED_FILES" ]; then
  echo "🛑 diff against merge-base $MERGE_BASE is empty (no tracked changes, no untracked files) — refusing to audit nothing. Check BASE_BRANCH above." >&2
  exit 1
elif [ "$DIFF_RC" -ge 2 ]; then
  echo "🛑 git diff against merge-base $MERGE_BASE failed (exit $DIFF_RC) — this is a git error, not an empty diff. Re-run 'git diff $MERGE_BASE' directly to see the actual error." >&2
  exit 1
fi
CHANGED_FILES=$(printf '%s\n%s\n' "$(git diff --name-only "$MERGE_BASE")" "$UNTRACKED_FILES" | grep -v '^$' | sort -u)
CHANGED_JAVA_FILES=$(echo "$CHANGED_FILES" | grep "\.java$" || true)
# pattern_checker.py has a Python-specific check (subprocess safety) gated on file.endswith('.py')
# — pass it Python files too, not just Java, or that check is permanently unreachable.
CHANGED_PY_FILES=$(echo "$CHANGED_FILES" | grep "\.py$" || true)
CHANGED_TEST_FILES=$(echo "$CHANGED_JAVA_FILES" | grep -E "(^|/)src/test/" || true)
CHANGED_SPEC_FILES=$(echo "$CHANGED_FILES" | grep -E "(SKILL\.md|README\.md|CONTRIBUTING\.md|USAGE\.md|CONSTRAINTS\.md|DESIGN\.md)" || true)

# If no Java or Python files, check if there are other languages to analyze
if [ -z "$CHANGED_JAVA_FILES" ] && [ -z "$CHANGED_PY_FILES" ]; then
  echo "No Java or Python files changed. Would you like me to analyze other file types?"
  # Extend to other languages as needed
fi
```

## Step 3: Load Project-Specific Patterns

Check if CLAUDE.md exists and has a "Pre-PR Audit Patterns" section:

```bash
if [ -f "CLAUDE.md" ]; then
  # Extract project patterns (example format shown below)
  PROJECT_PATTERNS=$(sed -n '/## Pre-PR Audit Patterns/,/^## /p' CLAUDE.md)
fi
```

**Example CLAUDE.md section**:
```markdown
## Pre-PR Audit Patterns

### Resource Cleanup (Spark)
- `.persist()` without `.unpersist()` in finally
- `.broadcast()` without `.destroy()` in finally

### Domain Validation
- OLIB ID uniqueness checks
- Record count validation
```

## Step 4: Adversarial Review (Direct), Then Parallel Analysis (Workflow)

**Run Step 4.7 (Adversarial Pattern Review) to a terminal outcome FIRST, then run the Workflow
batch below — never concurrently.** `adversarial-review` documents an explicit invariant its
per-round agents rely on: "within a round the tree is frozen until Phase D" (its own Setup Step
4). The Workflow batch's own Step 6 fix patterns mutate that same working tree. If a
Workflow-batch fix lands while an adversarial-review round is in flight, that round's per-class
agents no longer see one consistent tree, and the next round's diff surfaces the Step 6 edit as
unattributed churn that `PRIOR_FINDINGS` never saw — inflating cross-file yield and blocking
convergence on noise the review didn't cause.

**Step 4.7 (Adversarial Pattern Review)**: invoke `Skill(satori:adversarial-review, ...)` directly — it
is its own top-level invocation, not an entry inside the Workflow's `parallel()` call below, and
it needs its own live, per-round human review-pause (Phase C) before applying fixes. A
`Workflow`-spawned agent runs to completion and returns a result; it cannot pause mid-execution
to show the orchestrating session's user something and wait for a real decision — only the
orchestrating session itself can host that, the same way `/address-pr-issues`' Step 3.5 invokes
`/adversarial-review` directly rather than through a spawned sub-agent. Run it to a terminal
outcome (CONVERGED, NOT converged + escalated, INCOMPLETE + accepted, ABANDONED, or Test failures
after fix application — do not start the Workflow batch on a red suite) — see Step 4.7 below for
the full invocation — before starting the Workflow batch.

**Workflow batch** (Pattern Checks, Consistency Checks, Maven Plugin Checks, Spec-Completeness
Review, Whole-Document Coherence Walk): once adversarial-review is done touching the tree,
**re-derive `CHANGED_FILES`/`CHANGED_JAVA_FILES`/`CHANGED_TEST_FILES`/`CHANGED_SPEC_FILES` by
re-running Step 2's block** — Phase D may have applied fixes that add/remove files or shift line
numbers, so this batch's inputs must post-date those edits, not the pre-Step-4.7 snapshot. Then
use the `Workflow` tool (Claude Code's multi-agent orchestration primitive) to spawn these agents
simultaneously. Pass each agent the git diff output, changed file contents, and project patterns
from CLAUDE.md — **except** the Whole-Document Coherence Walk agent (Step 4.9), which must NOT
receive the diff or any indication of which sections changed; see that step's Agent mandate below
for why:

- **Pattern Checks** — checks described in Step 4 details below; read `pattern_checker.py`'s
  stderr output before trusting its findings — see that step's note on the scan-scope line
- **Consistency Checks** — checks described in Step 4.5 details below
- **Maven Plugin Checks** (skip if no `@Mojo` annotation or `maven-plugin` packaging detected) — checks in Step 4.6 below
- **Spec-Completeness Review** (skip if `CHANGED_SPEC_FILES` is empty) — checks described in Step 4.8 below; returns findings for review-pause in Step 5
- **Whole-Document Coherence Walk** (skip if `CHANGED_SPEC_FILES` is empty) — checks described in Step 4.9 below; single pass, non-repeating; returns findings for review-pause in Step 5

Most agents in this batch return findings in this shape:
```json
[{"severity": "CRITICAL|HIGH|MEDIUM|LOW", "file": "path:line", "description": "...", "recommendation": "..."}]
```
**Step 4.8 and Step 4.9 don't match this shape** — Step 4.8 returns `location` (not `file`) plus
an extra `check` field; Step 4.9 returns `location`/`changed_section`/`affected_section` with no
`recommendation` at all (see their own Output Format sections below). Merge all findings by
severity, then present them interactively (Step 5, which branches its template per finding source
rather than assuming every finding has `file`/`recommendation`), and apply Step 5/6 fixes for the
Workflow-batch's own findings.

The detailed check instructions for each agent follow below.

---

## Step 4 Details: Pattern-Based Checks

Use the bundled pattern checker script:

```bash
python3 ~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/pre-pr-audit/scripts/pattern_checker.py \
  --changed-files "$(printf '%s\n%s\n' "$CHANGED_JAVA_FILES" "$CHANGED_PY_FILES" | grep -v '^$')" \
  --merge-base "$MERGE_BASE" \
  --project-patterns "$PROJECT_PATTERNS"
```

**Check the script's stderr output before trusting an empty/clean result** — it prints a
"Scanned X/Y requested file(s)" line unconditionally, plus any per-file warnings (unreadable,
diff-failed). An empty findings list where `X < Y` means files were silently skipped, not
verified clean; the agent running this check (in the Workflow batch below) must read stderr, not
just the JSON result, before reporting "no issues found."

The script checks for:

### Universal Patterns (All Projects)

**Resource Lifecycle**:
- Spark `.persist()` without `.unpersist()`, `.broadcast()` without `.destroy()` (both gated on a
  `finally`-block check in the same method)
- `FileInputStream`/`FileOutputStream`/`BufferedReader`/`Files.newBufferedReader` opened without
  try-with-resources — the only four constructors checked; other stream/connection/lock types
  (sockets, JDBC connections, explicit `Lock.lock()`/`unlock()`) are NOT covered by this script

**Fail-Fast vs Silent Failures**:
- `LOGGER.warn()` or `LOGGER.error()` with keywords: duplicate, invalid, corrupt, conflict, mismatch
- Exception caught but not re-thrown, just logged
- Returning null instead of throwing on error conditions

**Edge Case Coverage**:
- Map operations (`.get()`, `.put()`, `Collectors.toMap()`) without handling missing keys or duplicates
- Collection operations without null/empty checks
- Parse operations (`parseInt`, `parse`, `valueOf`) without try-catch
- Array access without bounds checking

**NOT implemented by the script** (do these by hand / delegate to the Consistency-Checks agent —
`pattern_checker.py` has no `isinstance`/dict-default analysis):
- Python `dict.get(key, non_None_value)` where the key may be present with value `None` in externally-sourced dicts (JSON, API responses, subprocess output) — `dict.get` only uses the default for absent keys; flag and recommend `d.get(key) or default` instead (Python files only)
- Value extracted from a dict or parsed JSON immediately used in a type-dependent operation (iterated, sliced, `len()`, indexed, arithmetic) without a preceding `isinstance()` / `typeof` guard — applies to values from external sources where the schema is not compiler-enforced

**Implemented by the script but not covered above**:
- `.toString().equals()` on a receiver whose declared type is an interface/abstract class with known subclasses (fragile on polymorphic types)
- `.toString().startsWith()`/`.endsWith()` used as a type discriminator (same fragility, string-shape form)
- `catch` on a specific `*Exception`/`*Error` subtype immediately around a JDK/library call, when the API only documents a broader contract (may miss a sibling exception type)
- Python `subprocess.run`/`Popen` calls missing `cwd=`, `timeout=`, a `TimeoutExpired` handler, or an executable guard
- The same numeric constant appearing across changed files to control truncation/padding/formatting (the constant-level half of Consistency Check #4's "Parallel Derivation Anti-Pattern", below — the agent only needs to cover the string-manipulation and lookup-key halves, since the script already automates this one)
- `list.add()` inside a loop with no `Set`/`contains()` check guarding against duplicates

**Try/Finally Scope**:
- Operations between resource acquisition and try block
- Exception-throwing code outside try but before finally

**Test Coverage**:
- New classes in `src/main` without corresponding test in `src/test`
- Modified main classes where test class wasn't modified

### Project-Specific Patterns (From CLAUDE.md)

Apply any patterns loaded from the project configuration.

### Silent Failure Patterns

**NOT implemented by the script** — same as the isinstance/dict-default bullets above, these three
sub-categories (Parse/Compile Failures, Type/Name Resolution, Platform Compatibility) are not
automated by `pattern_checker.py`; check them by hand or delegate to the Consistency-Checks agent.
Check for operations that can fail without clear user-visible errors:

**Parse/Compile Failures**:
- Methods that catch exceptions and return null/empty
- Error logging without exception propagation
- Success flags set before operations complete
- Diagnostic collectors that are never inspected

**Type/Name Resolution**:
- Type resolution falling back to simple names without validation
- Name matching without disambiguation (HashMap iteration order)
- Import resolution without wildcard handling

**Platform Compatibility**:
- Path separators (forward slash vs backslash)
- File.separator not used where needed
- Hardcoded path assumptions

**Example issues found in PR #8:**
- IOException caught → return null → treated as success (Issue #37)
- Flag set before scan → all failures still "successful" (Issue #27)
- DiagnosticCollector created but never read (Issue #38)

## Step 4.5: Internal Consistency Checks (NEW)

After pattern-based checks complete, scan for inconsistencies **within the PR itself**:

### Consistency Check #1: Pattern Uniformity

For each pattern type, verify uniform application across changed files:

**Debug Logging Consistency**:
```bash
# Find all debug logging calls
grep -n "debug\|DEBUG" $CHANGED_FILES | tee /tmp/debug_patterns.txt

# Check for mixed patterns:
# - if (debug) getLog().info("[DEBUG] ...")  (plugin parameter)
# - getLog().debug(...)  (Maven -X only)
# - System.out.println for debug (wrong)
```

**Report if mixed**:
```markdown
⚠️ **Inconsistent Debug Logging** (MEDIUM)

Files use different debug logging approaches:
- `AnalyzeMojo.java:181` uses `if (debug) getLog().info("[DEBUG] ...")`  
- `AnalyzeMojo.java:221` uses `getLog().debug(...)`

**Why This Matters**: Users expect `-Ddebug=true` to work uniformly. Mixed patterns confuse users.

**Recommendation**: Standardize on one approach (prefer plugin parameter for user control).
```

**Scope/Parameter Normalization**:
```bash
# Check if scope/parameter handling is consistent
grep -n "scope\|parameter" $CHANGED_FILES | grep -E "(toLowerCase|trim|normalize)" > /tmp/param_patterns.txt

# Look for methods that:
# - Some normalize (trim, toLowerCase), others don't
# - Some validate early, others validate late
```

**Error Handling Consistency**:
```bash
# Find error handling patterns
grep -n "throw\|catch\|Exception\|IllegalArgumentException" $CHANGED_FILES > /tmp/error_patterns.txt

# Check for:
# - Some methods throw, others return null
# - Some log-and-throw, others just log
# - Inconsistent exception types for similar errors
```

### Consistency Check #2: Test Fixture Completeness

**Scan test helper methods**:
```bash
# Find test helper/factory methods
grep -n "create.*\|build.*\|make.*" $CHANGED_TEST_FILES | grep "private\|public" > /tmp/test_helpers.txt

# For each helper:
# 1. Extract what fields it populates
# 2. Find production code that reads from that object type
# 3. Report fields used in production but not set in tests
```

**Example Issue**:
```markdown
⚠️ **Incomplete Test Fixture** (HIGH)

`ConversionInventoryWriterTest.createLogCall()` creates `LogCall` objects but doesn't set:
- `absolutePath` (used in `ConversionInventoryWriter.hasValidSourceLocation()`)

Tests will pass but don't exercise production filtering logic.

**Recommendation**: Add `call.setAbsolutePath("/path/to/File.java")` to test helper.
```

### Consistency Check #3: Documentation Synchronization

**Check README vs Implementation**:
```bash
# Find documentation files
DOC_FILES=$(echo "$CHANGED_FILES" | grep -E "README|USAGE|GUIDE|\.md$")

# For each doc file, extract claims about behavior:
# - "generates X output"
# - "supports Y patterns"  
# - "defaults to Z"

# Cross-reference with code changes:
# - Does implementation still match claims?
# - Are examples still accurate?
```

**Example Issue**:
```markdown
⚠️ **Documentation Drift** (MEDIUM)

`README.md` line 51 says:
> conversion-inventory.json contains **traditional pattern only**

But `ConversionInventoryWriter.java` includes 4 patterns:
- TRADITIONAL, LOMBOK, LOGSTASH_MARKER_ONLY, FLUENT_WITH_MARKERS

**Recommendation**: Update README to reflect current behavior.
```

**Javadoc Accuracy**:
```bash
# Extract javadoc claims from changed files
grep -B 5 "public.*method\|class\|enum" $CHANGED_FILES | grep "/\*\*" -A 3 > /tmp/javadocs.txt

# Check for:
# - Javadoc says "returns X" but code returns Y
# - Parameter descriptions don't match actual validation
# - @deprecated but still used
```

### Consistency Check #4: Centralization Opportunities

**Detect Duplicated Logic**:
```bash
# Find similar code blocks (simple heuristic)
for file in $CHANGED_FILES; do
  # Extract method bodies
  csplit -f /tmp/method_ -b "%03d.java" $file '/public\|private\|protected/' '{*}' 2>/dev/null
  
  # Hash each method body
  for method in /tmp/method_*.java; do
    md5sum $method >> /tmp/method_hashes.txt
  done
done

# Find duplicate/similar hashes
sort /tmp/method_hashes.txt | uniq -c | awk '$1 > 1 { print }'
```

**Complex Conditions**:
```bash
# Find complex boolean expressions
grep -n "&&.*&&\|if.*||.*||" $CHANGED_FILES > /tmp/complex_conditions.txt

# Suggest extraction for readability
```

**Example Issue**:
```markdown
⚠️ **Centralization Opportunity** (LOW)

`ConversionInventoryWriter.java:32` has hard-coded pattern check:
```java
call.getPattern() == LogPattern.TRADITIONAL ||
call.getPattern() == LogPattern.LOMBOK ||
call.getPattern() == LogPattern.LOGSTASH_MARKER_ONLY ||
call.getPattern() == LogPattern.FLUENT_WITH_MARKERS
```

This logic should live in `LogPattern.isConvertible()` method.

**Recommendation**: Extract to enum method for reusability and single source of truth.
```

**Parallel Derivation Anti-Pattern** (highest-value check):
When the same conceptual value (truncated string, formatted key, computed hash, normalized name) is derived from the same input in two or more classes with no shared constant or shared method, the algorithms can silently diverge. Look specifically for:
- The same numeric constant (e.g., `60`, `80`, `MAX_LENGTH`) appearing in multiple files to control truncation, padding, or formatting — **already automated by `pattern_checker.py`** (Step 4 details above); this agent only needs to cover the two bullets below, which the script doesn't check
- The same string manipulation (prefix stripping, suffix appending, case normalization) repeated across classes
- Equality guards or lookup keys built from derived values where the derivation logic lives in each consumer independently

**Report if found**:
> ⚠️ **Parallel Derivation** (HIGH)
>
> The value `X` is derived from input `Y` in both `ClassA` and `ClassB` with no shared constant or method. If the two algorithms ever differ (different truncation lengths, different separator chars, different edge-case handling), equality checks between them will silently fail.
>
> **Recommendation**: Extract derivation to a shared constant + shared method so both classes are guaranteed to agree.

### Consistency Check #5: Edge Case Coverage

For each key operation in changed files, verify edge case handling:

```bash
# Find operations that commonly have edge cases
grep -n "\.get(\|\.put(\|\.parse(\|\.split(\|\.substring(\|\.charAt(\|new File(" $CHANGED_FILES > /tmp/edge_case_ops.txt

# For each operation, check nearby code for:
# - Null checks
# - Empty checks  
# - Bounds validation
# - Error handling
```

**Specific Patterns to Check**:

**Map Operations**:
```java
// Look for .get() without null check
map.get(key)  // ❌ Missing: if (value == null) handle it

// Look for Collectors.toMap() without merge function  
.collect(Collectors.toMap(k, v))  // ❌ Missing duplicate key handling
```

**String Operations**:
```java
// Look for parse operations without try-catch
Integer.parseInt(str)  // ❌ Missing NumberFormatException handling
path.substring(5)      // ❌ Missing bounds check
```

**File Operations**:
```java
// Look for File operations without validation
new File(path)        // ❌ Missing: exists() and isDirectory() checks
```

**Collection Operations**:
```java
// Look for collection access without size check
list.get(0)           // ❌ Missing: empty list check
array[index]          // ❌ Missing: bounds check
```

**Example Issue**:
```markdown
⚠️ **Missing Edge Case Validation** (HIGH)

`AnalyzeMojo.java:178` creates File without checking if it's a directory:
```java
File sourceDir = new File(sourceRoot);
if (!sourceDir.exists()) {
    continue;
}
scanner.scan(sourceDir, ...);  // ❌ What if it's a file, not directory?
```

**Recommendation**: Add `sourceDir.isDirectory()` check before scanning.
```

### Consistency Check #6: Related Code Review

When finding an issue pattern, expand search to related areas:

```bash
# If you find issue in method X, check:
# 1. Other methods in same class
# 2. Overridden methods in subclasses
# 3. Similar named methods in other classes

# Example: Found debug logging issue in detectJavaVersion()
grep -n "debug\|DEBUG" $CHANGED_FILES | grep -v "detectJavaVersion"  # Find other debug calls
```

**Example Issue**:
```markdown
⚠️ **Related Code Pattern** (MEDIUM)

Fixed debug logging in `detectJavaVersion()` (lines 221, 230) but found same issue in:
- `analyzeModule()` line 88
- `buildClasspath()` line 295

All should use consistent debug pattern.

**Recommendation**: Apply same fix to related methods.
```

### Consistency Check #7: Partial-Success Audit Write Guard

When a function uses a boolean flag to track partial failures (`had_failures`, `errors`,
`failed_count`, `partial`, or similar), any write of a timestamp, audit record, approval
marker, or status field must be guarded by `not had_failures` (or equivalent). Flag
unconditional writes of such fields in functions that have a failure-tracking variable.

**Report if found**:
> ⚠️ **Unguarded Audit Write on Partial Failure** (HIGH)
>
> `had_failures` is set to `True` in some paths, but `<field>` is written unconditionally
> afterward. If any repo/item fails, the audit record will claim full success.
>
> **Recommendation**: Guard the audit write behind `if not had_failures:` (or equivalent).

### Consistency Check #8: Nullable Field Normalization Consistency

When a field is read from a shared data structure (dict, record, JSON object), identify
whether some read sites apply a normalization expression (`x or default`,
`x if x is not None else default`, `x ?? default`). If ≥2 read sites apply it, flag
read sites that don't — they will produce different behavior on null inputs.

**Report if found**:
> ⚠️ **Inconsistent Null Normalization** (MEDIUM)
>
> Field `<name>` is normalized with `or <default>` in N places but read raw in M others.
> Raw reads will expose `None`/`null` to consumers that expect a concrete value.
>
> **Recommendation**: Apply the same normalization at every read site, or normalize once
> at the write/load boundary.

### Consistency Check #9: Factory/Blank-Record Completeness

For functions whose role is to produce a default/empty instance of a data structure
(heuristic: name matches `_empty_*`, `create_*`, `make_*`, `_default_*`, or a builder
pattern), cross-reference the fields they initialize against:
(a) all fields read from that structure type elsewhere in the same file, and
(b) any schema documentation in docstrings or comments.

Flag fields that appear in (a) or (b) but are absent from the factory.

**Report if found**:
> ⚠️ **Factory Missing Documented Field** (MEDIUM)
>
> `<factory_function>` does not initialize `<field>`, but it is read in `<location>` and/or
> listed in the schema documentation. Consumers that rely on the field being present
> (even as `None`) will behave inconsistently compared to deserialized instances.
>
> **Recommendation**: Add `"<field>": None` (or equivalent zero value) to the factory.

### Summary Table

| Check Type | What It Catches | Severity | Example from PR #6 |
|------------|----------------|----------|-------------------|
| Pattern Uniformity | Mixed approaches for same operation | MEDIUM | Debug logging (Rounds 10, 12) |
| Test Fixture Completeness | Test helpers missing production-used fields | HIGH | absolutePath missing (Round 13) |
| Documentation Sync | README/Javadoc drift from code | MEDIUM | conversion-inventory description (Round 9) |
| Centralization | Duplicated/scattered logic | LOW | Pattern filtering (Round 10) |
| Edge Case Coverage | Missing null/empty/bounds checks | HIGH | isDirectory check (Round 10) |
| Related Code Review | Same issue in multiple places | MEDIUM | Debug logging across methods (Round 12) |
| Partial-success audit write | Audit markers written on partial failure | HIGH | Pattern 3 |
| Nullable normalization consistency | Mixed null-guard on same field | MEDIUM | Pattern 6 |
| Factory completeness | Blank-record factory missing schema fields | MEDIUM | Pattern 4 |

**Estimated Impact**: Catch 60-85% of issues before PR creation (8-11 rounds saved from our 13-round example).

## Step 4.6: Maven Plugin-Specific Checks (Conditional)

**Trigger**: Only run if changed files include Maven plugin code (detected by `@Mojo` annotation or `pom.xml` with `maven-plugin` packaging)

### Maven Plugin Checklist

**1. Parameter CLI Binding**:
```bash
# Find @Parameter annotations without property attribute
grep -B 2 "@Parameter" $CHANGED_FILES | grep -v "property =" > /tmp/params_no_property.txt

# Report each one
```

**Example Issue**:
```markdown
⚠️ **Maven Plugin: Missing CLI Binding** (HIGH)

`AnalyzeMojo.java:52`:
```java
@Parameter(defaultValue = ".claude/analyze-reports")
private File outputDirectory;  // ❌ No property attribute
```

Without `property = "outputDirectory"`, users cannot set via `-DoutputDirectory=...`

**Recommendation**: Add `property = "outputDirectory"` to @Parameter annotation.
```

**2. Resolution Scope vs Classpath Usage**:
```bash
# Check if @Mojo resolution scope matches classpath methods called
grep "@Mojo" $CHANGED_FILES -A 5 | grep "requiresDependencyResolution" > /tmp/resolution_scope.txt
grep "getCompileClasspathElements\|getTestClasspathElements" $CHANGED_FILES > /tmp/classpath_calls.txt

# If resolution scope is TEST but only using compile classpath → warn about overhead
# If resolution scope is COMPILE but calling getTestClasspathElements → warn about mismatch
```

**3. Maven API Usage**:
```bash
# Check if code constructs paths manually instead of using Maven API
grep "src/main/java\|src/test/java" $CHANGED_FILES > /tmp/hardcoded_paths.txt

# Recommend: project.getCompileSourceRoots() instead of manual construction
```

**Example Issue**:
```markdown
⚠️ **Maven Plugin: Hardcoded Source Paths** (MEDIUM)

`AnalyzeMojo.java:160` constructs source path manually:
```java
String sourcePath = project.getBasedir() + "/src/main/java";  // ❌ Fragile
```

**Recommendation**: Use Maven API:
```java
List<String> sourceRoots = project.getCompileSourceRoots();
```
```

**4. Aggregator vs Per-Module Logic**:
```bash
# If @Mojo has aggregator=true, check if code iterates reactor projects
grep "@Mojo.*aggregator.*true" $CHANGED_FILES > /tmp/aggregators.txt

# For each aggregator mojo, verify it uses reactorProjects, not just current project
```

**5. Debug Logging Convention**:
```bash
# Check if plugin has debug parameter
grep "@Parameter.*debug" $CHANGED_FILES > /tmp/debug_param.txt

# If yes, check all debug logging respects it (not just Maven -X)
grep "getLog().debug(" $CHANGED_FILES > /tmp/maven_debug_calls.txt

# Recommend: if (debug) getLog().info("[DEBUG] ...") instead of getLog().debug(...)
```

### Maven Plugin Summary

```markdown
## Maven Plugin Checks: {PASS|WARNINGS}

- [ ] CLI parameter binding (property attributes)
- [ ] Resolution scope matches usage
- [ ] Uses Maven API (not manual paths)
- [ ] Aggregator logic correct
- [ ] Debug logging convention

Found N Maven-specific issues (see above for details).
```

## Step 4.7: Adversarial Pattern Review (MANDATORY)

**This is the core value of pre-pr-audit** — a parallel, multi-round sweep across all known Copilot issue pattern classes, with human review-pause between rounds and git-guardrailed fixes.

### Before invoking, construct an Intent Brief (~200 words)

The Intent Brief is the single most important input to the adversarial review. It tells the review and fix agents what you intended — so they can distinguish "correct design decision" from "bug to fix." Compose it from this session's context:

```
Intent Brief:
- Problem being solved: <what this PR does and why>
- Key design decisions: <choices made and the trade-offs accepted>
- What was deferred: <known gaps intentionally left for a future PR>
- Any accepted risks: <known edge cases deliberately not handled here>
```

### Invoke the peer skill

```
Skill(satori:adversarial-review, args="--rounds 3 --base-branch <BASE_BRANCH> --intent-brief \"<intent-brief text>\"")
```

Run it to a terminal outcome, then immediately capture that outcome and **persist it to disk** —
Step 8's marker reads it back, and shell variables do NOT survive across this document's separate
fenced-block invocations (the same warning applies here as at Step 7's SonarQube section: "shell
state doesn't persist across separate command invocations"). Steps 4.8, 4.9, 5 (an interactive
review-pause), 6, and 7 (its own Sonar block, which can itself `exit 1`) all run between this point
and Step 8's read. The skill's own Summary Output badge (e.g. "✅ CONVERGED — cross-file yield
0...") is a human-readable line, not itself a token to compare against — derive the bare value
from it explicitly, including the combined badge (adversarial-review always runs with `--rounds 3`
here, so its "INCOMPLETE + NOT converged" combined outcome is reachable):

```bash
ADVERSARIAL_OUTCOME=<bare token derived from the skill's Outcome badge: CONVERGED|NOT_CONVERGED|INCOMPLETE|INCOMPLETE_NOT_CONVERGED|ABANDONED|TEST_FAILURES>
TESTS_GREEN=<true unless the skill's own Phase D test run reported "Test failures after fix application", in which case false>
printf '%s %s\n' "$ADVERSARIAL_OUTCOME" "$TESTS_GREEN" > "$(git rev-parse --git-dir)/pre-pr-audit-adversarial-outcome" || {
  echo "🛑 Failed to write the outcome marker — Step 8 will not be able to read it back." >&2
  exit 1
}
```

Only `CONVERGED` maps to a potentially-clean run at Step 8 — every other token (including the
combined one) maps to `NOT_CLEAN`, so the addition of `INCOMPLETE_NOT_CONVERGED` above is for
operator clarity, not a behavior change.

The `/adversarial-review` skill handles the full protocol:
- One review agent per pattern class (parallel, dynamic enumeration from the pattern file)
- Cascade sweep within each class (every callsite, not just changed lines)
- Synthesizer deduplication keyed on the `file` string (`path:line` or `path:startLine-endLine`) across classes — colliding recommendations are concatenated with "| ALSO:", not reduced to "the more specific one"
- Per-round review-pause happens live inside the skill (its own Phase C) — findings are not
  returned to Step 5 below, which covers Workflow-batch findings only (see Step 4/5 above)
- Git-guardrailed fix agents (PROHIBITED: git reset/rebase/commit/stash/checkout -- <file>/restore)
- Up to 3 rounds, terminating when a round yields zero new cross-file findings (local findings are reported for disposition but do not block convergence)
- Escalation at the round cap: if cross-file findings are still surfacing after round 3, the skill recommends a targeted deep-dive agent scoped to the recurring theme (or surfaces the theme to you for a judgment call)
- If a class's review agent never returns a result even after retries, `/adversarial-review` logs
  it visibly (`N class(es) returned no result and are excluded from this round: ...`) and that
  lens gets a natural retry next round while rounds remain — this is visible in the round's
  output, not silent, though no disposition is solicited from you yet. Only once round 3 (the
  cap) is reached without every class returning a result does the skill signal a distinct
  "INCOMPLETE" outcome instead of a clean pass, asking you to retry it, accept the gap, or abandon
  the round. INCOMPLETE and the NOT-converged escalation above are evaluated independently and can
  both fire at the cap — see /adversarial-review's Summary Output for the combined "INCOMPLETE +
  NOT converged" badge covering that case

The skill returns a summary containing: per-round breakdown, findings by class split by blast radius (cross-file vs. local), a known-limitations list (accepted-risk items plus `coverage_gap` entries) for the PR description, a separate fix-provenance-notes list ("planning skipped" findings — these were fixed, so they are NOT known limitations, just a lower-confidence-fix flag for the human disposing the round), a residual-risk statement (never a "clean" claim — a zero-yield round is one sample, not proof), and any escalation or incomplete-review recommendation.

## Step 4.8: Spec-Completeness Review (Conditional: procedural spec/doc files in diff)

**Trigger**: Only run if `CHANGED_SPEC_FILES` is non-empty (SKILL.md, README.md,
CONTRIBUTING.md, USAGE.md, CONSTRAINTS.md, or DESIGN.md changed — same trigger as Step 4.9,
since both target procedural/spec documents, not just Claude Code skill files).

This step runs the **heuristic checks of the Operator Spec Completeness pattern class** (named,
not numbered — `adversarial-review`'s own rule is to reference classes by name only, since
numbers drift as classes are added/reordered in `copilot-review-patterns.md`) — the five *known*
failure modes (scope sweep, rename cascade, operator executability, branch completeness, term
definition) that Copilot finds one at a time across many rounds. Running them proactively in one
pass eliminates those rounds. These five checks treat the changed documents as *operator
specifications* — executable, complete, and internally consistent. This applies to any procedural
document (a runbook, a migration guide, an onboarding doc, a SKILL.md), not just Claude Code
skills.

**Complementary lens handled elsewhere — do NOT duplicate here**: the holistic operator
walkthrough (the **Spec Operator Walkthrough** pattern class) is the judgment-based complement to
these heuristics — a reviewer reads the changed spec linearly as a first-time operator and flags
where they would get stuck, with *no* foreknowledge of the five failure modes above. It runs
**automatically as a parallel class agent inside `/adversarial-review` (Step 4.7)** — no separate
invocation is needed in Step 4.8. This separation is deliberate: priming one agent with Operator
Spec Completeness's failure-mode list would contaminate the fresh-eyes walk (it would hunt for
those five patterns instead of reading naively), and adversarial-review's per-class parallel
agents never see each other's findings, which preserves the walk's independence. Overlap between
Operator Spec Completeness findings (here) and Spec Operator Walkthrough findings (Step 4.7) is
expected; the adversarial-review synthesizer deduplicates by the `file` string.

Spawn a review agent with the full content of each changed spec/doc file and these five Operator
Spec Completeness checks:

### Check 1: Scope-Broadening Sweep

If the PR description or diff indicates a scope change (e.g., "now handles X in addition to Y"),
grep the document for the old scope terms. For each hit, ask: does this text still accurately
describe the new scope, or does it need updating to include the new scope?

Report every hit where the language is now too narrow. Apply in one pass.

### Check 2: Rename Cascade

If a phase, pass, or term was renamed anywhere in the diff, grep the full document for the old
name. Verify every hit was updated. Check: step headers, mid-step instructions, skip conditions,
idempotency notes, routing conditions, and report section labels.

Report every occurrence of the old name that was not updated.

### Check 3: Operator Executability

For every step that instructs the operator to "evaluate each X" or "review all Y":
- Is there a `jq`, `grep`, or shell command that enumerates X/Y? If not, report the gap.
- Is every file reference a fully-qualified path (with directory prefix)? If any file is
  referenced by basename only, report it.

### Check 4: Branch Completeness

For every conditional or decision point in the spec ("if candidates found… / if not…"):
- Does the "no candidates found" branch have a documented action (proceed to Step N, skip, etc.)?
- For steps that apply to multiple action types, does the spec explicitly scope which types
  are included and which are excluded?
- For routing conditions that combine multiple signals (e.g., "X=0 AND Y non-empty"), are
  all combinations documented?

Report every decision point with a missing branch.

### Check 5: Term Definition at First Use

Find every variable or value name used as a routing signal in later steps (e.g., "M from Step 3",
"semantic review list", "needsLlmReview"). Trace each back to where it is first computed.
Verify:
- The computation step labels the value with the same name used later.
- When a later step uses a different name for the same value (e.g., a jq field name vs. a
  step-local variable name), the spec explicitly ties them together.

Report every routing reference that is not anchored to a definition earlier in the spec.

### Output Format

Return findings as:
```json
[{
  "check": "scope_sweep|rename_cascade|operator_executability|branch_completeness|term_definition",
  "severity": "HIGH|MEDIUM",
  "location": "Step N, line description",
  "description": "what is missing or stale",
  "recommendation": "specific text to add or change"
}]
```

## Step 4.9: Whole-Document Coherence Walk (Conditional: spec/doc files in diff)

**Trigger**: Run when `CHANGED_SPEC_FILES` is non-empty (SKILL.md, README.md, CONTRIBUTING.md, USAGE.md, CONSTRAINTS.md, or DESIGN.md changed).

**This step runs once, pre-PR. It does not repeat in the adversarial-review fix cycle.**

The narrow-scope Spec Operator Walkthrough agent in adversarial-review reads only the changed sections of a spec and fires on every fix round. This step is its complement: it reads the **entire document** as a first-time reader, once, before the PR opens. Its specific purpose is to catch integration breaks between changed and unchanged content — issues that only appear when the whole document is read in sequence and the changed sections must cohere with the sections around them.

### Agent mandate

Spawn a fresh-eyes agent with the full content of each changed spec file. The agent receives:
- The complete document (not just the diff)
- This mandate only: "Read this document from beginning to end as someone who has never seen it. You have no knowledge of what changed, what was intended, or what any prior version said. Flag every place the document fails to hang together as a whole — where a changed section creates confusion, contradiction, or a gap when read alongside the unchanged sections around it."

Do **not** give the agent:
- The git diff or any indication of which sections changed
- The implementation session's intent or PR description
- The Operator Spec Completeness or Spec Operator Walkthrough classes' failure-mode lists

### What to look for

The agent reads linearly and flags:

1. **Integration breaks**: a changed section introduces a term, step, or behavior that contradicts or is inconsistent with an unchanged section elsewhere in the document
2. **Orphaned references**: an unchanged section refers to something (a step, a variable, a file) that the changed section has renamed, removed, or restructured — leaving the reference dangling
3. **Scope coherence**: the document's overall scope statement (often in the intro or a "When to use" section) no longer matches what the body of the document describes after the change
4. **Narrative discontinuity**: reading the document in order, the changed section feels abrupt, assumes context the preceding sections don't provide, or leaves the reader without enough information to continue to the next section

### Output format

The agent was deliberately given no diff, so `changed_section`/`affected_section` below are its
own **best-guess** identification of which side of an inconsistency looks newer — inferred from
context (a "(NEW)" marker, more specific/current-sounding language, an orphaned reference pointing
*at* one side and not the other) — not ground truth read from a diff it never saw. Say so if it's
genuinely unclear which side changed; a correctly-identified inconsistency with an uncertain
`changed_section` guess is still a valid, actionable finding.

```json
[{
  "severity": "HIGH|MEDIUM|LOW",
  "location": "section or step description",
  "description": "what fails to cohere and why",
  "changed_section": "best guess at the section that changed (or \"unclear\" if not inferable)",
  "affected_section": "the other section involved in the inconsistency"
}]
```

## Step 5: Present Findings Interactively

This step presents findings from the **Workflow batch** in Step 4 (Pattern Checks, Consistency
Checks, Maven Plugin Checks, Spec-Completeness Review, Whole-Document Coherence Walk) — **not**
adversarial-review findings. `/adversarial-review`'s own Phase C is its own live, per-round
review-pause, presented and disposed of entirely within the `Skill(satori:adversarial-review, ...)` call
itself, using its own four-way disposition (Fix / Contradicts design / Accepted risk / False
positive) — it doesn't hand findings back here for a second presentation in this step's format.

Step 4.8/4.9 findings don't carry `file`/`recommendation` (see Step 4's schema note above) — for
those, substitute `location` for **File** and, for Step 4.9, derive a one-line **Recommendation**
from `description` rather than leaving the template field blank.

For each issue found in the Workflow batch, present:

```markdown
## Issue #1: Resource Leak (CRITICAL)

**File**: `FullExportJob.java:159`
**Pattern**: `.broadcast()` without `.destroy()`

**Code**:
```java
159: Broadcast<Map<String, Integer>> targetCountBroadcast = jsc.broadcast(olibIdToTargetCountMap);
...
(no corresponding .destroy() found in method)
```

**Why This Matters**: Broadcasts persist in Spark driver memory until explicitly destroyed. In long-lived SparkSessions, this causes memory leaks.

**Recommendation**: Add `.destroy()` in finally block at method exit.

**Fix Available**: Yes

Would you like me to:
1. Fix this issue automatically
2. Skip — this contradicts a design decision (no fix; not counted as a miss)
3. Accept as known limitation — include in PR description
4. Mark as false positive — skip with reason
5. Show me the proposed fix first
```

**Accepted-risk items MUST be recorded in this step's own summary** (Step 8's per-check findings)
and surfaced in the PR description — same principle `/adversarial-review` applies to its own
Known Limitations, applied here to Workflow-batch findings. Silently dropping them is not
acceptable — the absence of a finding in the summary is a claim that it was addressed.

Wait for user input before proceeding to the next issue.

## Step 6: Auto-Fix Issues (When Approved)

**For adversarial-review findings (Step 4.7)**: fixes are applied by the `/adversarial-review`
skill's own fix agents under strict git guardrails (PROHIBITED: git reset, rebase, commit,
stash, checkout -- <file>, restore; PERMITTED: Edit/Write, read-only bash, git diff/status). The
disposition itself happens live inside that skill's own Phase C, not here — this section covers
applying Workflow-batch findings only (Steps 4, 4.5, 4.6, 4.8, 4.9). The Intent Brief is
forwarded to every fix agent. Do not apply adversarial-review findings manually — return the
disposition to the skill so it can apply them under the correct guardrails.

**For pattern-check findings (Steps 4, 4.5, 4.6)**: apply the fix patterns below.

**Track whether any Workflow-batch fix was applied this run**: set
`WORKFLOW_BATCH_FIXES_APPLIED=true` the moment the first one lands, `false` if none are approved.
Step 8's outcome marker needs this — `AUDITED_TREE` is computed there, AFTER this step's edits, but
nothing re-runs the Workflow-batch checks against the post-fix content, so a CLEAN verdict would
otherwise certify a tree no check ever actually ran against.

When user approves a fix, apply the appropriate fix pattern:

### Fix Pattern: Add Resource Cleanup

**For `.broadcast()` without `.destroy()`**:
1. Find the method containing the broadcast
2. Check if try/finally exists at method level
3. If yes, add `.destroy()` to existing finally
4. If no, wrap method body in try/finally with destroy in finally

**For `.persist()` without `.unpersist()`**:
1. Find the method containing persist
2. Add try/finally around subsequent operations
3. Add `.unpersist()` to finally block
4. Move any operations between persist and subsequent code inside try

### Fix Pattern: Convert Silent Failure to Fail-Fast

**For warning logs with data quality issues**:
1. Extract the logged message and context
2. Replace with `throw new IllegalStateException("...")`
3. Include all context in exception message
4. If in a stream/lambda, extract to helper method that throws

### Fix Pattern: Add Edge Case Handling

**For map.get() without null check**:
1. Replace with `.getOrDefault()` if default makes sense
2. Or add null check: `if (value == null) throw new IllegalStateException(...)`
3. Or use `Optional.ofNullable(map.get(key)).orElseThrow(...)`

**For Collectors.toMap() without merge function**:
1. Add validation before collecting:
   ```java
   // Check for duplicates
   Map<K, List<V>> grouped = items.stream()
     .collect(Collectors.groupingBy(keyFunction));
   Map<K, Long> duplicates = grouped.entrySet().stream()
     .filter(e -> e.getValue().size() > 1)
     .collect(Collectors.toMap(Map.Entry::getKey, e -> (long)e.getValue().size()));
   if (!duplicates.isEmpty()) {
     throw new IllegalStateException("Duplicate keys: " + duplicates);
   }
   ```

### Fix Pattern: Add Test Coverage

**For new class without tests**:
1. Create test class with same package structure in src/test
2. Add basic test structure:
   ```java
   class FooTest {
     @Test
     void shouldHandleNormalCase() {
       // Happy path
     }
     
     @Test
     void shouldHandleEmptyInput() {
       // Edge case
     }
     
     @Test
     void shouldRejectInvalidInput() {
       // Error path
     }
   }
   ```
3. Ask user to fill in test logic (or offer to generate based on class methods)

## Step 7: SonarQube Analysis (MANDATORY - Always Present This Choice)

**NEVER skip this step silently.** After pattern checks AND the Adversarial Pattern Review (Step 4.7) complete, you MUST present the SonarQube option to the user. The agent must wait for an explicit user decision — skipping without asking is not allowed.

```markdown
Pattern checks complete. Found X issues (Y fixed, Z skipped).
Adversarial Pattern Review complete. Found N high-confidence issues across M rounds.

Would you like me to run SonarQube analysis for additional checking?
(This will take 2-3 minutes but may catch build-time issues)

Options:
1. Yes, run SonarQube now
2. No, I'll run it manually before pushing
3. Show me the command to run it myself
```

If user chooses option 1, resolve this repo's own project key first — never assume a specific
one:

Resolve the project key AND host in the same shell invocation that runs the analysis below —
splitting resolution and analysis into separate fenced blocks loses the variable, since shell
state doesn't persist across separate command invocations (`address-pr-issues/SKILL.md`'s Step 1
`$WORKSPACE_DIR` shorthand note warns about exactly this same pitfall, in that file's own context):

```bash
if [ -f "sonar-project.properties" ]; then
  SONAR_PROJECT_KEY=$(grep -m1 '^sonar.projectKey=' sonar-project.properties | cut -d= -f2-)
  SONAR_HOST=$(grep -m1 '^sonar.host.url=' sonar-project.properties | cut -d= -f2-)
fi
SONAR_HOST="${SONAR_HOST:-https://sonarqube.churchofjesuschrist.org}"
SONAR_HOST="${SONAR_HOST%/}"  # normalize: no trailing slash, added explicitly below
if [ -z "$SONAR_PROJECT_KEY" ]; then
  echo "No sonar-project.properties found (or no sonar.projectKey line) — what's this repo's SonarQube project key? Wait for the answer and assign it to \$SONAR_PROJECT_KEY before continuing; do not run the analysis below with an empty key."
  exit 1
fi
echo "SonarQube project: $SONAR_PROJECT_KEY (host: $SONAR_HOST)"

# Build first (skip tests for speed)
mvn clean install -DskipTests

# Run SonarQube analysis.
# This environment provisions the credential as SONARQUBE_CLI_TOKEN (GNOME Keyring, exported in
# ~/.bashrc), not SONAR_TOKEN — so prefer it and fall back, rather than reporting "no token".
SONAR_TOKEN="${SONAR_TOKEN:-$SONARQUBE_CLI_TOKEN}"
mvn sonar:sonar \
  -Dsonar.host.url="$SONAR_HOST/" \
  -Dsonar.projectKey="$SONAR_PROJECT_KEY" \
  -Dsonar.token=$SONAR_TOKEN

# Wait for analysis to complete
echo "⏳ Waiting for SonarQube analysis..."
sleep 10

# Check quality gate
QUALITY_GATE=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "$SONAR_HOST/api/qualitygates/project_status?projectKey=$SONAR_PROJECT_KEY" \
  | jq -r '.projectStatus.status')

if [ "$QUALITY_GATE" = "OK" ]; then
  echo "✅ Quality Gate: PASSED"
elif [ -z "$QUALITY_GATE" ] || [ "$QUALITY_GATE" = "null" ]; then
  echo "⚠️  Could not read quality gate for key '$SONAR_PROJECT_KEY' at $SONAR_HOST — this is NOT necessarily a gate failure; check the key/host/\$SONAR_TOKEN before reporting FAILED."
else
  # SonarQube's projectStatus.status is one of OK/WARN/ERROR/NONE — name the actual value and the
  # state actually reached, rather than asserting FAILED for any non-OK, non-empty status. Use a
  # per-status marker, not an unconditional ❌ — WARN/NONE are not failures.
  case "$QUALITY_GATE" in
    ERROR) echo "❌ Quality Gate: ERROR — blocking issues below." ;;
    WARN) echo "⚠️  Quality Gate: WARN — warning threshold breached, not a hard failure." ;;
    NONE) echo "⚠️  Quality Gate: NONE — no quality gate conditions are configured for '$SONAR_PROJECT_KEY'; there is nothing to pass or fail." ;;
    *) echo "⚠️  Quality Gate: $QUALITY_GATE (unrecognized status) — treat as not-necessarily-failed and verify manually." ;;
  esac
  # Fetch and display issues
  curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/issues/search?componentKeys=$SONAR_PROJECT_KEY&resolved=false&inNewCodePeriod=true&impactSeverities=MEDIUM,HIGH,CRITICAL" \
    | jq -r '.issues[] | "[\(.impacts[0].severity)] \(.component | split(":")[-1]):\(.line // "N/A") - \(.message)"'
fi
```

Present any SonarQube findings in the same interactive format as pattern-based issues.

## Step 8: Final Summary and Recommendations

After all checks complete:

```markdown
## Pre-PR Audit Complete

**Pattern Checks**: X issues found
- Fixed: Y
- Skipped: Z
- Manual review needed: W

**Consistency Checks**: A issues found
- Pattern uniformity: B
- Test fixture gaps: C  
- Documentation drift: D
- Centralization opportunities: E
- Edge case coverage: F
- Related code patterns: G

**Maven Plugin Checks** (if applicable): H issues found
- CLI binding: I
- Resolution scope: J
- Maven API usage: K

**Spec-Completeness Review** (Step 4.8, if spec/doc files changed):
- Scope-broadening sweep: N issues found
- Rename cascade: N issues found
- Operator executability: N issues found
- Branch completeness: N issues found
- Term definition: N issues found
- Clean: ✅ all checks / ⚠️ N findings remain

**Whole-Document Coherence Walk** (Step 4.9, if spec/doc files changed):
- Integration breaks: N found
- Orphaned references: N found
- Scope coherence: N found
- Narrative discontinuity: N found
- Clean: ✅ document hangs together / ⚠️ N findings remain

**Adversarial Pattern Review** (Step 4.7):
- Rounds completed: R / 3
- Findings: N found, M fixed, K accepted-risk, J false-positives
- By class: [State Machine: N1, Operator Observability: N2, ...]
- By blast radius: cross_file N1, local N2
- Outcome: ❌ TEST_FAILURES — this round's test suite is red; checked FIRST by /adversarial-review's own Phase E, before every other outcome below — do not push until resolved / ✅ CONVERGED (cross-file yield 0; residual risk: open local findings/accepted-risk above) / ⚠️ NOT converged — escalate to targeted deep-dive on <theme> / 🟡 INCOMPLETE — N class(es) unreviewed (can co-occur with NOT converged — see /adversarial-review's Summary Output for the combined badge, not a mutually exclusive list) / 🟠 ABANDONED — round stopped at the human's request, no further rounds; approved fixes from that round remain applied in the working tree, committed or not

**Known Limitations** (for PR description):
> _(List findings classified as "accepted risk", plus any `coverage_gap` entries from a
> Phase E Accept/Abandon decision (visually distinct) — all MUST appear verbatim in the PR
> description so reviewers understand what was deliberately left in and why.)_

**Fix Provenance Notes** (round summary only — NOT a PR-description limitation, since these
findings were fixed, not left unaddressed):
> _(`/adversarial-review`'s own Summary Output returns this list per Step 4.7's contract above —
> "planning skipped: <stage> <failed|timed out|returned nothing usable>" entries. Surface them
> here, visually distinct from Known Limitations, so they don't silently disappear when this
> template is filled out verbatim.)_

**SonarQube**: Quality Gate {PASSED | FAILED | WARN — warning threshold breached, not a hard failure | NONE — no quality gate conditions configured | UNKNOWN — could not read (see key/host/$SONAR_TOKEN) | NOT RUN — user deferred}
- New issues: N
- Blocking issues: M

**Test Coverage**:
- New classes without tests: P
- Modified classes without test updates: Q

**Recommendations**:
✅ Safe to push - no blocking issues
OR
⚠️  Fix N blocking issues before pushing
OR
❌ Quality gate ERROR - see issues above
OR
⚠️  Quality gate undetermined (UNKNOWN / NOT RUN) — treated as blocking, but this is NOT a gate failure; resolve the key/host/$SONAR_TOKEN or run Step 7 before pushing

**Next Steps**:
1. Run tests: `mvn test`
2. Review changes: `git diff`
3. Commit: `git commit -m "..."`
4. Push: `git push`
```

**Record the audited tree and outcome** so the self-check in "When to Use This Skill" can tell a
genuinely new change from a re-trigger on content this skill already audited (re-invoking a
mandatory `/adversarial-review --rounds 3` sweep is the most expensive thing either skill does —
don't pay that cost twice for the same content), and so it never treats an incomplete run as
equivalent to a clean one:

```bash
# Read back Step 4.7's persisted outcome — shell variables do NOT survive from that block to this
# one (Steps 4.8/4.9/5/6/7 ran in between, in separate invocations); see Step 4.7's own note.
OUTCOME_FILE="$(git rev-parse --git-dir)/pre-pr-audit-adversarial-outcome"
if [ ! -f "$OUTCOME_FILE" ]; then
  echo "🛑 $OUTCOME_FILE not found — could be: Step 4.7's capture block was never run or was skipped (resumed session); its write failed; git rev-parse --git-dir resolved to a different path than when it was written (cwd moved — submodule, another repo, or a different worktree); or the file was manually removed. Re-run Step 4.7's capture block, or re-derive ADVERSARIAL_OUTCOME/TESTS_GREEN from adversarial-review's last-printed Outcome/test-result lines and write the file yourself before continuing." >&2
  exit 1
fi
read -r ADVERSARIAL_OUTCOME TESTS_GREEN < "$OUTCOME_FILE"
# Single-use, but NOT consumed yet — deferred to just before the final printf below, after every
# operation that can still exit 1 (the base-branch read-back next, then AUDITED_TREE derivation).
# Consuming it here would leave the marker destroyed if any of those later steps aborts, forcing
# a re-run of Step 4.7's mandatory --rounds 3 sweep (the most expensive part of this skill) just
# to regenerate a value this run already had in hand.

# Same reasoning as ADVERSARIAL_OUTCOME/TESTS_GREEN above — $BASE_BRANCH/$BASE_SOURCE were set
# back in Step 1, several fenced blocks and steps ago, and do NOT survive as shell variables to
# this one. Two fields, matching Step 1's two-field write — a single-field `cat` here would
# capture "branch source" as one corrupted string.
BASE_BRANCH_FILE="$(git rev-parse --git-dir)/pre-pr-audit-base-branch"
if [ ! -f "$BASE_BRANCH_FILE" ]; then
  echo "🛑 Could not read the persisted base branch — re-run Step 1's resolution (which persists it) before continuing." >&2
  exit 1
fi
read -r BASE_BRANCH BASE_SOURCE < "$BASE_BRANCH_FILE"

# Derive the audited tree from HEAD + any uncommitted changes — this skill routinely audits work
# before it's committed ("After implementing a feature but before committing"), and `HEAD^{tree}`
# alone only reflects the last commit: it would go stale the moment the working tree is dirty and
# could falsely match a later, DIFFERENT set of uncommitted edits made over the same HEAD. `git
# stash create` builds a commit object representing HEAD + working-tree + index state WITHOUT
# touching HEAD, the index, or the working tree (non-destructive, nothing is actually stashed); it
# prints nothing when the tree is already clean, hence the fallback to HEAD^{tree} in that case.
# NOTE on WHAT this certifies: this hash is taken HERE, at Step 8 — i.e. AFTER Step 6 may have
# applied Workflow-batch fixes — not at the point the checks in Steps 4/4.5/4.6/4.8/4.9 actually
# ran. Nothing re-runs those checks against Step 6's edits, so this marker can only certify "the
# tree as it stood when this run finished", not "content every check has verified". See
# WORKFLOW_BATCH_FIXES_APPLIED below, which forces NOT_CLEAN whenever that gap is live this run.
STASH_SHA=$(git stash create 2>/dev/null)
if [ -n "$STASH_SHA" ]; then
  AUDITED_TREE=$(git rev-parse "$STASH_SHA^{tree}")
else
  AUDITED_TREE=$(git rev-parse HEAD^{tree})
fi
# `git stash create` captures TRACKED content only — fold in a fingerprint of untracked (never
# `git add`ed) files too, or two working trees differing only by a brand-new file hash identically.
# sha1sum and xargs -r are GNU-coreutils-only — absent by default on macOS (which ships
# `shasum -a 1`/no -r support in BSD xargs). Guard both rather than assume a GNU environment.
HASH_CMD="sha1sum"; command -v sha1sum >/dev/null 2>&1 || HASH_CMD="shasum -a 1"
UNTRACKED_LIST=$(git ls-files --others --exclude-standard)
if [ -n "$UNTRACKED_LIST" ]; then
  UNTRACKED_FINGERPRINT=$(echo "$UNTRACKED_LIST" | while IFS= read -r f; do git hash-object "$f"; done | sort | $HASH_CMD | cut -d' ' -f1)
else
  UNTRACKED_FINGERPRINT=""
fi
AUDITED_TREE="${AUDITED_TREE}-${UNTRACKED_FINGERPRINT}"

# BLOCKING_ISSUES: unresolved CRITICAL/HIGH findings from the Workflow batch (Steps 4/4.5/4.6/4.8/
# 4.9) per Step 5/6's disposition tally, plus 1 if Step 7's SonarQube Quality Gate is ERROR,
# UNKNOWN, or NOT RUN — an undetermined gate must never read as clean. WARN and NONE are NOT
# blocking on their own (Step 7's own case block calls both "not a hard failure" /
# "nothing to pass or fail") — surface either as a note, not a blocking count.
BLOCKING_ISSUES=<count of open CRITICAL/HIGH Workflow-batch findings, plus 1 if the Quality Gate above is ERROR, UNKNOWN, or NOT RUN (WARN/NONE do not count)>

if [ "$ADVERSARIAL_OUTCOME" = "CONVERGED" ] && [ "$TESTS_GREEN" = "true" ] && [ "$BLOCKING_ISSUES" -eq 0 ] && [ "$WORKFLOW_BATCH_FIXES_APPLIED" != "true" ]; then
  OUTCOME="CLEAN"
else
  OUTCOME="NOT_CLEAN"  # NOT converged, INCOMPLETE, ABANDONED, TEST_FAILURES, blocking pattern/Sonar
  # issues, or WORKFLOW_BATCH_FIXES_APPLIED=true (Step 6 edited the tree after the checks ran
  # against it — see the AUDITED_TREE note above; this tree has never actually been re-verified)
fi
# Single-use: consume the marker only now, once the record it feeds is about to be durably
# written — a stale leftover from a prior/failed run can never be silently reused, but consuming
# it any earlier (before the fallible reads/derivations above) risks destroying it on an abort
# with nothing yet written to replace it.
rm -f "$OUTCOME_FILE"
# Record BASE_BRANCH alongside the tree — what was audited is a function of both. An audit that
# recorded CLEAN against one base branch must not authorize skipping a later run against a
# different base branch, even if the tree hash happens to still match.
printf '%s %s %s\n' "$AUDITED_TREE" "$BASE_BRANCH" "$OUTCOME" > "$(git rev-parse --git-dir)/pre-pr-audit-last-audit"
```

Use `git rev-parse --git-dir` rather than a literal `.git/` path — in a linked worktree, `.git`
is a regular file (a `gitdir:` pointer), not a directory, and a bare redirect into it fails with
"Not a directory".

## Important Notes

- **Non-Destructive**: All fixes create git-trackable changes. Review with `git diff` before committing.
- **Iterative**: After applying fixes, re-run pattern checks to catch new issues introduced by fixes.
- **Project Context**: The more patterns in CLAUDE.md, the better the project-specific checks.
- **Fast Iteration**: Pattern checks are fast (~seconds). SonarQube is comprehensive but slower (~2-3 min).
- **Complementary**: This skill is proactive (before PR). Use `/address-pr-issues` for reactive fixing after PR created.

## Extending for Other Languages

To add support for Python, JavaScript, etc.:
1. Detect file extensions in Step 2
2. Add language-specific patterns to `pattern_checker.py`
3. Adjust edge case patterns (e.g., Python uses `with` for resources)
4. Update test coverage detection for language-specific test conventions
