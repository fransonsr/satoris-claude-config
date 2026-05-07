---
name: splunk-to-dynatrace:convert-logs
description: Converts traditional log statements to SLF4J fluent API with structured arguments per FamilySearch Observability Standards. Handles field naming trade-offs, lambda wrapping for performance, and provides incremental conversion options for large codebases. Use this skill when refactoring logging code for Dynatrace migration or applying observability standards.
---

# Convert Logs Skill

Converts traditional SLF4J log statements to fluent API with structured arguments, applying FamilySearch Observability Standards. Supports incremental conversion for large codebases with performance optimizations and field naming flexibility.

## When to Use This Skill

- Converting existing log statements to structured format
- Applying FamilySearch Observability Standards to logging code
- Refactoring logs during Dynatrace migration
- Adding structured fields to improve observability
- Fixing log level violations (INFO → DEBUG, etc.)
- Converting counter/timing logs to metrics
- Optimizing expensive logging operations

## Conversion Capabilities

### 1. Basic Structured Conversion

Converts traditional parameterized logging to fluent API with structured fields:

**Before:**
```java
logger.info("Processing request for person {} with ordinance {}", personId, ordinanceType);
```

**After (Minimal - Default):**
```java
logger.atInfo()
    .addKeyValue("person.id", personId)
    .addKeyValue("ordinance.type", ordinanceType)
    .log("Processing ordinance request");
```

**After (Full Context - Optional):**
```java
logger.atInfo()
    .addKeyValue("person.id", personId)
    .addKeyValue("ordinance.type", ordinanceType)
    .addKeyValue("event.name", "ordinance.request.processing")
    .addKeyValue("request.source", "related-ready-api")
    .log("Processing ordinance request");
```

**Note**: By default, only convert fields present in the original log. Add context fields only when explicitly requested or when they add significant troubleshooting value (startup/config logs, errors, business events).

### 2. Delete Logs Dynatrace Auto-Captures

Identifies and marks for deletion logs that provide no value because Dynatrace OneAgent automatically captures the data:

**Before:**
```java
long startTime = System.currentTimeMillis();
// ... process request ...
logger.info("Request completed in {}ms with status {}", 
    System.currentTimeMillis() - startTime, statusCode);
```

**After:**
```java
// DELETE: Dynatrace OneAgent automatically captures HTTP request timing and status codes.
// Per FamilySearch Observability Standards, this log wastes ingest cost.
// Reference: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
// Original: logger.info("Request completed in {}ms with status {}", duration, statusCode);
//
// ... process request ...
// (log statement removed)
```

### 3. Convert to Metrics

Replaces aggregation-style INFO logs with Micrometer metrics:

**Before:**
```java
logger.info("Ordinance reservation completed. type={} count={}", ordinanceType, count);
```

**After:**
```java
// METRIC REPLACEMENT: Counter metric is more efficient than INFO log for aggregation
// Per FamilySearch Observability Standards, metrics are preferred for numerical tracking
meterRegistry.counter("gofr.ordinance.reservation.count",
        Tag.of("ordinance.type", ordinanceType))
    .increment(count);

// Retain minimal INFO log for trace correlation
logger.atInfo()
    .addKeyValue("event.name", "ordinance.reservation.completed")
    .addKeyValue("ordinance.type", ordinanceType)
    .addKeyValue("reservation.count", count)
    .log("Ordinance reservation completed");
```

### 4. Correct Log Levels

Applies log level decision tree from FamilySearch Observability Standards:

**Before:**
```java
logger.info("Cache miss for key {}", cacheKey);
```

**After (Minimal - Default):**
```java
// LEVEL CHANGED: Cache operations are diagnostic details → DEBUG, not INFO
// Per FamilySearch Observability Standards: INFO is for meaningful operational milestones
logger.atDebug()
    .addKeyValue("cache.key", cacheKey)
    .log("Cache miss");
```

**After (Full Context - Optional):**
```java
logger.atDebug()
    .addKeyValue("cache.name", "ordinance-status")
    .addKeyValue("cache.key", cacheKey)
    .addKeyValue("cache.result", "MISS")
    .addKeyValue("cache.hit_rate", getCacheHitRate())
    .log("Cache miss");
```

### 5. Exception Handling with Stack Traces

Converts exception logging to use `setCause()`:

**Before:**
```java
logger.error("Failed to fetch person data for {}", personId, exception);
```

**After (Minimal - Default):**
```java
logger.atError()
    .addKeyValue("person.id", personId)
    .setCause(exception)  // Stack trace automatically included and filtered per logback config
    .log("Failed to fetch person data");
```

**After (Full Context - Recommended for errors):**
```java
logger.atError()
    .addKeyValue("person.id", personId)
    .addKeyValue("external.dependency", "tree-foundation.familysearch.org")
    .addKeyValue("retry.count", 3)
    .addKeyValue("retry.strategy", "exponential-backoff")
    .setCause(exception)
    .log("Failed to fetch person data after retries");
```

