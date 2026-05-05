---
name: splunk-to-dynatrace:migrate
description: Orchestrates the complete Splunk-to-Dynatrace migration workflow. Coordinates all plugin skills (analyze, convert-logs, setup-logback, validate-dashboards) with task management, user approval gates, and deployment checklists. Use this skill for end-to-end migration execution with phased rollout and validation.
---

# Migrate Skill

Orchestrates the complete end-to-end migration from Splunk to Dynatrace observability using structured JSON logging. Coordinates all skills in the plugin with task-based workflow, approval gates, and comprehensive validation.

## When to Use This Skill

- Executing complete Splunk-to-Dynatrace migration from start to finish
- Coordinating multiple migration activities across modules
- Managing phased rollout with validation gates
- Tracking migration progress with task management
- Generating deployment checklists and runbooks

## Migration Workflow Overview

```
┌─────────────┐
│   Phase 0   │ Discovery & Planning
│   Analyze   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 1   │ Convert to Structured JSON (Splunk Only)
│   Convert   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 2   │ Configure & Deploy
│   Setup     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 3   │ Validate Dashboards
│  Validate   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 4   │ Add Dynatrace (Dual Ingestion)
│  Dynatrace  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Phase 5   │ Cutover & Cleanup
│   Complete  │
└─────────────┘
```

## Orchestration Modes

### Mode 1: Full Automated Migration

Execute all phases sequentially with approval gates between major phases.

**Use when:**
- Small codebase (<100 log statements)
- Single-module application
- Confidence in automated transformations
- Strong test coverage

### Mode 2: Incremental Module-by-Module

Execute migration one module at a time with validation between modules.

**Use when:**
- Multi-module codebase
- Want to minimize risk
- Phased deployment preferred
- Different modules owned by different teams

### Mode 3: Task-by-Task Conversion

Execute migration in small task-based chunks with manual review between tasks.

**Use when:**
- Large codebase (500+ log statements)
- High risk or critical application
- Want maximum control
- Learning process for team

## Skill Workflow

### Phase 0: Discovery & Planning

**Objective**: Understand current state and create migration plan

#### Step 0.1: Run Analysis

Invoke `splunk-to-dynatrace:analyze` skill:

```
Input: Codebase path (current working directory or specified path)
Output: Analysis reports in workspace
```

**What this produces:**
- `00-executive-summary.md` (overall statistics and priorities)
- `01-quick-wins.md` (top deletion/conversion candidates)
- `02-metrics-conversion.md` (logs that should become metrics)
- `03-level-corrections-summary.md` (log level violations)
- `04-business-events.md` (business event separation plan)
- `05-field-naming-analysis.md` (field naming trade-off assessment)
- Module-specific detailed reports

#### Step 0.2: Present Analysis to User

Show executive summary and ask user to confirm understanding:

1. **Total scope**: X log statements across Y modules
2. **Quick wins**: Z logs to delete (Dynatrace auto-captures)
3. **Metrics conversions**: N logs to convert to metrics
4. **Level corrections**: M logs with incorrect levels
5. **Field naming decision**: Which strategy (Option 1, 2, or 3)?

#### Step 0.3: Confirm Migration Approach

Ask user to choose:

1. **Orchestration Mode**: Full automated, module-by-module, or task-by-task
2. **Field Naming Strategy**: Standardize now (Option 1), defer (Option 2), or hybrid (Option 3)
3. **Performance Optimizations**: Lambda wrapping, guard clauses where needed?
4. **Scope**: All modules or specific subset?

#### Step 0.4: Create Migration Plan

Generate task list based on chosen mode and scope:

**Full Automated Mode**:
- Task: Convert all logs to structured format
- Task: Setup logback configuration
- Task: Validate dashboards
- Task: Deploy to integration environment
- Task: Add Dynatrace configuration
- Task: Cutover to Dynatrace

**Module-by-Module Mode** (example: gofr):
- Task: Convert logs in gofr-service module
- Task: Test gofr-service module
- Task: Convert logs in gofr-ws module
- Task: Test gofr-ws module
- Task: Setup logback configuration
- Task: Validate dashboards
- Task: Deploy Phase 1 to integration
- ...

