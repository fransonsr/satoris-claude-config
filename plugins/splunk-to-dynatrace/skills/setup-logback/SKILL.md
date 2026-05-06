---
name: splunk-to-dynatrace:setup-logback
description: Generates logback-spring.xml configuration for structured JSON logging with profile-based appenders (local, production, staging, integ, canary). Supports phased migration from Splunk to Dynatrace with business event separation. Use this skill when setting up logging infrastructure for Dynatrace migration or configuring profile-specific log output.
---

# Setup Logback Skill

Generates `logback-spring.xml` configuration for structured JSON logging, supporting phased migration from Splunk-only to dual-destination (Splunk + Dynatrace) to Dynatrace-only.

## When to Use This Skill

- Setting up structured JSON logging infrastructure
- Configuring profile-based log appenders (local vs deployed)
- Implementing phased Splunk-to-Dynatrace migration
- Separating business events from application logs
- Adding rolling policies and retention settings
- Configuring stack trace filtering per observability standards

## Configuration Phases

### Phase 1: Structured JSON to Splunk (Initial)

**Files Written:**
- `/var/log/fs/app.json` (Application logs → Splunk)
- `/var/log/fs/business-events.json` (Business events → Splunk, separate retention)

**Profiles:** `production`, `staging`, `integ`, `canary`

### Phase 2: Dual Destination (Migration Period)

**Files Written:**
- `/var/log/fs/app.json` (Application logs → Splunk)
- `/var/log/fs-log/app.json` (Application logs → Dynatrace)
- `/var/log/fs/business-events.json` (Business events → Splunk/future S3)

**Both Splunk and Dynatrace ingest structured JSON simultaneously for validation.**

### Phase 3: Dynatrace Only (Final State)

**Files Written:**
- `/var/log/fs-log/app.json` (Application logs → Dynatrace)
- `/var/log/fs-log/business-events.json` (Business events → Dynatrace/S3)

**Splunk appenders removed, Dynatrace is primary observability platform.**

## Configuration Strategy

### Profile-Based Appenders

Use Spring profiles to control which appenders are active:

- **`local`**: Human-readable console + optional JSON verification file
- **`production`, `staging`, `integ`, `canary`**: JSON file appenders for Splunk/Dynatrace

### Encoder Choice

- **`LoggingEventCompositeJsonEncoder`**: Used for all JSON appenders
  - Provides fine-grained control over JSON structure
  - Supports MDC, structured arguments, stack trace filtering
  - Compatible with both Splunk and Dynatrace

### Business Event Routing

Use named logger routing to separate business events:

```xml
<logger name="org.familysearch.gofr.service.metrics.CounterMetricsListeners.metricsReport"
        level="INFO"
        additivity="false">
    <appender-ref ref="BUSINESS_EVENTS" />
</logger>
```

**Pattern**: `{ClassName}.metricsReport` or similar suffix identifies business event logs.

## Skill Workflow

### Step 1: Detect Current Configuration

**CRITICAL**: Always check for existing configuration before generating. Real-world projects often have logging already configured.

#### 1.1 Check for Existing Logback Files

```bash
find . -name "logback*.xml" -o -name "logback*.groovy"
```

**Possible states**:
- **A. `logback-spring.xml` exists**: Enhance/merge (most common in Spring Boot projects)
- **B. `logback.xml` exists**: Migrate to `logback-spring.xml` (add Spring profile support)
- **C. `logback-test.xml` only**: Properties-based logging in main, create `logback-spring.xml`
- **D. No logback files**: Properties-based logging, create from scratch

#### 1.2 Read Existing Configuration (if found)

For each existing file:

1. **Parse XML structure**:
   - Extract existing appenders (console, file, async, syslog, etc.)
   - Extract existing loggers (custom routing, level overrides)
   - Extract existing properties/variables
   - Identify async wrappers, filters, custom encoders

2. **Identify customizations to preserve**:
   - Custom appenders (Slack, email, database, etc.)
   - Custom loggers (third-party library level overrides)
   - Custom patterns or formats
   - Async configuration (queue size, discarding policies)
   - Custom filters (threshold, marker, evaluator)

3. **Check for Spring profiles**:
   - If `<springProfile>` tags exist → already Spring-aware
   - If not → needs migration to logback-spring.xml

