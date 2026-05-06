# Splunk-to-Dynatrace Migration Plugin

**Start your Splunk-to-Dynatrace migration your way** - Comprehensive, Quick, or Incremental

A flexible plugin for migrating Spring Boot applications from Splunk to Dynatrace observability, with structured JSON logging and compliance with FamilySearch Observability Standards.

## Three Ways to Use This Plugin

### 🚀 Quick Migration (1-2 weeks)
Skip the analysis, deploy structured JSON to Dynatrace immediately, optimize later.

**Skills**: setup-logback → deploy → (improve over time)

**Best for**: Urgent deadlines, minimal dashboards, can tolerate iterative improvements

---

### 🔍 Comprehensive Migration (6-12 weeks)
Analyze, fix logs, validate dashboards, then migrate with confidence.

**Skills**: analyze → convert-logs → validate-dashboards → setup-logback → cutover

**Best for**: Teams with many dashboards, strong test coverage, time to invest upfront

---

### 📈 Progressive Enhancement (your pace)
Use any skill standalone, stop when you've achieved "good enough" for your needs.

**Skills**: Pick what adds value today (analyze only? DELETE logs? Fix levels?)

**Best for**: Limited bandwidth, want to validate value before full investment

---

**Not sure which path?** Run `/splunk-to-dynatrace:choose-approach` for a personalized recommendation based on your context.

---

## Skills Add Value Independently

You don't need to run a full migration to benefit from this plugin:

- **analyze**: Improve logging quality even staying on Splunk (30-60% log volume reduction possible)
- **convert-logs**: Reduce ingest costs by deleting auto-captured logs
- **validate-dashboards**: Audit dashboard health (catches brittle queries, documents dependencies)
- **setup-logback**: Get structured JSON without leaving Splunk infrastructure

Each skill returns value on its own. **Use what you need, when you need it.**

---

## Skills in This Plugin

### `/splunk-to-dynatrace:choose-approach` ⭐ START HERE

**Interactive questionnaire that recommends migration approach based on your context.**

Asks 7 questions about:
- Dashboard count and ownership
- Migration urgency and timeline
- Current logging quality (% compliant)
- Test coverage and team bandwidth
- Risk tolerance

**Produces**:
- Personalized migration plan with phased workflow
- Effort estimates (developer-weeks, calendar duration)
- Risk assessment and mitigation strategies
- Progressive enhancement path (stop points along the way)
- Claude Code best practices for multi-phase work

**Use when**: Starting migration planning, building stakeholder consensus, estimating effort

**Teaches**: Session management, task tracking, handoff documents, git hygiene, approval gates

---

### `/splunk-to-dynatrace:analyze`

**Analyzes current logging patterns and generates compliance reports against FamilySearch Observability Standards.**

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

**Use standalone?**: YES - valuable even if you never migrate to Dynatrace

**Time**: 10-15 minutes

---

### `/splunk-to-dynatrace:convert-logs`

**Converts traditional log statements to SLF4J fluent API with structured arguments per observability standards.**

**Capabilities:**
- Converts to SLF4J fluent API with `addKeyValue()` structured fields
- Applies log level corrections per FamilySearch decision tree
- Deletes logs Dynatrace auto-captures (with explanation comments)
- Converts counter/timing logs to Micrometer metrics
- **CRITICAL**: Validates metrics cardinality (prevents explosion)
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

**Use standalone?**: YES - improves observability even staying on Splunk

**Time**: Varies (30 mins - 8 hours depending on scope)

---

### `/splunk-to-dynatrace:setup-logback`

**Generates logback-spring.xml configuration for structured JSON logging with profile-based appenders.**

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

**Use standalone?**: YES - can setup structured JSON to Splunk only (Phase 1)

**Time**: 5-10 minutes

---

### `/splunk-to-dynatrace:validate-dashboards`

**Validates Splunk dashboards work with structured logging and generates Dynatrace equivalents.**

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

**Use standalone?**: YES - validates dashboard health even without migration

**Time**: 15-30 minutes

---

### `/splunk-to-dynatrace:migrate`

**Orchestrates the full migration process from analysis through deployment. This is the "full meal deal" option.**

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

**Outputs:**
- Migration task list with dependencies
- Phase summary reports
- Environment-specific deployment checklists
- Final migration report (metrics, timeline, lessons learned)

**Use standalone?**: NO - this is the full orchestration (use other skills for a la carte)

**Time**: 6-12 weeks (depends on approach and scope)

---

## Progressive Enhancement Levels

You can stop at any level - each adds value:

### Level 0: Analysis Only (10 minutes)
- Run `analyze` skill
- Review findings with team
- Use insights to improve logging (no migration commitment)
- **Value**: Understand technical debt, cost savings opportunities

