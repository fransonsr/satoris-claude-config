---
name: splunk-to-dynatrace:analyze
description: Analyze Spring Boot application logging patterns and generate compliance report against FamilySearch Observability Standards. Use this skill when starting a Splunk-to-Dynatrace migration, auditing existing log statements, checking standards compliance, or generating an inventory of logging patterns. This skill identifies logs that Dynatrace auto-captures (candidates for deletion), incorrect log levels, missing required fields, business events vs application logs, and provides a prioritized action list with compliance scoring.
---

# Splunk-to-Dynatrace Log Analysis Skill

Analyzes current logging patterns in a Spring Boot codebase and generates a comprehensive compliance report against [FamilySearch Observability Standards](https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards).

## When to Use This Skill

Use this skill when:
- Starting a Splunk-to-Dynatrace migration
- Auditing existing log statements for standards compliance
- Generating an inventory of current logging patterns
- Identifying logs that waste money (Dynatrace auto-captures them)
- Finding logs with incorrect levels (INFO that should be DEBUG, etc.)
- Separating business events from application logs

## What This Skill Does

Scans the codebase and produces a detailed report with:

1. **Log Inventory**: Count and categorization by level (ERROR, WARN, INFO, DEBUG, TRACE)
2. **Standards Compliance Analysis**: Evaluation against FamilySearch Observability Standards
3. **Deletion Candidates**: Logs Dynatrace auto-captures (HTTP timing, status codes, DB queries)
4. **Level Corrections**: Logs using wrong levels per decision tree
5. **Missing Fields**: Logs missing required fields (dt.trace_id, event.name, etc.)
6. **Business Events**: Identification of business/functional logs vs application logs
7. **Prioritized Action List**: DELETE > METRIC > LEVEL_CHANGE > STRUCTURED_FIELDS
8. **Compliance Score**: Percentage adhering to standards

## Analysis Process

### Step 1: Scan for Log Statements

Search the codebase for all logging patterns:

```bash
# Find all log statements (SLF4J, Lombok @Slf4j, Log4j)
find . -name "*.java" -type f -exec grep -l "logger\.\|log\.\|LOGGER\." {} \;
```

Look for:
- `logger.error()`, `logger.warn()`, `logger.info()`, `logger.debug()`, `logger.trace()`
- `log.error()`, `log.warn()`, `log.info()`, `log.debug()`, `log.trace()` (Lombok)
- `LOGGER.atError()`, `LOGGER.atInfo()` (fluent API)
- Named loggers (e.g., `LogManager.getLogger(class.getName() + ".metricsReport")`)

### Step 2: Categorize by Type

For each log statement, determine:

**A. Log Level** (ERROR, WARN, INFO, DEBUG, TRACE)

**B. Pattern Type**:
- Simple parameterized: `logger.info("message {}", param)`
- Fluent API: `logger.atInfo().addKeyValue("key", val).log("message")`
- Exception: `logger.error("message", exception)`
- Conditional: `if (logger.isDebugEnabled()) { ... }`
- Named logger (business events): Pattern contains `.metricsReport`, `.business`, `.analytics`

**C. Context** (helps determine if log is appropriate):
- Request handling (REST controllers)
- Batch jobs (loops, large datasets)
- Background tasks (scheduled jobs)
- Service calls (external dependencies)
- Configuration/startup
- Error handling

### Step 3: Evaluate Against Standards

For each log statement, check against FamilySearch Observability Standards:

#### Rule 1: Dynatrace Auto-Capture (DELETE candidates)

Check if log matches the "What You Used to Log in Splunk" table from standards:

| Pattern | Action | Reason |
|---------|--------|--------|
| HTTP request timing/duration | **DELETE** | OneAgent auto-captures |
| HTTP status codes per request | **DELETE** | OneAgent auto-captures |
| Database query timing | **DELETE** | OTel auto-instruments |
| JVM heap/GC/thread metrics | **DELETE** | OneAgent process monitoring |
| Container CPU/memory | **DELETE** | Kubernetes integration |
| Health check 200 OK | **DELETE** | Synthetic monitoring |

**Examples**:
```java
// DELETE: Dynatrace captures this automatically
logger.info("Request completed in {}ms with status {}", duration, statusCode);
logger.info("DB query took {}ms", queryTime);
logger.info("JVM heap usage: {} MB", heapUsed);
```

