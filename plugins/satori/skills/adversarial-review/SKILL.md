---
name: adversarial-review
description: >
  Multi-round parallel adversarial pattern review against copilot-review-patterns.md.
  One agent per pattern class, cascade-sweep within each class, human review-pause between
  rounds, git-guardrailed fixes. Invoked by /pre-pr-audit (3 rounds) and /address-pr-issues
  (1 round), or standalone. Use before opening a PR or before pushing a fix round on code changes.
---

# Adversarial Pattern Review

Run a multi-round, parallel-agent sweep of your changed code against the known Copilot issue
pattern classes. Each round spawns one reviewer per class, deduplicates findings, pauses for
human disposition, applies approved fixes under strict git guardrails, then re-evaluates.

## When to Use

- Directly: `Skill(adversarial-review)` or `/adversarial-review` — standalone sweep before opening a PR
- Called by `/pre-pr-audit` Step 4.7 with `--rounds 3`
- Called by `/address-pr-issues` Step 3.5 with `--rounds 1`

## Inputs (all optional, with defaults)

| Arg | Default | Description |
|-----|---------|-------------|
| `--rounds N` | `3` | Maximum review rounds |
| `--base-branch BRANCH` | auto-detect | Compare against this branch (`@{u}` → `main` → `master`) |
| `--intent-brief "..."` | _(prompt user)_ | ~200 words: problem statement, design decisions, what was deferred |

If `--intent-brief` is not supplied by a caller, ask the user to provide it before proceeding.
The Intent Brief is the single most important input: without it, fix agents cannot distinguish
"intentional design decision" from "bug to fix."

---

## Setup (run once before the round loop)

### 1. Resolve the pattern file

```bash
# Prefer the living user-global copy; fall back to the bundled snapshot
PATTERNS_FILE=~/.claude/copilot-review-patterns.md
if [ ! -f "$PATTERNS_FILE" ]; then
  PATTERNS_FILE=~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md
fi
```

### 2. Enumerate pattern classes dynamically

```bash
# DO NOT hardcode a number — classes grow as new issues are encountered
PATTERN_CLASSES=$(grep "^### [0-9]" "$PATTERNS_FILE" | sed 's/^### [0-9]*\. //')
```

### 3. Resolve the base branch

```bash
BASE_BRANCH=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null | cut -d/ -f2-)
if [ -z "$BASE_BRANCH" ]; then
  if git show-ref --verify --quiet refs/heads/main; then
    BASE_BRANCH=main
  elif git show-ref --verify --quiet refs/heads/master; then
    BASE_BRANCH=master
  else
    echo "Cannot detect base branch — supply --base-branch"
    exit 1
  fi
fi
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
```

### 4. Pin the comparison refs (run once)

Record these values and pass them verbatim to every review agent. **Agents run their own diff
and read the files their lens needs** — the orchestrator does not pre-read or paste file
contents into agent prompts.

```bash
# Pinned from Step 3 — fixed for all agents in all rounds
BASE_BRANCH=<resolved in Step 3>
CURRENT_BRANCH=<resolved in Step 3>
```

Agents use these ref values with the following enumeration commands (embed these in every agent
prompt alongside the refs):

```bash
# Orientation: run once at review start to see what changed and where
git diff origin/$BASE_BRANCH...$CURRENT_BRANCH

# List changed source files (read in full for cascade sweep)
git diff --name-only origin/$BASE_BRANCH...$CURRENT_BRANCH \
  | grep -E "\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$"

# List changed doc files (for doc/spec lenses — see Setup Step 5)
#   (1) doc files changed directly in the PR
git diff --name-only origin/$BASE_BRANCH...$CURRENT_BRANCH \
  | grep -E "(\.md|\.rst|\.adoc|CHANGELOG|README)"
#   (2) README/CHANGELOG adjacent to any changed source file (up one directory)
git diff --name-only origin/$BASE_BRANCH...$CURRENT_BRANCH \
  | grep -E "\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$" \
  | xargs -I{} dirname {} 2>/dev/null | sort -u \
  | xargs -I{} sh -c 'find {} "{}/.." -maxdepth 1 \( -name "README*" -o -name "CHANGELOG*" \) 2>/dev/null' \
  | sort -u
```

