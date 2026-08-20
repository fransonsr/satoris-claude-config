# Continuation: {Session Name or Goal}

**Slug**: `{slug}`
**Session Kind**: `{orchestration | implementation | research | general}`
**Created**: {date}
**Last Checkpointed**: {date}
**Working Dir**: `{/absolute/path/to/working/directory}`
**Branch**: `{git branch or "none"}`
**Budget Directive**: `{e.g. "+500k" | none}`
**Workflow Run ID**: `{wf_abc123 — for resumeFromRunId | none}`
**Originating Handoff**: `{~/.claude/handoff/active/<task>.md — the handoff THIS session was launched to implement | none}`

*(When Originating Handoff is set, that document is the authoritative source for Mission,
Verified Context, Scope Clarity, Implementation Plan, Acceptance Criteria, and any process
mandate it carries — `/satori:xp-pair` per production commit, test-first, and the like. Do
NOT duplicate those here. This doc records only the delta: progress since, decisions and
scope corrections found during implementation, dead ends, and the next action. The path
must be verified on disk, not assumed.)*

**Active Handoffs**:

| Handoff Doc | Progress Doc | Orchestrator Status |
|---|---|---|
| `~/.claude/handoff/active/task-4.16.2-writer.md` | `~/.claude/handoff/active/task-4.16.2-collection-writer-PROGRESS.md` | Phase 2/3 in flight, no blockers |
| `~/.claude/handoff/active/bug-99-null-ref.md` | none yet | Implementing session not started |

*(or: none)*

---

## ▶ Re-Entry Instruction

You are resuming after a context clear. **Read this entire document before taking any
action.**

- **Do NOT** re-derive anything listed in "Established Facts" — it is already verified.
- **Do NOT** retry anything listed in "Dead Ends" — it was already rejected.
- **Your immediate next action is in "Next Action"** — execute it verbatim.
- **If "Originating Handoff" is set above, re-read that document in full before acting** —
  it holds this session's binding scope, acceptance criteria, and process mandates, and is
  deliberately not copied into this doc.

Resume by executing **Next Action**.

---

## Mission

{North-star goal in 1–2 sentences. Not a task list — the reason this session exists.

If an Originating Handoff is set in the frontmatter, keep this to a single orienting line
and let the handoff carry the full Mission — do not restate its Mission section here.

Example:}

Build the `handoff:continue` skill: a second skill in the handoff plugin that produces
in-session continuation prompts optimized for orchestration sessions, complete with a
PreCompact hook as a safety net against lossy auto-compaction.

---

## Plan State

{Phases with status markers. ✅ done / 🔄 in-flight / ⬜ pending. Example:}

| Phase | Status | Notes |
|---|---|---|
| 1 · Explore plugin structure | ✅ Done | Confirmed auto-discovery via install.sh:65 symlink |
| 2 · Design (plan mode) | ✅ Done | Plan approved; SKILL.md + template + hook + packaging |
| 3 · Create skills/continue/SKILL.md | 🔄 In-flight | Written; quality gate not yet run |
| 4 · Create CONTINUATION-template.md | ⬜ Pending | |
| 5 · Create PreCompact hook | ⬜ Pending | |
| 6 · Update CHANGELOG, plugin.json, README, install.sh | ⬜ Pending | |
| 7 · Verify + commit | ⬜ Pending | |

---

## Task State

{Open or in-progress tasks from the TaskTool. Run TaskList before writing this section.
Tasks do NOT survive /clear — capture everything here so the resumed session can
recreate or continue tracking them.

Format: ID · Title · Status · Notes. Example:}

| ID | Title | Status | Notes |
|---|---|---|---|
| 1 | Implement FooClass | in-progress | Method X done; method Y next |
| 2 | Write tests for FooClass | pending | Blocked on task 1 |
| 3 | Update changelog | pending | |

*(or: none — TaskList confirmed empty)*

---

## In-Conversation Findings

{Distilled findings from Explore/Plan/general agents spawned DIRECTLY in this session.
These are ephemeral — they vanish on /clear — so they must be captured here.

Delegated handoff sessions are NOT summarized here. Their findings live in their PROGRESS
docs; see the frontmatter Active Handoffs table above.

Format: agent role → distilled finding → impact on the plan. Example:}

**Explore (plugin structure & auto-discovery)**:
- Asked: How is the handoff plugin structured and how does skill discovery work?
- Found: `install.sh:65` symlinks the whole repo as a marketplace. Any
  `plugins/<name>/skills/<skill-name>/SKILL.md` auto-surfaces as `name:skill-name`.
  No marketplace.json change needed for a new skill in an existing plugin.
- Impact: Second skill lives at `plugins/satori/skills/continue/SKILL.md` and
  auto-discovers as `satori:continue` at zero registration cost.

