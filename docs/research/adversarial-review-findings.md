# Adversarial Pre-PR Review: Findings and Design Notes

**Context**: On 2026-06-26, we ran a 5-round Opus adversarial review against
`run_step_sync_repos` (a new ~200-line Python function added to the logging-migration plugin
fleet runner). The reviewer swept against the 7 pattern classes in
`~/.claude/copilot-review-patterns.md`. Found 16 real bugs, all fixed, 135 tests passing.

This document captures what worked, what failed, how to improve it, and what a mature skill
should look like. It is the basis for a future `adversarial-review` skill — not the finished
article.

---

## What We Tried

A Workflow with a `while round < 5` loop:

1. **Opus review agent** — reads the copilot-review-patterns.md, runs `git diff`, reads changed
   Python files in full, applies each pattern class's "How to find" heuristics, returns
   structured JSON (`findings[]`, `is_clean`, `summary`).
2. **Sonnet fix agent** — receives the JSON findings, edits files to apply each suggested fix,
   runs pytest, reports pass/fail.
3. Repeats until `is_clean=true` or 5 rounds exhausted.

**Results**: 16 bugs found across 5 rounds. Exited at the round limit, not when clean.

---

## What Worked

### Opus reviewer was accurate
Every one of the 16 findings was a genuine bug matching a copilot pattern class. No false
positives were reported. The structured schema (`pattern_class`, `location`, `suggested_fix`)
forced the reviewer to be specific enough to act on immediately.

### Tests per round caught regressions
Running pytest after every fix round caught when a fix broke something, keeping the suite
green throughout (except when a fix agent corrupted the repo state — see failures below).

### Pattern classification guided fixers
Labeling each finding with its class (State Machine, Infrastructure, etc.) gave the fix agent
enough context to understand the *kind* of fix needed, not just the location.

---

## What Failed

### 1. Fix agent destroyed git history

