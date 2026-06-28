# Changelog

All notable changes to the Handoff plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.0] - 2026-06-28

### Added

- **SKILL.md Writing Disciplines** — conditional section generated in handoff documents when
  any `key-files` are SKILL.md files
  - Delegates three pre-write disciplines to the implementing session (orchestration session
    does NOT execute them — keeps its context clean)
  - **Discipline 1: Scope-term grep pre-flight** — identify and grep all old scope terms
    before touching the file; mark each hit "update needed" or "no change needed" first
  - **Discipline 2: Branch enumeration** — enumerate every decision branch explicitly before
    writing any conditional prose; a branch with no documented path is a Copilot finding
    waiting to happen
  - **Discipline 3: Pre-commit operator read** — read modified sections linearly as a
    first-time operator with no knowledge of intent; flag every step where guessing is
    required; fix before committing
  - Root cause addressed: three classes of PR #106's 22-thread Copilot sweep (stale-scope
    text, missing conditional branches, operator executability gaps) all arose from
    implementing correctly as the author but not as an operator

### Changed

- **Quality Gate Critical checklist** — added conditional: "If any `key-files` are SKILL.md
  files: SKILL.md Writing Disciplines section is present" (enforces the new conditional)

## [2.4.0] - 2026-06-17

### Added

- **`handoff:continue` skill** — in-session continuation prompts for `/clear`-based context refresh
  - Produces a self-contained continuation document at `~/.claude/handoff/continue/<slug>-CONTINUATION.md`
  - Optimized for **orchestration sessions** where compaction is most damaging (agent results flood context; coordinator pivot reasoning is exactly what gets summarized away)
  - Works for any long or complex session (general-purpose, orchestration-emphasized)
  - **Manual invocation discipline**: `/handoff:continue [slug]` — run before a large fan-out, at phase boundaries, or before ending a resumable session
  - **Soft suggestions**: skill instructs Claude to proactively suggest checkpoints at natural boundaries
  - Captures: plan phase state, direct subagent findings, decisions/pivots, dead ends, open questions, verbatim next action
  - PROGRESS docs for delegated handoffs are **linked (verified path), never duplicated**; the PROGRESS doc remains the single source of truth for delegated sessions
  - Quality gate mirrors the `handoff` skill: no doc written until all Critical items pass

- **CONTINUATION-template.md** — template for continuation documents
  - YAML frontmatter: slug, session-kind, timestamps, working-dir, branch, budget-directive, workflow-run-id, active-handoffs with verified handoff + progress doc paths
  - Sections: Re-Entry Instruction, Mission, Plan State (✅/🔄/⬜), In-Conversation Findings (distilled direct agent results), Established Facts (anti-re-derivation), Decisions & Pivots, Dead Ends (anti-retry), Open Questions/Blockers, Next Action (verbatim executable), Working State
  - All sections include filled examples following the IMPLEMENTATION-PROGRESS-template style

### Changed

- Plugin now bundles **two skills**: `handoff` (task specification) and `continue` (in-session continuation)
- Plugin `description` updated to reflect both skills
- README updated with `continue` documentation and the handoff-vs-continue comparison table

## [2.3.0] - 2026-06-11

### Added

- **YAML frontmatter on generated handoff documents**
  - Every generated handoff now begins with structured metadata: `task-id`, `task-type`,
    `repo`, `branch-from`, `plugin-version`, `key-files`, `dependencies-complete`,
    `estimated-complexity`
  - Receiving agent can pre-load context and determine xp-pair vs solo without reading prose
  - `key-files` paths verified to exist before writing the document