Each agent runs the diff **once at the start of its review**, before applying its lens. An agent
must not re-diff after Phase D fixes begin. Within a round the tree is frozen until Phase D, so
every review agent sees the same state — consistent across all agents in the round — without
the orchestrator needing to hold or pass file contents itself.

### 5. Build per-class review prompts (run once — reused by every round)

For **each entry in `PATTERN_CLASSES`**, build one complete review-agent prompt. The prompt text
is round-invariant (it references `$BASE_BRANCH`/`$CURRENT_BRANCH` and tells the agent to diff
and read files itself) — build it once here, then pass the same prompt into every round's
Workflow call in the Per-Round Loop below.

**Every prompt MUST include:**

1. The relevant pattern class section (cut from `$PATTERNS_FILE`)
2. The pinned `BASE_BRANCH`, `CURRENT_BRANCH`, and the enumeration commands from Step 4
3. Instruction to the agent: *run the diff once (orientation), enumerate changed files, and read
   the **full contents** of the files your lens needs:*
   - **Code lenses** (State Machine / Control Flow Logic, Defensive Guards, Operator
     Observability / Error Message Accuracy, Provenance / Identity Discrimination,
     Infrastructure / Environment Handling, Test Integrity): read the full contents of changed
     **source** files
   - **Doc/spec lenses** (Documentation Accuracy, Semantic Correctness / Logical Completeness,
     Operator Spec Completeness, Spec Operator Walkthrough): read the full contents of changed
     **doc** files; read source files only if the lens explicitly requires cross-referencing
     code (e.g., Documentation Accuracy's doc-vs-code checks)
   - **Cross-File Rule Consistency**: read full contents of **both** changed source and doc
     files — a rule can be restated across a doc and a code file (this lens is not in either
     bucket above; it needs everything)
4. The Intent Brief
5. The **cascade sweep rule** (embed verbatim):

   > When you find a bug, state its specific failure mode in one sentence (e.g., "subprocess
   > returncode used before checking stdout"). Then scan *every other callsite of the same kind*
   > in the entire changed source — every subprocess call, every JSON read, every branch exit —
   > for the same failure mode before reporting. Report all instances together as a cluster.
   > Do NOT hold back and expect later rounds to catch siblings. A missed sibling is a miss.

6. The `blast_radius` classification rule: classify structurally, never by severity or gut feel —
   `local` = confined to one file/callsite, something the current session could diagnose and fix
   in-context if it ever manifested; `cross_file` = spans multiple files, affects call sites
   outside the diff, or restates a rule defined elsewhere (e.g., a doc restating a code
   constant). Justification must cite structural evidence actually checked — a grep for other
   callers, the other file that restates the rule; a `local` tag with no evidence is invalid,
   and `local` is never a reason to down-rank a real bug.
7. The finding-schema conventions the Phase A/B script below relies on: report `file` as
   `path:line` or `path:startLine-endLine` (the synthesis script dedupes by matching this string
   exactly — an inconsistent format silently breaks the dedup); populate `cascade_siblings` with
   every sibling location found via the cascade sweep rule (item 5); return `is_clean: true` with
   an empty `findings` array if the class is fully clear, `false` otherwise.

Reference classes by name only, as `PATTERN_CLASSES` does — never by number. Numbers drift as
classes are added, renamed, or reordered in the patterns file; names are the stable identifier.

**Model selection** (used as the `model` override when the Workflow script below calls `agent()`;
omit for Sonnet — it's the default):
- **Opus**: State Machine / Control Flow Logic; Operator Observability / Error Message Accuracy; any class flagged by the user as high-complexity
- **Sonnet**: all other classes

Store the result as `CLASSES`: a list of `{ name, prompt, model? }`, one entry per pattern class.
Reused verbatim by every round's Workflow call in the Per-Round Loop below.

---

## Per-Round Loop

Repeat up to `--rounds` times. After each round, check the termination condition (Phase E) before
deciding whether to continue. Maintain `PRIOR_FINDINGS` across rounds — empty at round 1,
appended to at the end of each round's Phase C (see below).

### Phase A/B — Parallel Review + Synthesize (Workflow)

Run per-class review and synthesis as a single call to the `Workflow` tool (Claude Code's
multi-agent orchestration primitive). `parallel()` is a hard barrier — the script cannot advance
to synthesis until every class has resolved or been retried to a terminal failure, and `schema`
forces structured output instead of relying on an agent to comply with a text instruction. This
replaces spawning per-class review agents directly. `agent`, `parallel`, `phase`, `log`, and
`args` below are pre-bound globals the Workflow tool provides inside the script it executes —
not something this file defines. `agent()` retries a failed call internally before giving up;
`missingClasses` (below) reflects only classes that exhausted those retries.

```js
export const meta = {
  name: 'adversarial-review-phase-ab',
  description: 'One round: parallel per-class review + synthesis',
  phases: [{ title: 'Review' }, { title: 'Synthesize' }],
}

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      severity: { enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
      blast_radius: { enum: ['local', 'cross_file'] },
      blast_radius_justification: { type: 'string' },
      file: { type: 'string' },
      pattern_class: { type: 'string' },
      description: { type: 'string' },
      recommendation: { type: 'string' },
      cascade_siblings: { type: 'array', items: { type: 'string' } },
    }, required: ['severity', 'blast_radius', 'blast_radius_justification', 'file', 'pattern_class', 'description', 'recommendation'] } },
    is_clean: { type: 'boolean' },
  },
  required: ['findings', 'is_clean'],
}

// `args` has been observed arriving as a raw JSON string rather than a parsed object,
// regardless of how the caller passed it — parse defensively rather than trust the docs here.
const { classes, priorFindings = [] } = typeof args === 'string' ? JSON.parse(args) : args

phase('Review')
const results = await parallel(classes.map(c => () =>
  agent(c.prompt, { label: `review:${c.name}`, phase: 'Review', schema: FINDING_SCHEMA,
    ...(c.model ? { model: c.model } : {}) })))

const missingClasses = classes.map(c => c.name).filter((_, i) => !results[i])
if (missingClasses.length) {
  log(`${missingClasses.length} class(es) returned no result and are excluded from this round: ${missingClasses.join(', ')}`)
}

phase('Synthesize')
const SEVERITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
const raw = results.filter(Boolean).flatMap(r => r.findings)

const merged = new Map()
for (const f of raw) {
  const existing = merged.get(f.file)
  if (!existing) { merged.set(f.file, { ...f, pattern_classes: [f.pattern_class] }); continue }
  existing.pattern_classes.push(f.pattern_class)
  if (f.blast_radius === 'cross_file') {
    existing.blast_radius = 'cross_file'
    existing.blast_radius_justification = f.blast_radius_justification
  }
  if (existing.recommendation !== f.recommendation) {
    existing.recommendation = `${existing.recommendation} | ALSO: ${f.recommendation}`
  }
}
const findings = [...merged.values()].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])

const priorKeys = new Set(priorFindings.map(f => f.file))
const provisionalYield = findings.filter(f => f.blast_radius === 'cross_file' && !priorKeys.has(f.file)).length

return { findings, provisionalYield, missingClasses }
```

Invoke with `Workflow({ script: <above>, args: { classes: CLASSES, priorFindings: PRIOR_FINDINGS } })`.
Dedup keys on the `file` string (already `path:line` or `path:startLine-endLine`, as agents
report it) — merges `pattern_class` into a list, keeps `cross_file` on a `blast_radius`
disagreement (wider radius wins), and **lists both recommendations side by side (`| ALSO:`)
rather than guessing which is "more specific"** when two lenses collide on the same location.
This is deterministic JS, not an LLM judgment call — leave the actual disposition to Phase C.

**`missingClasses` is not "that class was clean."** A class whose agent never returned a result
(terminal API error after retries) means that lens genuinely didn't run this round. Carry
`missingClasses` forward into Phase C and Phase E — it blocks a CONVERGED verdict (see Phase E).

### Phase C — Review-Pause (human decision)

Present the synthesized findings **and any `missingClasses`** to the calling session. For each
finding, the user classifies it:

| Disposition | Action |
|-------------|--------|
| **Fix** | Proceed to Phase D |
| **Contradicts design** | Override — no fix; do not flag as "missed" |
| **Accepted risk** | Record as a known limitation; include in the Summary Output's Known Limitations section and PR description. Do NOT silently drop — the absence of a finding in the summary is a claim that it was addressed |
| **False positive** | Skip; note the reason in the round summary |

**Finalize the round's cross-file yield** after disposition: subtract any `cross_file` finding
dispositioned as **False positive** or **Contradicts design** from Phase A/B's provisional count
— those are not confirmed bugs, so they should not read as evidence the sweep is still finding
real issues. **Fix** and **Accepted risk** dispositions both count (an accepted-risk finding is
a real, confirmed issue the human chose not to fix yet). This finalized number is what Phase E
reads.

**Append to `PRIOR_FINDINGS`** before the next round: every finding dispositioned **Fix** or
**Accepted risk** this round, as `{file, blast_radius}`. Next round's Phase A/B call passes this
updated list so its yield computation compares against the full history, not just this round.

### Phase D — Apply Fixes

For each approved finding, apply the fix. The fix agent receives:
- The approved finding + its recommendation
- The Intent Brief
- These **git guardrails** (embed verbatim in every fix agent prompt):

> **PROHIBITED**: `git reset` (any form), `git rebase`, `git commit`, `git stash`,
> `git checkout -- <file>`, `git restore`.
>
> **PERMITTED**: Edit/Write (file edits only); Bash commands only for running tests, reading
> files, or grep/find; `git diff` and `git status` (read-only).
>
> Do NOT create new test classes. Add tests to the **existing** test class for the changed file.

Run the test suite after applying all fixes for this round. If tests fail, report the failures
before proceeding — do not continue to the next round with a red test suite.

### Phase E — Check Termination

The next round's Phase A/B Workflow call will self-diff the now-modified working tree when it
starts — the orchestrator does not need to re-read or re-pass file contents between rounds.

Termination is driven by the round's **finalized cross-file yield** (provisional in Phase A/B,
finalized in Phase C) and `missingClasses`, not by `is_clean` flags. Open `local` findings never
force another round — report them in the Summary Output for human disposition and move on.

**Terminate as CONVERGED when:**
- Cross-file yield == 0 — no new `cross_file` finding this round, even if `local` findings remain open
- AND `missingClasses` is empty — every class returned a definitive result this round

**If rounds remain below `--rounds`** and the round didn't converge (either yield > 0, or yield
== 0 but `missingClasses` is non-empty), continue to the next round — the next round's Workflow
call reuses the full `CLASSES` list, so a class that failed this round gets a natural retry
alongside everything else. Don't force a human decision about a missing class while rounds are
still available; that's premature friction the round loop already resolves on its own.

**Only once the round limit (`--rounds`) is reached without converging** do the remaining
outcomes apply, in this order:

1. **If `missingClasses` is non-empty**, a class nobody ever reviewed is not evidence it's
   clean — it's an unresolved gap, distinct from "found real issues" (below). Signal
   **"INCOMPLETE — N class(es) unreviewed: `<names>`"** and present the human a choice:
   - Retry only the missing classes (re-invoke the Workflow with `classes` filtered to just those,
     passing the same `PRIOR_FINDINGS` used this round — the script needs both fields)
   - Accept the gap as a known limitation — a missing class has no `file`/`severity`/
     `recommendation` to reuse, so record it as `{file: '<class name> (unreviewed)', severity:
     'N/A', blast_radius: 'local', recommendation: 'retry in a future round'}` alongside the
     real accepted-risk findings
   - Abandon the round
2. **Else if cross-file yield > 0**, see the NOT-converged / single-round-only outcomes below.

A zero-yield round is one sample from a non-deterministic reviewer, not a proof of correctness.
Report convergence as "no new cross-file findings surfaced; residual risk remains in open local
findings and accepted-risk items" — never as "clean" or unconditionally "safe".

**If cross-file yield > 0 when the round limit (`--rounds`) is reached AND more than one round
has actually run**, do NOT terminate quietly and do NOT recommend another broad round — the
generic per-class sweep has stopped paying off. Signal **"NOT converged — escalate to targeted
deep-dive on <theme>"**:
- Present this as a recommendation to the user and wait for their go-ahead — do not spawn the
  deep-dive agent unilaterally; this escalation gets the same human-in-the-loop bar Phase C
  applies to fixes
- Name the recurring theme or cluster in the still-yielding `cross_file` findings
- Recommend spawning **one narrowly-scoped deep-dive agent** aimed at that theme (e.g., "trace
  every caller of `parseX` across the module", "audit every site that restates rule Y") — or hand
  the theme to the user for a judgment call
- Possible underlying causes, mentioned only after the escalation: the PR may be too large
  (consider splitting it), or a new failure mode has appeared that doesn't fit any existing
  class — draft it per the Pattern-File Update Hook below

**If cross-file yield > 0 at the round limit but only one round ever ran** (e.g., a single-round
caller like `/address-pr-issues`'s `--rounds 1` invocation), there is no multi-round trend to
act on — a single round finding and fixing real cross-file issues is normal, not a failure
signal. Report **"Found and fixed N confirmed cross-file findings this round; convergence
unconfirmed — a single round cannot show yield trending to zero"** instead of the deep-dive
escalation.

---

## Pattern-File Update Hook

If a finding doesn't fit any existing class:
1. Draft a new classification entry (description, "How to find" steps, before/after example)
2. Prompt the user to add it to `~/.claude/copilot-review-patterns.md`
3. After the user confirms, refresh the bundled copy:
   ```bash
   cp ~/.claude/copilot-review-patterns.md \
     ~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md
   ```

---

## Summary Output

Return to the calling session (or present to the user if run standalone):

```markdown
## Adversarial Review Summary — <N> round(s)

**Pattern file**: [global | bundled] (~/.claude/copilot-review-patterns.md or references/)
**Pattern classes swept**: <list from PATTERN_CLASSES>
**Rounds completed**: <N> / <max>

### Per-Round Breakdown
| Round | Found | Fixed | Known Limitations | False Positives | Cross-File Yield | Missing Classes |
|-------|-------|-------|-------------------|-----------------|------------------|------------------|

### By Pattern Class
| Class | Findings | Fixed |
|-------|----------|-------|
...

### By Blast Radius
| Blast Radius | Findings | Fixed | Open |
|--------------|----------|-------|------|
| cross_file | | | |
| local | | | |
<Open = not fixed in code, regardless of why (accepted risk, false positive, contradicts
design, or still pending) — Findings = Fixed + Open by construction. Open local findings are
listed here for human disposition — they did not block termination.>

### Known Limitations (for PR Description)
<List of findings classified as "accepted risk" — these MUST appear in the PR description.>

### Outcome
✅ CONVERGED — cross-file yield 0 this round (one sample, not a proof); residual risk: open local findings and accepted-risk items above
⚠️  NOT converged — cross-file yield N at round limit after M>1 rounds; escalate to targeted deep-dive on <theme> (see Phase E)
🔵 Single round only — found & fixed N confirmed cross-file findings; convergence unconfirmed (see Phase E)
🟡 INCOMPLETE — N class(es) unreviewed: <names>; retry, accept as known limitation, or abandon (see Phase E)
❌  Test failures after fix application — do not push until resolved
```

---

## Notes

- **Language-agnostic**: The source file glob covers all common languages. The pattern-class
  heuristics are implementation-language-independent; they describe code logic patterns.
- **Model cost**: Opus agents for the two highest-ROI classes (State Machine, Operator
  Observability) are deliberate. Sonnet handles the rest. Budget ~5-10 agents per round.
- **Cascade sweep is mandatory on first find**: The sweep rule is not optional — it prevents
  the "sibling miss" failure mode where a bug class is fixed in the reported instance but its
  identical siblings in the same diff survive.
- **Known limitations are public commitments**: Accepted-risk findings in the PR description
  are explicit design acknowledgments, not silent omissions. An operator reading the PR can
  understand what was left in and why.
- **Local findings don't block termination**: A `local` finding is confined to one file or
  callsite — if it ever manifests, the session can diagnose and fix it reactively in-context,
  which costs less than another full broad round. `cross_file` findings are the ones a session
  cannot cheaply recover from, so only they drive the yield signal and force more rounds.
- **A missing class is never silently "clean"**: `parallel()`'s barrier means a class that never
  returns is caught, not swallowed — Phase E's INCOMPLETE outcome is a distinct verdict from
  CONVERGED specifically so a review gap can never be mistaken for a clean pass.