**Note**: For ERROR-level logs, full context is often valuable for troubleshooting. Consider adding retry details, dependency names, and operation context.

### 6. Lambda Wrapping for Performance

Wraps expensive operations in lambdas to defer execution:

**Before:**
```java
logger.debug("Request details: {}", buildExpensiveDebugString(request));
```

**After:**
```java
logger.atDebug()
    .addKeyValue("request.details", () -> buildExpensiveDebugString(request))
    .log("Request details");
```

### 7. Guard Clauses for Performance-Critical Paths

Adds level checks for expensive operations:

**Before:**
```java
logger.debug("Full request dump: {}", serializeToJson(request));
```

**After:**
```java
if (logger.isDebugEnabled()) {
    logger.atDebug()
        .addKeyValue("request.dump", serializeToJson(request))
        .log("Full request dump");
}
```

## Field Enrichment Guidelines

The skill supports two levels of field enrichment when converting logs:

### Minimal Enrichment (Default)

Only convert fields that are present in the original log statement. This is the safest, cleanest approach.

**When to use:**
- General-purpose conversions
- High-volume logs (per-request, per-record)
- Simple state transitions
- When the original log already has sufficient context

**Example:**
```java
// Original: logger.info("Processing user {}", userId);
// Minimal: logger.atInfo().addKeyValue("user.id", userId).log("Processing user");
```

### Full Context Enrichment (Opt-In)

Add related context fields to provide complete configuration snapshot or troubleshooting details.

**When to use:**
- **Configuration/startup logs** (fires once at startup, rich context valuable)
- **ERROR-level logs** (needs full context for troubleshooting: retries, dependencies, timeouts)
- **Business event logs** (reporting/analytics needs complete data)
- **Complex operations** (multi-step workflows, external dependencies)

**When NOT to use:**
- High-volume DEBUG logs
- Simple cache hits/misses
- Per-record iteration logs
- Logs that already have sufficient context

**Example:**
```java
// Original: logger.info("Initializing executor with {} threads", corePoolSize);
// Full context:
logger.atDebug()
    .addKeyValue("executor.name", "asyncTaskExecutor")
    .addKeyValue("executor.type", "ThreadPoolTaskExecutor")
    .addKeyValue("pool.core_size", corePoolSize)
    .addKeyValue("pool.max_size", corePoolSize)
    .addKeyValue("pool.queue_capacity", 0)
    .addKeyValue("thread.name_prefix", "async-task-exec")
    .log("Initializing async executor");
```

**Default behavior**: Skill uses minimal enrichment unless user explicitly requests full context.

## Field Naming Strategies

The skill offers three approaches to field naming, with trade-off analysis:

### Option 1: Standardize Now (dot.notation)

Convert all fields to standard naming conventions immediately.

**Pros:**
- Clean, consistent field names from day one
- Aligns with FamilySearch Observability Standards
- Easier Dynatrace queries (standard field names)

**Cons:**
- Breaks existing Splunk dashboards immediately
- Requires updating all dashboards before deployment
- Higher risk, more coordination needed

**Example:**
```java
// Before: personId, ordinanceType
// After: person.id, ordinance.type
logger.atInfo()
    .addKeyValue("person.id", personId)
    .addKeyValue("ordinance.type", ordinanceType)
    .log("Processing request");
```

### Option 2: Defer Standardization (preserve original names)

Keep original field names during Phase 1, standardize later.

**Pros:**
- Existing Splunk dashboards continue working
- Lower risk initial deployment
- Can standardize fields incrementally

**Cons:**
- Non-standard field names in Splunk/Dynatrace
- Requires future refactoring pass
- Dashboards need updating eventually anyway

**Example:**
```java
// Keep original names: personId, ordinanceType
logger.atInfo()
    .addKeyValue("personId", personId)
    .addKeyValue("ordinanceType", ordinanceType)
    .log("Processing request");
```

### Option 3: Hybrid Approach (dual fields)

Include both original AND standard field names.

**Pros:**
- Dashboards work immediately (old field names)
- New dashboards can use standard names
- Smooth migration path

**Cons:**
- Higher log volume (duplicate fields)
- More verbose code
- Temporary solution still needs cleanup

**Example:**
```java
logger.atInfo()
    .addKeyValue("personId", personId)           // Old name for Splunk dashboards
    .addKeyValue("person.id", personId)          // Standard name for Dynatrace
    .addKeyValue("ordinanceType", ordinanceType) // Old name
    .addKeyValue("ordinance.type", ordinanceType) // Standard name
    .log("Processing request");
```

## Incremental Conversion for Large Codebases

For codebases with 500+ log statements, convert incrementally by module or task:

### Task-Based Conversion

User provides a specific task or scope:

**Example Tasks:**
- "Convert all ERROR-level logs in gofr-service module"
- "Convert logs in `RedisTokenStore` and `NextOrdinanceServiceImpl` classes"
- "Convert all logs that Dynatrace auto-captures (DELETE candidates)"
- "Convert business event logs to structured format"

**Workflow:**
1. User specifies task scope (module, class, log level, action type)
2. Skill identifies matching logs from analyze report
3. Skill performs conversion only on specified logs
4. Generates summary of changes made
5. User reviews, tests, commits, repeats for next task

### Module-Based Conversion

Convert one Maven module at a time:

**Example:**
- Phase 1: Convert `gofr-service` module
- Phase 2: Convert `gofr-ws` module
- Phase 3: Convert `gofr-acceptance` module

## Execution Strategy

This section defines HOW the skill executes conversions safely and efficiently.

### Critical Safety Requirements

**1. ALWAYS Create Feature Branch First**

Before ANY code modifications:

```bash
# Check current branch
git branch --show-current

# If on main/master/develop, create feature branch
git checkout -b feature/structured-logging-conversion-{module-or-scope}
```

**Rationale**: Enables safe rollback, isolation from main branch, easy code review.

**If user is already on a feature branch**: Ask "Continue on `{branch-name}` or create new branch?"

**2. ALWAYS Enter Plan Mode**

**MANDATORY**: Use plan mode to create detailed conversion plan and get user approval before making changes.

```
EnterPlanMode()
```

**Plan must include**:
- Specific logs to convert (file:line references)
- Action type per log (CONVERT, DELETE, METRIC, LEVEL_CHANGE)
- Field naming strategy chosen (Option 1, 2, or 3)
- Files that will be modified (full list)
- Estimated time and token usage
- Testing strategy
- Rollback plan if issues arise

**User must approve plan** before exiting plan mode and executing conversions.

**Rationale**: Large-scale code changes require explicit approval. Plan mode provides structured review and approval gate.

### User Interaction Flow

**Phase 1: Gather Context (6 questions)**

1. **Conversion Scope**
   ```
   "I found 33 log statements to convert across 3 modules. How would you like to proceed?
   
   A. Full conversion (all 33 logs, all modules)
   B. Module-by-module (gofr-service: 17, gofr-ws: 14, gofr-acceptance: 2)
   C. Task-based (choose: DELETE/METRIC/LEVEL_CHANGE/STRUCTURED)
   D. Specific classes (you specify class names)
   E. Custom scope (you describe)
   
   Recommended: B (module-by-module) for incremental testing"
   ```

2. **Field Naming Strategy**
   ```
   "Field naming strategy? (See 05-field-naming-analysis.md for details)
   
   Option 1: Standardize now (personId → person.id)
     ✅ Clean, standard queries in Dynatrace
     ❌ Breaks Splunk dashboards immediately
   
   Option 2: Defer standardization (keep personId)
     ✅ Splunk dashboards keep working
     ❌ Non-standard names, eventual refactor needed
   
   Option 3: Hybrid (include both personId AND person.id)
     ✅ Smooth migration, both systems work
     ❌ Higher log volume temporarily
   
   Which option? (1/2/3)"
   ```

3. **Field Enrichment Level**
   ```
   "Field enrichment strategy?
   
   Minimal: Only convert fields present in original log statement
     ✅ Clean, minimal changes (1-3 fields per log typically)
     ✅ Matches original log's intent
     ❌ Less context for troubleshooting
   
   Full: Add related context fields for complete configuration/error snapshot
     ✅ Rich context for troubleshooting (5-7 fields per log)
     ✅ Better for startup/config/error logs
     ❌ More verbose, may be over-logging for high-volume logs
   
   Which level? (minimal/full, default: minimal)
   
   Note: You can specify 'full' for specific log types (e.g., 'minimal, but full for errors and config logs')"
   ```

4. **Performance Optimizations**
   ```
   "Performance optimizations needed?
   
   - Lambda wrapping for expensive operations? (y/n)
     (Defers execution if log level suppressed)
   
   - Guard clauses for performance-critical paths? (y/n)
     (Adds if (logger.isDebugEnabled()) checks)
   
   Recommended: y for lambdas, n for guard clauses (add manually if needed)"
   ```

5. **Testing Strategy**
   ```
   "After conversion, should I:
   
   A. Run compilation only (mvn compile)
   B. Run tests (mvn clean compile test)
   C. Skip automated testing (you'll test manually)
   
   Recommended: B (catch issues early)"
   ```

6. **Plan Mode Confirmation**
   ```
   "I'll create a detailed conversion plan for your review.
   
   After you approve the plan, I'll:
   - Create/verify feature branch
   - Convert log statements per plan
   - Run tests (if selected)
   - Generate conversion summary report
   
   Ready to proceed? (y/n)"
   ```

**Phase 2: Create Plan (Plan Mode)**

**ENTER PLAN MODE** and create detailed plan:

```markdown
# Conversion Plan: [Scope Description]

## Summary
- Scope: [module/task/full]
- Field Naming: Option [1/2/3]
- Field Enrichment: [minimal/full/selective]
- Performance: Lambda wrapping [yes/no], Guard clauses [yes/no]
- Logs to convert: [N]
- Files to modify: [N]

## Branch Safety
- Current branch: [name]
- Action: [create feature branch / use existing]
- Branch name: feature/structured-logging-conversion-[scope]

## Conversions by File

### File: gofr-service/.../RedisTokenStore.java
- Line 45: CONVERT (INFO → structured fields)
  - Before: logger.info("Initializing token keys. token={}, tokenMeta={}", token, tokenMetadata);
  - After: logger.atInfo().addKeyValue("token.id", token).addKeyValue("token.metadata", tokenMetadata).log(...)
  - Fields: token.id, token.metadata, event.name
  
- Line 67: DELETE (HTTP timing auto-captured)
  - Will comment out with explanation
  
- Line 89: LEVEL_CHANGE (INFO → DEBUG, cache operation)
  - Will change to DEBUG + structured fields

### File: gofr-service/.../NextOrdinanceServiceImpl.java
[... continue for all files ...]

## Testing Plan
1. Run: mvn clean compile test -pl [module]
2. Expected: All tests pass
3. If tests fail: [analyze, fix, or rollback strategy]

## Estimated Effort
- Wall-clock time: 10-15 minutes
- Token usage: ~50K tokens
- Files modified: [N] files

## Rollback Plan
If issues arise:
1. git checkout [original-branch]
2. git branch -D [feature-branch]
3. Analysis reports preserved for future attempt

## Approval Required
User must approve this plan to proceed.
```

**Phase 3: Get Approval**

Present plan to user, wait for explicit approval:
```
"Plan created. Please review above.

Approve and proceed with conversion? (y/n)
If no, I can adjust the plan or cancel."
```

**If approved**: Exit plan mode, proceed to Phase 4
**If not approved**: Adjust plan based on feedback, re-present

**Phase 4: Execute Conversions**

**4.1 Safety Checks**
- Verify/create feature branch
- Verify analyze reports exist and are current
- Verify FamilySearch standards loaded

**4.2 Agent Orchestration Strategy**

**For Small Scope (<50 logs, <10 files):**
- **Single agent, sequential execution**
- Read analyze report → convert logs → write files → generate report
- Pro: Simple, predictable, low overhead
- Con: Slower for large scopes
- Wall-clock: ~10-15 minutes

**For Medium Scope (50-200 logs, multiple modules):**
- **Parallel agents per module**
- Spawn 1 agent per module (max 3-4 parallel)
- Each agent: reads module report → converts module logs → writes files
- Main agent: waits for completion → aggregates reports
- Pro: Faster (parallel work), module isolation
- Con: More complex orchestration
- Wall-clock: ~15-20 minutes

**For Large Scope (200+ logs, full codebase):**
- **Task-based batching with sequential agents**
- Break into tasks: DELETE (first), METRIC (second), LEVEL_CHANGE (third), STRUCTURED (last)
- Run 1 task at a time, sequential agents per task
- Progress reporting: "Completed task 2/4: METRIC conversions (25/33 total logs)"
- Pro: Manageable chunks, clear progress, can pause between tasks
- Con: Slower than parallel
- Wall-clock: ~30-60 minutes

**4.3 Per-File Conversion Process**

For each file to modify:

1. **Read file** (full content if <500 lines, targeted if larger)
2. **Identify log statements** (use analyze report line numbers)
3. **Apply transformations**:
   - Parse current format
   - Apply standards-based conversion (log level, fluent API)
   - **Field enrichment**:
     - **Minimal**: Only convert fields present in original log
     - **Full**: Add context fields based on log type (config, error, business event)
     - **Selective**: Apply full enrichment only to specified log types (e.g., errors, startup)
   - Generate fluent API code
   - Add explanatory comment if action type is DELETE, METRIC, or LEVEL_CHANGE
   - Preserve original as comment (optional, for review)
4. **Write file** (Edit tool, atomic operation)
5. **Track progress** (log to conversion report)

**4.4 Error Handling**

If conversion encounters issues:

- **Syntax error**: Skip log, document in report, continue with others
- **Ambiguous field name**: Use analyze report field name, document if uncertain
- **Missing context**: Skip log, flag for manual review in report
- **File read/write error**: Halt, report error, ask user for guidance

**Never guess or assume** - when uncertain, skip and document for manual review.

**Phase 5: Validation**

**5.1 Compilation Check**

If user selected testing:
```bash
mvn clean compile test -pl [module]
```

**If compilation fails**:
- Show error output
- Offer to fix syntax errors
- Offer to rollback if unfixable