#### Rule 2: Incorrect Log Level (LEVEL_CHANGE candidates)

Use the decision tree from standards:

```
Is the system able to complete the operation?
├── NO → Did the system handle it gracefully?
│         ├── YES → WARN
│         └── NO  → ERROR
└── YES → Is this a meaningful business or operational milestone?
          ├── YES → INFO
          └── NO  → Is this diagnostic detail for troubleshooting?
                    ├── YES → Is it step-by-step execution flow?
                    │         ├── YES → TRACE (dev only)
                    │         └── NO  → DEBUG (off in prod)
                    └── NO  → DO NOT LOG
```

**Common misclassifications**:
- **INFO → DEBUG**: Cache operations, routing decisions, per-iteration logs
- **INFO → METRIC**: Counters, success rates, durations (use Micrometer instead)
- **ERROR → WARN**: Circuit breaker opens, retries succeeded, fallback used
- **WARN → DEBUG**: Client 400 errors (expected behavior)

**Examples**:
```java
// LEVEL_CHANGE: Cache operations are diagnostic → DEBUG, not INFO
logger.info("Cache miss for key {}", cacheKey);  // Should be DEBUG

// LEVEL_CHANGE: Per-record iteration → Should be aggregated or metric
logger.info("Processing record {} of {}", i, total);  // Should be DEBUG or summary

// LEVEL_CHANGE: Retry succeeded → WARN, not ERROR
logger.error("Request failed, retrying...", exception);  // Should be WARN if retry succeeds
```

#### Rule 3: Convert to Metric (METRIC candidates)

Logs that track numerical measurements should be metrics:

**Patterns**:
- Counters: "X completed", "Y processed", "Z failed"
- Gauges: "Queue depth", "Active connections", "Pool size"
- Timers/Histograms: "Operation took Xms" (if custom timing, not auto-captured)

**Examples**:
```java
// METRIC: Use Micrometer counter instead
logger.info("Ordinance reservation completed. type={} count={}", type, count);
// Recommend: meterRegistry.counter("gofr.ordinance.reservation.count", Tag.of("type", type)).increment(count);

// METRIC: Use gauge for resource tracking
logger.info("Connection pool at {}% capacity", utilization);
// Recommend: Gauge.builder("pool.utilization", () -> getUtilization()).register(registry);
```

#### Rule 4: Missing Required Fields

Per standards, structured logs MUST include:

**Base fields** (every log):
- `timestamp` (ISO 8601)
- `level` (ERROR, WARN, INFO, DEBUG, TRACE)
- `logger` (source class)
- `message` (human-readable)

**In request context** (automatically via MDC):
- `dt.trace_id` or `trace.id`
- `dt.span_id` or `span.id`

**Level-specific fields**:
- **INFO**: `event.name` (dot-separated identifier, e.g., "order.completed")
- **WARN**: `warn.category` (DEGRADATION | THRESHOLD | DEPRECATION | RETRY | FALLBACK)
- **ERROR**: `external.dependency` (if external service failed), `retry.count`

**Examples**:
```java
// MISSING FIELDS: INFO log should have event.name
logger.info("Ordinance reservation completed");
// Recommend: logger.atInfo().addKeyValue("event.name", "ordinance.reservation.completed").log(...)

// MISSING FIELDS: WARN should have category
logger.warn("Circuit breaker opened for service");
// Recommend: logger.atWarn().addKeyValue("warn.category", "DEGRADATION").log(...)

// MISSING FIELDS: ERROR should identify dependency
logger.error("Failed to fetch person data");
// Recommend: logger.atError().addKeyValue("external.dependency", "tree-foundation.familysearch.org").log(...)
```

#### Rule 5: Business Events vs Application Logs

**Business events** (for S3/Databricks, not Dynatrace):
- Track user actions, transactions, data changes
- Used for operational reports, analytics, auditing
- High volume, structured for querying
- Examples: "ordinance reserved", "record merged", "user signed in"

**Application logs** (for Dynatrace):
- Track system behavior, errors, performance
- Used for troubleshooting, alerting, monitoring
- Lower volume, contextual for debugging
- Examples: "circuit breaker opened", "retry succeeded", "startup completed"

**Identification patterns**:
- Named logger with suffix: `.metricsReport`, `.business`, `.analytics`, `.audit`
- High-volume INFO logs with counters
- Event names suggesting business activity: `*.completed`, `*.submitted`, `*.exported`
- Logs inside loops processing user data

