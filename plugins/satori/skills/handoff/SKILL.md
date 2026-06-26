---
name: handoff
description: Create comprehensive handoff documents for tasks to be implemented in a fresh Claude Code session. Includes verified context, explicit unknowns, scope boundaries, and acceptance criteria.
argument-hint: <task-id> <brief-description>
---

# Task Handoff Skill

Creates comprehensive handoff documents that enable a fresh Claude Code session to implement tasks without needing conversation history.

## Usage

```
/handoff <task-id> <brief-description>
```

**Examples**:
- `/handoff 4.16.3 Implement MasterIndexWriter for top-level indices`
- `/handoff 5.2 Add retry logic to Kafka consumer`
- `/handoff bug-123 Fix null pointer in ChunkWriter`

## What This Skill Does

Creates a surgical, production-ready handoff document with:

### 1. Verified Context (NOT Assumptions)
- ✅ Facts verified with file:line citations or commit hashes
- ✅ Explicit unknowns listed (what needs discovery)
- ❌ NO "probably" or "might" statements

**Example**:
```markdown
### Known Facts ✅
- Current implementation: `PersonaFilter.java:45-67` checks persona IDs
- Performance baseline: 85ms for 10k records (measured 2026-04-15)
- Legacy behavior: `LegacyFilter.java:78` (commit abc123) DOES handle null refs

### Explicit Unknowns ❓
- Does production data contain null resource URIs? → Check S3: `s3://bucket/test-data/sample.json`
- Is this code path hit during incremental sync? → Ask team lead
```

### 2. Scope Clarity (Surgical Precision)
- What to change (file paths + line numbers)
- What NOT to change (explicit boundaries)
- Decision authority (what implementer decides vs asks)

**Example**:
```markdown
### What to Change 🎯
- File: `PersonaFilter.java`
  - Lines 45-67: Add null checks before filter operation

### What NOT to Change 🚫
- DO NOT refactor entire filter chain (out of scope)
- DO NOT change public API signatures (breaks consumers)

### Decision Authority
**You Decide**: Implementation details, test structure
**Ask First**: API changes, new dependencies, scope expansion
```

### 3. Prior Work & Patterns
- Similar patterns to follow (with file:line references)
- Anti-patterns to AVOID (with reasons)
- Related PRs (successful and failed attempts)

**Example**:
```markdown
### Follow These Patterns ✅
- `CollectionMetadataReader.java:78-92` - CSV parsing with null checks
- CLAUDE.md section 2.3 - JSpecify null-safety annotations

### AVOID These Patterns ❌
- PR #45 approach (had performance issues, reverted in PR #52)
```

### 4. Known Gotchas & Constraints
- Edge cases to handle
- Platform/library constraints
- Team preferences

**Example**:
```markdown
### Known Gotchas 🔥
- Empty strings (not just null) cause silent failures
- CSV column 3 can contain commas → use `split(regex, limit)`

### Constraints
- Must maintain Java 17 compatibility (no JDK 21+ features)
- Can't use lombok (@Builder) - team preference
```

### 5. Testable Acceptance Criteria
- Specific test names that must pass
- Manual verification steps
- Quality gates (Sonar, Copilot)

**Example**:
```markdown
### Definition of Done ✅
- [ ] Test: `shouldRemoveRelationshipsWithNullPersonaId()` passes
- [ ] All existing tests still pass (481/481)
- [ ] SonarQube: No new BLOCKER/CRITICAL issues
- [ ] Manual verification: Run against `/test-data/sample-data.json`
```

### 6. Complexity Signal

The implementing session decides its own process (test-first vs test-after, `/xp-pair` vs solo). Your job is to surface the evidence that informs those decisions — not to prescribe the outcome.

Document which complexity indicators are actually present in this task:
- Multiple execution paths (if/else, loops, recursion)
- String manipulation or parsing
- Collections (iteration, filtering, mapping, grouping)
- Inheritance or type resolution
- Null handling or defensive checks
- Cross-class or cross-module interactions
- Privacy/security critical code
- Unclear or ambiguous requirements

**Example**:
```markdown
### Complexity Signal
**Indicators**: type resolution across 3 inheritance levels, HashMap iteration (nondeterminism risk), privacy-critical filtering

**Specific risks**:
- `PersonaFilter.java:45` uses HashMap for deduplication — iteration order is nondeterministic
- Type resolution must handle: simple names, `super.`, fully-qualified, and wildcard imports
- Privacy-critical: conservative fail-safe required (remove ALL relationships if ANY fails verification)
```

### 7. When to Pause and Ask

Set expectations for when the implementing session should stop and ask rather than push forward.

**Example**:
```markdown
### Complexity: MEDIUM

