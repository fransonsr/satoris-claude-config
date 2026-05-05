# FamilySearch Observability Standards

**Version**: 1.3  
**Last Updated**: 2026-04-09  
**Source**: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards

## Executive Summary

As we transition from Splunk to Dynatrace, we are shifting from a log-centric approach to a full observability model that leverages logs, traces, and metrics together. We also are shifting to using different tools for application observability versus functional reporting.

**Key Principles:**
- Use Dynatrace for application observability and S3/Databricks for functional reporting and security forensics
- Use metrics for aggregation, traces for request flow, and logs for context and debugging

## Background

### Previous Approach (Splunk)
- Logs were the primary telemetry signal
- Heavy reliance on log aggregation for metrics and dashboards
- High log volume to capture business and operational data
- Custom log parsing and field extraction

### New Approach (Dynatrace)

Use Dynatrace to answer application and system observability questions, not business nor functional questions.

**Examples of application / system observability questions that Dynatrace is for:**
- Why is the website down?
- Why is the system slow?
- What failures are users experiencing?
- How much more headroom does the service have before needing to scale?

**Examples of business, functional, and operational questions that Dynatrace is not intended for:**
- How many users submitted names for ordinances last month?
- How many members signed in using Google versus a password over the last quarter?
- How has the data in the tree changed over the last couple of weeks?
- What records were accessed 6 months ago by a particular user?

**Use the right telemetry type:**
- **Metrics**: Numerical measurements (counters, gauges, histograms) for dashboards and alerts
- **Logs**: Context for errors, debugging, and events that need narrative detail
- **Traces**: Distributed request flow with automatic instrumentation

## Core Principles

### 1. Choose the Right Tool

| Use Case | Old (Splunk) | New |
|----------|--------------|-----|
| Application / system observability | Logs with some metrics | Dynatrace |
| Operational, functional, and business observability | Log every business transaction | S3 with Databricks queries |
| Data consistency reports | Log all changes to data | S3 with Databricks queries |
| Security forensics | Access logs and audit events | S3 with Databricks queries |

### 2. Choose the Right Telemetry Type

Service Caller Identification (SCID) is a hand-rolled distributed trace propagation context defined in 2015 at FamilySearch. While modern distributed tracing automatically propagates tracing context in theory, in practice not all aspects of the system support it. Until we are confident there are no gaps in trace context propagation, we will continue to support SCID.

### 3. Leverage Dynatrace Auto-Instrumentation

Dynatrace OneAgent automatically captures:
- Request/response times
- HTTP status codes
- Database query performance
- Service dependencies
- Error rates
- Infrastructure metrics

**Standard**: Do NOT log what Dynatrace captures automatically.

### 4. Reduce Log Volume

High log volume increases license costs around ingest, retention, and query.

**Standard**: Aim to reduce log volume compared to current Splunk usage by using the right tool.

## Log Levels

### How to Choose a Log Level

```
Is the system able to complete the operation?
├── NO → Did the system handle it gracefully?
│         (retry succeeded / fallback used / circuit breaker tripped)
│         ├── YES → WARN
│         └── NO  → ERROR
└── YES → Is this a meaningful business or operational milestone?
          ├── YES → INFO
          └── NO  → Is this diagnostic detail for troubleshooting?
                    ├── YES → Is it step-by-step execution flow?
                    │         (loop iterations, method entry/exit)
                    │         ├── YES → TRACE (dev only)
                    │         └── NO  → DEBUG (off in prod)
                    └── NO  → DO NOT LOG
```

**Golden rule**: If you cannot say who would act on this log line and why, do not log it.

### Log Level Summary

| Level | Production? | Volume Target | Human Response? |
|-------|-------------|---------------|-----------------|
| ERROR | Always on | <0.1% | Yes — investigate promptly |
| WARN | Always on | 1–2% | Monitor; alert on trends |
| INFO | On by default | 10–20% | No — operational visibility |
| DEBUG | OFF (enable temporarily) | 50–70% when enabled | No — diagnostic only |
| TRACE | OFF (never in prod) | N/A | No — development only |