### Level 1: Structured JSON to Splunk (1-2 weeks)
- Run `setup-logback` (Phase 1)
- Deploy structured JSON to existing Splunk
- **Value**: Better queries, lower volume, same infrastructure

### Level 2: Log Quality Improvements (2-4 weeks)
- Run `convert-logs` on high-value targets (DELETE candidates, metrics)
- Test & deploy incrementally
- **Value**: Compound benefits - structured + clean + efficient

### Level 3: Dashboard Validation (1 week)
- Run `validate-dashboards`
- Update critical dashboards proactively
- **Value**: Ready for Dynatrace when team decides to migrate

### Level 4: Dynatrace Migration (4-8 weeks)
- Run `setup-logback` (Phase 2 & 3)
- Dual ingestion → validation → cutover
- **Value**: Modern observability platform, decommission Splunk

### Level 5: Full Compliance (ongoing)
- Continue `convert-logs` for remaining issues
- Optimize queries and dashboards
- **Value**: Maintain observability standards, continuous improvement

---

## Claude Code Best Practices for Multi-Phase Work

This plugin teaches and reinforces best practices for managing complex, multi-phase work with Claude Code:

### 1. Session Naming for Clarity

**Name your Claude Code sessions descriptively** to distinguish orchestration from execution work.

**Orchestration Session** (keep for entire migration):
- Name: `"Migration Orchestrator - GOFR Splunk→Dynatrace"`
- Purpose: High-level coordination, decision-making, phase transitions
- Lifespan: Entire migration (weeks/months)
- Keep context lean (don't load large files)

**Execution Sessions** (spawn as needed, close when done):
- Name examples:
  - `"Phase 1: Analyze GOFR Logs"`
  - `"Phase 2A: Convert DELETE Logs - gofr-service"`
  - `"Phase 2B: Metrics Conversion - CounterMetricsListeners"`
  - `"Phase 3: Validate Splunk Dashboards"`
  - `"Phase 4: Deploy Structured JSON to Integration"`
- Purpose: Detailed execution work for specific phase
- Lifespan: Duration of phase (hours/days)
- Close after phase complete

**Why This Matters**:
- Multiple browser tabs with "Claude Code" aren't helpful
- Descriptive names help you quickly identify which session to use
- Prevents accidentally mixing orchestration and execution work
- Makes it obvious which session to resume after a break

**How to Name Sessions**:
- In browser: Use the page/tab title (browser extensions or manual bookmark naming)
- In conversation: Refer to session by name ("In the Orchestrator session, let's review...")
- In handoff docs: Document which session should be used next

### 2. Meta-Planning with Task Tracking

**Create high-level plan BEFORE detailed work** using the choose-approach skill.

After plan generated, create tracking tasks:
```bash
/task create "Splunk-to-Dynatrace Migration (GOFR)" --status in_progress
/task create "Phase 1: Analyze" --status pending
/task create "Phase 2: Convert Critical Logs" --status pending
# ... etc
```

Update as you progress:
```bash
/task update "Phase 1: Analyze" --status completed
/task update "Phase 2: Convert Critical Logs" --status in_progress
```

### 3. Handoff Documents Between Sessions

When spawning execution session, create `.claude/handoff-phase-{N}.md`:

**Template**:
```markdown
# Handoff: Phase {N} - {Phase Name}

## Context from Previous Phases
[Key decisions, constraints, artifacts]

## Your Mission
[What this phase should accomplish]

## Files to Review First
- .claude/migration-plan.md (overall plan)
- .claude/decisions.md (why decisions)
[phase-specific files]

## Success Criteria
[How to know phase is complete]

## Return to Orchestration Session
When complete:
1. Create phase summary
2. Commit changes
3. Update tasks
4. Return to "Migration Orchestrator - GOFR" session
```

### 4. Workspace Organization

Use `.claude/workspace/{phase}/` for phase outputs:

```
.claude/
├── migration-plan.md (choose-approach output)
├── decisions.md (trade-off rationale)
├── session-state.md (current phase, blockers)
├── handoff-phase-1.md
├── handoff-phase-2.md
└── workspace/
    ├── analysis/
    ├── conversion-phase-2/
    ├── dashboard-validation/
    └── iteration-summaries/
```

### 5. Git Hygiene and Checkpoints

Commit after each phase completion:

```bash
git add .claude/workspace/analysis/
git commit -m "docs: Phase 1 analysis - 33 logs, 60% compliant

[Phase summary here]

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### 6. Phase Summaries

After each phase, create `.claude/workspace/iteration-summaries/phase-{N}-summary.md`:

**Template**:
```markdown
# Phase {N} Summary: {Phase Name}

## Completed
[Deliverables]

## Metrics
Files modified: X, Logs converted: Y, Duration: N days

## Learnings
[What went well, challenges, solutions]

## Decisions Made
[Key decisions with rationale]

## Next Phase Prep
[Prerequisites, recommended reading]
```

**The choose-approach skill teaches all these practices in detail.**

---

## Key Features

- **Standards-based transformation** using FamilySearch Observability Standards
- **Automated compliance checking** with objective criteria
- **Business event separation** for future S3/Databricks routing
- **Log level recommendations** per decision tree (ERROR, WARN, INFO, DEBUG, TRACE)
- **Deletion recommendations** for logs Dynatrace auto-captures
- **Metric conversion** with cardinality validation (prevents explosion)
- **Field naming flexibility** (three strategies: standardize, defer, hybrid)
- **Performance optimizations** (lambda wrapping, guard clauses)
- **Incremental conversion** (full, module-by-module, task-by-task)
- **Dashboard validation** (SPL to DQL conversion, breakage risk assessment)
- **Phased rollout** (Splunk → Dual → Dynatrace with approval gates)
- **Task management** (progress tracking, dependencies, approval gates)
- **Deployment checklists** (per phase, per environment)
- **Multi-phase work best practices** (session management, handoffs, git hygiene)

---

## Benefits

1. **Flexible approaches** - Choose comprehensive, quick, or progressive enhancement
2. **Standalone value** - Each skill adds value independently (not all-or-nothing)
3. **Validate with Splunk first** - Test structured format with known quantity (lower risk)
4. **Update dashboards incrementally** - Splunk first, then Dynatrace
5. **Single code conversion** - Not dual-format maintenance
6. **Clear migration path** - Splunk JSON → Both → Dynatrace only
7. **Automated compliance** - Objective criteria from standards
8. **Reusable across teams** - Standardized approach
9. **Progressive enhancement** - Stop when "good enough", resume later
10. **Best practices built-in** - Teaches effective Claude Code usage

---

## File Structure

```
/var/log/fs/app.json              → Splunk forwarder (Phase 1-4)
/var/log/fs-log/app.json          → Dynatrace OneAgent (Phase 4+)
/var/log/fs/business-events.json  → Business events (eventual S3/Databricks)
```

---

## Requirements

- Spring Boot with SLF4J and Logback
- Maven or Gradle build system
- Java 11+ (for SLF4J fluent API)
- Access to FamilySearch Observability Standards
- `net.logstash.logback:logstash-logback-encoder` dependency (v8.0+)
- Micrometer (for metric conversions, usually included with Spring Boot Actuator)

---

## Quick Start

### If You're Unsure Where to Start

```bash
# Get personalized recommendation
/splunk-to-dynatrace:choose-approach
```

Answer 7 questions → receive customized migration plan with effort estimates.

### If You Just Want to Understand Current State

```bash
# Analyze only (10-15 minutes)
/splunk-to-dynatrace:analyze
```

Generates reports, estimates savings, identifies quick wins. No commitment to migrate.

### If You Want Full Orchestrated Migration

```bash
# End-to-end migration with approval gates
/splunk-to-dynatrace:migrate
```

Choose approach, follow phased workflow, deploy with validation.

### If You Want to Pick and Choose

```bash
# Use skills independently:
/splunk-to-dynatrace:analyze           # Understand current state
/splunk-to-dynatrace:convert-logs      # Fix high-value logs
/splunk-to-dynatrace:validate-dashboards  # Check dashboard health
/splunk-to-dynatrace:setup-logback     # Generate config
```

Stop when you've achieved "good enough" value.

---

## What's Next?

This plugin will grow based on user needs. See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for planned features:

- **Dashboard creation assistance** (HIGH priority) - Help teams create Dynatrace dashboards
- **Alert migration tools** (HIGH priority) - Migrate Splunk alerts to Dynatrace
- **Query translation** (MEDIUM priority) - Standalone SPL → DQL converter
- **Dashboard optimization** (MEDIUM priority) - Performance and usability improvements
- **ROI calculator** (under consideration) - Estimate cost savings and observability gains
- **Drift detection** (under consideration) - Monitor for log quality regressions post-migration

Have an idea? See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for how to suggest features.

---

## References

- **FamilySearch Observability Standards**: [Confluence Page](https://icseng.atlassian.net/wiki/spaces/Product/pages/1700954295/FamilySearch+Observability+Standards)
- **Logstash Logback Encoder**: [GitHub](https://github.com/logfellow/logstash-logback-encoder)
- **SLF4J Fluent API**: [SLF4J Manual](https://www.slf4j.org/manual.html)
- **Dynatrace DQL Documentation**: [Dynatrace Docs](https://docs.dynatrace.com/docs/observe-and-explore/query-data/dynatrace-query-language)

---

## Version

1.0.0 - Initial release

## Author

FamilySearch Engineering - SATORIS Team

## License

© 2026 by Intellectual Reserve, Inc. All rights reserved.
