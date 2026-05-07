---
name: splunk-to-dynatrace:choose-approach
description: Interactive questionnaire that helps teams choose the right Splunk-to-Dynatrace migration approach (Comprehensive, Quick, or Progressive Enhancement) based on their context. Recommends specific workflow, estimates effort, and generates personalized migration plan. Use this skill when teams are unsure which migration strategy fits their needs, want effort estimates before committing, or need to build consensus on approach.
---

# Choose Migration Approach Skill

Helps teams select the optimal Splunk-to-Dynatrace migration strategy by analyzing their context, constraints, and goals through an interactive questionnaire.

## When to Use This Skill

- Team is unsure which migration approach to take (Comprehensive vs Quick vs Progressive)
- Need effort estimates to secure budget/resources
- Want to understand trade-offs before committing to a strategy
- Building consensus across stakeholders (developers, ops, management)
- Starting migration planning and need structured decision-making
- Want to validate assumptions about migration complexity

## What This Skill Produces

**Primary Output**: Personalized migration plan document saved to `.claude/migration-plan.md`

**Contents**:
- Recommended approach (Comprehensive / Quick / Hybrid / Progressive) with rationale
- Customized workflow with phase-by-phase breakdown
- Effort estimates (developer-weeks, calendar duration)
- Risk assessment and mitigation strategies
- Progressive enhancement path (stop points along the way)
- Alternative approaches if context changes

