# Splunk-to-Dynatrace Migration Plugin

A comprehensive plugin for migrating Spring Boot applications from Splunk to Dynatrace observability, with structured JSON logging and compliance with FamilySearch Observability Standards.

## Overview

This plugin provides skills to help teams migrate from traditional Splunk logging to Dynatrace observability using structured JSON logging. It automates the analysis, conversion, and validation of log statements while ensuring compliance with [FamilySearch Observability Standards](https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards).

## Migration Strategy

The plugin supports a phased approach:

1. **Phase 1-2**: Convert logs to structured format and deploy to Splunk
2. **Phase 3-4**: Update Splunk dashboards to use JSON fields
3. **Phase 5**: Add Dynatrace (dual ingestion with separate files)
4. **Phase 6**: Cut over to Dynatrace only

## Skills in This Plugin

### `/splunk-to-dynatrace:analyze`
Analyzes current logging patterns and generates compliance reports against FamilySearch Observability Standards.

**Capabilities:**
- Scans codebase for all log statements (SLF4J, Log4j, Lombok)
- Evaluates against FamilySearch Observability Standards (decision trees, field requirements)
- Identifies DELETE candidates (logs Dynatrace auto-captures)
- Detects incorrect log levels (INFO → DEBUG, etc.)
- Suggests METRIC conversions (counters, timers)
- Identifies business events vs application logs
- Analyzes field naming trade-offs (three strategies)
- Generates hierarchical reports with progressive disclosure
- Adapts to codebase size (<100, 100-500, 500+ logs)

**Outputs:**
- `00-executive-summary.md` (overall statistics, priorities)
- `01-quick-wins.md` (top 30 deletion/conversion candidates)
- `02-metrics-conversion.md` (logs to convert to metrics)
- `03-level-corrections-summary.md` (log level violations)
- `04-business-events.md` (business event separation plan)
- `05-field-naming-analysis.md` (field naming trade-off assessment)
- `modules/{module-name}/` (per-module detailed reports)

**Use when**: Starting migration, auditing existing logs, checking standards compliance

---

### `/splunk-to-dynatrace:convert-logs`
Converts traditional log statements to SLF4J fluent API with structured arguments per observability standards.

**Capabilities:**
- Converts to SLF4J fluent API with `addKeyValue()` structured fields
- Applies log level corrections per FamilySearch decision tree
- Deletes logs Dynatrace auto-captures (with explanation comments)
- Converts counter/timing logs to Micrometer metrics
- Handles exception logging with `setCause()` method
- Adds lambda wrapping for expensive operations
- Adds guard clauses for performance-critical paths
- Supports three field naming strategies (standardize, defer, hybrid)
- Incremental conversion (full codebase, module-by-module, task-by-task)
- Preserves original logs as comments for review

**Field Naming Options:**
1. **Standardize Now** (dot.notation): Clean field names, breaks Splunk dashboards initially
2. **Defer Standardization** (preserve names): Dashboards keep working, refactor later
3. **Hybrid Approach** (dual fields): Both old and new names, higher log volume temporarily

**Conversion Actions:**
- **CONVERTED**: Traditional → structured fluent API
- **DELETE**: Dynatrace auto-captures, no value (commented with explanation)
- **METRIC**: Counter/timer replacement with Micrometer
- **LEVEL_CHANGE**: Correct log level per standards

**Outputs:**
- Modified Java files with converted logs
- `conversion-summary-{task}.md` (statistics, files modified, next steps)

**Use when**: Refactoring log statements, applying standards-based transformations, incremental migration

---

### `/splunk-to-dynatrace:setup-logback`
Generates logback-spring.xml configuration for structured JSON logging with profile-based appenders.

**Capabilities:**
- Detects current configuration (logback.xml, application.properties)
- Generates logback-spring.xml with profile-based appenders
- Configures JSON encoder (LoggingEventCompositeJsonEncoder)
- Sets up business event routing (named logger → separate file)
- Configures rolling policies (time-based, compressed)
- Adds stack trace filtering per observability standards
- Supports phased migration (Splunk → Dual → Dynatrace)
- Updates POM dependencies (logstash-logback-encoder)

**Configuration Phases:**
- **Phase 1**: Structured JSON to Splunk only (`/var/log/fs/app.json`)
- **Phase 2**: Dual destination (`/var/log/fs/app.json` + `/var/log/fs-log/app.json`)
- **Phase 3**: Dynatrace only (`/var/log/fs-log/app.json`)