### ERROR

**One-Line Rule**: Something broke and a human needs to investigate.

**When to Use**:
- Operation failed completely — all retries exhausted, no fallback available
- Data corruption or integrity violation detected
- Critical dependency completely unavailable (database, payment gateway)
- Contract violation from upstream — required field missing or wrong shape
- Unhandled exception that terminates a request or job

**When NOT to Use**:
- Client sent a bad request (400, 422) — use WARN or INFO instead
- Circuit breaker tripped — system is protecting itself → use WARN
- Single transient failure before retry succeeded → use WARN
- Expected 404 during normal operation → use DEBUG or nothing

**Production Setting**: Always on | **Volume Target**: < 0.1% of log volume

**Required Fields**:
- `timestamp`, `level`, `logger`, `message`, `host.name`
- `dt.trace_id`, `dt.span_id` (in request context)
- `stack_trace` (optional), `user.action` (optional)
- `retry.count` (optional), `external.dependency` (optional)

### WARN

**One-Line Rule**: Something is degraded or unexpected, but the system handled it.

**When to Use**:
- Circuit breaker opens against a struggling dependency
- Retry succeeded after one or more transient failures
- Fallback value or default used because preferred source was unavailable
- Resource threshold approaching critical level
- Deprecated endpoint, API version, or config key is being used
- Scheduled task skipped because previous run had not yet completed

**Production Setting**: Always on | **Volume Target**: 1–2% of log volume

**Required Fields**:
- `timestamp`, `level`, `logger`, `message`, `host.name`
- `dt.trace_id`, `dt.span_id` (in request context)
- `warn.category` (DEGRADATION | THRESHOLD | DEPRECATION | RETRY | FALLBACK)
- `retry.count`, `fallback.used`, `threshold.current`, `external.dependency` (contextual)

### INFO

**One-Line Rule**: A meaningful operational event completed.

The primary purpose of INFO logs is to facilitate triaging problems by giving context to other telemetry such as traces and warn/error logs. It is **not** for operational reports.

**When to Use**:
- Significant transaction completed (ordinance recorded, record merged, export finished)
- Service startup completed — one structured event with version and config summary
- Scheduled job started or completed (with record counts and duration)
- Configuration change applied at runtime
- Feature flag value changed
- Audit-worthy event (user data exported, admin action performed)

**When NOT to Use**:
- Per-record iteration in a batch job — log one summary at the end instead
- Internal method calls or intermediate steps within a request
- Any operation that occurs more than once per request → DEBUG
- Raw request/response bodies

**Production Setting**: On by default | **Volume Target**: 10–20% of log volume

**Required Fields**:
- `timestamp`, `level`, `logger`, `message`, `host.name`
- `dt.trace_id`, `dt.span_id` (in request context)
- `event.name` (recommended, dot-separated identifier)
- `record.count`, `user.id` (contextual)

### DEBUG

**One-Line Rule**: Details useful for diagnosing a specific problem.

**When to Use**:
- Routing, branching, or decision points that affect behavior
- Cache lookup details (key and hit/miss result)
- Outbound HTTP request being sent (URL, method — never credentials or body)
- Query parameters for a database call (never the results)
- Serialization/deserialization details when format issues are likely

**Production Setting**: OFF in production (enable temporarily) | **Volume Target**: 50–70% when enabled

### TRACE

**One-Line Rule**: Step-by-step execution flow for deep debugging.

**Production Setting**: NEVER enabled in production

**Recommendation**: Use OpenTelemetry span events instead of TRACE-level logs.

## What Data to Send to Dynatrace

### STOP: Dynatrace Captures This Automatically

Delete these log statements during migration:

| What You Used to Log in Splunk | How Dynatrace Captures It | Migration Action |
|--------------------------------|----------------------------|------------------|
| Every HTTP request with timing | OneAgent auto-instrumentation | DELETE |
| HTTP response times | OneAgent auto-instrumentation | DELETE |
| Inbound request URL, method, headers | OneAgent + OTel auto-instrumentation | DELETE |
| JVM heap, GC, thread count | OneAgent process monitoring | DELETE |
| Node.js event loop lag | OneAgent process monitoring | DELETE |
| Container CPU, memory, restarts | Kubernetes integration/ECS | DELETE |
| HTTP call duration and status | OTel auto-instrumented HTTP spans | DELETE or REPLACE with Metrics |
| Database query execution time | OTel auto-instrumented DB spans | DELETE |
| Message queue timing | OTel auto-instrumented messaging spans | DELETE or REPLACE with Metrics |
| Health check endpoint hits (200 OK) | Synthetic monitoring | DELETE |

### DO: Log These to Dynatrace

| What to Log | Level | Key Fields |
|-------------|-------|------------|
| Unrecoverable errors with stack trace | ERROR | stack_trace, external.dependency, http.status |
| Significant transaction milestones | INFO | event.name, duration.ms, outcome |
| Circuit breaker state changes | WARN | circuit.name, state.new, state.old, failure.rate |
| Retry outcomes (multiple attempts) | WARN | retry.count, retry.outcome, external.dependency |
| Resource threshold warnings | WARN | threshold.current, threshold.limit, resource.name |
| Batch/job completion summaries | INFO | job.name, record.count, duration.ms |
| Feature flag changes | INFO | flag.name, flag.value.old, flag.value.new |

### DO NOT: Never Send This to Dynatrace

**Category 1: Confidential Data**
- Passwords, API keys, client secrets, credentials
- Full authentication tokens
- Social Security Numbers or national ID numbers
- Credit/debit card numbers (PAN)
- Health record data (PHI)
- Database connection strings containing credentials
- Full PII (names, emails, phone numbers, membership record number)

**Category 2: Operational / Security Reporting**
Send these to S3 with Databricks queries instead.

**Category 3: Dynatrace Already Captures This**
See STOP table above.

## Structured Logging

**Standard**: Structured logging (JSON) is strongly preferred as the log format.

### Base Required Fields (every log event)

```json
{
  "timestamp": "2026-02-23T14:32:01.456Z",
  "level": "ERROR",
  "logger": "org.familysearch.reservation.ReservationService",
  "message": "Failed to process ordinance reservation"
}
```

**Standard**: Always include correlation IDs in logs.

### Dynatrace / OTel Correlation (automatic)

- `dt.trace_id` or `trace.id` — links the log line to a distributed trace
- `dt.span_id` or `span.id` — links to a specific operation span

These are automatically added by Dynatrace OneAgent to MDC.

### Business Correlation (manual)

- `user.id` — opaque user identifier (never plain-text name or email)
- `fscorrid` — browser/app session correlation identifier

## Metrics

Metrics are numerical data tracked over time. Storage and cost are much more efficient than logs when dimension cardinality is low.

**Standard**: Prefer metrics over logs when the data is numeric.

**Key concepts**:
- **Dimension**: Key/value attribute for filtering and grouping
- **Time series**: One stream per unique dimension combination
- **Cardinality**: How many different values. Low cardinality is safe, high cardinality explodes cost.

**Standard**: Attach dimensions to metrics when the set of possible values is small and known.

### New Approach (Micrometer-Based Dynatrace Metrics)

```properties
# In application.properties
management.dynatrace.metrics.export.enabled=true
```

```java
// In code, increment a tagged counter
meterRegistry.counter("volunteer-statistics.task-submission.count",
        Tag.of("task_name", submission.getTask().name()))
    .increment(submission.getCount());
```

Use predictable naming: `<blueprint>.<entity>.<measurement>`

## Log Sampling

### Always Log (no sampling)
- All ERROR-level events
- All WARN-level events

### Sample for High-Frequency Paths

```javascript
if (response.status >= 500) {
  logger.error("Request failed", error);
} else if (response.status >= 400) {
  logger.warn("Client error", {status, context});
} else if (shouldSample(0.001)) { // 0.1% sample
  logger.debug("Request succeeded", {context});
}
```

