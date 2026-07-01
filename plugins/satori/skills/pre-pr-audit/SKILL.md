---
name: pre-pr-audit
description: Proactive code quality audit before creating a pull request - identifies resource leaks, edge case gaps, test coverage issues, and code quality problems using pattern matching and optional SonarQube analysis. Automatically fixes issues when possible. Use this skill whenever the user is about to create a PR, push code, or wants to check code quality before committing. Also use when they mention "before PR", "pre-commit check", "quality check", or "catch issues early".
---

# Pre-PR Code Quality Audit

Catch Copilot and SonarQube issues **before** creating a PR by running defensive programming checks and optional static analysis on changed files.

## When to Use This Skill

✅ **BEFORE creating PR** (proactive):
- User says "ready to create PR", "before I push", "check my code", "quality check"
- User asks to "catch issues early", "avoid PR feedback", "pre-commit review"
- After implementing a feature but before committing
- This skill predicts what Copilot will flag BEFORE you push

❌ **AFTER creating PR** (reactive):
- Use `/address-pr-issues` instead
- That skill handles existing Copilot comments and SonarQube issues
- Different workflows for different stages

## Workflow Overview

1. **Identify changed files** (git diff against base branch)
2. **Load project patterns** (from CLAUDE.md if present)
3. **Run pattern-based checks** (fast, structural analysis)
4. **Adversarial pattern review** (MANDATORY — invokes /adversarial-review, parallel per-class agents)
5. **Report findings** with severity and recommendations
6. **Offer to fix** issues automatically
7. **Validate fixes** (tests + optional SonarQube)
8. **Re-check after fixes** to verify

## Step 1: Determine Base Branch

Ask the user which branch to compare against, or auto-detect:

```bash
# Auto-detect upstream branch
BASE_BRANCH=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null | cut -d/ -f2)

# Fallback to common names
if [ -z "$BASE_BRANCH" ]; then
  if git show-ref --verify --quiet refs/heads/main; then
    BASE_BRANCH="main"
  elif git show-ref --verify --quiet refs/heads/master; then
    BASE_BRANCH="master"
  else
    # Ask user
    echo "Which branch should I compare against? (main/master/other)"
  fi
fi
```

## Step 2: Get Changed Files

```bash
CHANGED_FILES=$(git diff --name-only $BASE_BRANCH...HEAD)
CHANGED_JAVA_FILES=$(echo "$CHANGED_FILES" | grep "\.java$" || true)
CHANGED_SPEC_FILES=$(echo "$CHANGED_FILES" | grep -E "(SKILL\.md|README\.md|CONTRIBUTING\.md|USAGE\.md|CONSTRAINTS\.md|DESIGN\.md)" || true)

# If no Java files, check if there are other languages to analyze
if [ -z "$CHANGED_JAVA_FILES" ]; then
  echo "No Java files changed. Would you like me to analyze other file types?"
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

## Step 4: Run Parallel Analysis (Workflow)

Steps 4, 4.5, 4.6, and 4.7 run as parallel workflow agents — not sequentially in this session. This keeps the implementation session's context lean: only findings return, not the full analysis work.

Use the Workflow tool to spawn these agents simultaneously. Pass each agent the git diff output, changed file contents, and project patterns from CLAUDE.md:

- **Pattern Checks** — checks described in Step 4 details below
- **Consistency Checks** — checks described in Step 4.5 details below
- **Maven Plugin Checks** (skip if no `@Mojo` annotation or `maven-plugin` packaging detected) — checks in Step 4.6 below
- **Spec-Completeness Review** (skip if `CHANGED_SPEC_FILES` is empty) — checks described in Step 4.8 below; returns findings for review-pause in Step 5
- **Whole-Document Coherence Walk** (skip if `CHANGED_SPEC_FILES` is empty) — checks described in Step 4.9 below; single pass, non-repeating; returns findings for review-pause in Step 5
- **Adversarial Pattern Review** — delegates to /adversarial-review (see Step 4.7); returns per-round findings for review-pause in Step 5

Each agent returns findings as a list:
```json
[{"severity": "CRITICAL|HIGH|MEDIUM|LOW", "file": "path:line", "description": "...", "recommendation": "..."}]
```

Merge all findings by severity, then proceed to Step 5 to present interactively.

The detailed check instructions for each agent follow below.

---

## Step 4 Details: Pattern-Based Checks

Use the bundled pattern checker script:

```bash
python3 ~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/pre-pr-audit/scripts/pattern_checker.py \
  --changed-files "$CHANGED_JAVA_FILES" \
  --base-branch "$BASE_BRANCH" \
  --project-patterns "$PROJECT_PATTERNS"