#### 1.3 Read Application Properties

```bash
grep -r "logging\." src/main/resources/application*.properties
```

**Extract**:
- Log levels: `logging.level.root`, `logging.level.{package}`
- File paths: `logging.file.name`, `logging.file.path`
- Patterns: `logging.pattern.console`, `logging.pattern.file`
- Profiles: List all `application-{profile}.properties` files

#### 1.4 Categorize Configuration State

Based on findings, determine approach:

**State A: `logback-spring.xml` exists (Enhance/Merge)**
- Preserve all existing appenders and loggers
- Add JSON appenders for Phase 1 (Splunk)
- Add Phase 2 section (Dynatrace, commented)
- Add business event routing if not present
- Update encoder to LoggingEventCompositeJsonEncoder if needed

**State B: `logback.xml` exists (Migrate)**
- Rename to `logback-spring.xml` (or create new, deprecate old)
- Wrap existing config in `<springProfile>` tags
- Add profile-specific sections (local vs deployed)
- Add JSON appenders for Phase 1
- Preserve all custom loggers and appenders

**State C/D: Properties-only or no logging config (Create from scratch)**
- Generate full `logback-spring.xml` from template
- Use detected profiles from application properties
- Use detected log levels as defaults

### Step 2: Confirm Configuration Approach

Ask user to confirm approach based on detected state:

**If existing configuration found (State A or B)**:
```
"I found existing logback configuration:
- File: {logback-spring.xml or logback.xml}
- Existing appenders: {list detected appenders}
- Existing loggers: {list custom loggers}
- Spring profiles: {present/not present}

Approach: {Enhance/Migrate}
- Preserve all existing custom appenders and loggers
- Add JSON appenders for structured logging to Splunk
- Add commented Phase 2 section for future Dynatrace
- {If logback.xml: Migrate to logback-spring.xml with profile support}

Proceed with this approach? (y/n)
If no, I can show you what will be preserved/changed."
```

**If no existing configuration (State C/D)**:
```
"No logback configuration found. I'll create logback-spring.xml from scratch.
Detected profiles: {list from application-{profile}.properties}
Proceed? (y/n)"
```

**Then ask standard configuration questions**:

1. **Migration Phase**: Which phase to configure?
   - Phase 1: Splunk only (default for initial setup)
   - Phase 2: Dual destination (Splunk + Dynatrace)
   - Phase 3: Dynatrace only

2. **Local Development**: What should local profile do?
   - Console pattern only (human-readable, default)
   - Console + JSON verification file (for testing)

3. **Business Event Logger Names**: Identify named loggers for business events
   - Pattern: `{ClassName}.metricsReport`
   - Scan codebase for named logger declarations

4. **Retention Policies**: Confirm retention settings
   - Application logs: 7 days (default)
   - Business events: 30 days (default)
   - Max total size: 1GB application, 2GB business events

5. **Stack Trace Filtering**: Confirm exclusion patterns
   - Default: Dynatrace, Reactor, Netty, Spring Security, Catalina
   - Add project-specific packages if needed

### Step 3: Generate or Enhance Configuration

**For State A (logback-spring.xml exists) - ENHANCE/MERGE**:

1. **Read existing file completely**
2. **Identify insertion points**:
   - Add JSON appenders to appropriate `<springProfile>` sections
   - If no profile sections exist, wrap existing config in profiles
   - Add business event logger routing before `<root>` element
3. **Preserve existing elements**:
   - Keep all custom appenders (email, Slack, syslog, etc.)
   - Keep all custom loggers with their configurations
   - Keep all properties/variables
   - Keep async wrappers and filters
4. **Add new elements**:
   - APPLICATION_LOGS appender (JSON for Splunk)
   - BUSINESS_EVENTS appender (JSON separate file)
   - Phase 2 section (commented Dynatrace appender)
   - Business event logger routing
5. **Update existing elements** (if needed):
   - Add appender-ref to root logger for new JSON appenders
   - Update encoder if using old format

