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

Creates a surgical, production-ready handoff document with the sections below — and, optionally,
can launch the implementing session itself and dispatch the handoff to it directly rather than
leaving that to a human (see "How It Works" step 4, Live Dispatch). Content:

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
### Pause-and-Ask Conditions

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
   - **Before creating**, check whether `~/.claude/handoff/active/<task-id>-<slug>.md` already
     exists. If it does and its frontmatter has a `dispatch:` block, a session may already be
     live-dispatched for this task — do not silently overwrite it (a routine re-run, e.g. after a
     spec correction, would otherwise orphan that running session: its color never gets cleared at
     archive, and step 4 would re-enter with no memory of the earlier dispatch). Tell the user a
     `dispatch:` block already exists (name the `aoe-session-id`/`aoe-session-title`) and ask
     whether to (i) preserve it — regenerate the rest of the document but carry the existing
     `dispatch:` block over unchanged, (ii) replace it — proceed normally, but only after
     confirming the old session has actually been cleaned up (archived/removed), or (iii) abort.
     No existing file, or an existing file with no `dispatch:` block → proceed normally.
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
     verified-from: <absolute path — the cwd these key-files were checked against, below>
     dependencies-complete: <true | false — are all prerequisite tasks done?>
     estimated-complexity: <trivial | small | medium | large>
     dispatch:                        # optional — populated by step 4 (Live Dispatch) below,
                                       # if/when it runs; omit this whole key entirely otherwise
       aoe-session-id: <id>
       aoe-session-title: <task-id>-<slug>, or ~<task-id>-<slug> if parent-linked — see step 4(e)
       launched-path: <absolute path the session was launched from>
       launched-at: <ISO 8601 timestamp>
     ---
     ```
   - Verify all `key-files` paths exist before writing — fail if any path is wrong. Record the
     absolute cwd this check ran from as `verified-from`, above. `key-files` are intentionally
     relative (so the same handoff stays valid across worktrees of the same repo, which share
     relative structure but differ in absolute path); `verified-from` is what makes those
     relative paths resolvable at all — without it, nothing downstream (including step 4(b)) has
     an anchor to compute a repo root from. Populate this for every handoff, not only ones that
     reach step 4.
   - Follows comprehensive template for prose sections
   - Includes verified context with citations
   - Lists explicit unknowns for implementer to discover
   - **Always** include a `## Before You Start` section immediately after the frontmatter and
     before section 1 (Verified Context) — applies to every generated handoff, not only ones
     that end up live-dispatched via step 4. This section must be self-contained: a fresh
     implementing session reads only the generated handoff, never this SKILL.md, so it cannot
     resolve "see SKILL.md" or "below" references back into a document it doesn't have. Resolve
     the progress-doc template's absolute path *now*, at generation time (e.g. it typically lives
     at `~/.claude/plugins/.../satori/skills/handoff/templates/IMPLEMENTATION-PROGRESS-template.md`
     — resolve the actual installed path for real rather than writing that example verbatim), and
     paste the concrete path into the template below in place of `<resolved-template-path>`.
     Substitute the real `<task-id>-<slug>` too:

     ```markdown
     ## Before You Start

     Create your progress doc now, before touching anything else:
     `~/.claude/handoff/active/<task-id>-<slug>-PROGRESS.md`, from
     `<resolved-template-path>`. That file is your only channel back to the orchestrating
     session — it does not read your conversation, only that file.

     If this session was started via aoe (`aoe session current` succeeds), the orchestrating
     session may also nudge you live via `aoe send` — treat any such nudge as a backup prompt
     only, never a substitute for updating the progress doc itself; the file is what actually
     gets read.

     If you can successfully run `aoe session current`, mirror your progress doc's `**Status**`
     field into your own aoe session color as it changes:
     `aoe session color $(aoe session current -q) amber` while In Progress, `red` the moment you
     add a `### Blockers` entry, `green` once Status is Complete. If a blocker gets resolved and
     Status returns to In Progress, set the color back to `amber` too — don't leave it `red`
     after the blocker that caused it is gone. If that command fails (you're not aoe-managed),
     skip it — this is a nice-to-have, not a requirement.
     ```
   - **If any `key-files` are SKILL.md files**, include a **SKILL.md Writing Disciplines** section
     in the generated handoff document, placed after the numbered context sections (1-5 above)
     and before Complexity Signal (6). This delegates the pre-write disciplines to the
     implementing session — the orchestration session does NOT execute them. Use this template:

     ```markdown
     ## SKILL.md Writing Disciplines

     This handoff involves editing a SKILL.md file. Before writing any new content, the
     implementing session must complete these disciplines in order:

     **1. Scope-term grep pre-flight** (do this FIRST, before touching the file):
     - Identify every term that describes the current scope (e.g., the call categories,
       phase names, or step references that the change will broaden or rename)
     - Grep the full SKILL.md for each old term and list all hits explicitly
     - Mark each hit as "update needed" or "no change needed" before writing anything
     - This sweep is a precondition of the edit, not a post-condition

     **2. Branch enumeration** (do this before writing any conditional step):
     - For every decision point the new content introduces, list all branches explicitly:
       found / not-found, per-type distinctions, combined conditions (X=0 AND Y non-empty)
     - Write the prose for each branch only after the full branch set is enumerated
     - A branch with no documented path is a Copilot finding waiting to happen

     **3. Pre-commit operator read** (do this before committing):
     - Read the modified sections linearly, top to bottom, as an operator who has never
       seen this document and has no knowledge of what was intended
     - Flag every step where you cannot proceed without guessing
     - Fix before committing — this is the cheapest moment to catch these gaps
     ```

   - **Note**: progress-document creation is directed via the generated `## Before You Start`
     section above, not restated here — pattern: implementing agent reads handoff (stable),
     updates progress (mutable)

3. **Quality Gate** (do not write the file until all pass — this is its own gate, enforced here
   before writing; it overlaps substantially with, but is not a literal duplicate of, "Quality
   Checklist" near the end of this document, which describes the same intent at a higher level for
   a reader who isn't executing this step by step):

   **Critical (MUST pass)**:
   - [ ] All file paths in `key-files` and "What to Change" verified to exist
   - [ ] `verified-from` records the exact absolute cwd the `key-files` check above ran from
   - [ ] All line number references checked for accuracy (read the file, confirm lines)
   - [ ] No "TODO", "fill this in", or placeholder sections remain
   - [ ] No invented commit hashes or unverified references
   - [ ] Explicit unknowns listed — if a fact could not be verified, it is in "Explicit Unknowns"
   - [ ] Scope boundaries present (what to change AND what NOT to change)
   - [ ] Decision authority explicit (what implementer decides vs asks)
   - [ ] Pause-and-ask conditions explicit
   - [ ] If any `key-files` are SKILL.md files: SKILL.md Writing Disciplines section is present

   **Essential (REQUIRED)**:
   - [ ] YAML frontmatter complete and all paths verified
   - [ ] Prior work referenced with file:line citations
   - [ ] Complexity signal present with specific indicators (not "MEDIUM" alone)
   - [ ] Acceptance criteria are checkable (not "tests pass" — specific test names or commands)

   If any Critical item fails: fix the handoff before writing. Do not write a
   handoff with known gaps and leave them as TODOs.

4. **Live Dispatch (Optional)** — reached only after the handoff document has actually been
   written (Quality Gate passed). This step launches a real, separately-running `claude` process
   as a tracked `aoe` sub-session and points it at the handoff, instead of leaving a human to
   start the next session manually. It requires the `aoe` CLI (a tmux-based session manager);
   without it, this step does not apply. **Every stop-and-ask below should show the actual
   failing command's exit code and stderr**, not just name the general cause — a specific `-P`
   nesting error and an unrelated `aoe add` failure need different responses, and an operator
   can't tell which happened from a paraphrase alone.

   **a. Gate on `aoe` presence — never silently default either way**:
   - `command -v aoe` fails → skip this entire step, no question asked. The handoff document is
     already complete; proceed to normal completion.
   - `command -v aoe` succeeds → **always** ask via `AskUserQuestion` whether to live-dispatch
     now. Never assume yes (an unattended dispatch the user didn't ask for) or no (silently
     dropping a capability that's available). User declines → skip the rest of this step, same
     end-state as the absent case. User accepts → continue to (b).

   **b. Resolve the launch path**:
   - `key-files` are bare relative paths — they don't self-describe a repo root. Resolve each one
     to an absolute path as `<verified-from>/<key-file>` (the frontmatter's `verified-from`, from
     step 2) first; only then can a root be computed at all. (Don't make `key-files` themselves
     absolute instead — that breaks the moment dispatch lands in a different worktree of the same
     repo, which is the common case, since each worktree has its own absolute path despite
     identical relative structure.)
   - For each resolved absolute path, determine its actual git repo root, e.g.:
     ```bash
     resolved_path="<verified-from>/<key-file>"
     repo_root=$(git -C "$(dirname "$resolved_path")" rev-parse --show-toplevel)
     key_relative_to_repo=${resolved_path#"$repo_root/"}   # this file's path relative to ITS OWN repo root
     ```
     Keep `key_relative_to_repo` around per key-file — it's what re-verification below actually
     needs, not the original (possibly workspace-relative) `key-files` string.
   - All resolved paths share one git root, and that root is the current directory → default
     path = cwd.
   - All resolved paths share one git root, but it isn't cwd, and an ancestor directory has a
     `repos/repos.json` whose `groups.<group>.repos[].name` names that repo (the fleet-workspace
     convention — see `<workspace-root>/CLAUDE.md` for how a given fleet workspace documents it;
     `records-platform-workspace/CLAUDE.md` is one confirmed example, not the only shape this can
     take), e.g.:
     ```bash
     dir="$(dirname "<resolved-path>")"
     while [ "$dir" != "/" ]; do
       [ -f "$dir/repos/repos.json" ] && { echo "found: $dir/repos/repos.json"; break; }
       dir="$(dirname "$dir")"
     done
     ```
     → default path = `<workspace-root>/repos/<group>/<repo-name>/`. (This should equal the git
     root computed above — if it doesn't, that mismatch is itself worth surfacing rather than
     silently trusting one over the other.)
   - All resolved paths share one git root, but neither of the above resolves it → there is no
     safe default; present cwd explicitly labeled as an unverified guess and require the user to
     confirm or override — never assume silently (this is the one case design review called out
     by name: "guessing a fleet repo's launch path silently").
   - Resolved paths span multiple git roots → stop; do not offer any default. Ask the user
     directly whether to (i) dispatch against just the primary repo, or (ii) skip live dispatch
     for this task. Automating a true multi-repo dispatch (aoe's own `-r`/`--project`) is an
     explicit, deferred follow-on — not implemented here. If (i): key-files belonging to any
     *other* repo are expected to not resolve under the primary repo's path — exclude them from
     the re-verification below rather than treating their absence as a failure.
   - Always confirm the resolved path via `AskUserQuestion`, even the "obvious" cwd case — this
     mirrors the mandatory-ask precedent, not a rubber stamp.
   - **Re-verify whenever the confirmed path differs from the git root computed above** (not
     whenever it differs from `verified-from` — those are allowed to legitimately differ, e.g.
     the fleet-workspace default path above is *always* a subdirectory of `verified-from`, by
     construction, with nothing wrong). For each in-scope key-file (excluding any from other
     repos per the multi-root case above), check that `<confirmed-path>/<key_relative_to_repo>`
     exists — using the per-key-file relative path computed in the git-root step, never the
     original possibly-workspace-relative `key-files` string, or a fleet-workspace path ends up
     checked twice and duplicated (`<repo>/repos/<group>/<repo>/...`) instead of resolved. If
     anything in scope is still missing under the confirmed path, stop, name exactly which paths
     are missing, and require the user to correct the path or abandon live dispatch — don't
     silently continue past a failed re-verification. On success, treat the confirmed path as the
     effective anchor for the rest of *this* live-dispatch flow (steps (c) onward). Do not
     overwrite the handoff document's own `verified-from` field to match: that field records
     history (where the document was originally verified), not where a later session happened to
     dispatch from.

   **c. Worktree decision**:
   - Existing fleet worktree convention detected at the confirmed path's workspace root — check
     explicitly, e.g. `test -f "<workspace-root>/repos/worktree.sh"` or
     `ls -d "<workspace-root>/repos/"*"-worktrees" 2>/dev/null` for a pre-existing
     `<repo>-worktrees/` sibling. Found → defer to it: name the exact command to run (e.g.
     `repos/worktree.sh add <task-id>-<slug> <repo-name>`), then re-resolve the launch path to
     the worktree it creates. Do not drive it via aoe's own worktree flags — a repo that already
     has a worktree convention doesn't need a second, competing one.
   - No existing convention detected → offer aoe's own worktree creation as the recommended
     default via `AskUserQuestion`: `-w <branch-name> -b --base-branch <branch-from>` (using the
     frontmatter's own `branch-from` as the base). `<branch-name>` is `<task-id>-<slug>` — or that
     value plus whatever disambiguation suffix (e) below ends up appending to the title, if it
     does; the branch name and the session title must move together, since a mismatched pair is
     confusing on its own and can independently collide on `-b` if a prior run already created the
     un-suffixed branch. User may decline and dispatch directly against the resolved path with no
     worktree.
   - **Re-run case**: if the worktree directory or branch from a prior dispatch of this exact
     task already exists (`repos/worktree.sh add` erroring that the target exists, or aoe's `-b`
     failing because the branch survived an earlier run), don't treat that as a fresh-creation
     failure — surface the collision and ask whether to reuse the existing worktree/branch,
     delete and recreate, or abandon live dispatch. Never silently plow ahead either way.

   **d. Parent linkage** (resolved before naming in (e) below, since the title's prefix depends
   on this outcome):
   - Run `aoe session current -q`. Failure (the orchestrating session isn't itself aoe-managed)
     → omit `-P`; the new session is created standalone. Success → capture the returned name
     (despite the flag's own `-q, --quiet` help text calling it "session name," it's a valid
     `IDENTIFIER` — aoe's `-P`, like its other session-referencing flags, accepts a title
     interchangeably with an id; verified empirically: the nesting-limit test in the very next
     bullet used a title-form value for `-P` and got `Cannot create sub-session of a
     sub-session`, not a not-found-style error — proof aoe resolved the title to a real session
     before rejecting it for depth, not that the title was simply ignored) and pass it as
     `-P <parent>` to `aoe add`.
   - **aoe only supports one level of sub-session nesting.** If the orchestrating session
     invoking this skill is *itself* already a sub-session (i.e., it was `-P`-linked to some
     further-up parent), passing `-P` here fails with `Cannot create sub-session of a
     sub-session (single level only)` — confirmed empirically (attempted from a session that was
     itself a live-dispatch sub-session, using that session's title as the `-P` value; `aoe add`
     exited 1 with exactly that message, no stray session record left behind). Detect this by
     checking the exit code and stderr text of the `aoe add` call in (f); on this specific error,
     retry the same `aoe add` command with `-P` omitted (standalone) rather than aborting the
     dispatch — the nesting limit is a soft aoe constraint, not a reason to give up on live
     dispatch. Also revise the title from (e) below to drop its `~` prefix in this case: the
     fallback means there's no real parent link after all, so don't leave a marker implying one.

   **e. Naming and duplicate-title check**:
   - Title = `<task-id>-<slug>` (the same slug used in "File Naming Convention" below) — this is
     the identifier used everywhere else (handoff filename, progress filename, branch name); it
     never changes shape based on whether a parent link exists.
   - **When a real parent link exists** (`-P` is actually being passed per (d) above — not the
     standalone case, whether standalone because the orchestrator isn't aoe-managed or because of
     the single-level-nesting fallback), prefix the *displayed* `-t` value with a leading `~`:
     `~<task-id>-<slug>`. This is a purely cosmetic, temporary workaround for
     [agent-of-empires/agent-of-empires#3472](https://github.com/agent-of-empires/agent-of-empires/issues/3472)
     — confirmed open: `-P` parent linkage is tracked in aoe's data model but never shown in
     `aoe list` or the TUI, so a child session is visually indistinguishable from an unrelated
     top-level one in a flat list. Remove this prefix once that issue ships proper parent/child
     display. No parent link at all (standalone) → no prefix; don't imply a parent that doesn't
     exist.
   - **Why a leading `~`, not a leading `-` or a trailing marker** — both alternatives were tried
     and rejected empirically:
     - A leading `-` breaks: aoe's CLI is clap-based, and `aoe add --scratch -t "-x" --tool
       claude` fails with `error: a value is required for '--title <TITLE>' but none was
       supplied` — clap reads the leading `-` as introducing a new flag, not as part of the
       title's value.
     - A trailing marker parses fine, but a column-width-limited session list commonly truncates
       from the right — exactly where a trailing marker would sit, defeating the point of adding
       one.
     - A leading `~` avoids both: confirmed via `aoe add --scratch -t "~x" --tool claude` (exit
       0, `aoe session show --json` echoed the title back with the `~` intact), and a leading
       character survives right-side truncation that a trailing one wouldn't.
   - Check `aoe list --json` for an existing session with that title (prefix included, if
     applicable) *before* creating one. If found, surface it and ask whether to disambiguate
     (append a suffix) or abandon live dispatch for this run — never silently create a second
     session under a duplicate title. If a suffix gets appended here, propagate it into (c)'s
     branch name too (see (c) above) — don't leave the two out of sync.

   **f. Create the session and resolve its id**:
   - Run `aoe add <path> -t "<title from (e)>" [-P <parent>] --tool claude --launch [worktree
     flags from (c)]`.
   - Parse the `ID:` line from its stdout for the new session's id — verified empirically
     reliable (tested via `aoe add --scratch --tool claude --launch`, captured raw stdout: exit
     0, `ID:      <id>` present every time). If that line is unexpectedly absent (e.g. a future
     `aoe` version changes its output format), stop and ask rather than guessing at an id from a
     list scan.
   - If this call instead fails with the single-level-nesting error from (d): before retrying,
     re-run (e)'s duplicate-title check against the *fallback* title (the `~` prefix stripped) —
     it was never checked, since (e)'s original check ran against the still-prefixed title, and
     the stripped form is a different string that could independently collide. Then retry
     `aoe add` with `-P` omitted and the stripped title, before falling back to the stop-and-ask
     above.

   **g. Record dispatch metadata — immediately, before the readiness poll in (h)**:
   - Write the `dispatch:` block (see step 2's frontmatter template) into the handoff document's
     frontmatter *now*, right after (f) resolves an id — with `aoe-session-id`,
     `aoe-session-title` (the actual title used, `~` prefix included if applicable),
     `launched-path`, and `launched-at` (ISO 8601, now). This is the one frontmatter field this
     skill updates outside the normal "stable" policy — see the carve-out in "When to Update
     Handoff Document" below.
   - Do this regardless of what happens next: (h)'s readiness-poll timeout, and (i)'s kickoff
     message being skipped as a result, must NOT skip this step. A session that exists but never
     got a kickoff message is still a real, running (and possibly aoe-colored) session — it needs
     to stay traceable from the handoff document, not become orphaned.
   - `launched-path` is the session's actual working directory, not simply the `<path>` argument
     handed to `aoe add` — those differ in the worktree case, since aoe creates and launches in a
     separate worktree directory rather than `<path>` itself. Read it back from
     `aoe session show --json`'s `path` field after (f) succeeds, rather than echoing the input
     argument.
   - If (f) never obtained an id at all (the missing-`ID:`-line stop-and-ask fired), there's
     nothing to record here — but the session may still exist and be running untracked. Recovery:
     note the title that was used and run `aoe list --json` after the fact to look it up, so the
     orphan stays traceable even without the normal id-parsing path; record this in the progress
     doc rather than letting it go fully untracked.

   **h. Readiness poll before send — do not send blind**:
   - The launch→send race is real: a fresh `claude` process opening a directory it's never
     opened before shows a first-run folder-trust dialog, and a message sent before that's
     resolved can end up answering the trust dialog instead of reaching the agent.
   - **`aoe session show --json`'s `status` field is the check — poll that, not pane content.**
     Verified directly against a real trust dialog (dispatched into a genuinely fresh directory
     never opened before — a worktree of an *already-trusted* repo doesn't reproduce this; trust
     is inherited at the repo level, confirmed by two dispatches that landed in a new worktree of
     a trusted repo and never saw the dialog at all): `status` reads `"waiting"` while the trust
     dialog is showing, `"running"` immediately after it's answered, then settles to `"idle"`
     once genuinely ready. `"waiting"` isn't specific to the trust dialog either — sending a
     request that triggered an unrelated, later permission prompt (reading a file outside the
     project directory) reproduced the identical `"waiting"` reading. Ready = `status == "idle"`;
     `"waiting"` or `"running"` = not ready yet.
   - Wait at least ~2s after creation before the first poll regardless — this hasn't been
     independently verified as immune to the same blank-pane-at-t=0 risk a pure pane-content check
     has (nothing may have rendered yet, which could plausibly read as `"idle"` falsely for the
     same reason an empty pane capture would wrongly read as "no dialog markers present"). Keep
     the settle delay as a cheap defensive margin rather than assume the field can't have an
     equivalent bootstrap gap.
   - Poll `aoe session show <id> --json`, every ~2s for up to ~30s total.
   - Handle `aoe session show` (and, in (e), `aoe list --json`) exiting non-zero explicitly — an
     errored check is not a pass. Retry a small number of times; if it keeps failing, treat it the
     same as the timeout below rather than silently treating a failed check as "ready."
   - On timeout without reaching `"idle"` (still `"waiting"`/`"running"` after ~30s, or the check
     itself repeatedly erroring): do not send blind. Print the exact `aoe send <id> "<message>"`
     command (and `aoe session attach <id>` as an alternative) for a human to run once whatever's
     blocking it is cleared. Do not reach for `--yolo` / `--trust-hooks` to make this problem go
     away — establishing a default trust/permission-bypass policy for dispatched sessions is a
     separate, explicitly deferred follow-on, not a decision made here, and cuts against the point
     below: permission prompts are supposed to reach the user, not be routed around.

   **i. Kickoff message**:
   - Once ready: `aoe send <id> "<terse pointer — e.g. 'Read
     ~/.claude/handoff/active/<task-id>-<slug>.md and begin. Update the -PROGRESS.md file (same
     directory, -PROGRESS.md suffix) as you go — that's your channel back to me.'>"`.
   - Keep it a pointer, not a restatement — see `~/.claude/CLAUDE.md`'s "Multi-Agent Dispatch
     Communication" section for why detailed content routes through the shared file rather than
     the message payload.

   **By design, not a limitation: Live Dispatch is a convenience for starting the session, not an
   unattended/autonomous-execution mechanism.** The readiness poll in (h) exists only to protect
   the one thing this step automates without a human present — the single kickoff message in
   (i). It deliberately does not extend into a standing "watch for later prompts" loop, even
   though `status` (per (h)) would technically support one. Once the kickoff lands, the model is
   the same as any session the user started by hand: the user is expected to shift attention to
   the dispatched session (`aoe session attach <id>` or the aoe dashboard) and grant whatever
   permissions it asks for as they come up. A later permission prompt is the normal, expected
   interaction — not a stall to detect, poll for, or work around.

## File Naming Convention

Handoff documents are saved as:
```
~/.claude/handoff/active/<task-id>-<slug>.md
```

**Examples**:
- `active/task-4.16.2-collection-indices-writer.md`
- `active/bug-123-null-pointer-fix.md`
- `active/feature-kafka-retry-logic.md`

The same `<task-id>-<slug>` doubles as the `aoe` session title (optionally `~`-prefixed — see
step 4(e) — when the session is parent-linked; the prefix is display-only and never appears in
the branch name) and, when a worktree is created, the git branch name if Live Dispatch (How It
Works step 4) runs — one identifier, reused rather than invented fresh at dispatch time.

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
- ✅ Optionally, start working immediately — dispatched into a real, tracked session by the
  orchestrating session itself, instead of waiting for a human to start the next one

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

**Handoff Document (Stable — updated only per "When to Update Handoff Document" below)**:
- Location: `~/.claude/handoff/active/{task-slug}.md`
- Purpose: Original specification for implementing agent
- Content: Executive summary, technical specs, architecture, implementation guide, acceptance criteria
- Update policy: Only on fundamental architecture changes

**Implementation Progress (Mutable)**:
- Location: `~/.claude/handoff/active/{task-slug}-PROGRESS.md`
- Purpose: Track implementation evolution, decisions, blockers, and feedback to the orchestrating session
- Content: Architectural decisions, progress checklist, blockers, questions
- Update policy: Implementing agent updates frequently — this is the primary communication
  channel back to the orchestrator (see "aoe as a Backup/Live Communication Channel" below for
  the optional secondary one)

### aoe as a Backup/Live Communication Channel

When the implementing session was started via Live Dispatch (How It Works step 4), a second,
optional channel exists alongside the file-based one above: `aoe send <id> "<message>"` types a
message directly into the live session's terminal.

- **This is a backup, not a replacement.** The `-PROGRESS.md` file above remains the primary,
  authoritative record — `aoe send` is for a short live nudge ("please update your progress
  doc", "reminder: acceptance criterion X is still open"), not for carrying substantive content.
  Route detailed context through the shared file per `~/.claude/CLAUDE.md`'s "Multi-Agent
  Dispatch Communication" section, the same discipline that governs every other dispatch
  mechanism in this environment.
- **It's not the only backup path, either.** An aoe-launched session is a real tmux-backed
  `claude` process, and confirmed live (via `ListAgents`) to also show up as a reachable peer
  session through the harness's own cross-session messaging — so `SendMessage` can reach it too,
  subject to that mechanism's own non-guaranteed-delivery caveats (see the same CLAUDE.md
  section). `aoe send` is the mechanism this skill documents and relies on; it is not the sole
  route.
- Only usable if the orchestrating session resolved the dispatched session's id in step 4(f) —
  without it, fall back to reading the `-PROGRESS.md` file cold.

### Responsibility Model

**Orchestrating Agent (this skill)**:
- Creates handoff document with complete specification
- Does NOT create progress document (implementing agent creates it)
- Reviews progress document to answer questions
- Updates handoff only on fundamental changes

**Implementing Agent (reads handoff)**:
- Reads handoff document (does not modify)
- Creates progress document on first session
- Updates progress document frequently — **this is the primary feedback channel back to the
  orchestrator** (`aoe send` nudges are a backup, not a substitute — see "aoe as a Backup/Live
  Communication Channel" above)
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

**Exception**: the frontmatter `dispatch:` block (How It Works step 4(g)) is written by the live
dispatch step itself, immediately after creating the session — routine bookkeeping of one
metadata field, not a fundamental architecture change, so it doesn't need the bar above to apply.

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

If the archived handoff's frontmatter has a `dispatch:` block (i.e., it was live-dispatched — see
How It Works step 4), also clear that session's color so it stops showing as active in aoe's
dashboard: `aoe session color <aoe-session-id> none`. Best-effort — wrap it so a failure (e.g.,
the session was already removed) doesn't block the archive itself, but don't swallow the reason
silently either — a bare `|| true` discards a wrong/truncated id, a profile mismatch, aoe being
uninstalled, and a version change all identically, with no way to tell which happened later:
```bash
err_file="/tmp/aoe-color-clear-<aoe-session-id>-$$.log"   # namespaced by session id + PID, not a shared generic name
aoe session color <aoe-session-id> none 2>"$err_file" || \
  echo "warning: couldn't clear color for session <aoe-session-id>: $(cat "$err_file")"
rm -f "$err_file"
```
No `dispatch:` block → nothing to clear, skip this.

**When NOT to archive**:
- Implementation is still in progress (progress document shows incomplete items)
- Acceptance criteria have not been verified by the orchestrating session
- The implementing session flagged blockers or open questions

**Verification before archiving**: Read the PROGRESS document and confirm:
- [ ] All acceptance criteria checklist items are checked
- [ ] No open blockers or questions remain
- [ ] The orchestrating session has verified the output (not just taken the implementing agent's word)

> **Why archive rather than delete?** Completed handoff docs preserve the *why* behind design decisions, anti-patterns to avoid on re-entry, and scope constraints that aren't obvious from the code. Archiving keeps `active/` small and scannable while retaining the audit trail.