**Examples**:
```java
// BUSINESS EVENT: Named logger pattern
private static final Logger METRICS_LOGGER = LogManager.getLogger(
    CounterMetricsListeners.class.getName() + ".metricsReport");
METRICS_LOGGER.info("type=BAPTISM count=4 userId=12345");

// APPLICATION LOG: System observability
logger.atWarn()
    .addKeyValue("warn.category", "DEGRADATION")
    .addKeyValue("circuit.name", "temple-service")
    .log("Circuit breaker opened");
```

### Step 4: Calculate Compliance Score

For each log statement, assign compliance status:

- ✅ **COMPLIANT**: Correct level, has required fields, appropriate use
- ⚠️ **NEEDS_STRUCTURED_FIELDS**: Right level but missing addKeyValue() format
- ❌ **NON_COMPLIANT**: Wrong level, missing fields, or should be deleted/metric

**Compliance Score** = (COMPLIANT count) / (total logs) × 100%

### Step 5: Generate Prioritized Action List

Group recommendations by priority:

**Priority 1: DELETE** (highest ROI, reduces cost immediately)
- Logs Dynatrace auto-captures
- No value, pure waste

**Priority 2: METRIC** (improves observability, enables aggregation)
- Counters, gauges, histograms
- Better tool for the job

**Priority 3: LEVEL_CHANGE** (fixes noise, improves signal)
- Incorrect ERROR/WARN levels causing alert fatigue
- INFO logs that should be DEBUG (reducing volume)

**Priority 4: STRUCTURED_FIELDS** (enables querying, future-proofs)
- Add `addKeyValue()` for JSON fields
- Add required fields (event.name, warn.category, etc.)

**Priority 5: RENAME** (cosmetic, but improves consistency)
- Field naming conventions (snake_case, dot.notation)

## Output Format

Generate a Markdown report with these sections:

### 1. Executive Summary

```markdown
# Splunk-to-Dynatrace Log Analysis Report

**Project**: [project-name]
**Analysis Date**: [date]
**Compliance Score**: [X]% ([Y] of [Z] logs compliant)

## Key Findings

- **Total Logs**: [N] statements across [M] files
- **Delete Candidates**: [X] logs (Dynatrace auto-captures)
- **Metric Candidates**: [Y] logs (should use Micrometer)
- **Level Changes**: [Z] logs (incorrect severity)
- **Business Events**: [B] logs (separate from app logs)
- **Estimated Volume Reduction**: [P]% (via deletions + metrics)
```

### 2. Log Inventory by Level

```markdown
## Log Inventory

| Level | Count | % of Total | Standards Volume Target |
|-------|-------|------------|--------------------------|
| ERROR | X     | Y%         | <0.1%                    |
| WARN  | X     | Y%         | 1-2%                     |
| INFO  | X     | Y%         | 10-20%                   |
| DEBUG | X     | Y%         | OFF in prod              |
| TRACE | X     | Y%         | OFF in prod              |

**Volume Assessment**: [Analysis of whether current distribution matches standards]
```

### 3. Detailed Findings

For each non-compliant log, include:

```markdown
### [File:LineNumber] - [ACTION]

**Current Code**:
```java
logger.info("Request completed in {}ms", duration);
```

**Issue**: Dynatrace OneAgent automatically captures request timing. This log provides no additional value.

**Recommendation**: DELETE

**Standards Reference**: "What You Used to Log in Splunk" table - HTTP call duration

**Priority**: 1 (DELETE)

---
```

### 4. Business Events Analysis

```markdown
## Business Events Identified

Business events should be routed to `/var/log/fs/business-events.json` for eventual S3/Databricks ingestion.

| Logger Name | Location | Volume Estimate |
|-------------|----------|-----------------|
| `CounterMetricsListeners.metricsReport` | `CounterMetricsListeners.java:45` | High |

**Recommendation**: Configure separate appender in logback-spring.xml for these loggers.
```

### 5. Prioritized Action List