**Example enhancement**:
```xml
<!-- EXISTING (preserved) -->
<appender name="CUSTOM_EMAIL" class="ch.qos.logback.classic.net.SMTPAppender">
  <!-- ... existing config ... -->
</appender>

<!-- NEW (added by skill) -->
<appender name="APPLICATION_LOGS" class="ch.qos.logback.core.rolling.RollingFileAppender">
  <file>/var/log/fs/app.json</file>
  <!-- ... JSON encoder config ... -->
</appender>

<!-- EXISTING (preserved) -->
<logger name="com.example.MyClass" level="DEBUG"/>

<!-- NEW (added by skill) -->
<logger name="org.example.metrics.MetricsLogger.metricsReport" level="INFO" additivity="false">
  <appender-ref ref="BUSINESS_EVENTS" />
</logger>

<!-- EXISTING root (enhanced with new appender) -->
<root level="INFO">
  <appender-ref ref="CONSOLE" />
  <appender-ref ref="CUSTOM_EMAIL" />
  <appender-ref ref="APPLICATION_LOGS" /> <!-- ADDED -->
</root>
```

**For State B (logback.xml exists) - MIGRATE**:

1. **Read existing logback.xml**
2. **Create new logback-spring.xml**:
   - Wrap existing configuration in `<springProfile>` tags
   - Duplicate sections for local vs deployed profiles
   - Add JSON appenders to deployed profile sections
3. **Preserve all existing elements** within profile sections
4. **Leave old logback.xml in place** (Spring Boot prefers logback-spring.xml)
5. **Add comment in logback.xml**: "Deprecated: Use logback-spring.xml"

**For State C/D (No config) - CREATE**:

Generate complete configuration from template (existing behavior).

### Step 4: Generate or Enhance logback-spring.xml

Create complete configuration with:

1. **Spring Profile Sections**:
   - `<springProfile name="local">` → Console appender
   - `<springProfile name="production,staging,integ,canary">` → JSON file appenders

2. **Appender Definitions**:
   - Console (pattern for local, JSON optional for verification)
   - Application logs (JSON for Splunk/Dynatrace)
   - Business events (JSON separate file)

3. **Encoder Configuration**:
   - Timestamp (ISO 8601, UTC)
   - Base fields (level, logger, message)
   - MDC inclusion (dt.trace_id, dt.span_id, etc.)
   - Structured arguments (keyValuePairs, logstashMarkers)
   - Stack trace filtering (ShortenedThrowableConverter)

4. **Rolling Policies**:
   - Time-based: `.%d{yyyy-MM-dd}.gz`
   - Max history: 7 days application, 30 days business
   - Total size cap: 1GB application, 2GB business

5. **Logger Routing**:
   - Business event loggers → BUSINESS_EVENTS appender
   - Root logger → APPLICATION_LOGS + CONSOLE appenders

### Step 4: Update Dependencies

Ensure `pom.xml` includes required dependency:

```xml
<dependency>
  <groupId>net.logstash.logback</groupId>
  <artifactId>logstash-logback-encoder</artifactId>
  <version>${logstash-logback-encoder.version}</version>
</dependency>
```

Check parent POM for dependency management.

### Step 5: Generate Configuration Summary

Create summary document with:

- Configuration phase (Phase 1, 2, or 3)
- Profiles configured
- File paths for each appender
- Retention policies
- Stack trace exclusion patterns
- Business event logger names
- Next steps (testing, deployment)

## logback-spring.xml Template (Phase 1)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  ~ © 2026 by Intellectual Reserve, Inc. All rights reserved.
  ~
  ~ Logback configuration for {APPLICATION_NAME} structured logging migration
  ~ Phase 1: Structured JSON to Splunk
  ~
  ~ Reference: FamilySearch Observability Standards
  ~ https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
  -->