**Task-by-Task Mode** (example: gofr):
- Task: Convert ERROR-level logs across all modules
- Task: Convert DELETE candidates (Dynatrace auto-captures)
- Task: Convert business event logs
- Task: Convert remaining INFO logs in gofr-service
- Task: Convert remaining INFO logs in gofr-ws
- ...

Present plan to user for approval.

### Phase 1: Convert to Structured JSON

**Objective**: Convert log statements to SLF4J fluent API with structured arguments

#### Step 1.1: Execute Conversions

Invoke `splunk-to-dynatrace:convert-logs` skill according to plan:

**For each task in conversion plan:**
1. Identify logs matching task scope
2. Load context (analyze reports, observability standards)
3. Apply conversions (structured fields, level corrections, deletions, metrics)
4. Generate conversion summary
5. Mark task complete

**Output per task:**
- Modified Java files with converted logs
- `conversion-summary-{task}.md` report

#### Step 1.2: Validation After Each Task

After each conversion task:

1. **Compile**: Run `mvn clean compile -pl {module}`
2. **Test**: Run `mvn test -pl {module}`
3. **Fix Test Failures**: Update tests checking log output
4. **Review Changes**: Inspect modified files
5. **Commit**: Create feature branch commit

**Approval Gate**: User reviews and approves before next task.

#### Step 1.3: Aggregate Conversion Summary

After all conversion tasks complete:

Generate overall summary:
- Total logs converted, deleted, changed levels, converted to metrics
- Breakdown by module
- All files modified
- Test results (pass/fail)

### Phase 2: Configure & Deploy

**Objective**: Setup logback configuration and deploy to Splunk (Phase 1)

#### Step 2.1: Generate Logback Configuration

Invoke `splunk-to-dynatrace:setup-logback` skill:

```
Input: 
- Current configuration (application.properties)
- Business event logger names (from analyze)
- Phase: Phase 1 (Splunk only)
- Field naming strategy (from Phase 0)

Output:
- src/main/resources/logback-spring.xml
- Updated pom.xml (dependency)
- setup-logback-summary.md
```

#### Step 2.2: Local Verification

Test locally with JSON verification enabled:

1. **Enable verification appender**: Uncomment `LOCAL_JSON_VERIFY` in logback-spring.xml
2. **Run application**: `mvn spring-boot:run`
3. **Exercise features**: Trigger log statements
4. **Inspect JSON**: `cat target/local-app.json | jq .`
5. **Validate structure**: Check fields, MDC, timestamps, stack traces

**Checklist:**
- [ ] Valid JSON per line
- [ ] Structured fields present (`person.id`, `ordinance.type`, etc.)
- [ ] MDC fields included (`dt.trace_id`, `dt.span_id`)
- [ ] Timestamps in ISO 8601 UTC
- [ ] Stack traces filtered correctly
- [ ] Business events routed to separate file

#### Step 2.3: Deploy to Integration Environment

Deploy with Splunk JSON appender:

1. **Build**: `mvn clean install`
2. **Deploy**: Deploy to integration environment
3. **Verify files written**: Check `/var/log/fs/app.json` and `/var/log/fs/business-events.json` exist
4. **Verify Splunk ingestion**: Check Splunk receiving structured JSON
5. **Verify disk usage**: Monitor file sizes and rolling

**Approval Gate**: User confirms integration deployment successful.

### Phase 3: Validate Dashboards

**Objective**: Ensure Splunk dashboards work with new structured fields

#### Step 3.1: Validate Existing Dashboards

Invoke `splunk-to-dynatrace:validate-dashboards` skill:

```
Input:
- Splunk dashboard definitions (JSON/XML exports)
- Field naming mappings (from analyze)

Output:
- dashboard-validation-report.md
- Required dashboard updates (find/replace)
- Dynatrace DQL equivalents
```

#### Step 3.2: Update Splunk Dashboards

Apply required updates to Splunk dashboards:

