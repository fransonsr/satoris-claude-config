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

# List changed doc files (for doc/spec lenses — see Phase A)
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
every Phase A agent sees the same state — consistent across all agents in the round — without
the orchestrator needing to hold or pass file contents itself.

---

## Per-Round Loop

Repeat up to `--rounds` times. After each round, check the termination condition (Phase E) before
deciding whether to continue.

### Phase A — Parallel Review (one agent per class)

Spawn one review agent for **each entry in `PATTERN_CLASSES`**. Run them concurrently.

**Every review agent prompt MUST include:**

1. The relevant pattern class section (cut from `$PATTERNS_FILE`)
2. The pinned `BASE_BRANCH`, `CURRENT_BRANCH`, and the enumeration commands from Setup Step 4
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

Reference classes by name only, as `PATTERN_CLASSES` does — never by number. Numbers drift as
classes are added, renamed, or reordered in the patterns file; names are the stable identifier.

**Model selection:**
- **Opus**: State Machine / Control Flow Logic; Operator Observability / Error Message Accuracy; any class flagged by the user as high-complexity
- **Sonnet**: all other classes

**Cascade sweep rule — embed this verbatim in every review agent prompt:**

> When you find a bug, state its specific failure mode in one sentence (e.g., "subprocess
> returncode used before checking stdout"). Then scan *every other callsite of the same kind*
> in the entire changed source — every subprocess call, every JSON read, every branch exit —
> for the same failure mode before reporting. Report all instances together as a cluster.
> Do NOT hold back and expect later rounds to catch siblings. A missed sibling is a miss.

**Output schema per agent (JSON):**

```json
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "blast_radius": "local|cross_file",
      "blast_radius_justification": "grepped for other callers of parseX — none found",
      "file": "path/to/file.py:lineNumber",
      "pattern_class": "State Machine / Control Flow Logic",
      "description": "...",
      "recommendation": "...",
      "cascade_siblings": ["path/to/file.py:otherLine"]
    }
  ],
  "is_clean": true
}
```

Return `"is_clean": true` (with an empty `findings` array) if the class is fully clear.

Classify `blast_radius` structurally, never by severity or gut feel: `local` = confined to one
file/callsite, something the current session could diagnose and fix in-context if it ever
manifested; `cross_file` = spans multiple files, affects call sites outside the diff, or restates
a rule defined elsewhere (e.g., a doc restating a code constant). `blast_radius_justification`
must cite structural evidence the agent actually checked — a grep for other callers, the other
file that restates the rule; a `local` tag with no evidence is invalid, and `local` is never a
reason to down-rank a real bug.

### Phase B — Synthesize

Collect all agent outputs. Deduplicate findings by `(file, line_range)`:
- When two agents flag the same location, keep the **more specific** recommendation
- Record **both** `pattern_class` values in the merged finding (a finding can belong to two classes)
- When merged findings disagree on `blast_radius`, keep `cross_file` (the wider radius wins) and
  carry its justification into the merged finding
- Sort remaining findings: CRITICAL → HIGH → MEDIUM → LOW

Then compute this round's **cross-file yield**: the count of `cross_file` findings that do not
match (by `(file, line_range)`) any finding surfaced in any prior round of this review run.
Maintain a running record of every `(file, line_range)` and `blast_radius` seen across all
rounds this review run — yield compares against that full history, not just the immediately
preceding round. `local` findings never count toward yield. Record the yield with the round's
results — Phase E uses it as the termination signal.

### Phase C — Review-Pause (human decision)

Present the synthesized findings to the calling session. For each finding, the user classifies it:

| Disposition | Action |
|-------------|--------|
| **Fix** | Proceed to Phase D |
| **Contradicts design** | Override — no fix; do not flag as "missed" |
| **Accepted risk** | Record as a known limitation; include in the Summary Output's Known Limitations section and PR description. Do NOT silently drop — the absence of a finding in the summary is a claim that it was addressed |
| **False positive** | Skip; note the reason in the round summary |

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

The next round's Phase A agents will self-diff the now-modified working tree when they start —
the orchestrator does not need to re-read or re-pass file contents between rounds.

Termination is driven by the round's **cross-file yield** (computed in Phase B), not by
`is_clean` flags. Open `local` findings never force another round — report them in the Summary
Output for human disposition and move on.

**Terminate as CONVERGED when:**
- Cross-file yield == 0 — no new `cross_file` finding this round, even if `local` findings remain open

Otherwise (cross-file yield > 0 and the round limit has not yet been reached), continue to the
next round.

A zero-yield round is one sample from a non-deterministic reviewer, not a proof of correctness.
Report convergence as "no new cross-file findings surfaced; residual risk remains in open local
findings and accepted-risk items" — never as "clean" or unconditionally "safe".

**If cross-file yield > 0 when the round limit (`--rounds`) is reached**, do NOT terminate
quietly and do NOT recommend another broad round — the generic per-class sweep has stopped paying
off. Signal **"NOT converged — escalate to targeted deep-dive on <theme>"**:
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
| Round | Found | Fixed | Known Limitations | False Positives | Cross-File Yield |
|-------|-------|-------|-------------------|-----------------|------------------|

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
⚠️  NOT converged — cross-file yield N at round limit; escalate to targeted deep-dive on <theme> (see Phase E)
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