<configuration>

    <!-- =====================================================
         LOCAL PROFILE: Human-readable console + optional JSON verification
         ===================================================== -->
    <springProfile name="local">
        <!-- Console appender: Human-readable pattern for development -->
        <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
            <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
                <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %X{asyncToken} [%logger{0}] %msg%n%ex</pattern>
            </encoder>
        </appender>

        <!-- Optional JSON file for local verification (commented by default) -->
        <!-- Uncomment to enable JSON output verification locally -->
        <!--
        <appender name="LOCAL_JSON_VERIFY" class="ch.qos.logback.core.FileAppender">
            <file>target/local-app.json</file>
            <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
                <providers>
                    <timestamp>
                        <pattern>yyyy-MM-dd'T'HH:mm:ss.SSSXXX</pattern>
                        <timeZone>UTC</timeZone>
                    </timestamp>
                    <pattern>
                        <pattern>
                            {
                                "level": "%level",
                                "logger": "%logger",
                                "message": "%message"
                            }
                        </pattern>
                    </pattern>
                    <mdc />
                    <keyValuePairs />
                    <logstashMarkers />
                    <stackTrace>
                        <throwableConverter class="net.logstash.logback.stacktrace.ShortenedThrowableConverter">
                            <rootCauseFirst>true</rootCauseFirst>
                            <shortenedClassNameLength>20</shortenedClassNameLength>
                            <exclude>{STACK_TRACE_EXCLUSIONS}</exclude>
                        </throwableConverter>
                    </stackTrace>
                </providers>
            </encoder>
        </appender>
        -->

        <root level="INFO">
            <appender-ref ref="CONSOLE" />
            <!-- Uncomment to enable local JSON verification -->
            <!-- <appender-ref ref="LOCAL_JSON_VERIFY" /> -->
        </root>
    </springProfile>

    <!-- =====================================================
         PRODUCTION/STAGING/INTEG PROFILES: JSON to Splunk (Phase 1)
         ===================================================== -->
    <springProfile name="production,staging,integ,canary">
        <!-- Console appender: Pattern layout for Kubernetes log aggregation -->
        <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
            <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
                <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%logger{0}] %msg%n%ex</pattern>
            </encoder>
        </appender>

        <!-- Application logs: JSON for Splunk (Phase 1) -->
        <appender name="APPLICATION_LOGS" class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>/var/log/fs/app.json</file>
            <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
                <providers>
                    <!-- Timestamp in ISO 8601 format with milliseconds -->
                    <timestamp>
                        <pattern>yyyy-MM-dd'T'HH:mm:ss.SSSXXX</pattern>
                        <timeZone>UTC</timeZone>
                    </timestamp>
                    <!-- Base log fields -->
                    <pattern>
                        <pattern>
                            {
                                "level": "%level",
                                "logger": "%logger",
                                "message": "%message"
                            }
                        </pattern>
                    </pattern>
                    <!-- Include MDC (Mapped Diagnostic Context) -->
                    <!-- This automatically includes dt.trace_id, dt.span_id, asyncToken, etc. -->
                    <mdc />
                    <!-- Include structured arguments from fluent API -->
                    <keyValuePairs />
                    <!-- Include logstash markers -->
                    <logstashMarkers />
                    <!-- Stack traces with filtering per FamilySearch Observability Standards -->
                    <stackTrace>
                        <throwableConverter class="net.logstash.logback.stacktrace.ShortenedThrowableConverter">
                            <rootCauseFirst>true</rootCauseFirst>
                            <shortenedClassNameLength>20</shortenedClassNameLength>
                            <!-- Exclude low-value frames per standards -->
                            <exclude>{STACK_TRACE_EXCLUSIONS}</exclude>
                        </throwableConverter>
                    </stackTrace>
                </providers>
            </encoder>
            <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
                <fileNamePattern>/var/log/fs/app.json.%d{yyyy-MM-dd}.gz</fileNamePattern>
                <maxHistory>7</maxHistory>
                <totalSizeCap>1GB</totalSizeCap>
            </rollingPolicy>
        </appender>

        <!-- Business events: Separate JSON file for future S3/Databricks routing -->
        <appender name="BUSINESS_EVENTS" class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>/var/log/fs/business-events.json</file>
            <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
                <providers>
                    <timestamp>
                        <pattern>yyyy-MM-dd'T'HH:mm:ss.SSSXXX</pattern>
                        <timeZone>UTC</timeZone>
                    </timestamp>
                    <pattern>
                        <pattern>
                            {
                                "level": "%level",
                                "logger": "%logger",
                                "message": "%message"
                            }
                        </pattern>
                    </pattern>
                    <mdc />
                    <keyValuePairs />
                    <logstashMarkers />
                </providers>
            </encoder>
            <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
                <fileNamePattern>/var/log/fs/business-events.json.%d{yyyy-MM-dd}.gz</fileNamePattern>
                <!-- Longer retention for business events -->
                <maxHistory>30</maxHistory>
                <totalSizeCap>2GB</totalSizeCap>
            </rollingPolicy>
        </appender>

        <!-- Route business events to separate appender -->
        <!-- Named logger pattern: {BusinessEventClassName}.metricsReport -->
        {BUSINESS_EVENT_LOGGER_ROUTING}

        <!-- All other application logs -->
        <root level="INFO">
            <appender-ref ref="CONSOLE" />
            <appender-ref ref="APPLICATION_LOGS" />
        </root>
    </springProfile>

    <!-- =====================================================
         FUTURE: Phase 2 - Add Dynatrace appender here
         Uncomment when ready for dual ingestion (Splunk + Dynatrace)
         ===================================================== -->
    <!--
    <springProfile name="production,staging,integ,canary">
        <appender name="DYNATRACE_APP" class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>/var/log/fs-log/app.json</file>
            <encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
                <providers>
                    <timestamp>
                        <pattern>yyyy-MM-dd'T'HH:mm:ss.SSSXXX</pattern>
                        <timeZone>UTC</timeZone>
                    </timestamp>
                    <pattern>
                        <pattern>
                            {
                                "level": "%level",
                                "logger": "%logger",
                                "message": "%message"
                            }
                        </pattern>
                    </pattern>
                    <mdc />
                    <keyValuePairs />
                    <logstashMarkers />
                    <stackTrace>
                        <throwableConverter class="net.logstash.logback.stacktrace.ShortenedThrowableConverter">
                            <rootCauseFirst>true</rootCauseFirst>
                            <shortenedClassNameLength>20</shortenedClassNameLength>
                            <exclude>{STACK_TRACE_EXCLUSIONS}</exclude>
                        </throwableConverter>
                    </stackTrace>
                </providers>
            </encoder>
            <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
                <fileNamePattern>/var/log/fs-log/app.json.%d{yyyy-MM-dd}.gz</fileNamePattern>
                <maxHistory>7</maxHistory>
                <totalSizeCap>1GB</totalSizeCap>
            </rollingPolicy>
        </appender>

        <root level="INFO">
            <appender-ref ref="CONSOLE" />
            <appender-ref ref="APPLICATION_LOGS" />
            <appender-ref ref="DYNATRACE_APP" />
        </root>
    </springProfile>
    -->