**Profiles:**
- **Local**: Human-readable console + optional JSON verification to `target/local-app.json`
- **Production/Staging/Integ/Canary**: JSON file appenders for Splunk/Dynatrace

**Outputs:**
- `src/main/resources/logback-spring.xml` (complete configuration)
- Updated `pom.xml` (logstash-logback-encoder dependency)
- `setup-logback-summary.md` (configuration details, next steps)

**Use when**: Setting up logging infrastructure, configuring appenders for different environments, transitioning between phases

---

### `/splunk-to-dynatrace:validate-dashboards`
Validates Splunk dashboards work with structured logging and generates Dynatrace equivalents.

**Capabilities:**
- Parses Splunk dashboard definitions (JSON, XML, saved searches)
- Extracts field references from SPL queries (filters, aggregations, displays)
- Validates field mappings against structured logging field names
- Assesses breakage risk (green: preserved, yellow: renamed, red: removed)
- Generates required dashboard updates (find/replace, query rewrites)
- Converts SPL queries to Dynatrace DQL equivalents
- Creates Dynatrace dashboard JSON for import

**SPL to DQL Translation:**
- Search/filter: `index=... field=value` → `fetch logs | filter field == value`
- Aggregation: `stats count by field` → `summarize count(), by:{field}`
- Time series: `timechart count` → `summarize count(), by:{bin(timestamp, 5m)}`
- Calculated fields: `eval new=expr` → `fields new = expr`
- Top values: `top 10 field` → `summarize count(), by:{field} | sort count desc | limit 10`

**Validation Report Includes:**
- Dashboard inventory (name, owner, panels, risk level)
- Per-panel field reference analysis
- Breakage risk assessment with color coding
- Required updates per dashboard (find/replace operations)
- Dynatrace DQL query equivalents
- Migration checklist per dashboard

**Outputs:**
- `dashboard-validation-report.md` (comprehensive validation results)
- Dynatrace dashboard JSON templates (ready to import)

**Use when**: Migrating dashboards, validating field mappings, preventing dashboard breakage during migration

---

### `/splunk-to-dynatrace:migrate`
Orchestrates the full migration process from analysis through deployment.

**Capabilities:**
- Orchestrates all plugin skills in phased workflow
- Creates and manages migration task list
- Provides approval gates between major phases
- Generates deployment checklists per phase
- Tracks progress with task status updates
- Handles errors and rollback scenarios
- Produces final migration report

**Orchestration Modes:**
1. **Full Automated**: All phases sequentially (small codebases)
2. **Module-by-Module**: Incremental per module (multi-module apps)
3. **Task-by-Task**: Small chunks with review (large/critical apps)

**Migration Phases:**
- **Phase 0**: Discovery & Planning (analyze, confirm approach)
- **Phase 1**: Convert to Structured JSON (convert-logs skill)
- **Phase 2**: Configure & Deploy Splunk (setup-logback, local verification, deploy)
- **Phase 3**: Validate Dashboards (validate-dashboards, update dashboards)
- **Phase 4**: Add Dynatrace (dual ingestion, create Dynatrace dashboards)
- **Phase 5**: Cutover & Cleanup (Dynatrace-only, decommission Splunk)

**Approval Gates:**
- After analysis (confirm plan)
- After each conversion task (review changes)
- After integration deployment (validate logs)
- After dashboard updates (dashboard owners approve)
- After dual ingestion (validate Dynatrace)
- Before cutover (final approval)

**Deployment Checklists:**
- Pre-deployment validation (tests, reviews, dependencies)
- Deployment steps (build, deploy, verify)
- Post-deployment validation (logs, dashboards, monitoring)
- Rollback procedures (if issues detected)

**Outputs:**
- Migration task list with dependencies
- Phase summary reports
- Environment-specific deployment checklists
- Final migration report (metrics, timeline, lessons learned)

**Use when**: Executing complete end-to-end migration, coordinating multi-team migration, tracking migration progress

## Key Features

