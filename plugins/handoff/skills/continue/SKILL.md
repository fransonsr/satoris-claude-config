---
name: continue
description: "ONLY invoke when the user explicitly requests a session checkpoint or says '/handoff:continue'. Builds a self-contained continuation doc to resume after /clear — capturing plan state, agent findings, decisions/pivots, dead ends, and the verbatim next action. Do NOT trigger on conversational use of 'continue' or 'proceed'."
argument-hint: "[session-slug]"
---

# Session Continuation Skill

Produces a self-contained **continuation document** that lets you resume the current
session with full fidelity after `/clear` — avoiding the lossy summaries that automatic
compaction produces.

Optimized for **orchestration sessions** where context fills fastest (agent results flood
in) and compaction is most damaging (the coordinator's pivot reasoning is exactly what gets
summarized away). Works for any long or complex session.

## Usage

```
/handoff:continue [slug]
```

**Examples**:
- `/handoff:continue` — slug derived from working dir / branch / primary active task
- `/handoff:continue sls-bi-phase3` — explicit slug for a named orchestration effort
- `/handoff:continue bugfix-kafka-retry` — implementation session checkpoint

**Output**: `~/.claude/handoff/continue/<slug>-CONTINUATION.md`

**Resume command** (paste after `/clear`):
```
Read ~/.claude/handoff/continue/<slug>-CONTINUATION.md and resume.
```

---

## How `continue` Differs from `handoff`

| | `/handoff` | `/handoff:continue` |
|---|---|---|
| Audience | A *different* fresh session / worker | The *same* worker, post-`/clear` |
| Background | Includes project background + specs | Assumes same goals — **no** background |
| Focus | "What to build" spec + acceptance criteria | Live state + **verbatim next step** |
| Lifecycle | Immutable spec + separate PROGRESS doc | Single file, overwritten each checkpoint |
| Trigger | Before delegating a task | Checkpoint during a long session |

---

## When to Run (Checkpoint Discipline)

**Run `/handoff:continue` before:**
- A large fan-out: `parallel()` / `pipeline()` calls or many `Agent` invocations whose
  results will flood context
- Crossing a phase boundary in a multi-phase plan
- Ending a session you intend to resume
- Context feels roughly 50–60% full — *before* quality degrades

**⚠️ Anti-pattern: running it after compaction already fired** — the clean context
window is gone and the state you would capture is already degraded. The skill pays
off when run *before* the flood, not after.

**⚠️ Anti-pattern: running at the very start** — the doc encodes live state. At session
start there is no state to capture.

---

## Proactive Checkpoint Suggestions

During long sessions, **Claude should proactively suggest a checkpoint** at natural
boundaries — without waiting to be asked:
- "I'm about to spawn N agents"
- "I'm about to start phase X"
- "Context is getting large"
- "This looks like a good stopping point"

**You always decide** whether to actually run the skill. The suggestion is the nudge;
`/handoff:continue` is the action.

---

## PROGRESS Docs: Link, Don't Duplicate

The continuation doc distinguishes two kinds of in-session findings:

**In-conversation subagents** (Explore/Plan/general agents spawned *directly* in this
session):
- Their findings are **ephemeral** — they vanish on `/clear`
- **Must** be distilled into the continuation doc under "In-Conversation Findings"

**Delegated handoff sessions** (work handed off via `/handoff`):
- Their findings, reports, questions, and blockers live in the **PROGRESS doc** —
  that is the established communication channel
- The continuation records only *orchestrator-side* status (phase progress, any
  blockers flagged) and the **actual, verified path** to the PROGRESS doc
- **Do NOT** re-summarize PROGRESS doc content into the continuation — that creates
  two sources of truth

### Why Verified Paths Matter

Sessions drift on PROGRESS-doc naming (e.g., `task-4.16.2-impl-PROGRESS.md` vs
`task-4.16.2-collection-writer-PROGRESS.md`). The continuation must record the
**actual path found on disk**, not an assumed name. The quality gate verifies these
paths exist before writing.

---

## How It Works

1. **Gather live state** from the current conversation:
   - Active plan phase and status (per phase)
   - Direct subagent calls made this session and their distilled findings
   - Key decisions made and pivots taken (with the *why*)
   - Approaches that failed — dead ends — and why they were rejected
   - Open questions or blockers awaiting the user
   - The exact, verbatim next action

2. **Gather handoff references** (if any active handoffs):
   - Scan `~/.claude/handoff/active/` to locate actual handoff docs
   - For each: find the actual PROGRESS doc path (do not assume the name)
   - Summarize orchestrator-side status from the PROGRESS doc; do not copy its content