</configuration>
```

## Template Variables

The skill replaces these placeholders when generating configuration:

- `{APPLICATION_NAME}`: Application name from POM or user input
- `{STACK_TRACE_EXCLUSIONS}`: Regex pattern for filtering stack traces
- `{BUSINESS_EVENT_LOGGER_ROUTING}`: Logger declarations for business events

### Default Stack Trace Exclusions

```
(com\.dynatrace|reactor\.core\.publisher|io\.netty\.channel\.Abstract|org\.springframework\.security\.web\.Observation|org\.apache\.catalina\.core\.ApplicationFilterChain|org\.springframework\.web\.filter\.OncePerRequestFilter)
```

**Customize based on project**: Add organization-specific packages to exclude noisy frames.

### Business Event Logger Routing Example

```xml
<!-- Route business events to separate appender -->
<logger name="org.familysearch.gofr.service.metrics.CounterMetricsListeners.metricsReport"
        level="INFO"
        additivity="false">
    <appender-ref ref="BUSINESS_EVENTS" />
</logger>
```

**Pattern Detection**: Scan for `Logger logger = LogManager.getLogger({ClassName}.class.getName() + ".metricsReport")` or similar patterns.

## Phase 2 Configuration (Dual Destination)

When ready to add Dynatrace:

1. **Uncomment Phase 2 section** in generated logback-spring.xml
2. **Verify both appenders** write to correct paths:
   - Splunk: `/var/log/fs/app.json`
   - Dynatrace: `/var/log/fs-log/app.json`
3. **Monitor disk usage** (dual files = ~2x storage during migration)
4. **Validate both systems** ingest structured JSON correctly

## Phase 3 Configuration (Dynatrace Only)

When decommissioning Splunk:

1. **Remove Splunk appender** (`APPLICATION_LOGS` writing to `/var/log/fs/app.json`)
2. **Keep only Dynatrace appender** (`DYNATRACE_APP` writing to `/var/log/fs-log/app.json`)
3. **Update business events path** (optional): Move to `/var/log/fs-log/business-events.json` if routing to Dynatrace
4. **Clean up file references** in deployment scripts

## Local Development Verification

### Option 1: Console Only (Default)

Human-readable pattern output to console. Good for daily development.

### Option 2: Console + JSON Verification

Uncomment `LOCAL_JSON_VERIFY` appender to write JSON to `target/local-app.json`. Use this to:

1. **Verify JSON structure** before deploying to environment
2. **Test structured fields** appear correctly
3. **Validate MDC propagation** (trace IDs, span IDs)
4. **Check stack trace filtering** works as expected

**Testing workflow**:
```bash
# 1. Start application locally
mvn spring-boot:run

