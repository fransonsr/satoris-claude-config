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

**After:**
```java
logger.atInfo()
    .addKeyValue("person.id", personId)
    .addKeyValue("ordinance.type", ordinanceType)
    .addKeyValue("event.name", "ordinance.request.processing")
    .log("Processing ordinance request");
```

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

**After:**
```java
// LEVEL CHANGED: Cache operations are diagnostic details → DEBUG, not INFO
// Per FamilySearch Observability Standards: INFO is for meaningful operational milestones
logger.atDebug()
    .addKeyValue("cache.name", "ordinance-status")
    .addKeyValue("cache.key", cacheKey)
    .addKeyValue("cache.result", "MISS")
    .log("Cache miss");
```

### 5. Exception Handling with Stack Traces

Converts exception logging to use `setCause()`:

**Before:**
```java
logger.error("Failed to fetch person data for {}", personId, exception);
```

**After:**
```java
logger.atError()
    .addKeyValue("person.id", personId)
    .addKeyValue("external.dependency", "tree-foundation.familysearch.org")
    .addKeyValue("retry.count", 3)
    .setCause(exception)  // Stack trace automatically included and filtered per logback config
    .log("Failed to fetch person data after retries");
```

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

## Conversion Process

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
   - Add standard fields: `event.name` (INFO), `warn.category` (WARN)

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

// After (Option 1: dot.notation)
logger.atInfo()
    .addKeyValue("user.id", userId)
    .addKeyValue("ordinance.count", count)
    .addKeyValue("event.name", "ordinance.submission.completed")
    .log("User submitted ordinances");
```

### Pattern 2: ERROR with Exception

```java
// Before
logger.error("Failed to connect to Redis: {}", ex.getMessage(), ex);

// After (Option 1: dot.notation)
logger.atError()
    .addKeyValue("external.dependency", "redis")
    .addKeyValue("error.message", ex.getMessage())
    .setCause(ex)
    .log("Failed to connect to Redis");
```

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