1. **Low-risk updates**: Find/replace field names (e.g., `ordinanceType` → `ordinance.type`)
2. **High-risk updates**: Manual query rewrites for removed fields
3. **Test updated dashboards**: Verify correct data in Splunk (using integration logs)
4. **Get approval**: Dashboard owners confirm updates work

**Approval Gate**: Dashboard owners approve updated dashboards.

#### Step 3.3: Deploy Phase 1 Complete

Deploy to additional environments:

1. **Staging**: Deploy structured logging + updated dashboards
2. **Canary**: Deploy to canary instances
3. **Production**: Full production deployment

**Monitor for 1-2 weeks**: Ensure dashboards work correctly, logs volume acceptable, no issues.

### Phase 4: Add Dynatrace (Dual Ingestion)

**Objective**: Add Dynatrace appender for parallel ingestion

#### Step 4.1: Update Logback Configuration

Invoke `splunk-to-dynatrace:setup-logback` skill with Phase 2:

```
Input:
- Existing logback-spring.xml
- Phase: Phase 2 (Splunk + Dynatrace)

Output:
- Updated logback-spring.xml (Dynatrace appender uncommented)
- setup-logback-summary.md
```

**Changes:**
- Uncomment Phase 2 section in logback-spring.xml
- Adds Dynatrace appender writing to `/var/log/fs-log/app.json`
- Both Splunk and Dynatrace ingest simultaneously

#### Step 4.2: Verify Dynatrace Agent Installed

Check Dynatrace OneAgent status:

1. **Integration environment**: Verify OneAgent running
2. **File path monitored**: Confirm `/var/log/fs-log/app.json` monitored by OneAgent
3. **Test ingestion**: Check Dynatrace receives logs

#### Step 4.3: Create Dynatrace Dashboards

Use DQL equivalents from validate-dashboards skill:

1. **Create dashboard**: Use Dynatrace UI or API
2. **Import queries**: Copy DQL queries from validation report
3. **Test visualizations**: Verify charts show correct data
4. **Compare with Splunk**: Validate results match between systems

#### Step 4.4: Deploy Phase 2 to Environments

Deploy dual ingestion:

1. **Integration**: Deploy updated config, verify both Splunk and Dynatrace receive logs
2. **Staging**: Same verification
3. **Canary**: Limited production validation
4. **Production**: Full deployment

**Monitor 1-2 weeks**: Validate Dynatrace reliability, compare results with Splunk.

**Approval Gate**: User confirms Dynatrace working correctly.

### Phase 5: Cutover & Cleanup

**Objective**: Decommission Splunk, Dynatrace becomes primary observability

#### Step 5.1: Final Validation

Verify Dynatrace is ready to be primary:

- [ ] All dashboards migrated and validated
- [ ] Alerts configured in Dynatrace
- [ ] Team trained on Dynatrace queries (DQL)
- [ ] Runbooks updated to reference Dynatrace
- [ ] 1-2 weeks of parallel operation successful

#### Step 5.2: Remove Splunk Appender

Invoke `splunk-to-dynatrace:setup-logback` skill with Phase 3:

```
Input:
- Existing logback-spring.xml
- Phase: Phase 3 (Dynatrace only)

Output:
- Updated logback-spring.xml (Splunk appender removed)
- setup-logback-summary.md
```

**Changes:**
- Remove Splunk appender (APPLICATION_LOGS writing to `/var/log/fs/app.json`)
- Keep Dynatrace appender only
- Update business events path if routing to Dynatrace

#### Step 5.3: Deploy Phase 3 to Environments

Final deployment:

1. **Integration**: Deploy Dynatrace-only config
2. **Staging**: Verify Splunk no longer receiving logs
3. **Canary**: Limited production validation
4. **Production**: Full deployment

#### Step 5.4: Decommission Splunk Infrastructure

Work with infrastructure team:

