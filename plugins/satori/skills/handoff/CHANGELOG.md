# Changelog

All notable changes to the Handoff plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.1] - 2026-08-24

### Fixed

- **Live Dispatch readiness check** — the `2.7.0` readiness poll was built on a disproven premise:
  `aoe session show --json`'s `status` field was believed unable to distinguish "blocked on the
  first-run trust dialog" from "genuinely ready," requiring a positive pane-content match instead.
  Verified directly against a real trust dialog (a worktree of an *already-trusted* repo never
  reproduces it — trust is inherited at the repo level, confirmed by two dispatches that landed in
  a new worktree and never saw the dialog; a genuinely fresh, never-opened directory does):
  `status` reads `"waiting"` while any interactive prompt blocks (the trust dialog, or a later,
  unrelated permission prompt), `"running"` while processing, `"idle"` once genuinely ready.
  Simplified the check to poll `status` directly instead of pane-content marker matching, which
  also correctly generalizes past the first-run dialog specifically

### Changed

- **"Known limitation" reframed as "by design"** — Live Dispatch's readiness poll exists only to
  protect the one thing it automates without a human present: the single kickoff message. It was
  never meant to extend into watching for or working around *later* permission prompts, even
  though the corrected `status` check above would technically support that. Once the kickoff
  lands, the intended model is the same as any session started by hand — the user is expected to
  shift attention to it and grant whatever permissions it asks for as they come up

## [2.7.0] - 2026-08-21

### Added

- **Live Dispatch (Optional)** — `How It Works` step 4. When the `aoe` CLI is present, offers to
  launch a real, separately-running `claude` sub-session and dispatch the handoff to it directly,
  instead of leaving a human to start the next session manually
  - Always asked via `AskUserQuestion` when `aoe` is present, never silently defaulted either
    way; skipped entirely (no question) when `aoe` is absent
  - Resolves the launch path from `key-files` plus the new `verified-from` anchor (below),
    computing each key-file's actual git repo root rather than inferring one from bare relative
    strings; explicit stop-and-ask on a genuine multi-repo span
  - Defers to an existing fleet worktree convention when one is detected; otherwise offers aoe's
    own worktree creation as a recommended default
  - Session id resolved by parsing `aoe add`'s stdout `ID:` line (verified reliable); parent
    linkage (`-P`) attempted when the orchestrating session is itself aoe-managed, with a
    detect-and-retry-standalone fallback for aoe's single-level sub-session-nesting limit
  - Interim `~`-prefix naming convention for parent-linked session titles — cosmetic workaround
    for [agent-of-empires/agent-of-empires#3472](https://github.com/agent-of-empires/agent-of-empires/issues/3472)
    (parent/child linkage tracked by aoe but not yet rendered in `aoe list`/the TUI); a leading
    `-` and a trailing marker were both tried and rejected (clap misparses the former;
    column-truncation eats the latter)
  - Readiness detected via pane-content matching (`aoe session capture`) at the time this
    shipped — corrected in `2.7.1` above to a simpler, more accurate `status`-field check
  - `dispatch:` metadata (`aoe-session-id`, `aoe-session-title`, `launched-path`,
    `launched-at`) recorded in the handoff's frontmatter immediately after the session is
    created — the one frontmatter field this skill updates outside its normal "stable spec"
    policy
- **`verified-from` frontmatter field** — records the absolute cwd `key-files` were verified
  against at generation time, for every handoff (not only dispatched ones). `key-files` stay
  intentionally relative (so a single handoff stays valid across worktrees of the same repo);
  `verified-from` is what makes them resolvable again later, including by a different session in
  a different cwd
- **`## Before You Start`** — new standard section in every generated handoff document (not only
  dispatched ones): directs the implementing session to create its progress doc immediately and,
  if aoe-managed, mirror progress-doc `**Status**` into its own aoe session color
- **"aoe as a Backup/Live Communication Channel"** — new subsection under "Inter-Agent
  Communication Pattern" documenting `aoe send` as a secondary, backup nudge channel for a
  live-dispatched session — never a substitute for the `-PROGRESS.md` file, which remains primary

### Changed

- **File Naming Convention** — notes that `<task-id>-<slug>` also doubles as the aoe session
  title (optionally `~`-prefixed) and worktree branch name when Live Dispatch runs
- **"When to Update Handoff Document"** — carved out an exception for the `dispatch:`
  frontmatter block, written by the Live Dispatch step itself as routine bookkeeping, not a
  fundamental architecture change
- **Handoff Lifecycle** — archiving a live-dispatched handoff now also clears that session's aoe
  color (best-effort, with a surfaced warning on failure rather than one silently swallowed)
- **README.md** — collapsed several sections (`How It Works` detail, `File Naming Convention`
  detail, `Inter-Agent Communication Pattern`'s subsections) that had drifted out of sync with
  `SKILL.md` into short summaries with explicit pointers, rather than re-syncing duplicated
  content that would only drift again

## [2.6.0] - 2026-08-20

### Added

- **`continue`: originating-handoff case** — a third case in "PROGRESS Docs: Link, Don't
  Duplicate", distinct from the two existing ones (which cover handoffs *this* session
  delegated OUT). When the checkpointed session is itself implementing a `/satori:handoff`
  document, the continuation records only the delta: verified handoff path, progress since,
  decisions and scope corrections found during implementation, implementation-specific dead
  ends, and the verbatim next action
  - **Do NOT** restate the handoff's Mission, Verified Context, Scope Clarity,
    Implementation Plan, or Acceptance Criteria — including any process mandate it carries
    (`/satori:xp-pair` per production commit, test-first). Those are recovered by re-reading
    the handoff on resume, per the "re-anchor on compaction" rule in global `CLAUDE.md`
  - Root cause addressed: a handoff's `/satori:xp-pair` mandate was silently dropped across
    a mid-implementation compaction and never followed for a 5-PR effort. Copying a mandate
    into a checkpoint doc is how it drifts or disappears; never copying it is what makes it
    survive
- **`How It Works` step 2** — now covers delegated *and* originating handoffs; added the
  step to identify this session's own originating handoff and record its verified path
- **CONTINUATION-template.md `Originating Handoff` field** — singular frontmatter field
  (this session's own handoff) alongside the existing delegated-out Active Handoffs table,
  with an inline note that Mission/Scope/Plan/Acceptance Criteria are not duplicated when it
  is set; Re-Entry Instruction gained a re-read bullet, and the Mission section a note to
  stay to one orienting line when the field is set

### Changed

- **Quality Gate Critical checklist** — added: "Originating handoff linked, not duplicated"
  (path verified on disk; content delta-recorded only, or explicitly "none")
- **Quality Gate Essential "No skill instruction content"** — clarified that the exclusion
  covers skill *methodology*, not a task-specific mandate to *invoke* a skill; such a mandate
  stays in the originating handoff (recovered by re-read) or, absent one, is live state and
  must be recorded

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
