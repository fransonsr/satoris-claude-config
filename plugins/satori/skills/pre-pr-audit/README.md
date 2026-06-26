---
name: pre-pr-audit
description: Proactive code quality audit before creating a pull request - identifies resource leaks, edge case gaps, test coverage issues, and code quality problems using pattern matching and optional SonarQube analysis. Automatically fixes issues when possible. Use this skill whenever the user is about to create a PR, push code, or wants to check code quality before committing. Also use when they mention "before PR", "pre-commit check", "quality check", or "catch issues early".
---

# Pre-PR Code Quality Audit

Catch Copilot and SonarQube issues **before** creating a PR by running defensive programming checks and optional static analysis on changed files.

## When to Use This Skill

Run this skill when:
- User says "ready to create PR", "before I push", "check my code", "quality check"
- User asks to "catch issues early", "avoid PR feedback", "pre-commit review"
- After implementing a feature but before committing
- Before running `/address-pr-issues` (this skill is proactive, that one is reactive)

## What's New in v1.1.0

**New Consistency Checks** (based on learnings from PR #6 - 13 rounds of Copilot feedback):

- ✅ **Pattern Uniformity**: Detects mixed approaches (e.g., inconsistent debug logging)
- ✅ **Test Fixture Completeness**: Finds test helpers missing fields used in production  
- ✅ **Documentation Sync**: Catches README/Javadoc drift from implementation
- ✅ **Centralization Opportunities**: Identifies duplicated logic that should be extracted
- ✅ **Enhanced Edge Case Coverage**: Expands null/empty/bounds validation checks
- ✅ **Related Code Review**: When finding an issue, checks for same pattern elsewhere

**Maven Plugin-Specific Checks** (conditional):

- ✅ Parameter CLI binding (@Parameter property attributes)
- ✅ Resolution scope vs classpath usage alignment
- ✅ Maven API usage (vs manual path construction)
- ✅ Aggregator vs per-module logic validation
- ✅ Debug logging convention enforcement

**Estimated Impact**: Catch 60-85% of Copilot/SonarQube issues before PR creation (8-11 rounds saved in our case study).

## Workflow Overview

1. **Identify changed files** (git diff against base branch)
2. **Load project patterns** (from CLAUDE.md if present)
3. **Run pattern-based checks** (fast, lightweight)
4. **Run consistency checks** (NEW - internal PR consistency)
5. **Run Maven plugin checks** (NEW - conditional on Maven plugins)
6. **Optionally run SonarQube** (comprehensive but slower)
7. **Report findings** with severity and recommendations
8. **Offer to fix** issues automatically
9. **Re-check after fixes** to verify

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

## Step 4: Run Pattern-Based Checks

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

**Try/Finally Scope**:
- Operations between resource acquisition and try block
- Exception-throwing code outside try but before finally

**Test Coverage**:
- New classes in `src/main` without corresponding test in `src/test`
- Modified main classes where test class wasn't modified

### Project-Specific Patterns (From CLAUDE.md)

Apply any patterns loaded from the project configuration.

## Step 5: Present Findings Interactively

For each issue found, present:

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
2. Skip this issue
3. Show me the proposed fix first
```

Wait for user input before proceeding to next issue.

## Step 6: Auto-Fix Issues (When Approved)

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

## Step 7: Optional SonarQube Analysis

After pattern checks complete, offer to run full SonarQube analysis:

```markdown
Pattern checks complete. Found X issues (Y fixed, Z skipped).

Would you like me to run SonarQube analysis for comprehensive checking?
(This will take 2-3 minutes but catches issues pattern matching can't detect)

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

## Real-World Example: PR #6 (13 Rounds → 2-5 Rounds)

### Without Pre-PR Audit (Baseline)

PR #6 (java-stack-logging-maven-plugin) went through **13 rounds** of Copilot feedback:

- **Round 10**: Mixed debug logging patterns (some used `getLog().debug()`, others `if (debug) getLog().info("[DEBUG]")`)
- **Round 10**: Missing `isDirectory()` check before scanning source roots
- **Round 10**: Hard-coded pattern filtering (should be in enum method)
- **Round 11**: File path collision in multi-module projects (relative vs absolute paths)
- **Round 11**: Brittle test for JSON indentation
- **Round 12**: More debug logging inconsistencies in related methods
- **Round 13**: Test fixture missing `absolutePath` field used in production

### With Pre-PR Audit (Projected)

The new consistency checks would have caught **8-11 of these issues** proactively:

✅ **Consistency Check #1 (Pattern Uniformity)**: Catches Rounds 10, 12 debug logging issues  
✅ **Consistency Check #2 (Test Fixture)**: Catches Round 13 missing field issue  
✅ **Consistency Check #4 (Centralization)**: Catches Round 10 scattered pattern logic  
✅ **Consistency Check #5 (Edge Cases)**: Catches Rounds 10, 11 validation gaps  
✅ **Maven Plugin Check #5 (Debug Convention)**: Catches all debug logging mismatches

**Result**: Estimated reduction from **13 rounds → 2-5 rounds** (60-85% fewer iterations).

## Extending for Other Languages

To add support for Python, JavaScript, etc.:
1. Detect file extensions in Step 2
2. Add language-specific patterns to `pattern_checker.py`
3. Adjust edge case patterns (e.g., Python uses `with` for resources)
4. Update test coverage detection for language-specific test conventions