- **Feedback taxonomy in PROGRESS template**
  - Replaced single "Questions for Orchestrating Agent" section with two explicit sections:
    `### Blockers` (hard stops requiring orchestrator reply) and `### Observations`
    (corrections/surprises that don't block progress)
  - Prevents actionable blockers from being buried in informational text
  - Orchestrating session scans `### Blockers` first

- **Checklist-gated generation workflow**
  - Quality checklist promoted from post-hoc documentation to an explicit generation gate
    (step 3 of "How It Works")
  - Handoff is not written until all Critical items pass
  - Critical gate: paths verified, line numbers confirmed, no TODOs, no invented references,
    explicit unknowns present, scope boundaries clear, pause-and-ask conditions explicit

### Changed

- **`active/` directory enforced throughout**
  - Generation step now runs `mkdir -p ~/.claude/handoff/active` before writing
  - All path references in SKILL.md consistently use `~/.claude/handoff/active/`
  - PROGRESS template header updated to reflect `active/` path
  - "Inter-Agent Communication" section updated with blocker/observation guidance

## [2.2.0] - 2026-06-11

### Added

- **Handoff lifecycle (active/archive)**
  - Documents live in `~/.claude/handoff/active/` while in flight
  - Orchestrating session moves to `~/.claude/handoff/archive/` on completion
  - Preserves audit trail while keeping `active/` small and scannable

### Changed

- All path references updated from flat `~/.claude/handoff/` to `~/.claude/handoff/active/`

## [2.1.1] - 2026-06-10

### Changed

- **Clarified that Claude memory must NOT be used for inter-agent communication**
  - Added prominent warning in Two-File Approach section
  - Progress document is the only feedback channel back to the orchestrator
  - Memory is for durable cross-project preferences, not task-level progress noise

## [2.0.0] - 2026-05-18

### Changed (BREAKING)

- **Implemented Handoff + Progress pattern for inter-agent communication**
  - Handoff documents now specification-only (immutable)
  - Implementing agents create separate progress document (mutable)
  - Clear separation between "what to build" (handoff) and "how we're building it" (progress)

### Added

- **IMPLEMENTATION-PROGRESS-template.md** - Comprehensive template for progress tracking
  - Architectural decision records (date, rationale, impact, files affected)
  - Progress checklist
  - Current blockers section
  - Questions for orchestrating agent
  - Deviations from original spec
  - Notes & observations

- **Inter-Agent Communication Pattern documentation**
  - Two-file approach (handoff + progress)
  - Responsibility model (orchestrating vs implementing agents)
  - Guidelines on when to update handoff vs progress
  - Examples of appropriate use cases

- **Benefits section** documenting advantages:
  - Clean specification (handoff remains focused)
  - Clear progress tracking (evolution captured separately)
  - Better communication (questions don't pollute spec)
  - Audit trail (decisions captured with context)

### Migration Guide

**No migration required** for existing handoff documents. They remain valid as-is since they are one-time use documents.

**For future handoffs** (v2.0.0+):
1. Orchestrating agent creates handoff document (specification only)
2. Implementing agent reads handoff (does not modify)
3. Implementing agent creates progress document on first session
4. Implementing agent updates progress frequently during work
5. Orchestrating agent reviews progress to answer questions

**Key principle**: Handoff = immutable specification, Progress = mutable implementation tracking

### Why This Change?

Through real-world usage in the java-stack-logging-maven-plugin project, we discovered that implementing agents updating handoff documents caused confusion:
- Mixed immutable specifications with mutable progress
- Unclear what was original spec vs what evolved during implementation
- Example: "Filtered (traditional only)" - was this spec or progress?

The two-file approach solves this by maintaining clean separation of concerns.

## [1.0.0] - 2026-05-12

### Added

- Initial release of handoff skill
- Comprehensive handoff document generation
- Verified context with file:line citations
- Explicit unknowns tracking
- Scope boundaries (what to change vs what NOT to change)
- Decision authority guidelines
- Prior work patterns and anti-patterns
- Known gotchas and constraints
- Testable acceptance criteria
- Test strategy justification
- Iteration expectations
- Skill routing recommendations
- Quality validation (file paths, line numbers)
- Integration with CLAUDE.md and coding standards