**If tests fail**:
- Analyze failures (log output expectations vs structured format)
- Offer to fix test expectations
- Offer to rollback if complex

**5.2 Generate Conversion Report**

Create `conversion-summary-{scope}.md` with:
- Statistics (total converted, breakdown by action)
- Files modified with line-by-line actions
- Testing results (pass/fail, issues encountered)
- Next steps (commit, PR, continue to next module)

**Phase 6: Commit (Optional)**

Offer to create commit:
```
"Conversion complete! Create git commit?

I'll generate a commit message following your standards:
- feat/refactor prefix
- Scope in subject line
- Before/after summary in body
- Co-authored-by tag

Create commit now? (y/n)"
```

If yes, generate commit message and create commit.
If no, provide manual commit instructions.

### Performance Scaling Strategies

**Small Codebases (<100 logs):**
- Single agent sequential
- Read full files into context
- ~15K tokens per file × 10 files = ~150K tokens
- Wall-clock: 10-15 minutes

**Medium Codebases (100-500 logs):**
- Parallel agents per module (max 3-4)
- Targeted file reads (Edit tool for specific lines)
- ~30K tokens per module × 3 modules = ~90K tokens
- Wall-clock: 15-25 minutes

**Large Codebases (500+ logs):**
- Task-based sequential batching
- Process 50-100 logs per batch
- Progress reporting between batches
- ~50K tokens per batch × 6 batches = ~300K tokens
- Wall-clock: 45-90 minutes

### Validation Gates

Before considering conversion complete:

1. ✅ **Plan approved** by user in plan mode
2. ✅ **Feature branch** created/verified
3. ✅ **All planned conversions** attempted
4. ✅ **Compilation** succeeds (if testing enabled)
5. ✅ **Tests pass** (if testing enabled)
6. ✅ **Conversion report** generated with statistics
7. ✅ **User notified** of completion with next steps

If any gate fails, halt and report issue to user.

### Rollback Strategy

If critical issues arise during conversion:

**Option 1: Git Rollback (Safest)**
```bash
git checkout [original-branch]
git branch -D [feature-branch]
```
All changes discarded, clean slate.

**Option 2: Revert Specific Files**
```bash
git checkout HEAD -- path/to/file.java
```
Undo changes to specific files, keep others.

**Option 3: Commit and Fix Forward**
```bash
git add -A
git commit -m "WIP: Partial conversion with issues"
# Then fix issues in subsequent commits
```
Preserve work, fix incrementally.

**Present options to user** when issues arise, let them choose.

## Conversion Process

### Step 0: Repository Type Check (NEW in v1.1.0)

**For library repositories**, perform additional SLF4J facade validation before conversion.

Check repository type:
```bash
if [ -f .claude/workspace/repository-type.txt ]; then
    REPO_TYPE=$(cat .claude/workspace/repository-type.txt)
fi
```

**If `REPO_TYPE == "library"`**, execute library-specific validations (see "Library Repository Considerations" below).

---

### Step 1: Load Context

Read necessary context for conversion:

1. **Analyze Report**: Load `00-executive-summary.md` and relevant module reports
   - Identify log locations, current format, recommended actions
   - Understand field naming from `05-field-naming-analysis.md`

2. **FamilySearch Observability Standards**: Load decision trees and field requirements
   - Log level decision tree
   - Required fields by level (ERROR, WARN, INFO)
   - Standard field names (person.id, ordinance.type, etc.)

3. **User Preferences**: Confirm conversion scope and options
   - Field naming strategy (Option 1, 2, or 3)
   - Field enrichment level (minimal or full)
   - Performance optimization needs (lambda wrapping, guard clauses)
   - Conversion scope (full codebase, module, specific task)

### Step 2: Identify Logs to Convert

Based on user-specified scope:

- **Full conversion**: All logs from analyze report
- **Module conversion**: Logs in specified module(s)
- **Task conversion**: Logs matching task criteria (level, action type, class)

### Step 3: Perform Conversions

For each log statement:

1. **Parse Current Format**
   - Extract logger call, level, message template, parameters
   - Identify variable names and types

2. **Apply Standards-Based Transformation**
   - Determine correct log level per decision tree
   - Identify required fields for that level
   - Apply field naming strategy (Option 1, 2, or 3)
   - **Apply field enrichment**:
     - **Minimal (default)**: Only convert fields present in original log
     - **Full**: Add context fields based on log characteristics:
       - **Config/startup logs**: executor config, pool settings, connection params
       - **Error logs**: retry details, dependency names, timeout values
       - **Business events**: complete metric set, user demographics
     - **Selective**: Apply full enrichment to specific log types (e.g., "full for errors and config, minimal otherwise")
   - Add required standard fields only if enrichment is "full": `event.name` (INFO), `warn.category` (WARN)

3. **Handle Special Cases**
   - DELETE: Comment out and explain why
   - METRIC: Generate Micrometer counter/timer + minimal log
   - Exception: Use `setCause()` method
   - Expensive operation: Add lambda or guard clause

