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
   - Creates `~/.claude/handoff/<task-id>-<slug>.md`
   - Follows comprehensive template (see README.md)
   - Includes verified context with citations
   - Lists explicit unknowns for implementer to discover
   - **Note**: The implementing agent should create a progress document on first session:
     - Location: `~/.claude/handoff/<task-id>-<slug>-PROGRESS.md`
     - Template: `~/.claude/plugins/*/handoff/templates/IMPLEMENTATION-PROGRESS-template.md`
     - Pattern: Implementing agent reads handoff (immutable), updates progress (mutable)

3. **Quality Validation**:
   - Verifies all file paths exist
   - Checks line number references for accuracy
   - Ensures no "TODO" or placeholder sections
   - Confirms all references are real (no made-up commit hashes)

## File Naming Convention

Handoff documents are saved as:
```
~/.claude/handoff/<task-id>-<slug>.md
```

**Examples**:
- `task-4.16.2-collection-indices-writer.md`
- `bug-123-null-pointer-fix.md`
- `feature-kafka-retry-logic.md`

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

**Handoff Document (Immutable)**:
- Location: `~/.claude/handoff/{task-slug}.md`
- Purpose: Original specification for implementing agent
- Content: Executive summary, technical specs, architecture, implementation guide, acceptance criteria
- Update policy: Only on fundamental architecture changes

**Implementation Progress (Mutable)**:
- Location: `~/.claude/handoff/{task-slug}-PROGRESS.md`
- Purpose: Track implementation evolution, decisions, blockers
- Content: Architectural decisions, progress checklist, blockers, questions
- Update policy: Implementing agent updates frequently

### Responsibility Model

**Orchestrating Agent (this skill)**:
- Creates handoff document with complete specification
- Does NOT create progress document (implementing agent creates it)
- Reviews progress document to answer questions
- Updates handoff only on fundamental changes

**Implementing Agent (reads handoff)**:
- Reads handoff document (does not modify)
- Creates progress document on first session
- Updates progress document frequently
- Records decisions, progress, blockers, questions
- May request handoff updates for fundamental changes

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

### Benefits

- **Clean Specification**: Handoff remains readable, focused on "what to build"
- **Clear Progress**: Progress document tracks "how we're building it"
- **Better Communication**: Implementing agent can ask questions without polluting spec
- **Audit Trail**: Decisions captured with date, rationale, impact

## Related Documentation

See `~/.claude/skills/handoff/README.md` for:
- Complete document structure template
- Detailed examples of each section
- Context gathering strategy
- Document generation process
- Error handling guidelines