**Secondary Outputs**:
- Decision matrix showing scoring rationale
- Context summary (team's answers to key questions)
- Next steps checklist (what to do after choosing approach)

## Claude Code Best Practices Integration

This skill incorporates and teaches best practices for multi-phase work with Claude Code:

### 1. Meta-Planning Before Execution

**What**: Create high-level plan BEFORE detailed work
**Why**: Prevents scope creep, enables approval gates, tracks progress
**How**: This skill generates meta-plan as output

**Practice**: After running this skill, review the generated plan with your team, get approval, then create a tracking task:

```bash
# In Claude Code session
/task create "Execute Splunk-to-Dynatrace migration" --description "Follow migration-plan.md phases" --status pending
```

### 2. Phase-Based Session Management

**What**: Use separate Claude Code sessions for different phases
**Why**: Keeps context lean, prevents token exhaustion, enables parallel work

**Practice**:
- **Orchestration Session**: Keep one "clean" session for high-level coordination
  - Tracks overall progress
  - Makes phase-level decisions
  - Reviews phase outputs
  - Updates meta-plan
  
- **Execution Sessions**: Spawn new sessions for detailed work
  - One session per phase (analyze, convert, validate, etc.)
  - Close session after phase complete
  - Handoff document bridges sessions

**Example**:
```
Session 1 (Orchestration): Run choose-approach, review plan, create tasks
Session 2 (Analysis): Run analyze skill, generate reports, close session
Session 1 (Orchestration): Review analysis, decide next phase
Session 3 (Conversion): Run convert-logs on module A, test, close session
Session 1 (Orchestration): Review conversions, approve next module
```

### 3. Handoff Documents Between Sessions

**What**: Create `.claude/handoff-{phase}.md` when switching sessions
**Why**: New session has no context from previous sessions - handoff provides orientation

**Template**:
```markdown
# Handoff: {Phase Name}

## What We Accomplished
- [Bullet list of completions]

## Current State
- Branch: feature/structured-logging
- Files modified: [list]
- Tests status: passing/failing
- Blockers: [any issues]

## Next Session Should
- [Action items for next phase]
- [Files to review]
- [Decisions needed]

## Context Files to Read
- .claude/migration-plan.md (overall plan)
- .claude/analyze-reports/00-executive-summary.md (analysis)
- [other relevant files]
```

### 4. Task Tool for Progress Tracking

**What**: Use `/task` commands to track phase completion
**Why**: Visual progress tracking, prevents duplicate work, enables pause/resume

**Practice**: Create parent task for migration, subtasks for each phase

```bash
# Parent task (from migration-plan.md)
/task create "Splunk-to-Dynatrace Migration (GOFR)" --description "Follow hybrid approach per migration-plan.md" --status in_progress

# Phase tasks (create all upfront from plan)
/task create "Phase 1: Analyze logs and generate reports" --status pending
/task create "Phase 2: Convert critical logs (DELETE, METRIC)" --status pending
/task create "Phase 3: Validate dashboards" --status pending
/task create "Phase 4: Setup logback and deploy Phase 1" --status pending
/task create "Phase 5: Add Dynatrace dual ingestion" --status pending
/task create "Phase 6: Cutover to Dynatrace only" --status pending

# Update as you progress
/task update "Phase 1: Analyze logs and generate reports" --status completed
/task update "Phase 2: Convert critical logs (DELETE, METRIC)" --status in_progress
```

### 5. Workspace Organization

**What**: Use `.claude/workspace/{phase}/` directories for phase outputs
**Why**: Organized outputs, easy to find, doesn't clutter repo root

**Structure**:
```
.claude/
├── migration-plan.md (this skill's output)
├── decisions.md (log "why" decisions)
├── session-state.md (current phase, blockers, next steps)
├── handoff-phase-1.md
├── handoff-phase-2.md
└── workspace/
    ├── analysis/
    │   ├── 00-executive-summary.md
    │   └── modules/...
    ├── conversion-phase-2/
    │   ├── conversion-summary.md
    │   └── modified-files.txt
    ├── dashboard-validation/
    │   └── validation-report.md
    └── iteration-summaries/
        ├── phase-1-complete.md
        └── phase-2-complete.md
```

### 6. Git Hygiene and Checkpoints

**What**: Commit after each phase completion
**Why**: Atomic progress, easy rollback, clear history

**Practice**:
```bash
# After Phase 1 (Analysis)
git add .claude/workspace/analysis/
git commit -m "docs: Complete Phase 1 analysis - 33 logs identified, 60% compliant"

# After Phase 2 (Conversion)
git add gofr-service/src/main/java/...
git add gofr-service/src/test/java/...
git add .claude/workspace/conversion-phase-2/
git commit -m "refactor: Phase 2 - Convert critical logs (DELETE, METRIC)

- Delete 8 logs (Dynatrace auto-captures)
- Convert 3 logs to Micrometer metrics
- Tests updated and passing

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### 7. Approval Gates for Irreversible Actions

**What**: Pause before deletions, deployments, breaking changes
**Why**: Prevents mistakes, builds user confidence, enables review

**Practice**: This skill prompts for approval at:
- After generating migration plan (approve before starting)
- Before log deletions (review what will be deleted)
- Before dashboard updates (review queries)
- Before deployments (review changeset)
- Before cutover (final confirmation)

### 8. Iteration Summaries

**What**: After each phase, create `phase-{N}-summary.md`
**Why**: Documents progress, learnings, decisions for future reference

**Template**:
```markdown
# Phase {N} Summary: {Phase Name}

## Completed
- [What was accomplished]

## Metrics
- Files modified: X
- Logs converted: Y
- Tests updated: Z
- Duration: N developer-days

## Learnings
- [What went well]
- [Challenges encountered]
- [Solutions applied]

## Decisions Made
- [Key decisions with rationale]

## Next Phase Prep
- [Prerequisites for next phase]
- [Recommended reading]
```

---

## Questionnaire: 7 Key Questions

The skill asks these questions to understand team context:

### Q1: Dashboard Dependency
"How many active Splunk dashboards monitor this application?"

**Options**:
- A. 0-5 dashboards (LOW dependency)
- B. 6-20 dashboards (MODERATE dependency)
- C. 21+ dashboards (HIGH dependency)

**Scoring**:
- LOW → Favor Quick or Progressive (dashboards not blocker)
- MODERATE → Favor Hybrid (validate critical dashboards, defer others)
- HIGH → Favor Comprehensive (coordinate all updates upfront)

---

### Q2: Dashboard Ownership
"Who owns/maintains these dashboards?"

**Options**:
- A. Your team only (SIMPLE coordination)
- B. Shared operations team (MODERATE coordination)
- C. Multiple stakeholder teams (COMPLEX coordination)

**Scoring**:
- SIMPLE → Favor Quick or Progressive (you control updates)
- MODERATE → Favor Hybrid (coordinate with ops)
- COMPLEX → Favor Comprehensive (many stakeholders need involvement)

---

### Q3: Migration Urgency
"When do you need to cutover to Dynatrace?"

**Options**:
- A. 1-2 weeks (URGENT deadline)
- B. 1-3 months (STRATEGIC timeline)
- C. 6+ months or flexible (RELAXED timeline)

**Scoring**:
- URGENT → Favor Quick (skip analysis, migrate fast, fix later)
- STRATEGIC → Favor Hybrid (critical fixes upfront, iterate later)
- RELAXED → Favor Comprehensive (time to do it right)

---

### Q4: Current Logging Quality
"What percentage of logs already follow FamilySearch Observability Standards?"

**Options**:
- A. 0-25% (POOR compliance, many issues)
- B. 26-75% (MODERATE compliance, some issues)
- C. 76-100% (GOOD compliance, minor issues)

**Scoring**:
- POOR → Favor Comprehensive (needs significant fixing)
- MODERATE → Favor Hybrid (fix critical, defer rest)
- GOOD → Favor Quick or Progressive (mostly ready)

---

### Q5: Test Coverage
"What's your test coverage?"

**Options**:
- A. Minimal (<50% coverage)
- B. Moderate (50-80% coverage)
- C. Strong (80%+ coverage)

**Scoring**:
- MINIMAL → Favor Quick or Progressive (risky to refactor extensively)
- MODERATE → Favor Hybrid (selective refactoring)
- STRONG → Favor Comprehensive (can refactor safely)

---

### Q6: Team Bandwidth
"How many developer-weeks are available for this migration?"

**Options**:
- A. 1-2 weeks (LIMITED bandwidth)
- B. 4-6 weeks (MODERATE bandwidth)
- C. 8+ weeks (AMPLE bandwidth)

**Scoring**:
- LIMITED → Favor Quick or Progressive (minimal upfront investment)
- MODERATE → Favor Hybrid (strategic improvements)
- AMPLE → Favor Comprehensive (maximize long-term value)

---

### Q7: Risk Tolerance
"Risk tolerance for dashboard downtime or data gaps?"

**Options**:
- A. Zero tolerance (CRITICAL monitoring, no downtime acceptable)
- B. Brief acceptable (IMPORTANT monitoring, <1 hour downtime OK)
- C. Can iterate (STANDARD monitoring, fix-as-we-go acceptable)

**Scoring**:
- ZERO → Favor Comprehensive or Hybrid (validate exhaustively)
- BRIEF → Favor Hybrid (validate critical dashboards only)
- ITERATE → Favor Quick or Progressive (fix issues as discovered)

---

## Scoring Algorithm

**Input**: Answers to 7 questions (A/B/C)
**Output**: Recommendation score for each approach

### Score Calculation

Each answer contributes points to different approaches:

| Question | Answer | Comprehensive | Quick | Hybrid | Progressive |
|----------|--------|--------------|-------|--------|-------------|
| Q1: Dashboards | A (0-5) | 0 | +3 | +2 | +3 |
| | B (6-20) | +2 | 0 | +3 | +1 |
| | C (21+) | +3 | 0 | +2 | 0 |
| Q2: Ownership | A (Your team) | +1 | +3 | +2 | +3 |
| | B (Shared ops) | +2 | 0 | +3 | +1 |
| | C (Multiple) | +3 | 0 | +2 | 0 |
| Q3: Urgency | A (1-2 weeks) | 0 | +3 | +1 | +2 |
| | B (1-3 months) | +2 | 0 | +3 | +1 |
| | C (6+ months) | +3 | 0 | +2 | +3 |
| Q4: Quality | A (0-25%) | +3 | 0 | +2 | +1 |
| | B (26-75%) | +2 | +1 | +3 | +2 |
| | C (76-100%) | +1 | +3 | +1 | +2 |
| Q5: Tests | A (Minimal) | 0 | +2 | +1 | +3 |
| | B (Moderate) | +2 | +1 | +3 | +2 |
| | C (Strong) | +3 | +1 | +2 | +1 |
| Q6: Bandwidth | A (1-2 weeks) | 0 | +3 | +1 | +3 |
| | B (4-6 weeks) | +2 | +1 | +3 | +2 |
| | C (8+ weeks) | +3 | 0 | +2 | +1 |
| Q7: Risk | A (Zero) | +3 | 0 | +2 | +1 |
| | B (Brief) | +2 | +1 | +3 | +2 |
| | C (Iterate) | +1 | +3 | +1 | +3 |

**Recommendation**: Highest score wins. Tie-breaker: prefer Hybrid (most flexible).

---

## Approach Definitions

### Comprehensive Approach
**Philosophy**: Fix Splunk first, migrate later
**Timeline**: 6-12 weeks
**Phases**: Analyze → Convert all logs → Validate all dashboards → Deploy structured JSON to Splunk → Add Dynatrace → Cutover
**Best For**: Strong test coverage, many dashboards, time to invest upfront
**Outcome**: Clean, compliant logs from day one in Dynatrace

### Quick Approach
**Philosophy**: Migrate first, fix later
**Timeline**: 1-2 weeks
**Phases**: (Optional: Quick analyze) → Setup logback Phase 3 (Dynatrace-only) → Deploy → Improve incrementally
**Best For**: Urgent deadline, few dashboards, can tolerate iterative fixes
**Outcome**: On Dynatrace fast, optimize over time

### Hybrid Approach (Recommended Default)
**Philosophy**: Fix critical issues first, defer non-critical
**Timeline**: 4-8 weeks
**Phases**: Analyze → Convert critical logs (DELETE, METRIC, ERROR) → Validate critical dashboards → Deploy Phase 1 (Splunk) → Add Dynatrace → Cutover → Continue improvements
**Best For**: Most teams - balances speed and quality
**Outcome**: Major issues fixed, on Dynatrace within reasonable timeline, path for continued improvement

### Progressive Enhancement
**Philosophy**: Incremental improvements at your pace
**Timeline**: Ongoing (start immediately)
**Phases**: Choose improvements a la carte, stop when "good enough"
**Best For**: Limited bandwidth, want to validate value before full investment
**Outcome**: Each increment adds value, no big-bang commitment

---

## Workflow Execution

### Step 1: Interactive Questionnaire

Present questions one at a time, capture answers:

```
=== Splunk-to-Dynatrace Migration Approach Selection ===

I'll ask you 7 questions to recommend the best migration approach for your team.
This will take about 5 minutes.

Ready to start? (y/n)
```

After confirmation, ask each question with options:

```
Q1: How many active Splunk dashboards monitor this application?

A. 0-5 dashboards (few dashboards, low coordination)
B. 6-20 dashboards (moderate dashboard dependency)
C. 21+ dashboards (many dashboards, high coordination)

Your answer (A/B/C):
```

Capture all 7 answers.

---

### Step 2: Calculate Scores and Recommend

Apply scoring algorithm, determine winner:

```
=== Analyzing Your Context ===

Calculating scores...

Comprehensive: 12 points
Quick: 8 points
Hybrid: 18 points ⭐ RECOMMENDED
Progressive: 10 points

Based on your answers, I recommend: **Hybrid Approach**
```

---

### Step 3: Generate Personalized Migration Plan

Create `.claude/migration-plan.md` with:

**Section 1: Context Summary**
- Your team's answers to 7 questions
- Key constraints identified (dashboards, urgency, bandwidth)

**Section 2: Recommended Approach**
- Approach name (Comprehensive/Quick/Hybrid/Progressive)
- Rationale (why this approach fits your context)
- Scoring breakdown (show how recommendation was determined)

**Section 3: Customized Workflow**
- Phase-by-phase breakdown tailored to your approach
- For each phase:
  - Objective
  - Skills to run
  - Deliverables
  - Effort estimate (developer-days)
  - Success criteria

**Section 4: Effort Estimates**
- Total developer-weeks
- Calendar duration (accounting for parallel phases, approval gates)
- Resource requirements (developers, reviewers, approvers)

**Section 5: Risk Assessment**
- Identified risks based on context (many dashboards, tight deadline, etc.)
- Mitigation strategies per risk

**Section 6: Progressive Enhancement Path**
- "Stop here" checkpoints along the way
- Each checkpoint: % complete, value delivered, effort to date
- Shows you can stop early if needed

**Section 7: Alternative Approaches**
- If urgency increases, what changes?
- If bandwidth increases, what's possible?
- If priorities shift, how to adapt?

**Section 8: Next Steps Checklist**
- [ ] Review this plan with team
- [ ] Get stakeholder approval
- [ ] Create tracking tasks in Claude Code
- [ ] Run analyze skill to validate estimates
- [ ] Create feature branch
- [ ] Set up workspace directories
- [ ] Start Phase 1

**Section 9: Claude Code Best Practices**
- Reminder to use orchestration session + execution sessions
- Handoff document template
- Task tracking commands
- Git hygiene checklist
- Approval gate reminders

---

### Step 4: Teach Claude Code Best Practices

After generating plan, educate user:

```
=== Your Migration Plan is Ready ===

I've created a personalized migration plan: .claude/migration-plan.md

This plan includes customized phases, effort estimates, and risk mitigation
based on your team's context.

Before you start, let me share some best practices for managing multi-phase
work with Claude Code:

1. **Create Tracking Tasks** (recommended now)
   /task create "Splunk-to-Dynatrace Migration (YOUR_APP)" --status in_progress
   /task create "Phase 1: Analyze" --status pending
   /task create "Phase 2: Convert" --status pending
   [... create task for each phase ...]

2. **Use Separate Sessions for Phases**
   - Keep THIS session for high-level orchestration
   - Spawn NEW sessions for detailed phase work
   - Close execution sessions when phase complete
   - Return here to review outputs and plan next phase

3. **Create Handoff Documents Between Sessions**
   When switching sessions, create .claude/handoff-{phase}.md
   New session reads handoff to get oriented quickly

4. **Commit After Each Phase**
   git commit after phase completion (atomic progress, easy rollback)
   Include phase summary in commit message

5. **Organize Outputs in Workspace**
   .claude/workspace/{phase-name}/ for phase-specific files
   Keeps repo clean, outputs organized

6. **Document Decisions**
   When making trade-off decisions, log them in .claude/decisions.md
   Prevents re-litigation, explains "why" to future readers

7. **Phase Summaries**
   After each phase, create .claude/workspace/iteration-summaries/phase-{N}-summary.md
   Documents: what completed, metrics, learnings, next steps

Would you like me to:
A. Create tracking tasks now
B. Set up workspace structure
C. Start Phase 1 (analyze)
D. Wait (you'll review plan with team first)

Your choice (A/B/C/D):
```

---

### Step 5: Set Up Project Structure (If User Requests)

If user chooses A or B, create:

```bash
# Workspace directories
mkdir -p .claude/workspace/analysis
mkdir -p .claude/workspace/conversion
mkdir -p .claude/workspace/dashboard-validation
mkdir -p .claude/workspace/iteration-summaries

# Tracking files
touch .claude/decisions.md
touch .claude/session-state.md

# Placeholder files with templates
```

Create `.claude/session-state.md`:
```markdown
# Migration Session State

**Current Phase**: Planning (pre-Phase 1)
**Active Branch**: [not yet created]
**Last Updated**: [timestamp]

## Current Status
- migration-plan.md created
- Waiting for user to review plan and approve
- Tasks not yet created

## Next Actions
1. Review migration-plan.md with team
2. Get stakeholder approval
3. Create tracking tasks
4. Run analyze skill (Phase 1)

## Blockers
None currently

## Notes
- Recommended approach: Hybrid
- Estimated effort: [from plan]
- Target completion: [from plan]
```

Create `.claude/decisions.md`:
```markdown
# Migration Decisions Log

## 2026-05-06: Approach Selection

**Decision**: Selected Hybrid approach for migration
**Rationale**: Based on 7-question assessment:
- 15 dashboards (moderate coordination)
- 6-week timeline (strategic, not urgent)
- 85% test coverage (can refactor safely)
- 60% current compliance (some work needed)
- 4-6 weeks bandwidth (moderate resources)
- Brief downtime acceptable (not critical)

**Alternatives Considered**:
- Comprehensive: Too slow for 6-week timeline
- Quick: Risk to dashboards unacceptable
- Progressive: Team wants defined completion date

**Trade-offs**:
- PRO: Balances speed and quality
- PRO: Fixes critical issues upfront
- CON: Still requires 4-6 weeks effort
- CON: Some non-critical logs deferred

---

[Future decisions will be logged here]
```

---

## Example Output: migration-plan.md

```markdown
# Splunk-to-Dynatrace Migration Plan: GOFR Service

**Generated**: 2026-05-06
**Recommended Approach**: Hybrid
**Estimated Effort**: 4-6 developer-weeks over 6-8 calendar weeks

---

## Your Team's Context

### Answers to Key Questions

| Question | Your Answer | Implication |
|----------|-------------|-------------|
| Dashboards | B. 6-20 dashboards | Moderate coordination needed |
| Ownership | B. Shared ops team | Coordinate with operations |
| Urgency | B. 1-3 months | Strategic timeline, not rush |
| Current Quality | B. 26-75% compliant | Some work needed, not starting from scratch |
| Test Coverage | C. Strong (80%+) | Can refactor safely |
| Bandwidth | B. 4-6 weeks | Moderate resources available |
| Risk Tolerance | B. Brief acceptable | Can tolerate <1hr dashboard gaps |

### Scoring Breakdown

| Approach | Score | Rationale |
|----------|-------|-----------|
| **Hybrid** | **18 points** ⭐ | Best fit: balances dashboard coordination needs with strategic timeline. Strong tests enable safe refactoring. Moderate bandwidth sufficient for critical fixes. |
| Comprehensive | 12 points | Strong second choice, but timeline too aggressive for full fix-everything approach |
| Progressive | 10 points | Viable fallback if bandwidth shrinks |
| Quick | 8 points | Too risky given dashboard dependency and operations coordination needs |

---

## Recommended Approach: Hybrid

### Philosophy
Fix critical issues first (DELETE logs, metrics, ERROR-level problems), defer non-critical improvements to post-migration. Gets you on Dynatrace within timeline while addressing high-impact problems.

### Why Hybrid Fits Your Team
1. **Dashboard Coordination**: 6-20 dashboards manageable with targeted validation (not exhaustive)
2. **Timeline**: 6-8 weeks aligns with 1-3 month strategic timeline
3. **Quality**: 26-75% compliance means some logs already good (don't redo what works)
4. **Safety**: Strong test coverage enables confident refactoring
5. **Resources**: 4-6 weeks sufficient for critical fixes, not full rewrite
6. **Risk**: Brief downtime tolerance allows iterative dashboard updates

### What Makes This "Hybrid"
- **Like Comprehensive**: Analyze thoroughly, validate critical dashboards, test extensively
- **Like Quick**: Deploy to Dynatrace within 6-8 weeks, defer non-critical improvements
- **Unique**: Strategic about what to fix now vs later (ROI-driven prioritization)

---

## Your Customized Workflow

### Phase 1: Analysis & Planning (Week 1)
**Objective**: Understand current state, identify critical issues, validate effort estimates

**Skills to Run**:
```bash
/splunk-to-dynatrace:analyze
```

**Activities**:
1. Run analyze skill (10-15 minutes execution, 1-2 hours review)
2. Review executive summary with team
3. Identify critical logs (DELETE candidates, metrics, ERROR-level)
4. Identify critical dashboards (top 5 most-used)
5. Validate effort estimates from this plan
6. Get stakeholder approval for next phases

**Deliverables**:
- `.claude/workspace/analysis/00-executive-summary.md`
- `.claude/workspace/analysis/01-quick-wins.md`
- `.claude/workspace/analysis/02-metrics-conversion.md`
- List of critical logs for Phase 2
- List of critical dashboards for Phase 3

**Effort**: 1 developer-day (analysis) + 1 day (team review/approval)

**Success Criteria**:
- [ ] Analyze reports reviewed by team
- [ ] Critical logs identified (DELETE, METRIC, ERROR priorities)
- [ ] Critical dashboards identified (top 5-10)
- [ ] Stakeholder approval to proceed
- [ ] Feature branch created

**Claude Code Best Practice**: Use this orchestration session for analysis. Keep execution session open until Phase 1 complete, then create handoff document.

---

### Phase 2: Convert Critical Logs (Weeks 2-3)
**Objective**: Fix high-impact logging issues (DELETE, METRIC, ERROR-level)

**Skills to Run**:
```bash
/splunk-to-dynatrace:convert-logs --scope critical
```

**Activities**:
1. **Week 2**: Convert DELETE candidates (logs Dynatrace auto-captures)
   - Expected: 20-30% log volume reduction
   - Low risk (removing redundancy)
   - Test and commit after conversion
   
2. **Week 2**: Convert METRIC candidates (business counters/timers)
   - Expected: 5-10 logs → Micrometer metrics
   - **CRITICAL**: Review cardinality before conversion
   - Test metrics, commit
   
3. **Week 3**: Fix ERROR-level logs (required fields, structured format)
   - Expected: 10-15 logs
   - Add external.dependency, proper exception handling
   - Update tests, commit

4. **Week 3**: Fix WARN-level logs (add warn.category)
   - Expected: 5-10 logs
   - Low effort, high value for filtering
   - Test, commit

**Deliverables**:
- `.claude/workspace/conversion/conversion-summary-delete.md`
- `.claude/workspace/conversion/conversion-summary-metrics.md`
- `.claude/workspace/conversion/conversion-summary-errors.md`
- Modified Java files (committed incrementally)
- Updated test files

**Effort**: 1.5-2 developer-weeks (conversion + testing)

**Success Criteria**:
- [ ] DELETE candidates removed (log volume reduced 20-30%)
- [ ] METRIC candidates converted to Micrometer (cardinality validated)
- [ ] ERROR logs have required fields (external.dependency, etc.)
- [ ] WARN logs have warn.category field
- [ ] All tests passing after each conversion batch
- [ ] Code reviewed and merged to feature branch

**Claude Code Best Practice**: 
- Spawn NEW execution session for Phase 2 (keeps this orchestration session clean)
- Create `.claude/handoff-phase-1.md` with analysis insights for Phase 2 session
- Commit after each conversion batch (DELETE, then METRIC, then ERROR, then WARN)
- Update tasks: mark Phase 1 complete, mark Phase 2 in-progress

---

### Phase 3: Validate Critical Dashboards (Week 4)
**Objective**: Ensure top dashboards won't break with log changes

**Skills to Run**:
```bash
/splunk-to-dynatrace:validate-dashboards
```

**Activities**:
1. Gather Splunk dashboard exports (top 5-10 dashboards)
2. Run validation skill
3. Review risk assessment with dashboard owners
4. Update critical dashboards (field renames if needed)
5. Defer non-critical dashboard updates to post-migration

**Deliverables**:
- `.claude/workspace/dashboard-validation/validation-report.md`
- Updated Splunk dashboard definitions (XML/JSON)
- DQL equivalents for Dynatrace dashboards

**Effort**: 3-5 developer-days (validation + updates + review)

**Success Criteria**:
- [ ] Critical dashboards validated (no breaking changes)
- [ ] Required updates applied and tested
- [ ] Dashboard owners approve changes
- [ ] DQL equivalents documented for future Dynatrace dashboards
- [ ] Non-critical dashboards documented for later

**Claude Code Best Practice**:
- Can reuse Phase 2 execution session OR spawn new one
- Create `.claude/handoff-phase-2.md` summarizing conversions
- Commit dashboard updates separately from code changes

---

### Phase 4: Deploy Phase 1 (Structured JSON to Splunk) (Week 5)
**Objective**: Deploy structured logging to integration/staging, validate Splunk ingestion

**Skills to Run**:
```bash
/splunk-to-dynatrace:setup-logback --phase 1
```

**Activities**:
1. Run setup-logback skill (generates logback-spring.xml)
2. Review generated config (validate field naming strategy)
3. Test locally with JSON verification appender
4. Deploy to integration environment
5. Validate Splunk receiving structured JSON
6. Check critical dashboards (updated ones) show correct data
7. Deploy to staging (1 week parallel run)

**Deliverables**:
- `src/main/resources/logback-spring.xml` (Phase 1 config)
- Local JSON verification output
- Integration environment logs in Splunk
- Dashboard validation screenshots/reports

**Effort**: 1 developer-week (config + deploy + validation)

**Success Criteria**:
- [ ] logback-spring.xml generated and reviewed
- [ ] Local testing successful (valid JSON output)
- [ ] Integration deployment successful
- [ ] Splunk ingesting structured JSON
- [ ] Critical dashboards show correct data
- [ ] Log volume within expected range (20-30% reduction)
- [ ] Staging deployment successful (1 week monitoring)

**Claude Code Best Practice**:
- Use orchestration session for setup-logback skill
- Spawn execution session for deployment troubleshooting if needed
- Create `.claude/handoff-phase-3.md` with deployment learnings
- Update `.claude/decisions.md` with any config choices made

---

### Phase 5: Add Dynatrace Dual Ingestion (Week 6-7)
**Objective**: Add Dynatrace appender, run parallel ingestion for validation

**Skills to Run**:
```bash
/splunk-to-dynatrace:setup-logback --phase 2
```

**Activities**:
1. Update logback-spring.xml for Phase 2 (uncomment Dynatrace appender)
2. Verify Dynatrace OneAgent installed on hosts
3. Deploy to integration
4. Validate both Splunk AND Dynatrace receiving logs
5. Create critical Dynatrace dashboards (use DQL from Phase 3)
6. Compare dashboard results (Splunk vs Dynatrace)
7. Deploy to staging (1-2 weeks parallel operation)
8. Monitor for discrepancies

**Deliverables**:
- Updated `logback-spring.xml` (Phase 2 config)
- Dynatrace dashboards (JSON definitions)
- Parallel operation report (Splunk vs Dynatrace comparison)

**Effort**: 1 developer-week (config + dashboard creation + validation)

**Success Criteria**:
- [ ] Dynatrace appender added to logback config
- [ ] Both Splunk and Dynatrace receiving logs
- [ ] Dynatrace dashboards created (critical ones)
- [ ] Dashboard results match between systems
- [ ] No discrepancies in log data
- [ ] 1-2 weeks parallel operation successful
- [ ] Team comfortable with Dynatrace queries

**Claude Code Best Practice**:
- Use orchestration session for setup-logback skill
- Create Dynatrace dashboards in separate execution session if complex
- Create `.claude/handoff-phase-4.md` with deployment state
- Create `.claude/workspace/iteration-summaries/phase-4-summary.md`

---

### Phase 6: Cutover to Dynatrace Only (Week 8)
**Objective**: Disable Splunk appender, Dynatrace becomes primary

**Skills to Run**:
```bash
/splunk-to-dynatrace:setup-logback --phase 3
```

**Activities**:
1. Final validation: Dynatrace dashboards, alerts, queries all working
2. Update logback-spring.xml for Phase 3 (remove Splunk appender)
3. Deploy to integration
4. Validate Dynatrace-only operation
5. Deploy to staging (brief monitoring)
6. Deploy to production (phased rollout)
7. Decommission Splunk forwarder

**Deliverables**:
- Final `logback-spring.xml` (Phase 3 config, Dynatrace-only)
- Cutover validation report
- Decommissioning checklist (Splunk infrastructure)

**Effort**: 3-5 developer-days (cutover + validation + decommission)

**Success Criteria**:
- [ ] Splunk appender removed from config
- [ ] Dynatrace-only operation validated
- [ ] All dashboards working in Dynatrace
- [ ] Production cutover successful
- [ ] Splunk forwarder stopped
- [ ] Team trained on Dynatrace queries/dashboards

**Claude Code Best Practice**:
- Use orchestration session for final setup-logback
- Create `.claude/workspace/iteration-summaries/phase-6-complete.md`
- Create final `.claude/migration-retrospective.md` (what went well, learnings)
- Close feature branch, merge to main

---

## Effort Estimates Summary

| Phase | Calendar Time | Developer Effort | Dependencies |
|-------|--------------|------------------|--------------|
| Phase 1: Analysis | Week 1 | 2 days | None |
| Phase 2: Convert Critical | Weeks 2-3 | 2 weeks | Phase 1 complete |
| Phase 3: Validate Dashboards | Week 4 | 1 week | Phase 2 complete |
| Phase 4: Deploy Phase 1 | Week 5 | 1 week | Phase 3 complete |
| Phase 5: Dynatrace Dual | Weeks 6-7 | 1 week | Phase 4 validated |
| Phase 6: Cutover | Week 8 | 0.5 weeks | Phase 5 validated |
| **TOTAL** | **8 weeks** | **5.5 weeks** | Sequential |

**Notes**:
- Calendar time includes parallel validation periods (staging runs, dual ingestion monitoring)
- Developer effort is actual hands-on-keyboard time
- Approvals/reviews add 1-2 days per phase (not included in estimates)

---

## Risk Assessment & Mitigation

### Risk 1: Dashboard Coordination (MODERATE)
**Risk**: Shared operations team owns dashboards, coordination needed
**Impact**: Delays if ops team unavailable or disagrees on changes
**Mitigation**:
- Identify ops dashboard owner early (Phase 1)
- Schedule Phase 3 review meeting with ops team
- Provide validation report showing no breaking changes
- Offer to update dashboards for them (reduce their burden)
**Likelihood**: Medium | **Impact**: Medium

### Risk 2: Timeline Pressure (LOW-MODERATE)
**Risk**: 6-week timeline ambitious, delays possible
**Impact**: May need to defer more logs to post-migration
**Mitigation**:
- Focus on critical logs (DELETE, METRIC, ERROR) in Phase 2
- Defer WARN/INFO improvements to post-migration if needed
- Progressive enhancement path allows stopping at Phase 4 (80% complete)
**Likelihood**: Medium | **Impact**: Low

### Risk 3: Metrics Cardinality (HIGH IMPACT if missed)
**Risk**: Converting high-cardinality logs to metrics causes explosion
**Impact**: Dynatrace performance degradation, cost increase
**Mitigation**:
- **CRITICAL**: Review cardinality during Phase 2 METRIC conversions
- Exclude high-cardinality tags from metrics (keep in logs)
- Validate metrics in integration before staging
- Monitor metrics volume after deployment
**Likelihood**: Low (with proper review) | **Impact**: High

### Risk 4: Test Coverage Gaps (LOW)
**Risk**: Strong tests (80%+) but may miss edge cases
**Impact**: Log format changes break untested code paths
**Mitigation**:
- Run full test suite after each conversion batch
- Integration tests validate log output format
- Staged deployments catch issues before production
**Likelihood**: Low | **Impact**: Low

---

## Progressive Enhancement Path

You can stop at any point - each phase adds value:

### Stop After Phase 1 (30% Complete)
**Value Delivered**:
- Deep understanding of logging issues
- Roadmap for improvements
- Analysis reports for future reference

**Effort**: 2 developer-days
**When to Stop Here**: Team decides migration not worth it, or priorities change

---

### Stop After Phase 2 (60% Complete)
**Value Delivered**:
- 20-30% log volume reduction (cost savings on Splunk)
- Business metrics in Micrometer (better aggregation)
- ERROR logs structured (faster triage)
- Improved observability even staying on Splunk

**Effort**: 2.5 weeks
**When to Stop Here**: Migration delayed but want to keep improvements

---

### Stop After Phase 4 (80% Complete)
**Value Delivered**:
- Structured JSON to Splunk (better queries)
- Critical logs improved
- Validated dashboards
- Ready for Dynatrace when organization decides

**Effort**: 5 weeks
**When to Stop Here**: Dynatrace cutover delayed at org level, but you're ready

---

### Complete Through Phase 6 (100% Complete)
**Value Delivered**:
- On Dynatrace (modern observability platform)
- Critical logs compliant with standards
- Dashboards migrated and validated
- Path for continued optimization

**Effort**: 5.5 weeks (8 calendar weeks)
**When to Stop Here**: Full migration complete, continue incremental improvements

---

## Alternative Approaches (If Context Changes)

### If Urgency Increases (Deadline moves to 2 weeks)
**Recommendation**: Switch to **Quick Approach**
**Changes**:
- Skip Phase 1 analysis (or minimal 2-hour review)
- Skip Phase 2 conversions
- Skip Phase 3 dashboard validation
- Jump to Phase 4 setup-logback Phase 3 (Dynatrace-only)
- Deploy in 1 week, fix issues post-migration
**Effort**: 1-2 weeks (3-5 developer-days)
**Trade-off**: Log quality issues deferred, dashboard breakage possible

---

### If Bandwidth Increases (8+ weeks available)
**Recommendation**: Upgrade to **Comprehensive Approach**
**Changes**:
- Phase 2: Convert ALL logs (not just critical)
- Phase 3: Validate ALL dashboards (not just top 5-10)
- Add Phase 2.5: Fix log levels (INFO → DEBUG where appropriate)
- Longer parallel operation in Phase 5 (2-4 weeks)
**Effort**: 8-10 weeks (full compliance from day one)
**Trade-off**: Longer timeline, but 100% compliant at cutover

---

### If Priorities Shift (Migration deprioritized)
**Recommendation**: Switch to **Progressive Enhancement**
**Changes**:
- Complete Phase 1 (analysis)
- Cherry-pick improvements a la carte (DELETE logs this sprint, metrics next sprint)
- No fixed timeline, improve at your pace
- Use insights to improve observability even staying on Splunk
**Effort**: Ongoing, as bandwidth allows
**Trade-off**: Never "done", but continuous incremental value

---

## Next Steps Checklist

### Immediate (Today)
- [ ] Read this migration-plan.md thoroughly
- [ ] Review with tech lead and team
- [ ] Identify any concerns or constraints not captured
- [ ] Decide: proceed with Hybrid approach, or adjust?

### This Week
- [ ] Get stakeholder approval (management, operations, dashboard owners)
- [ ] Create tracking tasks in Claude Code (see commands below)
- [ ] Create feature branch: `feature/structured-logging-migration`
- [ ] Set up workspace directories (see commands below)
- [ ] Run analyze skill (Phase 1)

### Next Week
- [ ] Review analyze reports with team
- [ ] Identify critical logs for Phase 2
- [ ] Start Phase 2 conversions (DELETE candidates first)

---

## Claude Code Best Practices for This Migration

### 1. Create Tracking Tasks (Run Now)

```bash
# In Claude Code, create parent and phase tasks:
/task create "Splunk-to-Dynatrace Migration (GOFR)" --description "Hybrid approach per migration-plan.md" --status in_progress

/task create "Phase 1: Analyze logs and generate reports" --status pending
/task create "Phase 2: Convert critical logs (DELETE, METRIC, ERROR, WARN)" --status pending
/task create "Phase 3: Validate critical dashboards" --status pending
/task create "Phase 4: Setup logback Phase 1 (Splunk structured JSON)" --status pending
/task create "Phase 5: Add Dynatrace dual ingestion" --status pending
/task create "Phase 6: Cutover to Dynatrace only" --status pending
```

### 2. Session Management Strategy

**Orchestration Session** (this session):
- Keep open for entire migration (8 weeks)
- Use for high-level decisions and phase coordination
- Review phase outputs here
- Update tasks here
- Make trade-off decisions here
- Keep context lean (don't read large files unnecessarily)

**Execution Sessions** (spawn as needed):
- Phase 1: Spawn session for analyze skill → close after analysis complete
- Phase 2: Spawn session for convert-logs → close after conversions merged
- Phase 3: Spawn session for validate-dashboards → close after validation complete
- Phase 4-6: Can reuse orchestration session (setup-logback is quick)

### 3. Handoff Document Pattern

When spawning execution session, create handoff first:

**Template**: `.claude/handoff-phase-{N}.md`

```markdown
# Handoff: Phase {N} - {Phase Name}

## Context from Previous Phases
- [Key decisions made]
- [Constraints discovered]
- [Artifacts created]

## Your Mission
[What this phase should accomplish]

## Files to Review First
- .claude/migration-plan.md (overall plan)
- .claude/decisions.md (why decisions)
- [phase-specific files]

## Success Criteria
[How to know phase is complete]

## Return to Orchestration Session
When phase complete:
1. Create .claude/workspace/iteration-summaries/phase-{N}-summary.md
2. Commit changes with phase tag in message
3. Update tasks (mark phase complete)
4. Return to orchestration session
```

### 4. Git Hygiene

Commit after each major milestone:

```bash
# After Phase 1
git add .claude/workspace/analysis/
git commit -m "docs: Phase 1 analysis - 33 logs, 60% compliant, 11 critical fixes identified"

# After Phase 2 (per batch)
git add gofr-service/src/main/java/.../
git add gofr-service/src/test/java/.../
git commit -m "refactor: Phase 2A - Delete auto-captured logs (8 logs removed, 30% volume reduction)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git commit -m "refactor: Phase 2B - Convert logs to Micrometer metrics (3 logs, cardinality validated)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### 5. Workspace Organization

Set up now:

```bash
mkdir -p .claude/workspace/analysis
mkdir -p .claude/workspace/conversion
mkdir -p .claude/workspace/dashboard-validation
mkdir -p .claude/workspace/iteration-summaries

touch .claude/decisions.md
touch .claude/session-state.md
```

### 6. Decision Logging

When making trade-offs, log in `.claude/decisions.md`:

```markdown
## 2026-05-06: Field Naming Strategy

**Decision**: Use Hybrid field naming (keep existing camelCase, add required dot.notation)
**Context**: GOFR has 15 Splunk dashboards using camelCase field names
**Alternatives Considered**:
- Option 1: Standardize all to dot.notation (breaks dashboards)
- Option 2: Keep all as camelCase (non-compliant)
**Rationale**: Non-breaking for dashboards, achieves compliance, temporary duplication acceptable
**Trade-offs**: Slightly higher log volume until Phase 6, more verbose code
```

### 7. Phase Summaries

After each phase, create `.claude/workspace/iteration-summaries/phase-{N}-summary.md`:

**Template**:
```markdown
# Phase {N} Summary: {Phase Name}

## Completed
- [Deliverables]

## Metrics
- Files modified: X
- Logs converted: Y
- Tests updated: Z
- Duration: N days

## Learnings
- [What went well]
- [Challenges]
- [Solutions]

## Decisions Made
- [Key decisions with rationale]

## Next Phase Prep
- [Prerequisites]
- [Recommended reading]
```

### 8. Approval Gates

Before irreversible actions, pause for approval:

- Before Phase 2: "I've identified 8 logs to DELETE. Review list?"
- Before Phase 3: "I'll update 5 dashboards. Review changes?"
- Before Phase 4: "Ready to deploy to integration? Review logback-spring.xml?"
- Before Phase 6: "Ready to cutover to Dynatrace-only? Final confirmation?"

---

## Questions or Issues?

If you have questions about this plan or encounter issues:

1. **Review this document** - it contains detailed rationale
2. **Check `.claude/decisions.md`** - explains trade-off choices
3. **Ask in orchestration session** - I can clarify or adjust plan
4. **Consult analyze reports** - data-driven insights about your codebase
5. **Review PLUGIN.md** - detailed skill documentation

This plan is a living document - adjust as you learn more about your codebase and constraints.

**Ready to start Phase 1?** Run:
```bash
/splunk-to-dynatrace:analyze
```

Good luck with your migration! 🚀
```

---

## Implementation Checklist

When executing this skill:

- [ ] Ask 7 questions interactively
- [ ] Capture user answers (A/B/C format)
- [ ] Calculate scores per approach
- [ ] Determine recommended approach (highest score)
- [ ] Generate personalized `migration-plan.md` with:
  - [ ] Context summary
  - [ ] Recommended approach with rationale
  - [ ] Customized workflow (phases tailored to approach)
  - [ ] Effort estimates
  - [ ] Risk assessment
  - [ ] Progressive enhancement path
  - [ ] Alternative approaches
  - [ ] Next steps checklist
  - [ ] Claude Code best practices section
- [ ] Educate user on Claude Code best practices
- [ ] Offer to set up project structure (tasks, workspace)
- [ ] Create `.claude/session-state.md`
- [ ] Create `.claude/decisions.md` with approach selection rationale

---

## Success Criteria

This skill succeeds when:

- [ ] User understands their recommended approach and WHY
- [ ] User has concrete next steps (not overwhelmed)
- [ ] User knows how to use Claude Code effectively for multi-phase work
- [ ] User has realistic effort estimates (can plan resources)
- [ ] User knows where to stop if needed (progressive enhancement path)
- [ ] User feels confident starting Phase 1
- [ ] migration-plan.md exists and is comprehensive
- [ ] Tracking structure set up (tasks, workspace, decision log)

---

## References

- **FamilySearch Observability Standards**: `/plugins/splunk-to-dynatrace/references/familysearch-observability-standards.md`
- **Plugin Documentation**: `/plugins/splunk-to-dynatrace/PLUGIN.md`
- **Skill Documentation**: Other skills in `/plugins/splunk-to-dynatrace/skills/`