4. **Generate Converted Code**
   - Write fluent API call with structured fields
   - Add explanatory comment if action type is DELETE, METRIC, or LEVEL_CHANGE
   - Preserve original as comment for review

### Step 4: Generate Conversion Report

Create summary document with:

- Total logs converted
- Breakdown by action type (CONVERTED, DELETE, METRIC, LEVEL_CHANGE)
- Breakdown by module
- List of files modified with line numbers
- Next steps (testing, review, commit)

---

## Library Repository Considerations (NEW in v1.1.0)

**If repository type is "library"** (detected from `.claude/workspace/repository-type.txt`):

### SLF4J Facade Enforcement

**Before conversion**, validate all logging uses SLF4J facade (no backend-specific APIs):

```bash
# Check for backend-specific imports (should be NONE in src/main/java)
find src/main/java -name "*.java" -exec grep -l "import ch.qos.logback" {} \;
find src/main/java -name "*.java" -exec grep -l "import org.apache.log4j" {} \;
find src/main/java -name "*.java" -exec grep -l "import org.apache.logging.log4j" {} \;

# Expected: (empty - no matches)
```

**If backend imports found**, prompt user:

```
"⚠️ BACKEND-SPECIFIC IMPORTS DETECTED

Found logback/log4j imports in production code:
{LIST_FILES_WITH_BACKEND_IMPORTS}

Libraries MUST use SLF4J facade only:
- Use: import org.slf4j.Logger;
- Use: import org.slf4j.LoggerFactory;

**Why**: Consumer applications control the logging backend. Libraries depending on specific backends create version conflicts.

Convert backend-specific code to SLF4J? (y/n)"
```

**If yes**, convert backend-specific Logger declarations to SLF4J:

```java
// ❌ BEFORE: Backend-specific
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;

private static final Logger LOGGER = 
    (Logger) LoggerFactory.getLogger(MyClass.class);

// ✅ AFTER: SLF4J facade
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger LOGGER = 
    LoggerFactory.getLogger(MyClass.class);
```

**Track backend conversions** in conversion summary.

---

### Conversion Process (Same as Applications)

- **Code conversion**: IDENTICAL to applications (fluent API, structured fields)
- **Testing**: Run library tests as normal
- **No logback generation**: Libraries don't own encoder configuration

---

### Post-Conversion Consumer Reminder

**After conversion completion**, remind user about downstream coordination:

```
"✅ Conversion complete! 

✅ SLF4J facade validation: PASSED (no backend-specific imports)

⚠️ REMINDER: This is a library repository. Consumer applications must:
1. Have JSON encoder configured (run setup-logback in consumers)
2. Deploy updated logback BEFORE using this library version
3. Update dashboards if field names changed

See .claude/workspace/analysis/06-downstream-impact.md for detailed guidance.

**Next steps**:
1. Run tests: mvn clean test
2. Review changes: git diff
3. Read consumer guidance: .claude/workspace/analysis/06-downstream-impact.md
4. Coordinate with consumer teams before releasing new version"
```

---

## Output Format

### Modified Java Files

Each converted log includes explanatory comment:

```java
// CONVERTED: Added structured fields per FamilySearch Observability Standards
// Field naming: dot.notation (Option 1) for consistency with Dynatrace
logger.atInfo()
    .addKeyValue("person.id", personId)
    .addKeyValue("ordinance.type", ordinanceType)
    .addKeyValue("event.name", "ordinance.request.processing")
    .log("Processing ordinance request");
// Original: logger.info("Processing request for person {} with ordinance {}", personId, ordinanceType);
```

### Conversion Summary Report

Saved to workspace as `conversion-summary-{task-name}.md`:

```markdown
# Conversion Summary: {Task Description}

**Date**: 2026-05-04
**Scope**: {module or task description}
**Field Naming Strategy**: {Option 1, 2, or 3}
**Field Enrichment**: {minimal/full/selective}

## Summary Statistics

- **Total Logs Processed**: 47
- **Converted to Structured**: 32
- **Deleted (Dynatrace auto-captures)**: 8
- **Converted to Metrics**: 5
- **Level Changed**: 12

## Files Modified

### gofr-service/src/main/java/org/familysearch/gofr/service/impl/RedisTokenStore.java
- Line 45: CONVERTED (INFO → structured fields)
- Line 67: DELETE (HTTP timing auto-captured)
- Line 89: LEVEL_CHANGE (INFO → DEBUG, cache operation)

### gofr-service/src/main/java/org/familysearch/gofr/service/impl/NextOrdinanceServiceImpl.java
- Line 123: METRIC (counter replacement)
- Line 145: CONVERTED (WARN → structured fields with warn.category)

## Next Steps

1. **Review Changes**: Inspect modified files for correctness
2. **Run Tests**: Execute `mvn clean compile test -pl gofr-service`
3. **Fix Test Expectations**: Update any tests checking log output
4. **Commit Changes**: Create feature branch commit with descriptive message
5. **Verify Locally**: Test with JSON verification appender enabled
6. **Next Task**: Convert next module or task scope
```