## Logger Configuration Guidance

- Use SLF4J with Logback or Log4j2
- Configure MDC to include correlation IDs
- Use `logstash-logback-encoder` for structured JSON output

**Example Configuration**:

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
  <file>/var/log/fs/app.json</file>
  <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
    <providers>
      <timestamp/>
      <pattern>
        <pattern>{"timestamp":"%date{ISO8601}","logger":"%logger","level":"%level","message":"%message"}</pattern>
      </pattern>
      <keyValuePairs/>
      <mdc/>
      <stackTrace>
        <throwableConverter class="net.logstash.logback.stacktrace.ShortenedThrowableConverter">
          <rootCauseFirst>true</rootCauseFirst>
          <exclude>(com\.dynatrace|reactor\.core\.publisher|io\.netty\.channel\.Abstract)</exclude>
        </throwableConverter>
      </stackTrace>
    </providers>
  </encoder>
</appender>
```

## Migration Guide

### Phase 1: Add Instrumentation
- Install Dynatrace OneAgent
- Verify automatic instrumentation
- Configure Micrometer for custom metrics
- Ensure structured logging includes trace/span IDs

### Phase 2: Reduce Log Volume
- Identify high-volume log statements
- Delete log statements for auto-captured data
- Implement log sampling for high-frequency paths
- Convert metric-style logs to custom OTel metrics

### Phase 3: Optimize
- Adjust production log levels per-service
- Fine-tune sampling rates
- Create Dynatrace dashboards (backed by metrics, not logs)
- Migrate alerts from log-based to metric-based

### Pre-Deployment Checklist

- [ ] No logging of auto-captured metrics
- [ ] All production logs include dt.trace_id and dt.span_id
- [ ] Structured logging produces valid JSON
- [ ] No sensitive data in logs
- [ ] Production default is INFO or higher (not DEBUG)
- [ ] Custom metrics for business KPIs
- [ ] Metric dimension cardinality is low
- [ ] High-frequency paths use sampling or metrics
- [ ] Logs include relevant business context
- [ ] Batch jobs log one summary at completion
- [ ] No duplicate error logging across layers

## Success Criteria

| Metric | Target |
|--------|--------|
| Log Volume Reduction | 60–80% vs current Splunk |
| Log Ingest Cost Reduction | 50–70% |
| Mean Time to Detect (MTTD) | Improve with metric-based alerting |
| Mean Time to Resolve (MTTR) | Improve with correlated log + trace data |
| ERROR Rate Accuracy | Fewer spurious ERRORs after reclassification |

## Support and Resources

- Logging and Observability Security Policy v1
- Dynatrace Documentation: https://docs.dynatrace.com
- OpenTelemetry Documentation: https://opentelemetry.io/docs/
- Internal Slack: #dynatrace-migration

## Quick Reference Card

```
SHOULD I LOG THIS?
1. Does Dynatrace already capture this?          -> DO NOT log it
2. Does it contain PII, tokens, or credentials?  -> NEVER log it
3. Does it happen more than once per request?    -> DEBUG/TRACE or metric
4. Would any human act on this log line?
   If no clear answer                            -> do not log it

WHICH LEVEL?
System could not complete the operation?
- No recovery possible                           -> ERROR
- System handled it (retry/fallback)             -> WARN
Meaningful business or operational milestone?    -> INFO
Diagnostic detail for troubleshooting?
- Step-by-step / loop iteration                  -> TRACE (dev only)
- Decisions, params, cache details               -> DEBUG (off in prod)

PRODUCTION VOLUME TARGETS
ERROR <0.1% | WARN 1-2% | INFO 10-20% | DEBUG OFF | TRACE OFF

REQUIRED FIELDS
Every log: timestamp, level, message
In request context: dt.trace_id, dt.span_id

GOLDEN RULE: If in doubt, do not log it.
```

---

**End of FamilySearch Observability Standards Reference**