# 2. Exercise features that log
# 3. Inspect JSON output
cat target/local-app.json | jq .
```

## Validation Checklist

After generating logback-spring.xml, verify:

- [ ] File saved to `src/main/resources/logback-spring.xml`
- [ ] Dependency `logstash-logback-encoder` present in POM
- [ ] Profile sections for local and deployed environments
- [ ] Console appender uses pattern layout (not JSON)
- [ ] JSON appenders use LoggingEventCompositeJsonEncoder
- [ ] Timestamp in ISO 8601 UTC format
- [ ] MDC, keyValuePairs, logstashMarkers included
- [ ] Stack trace filtering configured
- [ ] Rolling policies with compression (.gz)
- [ ] Business event loggers routed to separate file
- [ ] Phase 2 configuration present but commented
- [ ] File paths correct for Splunk/Dynatrace

## Testing the Configuration

### Unit Test: Verify JSON Structure

```java
@Test
void shouldProduceValidJsonLogs() throws Exception {
    // Given
    Logger logger = LoggerFactory.getLogger(getClass());
    
    // When
    logger.atInfo()
        .addKeyValue("person.id", "TEST123")
        .addKeyValue("event.name", "test.event")
        .log("Test message");
    
    // Then
    // Read target/local-app.json (if verification appender enabled)
    // Parse JSON and verify structure
    Path logFile = Paths.get("target/local-app.json");
    String lastLine = Files.readAllLines(logFile).getLast();
    
    JsonNode json = new ObjectMapper().readTree(lastLine);
    assertThat(json.get("level").asText()).isEqualTo("INFO");
    assertThat(json.get("person.id").asText()).isEqualTo("TEST123");
    assertThat(json.get("event.name").asText()).isEqualTo("test.event");
    assertThat(json.get("message").asText()).isEqualTo("Test message");
}
```

### Integration Test: Verify Appender Routing

```java
@SpringBootTest
@ActiveProfiles("production")
class LogbackConfigurationIT {
    
    @Test
    void shouldRouteBusinessEventsToSeparateFile() {
        // Given
        Logger businessLogger = LogManager.getLogger(
            "org.familysearch.gofr.service.metrics.CounterMetricsListeners.metricsReport");
        
        // When
        businessLogger.atInfo()
            .addKeyValue("event.name", "business.metric")
            .log("Business event");
        
        // Then
        // Verify /var/log/fs/business-events.json contains event
        // Verify /var/log/fs/app.json does NOT contain event (additivity=false)
    }
}
```

## Common Issues and Solutions

### Issue 1: "NoClassDefFoundError: LoggingEventCompositeJsonEncoder"

**Cause**: Missing logstash-logback-encoder dependency

**Solution**: Add to POM:
```xml
<dependency>
  <groupId>net.logstash.logback</groupId>
  <artifactId>logstash-logback-encoder</artifactId>
</dependency>
```

### Issue 2: Structured fields not appearing in JSON

**Cause**: Using traditional parameterized logging instead of fluent API

**Solution**: Convert to fluent API with `addKeyValue()`:
```java
// ❌ Traditional (won't work)
logger.info("value={}", value);

// ✅ Fluent API (works)
logger.atInfo()
    .addKeyValue("key", value)
    .log("Message");