## Standard Field Names Reference

Use these standard field names per FamilySearch Observability Standards:

### Common Fields (All Levels)
- `timestamp`: ISO 8601 timestamp (auto-added by encoder)
- `level`: Log level (auto-added)
- `logger`: Logger name (auto-added)
- `message`: Human-readable message (required)
- `dt.trace_id`: Dynatrace trace ID (auto-added by MDC)
- `dt.span_id`: Dynatrace span ID (auto-added by MDC)

### Business Context
- `person.id`: Tree person identifier (opaque ID)
- `ordinance.type`: Ordinance type (BAPTISM_CONFIRMATION, ENDOWMENT, etc.)
- `ordinance.target`: READY or SHARED
- `request.count`: Requested count
- `supply.count`: Actual count supplied
- `user.id`: Opaque user identifier (never PII)
- `fscorrid`: Browser/app session correlation ID

### Technical Context
- `event.name`: Dot-separated event identifier (e.g., "ordinance.request.completed")
- `external.dependency`: External service name (e.g., "tree-foundation.familysearch.org")
- `retry.count`: Number of retry attempts
- `retry.outcome`: SUCCESS or FAILURE
- `circuit.name`: Circuit breaker name
- `circuit.state`: OPEN, CLOSED, HALF_OPEN
- `cache.name`: Cache name
- `cache.key`: Cache key
- `cache.result`: HIT or MISS
- `threshold.current`: Current resource usage
- `threshold.limit`: Resource limit

### Error Context (ERROR level)
- `stack_trace`: Exception stack trace (via setCause())
- `http.status`: HTTP status code if relevant
- `error.code`: Application error code

### Warning Context (WARN level)
- `warn.category`: DEGRADATION, THRESHOLD, DEPRECATION, RETRY, FALLBACK
- `fallback.used`: true/false
- `deprecation.field`: Deprecated field name

## Best Practices

### 1. Preserve Original for Review

Always comment the original log statement to help code reviewers understand the change:

```java
// CONVERTED: Added structured fields
logger.atInfo()
    .addKeyValue("person.id", personId)
    .log("Processing person");
// Original: logger.info("Processing person {}", personId);
```

### 2. Apply Standards Strictly

Follow FamilySearch Observability Standards for:
- Log level appropriateness (decision tree)
- Required fields by level
- Field naming conventions
- No PII/credentials in logs

### 3. Test After Conversion

After each conversion task:
- Run `mvn clean compile test -pl {module}`
- Fix any tests checking log output
- Verify structured fields in JSON output (local verification)

### 4. Extract Complex Field Values

If field value requires complex computation, extract to variable:

```java
// ✅ GOOD: Extract complex value
String requestSummary = buildRequestSummary(request);
logger.atInfo()
    .addKeyValue("request.summary", requestSummary)
    .log("Request received");

// ❌ AVOID: Inline complex computation
logger.atInfo()
    .addKeyValue("request.summary", buildRequestSummary(request))
    .log("Request received");
```

### 5. Use Lambda Only for Expensive Operations

Don't over-use lambdas. Only wrap truly expensive operations:

```java
// ✅ GOOD: Lambda for expensive serialization
logger.atDebug()
    .addKeyValue("request.json", () -> objectMapper.writeValueAsString(request))
    .log("Request details");

// ❌ OVERKILL: Lambda for simple field access
logger.atInfo()
    .addKeyValue("person.id", () -> personId)  // Unnecessary
    .log("Processing person");
```

### 6. Business Events Need Structured Format Too

Convert business events (metrics logs) to structured format:

**Before:**
```java
METRICS_LOGGER.info(() -> {
    LogEventTagBuilder builder = new LogEventTagBuilder();
    event.forEachTag(builder::appendTag);
    return builder.toString();
});
```

**After:**
```java
// CONVERTED: Business event with structured fields
var logBuilder = METRICS_LOGGER.atInfo()
    .addKeyValue("event.name", "ordinance.metrics.report");
event.forEachTag((key, value) -> logBuilder.addKeyValue(key, value));
getCounterMetricCollector().forEachMetric((key, value) -> 
    logBuilder.addKeyValue(key, value));
logBuilder.log("Ordinance metrics report");
```

## Validation Rules

Before considering a log conversion complete, verify:

- [ ] Fluent API used correctly (`.atLevel()` → `.addKeyValue()` → `.log()`)
- [ ] All original parameters captured as structured fields
- [ ] Field names follow chosen naming strategy
- [ ] Required fields included (`event.name` for INFO, `warn.category` for WARN)
- [ ] Log level appropriate per decision tree
- [ ] No PII/credentials in field values
- [ ] Exception handled via `setCause()` not string parameter
- [ ] Expensive operations wrapped in lambda or guard clause
- [ ] Original log statement preserved as comment
- [ ] Explanatory comment added for DELETE/METRIC/LEVEL_CHANGE actions