```markdown
## Prioritized Action List

### Priority 1: DELETE ([N] logs, [P]% volume reduction)
1. `ServiceImpl.java:123` - HTTP request timing
2. `DatabaseDao.java:45` - DB query duration
3. ...

### Priority 2: METRIC ([N] logs)
1. `ReservationService.java:67` - Ordinance count
2. `BatchProcessor.java:89` - Records processed
3. ...

### Priority 3: LEVEL_CHANGE ([N] logs)
1. `CacheService.java:34` - Cache miss (INFO → DEBUG)
2. `FilterChain.java:12` - Per-request (INFO → DEBUG)
3. ...

### Priority 4: STRUCTURED_FIELDS ([N] logs)
1. `AsyncRunner.java:56` - Missing event.name
2. `RetryService.java:78` - Missing warn.category
3. ...

### Priority 5: RENAME ([N] logs)
1. `TokenStore.java:23` - Field naming (personId → person.id)
2. ...
```

### 6. Next Steps

```markdown
## Recommended Next Steps

1. **Review Findings**: Validate recommendations with team
2. **Prioritize Quick Wins**: Start with DELETE candidates (immediate cost savings)
3. **Convert Metrics**: Add Micrometer counters for metric candidates
4. **Apply Level Changes**: Fix incorrect ERROR/WARN levels
5. **Add Structured Fields**: Convert to fluent API with addKeyValue()
6. **Run Conversion Skill**: Use `/splunk-to-dynatrace:convert-logs` to automate transformations
7. **Setup Logback**: Use `/splunk-to-dynatrace:setup-logback` to generate configuration
8. **Test Locally**: Enable JSON file verification in logback-spring.xml
9. **Deploy to Integration**: Validate Splunk ingestion of structured JSON
10. **Update Dashboards**: Migrate Splunk queries to use new JSON fields

**Estimated Effort**: [X] developer-days
**Estimated Cost Savings**: [Y]% log volume reduction → $[Z] per month
```

## Edge Cases and Considerations

### Handling Ambiguous Cases

Some logs are hard to categorize automatically. Flag these for human review:

**Ambiguous Level**:
```java
// Could be WARN (degraded) or INFO (milestone) depending on context
logger.info("Using cached data due to service unavailability");
```
→ Flag as "REVIEW: Level depends on whether service failure is expected"

**Potential Business Event**:
```java
// Could be business event or application log
logger.info("Template exported for user {}", userId);
```
→ Flag as "REVIEW: Determine if this is operational reporting or troubleshooting"

### MDC Trace Context

Don't flag logs as missing `dt.trace_id`/`dt.span_id` — these are automatically added by Dynatrace OneAgent to MDC. Mention this in the report:

```markdown
**Note**: `dt.trace_id` and `dt.span_id` are automatically injected into MDC by Dynatrace OneAgent. No code changes needed for trace correlation.
```

### Lombok Loggers

Recognize Lombok's `@Slf4j` annotation:
```java
@Slf4j
public class MyService {
    log.info("message");  // 'log' field injected by Lombok
}
```

### Legacy Patterns

Some codebases may use older patterns:
```java
// Legacy Log4j 2
private static final Logger logger = LogManager.getLogger(MyClass.class);

// Legacy Commons Logging
private static final Log log = LogFactory.getLog(MyClass.class);
```

Include these in the analysis.

## Performance Considerations

For large codebases (>100k lines):
1. **Parallelize file scanning** if possible
2. **Sample representative files** rather than analyzing every file
3. **Focus on critical paths** (REST controllers, service layer, batch jobs)
4. **Generate summary statistics** first, detailed findings for flagged items only

## References

- **FamilySearch Observability Standards**: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards
- **SLF4J Fluent API Documentation**: https://www.slf4j.org/manual.html#fluent
- **Micrometer Documentation**: https://micrometer.io/docs
- **Logstash Logback Encoder**: https://github.com/logfellow/logstash-logback-encoder

## Example Usage

```
User: "Analyze the logging in this Spring Boot project for Splunk-to-Dynatrace migration"

You:
1. Scan codebase for log statements
2. Evaluate each against FamilySearch Observability Standards
3. Generate comprehensive report with:
   - Compliance score
   - Log inventory
   - Deletion candidates
   - Level corrections
   - Business event identification
   - Prioritized action list
4. Present report to user
5. Recommend running `/splunk-to-dynatrace:convert-logs` next
```

## Integration with Other Skills

After running this analysis:
- Use `/splunk-to-dynatrace:convert-logs` to apply recommended transformations
- Use `/splunk-to-dynatrace:setup-logback` to generate configuration
- Use `/splunk-to-dynatrace:validate-dashboards` to check Splunk dashboard compatibility
