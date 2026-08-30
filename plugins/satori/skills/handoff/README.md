# Handoff Plugin

Two skills for keeping Claude sessions continuous and context-rich. `continue` is invoked as a
subcommand of the `handoff` plugin (`/handoff:continue`), which is why it's namespaced under
`handoff` even though it's a distinct, standalone skill:

| Skill | Command | Purpose |
|---|---|---|
| **handoff** | `/handoff <task-id> <desc>` | Create a task specification for a different session or worker |
| **continue** | `/handoff:continue [slug]` | Checkpoint the current session for resumption after `/clear` |

---

## `handoff:continue` — In-Session Continuation

Produces a self-contained continuation document that lets you resume the current session
with full fidelity after `/clear` — avoiding the lossy summaries that automatic compaction
produces.

**Optimized for orchestration sessions** where context fills fastest (agent results flood in)
and compaction is most damaging (the coordinator's pivot reasoning is exactly what gets
summarized away). Works for any long or complex session.

### How `continue` differs from `handoff`

| | `/handoff` | `/handoff:continue` |
|---|---|---|
| Audience | A *different* fresh session / worker | The *same* worker, post-`/clear` |
| Background | Includes project background + specs | Assumes same goals — **no** background |
| Focus | "What to build" spec + acceptance criteria | Live state + **verbatim next step** |
| Lifecycle | Stable spec (updated only for fundamental changes) + separate PROGRESS doc | Single file, overwritten each checkpoint |
| Trigger | Before delegating a task | Checkpoint during a long session |

### Key behaviors

- **Manual creation**: Run `/handoff:continue [slug]` when *you* decide to prepare for continuation — before `/clear`, before a large fan-out, at a phase boundary
- **Single file**: `~/.claude/handoff/continue/<slug>-CONTINUATION.md` — overwritten on each checkpoint, not archived
- **PROGRESS docs linked, not duplicated**: delegated handoff sessions' findings live in their PROGRESS docs; the continuation records verified paths + orchestrator-side status only
- **Quality gate**: no continuation doc written until all critical items pass (verified paths, executable next action, no invented references)

### Resume command

After `/clear`, paste:
```
Read ~/.claude/handoff/continue/<slug>-CONTINUATION.md and resume.
```

---

## `handoff` — Task Handoff Skill

Creates comprehensive handoff documents that enable a fresh Claude Code session to implement tasks without needing conversation history.

### Usage

```
/handoff <task-id> <brief-description>
```

**Examples**:
- `/handoff 4.16.3 Implement MasterIndexWriter for top-level indices`
- `/handoff 5.2 Add retry logic to Kafka consumer`
- `/handoff bug-123 Fix null pointer in ChunkWriter`

### What This Skill Does

Creates a surgical, production-ready handoff document with:

#### 1. Verified Context (NOT Assumptions)
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

#### 2. Scope Clarity (Surgical Precision)
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

#### 3. Prior Work & Patterns
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

#### 4. Known Gotchas & Constraints
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

#### 5. Testable Acceptance Criteria
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

#### 6. Complexity Signal

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

#### 7. When to Pause and Ask

Set expectations for when the implementing session should stop and ask rather than push forward.

**Example**:
```markdown
### Pause-and-Ask Conditions

**Pause and ask if**:
- Test data for null resource URIs not found in S3 sample files
- Legacy `LegacyFilter` behavior differs from documented expectation
- Scope expansion required beyond `PersonaFilter.java`
```

### How It Works

Four steps — full mechanics (including the YAML frontmatter template, the SKILL.md Writing
Disciplines template, and the Quality Gate checklist) live in `SKILL.md`'s own "How It Works"
section, not duplicated here, so this summary can't drift out of sync with it again:

1. **Context Gathering** — reads task details, searches the codebase for similar patterns,
   extracts architectural decisions, verifies facts (no assumptions).
2. **Document Generation** — writes the handoff to `~/.claude/handoff/active/<task-id>-<slug>.md`
   with YAML frontmatter (`key-files`, `verified-from`, and — if dispatched — a `dispatch:`
   block), a standard `## Before You Start` section, and the numbered context sections below.
