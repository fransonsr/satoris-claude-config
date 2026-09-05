# aoe session-tracking transcript collision

## Symptom

An aoe-managed session's own "which Claude Code transcript is this?" mapping gets silently
overwritten to point at a *different* conversation's transcript — not the session's own. Attaching
to the session, or anything reading its history, then shows the wrong conversation. No error is
raised; the session just quietly starts resolving to someone else's transcript.

Confirmed against a real, live orchestrating session during this investigation (aoe session
`b2ac292b9ecb41c8`, "Research jdtls-lsp crash fix") — see below.

## Confirmed mechanism

aoe logs the exact swap in `~/.config/agent-of-empires/debug.log`, target `session.store`, in a
literal message template:

```
session.store: Replacing stored session id with fresher live observation stale=<uuid> fresh=<uuid> tool=claude
```

This is aoe explicitly overwriting its own stored Claude Code session-id mapping for a tracked
session with whatever candidate transcript it most recently observed as "fresher" — evidently with
no check for whether that candidate transcript actually belongs to the session being tracked. The
comparison runs continuously as part of normal live status tracking, not only at daemon startup —
see Q2 below.

**Direct evidence, `b2ac292b9ecb41c8` (this session's own orchestrator), `debug.log:110559`:**
```
2026-09-04T19:33:37.947505Z  INFO session.startup_recovery: TUI starting recovery for missing tmux sessions count=5
2026-09-04T19:33:40.615324Z  INFO session.store: Replacing stored session id with fresher live observation stale=022009b1-fa35-416f-9d12-5befcba392c6 fresh=7f2e617e-0da2-47f9-b5f4-85805d4db3bd tool=claude
2026-09-04T19:33:41.074197Z  INFO session.store: Session ID observed for b2ac292b9ecb41c8: 7f2e617e-0da2-47f9-b5f4-85805d4db3bd
2026-09-04T19:33:42.942788Z  INFO session.startup_recovery: resumed id=b2ac292b9ecb41c8 title=Research jdtls-lsp crash fix
```
`022009b1-fa35-416f-9d12-5befcba392c6` is that session's real, current, top-level transcript
(opens with `{"type":"last-prompt",...}`). `7f2e617e-0da2-47f9-b5f4-85805d4db3bd` is a leftover
transcript from an in-process `Agent`-tool subagent that session had dispatched earlier (opens
with `{"type":"agent-setting","agentSetting":"general-purpose","sessionId":"7f2e617e-..."}`).
Re-verified 2026-09-05: `b2ac292b9ecb41c8`'s Claude Code project directory
(`~/.claude/projects/-home-fransonsr--config-agent-of-empires-scratch-b2ac292b9ecb41c8/`) contains
dozens of these flat sibling `.jsonl` files, each opening with the same `agent-setting` marker —
every one of them a past subagent's leftover transcript, sitting as a plain sibling of the real
transcript in the same directory, all dated 2026-09-03–04 (see the CLI-version caveat below).

Two distinct shapes of "shared directory" have been confirmed to trigger this, plus a third,
related-but-not-fully-disentangled failure mode. Do not assume they're the same bug just because
they share the same log message — only shape 1 is closed by an existing fix.

## Trigger shape 1: sibling Live-Dispatch sessions sharing a directory — mostly fixed

Multiple *separate, aoe-managed* sessions (not subagents — genuine sibling top-level Claude Code
processes) launched into the same, un-worktreed directory. Each one's Claude Code transcript lives
in the same project directory (transcripts are keyed by launch cwd), so aoe's live-observation
heuristic can't tell which file belongs to which aoe session — it picks whichever transcript was
most recently touched, regardless of which sibling actually owns it.

**Confirmed instance**, `debug.log:17308` (2026-08-19), independent of the `b2ac292b9ecb41c8`
incident above:
```
2026-08-19T17:38:47.352153Z  INFO session.store: Session ID observed for cd86d2f7105a45ab: 39cf76e3-8943-4d33-9dba-f8ce91305ce3
2026-08-19T17:38:47.668502Z  INFO session.store: Replacing stored session id with fresher live observation stale=e8c98e11-8666-4100-b589-f1e369d6cb74 fresh=39cf76e3-8943-4d33-9dba-f8ce91305ce3 tool=claude
```
`cd86d2f7105a45ab` (tmux target `aoe_refit_cd86d2f7`, title "refit" — an `rp-fleet:refit`
dispatch) had its own stored sid overwritten with `39cf76e3-...`, a transcript that actually
belongs to a *different* session (`992665cfd23b4276`, a structured-ACP session that had captured
that same id nine minutes earlier at 17:29:01, and which session `226952c064a240ac`, title
"locking issue - parent", had also separately observed at 17:29:50). Three distinct aoe sessions
resolving to the same underlying transcript at different points is a clean confirmation of the
directory-sharing mechanism, independent of the subagent-marker case.

**This shape is the one `plugins/satori/skills/handoff/CHANGELOG.md`'s `[2.7.2]` and `[2.8.0]`
entries already fixed**: `[2.7.2]` (2026-08-28) closed the specific case where Live Dispatch's
worktree-decision step silently no-opped when the launch path was a fleet workspace root itself;
`[2.8.0]` (2026-08-28) removed the option to decline a worktree at all, for the general case. Both
postdate the 2026-08-19 instance above by over a week — plausibly the same incident class that
motivated the fix, though the exact confirmed-production incident `[2.7.2]` describes ("three
live-dispatched sessions landed directly in a shared, un-worktreed workspace-root checkout") isn't
independently re-confirmed against this specific log line. Since Live Dispatch, as of `[2.8.0]`,
always creates a worktree, this shape should no longer be reachable through Live Dispatch going
forward — but it remains fully reachable through any *other* path that launches two aoe sessions
into the same directory (e.g., an aoe session created by hand without `-w`/`-b`).

## Trigger shape 2: in-process `Agent`-tool subagents sharing the coordinator's directory — not fixed, and only partly current

A coordinator session dispatches an `Agent`-tool subagent. The subagent is not a new aoe-managed
session or even a new top-level Claude Code process — it runs in-process within the coordinator's
own conversation. This shape is what
[fs-eng/records-platform-workspace#175](https://github.com/fs-eng/records-platform-workspace/issues/175)
describes from `rp-fleet:refit`'s dispatch-loop angle, and what actually hit `b2ac292b9ecb41c8`
above.

**This is a different bug from shape 1, and the `[2.8.0]` fix does nothing for it**: `[2.8.0]`'s
fix is entirely about Live Dispatch's worktree-creation decision for *new aoe sessions*. A subagent
dispatched via the `Agent` tool from inside an already-running session was never subject to that
decision at all — there's no separate aoe session being created, no worktree question to ask,
nothing for `[2.8.0]` to intercept.

**A materially dated finding, re-verify before relying on it**: the flat sibling
`{"type":"agent-setting",...}` transcript layout confirmed above is what the currently-installed
Claude Code CLI produced through at least 2026-09-04. As of 2026-09-05, with CLI **2.1.261**
installed, a fresh empirical test (see "What was tested" below) shows subagent transcripts are no
longer written as flat siblings in the project directory at all — they're nested at
`<parent-project-dir>/<parent-session-id>/subagents/agent-<id>.jsonl`, keyed by the parent's own
session identity rather than sitting as a plain file next to it. This may structurally reduce or
eliminate this exact vector going forward, purely as a side effect of a Claude Code CLI storage
change unrelated to aoe — **not because aoe fixed anything**. This is a CLI-version-dependent fact,
not an aoe fix; do not treat it as resolved without checking the installed `claude --version` and
transcript layout again, since it could as easily change back.

**What was tested** (2026-09-05, disposable scratch session `556887f0a86f4e86`, never
`b2ac292b9ecb41c8`):
1. Created via `aoe add --scratch --tool claude --launch`, confirmed its real transcript
   (`490efdac-50f7-40d0-82d7-407079d2a3e7`) via `aoe session show --json` and the transcript file
   on disk.
2. Dispatched a real, trivial `Agent`-tool subagent from inside it. Its transcript landed at
   `.../490efdac-50f7-40d0-82d7-407079d2a3e7/subagents/agent-afafed3f0d4c24021.jsonl` — nested, not
   a flat sibling `.jsonl`.
3. Checked `~/.config/agent-of-empires/profiles/main/sessions.json` afterward:
   `agent_session_id` was still correctly `490efdac-...`, unchanged.

This is suggestive but **not a confirmed disproof of the mechanism** — the background daemon
(pid 1885 in this environment) logged zero `session.store` activity at all for this scratch
session throughout the test (no `Session ID observed for 556887f0a86f4e86` line ever appeared),
which strongly suggests its live-observation polling only runs for sessions the daemon is actively
watching (rendered in a TUI, or swept during `session.startup_recovery`) — this scratch session was
neither. So the negative result here may simply mean "the observation pipeline never ran," not
"the new layout is immune to it." Confirming that would require either attaching a TUI to watch the
scratch session live, or restarting the aoe daemon to force a `startup_recovery` sweep over it —
the latter would also re-sweep every other tracked session including `b2ac292b9ecb41c8`, which this
task's Pause-and-Ask conditions explicitly rule out. Left unresolved rather than forced.

## Trigger shape 3: multi-daemon-instance flock contention — related, not disentangled

**Confirmed instance**, `debug.log:25312` (2026-08-27, session `226952c064a240ac` again):
```
2026-08-27T19:44:26.618571Z  WARN session.store: sid write rejected under flock: already owned by another instance instance_id=226952c064a240ac sid=06be9261-e02e-4450-9521-a3ca5890adf3 holder=3ad9df63731e442c
2026-08-27T19:44:26.621668Z  INFO session.store: Replacing stored session id with fresher live observation stale=dfe52177-aef5-4f80-ac5b-2c8a9d40d0a8 fresh=06be9261-e02e-4450-9521-a3ca5890adf3 tool=claude
2026-08-27T19:44:26.730725Z  WARN process.reap: pid survived SIGTERM after 100ms; sending SIGKILL pid=8416
```
Two different `instance_id`s (`226952c064a240ac`, the session's own id, and `3ad9df63731e442c`, a
different holder) are fighting over ownership of the same sid's on-disk storage, immediately
followed by process teardown (SIGTERM/SIGKILL) and a session restart
(`226952c064a240ac [claude] Starting -> Running`, `hook_age_ms=Some(40551)` — a stale hook age
consistent with a respawn).

**Best current assessment (inferred, not confirmed): the same root "freshest observation wins, no
tie-break" heuristic, compounded by an operational issue — multiple aoe daemon instances running
concurrently against the same profile without coordinated shutdown** (e.g., a previous instance
from an earlier restart that hadn't fully exited before a new one started). This is not the same
proximate trigger as shapes 1 or 2 (no shared Claude Code directory implicated here at all — this
is aoe-internal, multiple aoe processes disagreeing about who owns a sid), but it funnels into the
exact same "Replacing stored session id with fresher live observation" code path immediately after
the contention is resolved. Whether it's the same root cause or a genuinely separate bug that
happens to share a log line was **not fully resolved** in this investigation; flagged here as an
open item rather than merged into shape 1 or 2's narrative.

## Answers to the open questions this investigation set out to resolve

**Q1 — Does `aoe session set-session-id` durably pin a session, or only "at launch"?**
**Confirmed empirically: launch-only.** `set-session-id`'s own `--help` text already says "pins
*subsequent launches*"; the log's own vocabulary has a `"explicit pin consumed at launch"` message.
Direct test (scratch session `556887f0a86f4e86`): pinning to a fabricated UUID via
`set-session-id`, then reading `sessions.json` immediately after, showed the pin lands in a
**separate field**, `resume_intent: {"kind": "Use", "value": "<pinned-uuid>"}`, while the
live-tracked `agent_session_id` field was completely unaffected — still the session's real
transcript. The pin doesn't get overridden by a later swap; it never touches live tracking at all.
It only takes effect the next time the session's agent process is (re)started (a
`--resume <sid>`-style relaunch), which is also the only place the log shows it being "consumed."
**Conclusion: `set-session-id` is not a mitigation for a currently-running session's live tracking
being swapped out from under it.** It could plausibly help pre-seed a *not-yet-launched* session's
resume target, which is a different use case entirely.

**Q2 — What actually triggers a freshness re-evaluation?**
**Confirmed: continuous, not restart-exclusive.** The `b2ac292b9ecb41c8` incident coincided with
`session.startup_recovery` (a daemon/TUI restart). But the shape-1 instance at `debug.log:17308`
has no adjacent restart at all (nearest `AOE_START_MARKER` is ~10 minutes prior) — it happened
purely from ordinary runtime `session.store: Session ID observed for ...` events, which fire
continuously as part of normal status-change handling (visible throughout the log at every
`session.status_change` transition, not just at startup). Restart is simply the most *visible*
occasion for this, because `session.startup_recovery` forces a full re-observation pass across
every tracked session at once — if any tracked session happens to have a stray "fresher" transcript
sitting in its directory at that exact moment, restart guarantees it gets picked up right then. But
the underlying comparison runs continuously regardless of restart.

**Q3 — Is the flock-contention instance (`debug.log:25312`) the same bug or a different one?**
**Not fully resolved — treated as a related, not-disentangled, amplifying factor** (see Trigger
shape 3 above). Best assessment leans toward "same root heuristic, different proximate trigger,"
but this is inference from indirect evidence, not confirmation.

**Q4 — Does giving a subagent a different working directory relocate its transcript?**
**Confirmed empirically: no.** The test dispatched a subagent without varying its own tool calls'
working directory (there was no need to): the transcript path observed —
`<parent-project-dir>/<parent-session-id>/subagents/agent-<id>.jsonl` — is fully determined by the
*parent's* own project directory and session id, with no reference anywhere in that path to
whatever cwd the subagent's individual Bash/Read/etc. tool calls target. A path with no such
reference cannot be changed by varying the thing it doesn't reference — so no per-subagent
working-directory override could relocate it, confirmed by inspecting the path structure itself
rather than by exhaustively trying different cwds.

**Direct consequence for issue #175**: its suggested fix — "give each worker its own working
directory" — **cannot work as worded** for in-process `Agent`-tool subagents, because there is no
per-subagent working-directory knob that reaches the thing that actually determines transcript
location (the parent's own launch cwd). The only way to relocate a worker's transcript is to make
it a genuinely separate top-level process launched with its own cwd — which an in-process `Agent`
call structurally is not. Whether `Workflow`'s `agent()`/`parallel()` achieves this by running each
worker as an actually-separate top-level process (as issue #175's fallback suggestion speculates)
was **not tested here** — doing so would require invoking `Workflow` outside of a genuine
multi-agent-orchestration task, which this task is not, and this environment's `Workflow` tool is
explicitly gated on the user having opted into that scale of orchestration. Left as an open
question for whoever picks up issue #175's suggested-fix discussion.

**Q5 — Does aoe's own observation logic ever distinguish a subagent-marker transcript from a
genuine top-level one?**
**Confirmed: no, not for the flat-sibling-file layout.** aoe selected `7f2e617e-...` — a transcript
whose first line is the literal `{"type":"agent-setting",...}` marker — as the "fresher"
observation for `b2ac292b9ecb41c8`. If aoe's heuristic special-cased that marker at all, it would
not have chosen this file. **However, aoe does already have precedent for a similar check
elsewhere**: `debug.log` also shows `session.store: stored Claude sid has no transcript on disk;
launching fresh with --session-id instead of --resume to avoid a certain resume failure` (e.g.
`debug.log:17203`) — a launch-time check that a stored sid actually corresponds to an on-disk
transcript before trying to resume it. That check runs only at launch and only verifies
*existence*, not *content* (it doesn't open the file to check for an `agent-setting` first line).
The gap issue #175 and this task both point at — "aoe isn't using a signal it already has" rather
than "aoe needs an entirely new one" — has a real, concrete anchor: the file-content check
(peeking at the first line for an `agent-setting` marker) doesn't currently exist anywhere in the
observed log vocabulary, but the general pattern of "validate a candidate sid against the
filesystem before trusting it" already does, elsewhere in the same codebase.

## What mitigates this, and what doesn't

**Confirmed to help:**
- Always launching sibling aoe sessions into their own worktree (shape 1) — already the default
  behavior as of `[2.8.0]`.

**Confirmed NOT to help:**
- `aoe session set-session-id` as a live-session mitigation (Q1) — it's a launch-time-only
  pre-seed, not a running guard.
- Giving a dispatched `Agent`-tool subagent its own working directory (Q4) — doesn't change where
  its transcript lands.

**Unconfirmed, worth tracking rather than relying on:**
- Whether the newer nested `subagents/` transcript layout (CLI 2.1.261, observed 2026-09-05)
  structurally eliminates shape 2 going forward, versus simply not having been exercised by this
  test's daemon-polling gap (see "What was tested" above).
- Whether `Workflow`'s `agent()`/`parallel()` dispatch model gives each worker a genuinely separate
  top-level transcript (untested here; relevant to issue #175's fallback suggestion).
- Whether shape 3 (flock contention) is the same root cause as shapes 1/2 or a distinct
  daemon-lifecycle bug.

**No aoe-side mitigation currently protects the case that actually hit this task's own
orchestrating session** (shape 2, an in-process subagent's leftover transcript being picked up as
"fresher" for the coordinator itself) beyond whatever the Claude Code CLI's own storage-layout
change happens to provide incidentally.

## Cross-references

- `plugins/satori/skills/handoff/CHANGELOG.md` `[2.7.2]` and `[2.8.0]` entries — the confirmed fix
  for trigger shape 1.
- `plugins/satori/skills/handoff/SKILL.md`, Live Dispatch worktree-decision step — where shape 1's
  fix actually lives.
- `CLAUDE.md`, "Multi-Agent Dispatch Communication" — cross-linked to this doc for the general
  "aoe-managed coordinator dispatching subagents" case (shape 2).
- [fs-eng/records-platform-workspace#175](https://github.com/fs-eng/records-platform-workspace/issues/175)
  — the filed issue this investigation traces back to, from `rp-fleet:refit`'s angle. Not modified
  by this task; Q4's finding was posted as a comment there rather than acted on here.
- [agent-of-empires/agent-of-empires#3773](https://github.com/agent-of-empires/agent-of-empires/issues/3773)
  — the upstream bug report filed from Q5's finding (aoe already validates a stored sid's
  existence on disk at launch time, but the live "fresher observation" comparison doesn't check a
  candidate transcript's first line for the `agent-setting` subagent marker before adopting it).