```

### Issue 3: MDC fields (dt.trace_id) missing

**Cause**: MDC not configured or async context not propagated

**Solution**: Verify:
- Dynatrace OneAgent installed (auto-adds trace IDs to MDC)
- Async tasks use proper context propagation (TaskDecorator)
- MDC included in encoder: `<mdc />`

### Issue 4: Logs not rotating

**Cause**: Incorrect rolling policy configuration or file permissions

**Solution**: Verify:
- TimeBasedRollingPolicy configured with fileNamePattern
- Directory `/var/log/fs/` exists and is writable
- Pattern includes date: `.%d{yyyy-MM-dd}.gz`

### Issue 5: Duplicate logs (both console and file in production)

**Cause**: Both console and file appenders active

**Expected**: This is correct behavior. Console for k8s log aggregation, files for Splunk/Dynatrace.

## Output Summary Document

After generating configuration, create `setup-logback-summary.md`:

```markdown
# Logback Configuration Summary

**Application**: {APPLICATION_NAME}
**Date**: 2026-05-04
**Phase**: Phase 1 (Structured JSON to Splunk)

## Configuration Generated

- **File**: `src/main/resources/logback-spring.xml`
- **Dependency**: `net.logstash.logback:logstash-logback-encoder:8.0`

## Profiles Configured

### Local Profile (`local`)
- **Console**: Human-readable pattern with MDC (asyncToken)
- **JSON Verification**: Optional file at `target/local-app.json` (commented by default)

### Deployed Profiles (`production`, `staging`, `integ`, `canary`)
- **Console**: Pattern layout for Kubernetes
- **Application Logs**: JSON file at `/var/log/fs/app.json`
- **Business Events**: JSON file at `/var/log/fs/business-events.json`

## File Paths

| Environment | Application Logs | Business Events |
|-------------|------------------|-----------------|
| Local | Console only | Console only |
| Production | /var/log/fs/app.json | /var/log/fs/business-events.json |

## Retention Policies

- **Application Logs**: 7 days, 1GB max
- **Business Events**: 30 days, 2GB max
- **Compression**: Enabled (.gz)

## Stack Trace Filtering

Excluded packages: `com.dynatrace`, `reactor.core.publisher`, `io.netty.channel.Abstract`, `org.springframework.security.web.Observation`, `org.apache.catalina.core.ApplicationFilterChain`, `org.springframework.web.filter.OncePerRequestFilter`

## Business Event Loggers

{LIST_OF_BUSINESS_EVENT_LOGGER_NAMES}

## Next Steps

1. **Verify Dependency**: Check `pom.xml` includes `logstash-logback-encoder`
2. **Test Locally**: Run application with `local` profile, verify console output
3. **Enable JSON Verification** (optional): Uncomment `LOCAL_JSON_VERIFY` appender
4. **Review Configuration**: Inspect generated `logback-spring.xml` for correctness
5. **Commit Changes**: Add configuration to version control
6. **Deploy to Integ**: Test with `integ` profile first
7. **Validate Splunk Ingestion**: Verify JSON appears in Splunk with correct structure

## Phase 2 Preparation

When ready to add Dynatrace:
1. Uncomment Phase 2 section in `logback-spring.xml`
2. Verify Dynatrace OneAgent installed on target hosts
3. Confirm `/var/log/fs-log/` directory exists and is monitored by OneAgent
4. Deploy and validate dual ingestion

## References

- **FamilySearch Observability Standards**: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
- **Logstash Encoder Documentation**: https://github.com/logfellow/logstash-logback-encoder
- **Spring Boot Logging**: https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.logging
```

## Best Practices

1. **Always detect existing configuration first** - never blindly overwrite
2. **Preserve custom appenders and loggers** when enhancing existing config
3. **Always generate commented Phase 2 section** even when configuring Phase 1 - makes transition easier
4. **Keep console appender pattern-based** (not JSON) for Kubernetes log aggregation
5. **Use time-based rolling with compression** to save disk space
6. **Separate business events early** even if routing to same destination initially
7. **Test locally with JSON verification** before deploying to environment
8. **Document stack trace exclusions** specific to your application
9. **When migrating from logback.xml** - create logback-spring.xml, leave old file with deprecation comment
10. **Backup existing configuration** before making changes (git commit or copy to .bak file)

## References

- **FamilySearch Observability Standards**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **Logstash Logback Encoder**: https://github.com/logfellow/logstash-logback-encoder
- **Spring Boot Logging**: https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.logging
- **Logback Manual**: https://logback.qos.ch/manual/

---

**Remember**: The configuration should be flexible enough to support all three phases without major rewrites - just commenting/uncommenting sections.
