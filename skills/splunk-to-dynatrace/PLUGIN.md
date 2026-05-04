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

**Use when**: Starting migration, auditing existing logs, checking standards compliance

### `/splunk-to-dynatrace:convert-logs`
Converts traditional log statements to SLF4J fluent API with structured arguments per observability standards.

**Use when**: Refactoring log statements, applying standards-based transformations

### `/splunk-to-dynatrace:setup-logback`
Generates logback-spring.xml configuration for structured JSON logging with profile-based appenders.

**Use when**: Setting up logging infrastructure, configuring appenders for different environments

### `/splunk-to-dynatrace:validate-dashboards`
Validates Splunk dashboards work with structured logging and generates Dynatrace equivalents.

**Use when**: Migrating dashboards, validating field mappings

### `/splunk-to-dynatrace:migrate`
Orchestrates the full migration process from analysis through deployment.

**Use when**: Executing complete end-to-end migration

## Key Features

- **Standards-based transformation** using FamilySearch Observability Standards
- **Automated compliance checking** with objective criteria
- **Business event separation** for future S3/Databricks routing
- **Log level recommendations** per decision tree (ERROR, WARN, INFO, DEBUG, TRACE)
- **Deletion recommendations** for logs Dynatrace auto-captures
- **Metric conversion** for counters and timing logs
- **Field naming standardization** (dot.notation, snake_case)

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
- Access to FamilySearch Observability Standards
- `net.logstash.logback:logstash-logback-encoder` dependency

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