```

The script checks for:

### Universal Patterns (All Projects)

**Resource Lifecycle**:
- File handles opened without try-with-resources or finally
- Locks acquired without unlock in finally
- Connections opened without close
- Streams not closed

**Fail-Fast vs Silent Failures**:
- `LOGGER.warn()` or `LOGGER.error()` with keywords: duplicate, invalid, corrupt, conflict, mismatch
- Exception caught but not re-thrown, just logged
- Returning null instead of throwing on error conditions

**Edge Case Coverage**:
- Map operations (`.get()`, `.put()`, `Collectors.toMap()`) without handling missing keys or duplicates
- Collection operations without null/empty checks
- Parse operations (`parseInt`, `parse`, `valueOf`) without try-catch
- Array access without bounds checking
- Python `dict.get(key, non_None_value)` where the key may be present with value `None` in externally-sourced dicts (JSON, API responses, subprocess output) — `dict.get` only uses the default for absent keys; flag and recommend `d.get(key) or default` instead (Python files only)
- Value extracted from a dict or parsed JSON immediately used in a type-dependent operation (iterated, sliced, `len()`, indexed, arithmetic) without a preceding `isinstance()` / `typeof` guard — applies to values from external sources where the schema is not compiler-enforced

**Try/Finally Scope**:
- Operations between resource acquisition and try block
- Exception-throwing code outside try but before finally

**Test Coverage**:
- New classes in `src/main` without corresponding test in `src/test`
- Modified main classes where test class wasn't modified

### Project-Specific Patterns (From CLAUDE.md)

Apply any patterns loaded from the project configuration.

### Silent Failure Patterns

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
- The same numeric constant (e.g., `60`, `80`, `MAX_LENGTH`) appearing in multiple files to control truncation, padding, or formatting
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
Skill(adversarial-review, args="--rounds 3 --base-branch <BASE_BRANCH> --intent-brief \"<intent-brief text>\"")
```

The `/adversarial-review` skill handles the full protocol:
- One review agent per pattern class (parallel, dynamic enumeration from the pattern file)
- Cascade sweep within each class (every callsite, not just changed lines)
- Synthesizer deduplication by (file, line_range) across classes
- Per-round review-pause (Step 5 below receives findings from each round)
- Git-guardrailed fix agents (PROHIBITED: git reset/rebase/commit/stash/restore)
- Up to 3 rounds, terminating when all classes are clean

The skill returns a summary containing: per-round breakdown, findings by class, known-limitations list (accepted-risk items) for the PR description, and any termination signal (PR too large / new unclassified bug class).

## Step 4.8: Spec-Completeness Review (Conditional: procedural spec/doc files in diff)

**Trigger**: Only run if `CHANGED_SPEC_FILES` is non-empty (SKILL.md, README.md,
CONTRIBUTING.md, USAGE.md, CONSTRAINTS.md, or DESIGN.md changed — same trigger as Step 4.9,
since both target procedural/spec documents, not just Claude Code skill files).

This step runs the **heuristic checks of Pattern #9 (Operator Spec Completeness)** from
`copilot-review-patterns.md` — the five *known* failure modes (scope sweep, rename cascade,
operator executability, branch completeness, term definition) that Copilot finds one at a time
across many rounds. Running them proactively in one pass eliminates those rounds. These five
checks treat the changed documents as *operator specifications* — executable, complete, and
internally consistent. This applies to any procedural document (a runbook, a migration guide,
an onboarding doc, a SKILL.md), not just Claude Code skills.

**Complementary lens handled elsewhere — do NOT duplicate here**: the holistic operator
walkthrough (Pattern #10, "Spec Operator Walkthrough") is the judgment-based complement to these
heuristics — a reviewer reads the changed spec linearly as a first-time operator and flags where
they would get stuck, with *no* foreknowledge of the five failure modes above. It runs
**automatically as a parallel class agent inside `/adversarial-review` (Step 4.7)** — no separate
invocation is needed in Step 4.8. This separation is deliberate: priming one agent with Pattern
#9's failure-mode list would contaminate the fresh-eyes walk (it would hunt for those five
patterns instead of reading naively), and adversarial-review's per-class parallel agents never see
each other's findings, which preserves the walk's independence. Overlap between Pattern #9 findings
(here) and Pattern #10 findings (Step 4.7) is expected; the adversarial-review synthesizer
deduplicates by (file, line_range).

Spawn a review agent with the full content of each changed spec/doc file and these five Pattern
#9 checks:

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

The narrow-scope Pattern #10 agent in adversarial-review reads only the changed sections of a spec and fires on every fix round. This step is its complement: it reads the **entire document** as a first-time reader, once, before the PR opens. Its specific purpose is to catch integration breaks between changed and unchanged content — issues that only appear when the whole document is read in sequence and the changed sections must cohere with the sections around them.

### Agent mandate

Spawn a fresh-eyes agent with the full content of each changed spec file. The agent receives:
- The complete document (not just the diff)
- This mandate only: "Read this document from beginning to end as someone who has never seen it. You have no knowledge of what changed, what was intended, or what any prior version said. Flag every place the document fails to hang together as a whole — where a changed section creates confusion, contradiction, or a gap when read alongside the unchanged sections around it."