3. **Quality Gate** — critical items must pass before the file is written (verified paths,
   no placeholders, explicit unknowns, scope boundaries, decision authority, pause-and-ask
   conditions).
4. **Live Dispatch (Optional)** — if the `aoe` CLI is present, optionally launches a real,
   separately-running `claude` sub-session and dispatches the handoff to it directly, instead of
   leaving that to a human. Always asked, never silently defaulted either way; see `SKILL.md`
   step 4 for the full branch-by-branch mechanics (path/worktree/naming resolution, readiness
   polling, dispatch-metadata recording, and the documented permission-prompt-stall limitation).

### File Naming Convention

Handoff documents are saved as `~/.claude/handoff/active/<task-id>-<slug>.md` (e.g.
`active/task-4.16.2-collection-indices-writer.md`). The same `<task-id>-<slug>` also doubles as
the aoe session title (optionally `~`-prefixed when parent-linked — see `SKILL.md`) and worktree
branch name if Live Dispatch runs.

### Key Philosophy

**Before**: Generic template-based handoffs  
**After**: Surgical precision with verified facts

**Prevents**:
- ❌ Wasting hours on wrong assumptions
- ❌ Discovering scope mid-implementation
- ❌ Hesitating about "should I TDD this?"
- ❌ Asking "am I done yet?"
- ❌ Repeating mistakes from failed PRs

### Integration with Project Standards

The skill automatically incorporates:
- **CLAUDE.md**: Architectural decisions, naming conventions
- **~/.claude/CLAUDE.md**: Coding standards (SOLID, TDD, refactoring)
- **Existing code**: Patterns from similar implementations
- **Legacy code**: References to previous implementations
- **Related PRs**: Successful patterns and failed attempts

### Quality Checklist

Every handoff document must have:

#### Critical Quality Gates (MUST HAVE)
- [ ] **Verified context** (NOT assumptions) - with file:line citations
- [ ] **Explicit unknowns** listed (what needs discovery)
- [ ] **Scope boundaries** clear (what to change + what NOT to change)
- [ ] **Decision authority** explicit (what implementer decides vs asks)
- [ ] **Acceptance criteria testable** (specific test names, checklists)

#### Essential Content (REQUIRED)
- [ ] Prior work referenced (similar patterns + anti-patterns)
- [ ] Known gotchas documented (edge cases, constraints)
- [ ] Complexity signal present (specific indicators, not "LOW/MEDIUM/HIGH" alone)
- [ ] Pause-and-ask conditions explicit

#### Self-Contained Verification
- [ ] Implementer can start without reading conversation history
- [ ] All file paths verified to exist
- [ ] All line number references accurate
- [ ] No "TODO: fill this in" sections

### Success Criteria

A good handoff document enables a fresh Claude session to:
- ✅ Understand the task without reading conversation history
- ✅ Know exactly what to implement and what is out of scope
- ✅ Have clear acceptance criteria for completion
- ✅ Follow project patterns and standards
- ✅ Make its own informed process decisions (TDD approach, xp-pair) from the complexity signal
- ✅ Know when to pause and ask rather than push forward
- ✅ Optionally, start working immediately via Live Dispatch instead of waiting on a human

### When to Use This Skill

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

### Inter-Agent Communication Pattern

This skill implements the **Handoff + Progress** pattern for inter-agent communication: the
handoff document is the stable spec (updated only on fundamental changes); the `-PROGRESS.md`
file is the mutable, primary channel the implementing agent uses to report decisions, progress,
and blockers back to the orchestrator — **never Claude memory**, which is for durable
cross-project preferences, not task-level state. If the implementing session was live-dispatched
(see Live Dispatch above), `aoe send` is available as a secondary, backup nudge channel — never a
substitute for updating the progress doc, which remains what actually gets read.

Full detail — the two files' exact contents and update policies, the orchestrator/implementer
responsibility split, precisely when the handoff itself may be updated (including the `dispatch:`
frontmatter carve-out), blockers-vs-observations conventions, and the archive lifecycle
(`active/` → `archive/`, including clearing a live-dispatched session's aoe color on archive) —
lives in `SKILL.md`'s "Inter-Agent Communication Pattern" section, not duplicated here.