3. **Run `mkdir -p ~/.claude/handoff/continue`** (idempotent)

4. **Fill the CONTINUATION template** at:
   ```
   ~/.claude/plugins/*/handoff/templates/CONTINUATION-template.md
   ```
   (or equivalent resolved path)

5. **Run the quality gate** — do not write the file until all items pass (see below)

6. **Write** `~/.claude/handoff/continue/<slug>-CONTINUATION.md`
   - Overwrite if the file already exists (this is a checkpoint, not an archive)
   - Update `last-checkpointed` with today's date

7. **Print the resume command** the user pastes after `/clear`:
   ```
   Read ~/.claude/handoff/continue/<slug>-CONTINUATION.md and resume.
   ```

---

## Quality Gate (Do Not Write Until All Pass)

**Critical (MUST pass)**:
- [ ] **Next Action is concrete and executable** — names a specific phase, agent prompt,
      command, or args; not "continue the work"
- [ ] **Established Facts carry citations** — file:line or commit hash; no unverified claims
- [ ] **In-Conversation Findings populated** — or explicitly "none yet" (not omitted)
- [ ] **Dead Ends populated** — or explicitly "none yet" (not omitted)
- [ ] **Active handoff paths verified** — for each `active-handoffs` entry:
      `handoff:` path exists on disk; `progress:` path exists on disk (or explicit
      "none yet" if the implementing session hasn't created it)
- [ ] **Re-entry instruction present** at top of body section
- [ ] **`last-checkpointed` is current** (today's date)
- [ ] **No TODO/placeholder sections** remain
- [ ] **No invented file paths, commit hashes, or references**

**Essential (REQUIRED)**:
- [ ] Mission is 1–2 sentences, north-star framing (not a task list)
- [ ] Plan State uses status markers (✅ done / 🔄 in-flight / ⬜ pending)
- [ ] Decisions & Pivots record the *why*, not just the decision

If any Critical item fails: fix it before writing. Do not write a continuation doc
with known gaps.

---

## File Naming & Slug

Continuation documents are saved as:
```
~/.claude/handoff/continue/<slug>-CONTINUATION.md
```

**Slug is session-scoped** (one effort = one slug), not handoff-scoped. An orchestration
session managing multiple handoffs uses a single continuation doc.

**Slug derivation** (if not supplied as arg):
1. Active task ID or primary active handoff name, if unambiguous
2. Working dir basename + git branch (e.g., `satoris-claude-config-master`)
3. Ask the user if neither is clear enough

**Examples**:
- `~/.claude/handoff/continue/sls-bi-phase3-CONTINUATION.md`
- `~/.claude/handoff/continue/bugfix-kafka-retry-CONTINUATION.md`
- `~/.claude/handoff/continue/satoris-claude-config-master-CONTINUATION.md`

---

## Memory Boundary

> **⚠️ Do NOT use Claude memory for continuation state.**
> Live task state, plan progress, agent findings, and decisions belong in the
> continuation doc — not in memory. Memory is for durable cross-project preferences,
> not session-level progress that would clutter future unrelated sessions.

---

## Relationship to Other Skills

- **`/handoff`** — creates a spec for a *different* worker. `continue` is for your own
  continuity after `/clear`. The two compose naturally: an orchestration session may
  create handoffs for delegated work *and* use `continue` to preserve its own
  coordinator state.
- **Orchestration discipline** — per the established pattern, orchestration sessions
  hand off *execution* work at round 1. `continue` is for the orchestrator's own context
  across clears, not for delegating implementation.

---

## Key Philosophy

The gap between compaction and `continue`:

| | Auto-Compaction | `/handoff:continue` |
|---|---|---|
| Decisions & pivots | Summarized (lossy) | Preserved verbatim |
| Dead ends | May be lost | Explicit anti-retry record |
| Direct agent findings | Summarized | Distilled by you |
| Next action | Inferred from summary | Written exactly |
| PROGRESS doc references | Lost | Verified paths preserved |
| Active handoff status | Lost | Orchestrator-side status captured |

Compaction is good enough for short sessions. `continue` pays off on:
- Long orchestration sessions managing multiple workstreams
- Sessions with complex pivot history
- Any session where "what did we try and reject" is load-bearing context

## Success Criteria

A good continuation document enables a fresh session to:
- ✅ Resume immediately without orientation questions
- ✅ Not re-derive already-established facts
- ✅ Not retry approaches already rejected
- ✅ Know the exact state of all delegated handoffs (via verified PROGRESS paths)
- ✅ Execute the verbatim next action without interpretation