## Common Conversion Patterns

### Pattern 1: Simple INFO with Parameters

```java
// Before
logger.info("User {} submitted {} ordinances", userId, count);

// After (Minimal - Default)
logger.atInfo()
    .addKeyValue("user.id", userId)
    .addKeyValue("ordinance.count", count)
    .log("User submitted ordinances");

// After (Full Context - if user requested)
logger.atInfo()
    .addKeyValue("user.id", userId)
    .addKeyValue("ordinance.count", count)
    .addKeyValue("event.name", "ordinance.submission.completed")
    .addKeyValue("submission.source", "web-ui")
    .log("User submitted ordinances");
```

### Pattern 2: ERROR with Exception

```java
// Before
logger.error("Failed to connect to Redis: {}", ex.getMessage(), ex);

// After (Minimal - Default)
logger.atError()
    .setCause(ex)
    .log("Failed to connect to Redis");

// After (Full Context - Recommended for errors)
logger.atError()
    .addKeyValue("external.dependency", "redis")
    .addKeyValue("redis.host", redisConfig.getHost())
    .addKeyValue("redis.port", redisConfig.getPort())
    .addKeyValue("retry.count", attemptNumber)
    .setCause(ex)
    .log("Failed to connect to Redis after retries");
```

**Note**: For ERROR-level logs, full context is often valuable for troubleshooting.

### Pattern 3: WARN with Retry

```java
// Before
logger.warn("Retrying request after failure, attempt {}", attemptNumber);

// After (Option 1: dot.notation)
logger.atWarn()
    .addKeyValue("warn.category", "RETRY")
    .addKeyValue("retry.count", attemptNumber)
    .addKeyValue("external.dependency", dependencyName)
    .log("Retrying request after failure");
```

### Pattern 4: DEBUG with Conditional

```java
// Before
if (logger.isDebugEnabled()) {
    logger.debug("Cache lookup: key={}, result={}", key, result);
}

// After (Option 1: dot.notation)
if (logger.isDebugEnabled()) {
    logger.atDebug()
        .addKeyValue("cache.name", "person-cache")
        .addKeyValue("cache.key", key)
        .addKeyValue("cache.result", result ? "HIT" : "MISS")
        .log("Cache lookup");
}
```

### Pattern 5: DELETE (Dynatrace Auto-Captures)

```java
// Before
logger.info("HTTP request to {} completed in {}ms with status {}", 
    url, duration, statusCode);

// After
// DELETE: Dynatrace OneAgent automatically captures HTTP request timing and status.
// Per FamilySearch Observability Standards, this log wastes ingest cost and provides no value.
// Reference: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
// Section: "STOP: Dynatrace Captures This Automatically"
// Original: logger.info("HTTP request to {} completed in {}ms with status {}", url, duration, statusCode);
```

### Pattern 6: METRIC Replacement

```java
// Before
logger.info("Processed {} records in {}ms", recordCount, duration);

// After
// METRIC REPLACEMENT: Histogram metric is more appropriate for timing + count aggregation
histogramTimer.record(duration, TimeUnit.MILLISECONDS);
meterRegistry.counter("gofr.records.processed")
    .increment(recordCount);

// Retain minimal INFO log for trace correlation
logger.atInfo()
    .addKeyValue("event.name", "batch.processing.completed")
    .addKeyValue("record.count", recordCount)
    .addKeyValue("duration.ms", duration)
    .log("Batch processing completed");
```

## When to Ask for Help

- **Ambiguous log purpose**: If you can't determine whether a log is meaningful or should be deleted, ask the user
- **Unknown external dependency**: If referencing external service but name unclear
- **Complex business logic**: If log captures domain-specific business event and you need context
- **Field naming conflicts**: If existing Splunk dashboards use specific field names that conflict with standards

## Error Handling

If conversion encounters issues:

1. **Syntax Errors**: Skip the problematic log, document in report, continue with others
2. **Unrecognized Patterns**: Flag for manual review, provide original + attempted conversion
3. **Missing Context**: Ask user for clarification rather than guessing

## References

- **FamilySearch Observability Standards**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **SLF4J Fluent API**: https://www.slf4j.org/manual.html#fluent
- **Logstash Logback Encoder**: https://github.com/logfellow/logstash-logback-encoder
- **Analyze Skill Output**: Look for files in workspace named `00-executive-summary.md`, `05-field-naming-analysis.md`, and module-specific reports

---

**Remember**: The goal is clear, maintainable structured logging that aligns with FamilySearch Observability Standards while providing flexibility for incremental migration and field naming trade-offs.