**Explore (PreCompact hook mechanics via claude-code-guide)**:
- Asked: Can a PreCompact hook invoke a skill, or only inject text / block?
- Found: Hooks are shell commands only. They can block auto-compaction via
  `{"decision":"block","reason":"..."}` stdout + exit 0. They cannot invoke agentic
  skills. Matcher field `auto` / `manual` on the settings.json entry controls which
  compaction trigger fires the hook.
- Impact: Hook design shifted from "auto-run the skill" to "block + remind user to
  run manually". Converts silent lossy event into visible decision point.

*(or: none yet)*

---

## Established Facts (Do NOT Re-Derive)

{Verified facts with citations. A fresh session must not re-research these. Example:}

- **Skill auto-discovery**: `install.sh:65` symlinks repo to
  `~/.claude/plugins/marketplaces/satoris-claude-config`. Any
  `plugins/<x>/skills/<y>/SKILL.md` surfaces as `x:y` — no registration step.
- **Quality-gate pattern**: lines 183–202 of
  `plugins/satori/skills/handoff/SKILL.md` — reuse for continue's gate.
- **PreCompact stdin JSON shape**: `{"session_id":"...","transcript_path":"...","cwd":"...","hook_event_name":"PreCompact","trigger":"auto|manual"}`.
- **Block response format**: `{"decision":"block","reason":"..."}` on stdout + exit 0.
- **Memory boundary warning** (verbatim-ish reuse): `plugins/satori/skills/handoff/SKILL.md:289–291`.

*(or: none yet)*

---

## Decisions & Pivots

{Key calls made this session and WHY — including pivots that changed direction.
Example:}

**Decision: PreCompact hook blocks auto-compaction; it does NOT run the skill**
- Why: Hooks are shell commands; they cannot invoke agentic skills. The achievable
  value is converting auto-compaction from silent+lossy to visible+interruptible.
  Explicit `/compact` remains the user's one-word override.

**Decision: Continuation doc links to PROGRESS docs; does not re-summarize them**
- Why: The PROGRESS doc is the established communication channel for delegated
  sessions. Duplicating its content into the continuation creates two sources of truth
  and divergence risk across checkpoints.

**Decision: Verified PROGRESS-doc path in frontmatter, not assumed name**
- Why: Sessions drift on PROGRESS naming. The quality gate catches naming drift at
  checkpoint time rather than at resume time when it would be harder to recover.

**Pivot: Hook ships via install.sh → settings.json (not a native plugin hook)**
- Why: Plugin-level hook auto-discovery is not a documented Claude Code feature.
  install.sh is the established integration mechanism; it already handles symlinks
  and can safely add a hook entry via jq.

*(or: none yet)*

---

## Dead Ends (Do NOT Retry)

{Approaches tried and rejected, with reasons. The anti-retry lock.
A resumed session must not re-attempt these — it is a waste and will reach the same
conclusion. Example:}

**Auto-running the skill from a PreCompact hook**
- Tried: Hook that invokes `/handoff:continue` directly on auto-compaction
- Rejected: Hooks are shell commands; cannot invoke agentic skills or trigger
  model-driven tool use
- Alternative taken: Hook blocks auto-compaction and reminds user to run manually

**Plugin-level hooks.json auto-discovery**
- Tried: Placing `hooks.json` in the plugin expecting Claude Code to auto-discover it
- Rejected: Not a documented Claude Code plugin feature
- Alternative taken: `hooks.json` is declarative documentation; `install.sh` wires
  the actual hook entry into `~/.claude/settings.json`

*(or: none yet)*

---

## Open Questions / Blockers

{Unresolved items waiting on user or external input. Note whether it blocks forward
progress. Example:}

- None at this checkpoint.

*(or:)*

- **Blocker**: Uncertain about X — cannot proceed with phase N without clarification.
- **FYI**: Noticed Y during implementation; no reply needed, just documenting.

---

## Next Action

{**Verbatim and executable.** A fresh session executes this immediately after reading
this document. Name the exact command, phase, agent prompt, or file to work on.
Example:}

Create `plugins/satori/skills/handoff/templates/CONTINUATION-template.md` using the section
structure defined in the approved plan at `~/.claude/plans/distributed-petting-mountain.md`.
Model the style after `plugins/satori/skills/handoff/templates/IMPLEMENTATION-PROGRESS-template.md` —
frontmatter + sectioned body with inline filled examples.

---

## Working State

{Files touched this session, uncommitted changes, in-flight workflow run IDs.
Example:}

**Files created/modified this session** (not yet committed):
- `plugins/satori/skills/continue/SKILL.md` — created
- `plugins/satori/skills/handoff/templates/CONTINUATION-template.md` — created (in-flight)

**Uncommitted changes**: Run `git diff --stat` on resume to confirm current state

**In-flight Workflow Run ID**: `wf_abc123` (pass as `resumeFromRunId` to continue)
*(or: none)*