Do **not** give the agent:
- The git diff or any indication of which sections changed
- The implementation session's intent or PR description
- Pattern #9's or Pattern #10's failure-mode lists

### What to look for

The agent reads linearly and flags:

1. **Integration breaks**: a changed section introduces a term, step, or behavior that contradicts or is inconsistent with an unchanged section elsewhere in the document
2. **Orphaned references**: an unchanged section refers to something (a step, a variable, a file) that the changed section has renamed, removed, or restructured — leaving the reference dangling
3. **Scope coherence**: the document's overall scope statement (often in the intro or a "When to use" section) no longer matches what the body of the document describes after the change
4. **Narrative discontinuity**: reading the document in order, the changed section feels abrupt, assumes context the preceding sections don't provide, or leaves the reader without enough information to continue to the next section

### Output format

```json
[{
  "severity": "HIGH|MEDIUM|LOW",
  "location": "section or step description",
  "description": "what fails to cohere and why",
  "changed_section": "the section that changed",
  "affected_section": "the unchanged section affected by the integration break"
}]
```

## Step 5: Present Findings Interactively (Per-Round Review-Pause)

This step is the **review-pause** between each adversarial-review round. For findings from Step 4.7, the `/adversarial-review` skill returns them here and waits for disposition before applying any fix.

For each issue found (pattern-check findings and adversarial-review findings), present:

```markdown
## Issue #1: Resource Leak (CRITICAL)

**File**: `FullExportJob.java:159`
**Pattern class**: Infrastructure / Environment Handling  ← for adversarial-review findings
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

**Accepted-risk items MUST be recorded in the adversarial-review summary** and surfaced in the PR description (Step 8). Silently dropping them is not acceptable — the absence of a finding in the summary is a claim that it was addressed.

Wait for user input before proceeding to the next issue.

## Step 6: Auto-Fix Issues (When Approved)

**For adversarial-review findings (Step 4.7)**: fixes are applied by the `/adversarial-review`
skill's own fix agents under strict git guardrails (PROHIBITED: git reset, rebase, commit,
stash, restore; PERMITTED: Edit/Write, read-only bash, git diff/status). The Intent Brief is
forwarded to every fix agent. Do not apply adversarial-review findings manually — return the
disposition to the skill so it can apply them under the correct guardrails.

**For pattern-check findings (Steps 4, 4.5, 4.6)**: apply the fix patterns below.

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

**NEVER skip this step silently.** After pattern checks AND Copilot simulator complete, you MUST present the SonarQube option to the user. The agent must wait for an explicit user decision — skipping without asking is not allowed.

```markdown
Pattern checks complete. Found X issues (Y fixed, Z skipped).
Copilot simulator complete. Predicted N high-confidence issues.

Would you like me to run SonarQube analysis for additional checking?
(This will take 2-3 minutes but may catch build-time issues)

Options:
1. Yes, run SonarQube now
2. No, I'll run it manually before pushing
3. Show me the command to run it myself
```

If user chooses option 1:

```bash
# Build first (skip tests for speed)
mvn clean install -DskipTests

# Run SonarQube analysis
mvn sonar:sonar \
  -Dsonar.host.url=https://sonarqube.churchofjesuschrist.org/ \
  -Dsonar.projectKey=fs-eng_cds-sls-bulk-export_maven-build \
  -Dsonar.token=$SONAR_TOKEN

# Wait for analysis to complete
echo "⏳ Waiting for SonarQube analysis..."
sleep 10

# Check quality gate
QUALITY_GATE=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "https://sonarqube.churchofjesuschrist.org/api/qualitygates/project_status?projectKey=fs-eng_cds-sls-bulk-export_maven-build" \
  | jq -r '.projectStatus.status')

if [ "$QUALITY_GATE" = "OK" ]; then
  echo "✅ Quality Gate: PASSED"
else
  echo "❌ Quality Gate: FAILED"
  # Fetch and display issues
  curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "https://sonarqube.churchofjesuschrist.org/api/issues/search?componentKeys=fs-eng_cds-sls-bulk-export_maven-build&resolved=false&inNewCodePeriod=true&impactSeverities=MEDIUM,HIGH,CRITICAL" \
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

**Spec-Completeness Review** (Step 4.8, if SKILL.md files changed):
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
- Clean: ✅ all classes / ⚠️ N findings remain

**Known Limitations** (for PR description):
> _(List findings classified as "accepted risk" — must appear verbatim in the PR description
> so reviewers understand what was deliberately left in and why.)_

**SonarQube**: Quality Gate {PASSED|FAILED}
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
❌ Quality gate failed - see issues above

**Next Steps**:
1. Run tests: `mvn test`
2. Review changes: `git diff`
3. Commit: `git commit -m "..."`
4. Push: `git push`
```

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