**What happened**: A fix agent ran `git reset HEAD~1` (likely to "start fresh" before
rewriting the function). This destroyed the committed content from the parent commit that the
agents had no knowledge of — specifically all the non-Python SKILL.md changes (#87, #89, #90,
#93 features). The fix agents then rebuilt from the reset state, compounding the problem.

**Why it happened**: The fix agent was given no constraints on git operations. When it decided
to "redo" a large chunk of code, resetting the commit was a natural but catastrophic choice.

**Fix**: Fix agents must be prohibited from ALL git history operations:
```
PROHIBITED (add to fix agent system prompt):
- git reset (any form)
- git rebase
- git commit
- git stash (pop/apply can leave inconsistent state)
- git checkout -- <file>  (reverts working-tree changes)
- git restore

PERMITTED:
- Edit / Write tools (file edits only)
- Bash (only for: running tests, reading files, grep/find)
- git diff (read-only, to verify a fix was applied)
- git status (read-only)
```

**Cascade effect**: After the reset, the Round 3 review agent saw a SKILL.md that was missing
sync-repos references (because the reset had removed them). It diagnosed this as "sync-repos
is never referenced in SKILL.md" and added a section saying the step is "NOT wired into the
automated flow" — which directly contradicted the design intent. The bug was the wrong
diagnosis from corrupted state, not a real design issue.

---

### 2. Cascades: same root cause found once per round

**What happened**: The "silent staleness" bug class was found in 4 separate rounds:

| Round | Bug | Root cause |
|-------|-----|-----------|
| 1 | SYNC-1: three-dot rev-list range (counts behind + ahead, not just local-ahead) | Wrong git range operand |
| 2 | SYNC-5: FF-merge failure fell through to "Synced OK" | Missing `had_failures` set on merge failure |
| 4 | SYNC-12: rev-list returncode not checked; empty stdout on failure treated as "0 ahead" | Missing returncode guard |
| 5 | SYNC-15: checked-out branch ≠ resolved default branch; rev-list counted against wrong ref | Branch/default mismatch |

Each of these is a distinct code path to the same bad outcome (repo reported synced, left
stale). Fixing SYNC-1 didn't prevent SYNC-5 because they're in different branches of the same
if-block. A review agent that had swept the entire fast-forward block after finding SYNC-1
would have found SYNC-5, SYNC-12, and SYNC-15 in the same round.

**Your observation is correct**: Once the reviewer finds an issue of class X at location L,
it should immediately sweep the rest of the changed function/file for *other manifestations
of the same root cause* before moving to the next class. "Same root cause" is narrower than
"same pattern class" — it means the specific failure mode (e.g., "command result used without
checking returncode").

**Proposed sweep instruction** (add to review agent prompt after finding each issue):
> After finding a bug, ask: "What is the specific failure mode — the one-sentence root cause?"
> Then sweep the rest of the changed code for other locations where that exact failure mode
> can occur. Report all instances before moving to the next pattern class.

This alone would have collapsed 4 rounds into 1 for the silent-staleness cluster, likely
reducing total rounds from 5 to 2.

---

### 3. Fix agents were unaware of PR intent

**What happened**: Fix agents received only the findings JSON. They had no knowledge of what
the PR was supposed to do overall. This caused SYNC-11's fix to add documentation saying
sync-repos is "NOT wired" when the PR's explicit design had Step 0.5 as an orchestration step.

**Fix**: Pass the Intent Brief to the fix agent alongside the findings. The brief (~200 words
describing what the PR is supposed to accomplish, key design decisions) lets the fix agent
recognize when a suggested fix contradicts the design, and adapt accordingly.

---

### 4. Review agent ran git diff (could see corrupted state)

**What happened**: The review agent was instructed to run `git diff origin/master...HEAD`
itself. After the reset, this diff was empty (the reset moved HEAD back to origin/master), so
the reviewer was reading a different code state than intended.

**Fix**: Extract the diff once, before the loop starts, and pass it to each review agent
explicitly. The diff is a fixed artifact — it should not change between rounds. If file
edits change what's in the diff, that's exactly what should be reviewed in the *next* round,
not re-derived mid-loop.

Alternately: if you want each round's reviewer to see the current state (post-fixes),
instruct it to `git diff origin/master...(current branch)` using the branch name, not HEAD,
so it always sees the accumulated state vs the base.

---

## Efficiency Assessment

| Metric | Observed | Notes |
|--------|----------|-------|
| Rounds | 5 (hit limit) | With cascade fix: probably 2-3 |
| Bugs found | 16 | All real, all in one new ~200-line function |
| Tokens | ~665k | ~67k/agent × 10 agents |
| Time | ~40 min | Opus reviewer is slow |
| Files reviewed | Python only | SKILL.md checked for pattern 6 only |

**Overall verdict**: *Effective but inefficient.* The reviewer caught bugs that would have
cost multiple Copilot rounds post-PR. The 16 bugs across 5 rounds represents probably 8-12
Copilot review threads avoided — roughly the cost of Rounds 4-5 × Copilot turnaround time.
The cascade issue is the main efficiency drain: with class-level sweeps, this should converge
in 2-3 rounds for most PRs.

**Is it worth it?** For PRs adding new Python functions with complex control flow (like this
one), yes. For PRs that are mostly documentation or simple SKILL.md edits, no — the overhead
is too high. The pre-pr-audit skill's rubric (run the Copilot simulator only for code
changes, skip for doc-only) is the right gating logic.

---

## Proposed Improvements (priority order)

### P0: Git guardrails (blocker — prevents data loss)
Hard-prohibit all git history operations in fix agent prompts. This is non-negotiable.
A fix that rewrites git history is worse than no fix.

### P1: Class-level root-cause sweep (biggest efficiency gain)
After each finding, the reviewer sweeps the rest of the changed code for the same root cause.
Prompt addition (after the pattern application guide):

> **Same-root-cause sweep rule**: When you find a bug, identify its specific failure mode
> in one sentence (e.g., "subprocess returncode not checked before reading stdout"). Then
> scan every other subprocess call / JSON read / branch exit / etc. in the diff for the
> same failure mode. Report all instances as a cluster before moving to the next pattern
> class. Do NOT rely on subsequent rounds to find them.

### P2: Pass Intent Brief to fix agents
Include the PR's Intent Brief (problem, goal, design decisions) in the fix agent prompt so
it can detect and flag fixes that contradict the design.

### P3: Provide diff as artifact, not git command
Extract the diff once at workflow startup. Pass it to reviewers as a string (or temp file).
This decouples the reviewer from the git state, which the fix agents may have mutated.

### P4: Parallel class sweeps in Round 1
In Round 1, spawn 7 parallel review agents — one per pattern class — instead of one agent
doing all 7 sequentially. Each agent specializes and runs faster. Synthesize all findings
before the fix round. This does NOT eliminate cascades (cascade is about finding all instances
of a root cause, not about finding all classes), but it reduces Round 1 time.

### P5: Commit after each round (optional safeguard)
Fix agent commits after applying fixes. Makes it impossible for subsequent fix agents to
accidentally destroy work via git reset. Downside: intermediate commits in history. Could be
squashed before PR creation.

### P6: Verify state before applying each fix
Fix agent confirms it can see the expected "buggy" code at the reported location before
applying the fix. If the code has already been changed (by a prior fix in the same round),
skip and report. This prevents double-application and incorrect fixes.

---

## Relationship to Existing Skills

### `pre-pr-audit` (satoris-claude-config)
Already has a "Copilot simulator" step (Step 4). This adversarial review approach is a
higher-fidelity, multi-round version of that step. The two should share:
- The same copilot-review-patterns.md as the classification source
- The same gating logic (skip for doc-only, run for code changes)
- The same pass/fail criteria

The main thing `pre-pr-audit` lacks is: (a) the multi-round loop, (b) the class-sweep rule,
and (c) the git guardrails. A mature adversarial-review skill could be called from within
`pre-pr-audit` for Step 4, replacing the current Copilot simulator.

### `address-pr-issues` (satoris-claude-config)
The "sweep PR-touched files for same issue class" feedback memory (in MEMORY.md) is the
same insight as the cascade reduction above. The adversarial review skill should enforce this
proactively so address-pr-issues never sees that pattern in the first place.

### `code-review` (cc-plugins-java-stack)
A general-purpose code reviewer. The adversarial review is more targeted — it focuses on the
7 copilot pattern classes specific to this codebase rather than general review dimensions.
Both have a role: general review for correctness/simplicity, adversarial review for
copilot-pattern bugs.

---

## What a Mature Skill Needs

A production `adversarial-review` skill would need:

1. **Configuration**: Which pattern file to use (default: `~/.claude/copilot-review-patterns.md`)
2. **Scope control**: Which files to review (default: changed files in git diff)
3. **Round limit**: Configurable, default 3 (not 5 — with cascade fix, 3 should be enough)
4. **Gating rubric**: Skip for doc-only PRs; run for code changes (same as pre-pr-audit)
5. **Fix mode control**: `--review-only` (no fixes), `--fix` (apply fixes automatically, default)
6. **Commit mode**: `--commit-per-round` for safety; default is no intermediate commits
7. **Intent brief injection**: Accept the PR Intent Brief to give fix agents design context
8. **Termination report**: Summary of what each round found, class distribution, total bugs
9. **Pattern file update hook**: When a new class of bug is found that doesn't fit existing
   categories, prompt the user to update `copilot-review-patterns.md`

**Estimated rounds to clean for typical PRs**:
- Simple utility function: 1-2 rounds
- Complex stateful function with subprocess calls: 2-3 rounds (with cascade fix)
- SKILL.md or doc-only changes: 1 round (pattern 6 only)

---

## Human-in-the-Loop: Should the Main Session Intervene?

**Short answer: yes, but only at round boundaries — not mid-fix.**

The main session (the conversation that launched the workflow) has context the workflow agents
lack entirely: the PR Intent Brief, the design decisions, what was explicitly deferred, and
the full project history. This is exactly the context that SYNC-11's fix agent needed when it
added "NOT wired into the automated flow" to SKILL.md — contradicting the design.

The current Workflow architecture does not support mid-run intervention: the workflow runs in
the background, and the main session only gets a notification when it completes. There is no
"pause and ask the orchestrator" primitive.

### The structural fix: two-phase per-round design

Instead of one monolithic workflow, restructure as a series of short invocations that return
to the main session between phases:

```
MAIN SESSION
│
├─► Workflow: Review-only (returns structured findings)
│   └── Opus review agent: pattern sweep, returns JSON
│
◄── Main session receives findings
│   · Reviews against Intent Brief
│   · Flags any finding that contradicts the design
│   · Approves or overrides each finding
│
├─► Workflow: Fix-only (receives approved findings, applies fixes, runs tests)
│   └── Sonnet fix agent: applies approved findings
│
◄── Main session receives fix results
│   · Reviews test output
│   · Reviews file diffs for design drift
│
└─► Repeat until clean
```

**What the main session catches that the workflow can't:**
- "This fix contradicts a design decision made in the Intent Brief."
- "This is a documentation accuracy issue in SKILL.md — the code is correct, the doc is
  just describing an earlier design. Don't change the doc; change the task description."
- "This finding is already tracked as a known limitation in the PR description — won't-fix."
- "The reviewer misread the code state — this bug doesn't exist in the current diff."

**What the main session should NOT do:**
- Re-review findings the Opus agent already assessed (trust the reviewer)
- Apply fixes itself (the fix agent is faster and can run tests)
- Override findings without a specific reason anchored in design intent or PR scope

### Practical trade-off

| Mode | Latency | Correctness | When to use |
|------|---------|-------------|-------------|
| Fully autonomous (current) | Lowest | Prone to design drift | Simple PRs, no SKILL.md changes |
| Review-pause (main reviews findings before fix) | +1 pause per round | Catches design contradictions | Any PR touching documentation or skill instructions |
| Full human-in-loop (both phases return to main) | +2 pauses per round | Maximum correctness | Complex PRs, large diffs, first run in a new codebase |

**Recommended default**: Review-pause mode. The main session reviews the findings JSON after
each Opus sweep (takes ~30 seconds), flags contradictions or scope issues, then approves the
fix phase. This catches the SYNC-11 class of problems without adding much latency, because
the bottleneck is the Opus reviewer and the fix agent — not the human review of a structured
JSON list.

### Implementation sketch

The workflow returns after the review phase:
```javascript
// In the workflow script:
const findings = await agent(reviewPrompt, { model: 'opus', schema: FINDINGS_SCHEMA });
return { phase: 'review-complete', findings };  // return to main session
```

The main session reviews, optionally removes or annotates findings, then re-invokes:
```javascript
// In the next workflow invocation:
const approvedFindings = args.findings;  // passed back in from main session
await agent(fixPrompt(approvedFindings), { label: 'fix', phase: 'Fix' });
```

This is clean today with `Workflow({args: approvedFindings})` — the main session is already
the natural checkpoint between invocations.

---

## Open Questions

1. **Should the review agent see the full file or just the diff?**
   Current approach: diff + full file for context. This is correct but expensive. Could we
   give it the diff only and only fetch context on demand? Probably not — the "same root
   cause" sweep requires seeing the full function, not just the changed lines.

2. **Should fix agents ever add new tests?**
   Currently: only for Test Integrity findings. In practice, several rounds (SYNC-8, SYNC-13)
   added tests for previously-uncovered paths. The answer is yes — test additions are always
   safe. The guardrail should be: "add tests to existing test classes, don't create new ones."

3. **How do we handle SKILL.md / markdown files?**
   Pattern 6 (Documentation Accuracy) applies. But "fixes" to SKILL.md are more ambiguous —
   the reviewer may misread the design intent (as SYNC-11 did). Fix agents editing SKILL.md
   need the Intent Brief especially strongly, or SKILL.md fixes should be reviewer-only
   (reported but not auto-fixed).

4. **Is 5 rounds ever justified?**
   In this run, the 5-round limit was hit. With the cascade fix, 3 rounds should be the
   ceiling. If a PR still isn't clean after 3 rounds with cascades, that's a signal either
   (a) the PR is too large and should be split, or (b) a new bug class has been discovered
   and the patterns file needs updating.

---

## Should You Pursue This?

The honest answer is yes — but not yet, and not as a new standalone skill.

The value case is real in a way that goes beyond saving manual steps. PR-1 for the
logging-migration plugin accumulated 21 Copilot review rounds. The adversarial review of
PR-2's sync-repos function found 16 bugs in code that hadn't yet been submitted. Several
of those — the three-dot rev-list range, the missing returncode check, the NOT_STARTED state
filter — are exactly the class of finding that would have cost a full Copilot round each:
submit, wait, context-switch back, read the comment, ask Claude to fix it, push, wait again.
Even a conservative estimate puts this at 6-8 avoided Copilot rounds just for that one
function. And those avoided rounds aren't merely time saved. They're avoided opportunities to
introduce new bugs through late-round fixes in a context that has grown stale.

But the version we ran today is not safe to use again without changes. The git reset incident
wasn't a near-miss — it destroyed committed work in a way that would have been invisible if
the reflog hadn't captured it. A tool that requires this level of post-hoc forensics to catch
its own failures isn't a productivity multiplier. It's a liability that happens to also find
bugs.

The deeper case for pursuing this isn't about freeing up manual steps in the review cycle,
though it does that. It's about what kind of reviewer this can be. Copilot reviews without
context. It doesn't know what was deferred, what was intentional, what design decision drove
a choice that looks odd in isolation. So it flags things that are correct, and you end up
spending rounds marking findings won't-fix, which is its own kind of friction. An adversarial
review run before Copilot ever sees the PR, with me in the loop at round boundaries, produces
something different: a reviewer that understands intent and applies the pattern classes with
that understanding. The SYNC-11 failure — where a fix agent added documentation contradicting
the Step 0.5 design — happened precisely because the fix agent was operating without that
context. With review-pause mode, that finding would have taken thirty seconds to flag and
override. The bug would have been documented accurately, the design preserved, and Copilot
would never have had the chance to ask about it.

**What to build first, and where.** Don't create a new plugin. The `pre-pr-audit` skill
already has a Copilot simulator step — it's the right home for what this becomes. The three
changes it needs, in priority order, are: the git guardrails (a single hardcoded prohibition
in the fix agent prompt — non-negotiable before any further use), the cascade sweep rule
(one paragraph instructing the reviewer to identify the specific failure mode and sweep the
full diff for other instances before moving to the next class), and the review-pause mode
(the workflow returns findings to the main session before the fix phase runs, giving us a
shared checkpoint). Those three changes address both of your observations directly, fix the
only catastrophic failure mode, and don't require maintaining a new plugin.

**How to know if it's working.** Run it on the next PR that has non-trivial Python changes.
Count how many findings the review produces, how many rounds it takes to converge, and how
many of those findings Copilot also flags after the PR is submitted. If the adversarial review
catches most of what Copilot would catch, and the review-pause checkpoint takes less than a
minute per round, the tool is earning its cost. If Copilot still finds a substantial number
of issues the adversarial review missed, the pattern classes need updating — which is itself
useful information about where the patterns file is incomplete.

The goal you named — the best that both of us can produce — is the right frame. This tool
isn't about replacing Copilot or replacing your judgment. It's about inserting a review pass
that has both pattern coverage and design context before the code reaches an automated
reviewer that has neither. Done right, by the time Copilot sees the PR, the substantive
bugs are already fixed and the remaining comments are style, naming, or genuinely ambiguous
tradeoffs worth discussing — not correctness issues that should have been caught earlier.

---

## Copilot Comparison Assessment

**Context**: PR #101 (logging-migration PR-2) received 6 rounds of Copilot review after the
5-round adversarial pre-PR review. All 15 Copilot findings across those rounds were valid and
fixed (Round 3 produced no new threads). This section records what Copilot found, how it maps
to what the adversarial review did or didn't catch, and what the gap reveals about where each
reviewer is strong.

### The 15 Copilot Findings

**Round 1 (commit 920aba5):**

| # | Location | Issue | Pattern Class | Adversarial |
|---|----------|-------|--------------|-------------|
| R1-1 | `fleet_runner.py:577` | `ahead_count` guard: `rc=0` with empty stdout fell through to "Synced OK" | State Machine / Control Flow | Partial — SYNC-12 caught `rc≠0` but not `rc=0` empty stdout |
| R1-2 | `SKILL.md:586` | Branch naming docs claimed jiraTicket embedded; `_branch_name()` didn't include it | Documentation Accuracy (also implementation gap) | Missed entirely |
| R1-3 | `SKILL.md:741` | ADF text node `[PR]({prUrl})` renders literal brackets in Jira | Documentation Accuracy | Missed entirely |
| R1-4 | `SKILL.md:757` | Same ADF issue in the JSON example block | Documentation Accuracy | Missed entirely |
| R1-5 | `SKILL.md:818` | J9-3b: `prMergedAt` falsely implies Jira comment was already posted | State Machine / Control Flow | Identified as Risk Area 3, accepted as trade-off — Copilot correctly flagged it |

**Round 2 (commit 7887373):**

| # | Location | Issue | Pattern Class | Adversarial |
|---|----------|-------|--------------|-------------|
| R2-1 | `fleet_runner.py:555` | Fast-forward ran even on wrong branch: `if ahead_count == "0"` checked before `elif current_branch != base` | State Machine / Control Flow | Partial — SYNC-15 caught wrong-branch scenario but missed the `if`/`elif` ordering |
| R2-2 | `fleet_runner.py:508` | Detached HEAD error message said "check out master" instead of "check out the default branch (master or main)" | Operator Observability | Missed entirely |
| R2-3 | `fleet_runner.py:544` | Unexpected-branch error message same "master" precision issue | Operator Observability | Missed entirely |
| R2-4 | `fleet_state.py:165` | `UnicodeDecodeError` caught and reported as "Invalid JSON" | Operator Observability | Partial — SYNC-9 added the `except UnicodeDecodeError` clause; missed that the error message was wrong |
| R2-5 | `CHANGELOG.md:19` | Changelog entry said `[PR]({prUrl})` instead of `{prUrl}` | Documentation Accuracy | Missed entirely |

**Round 3**: No new threads.

**Round 4 (commit 50c99d5):**

| # | Location | Issue | Pattern Class | Adversarial |
|---|----------|-------|--------------|-------------|
| R4-1 | `fleet_runner.py:599` | Wrong-branch block reason omits `git remote set-head origin -a` remediation hint when the inferred base branch may be a fallback | Operator Observability | Missed entirely |
| R4-2 | `fleet_runner.py:1350` | `_default_base_branch()` silently falls back to "master" with no warning when `git symbolic-ref refs/remotes/origin/HEAD` fails | Operator Observability | Missed entirely |

**Round 5 (commit 8e50507):**

| # | Location | Issue | Pattern Class | Adversarial |
|---|----------|-------|--------------|-------------|
| R5-1 | `fleet_runner.py:535` | `git status` returncode not checked; non-zero with empty stdout silently passes the dirty-tree gate | State Machine / Control Flow | Missed — same root cause as SYNC-12 (`subprocess.run` result used without checking returncode) but on a different command |
| R5-2 | `SKILL.md:434` | Subagent prompt referenced `.claude/migration-plan.md` (fleet-level file absent from per-repo worktrees) | Documentation Accuracy | Missed entirely |

**Round 6 (commit cdbe8fd):**

| # | Location | Issue | Pattern Class | Adversarial |
|---|----------|-------|--------------|-------------|
| R6-1 | `fleet_runner.py:552` | `sync-repos` allowed `logging-migration/*` branches for `NOT_STARTED` repos — baseline-corruption risk (repos with abandoned prior migration code passed the clean-baseline gate) | State Machine / Control Flow | Missed — same class as SYNC-3/SYNC-5 (fallback bypasses safety guard) but triggered by branch state, not command result |

### Coverage Summary

| Pattern Class | Copilot found | Adversarial caught fully | Adversarial caught partially | Adversarial missed |
|---|---|---|---|---|
| State Machine / Control Flow | 5 | 0 | 2 (SYNC-12, SYNC-15) | 3 (R1-5 accepted-risk; R5-1, R6-1 missed) |
| Operator Observability | 5 | 0 | 1 (SYNC-9) | 4 |
| Documentation Accuracy | 5 | 0 | 0 | 5 |
| **Total** | **15** | **0** | **3** | **12** |

### What the Gap Reveals

**State Machine / Control Flow: adversarial is strong but finds the cluster, not all its branches.**

The adversarial review found SYNC-12 (missing `returncode` check) and SYNC-15 (wrong-branch
mismatch) — the same bug family as R1-1 and R2-1. But in both cases it caught the precursor
to the problem, not the final manifestation that Copilot saw. SYNC-12 guarded against a
non-zero returncode; R1-1 was a zero-returncode with empty stdout — a distinct failure path
that the round-by-round sweep didn't reach because SYNC-12's fix moved the code in a way that
exposed the gap. This is exactly the cascade pattern described in "What Failed" above: the
same root cause ("command result used before validation") appeared across four separate rounds
because each fix only closed one exit path. The class-level sweep rule (P1) would have found
all four in round 1 — including the paths that Copilot eventually flagged.

R1-5 (J9-3b idempotency) is a different kind of miss: the adversarial review identified it as
a risk but accepted it as an intentional trade-off. Copilot correctly flagged that the prose
created a false implication regardless of intent. This argues for treating "accepted risk"
findings as incomplete, not resolved — they should go into the PR description as known
limitations and be reviewed again by Copilot. An adversarial reviewer that says "this is risky
but acceptable" should mean the risk is documented and surfaced to Copilot, not silently buried.

**Operator Observability: a systematic blind spot.**

All three Operator Observability findings were missed. The pattern class in `copilot-review-patterns.md`
focuses on "error messages asserting the wrong root cause" and "rejection messages omitting the
values driving the decision." The R2-2/R2-3 findings are about *imprecise* messages — "check
out master" is not *wrong* (master is the correct branch for these repos) but it's imprecise
enough to mislead operators whose repos use `main`. The R2-4 finding is a classic wrong-root-cause
error message: "Invalid JSON" for a UTF-8 encoding failure is technically a parse error but the
actionable diagnosis is entirely different.

The heuristic in the pattern file needs sharpening for this class:

> Current: "error messages asserting the wrong root cause"
> Missing: "error messages naming a specific value (e.g., branch name, encoding) when the code
> handles a more general range of values — the message should reflect the range, not one instance"

None of the adversarial rounds applied this angle. The Opus reviewer was looking for messages
that were *false*, not messages that were *too specific*. That's a prompt gap, not a pattern-class
gap — but it's narrow enough that adding one example to the Operator Observability section in
`copilot-review-patterns.md` would likely close it.

**Documentation Accuracy: Copilot's systematic advantage.**

All four Documentation Accuracy findings were missed. The pattern class in the patterns file
covers "docstrings that don't match the implementation" — and the adversarial review did apply
it (SYNC-16 found a docstring that listed 2 of 7 block conditions). But the Copilot findings
fell outside that scope in two ways:

1. **ADF rendering behavior** (R1-3, R1-4): this is domain-specific knowledge about how Atlassian
   Document Format text nodes work. No pattern heuristic will catch it without knowing that ADF
   text nodes don't render Markdown. This is the class of finding that requires either ADF domain
   knowledge in the reviewer's context, or a dedicated "ADF rendering" check in the Jira integration
   section of the patterns file.

2. **Implementation gap vs doc gap** (R1-2): the branch naming mismatch was listed under
   Documentation Accuracy but it was actually an implementation bug — the code didn't do what the
   doc said. The adversarial review read the docs and the code separately; it should have compared
   them. A "spec-code coherence" sweep (does the documented behavior match the implemented behavior?)
   would catch this class.

3. **Changelog accuracy** (R2-5): the CHANGELOG entry was stale because the ADF fix in R1 wasn't
   reflected back in the changelog. This is outside the Python diff, so the reviewer never read it.
   The fix: add "read CHANGELOG.md for any entries touching the same features as the diff" to the
   review scope. Changelog accuracy falls under Documentation Accuracy (class 6) and should be
   explicit in the heuristics.

### Efficiency Verdict

Without the adversarial pre-PR review, PR #101 would likely have arrived at Copilot with 16
additional bugs in the Python files alone (the ones fixed pre-PR). A conservative estimate of
5 findings per Copilot round would have produced 3-4 more rounds of review before the PR was
mergeable — at Copilot's turnaround time of hours per round, that's roughly a day of latency
plus the context-switch cost of returning to a PR after each round.

The adversarial review absorbed those 16 bugs and reduced Copilot's workload to 15 findings
across 6 rounds (1 empty) — still substantial, but weighted toward the pattern classes where
the adversarial review is systematically weaker. The pattern-class breakdown of those 15
findings shows where the value was captured:

- **State Machine / Control Flow** bugs: the adversarial review found the cluster; Copilot found
  the last two exit paths the cascade sweep missed. Net: shared credit.
- **Operator Observability** bugs: Copilot found all three. Adversarial review was blind to
  error-message precision issues. Net: Copilot's advantage.
- **Documentation Accuracy** bugs: Copilot found all four. Adversarial review's scope
  (changed Python files) didn't include SKILL.md line-by-line cross-referencing with the docs,
  ADF domain knowledge, or changelog coverage. Net: Copilot's advantage.

**The complementarity is real and predictable.** Adversarial review is strongest on:
- Control flow bugs with multiple exit paths
- Missing guards on system calls (subprocess returncode, JSON decode, unicode)
- Logic bugs visible from a function-level state machine trace

Copilot is stronger on:
- Error message accuracy and operator-facing precision
- Cross-artifact consistency (code vs docs vs changelog)
- Domain-specific rendering/platform behavior that requires external knowledge

### Pattern File Updates

Applying this assessment to `~/.claude/copilot-review-patterns.md`:

| Class | Count before PR#101 | Rounds 1–2 | Rounds 4–6 | Count after |
|-------|---------------------|-----------|-----------|-------------|
| State Machine / Control Flow | 9 | +3 (R1-1, R1-5, R2-1) | +2 (R5-1, R6-1) | 14 |
| Operator Observability | 7 | +3 (R2-2, R2-3, R2-4) | +2 (R4-1, R4-2) | 12 |
| Documentation Accuracy | 3 | +4 (R1-2, R1-3, R1-4, R2-5) | +1 (R5-2) | 8 |

**New heuristic candidates for the patterns file:**

- **Operator Observability**: Add "messages that name a specific value (branch name, encoding,
  file format) when the code handles a more general range — verify the message reflects the range"
- **Documentation Accuracy**: Add "ADF / external-format rendering" as a named sub-class for any
  Jira/Confluence integration code. Text nodes do not render Markdown; raw URLs auto-link.
- **Documentation Accuracy**: Add "spec-code coherence" — compare documented behavior with
  implemented behavior for any feature described in SKILL.md alongside its implementing code.
- **Documentation Accuracy**: Add "changelog coverage" — for any commit fixing a previous commit's
  artifact (e.g., fixing a CHANGELOG entry from an earlier commit in the same PR), check that the
  fix is reflected back in the changelog.