- **Standards-based transformation** using FamilySearch Observability Standards
- **Automated compliance checking** with objective criteria
- **Business event separation** for future S3/Databricks routing
- **Log level recommendations** per decision tree (ERROR, WARN, INFO, DEBUG, TRACE)
- **Deletion recommendations** for logs Dynatrace auto-captures
- **Metric conversion** for counters and timing logs
- **Field naming flexibility** (three strategies: standardize, defer, hybrid)
- **Performance optimizations** (lambda wrapping, guard clauses)
- **Incremental conversion** (full, module-by-module, task-by-task)
- **Dashboard validation** (SPL to DQL conversion, breakage risk assessment)
- **Phased rollout** (Splunk → Dual → Dynatrace with approval gates)
- **Task management** (progress tracking, dependencies, approval gates)
- **Deployment checklists** (per phase, per environment)

## Benefits

1. **Validate structured format with Splunk first** (known quantity, lower risk)
2. **Update dashboards incrementally** (Splunk first, then Dynatrace)
3. **Single code conversion** (not dual-format maintenance)
4. **Clear migration path** (Splunk JSON → Both → Dynatrace only)
5. **Automated compliance** (objective criteria from standards)
6. **Reusable across teams** (standardized approach)

## File Structure

```
/var/log/fs/app.json              → Splunk forwarder (Phase 1-5)
/var/log/fs-log/app.json          → Dynatrace OneAgent (Phase 5+)
/var/log/fs/business-events.json  → Business events (eventual S3/Databricks)
```

## Requirements

- Spring Boot with SLF4J and Logback
- Maven or Gradle build system
- Java 11+ (for SLF4J fluent API)
- Access to FamilySearch Observability Standards
- `net.logstash.logback:logstash-logback-encoder` dependency (v8.0+)
- Micrometer (for metric conversions, usually included with Spring Boot Actuator)

## Usage Examples

### Example 1: Full Migration (Small Codebase)

```bash
# Invoke migrate skill with full automated mode
/splunk-to-dynatrace:migrate

# Skill will:
# 1. Run analyze skill → generate reports
# 2. Ask for field naming strategy (Option 1, 2, or 3)
# 3. Convert all logs to structured format
# 4. Setup logback configuration (Phase 1)
# 5. Validate dashboards
# 6. Generate deployment checklists
# 7. Wait for user approval between phases
```

### Example 2: Analyze Only (Audit Current State)

```bash
# Just run analysis to understand current logging
/splunk-to-dynatrace:analyze

# Generates reports in workspace:
# - 00-executive-summary.md
# - 01-quick-wins.md (top deletion candidates)
# - 02-metrics-conversion.md
# - 03-level-corrections-summary.md
# - 04-business-events.md
# - 05-field-naming-analysis.md
# - modules/{module-name}/ (detailed per-module)
```

### Example 3: Incremental Conversion (Module-by-Module)

```bash
# Run migrate skill with module-by-module approach
/splunk-to-dynatrace:migrate

# Choose: Module-by-Module mode
# Skill creates tasks:
# - Task: Convert logs in gofr-service module
# - Task: Test gofr-service module
# - Task: Convert logs in gofr-ws module
# - Task: Test gofr-ws module
# - Task: Setup logback configuration
# - ... (continues through all phases)
```

### Example 4: Convert Specific Task (Large Codebase)

```bash
# Run convert-logs skill directly with specific scope
/splunk-to-dynatrace:convert-logs

# Specify task: "Convert all ERROR-level logs in gofr-service module"
# Skill will:
# 1. Load analyze report for gofr-service
# 2. Filter for ERROR-level logs
# 3. Convert only those logs
# 4. Generate conversion summary
```

### Example 5: Dashboard Validation Only

```bash
# Just validate dashboards (assumes structured logging already deployed)
/splunk-to-dynatrace:validate-dashboards

# Provide: Splunk dashboard export files (JSON/XML)
# Skill generates:
# - Dashboard validation report
# - Required updates (find/replace)
# - Dynatrace DQL equivalents
```

### Example 6: Setup Logback Only

```bash
# Generate logback configuration independently
/splunk-to-dynatrace:setup-logback

# Choose: Phase 1 (Splunk only)
# Skill generates:
# - src/main/resources/logback-spring.xml
# - Updates pom.xml with dependency
# - setup-logback-summary.md
```

## References

- **FamilySearch Observability Standards**: [Confluence Page](https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards)
- **Logstash Logback Encoder**: [GitHub](https://github.com/logfellow/logstash-logback-encoder)
- **SLF4J Fluent API**: [SLF4J Manual](https://www.slf4j.org/manual.html)

## Version

1.0.0 - Initial release

## Author

FamilySearch Engineering - SATORIS Team

## License

© 2026 by Intellectual Reserve, Inc. All rights reserved.
