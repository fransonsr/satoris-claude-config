---
name: xp-pair
description: XP pair programming with navigator (design oversight) and driver (implementation). Use for complex features requiring design oversight, TDD coaching, or high-quality code with continuous review.
argument-hint: [task-description | "Task: ... Acceptance Criteria: ..."]
---

# XP Pair Programming

Creates a two-person XP pairing team:
- **Navigator** (the main session): design oversight, architectural decisions, code review, TDD enforcement, and (via a Fable-model design-synthesis agent) generative design guidance before implementation starts
- **Driver** (subagent): implementation, coding, following TDD discipline

**This file is an overview, not the procedure.** `SKILL.md` in this directory is the source of
truth for the actual step-by-step workflow, the driver instructions template, the Communication
Protocol, and the Future Improvements / session-learnings log. This file previously carried a
full, independently maintained copy of that content and had drifted out of sync with it (a stale
`argument-hint`, no `## Inputs` contract, no Fable design-guidance step) — it now covers only the
"when to use" framing and a pointer.

- **Full step-by-step procedure**: see `SKILL.md`

## When to Use

**Good use cases:**
- Complex features requiring design oversight
- High-risk code (security, data loss potential)
- Multiple valid design approaches needing discussion
- Code with unclear requirements needing collaboration

**Skip it for:**
- Simple CRUD operations or straightforward validation
- Documentation-only work
- Trivial bug fixes (< 50 lines changed)
- Time-sensitive tasks (pairing has overhead)
- Obvious implementations with predetermined design

**Before spawning a driver, assess if the task truly needs collaborative oversight** — if
complexity doesn't clearly warrant pairing, discuss with the user first rather than defaulting
to it. See `SKILL.md`'s "XP-Pair Decision Checklist" and "Things that SEEM simple but
consistently hide bugs" list for the specific complexity signals worth checking against before
deciding either way.