**Pause and ask if**:
- Test data for null resource URIs not found in S3 sample files
- Legacy `LegacyFilter` behavior differs from documented expectation
- Scope expansion required beyond `PersonaFilter.java`
```

## How It Works

1. **Context Gathering**:
   - Reads task details from `docs/implementation/implementation-tasks.md`
   - Searches codebase for similar patterns
   - Reviews existing implementations
   - Extracts architectural decisions from CLAUDE.md
   - **VERIFIES** facts (no assumptions)

2. **Document Generation**:
   - Run `mkdir -p ~/.claude/handoff/active` (idempotent)
   - Creates `~/.claude/handoff/active/<task-id>-<slug>.md`
   - Begin document with YAML frontmatter (generate from gathered context):
     ```yaml
     ---
     task-id: <task-id>
     task-type: <implementation | port | fix | research | refactor>
     repo: <org/repo-name>
     branch-from: <branch name>
     plugin-version: <if applicable, e.g. "0.5.0">
     key-files:
       - <path/to/file.java>
       - <path/to/other.java>
     dependencies-complete: <true | false — are all prerequisite tasks done?>
     estimated-complexity: <trivial | small | medium | large>
     ---
     ```
   - Verify all `key-files` paths exist before writing — fail if any path is wrong
   - Follows comprehensive template for prose sections
   - Includes verified context with citations
   - Lists explicit unknowns for implementer to discover
   - **Note**: The implementing agent should create a progress document on first session:
     - Location: `~/.claude/handoff/active/<task-id>-<slug>-PROGRESS.md`
     - Template: `~/.claude/plugins/*/handoff/templates/IMPLEMENTATION-PROGRESS-template.md`
     - Pattern: Implementing agent reads handoff (immutable), updates progress (mutable)

3. **Quality Gate** (do not write the file until all pass):

   **Critical (MUST pass)**:
   - [ ] All file paths in `key-files` and "What to Change" verified to exist
   - [ ] All line number references checked for accuracy (read the file, confirm lines)
   - [ ] No "TODO", "fill this in", or placeholder sections remain
   - [ ] No invented commit hashes or unverified references
   - [ ] Explicit unknowns listed — if a fact could not be verified, it is in "Explicit Unknowns"
   - [ ] Scope boundaries present (what to change AND what NOT to change)
   - [ ] Pause-and-ask conditions explicit

   **Essential (REQUIRED)**:
   - [ ] YAML frontmatter complete and all paths verified
   - [ ] Prior work referenced with file:line citations
   - [ ] Complexity signal present with specific indicators (not "MEDIUM" alone)
   - [ ] Acceptance criteria are checkable (not "tests pass" — specific test names or commands)

   If any Critical item fails: fix the handoff before writing. Do not write a
   handoff with known gaps and leave them as TODOs.

## File Naming Convention

Handoff documents are saved as:
```
~/.claude/handoff/active/<task-id>-<slug>.md
```

**Examples**:
- `active/task-4.16.2-collection-indices-writer.md`
- `active/bug-123-null-pointer-fix.md`
- `active/feature-kafka-retry-logic.md`

## Key Philosophy

**Before**: Generic template-based handoffs  
**After**: Surgical precision with verified facts

**Prevents**:
- ❌ Wasting hours on wrong assumptions
- ❌ Discovering scope mid-implementation
- ❌ Hesitating about "should I TDD this?"
- ❌ Asking "am I done yet?"
- ❌ Repeating mistakes from failed PRs

## Integration with Project Standards

The skill automatically incorporates:
- **CLAUDE.md**: Architectural decisions, naming conventions
- **~/.claude/CLAUDE.md**: Coding standards (SOLID, TDD, refactoring)
- **Existing code**: Patterns from similar implementations
- **Legacy code**: References to previous implementations
- **Related PRs**: Successful patterns and failed attempts

## Quality Checklist

Every handoff document must have:

### Critical Quality Gates (MUST HAVE)
- [ ] **Verified context** (NOT assumptions) - with file:line citations
- [ ] **Explicit unknowns** listed (what needs discovery)
- [ ] **Scope boundaries** clear (what to change + what NOT to change)
- [ ] **Decision authority** explicit (what implementer decides vs asks)
- [ ] **Acceptance criteria testable** (specific test names, checklists)

### Essential Content (REQUIRED)
- [ ] Prior work referenced (similar patterns + anti-patterns)
- [ ] Known gotchas documented (edge cases, constraints)
- [ ] Complexity signal present (specific indicators, not "LOW/MEDIUM/HIGH" alone)
- [ ] Pause-and-ask conditions explicit

### Self-Contained Verification
- [ ] Implementer can start without reading conversation history
- [ ] All file paths verified to exist
- [ ] All line number references accurate
- [ ] No "TODO: fill this in" sections

## Success Criteria

A good handoff document enables a fresh Claude session to:
- ✅ Understand the task without reading conversation history
- ✅ Know exactly what to implement and what is out of scope
- ✅ Have clear acceptance criteria for completion
- ✅ Follow project patterns and standards
- ✅ Make its own informed process decisions (TDD approach, xp-pair) from the complexity signal
- ✅ Know when to pause and ask rather than push forward

## When to Use This Skill

**Use for**:
- Complex features requiring detailed context
- Tasks that will be implemented in a separate session
- Work that involves multiple files or subsystems
- Tasks with unclear requirements needing clarification
- Features with important gotchas or constraints

**Skip for**:
- Trivial bug fixes (< 50 lines)
- Documentation-only changes
- Tasks you'll implement immediately (in same session)

## Inter-Agent Communication Pattern

This skill implements the **Handoff + Progress** pattern for inter-agent communication.

### Two-File Approach

> **⚠️ Do NOT use Claude memory for inter-agent communication.**  
> Progress, decisions, blockers, and questions belong in the `-PROGRESS.md` file — not in memory.  
> Memory is for durable cross-project preferences, not task-level noise that would clutter future sessions.

**Handoff Document (Immutable)**:
- Location: `~/.claude/handoff/active/{task-slug}.md`
- Purpose: Original specification for implementing agent
- Content: Executive summary, technical specs, architecture, implementation guide, acceptance criteria
- Update policy: Only on fundamental architecture changes

**Implementation Progress (Mutable)**:
- Location: `~/.claude/handoff/active/{task-slug}-PROGRESS.md`
- Purpose: Track implementation evolution, decisions, blockers, and feedback to the orchestrating session
- Content: Architectural decisions, progress checklist, blockers, questions
- Update policy: Implementing agent updates frequently — this is the communication channel back to the orchestrator

### Responsibility Model

**Orchestrating Agent (this skill)**:
- Creates handoff document with complete specification
- Does NOT create progress document (implementing agent creates it)
- Reviews progress document to answer questions
- Updates handoff only on fundamental changes

**Implementing Agent (reads handoff)**:
- Reads handoff document (does not modify)
- Creates progress document on first session
- Updates progress document frequently — **this is the only feedback channel back to the orchestrator**
- Records decisions, progress, blockers, questions in progress document (NOT in memory)
- May request handoff updates for fundamental changes
- **Does NOT archive** — leave both files in `active/` when done; the orchestrating session archives after verifying

### When to Update Handoff Document

**Orchestrating agent updates handoff only when**:
- Fundamental architecture changes invalidate original spec
- Major scope changes require new implementation approach
- Technology stack changes
- Integration patterns change

**Examples**:
- Change: "Use PostgreSQL" → "Use MongoDB" (update handoff)
- Change: "Analyze skill creates conversion-inventory.json" → "Maven plugin creates it" (update handoff)

**NOT reasons to update handoff**:
- Implementation details (Java class structure)
- Progress notes
- Questions/blockers
- Tactical decisions within original architecture

(These go in progress document)

### When Implementing Agent Updates Progress

**Update progress document for**:
- Architectural decisions made during implementation
- Progress on tasks
- Current blockers
- Questions for orchestrating agent
- Deviations from spec (with rationale)

**Update after**:
- Completing a task or phase
- Making an architectural decision
- Encountering a blocker
- Discovering ambiguity in spec

**Distinguish blockers from observations**: Use `### Blockers` for items requiring
orchestrator reply before work continues. Use `### Observations` for corrections,
surprises, or lessons that don't block progress. The orchestrating session will scan
`### Blockers` first.

### Benefits

- **Clean Specification**: Handoff remains readable, focused on "what to build"
- **Clear Progress**: Progress document tracks "how we're building it"
- **Better Communication**: Implementing agent can ask questions without polluting spec
- **Audit Trail**: Decisions captured with date, rationale, impact

### Handoff Lifecycle (Orchestrating Session Responsibility)

Handoff documents are **task-scoped** — they live in `active/` while a task is in flight and move to `archive/` when complete.

**Directory layout**:
```
~/.claude/handoff/
  active/    ← in-progress tasks (small, scannable)
  archive/   ← completed tasks (audit trail preserved)
```

**When creating a handoff**, write it to `active/`:
```
~/.claude/handoff/active/<task-id>-<slug>.md
~/.claude/handoff/active/<task-id>-<slug>-PROGRESS.md  (created by implementing agent)
```

**When to archive**: Once the orchestrating session confirms the result is complete and accurate (all acceptance criteria met, output verified), move both files to `archive/`:

```bash
SLUG="<task-id>-<slug>"
mkdir -p ~/.claude/handoff/archive
mv ~/.claude/handoff/active/${SLUG}.md ~/.claude/handoff/archive/
mv -f ~/.claude/handoff/active/${SLUG}-PROGRESS.md ~/.claude/handoff/archive/ 2>/dev/null || true
```

**When NOT to archive**:
- Implementation is still in progress (progress document shows incomplete items)
- Acceptance criteria have not been verified by the orchestrating session
- The implementing session flagged blockers or open questions

**Verification before archiving**: Read the PROGRESS document and confirm:
- [ ] All acceptance criteria checklist items are checked
- [ ] No open blockers or questions remain
- [ ] The orchestrating session has verified the output (not just taken the implementing agent's word)

> **Why archive rather than delete?** Completed handoff docs preserve the *why* behind design decisions, anti-patterns to avoid on re-entry, and scope constraints that aren't obvious from the code. Archiving keeps `active/` small and scannable while retaining the audit trail.

## Related Documentation

See `~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/handoff/README.md` for:
- Complete document structure template
- Detailed examples of each section
- Context gathering strategy
- Document generation process
- Error handling guidelines