- [ ] Stop Splunk forwarder on application hosts
- [ ] Remove `/var/log/fs/app.json` file monitoring
- [ ] Archive Splunk dashboards (don't delete immediately)
- [ ] Update documentation to reference Dynatrace
- [ ] Celebrate migration complete! 🎉

### Phase 6: Generate Final Report

Create comprehensive migration report:

```markdown
# Splunk-to-Dynatrace Migration Final Report

## Executive Summary

- **Application**: GOFR
- **Start Date**: 2026-04-01
- **Completion Date**: 2026-05-04
- **Total Duration**: 5 weeks

## Metrics

### Code Changes
- **Total Logs Converted**: 247
- **Logs Deleted** (Dynatrace auto-captures): 38
- **Logs Converted to Metrics**: 12
- **Log Levels Corrected**: 47
- **Files Modified**: 23
- **Modules Updated**: 3 (gofr-service, gofr-ws, gofr-acceptance)

### Log Volume Reduction
- **Before**: 450 MB/day
- **After**: 180 MB/day
- **Reduction**: 60%

### Dashboards
- **Splunk Dashboards Migrated**: 8
- **Dynatrace Dashboards Created**: 8
- **Dashboard Queries Updated**: 23

### Timeline
- **Phase 0** (Analysis): Week 1
- **Phase 1** (Conversion): Weeks 2-3
- **Phase 2** (Splunk Deploy): Week 3
- **Phase 3** (Dashboard Validation): Week 4
- **Phase 4** (Dynatrace Dual): Week 4-5
- **Phase 5** (Cutover): Week 5

## Lessons Learned

### What Went Well
1. Structured logging improved log clarity
2. Field naming standardization made Dynatrace queries easier
3. Business event separation prepared for future S3 routing
4. Incremental approach reduced risk

### Challenges
1. Some dashboards required manual query rewrites
2. Test updates needed for changed log output
3. Disk usage spike during Phase 4 (dual ingestion)

### Recommendations for Future Migrations
1. Start with field naming analysis early
2. Engage dashboard owners sooner
3. Budget for disk space during dual ingestion
4. Invest in team training on DQL

## References

- **Analysis Reports**: `workspace/analyze-reports/`
- **Conversion Summaries**: `workspace/conversion-summaries/`
- **Dashboard Validation**: `workspace/dashboard-validation-report.md`
- **Configuration History**: Git commits on feature/structured-logging-migration branch

## Support

For questions or issues post-migration:
- **Dynatrace Documentation**: https://docs.dynatrace.com
- **FamilySearch Observability Standards**: https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295
- **Internal Slack**: #dynatrace-migration
```

## Task Management

The migrate skill creates and manages tasks throughout the workflow:

### Task Creation Strategy

**Phase-based tasks:**
- One task per phase (analyze, convert, setup, validate, deploy, cutover)
- Subtasks for major activities within phases
- Dependencies between tasks (Phase 2 blocks on Phase 1, etc.)

**Module-based tasks:**
- One task per module for conversion
- One task per module for testing
- Sequential or parallel based on dependencies

**Activity-based tasks:**
- Convert ERROR logs
- Convert DELETE candidates
- Setup logback config
- Update Splunk dashboards
- Create Dynatrace dashboards

### Task Status Updates

Migrate skill updates task status automatically:

- **pending**: Task created, not started
- **in_progress**: Skill actively working on task
- **completed**: Task finished successfully
- **blocked**: Task waiting on dependency

### User Approval Gates

Between major phases, pause for user approval:

1. **Migrate skill**: Completes phase tasks
2. **Migrate skill**: Generates phase summary report
3. **Migrate skill**: Creates approval task ("Review Phase X and approve to continue")
4. **User**: Reviews phase outputs
5. **User**: Marks approval task complete (or provides feedback)
6. **Migrate skill**: Proceeds to next phase

## Deployment Checklists

Generate environment-specific deployment checklists:

### Phase 1 Deployment Checklist (Splunk JSON)

```markdown
# Phase 1 Deployment Checklist: Structured JSON to Splunk

## Pre-Deployment

- [ ] All conversion tasks completed
- [ ] Tests passing (`mvn clean test`)
- [ ] Code reviewed and approved
- [ ] logback-spring.xml generated and reviewed
- [ ] Local JSON verification successful
- [ ] Feature branch merged to main

## Deployment (Integration Environment)

- [ ] Build application: `mvn clean install`
- [ ] Deploy artifact to integration environment
- [ ] Verify application starts successfully
- [ ] Check `/var/log/fs/app.json` file created
- [ ] Check `/var/log/fs/business-events.json` file created
- [ ] Verify files contain valid JSON (not empty)
- [ ] Verify Splunk forwarder ingesting files
- [ ] Check Splunk index for new structured logs
- [ ] Verify log volume within expected range
- [ ] Monitor disk usage (rolling policy working)
- [ ] Exercise application features, check logs

## Validation

- [ ] Structured fields present in Splunk (`person.id`, `ordinance.type`, etc.)
- [ ] MDC fields present (`dt.trace_id`, `dt.span_id`)
- [ ] Timestamps correct (ISO 8601 UTC)
- [ ] Stack traces formatted correctly
- [ ] Business events separated to different file
- [ ] No errors in application logs related to logging
- [ ] Log levels appropriate (ERROR <0.1%, WARN 1-2%, INFO 10-20%)

## Rollback Plan

If issues detected:

- [ ] Revert to previous deployment (unstructured logging)
- [ ] Investigate root cause
- [ ] Fix issue in feature branch
- [ ] Re-test locally
- [ ] Redeploy

## Next Steps

- [ ] Monitor integration for 24-48 hours
- [ ] Update Splunk dashboards with new field names
- [ ] Validate updated dashboards show correct data
- [ ] Get approval from dashboard owners
- [ ] Proceed to Phase 2 (staging deployment)
```

### Phase 2 Deployment Checklist (Dual Ingestion)

```markdown
# Phase 4 Deployment Checklist: Add Dynatrace (Dual Ingestion)

## Pre-Deployment

- [ ] Phase 1 successful in production
- [ ] Splunk dashboards updated and validated
- [ ] Dynatrace OneAgent installed on target hosts
- [ ] Dynatrace monitoring `/var/log/fs-log/` directory
- [ ] Dynatrace dashboards created and tested in non-prod
- [ ] Team trained on Dynatrace DQL queries
- [ ] logback-spring.xml updated for Phase 2 (uncommented Dynatrace appender)

## Deployment (Integration Environment)

- [ ] Build application: `mvn clean install`
- [ ] Deploy artifact to integration environment
- [ ] Verify application starts successfully
- [ ] Check `/var/log/fs/app.json` file still created (Splunk)
- [ ] Check `/var/log/fs-log/app.json` file created (Dynatrace)
- [ ] Verify both files contain valid JSON
- [ ] Verify Splunk still receiving logs
- [ ] Verify Dynatrace OneAgent ingesting logs
- [ ] Check Dynatrace UI for new logs
- [ ] Monitor disk usage (~2x during dual ingestion)

## Validation

- [ ] Both Splunk and Dynatrace show same log count
- [ ] Structured fields present in both systems
- [ ] Dynatrace dashboards show correct data
- [ ] Compare dashboard results: Splunk vs Dynatrace
- [ ] Trace IDs correlate across distributed traces
- [ ] No performance degradation (CPU, memory, I/O)
- [ ] Log volume within expected range (no unexpected spike)

## Rollback Plan

If issues detected:

- [ ] Remove Dynatrace appender (comment out Phase 2 section)
- [ ] Redeploy (Splunk-only)
- [ ] Investigate root cause
- [ ] Fix and re-test

## Next Steps

- [ ] Monitor dual ingestion for 1-2 weeks
- [ ] Validate Dynatrace reliability
- [ ] Ensure team comfortable with Dynatrace queries
- [ ] Get final approval to cutover
- [ ] Proceed to Phase 3 (Dynatrace-only cutover)
```

## Error Handling

If any phase encounters errors:

1. **Migrate skill**: Detects error (compilation, test failure, deployment issue)
2. **Migrate skill**: Marks current task as blocked
3. **Migrate skill**: Creates issue report with details
4. **Migrate skill**: Pauses workflow, waits for user resolution
5. **User**: Investigates and fixes issue
6. **User**: Marks blocking issue resolved
7. **Migrate skill**: Resumes from paused task

## Best Practices

### 1. Incremental Progress Over Big Bang

Prefer many small validated steps over one large risky deployment:

- Convert module-by-module or task-by-task
- Deploy environment-by-environment (integ → staging → canary → production)
- Validate thoroughly at each step before proceeding

### 2. Preserve Rollback Capability

At every phase, maintain ability to rollback:

- Feature branches with clear history
- Configuration changes behind feature flags if possible
- Splunk remains functional during Phase 4 (dual ingestion)
- Documented rollback procedures

### 3. Communicate Early and Often

Keep stakeholders informed:

- Dashboard owners: Changes to field names
- Operations team: New log file paths, retention policies
- Development team: New logging patterns (fluent API)
- Management: Progress updates, risk assessments

### 4. Measure and Monitor

Track key metrics throughout migration:

- Log volume (daily MB)
- Disk usage (file sizes, rolling frequency)
- Query performance (Splunk vs Dynatrace)
- Application performance (CPU, memory during logging)
- Error rates (logging-related errors)

### 5. Invest in Training

Ensure team prepared for Dynatrace:

- DQL query language training
- Dynatrace UI navigation
- Dashboard creation
- Alert configuration
- Distributed tracing concepts

## Common Issues and Solutions

### Issue 1: Tests Failing After Conversion

**Cause**: Tests checking specific log output format

**Solution**:
1. Identify failing tests
2. Update test expectations to match structured format
3. Consider using structured assertions:
   ```java
   // Instead of checking message text
   assertThat(logOutput).contains("Processing person TEST123");
   
   // Check structured fields
   JsonNode log = parseLogJson(logOutput);
   assertThat(log.get("person.id").asText()).isEqualTo("TEST123");
   ```

### Issue 2: Disk Space Exhaustion During Phase 4

**Cause**: Dual files (~2x storage), unexpected log volume

**Solution**:
1. Monitor disk usage proactively
2. Adjust retention policies if needed (reduce maxHistory temporarily)
3. Compress older files aggressively
4. Consider shorter Phase 4 duration

### Issue 3: Dashboard Shows No Data After Field Rename

**Cause**: Field name not updated in dashboard query

**Solution**:
1. Check validation report for required field name changes
2. Apply find/replace operations
3. Test updated query in Splunk
4. Verify structured field present in logs

### Issue 4: Performance Degradation During Logging

**Cause**: Expensive operations in log statements

**Solution**:
1. Identify expensive logging operations (profiling)
2. Add guard clauses: `if (logger.isDebugEnabled()) { ... }`
3. Use lambda wrapping: `.addKeyValue("field", () -> expensiveOperation())`
4. Consider async appenders in logback config

## Validation Success Criteria

Before marking migration complete, verify:

- [ ] **Code Quality**: All tests passing, no compilation warnings
- [ ] **Log Volume**: 60-80% reduction vs original Splunk volume
- [ ] **Compliance**: Logs meet FamilySearch Observability Standards
- [ ] **Dashboards**: All dashboards migrated and validated in Dynatrace
- [ ] **Performance**: No application performance degradation
- [ ] **Team Readiness**: Team trained and comfortable with Dynatrace
- [ ] **Documentation**: Migration documented, runbooks updated
- [ ] **Observability**: MTTD/MTTR maintained or improved
- [ ] **Cleanup**: Splunk infrastructure decommissioned cleanly

## References

- **FamilySearch Observability Standards**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **Plugin Documentation**: `/home/fransonsr/github/satoris-claude-config/skills/splunk-to-dynatrace/PLUGIN.md`
- **Analyze Skill**: `splunk-to-dynatrace:analyze`
- **Convert Logs Skill**: `splunk-to-dynatrace:convert-logs`
- **Setup Logback Skill**: `splunk-to-dynatrace:setup-logback`
- **Validate Dashboards Skill**: `splunk-to-dynatrace:validate-dashboards`

---

**Remember**: Migration is a marathon, not a sprint. Incremental progress with thorough validation at each step leads to successful outcomes with minimal risk.
