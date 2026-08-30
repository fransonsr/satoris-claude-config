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

- Directly: `Skill(satori:adversarial-review)` or `/adversarial-review` — standalone sweep before opening a PR
- Called by `/pre-pr-audit` Step 4.7 with `--rounds 3`
- Called by `/address-pr-issues` Step 3.5 with `--rounds 1`

## Inputs (all optional, with defaults)

| Arg | Default | Description |
|-----|---------|-------------|
| `--rounds N` | `3` | Maximum review rounds |
| `--base-branch BRANCH` | auto-detect | Compare against this branch — see Setup Step 3 for the exact resolution order |
| `--intent-brief "..."` | _(prompt user)_ | ~200 words: problem statement, design decisions, what was deferred |

If `--intent-brief` is not supplied by a caller, ask the user to provide it before proceeding.
The Intent Brief is the single most important input: without it, fix agents cannot distinguish
"intentional design decision" from "bug to fix." Store it as `INTENT_BRIEF` — referenced by that
name in Setup Step 5 and the Phase A/B Workflow call below.

---

## Setup (run once before the round loop)

### 1. Resolve the pattern file

```bash
# Prefer the living user-global copy; fall back to the bundled snapshot
PATTERNS_FILE=~/.claude/copilot-review-patterns.md
if [ ! -f "$PATTERNS_FILE" ]; then
  PATTERNS_FILE=~/.claude/plugins/marketplaces/satoris-claude-config/plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md
fi
# The fallback needs its own existence check too — the primary path is guarded, but with neither
# file present this would otherwise surface much later and misattributed: Setup Step 2's grep
# would fail to stderr, PATTERN_CLASSES would come back empty, and the first hard stop an operator
# actually sees would be Phase A/B's missing-arg guard throwing over an empty `classes` array —
# nothing pointing back at the real cause, a missing pattern file.
if [ ! -f "$PATTERNS_FILE" ]; then
  echo "🛑 No pattern file found at either the global (~/.claude/copilot-review-patterns.md) or bundled path — cannot enumerate pattern classes." >&2
  exit 1
fi
echo "$PATTERNS_FILE"
```

Echo the resolved path — it's the only observed record of which branch (global vs. bundled) fired, and it's what gets passed verbatim into the Phase A/B script's `patternFile` arg below.

### 2. Enumerate pattern classes dynamically

```bash
# DO NOT hardcode a number — classes grow as new issues are encountered
PATTERN_CLASSES=$(grep "^### [0-9]" "$PATTERNS_FILE" | sed 's/^### [0-9]*\. //')
if [ -z "$PATTERN_CLASSES" ]; then
  echo "🛑 $PATTERNS_FILE has no '### N. <name>' headings — cannot build CLASSES. Check the file's format." >&2
  exit 1
fi
```

### 3. Resolve the base branch

**If the caller supplied `--base-branch` (see Inputs above), set `BASE_BRANCH_ARG` to that value
before running this step; leave it unset otherwise.** The block below checks for it and uses it
directly, skipping auto-detection entirely — auto-detect is the fallback for when no override was
given, not a check that runs regardless:

```bash
if [ -n "$BASE_BRANCH_ARG" ]; then
  BASE_BRANCH="$BASE_BRANCH_ARG"
  BASE_SOURCE="arg"
else
  # NOT `@{u}` (the current branch's OWN upstream, e.g. origin/feature-x when ON feature-x) —
  # that resolves to the current branch itself once it's been pushed with -u, which every round
  # of /address-pr-issues does, making BASE_BRANCH == CURRENT_BRANCH and every subsequent diff
  # empty. Ask the PR itself first, then the repo's actual default branch:
  BASE_BRANCH=$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null)
  BASE_SOURCE="gh-pr"
  if [ -z "$BASE_BRANCH" ]; then
    BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's#.*/##')
    BASE_SOURCE="origin-head"
  fi
  if [ -z "$BASE_BRANCH" ]; then
    # Remote-tracking refs, not local refs/heads/* — every downstream diff uses an origin/-prefixed
    # range, and a shallow clone, a worktree checked out to only the feature branch, or a CI runner
    # can have origin/main or origin/master without a local main/master branch ever existing.
    if git show-ref --verify --quiet refs/remotes/origin/main; then
      BASE_BRANCH=main
    elif git show-ref --verify --quiet refs/remotes/origin/master; then
      BASE_BRANCH=master
    else
      echo "Cannot detect base branch — supply --base-branch" >&2
      exit 1
    fi
    BASE_SOURCE="origin-fallback"
  fi
fi
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "BASE_BRANCH=$BASE_BRANCH (resolved via $BASE_SOURCE) CURRENT_BRANCH=$CURRENT_BRANCH"

# A resolved name is not the same as one that actually exists on origin — gh-pr/origin-head can
# name a branch never fetched locally, or an arg can be misspelled. Fail loudly here instead of
# letting a later git command's fatal error get silently swallowed by a `2>/dev/null` downstream.
if ! git rev-parse --verify --quiet "origin/$BASE_BRANCH^{commit}" >/dev/null; then
  # NOT a bare `git fetch origin $BASE_BRANCH` — verified that in a restricted-refspec clone
  # (shallow, --single-branch, a CI runner checked out to only the feature branch — exactly the
  # scenario this guard exists for) the bare form fetches into FETCH_HEAD only and does NOT create
  # refs/remotes/origin/$BASE_BRANCH, so re-running this check fails again with the same error.
  echo "🛑 origin/$BASE_BRANCH does not exist locally (resolved via $BASE_SOURCE) — never fetched? remote not named 'origin'? base branch renamed? Run 'git fetch origin $BASE_BRANCH:refs/remotes/origin/$BASE_BRANCH' (the explicit-refspec form — a bare 'git fetch origin $BASE_BRANCH' does not create the remote-tracking ref in a restricted-refspec clone) or supply --base-branch." >&2
  exit 1
fi

# A resolution bug or a caller-supplied override that happens to match the current branch both
# produce an empty diff, which every per-class agent would then report as clean — a false
# CONVERGED verdict over a diff that was never actually examined. Refuse instead:
if [ "$BASE_BRANCH" = "$CURRENT_BRANCH" ]; then
  echo "🛑 BASE_BRANCH and CURRENT_BRANCH are both '$BASE_BRANCH' (resolved via $BASE_SOURCE) — refusing to review an empty diff. Supply a --base-branch that differs from the current branch." >&2
  exit 1
fi

# Two-dot form against the merge-base — NOT a three-dot commit range (`A...B`), which diffs
# commit-to-commit and can NEVER see uncommitted working-tree changes. Phase D's fixes are applied
# but deliberately never committed (guardrails below prohibit `git commit`), so a three-dot range
# would go blind to every fix the moment Phase D ran, making every round after the first re-diff
# the identical pre-fix content and re-report the same findings as "new" cross-file yield forever.
# MERGE_BASE is pinned once here and reused for the whole review (Setup Step 4, buildPrompt()), so
# every agent in every round compares against the same fixed point regardless of what accumulates
# on either branch meanwhile — whether this session's own practice (committing between rounds) or
# the documented default (leaving Phase D's fixes uncommitted).
MB_ERR=$(git merge-base "origin/$BASE_BRANCH" HEAD 2>&1); MB_RC=$?
if [ "$MB_RC" -eq 1 ]; then
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD found no common ancestor (shallow clone? unrelated histories? run 'git fetch --unshallow origin $BASE_BRANCH') — no diff range can be computed." >&2
  exit 1
elif [ "$MB_RC" -ne 0 ]; then
  # Any other exit code is a git error unrelated to "no common ancestor" (unborn HEAD, an
  # unresolvable/ambiguous HEAD, a corrupt object store, not a work tree, ...) — print git's own
  # message instead of asserting the wrong cause and prescribing a remedy that won't fix it.
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD failed (exit $MB_RC): $MB_ERR" >&2
  exit 1
fi
MERGE_BASE="$MB_ERR"
if [ -z "$MERGE_BASE" ]; then
  echo "🛑 git merge-base origin/$BASE_BRANCH HEAD returned nothing — no diff range can be computed." >&2
  exit 1
fi
DIFF_RC=0
git diff --quiet "$MERGE_BASE" || DIFF_RC=$?
# `git diff`/`git ls-files` only ever see TRACKED content — a change consisting solely of new,
# never-`git add`ed files (the canonical "after implementing a feature but before committing" case
# this skill is built for) makes the tracked-diff exit 0 even though real content exists. Union in
# untracked files before deciding the diff is empty.
UNTRACKED_FILES=$(git ls-files --others --exclude-standard)
if [ "$DIFF_RC" -eq 0 ] && [ -z "$UNTRACKED_FILES" ]; then
  echo "🛑 diff against merge-base $MERGE_BASE is empty (no tracked changes, no untracked files) — refusing to report a round as CONVERGED with nothing reviewed. Check BASE_BRANCH/CURRENT_BRANCH above." >&2
  exit 1
elif [ "$DIFF_RC" -ge 2 ]; then
  echo "🛑 git diff against merge-base $MERGE_BASE failed (exit $DIFF_RC) — this is a git error, not an empty diff. Re-run 'git diff $MERGE_BASE' directly to see the actual error." >&2
  exit 1
fi
CHANGED_FILE_COUNT=$(( $(git diff --name-only "$MERGE_BASE" | wc -l) + $(echo "$UNTRACKED_FILES" | grep -c . || true) ))
echo "MERGE_BASE=$MERGE_BASE CHANGED_FILE_COUNT=$CHANGED_FILE_COUNT"
```

### 4. Pin the comparison refs (run once)

Record this value and pass it verbatim to every review agent — `BASE_BRANCH`/`CURRENT_BRANCH`
are only used for the self-match check and error messages in Setup Step 3; `MERGE_BASE` is the
only one actually threaded into agent prompts. **Agents run their own diff and read the files
their lens needs** — the orchestrator does not pre-read or paste file contents into agent prompts.

```bash
# Pinned from Step 3 — fixed for all agents in all rounds
MERGE_BASE=<resolved in Step 3>
```

Agents use this ref value with the following enumeration commands (embed these in every agent
prompt alongside the ref). Note the two-dot form — `git diff $MERGE_BASE`, no second ref — rather
than a three-dot commit range: three-dot diffs commit-to-commit and cannot see uncommitted
changes, which would make every round after the first blind to Phase D's own (deliberately
uncommitted) fixes from the prior round. `git diff`/`git diff --name-only` only see **tracked**
content, so every enumeration below unions in `git ls-files --others --exclude-standard` — a
change consisting solely of brand-new, never-`git add`ed files would otherwise be invisible:

```bash
# Orientation: run once at review start to see what changed and where — includes uncommitted
# working-tree changes (e.g. a prior round's Phase D fixes), unlike a three-dot commit range
git diff $MERGE_BASE

# List changed source files (read in full for cascade sweep) — tracked diff UNION untracked files
{ git diff --name-only $MERGE_BASE; git ls-files --others --exclude-standard; } \
  | grep -E "\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$" | sort -u

# List changed doc files (for doc/spec lenses — see Setup Step 5)
#   (1) doc files changed directly in the PR (tracked diff UNION untracked files)
{ git diff --name-only $MERGE_BASE; git ls-files --others --exclude-standard; } \
  | grep -E "(\.md|\.rst|\.adoc|CHANGELOG|README)" | sort -u
#   (2) README/CHANGELOG adjacent to any changed source file (up one directory)
{ git diff --name-only $MERGE_BASE; git ls-files --others --exclude-standard; } \
  | grep -E "\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$" \
  | xargs -I{} dirname {} 2>/dev/null | sort -u \
  | xargs -I{} sh -c 'find {} "{}/.." -maxdepth 1 \( -name "README*" -o -name "CHANGELOG*" \) 2>/dev/null' \
  | sort -u
```

Each agent runs the diff **once at the start of its review**, before applying its lens. An agent
must not re-diff after Phase D fixes begin. Within a round the tree is frozen until Phase D, so
every review agent sees the same state — consistent across all agents in the round — without
the orchestrator needing to hold or pass file contents itself.

### 5. Build per-class agent metadata (run once — reused by every round)

For **each entry in `PATTERN_CLASSES`**, build one lightweight metadata record — do **not** cut
or read the pattern-class text into your own context here. The Phase A/B script (below) builds
each agent's actual review prompt at call time, and every spawned per-class agent reads its own
section of `$PATTERNS_FILE` directly, in its own isolated context — not the orchestrator's, and
not the `Workflow` script's (the script itself has no filesystem access; only spawned agents do).

The earlier approach — the orchestrating session `Read`-ing the pattern file itself to hand-cut
each class's section for embedding directly into a prompt string — has been observed to burn
~40,000 tokens on a single partial read, before the review itself had started: doing that per
class means the full pattern file's text lands in the orchestrator's own context once per class,
not once total. Passing a shell variable instead doesn't avoid this — the `Workflow` tool's
`args` must be literal JSON authored directly in the tool call, so any text assigned to a shell
variable would still have to pass through the orchestrator's context to be written out. The only
way to keep the pattern-class prose out of the orchestrator's context entirely is to never build
the per-class prompt there at all.

Store the result as `CLASSES`: a list of `{ name, lensKind, model? }`:

- `name` — the pattern class name, exactly as `PATTERN_CLASSES` returns it. Reference classes by
  name only, never by number — numbers drift as classes are added, renamed, or reordered in the
  patterns file; names are the stable identifier.
- `lensKind` — one of `code` | `doc` | `both`, telling the Phase A/B script which file-reading
  instruction to embed for this class:
  - `code`: State Machine / Control Flow Logic, Defensive Guards (null / type / encoding),
    Operator Observability / Error Message Accuracy, Provenance / Identity Discrimination,
    Infrastructure / Environment Handling, Test Integrity, Code Smells / SOLID & Structural
    Quality — read the full contents of changed **source** files
  - `doc`: Documentation Accuracy, Operator Spec Completeness, Spec Operator Walkthrough — read
    the full contents of changed **doc** files; read source files only if the lens explicitly
    requires cross-referencing code (e.g., Documentation Accuracy's doc-vs-code checks)
  - `both`: Cross-File Rule Consistency, Semantic Correctness / Logical Completeness — read full
    contents of **both** changed source and doc files. Semantic Correctness's own definition in
    `copilot-review-patterns.md` is "Code or documentation," and 3 of its 4 documented forms
    (validator/regex too permissive, conditional fall-through missing an unsafe case, two parts of
    the codebase disagreeing on a value's format) require reading source, not just docs — grouping
    it under `doc` alone would starve those 3 forms of the files they need to check
  - A class not named in any bucket above (e.g. one just added via the Pattern-File Update Hook):
    **leave `lensKind` unset** for it — do not guess `both` yourself. `buildPrompt()` defaults an
    unset/unrecognized `lensKind` to `both` (the safe over-read) and logs the class name so the
    bucket lists above get updated; setting `lensKind: 'both'` explicitly here would skip that
    log, since `both` is itself a valid, recognized value
- `model?` — per Model Selection below

**Model selection** (used as the `model` override when the Workflow script below calls `agent()`;
omit for Sonnet — it's the default):
- **Opus**: State Machine / Control Flow Logic; Operator Observability / Error Message Accuracy; any class flagged by the user as high-complexity
- **Fable**: not used for per-class review agents — reserved for Phase D's round-level fix-planning
  pass (runs once per round, see below), its per-finding fix-planning gate, Phase E's round-cap
  "NOT converged" targeted deep-dive agent (see below), and `xp-pair`'s generative design guidance
  step, all of which need deeper reasoning on a synthesis/planning/deep-dive task rather than a
  per-class scan
- **Sonnet**: all other classes

`CLASSES` is reused verbatim by every round's Workflow call in the Per-Round Loop below, alongside
`$PATTERNS_FILE`, `MERGE_BASE`, and the Intent Brief (`INTENT_BRIEF`) — each passed once via
`args`, not repeated per class (`BASE_BRANCH`/`CURRENT_BRANCH` are Setup-only values, used for the
self-match check and error messages — `buildPrompt()` never receives them). The Phase A/B script's
`buildPrompt()` assembles
each agent's actual prompt from this metadata, embedding the following — identical for every
class, so written once in the script rather than once per class:

1. An instruction to read `$PATTERNS_FILE` (passed as `args.patternFile`) and extract the section
   for `name` (a `### N. <name>` heading) itself — the only pattern-file read this step requires,
   and it happens inside the agent's own context
2. `args.mergeBase` and every enumeration command from Setup Step 4 — the orientation diff, the
   changed-source-files grep, and both doc-file commands (files changed directly in the diff, and
   any README/CHANGELOG adjacent to a changed source file even if untouched itself). A command
   added to Setup Step 4 must be added to `buildPrompt()` too — they're two copies of the same
   list, kept in sync by hand, not derived from one source
3. The `lensKind`-specific file-reading instruction above
4. `args.intentBrief`
5. The **cascade sweep rule** (embedded below, condensed from the fuller prose in this section —
   the meaning is unchanged, only the wording is shorter):

   > When you find a bug, state its specific failure mode in one sentence (e.g., "subprocess
   > returncode used before checking stdout"). Then scan *every other callsite of the same kind*
   > in the entire changed source — every subprocess call, every JSON read, every branch exit —
   > for the same failure mode before reporting. Report all instances together as a cluster.
   > Do NOT hold back and expect later rounds to catch siblings. A missed sibling is a miss.
   >
   > **When the failure mode centers on a specific named symbol** (a method, class, field, or
   > interface — e.g. "every caller of `IsolationBoundary.run()`", "every implementer of
   > `QuiesceHandler`"), use LSP's `findReferences`/`goToImplementation` on that symbol instead of
   > (or in addition to) a text grep. A grep for the symbol's literal text misses a call site
   > reached through a static import, a method reference (`Foo::bar`), or a differently-qualified
   > name, and can false-positive on an unrelated match inside a comment, string, or Javadoc `@link`
   > — LSP resolves the actual symbol and is immune to both failure modes. Grep remains the right
   > tool when the sweep is for a repeated *structural pattern* rather than one named symbol (e.g.
   > "every place that logs at ERROR with a duplicate-conflict keyword"), or for prose/doc-text
   > restatements, where LSP's reference-finding does not apply at all.

6. The `blast_radius` classification rule (embedded below, condensed the same way): classify structurally, never by severity or gut feel —
   `local` = confined to one file/callsite, something the current session could diagnose and fix
   in-context if it ever manifested; `cross_file` = spans multiple files, affects call sites
   outside the diff, or restates a rule defined elsewhere (e.g., a doc restating a code
   constant). Justification must cite structural evidence actually checked — an LSP
   `findReferences` result when the rule centers on a named symbol, a grep for other callers when
   it doesn't, or the other file that restates the rule; a `local` tag with no evidence is invalid,
   and `local` is never a reason to down-rank a real bug.
7. The finding-schema conventions the Phase A/B script relies on: report `file` as `path:line` or
   `path:startLine-endLine` (the synthesis script dedupes by matching this string exactly — an
   inconsistent format silently breaks the dedup); populate `cascade_siblings` with every sibling
   location found via the cascade sweep rule (item 5); return `is_clean: true` with an empty
   `findings` array if the class is fully clear, `false` otherwise.

---

## Per-Round Loop

Repeat up to `--rounds` times. After each round, check the termination condition (Phase E) before
deciding whether to continue. Maintain `PRIOR_FINDINGS` across rounds — empty at round 1,
appended to at the end of each round's Phase C (see below).

**Each round's Phase A/B is a fresh `Workflow` call — never `resumeFromRunId` pointed at any prior
run, including this round's own** (not just "a prior round's run" — a same-round missing-class
retry, below, is exactly as vulnerable and is the case where resuming reads as the intuitive
choice: "continue this incomplete round"). Every input `buildPrompt()` uses (`CLASSES`,
`$PATTERNS_FILE`, `MERGE_BASE`, `INTENT_BRIEF`) is round-invariant by construction — only
`priorFindings` differs round to round, and `buildPrompt()` doesn't use it. That means each
`agent()` call's actual prompt string is identical across rounds, AND identical for the same class
within a round's retry. The `Workflow` tool caches each `agent()` call by its `(prompt, opts)`
pair, so resuming any prior run — a previous round's, or this round's own already-terminated
attempt — would replay that run's stale per-class result (from the now-superseded tree, or from
the exact terminal failure the retry exists to overcome) instead of actually re-diffing the code,
even though the outer `args.priorFindings` value differs.

### Phase A/B — Parallel Review + Synthesize (Workflow)

Run per-class review and synthesis as a single call to the `Workflow` tool (Claude Code's
multi-agent orchestration primitive). `parallel()` is a hard barrier — the script cannot advance
to synthesis until every class has resolved or been retried to a terminal failure, and `schema`
forces structured output instead of relying on an agent to comply with a text instruction. This
replaces spawning per-class review agents directly. `agent`, `parallel`, `phase`, `log`, and
`args` below are pre-bound globals the Workflow tool provides inside the script it executes —
not something this file defines. `agent()` retries a failed call internally before giving up, but `missingClasses` (below) is
broader than "exhausted retries" alone — it also covers a prompt-construction failure (a malformed
`CLASSES` entry, which never reaches `agent()` at all) and a bare-null response slot; each entry
carries a `stage` (`'prompt'` | `'agent'` | `'slot'`) so these are never conflated into one story.

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
const rawArgs = typeof args === 'string' ? JSON.parse(args) : args
const { classes, patternFile, mergeBase, intentBrief } = rawArgs
// A destructuring default (`priorFindings = []`) only applies when the property is `undefined` —
// an explicit JSON `null` (plausible: PRIOR_FINDINGS is only documented as "empty at round 1", not
// typed as `[]`) passes straight through as `null` and bypasses the default entirely.
const priorFindings = Array.isArray(rawArgs.priorFindings) ? rawArgs.priorFindings : []

// Same defensive posture as the `args`-shape comment above, applied to the individual fields:
// each is interpolated directly into every class's prompt (buildPrompt below), so a missing one
// would render literal "undefined" into every agent's diff/read instructions. `classes` is
// checked separately since an empty/absent array doesn't render "undefined" anywhere — it just
// makes `parallel([])` spawn zero agents and the round silently report CONVERGED with nothing
// reviewed. Fail before spawning anything rather than burning a full round on prompts already
// known broken, or reporting a false-clean verdict from a round that never ran.
if (!Array.isArray(classes) || classes.length === 0) {
  throw new Error(`missing/empty required arg "classes": ${JSON.stringify(classes)} — zero agents would spawn and the round would report CONVERGED with nothing reviewed; aborting`)
}
if (!patternFile || !mergeBase || !intentBrief) {
  throw new Error(`missing required arg(s) for this round: patternFile=${patternFile} mergeBase=${mergeBase} intentBrief=${intentBrief} — every class's prompt would be broken; aborting before spawning any agents`)
}

const LENS_INSTRUCTIONS = {
  code: 'Read the full contents of the changed **source** files.',
  doc: 'Read the full contents of the changed **doc** files; read source files only if this lens explicitly requires cross-referencing code.',
  both: 'Read the full contents of **both** changed source and doc files — a rule can be restated across a doc and a code file.',
}

// Builds one class's review prompt at call time, so the pattern-class text itself is read by the
// spawned agent in its own context — never by this script or the orchestrator (see Setup Step 5).
// Every input here is round-invariant — identical text every round (see the resumeFromRunId note
// above); only `priorFindings` differs round to round, and it isn't used here.
function buildPrompt(c) {
  // Two-dot form (no second ref) against the pinned merge-base — includes uncommitted working-tree
  // changes, unlike a three-dot commit range. See Setup Step 3's MERGE_BASE derivation for why.
  const range = mergeBase
  const lens = LENS_INSTRUCTIONS[c.lensKind] || LENS_INSTRUCTIONS.both
  if (!LENS_INSTRUCTIONS[c.lensKind]) {
    log(`class "${c.name}" has unrecognized lensKind "${c.lensKind}" — defaulting to 'both'. Update Setup Step 5's bucket list.`)
  }
  return `Review the current diff against the "${c.name}" pattern class only.

**You are READ-ONLY. Do not use Edit or Write, and do not run any mutating git command (reset,
rebase, commit, stash, checkout --, restore).** If you want to test whether a mutation would be
caught (e.g. "would the test suite catch this regression"), reason about it structurally from the
code you've read — do not actually make the edit. A finding based on an untested mutation
hypothesis is still reportable; state the reasoning in \`description\` instead of demonstrating it.

1. Read ${patternFile} and extract the section for pattern class "${c.name}" (a "### N. ${c.name}" heading) — that section defines what to look for.
2. Run \`git diff ${range}\` once for orientation. \`git diff\`/\`git diff --name-only\` only see
   TRACKED content, so every enumeration below unions in \`git ls-files --others --exclude-standard\`
   (untracked, never-\`git add\`ed files) — a change consisting solely of brand-new files would
   otherwise be invisible. Enumerate changed source files with
   \`{ git diff --name-only ${range}; git ls-files --others --exclude-standard; } | grep -E "\\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$" | sort -u\`,
   changed doc files with
   \`{ git diff --name-only ${range}; git ls-files --others --exclude-standard; } | grep -E "(\\.md|\\.rst|\\.adoc|CHANGELOG|README)" | sort -u\`,
   and any README/CHANGELOG adjacent to a changed source file even if untouched itself with
   \`{ git diff --name-only ${range}; git ls-files --others --exclude-standard; } | grep -E "\\.(java|py|js|ts|go|rb|scala|kt|cs|cpp|c|h|rs|swift)$" | xargs -I{} dirname {} 2>/dev/null | sort -u | xargs -I{} sh -c 'find {} "{}/.." -maxdepth 1 \\( -name "README*" -o -name "CHANGELOG*" \\) 2>/dev/null' | sort -u\`.
3. ${lens}
4. Intent Brief: ${intentBrief}
5. Cascade sweep rule: when you find a bug, state its specific failure mode in one sentence (e.g., "subprocess returncode used before checking stdout"), then scan every other callsite of the same kind in the entire changed source for the same failure mode before reporting. Report all instances together as a cluster. Do NOT hold back and expect later rounds to catch siblings — a missed sibling is a miss. When the failure mode centers on one named symbol (a method/class/field/interface), use LSP findReferences/goToImplementation on it rather than a text grep — a grep misses a call site reached via a static import or method reference and can false-positive on a comment/string/Javadoc @link match; LSP resolves the actual symbol. Grep remains right for a repeated structural pattern (not one named symbol) or prose/doc-text restatements, where LSP does not apply.
6. blast_radius rule: classify structurally, never by severity or gut feel. local = confined to one file/callsite, diagnosable in-context if it ever manifested. cross_file = spans multiple files, affects callsites outside the diff, or restates a rule defined elsewhere. Justification must cite structural evidence actually checked (e.g. an LSP findReferences result for a named-symbol rule, a grep for other callers otherwise) — an unsupported local tag is invalid, and local is never a reason to down-rank a real bug.
7. Report file as path:line or path:startLine-endLine exactly (dedup matches this string exactly). Populate cascade_siblings with every sibling location found via the cascade sweep rule. Return is_clean: true with an empty findings array if fully clear, false otherwise.`
}

phase('Review')
// agent() is documented to resolve null on a terminal failure (exhausted retries) rather than
// reject — but a retry-cap error (e.g. StructuredOutput validation failing 5 times) has been
// observed to throw instead. If the thunk itself rejects, `parallel()`'s own contract ("a thunk
// that throws resolves to null in the result array") replaces this WHOLE element with a bare
// `null` — discarding the `{name, result}` wrapper along with it, so a downstream `r.result` read
// on that slot throws "null is not an object" instead of degrading to a missing-class entry.
// Catch inside the thunk so this slot always returns the `{name, result}` shape, `result: null`
// on any failure — belt-and-suspenders against agent()'s own documented contract not holding.
const responses = await parallel(classes.map(c => async () => {
  // buildPrompt(c) is a separate try from the agent() call below — it can throw independently
  // (a malformed CLASSES entry: non-object c, non-string lensKind, ...), which is an
  // orchestrator-side args defect, not an agent/model contract violation. Naming the failing
  // stage in the log keeps an operator from retrying the class or investigating the model
  // provider when the actual bug is upstream, in Setup Step 5's CLASSES construction. `stage` is
  // carried on the returned object so it reaches missingClasses below, not just the log line —
  // Setup Step 5 (:246-250) instructs hand-building CLASSES entries and deliberately leaving
  // `lensKind` unset for new classes, so a malformed entry is a plausible, expected input.
  let prompt
  try {
    prompt = buildPrompt(c)
  } catch (e) {
    log(`class "${c.name}" failed during prompt-construction: ${e && e.message ? e.message : e} — check Setup Step 5's CLASSES entry for this class, not the model/agent call`)
    return { name: c.name, result: null, stage: 'prompt' }
  }
  let result = null
  try {
    result = await agent(prompt, { label: `review:${c.name}`, phase: 'Review', schema: FINDING_SCHEMA,
      ...(c.model ? { model: c.model } : {}) })
  } catch (e) {
    log(`class "${c.name}" failed during the agent call: ${e && e.message ? e.message : e} instead of resolving null — treating as a terminal failure for this round`)
  }
  return { name: c.name, result, stage: 'agent' }
}))

// Preserve slot identity by index rather than filter-then-map — a bare-null slot (still possible
// in principle if the thunk itself throws before its own try/catch, e.g. a malformed `classes`
// entry) would otherwise contribute no name and silently vanish from this count instead of
// surfacing as a missing class. Each entry is `{name, stage}` — 'prompt' | 'agent' | 'slot' (a
// bare-null response slot, no stage information available) — not a bare string, so every
// downstream consumer (the log below, Phase E's retry carve-out, the coverage-gap note) can
// distinguish "exhausted retries" from "this was never a retry-shaped failure to begin with".
const missingClasses = responses
  .map((r, i) => (r && r.result) ? null : {
    name: (r && r.name) || `<class at index ${i}: ${JSON.stringify(classes[i])}>`,
    stage: (r && r.stage) || 'slot',
  })
  .filter(Boolean)
if (missingClasses.length) {
  log(`${missingClasses.length} class(es) returned no result and are excluded from this round: ${missingClasses.map(m => `${m.name} (${m.stage})`).join(', ')}`)
}

phase('Synthesize')
const SEVERITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
const raw = responses.filter(r => r && r.result).flatMap(r => r.result.findings)

// Shared by every free-text field below so "dedupe against the full accumulated set, not just
// the last value" is implemented once — not re-derived (and re-forgotten) per field.
function mergeStrings(existing, incoming) {
  return existing.split(' | ALSO: ').includes(incoming) ? existing : `${existing} | ALSO: ${incoming}`
}

const merged = new Map()
for (const f of raw) {
  const existing = merged.get(f.file)
  if (!existing) {
    const { pattern_class, ...rest } = f
    merged.set(f.file, { ...rest, pattern_classes: new Set([pattern_class]) })
    continue
  }
  existing.pattern_classes.add(f.pattern_class)
  if (SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[existing.severity]) {
    existing.severity = f.severity
  }
  if (f.blast_radius === 'cross_file') {
    existing.blast_radius_justification = existing.blast_radius === 'cross_file'
      ? mergeStrings(existing.blast_radius_justification, f.blast_radius_justification)
      : f.blast_radius_justification
    existing.blast_radius = 'cross_file'
  }
  existing.description = mergeStrings(existing.description, f.description)
  existing.recommendation = mergeStrings(existing.recommendation, f.recommendation)
  existing.cascade_siblings = [...new Set([...(existing.cascade_siblings || []), ...(f.cascade_siblings || [])])]
}
const findings = [...merged.values()]
  .map(f => ({ ...f, pattern_classes: [...f.pattern_classes] }))
  .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])

// Keyed on `file` alone. A prior attempt keyed on file + pattern_classes (to distinguish a
// fix-introduced defect from a re-flag of the same dismissed bug at the same line) made things
// worse: pattern_classes is which LENSES happened to flag a location in a given round — the most
// non-deterministic value in the pipeline. A location flagged by class A alone in round N and by
// classes A+B in round N+1 (ordinary reviewer variance, not a code change) then produces two
// different keys, so the unfixed, already-dismissed bug reads as fresh cross-file yield every
// time the lens set happens to shift. Keying on `file` alone under-suppresses the rarer case (a
// fix lands a genuinely new bug on the same reported line) but over-suppresses far less often —
// see Phase C's "Finalize the round's cross-file yield" for how a re-flagged, still-dismissed
// finding is kept out of the finalized count regardless.
function crossFileKey(f) {
  return f.file
}

// Only a PRIOR cross_file sighting excludes a location from this round's yield — a location
// previously seen as local must still count as fresh yield if it now escalates to cross_file.
const priorCrossFileKeys = new Set(priorFindings.filter(f => f.blast_radius === 'cross_file').map(crossFileKey))
const provisionalYield = findings.filter(f => f.blast_radius === 'cross_file' && !priorCrossFileKeys.has(crossFileKey(f))).length

return { findings, provisionalYield, missingClasses }
```

Invoke with `Workflow({ script: <above>, args: { classes: CLASSES, priorFindings: PRIOR_FINDINGS,
patternFile: PATTERNS_FILE, mergeBase: MERGE_BASE, intentBrief: INTENT_BRIEF } })`.
Dedup keys on the `file` string (already `path:line` or `path:startLine-endLine`, as agents
report it). On a collision: `severity` escalates to whichever is worse; `blast_radius` escalates
to `cross_file` if either finding says so (wider radius wins); `description` and `recommendation`
**always list distinct values side by side (`| ALSO:`) rather than guessing which is "more
specific"** via the shared `mergeStrings` helper, so a fix for one can't leave the other behind.
`blast_radius_justification` uses the same helper, but only once *both* sides already agree the
location is `cross_file` — that reasoning is worth preserving in full since it can gate
convergence. A `local`+`local` collision keeps whichever justification was recorded first rather
than merging both: a `local` verdict never blocks anything, so its reasoning isn't
decision-critical the way a `cross_file` verdict's is. `pattern_class` is replaced by a deduped
`pattern_classes` array (every class that flagged this location; downstream consumers, including
the Summary Output's "By Pattern Class" table, read the plural field). This is all deterministic
JS, not an LLM judgment call — leave the actual disposition to Phase C.

**Yield only excludes a *prior cross-file* sighting at the same location.** A location first
seen as `local` (and dismissed) that a later round's different lens re-flags as `cross_file` is
new information the sweep exists to surface — it must count as fresh yield, not get silently
absorbed because the file string was technically "seen before."

**`missingClasses` is not "that class was clean."** A class whose agent never returned a result —
whether that's exhausted retries after a terminal API error (`stage: 'agent'`), a malformed
`CLASSES` entry that never reached the agent call (`stage: 'prompt'`), or a bare-null response slot
(`stage: 'slot'`) — means that lens genuinely didn't run this round. Carry `missingClasses`
forward into Phase C and Phase E — it blocks a CONVERGED verdict (see Phase E).

### Phase C — Review-Pause (human decision)

**Snapshot `ROUND_START_PRIOR_FINDINGS = PRIOR_FINDINGS`** before anything below appends to it.
Every use of `priorFindings` for *this round's* yield math — the finalize-yield recompute below,
and Phase E's missing-class retry — reads this snapshot, never the live `PRIOR_FINDINGS` variable,
which this same phase mutates by appending. Using the live variable would make a retry's yield
recompute run against a `priorCrossFileKeys` set that already contains this round's own findings
(appended below, before Phase E ever runs), silently suppressing any retry-recovered finding whose
location happens to collide with one this round already flagged.

Present the synthesized findings **and any `missingClasses`** to the calling session. `missingClasses`
is surfaced here for visibility only while rounds remain below `--rounds` — do not solicit a
disposition for it yet; Phase E decides when a missing class actually requires one. For each
finding, the user classifies it:

| Disposition | Action |
|-------------|--------|
| **Fix** | Proceed to Phase D |
| **Contradicts design** | Override — no fix; do not flag as "missed" |
| **Accepted risk** | Record as a known limitation; include in the Summary Output's Known Limitations section and PR description. Do NOT silently drop — the absence of a finding in the summary is a claim that it was addressed |
| **False positive** | Skip; note the reason in the round summary |

**Finalize the round's cross-file yield** after disposition by recomputing it directly from the
same population Phase A/B's provisional count used — `cross_file` findings whose `crossFileKey`
is not in `ROUND_START_PRIOR_FINDINGS`'s cross-file keys (the snapshot above, NOT the live,
by-then-already-appended `PRIOR_FINDINGS`) — filtered to only those dispositioned **Fix** or **Accepted risk**
(an accepted-risk finding is a real, confirmed issue the human chose not to fix yet). Do NOT
compute this by subtracting False-positive/Contradicts-design counts from the provisional number:
a `cross_file` finding re-flagging a location already in `priorCrossFileKeys` was never in the
provisional count to begin with, so subtracting its disposition from that count can drive the
result negative — a value neither Phase E's CONVERGED check (`== 0`) nor its NOT-converged check
(`> 0`) handles. This finalized number is what Phase E reads.

**Append to `PRIOR_FINDINGS`** before the next round: **every** finding synthesized this round,
regardless of disposition, as `{file, blast_radius}` (`crossFileKey` only reads `file`;
`pattern_classes` doesn't need to be carried forward). This is deliberately not filtered to
Fix/Accepted-risk — `PRIOR_FINDINGS` tracks what has
already been *seen* at a location, not whether it's a *confirmed bug* (that distinction is what
finalized yield, above, already handles). If a False-positive- or Contradicts-design-dismissed
finding were dropped from this list, the same non-deterministic reviewer re-flagging that exact
spot next round would count as fresh cross-file yield — re-litigating something a human already
resolved.

### Phase D — Apply Fixes

**Round-level fix-planning pass (run once per round, before any per-finding gate or fix agent)**:
Per-finding planning (below) only sees one finding's own `cascade_siblings` — the sites its OWN
Phase A/B reviewer happened to catch while reviewing that one pattern class. It cannot see that a
DIFFERENT finding (found by a different class) touches the same underlying mechanism, so a fix for
one can land cleanly while the other's sibling instance of the same mechanism goes untouched. This
is an observed, recurring failure mode from this batch's own dogfooding, not a hypothetical: a
persistence fix for two variables missed a third added in the same commit; a base-branch rewrite
in one file dropped an override-argument branch structure a sibling file's parallel code already
had. Both are cross-finding interactions a per-finding planner never sees, because each finding is
planned in isolation from what the *other* approved findings in the same round are touching.

Spawn one top-level `Agent` call (not `Workflow`/`agent()` — same reasoning as the per-finding gate
below) with `model: 'fable'`, run once per round regardless of how many findings are approved,
receiving:
- **Every** finding dispositioned **Fix** this round (not just complex/cascading ones) — the full
  batch, each with its `file`, `recommendation`, and `cascade_siblings`
- The Intent Brief
- `$PATTERNS_FILE`'s path (read its own relevant sections itself, same as the per-finding gate —
  never embedded directly)
- An instruction: for each finding, name the general mechanism it touches (e.g. "base-branch
  resolution", "diff-range computation", "outcome persistence across bash blocks", "the changed-
  files enumeration pattern") in one phrase, then search for every other location implementing or
  depending on that same mechanism. This is deliberately broader than any single finding's own
  `cascade_siblings`: it is looking for siblings across the WHOLE round's approved-fix set, not
  within one finding's own file. When the mechanism centers on one named symbol (a method/class/
  field/interface), use LSP `findReferences`/`goToImplementation` on it rather than a text grep —
  grep misses a call site reached via a static import or method reference and can false-positive
  on a comment/string/Javadoc `@link` match, while LSP resolves the actual symbol regardless of how
  it's referenced. Grep remains right for a repeated structural pattern or prose/doc-text
  restatement, where LSP does not apply. Either way, **do not scope the search to the current diff
  alone** — a sibling restatement of a corrected value/phrase, or another caller of a changed
  method, is exactly as likely to live in a file this round's diff never touches (a prior round's
  own doc-fallout sweep can pass cleanly yet still miss a stale sibling outside its diff; see Class
  11's cascade-sweep provenance note in `copilot-review-patterns.md`) — search the whole module/
  repository, not just the files already touched by this round's fixes
- The same read-only **git guardrails** as the per-finding gate below

It returns, per finding, an expanded site list (a superset of that finding's own
`cascade_siblings`) the fix must cover, plus a round-level note of any mechanism shared by 2+
findings that Phase C didn't already link together (so a human disposing findings one at a time
isn't the only line of defense against two findings turning out to be the same underlying issue
viewed through different pattern classes).

**If it fails, times out, or returns nothing usable** (three distinct outcomes, not one), proceed
with Phase D unchanged (per-finding gate and fix agents use only what Phase A/B/C already
produced), and record in the round summary that the round-level plan was skipped — name which of
the three happened, since "returned nothing usable" and "the call itself failed" call for
different operator responses (retry vs. treat as a known tooling gap this round).

**Fix planning gate (complex/cascading findings only)**: before spawning the fix-implementation
agent, check the approved finding against fields it already carries from Phase A/B, **plus the
round-level pass above**: non-empty `cascade_siblings`, OR `blast_radius == 'cross_file'`, OR
`severity` is `CRITICAL`/`HIGH`, OR the round-level pass identified expanded sites for this finding
beyond its own `cascade_siblings`. If any is true, spawn a top-level `Agent` call — not a
`Workflow`/`agent()` stage, since Phase D runs in the orchestrating session, outside the Workflow
script block above — with `model: 'fable'` for extra reasoning depth on a fix that spans multiple
sites. It receives:
- The finding + its recommendation + `cascade_siblings` + **the round-level pass's expanded site
  list for this finding, when produced** + the Intent Brief
- `$PATTERNS_FILE`'s path and the finding's `pattern_classes` array (plural — see Phase A/B's
  synthesis step), with an instruction to read its own relevant sections itself. Never embed the
  pattern-class text directly in this prompt — from the orchestrating session, that would require
  `Read`-ing it into the orchestrator's own context first, exactly the cost Setup Step 5 exists to
  avoid, and this gate can fire once per qualifying finding in a round, multiplying the cost
- The same **git guardrails** as the fix agent below, minus the PERMITTED Edit/Write clause:
  read-only — no Edit/Write at all; Bash only for reading files or grep/find

It returns a structured fix plan (ordered steps, files touched, how each `cascade_sibling` **and**
each round-level expanded site is covered). **If it fails, times out, or returns nothing usable**
(three distinct outcomes, not one), fall through to the fix agent with the finding,
`cascade_siblings`, and the round-level expanded sites alone, and record which of the three
happened in the Summary Output's **Fix Provenance Notes** — not Known Limitations, since the
finding still gets fixed; this is a confidence/provenance note, not an unaddressed item.

This is a native planning step, not an `xp-pair` invocation — `xp-pair`'s own Step 5 commits and
shuts down its team as part of finishing a session, which would violate the git guardrails below
(no `git commit` inside a fix agent) and would drag a heavy, interactive team/driver session into
what's meant to stay an automated per-round fix-apply step. Findings the round-level pass didn't
expand and that don't otherwise meet the gate (simple, local, no siblings) skip per-finding
planning entirely and go straight to the fix agent below, same as before — this keeps the common
case cheap; only the one round-level pass runs unconditionally.

For each approved finding, apply the fix. The fix agent receives:
- The approved finding + its recommendation
- The finding's `cascade_siblings` **and the round-level pass's expanded site list for this
  finding, when produced** — the fix is not complete until it's applied at the primary `file`
  location **and** every sibling/expanded-site location; a fix that only patches the reported
  instance leaves the cascade sweep's whole purpose unmet
- **The fix plan from the gate above, when the finding met it** — the fix agent follows this plan
  rather than re-deriving the multi-site approach from scratch
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
before proceeding — do not continue to the next round with a red test suite. This is a **terminal
state**, not a soft warning: see Phase E's `TEST_FAILURES` outcome below, which this rule refers to
by name — evaluate it before CONVERGED or the round-limit outcomes, and do not evaluate either of
those on a red suite.

### Phase E — Check Termination

**Check the test suite first, before anything else below.** If Phase D's test run for this round
is red, terminate as **TEST_FAILURES** immediately — do not evaluate the CONVERGED conditions, do
not check whether rounds remain, and do not continue to the next round. A round that fixed
findings but broke the suite is not convergence and is not safe to build on top of; report the
failures and stop the loop here regardless of what cross-file yield or `missingClasses` say.

The next round's Phase A/B Workflow call will self-diff the now-modified working tree when it
starts — `MERGE_BASE` is pinned once in Setup and diffed with the two-dot form, so this is true
whether the prior round's Phase D fixes were committed (this session's own practice, one commit
per round) or left uncommitted (the documented default) — the orchestrator does not need to
re-read or re-pass file contents between rounds.

Termination is driven by the round's **finalized cross-file yield** (provisional in Phase A/B,
finalized in Phase C), `missingClasses`, and the test-suite check above — not by `is_clean` flags.
Open `local` findings never force another round — report them in the Summary Output for human
disposition and move on.

**Terminate as CONVERGED when:**
- The test suite check above passed (this round's suite is green) — a red suite terminates as
  TEST_FAILURES above and never reaches this check
- Cross-file yield == 0 — no new `cross_file` finding this round, even if `local` findings remain open
- AND `missingClasses` is empty — every class returned a definitive result this round

**If rounds remain below `--rounds`** and the round didn't converge (either yield > 0, or yield
== 0 but `missingClasses` is non-empty), continue to the next round — the next round's Workflow
call reuses the full `CLASSES` list, so a class that failed this round gets a natural retry
alongside everything else. Don't force a human decision about a missing class while rounds are
still available; that's premature friction the round loop already resolves on its own.

**Only once the round limit (`--rounds`) is reached without converging** do the remaining
outcomes apply. Evaluate both independently — they are not mutually exclusive. A coverage gap
(some class never reviewed) and a confirmed finding cluster (real cross-file bugs the classes
that *did* report already found) are different problems; resolving one does not make the other
disappear, and both can appear together in the same Summary Output (e.g. "INCOMPLETE + NOT
converged").

1. **If `missingClasses` is non-empty**, a class nobody ever reviewed is not evidence it's
   clean — it's an unresolved gap, distinct from "found real issues" (below). Signal
   **"INCOMPLETE — N class(es) unreviewed: `<names>`"** and present the human a choice:
   - Retry only the missing classes (a **fresh** `Workflow` call — never `resumeFromRunId`, per the
     Per-Round Loop note above; this retry is exactly as vulnerable to replaying a stale cached
     result as a cross-round resume would be — re-invoke with `classes` filtered to just those,
     and the same `patternFile`, `mergeBase`, and `intentBrief` values used this round —
     `buildPrompt()` interpolates all three directly into every prompt; omitting any throws before
     any agent spawns, per the missing-arg guard right after the `args` destructuring). **Carve out
     `stage: 'prompt'` entries first**: a prompt-construction failure means the `CLASSES` entry
     itself is malformed (see Setup Step 5) — retrying without fixing it burns a retry on a call
     that will fail identically again, since the bug never reached the agent/model at all. Fix the
     `CLASSES` entry, then retry that class; only `stage: 'agent'`/`'slot'` entries are worth a
     bare retry as-is. Also pass
     `ROUND_START_PRIOR_FINDINGS` (Phase C's snapshot) as `priorFindings` — **not** the live
     `PRIOR_FINDINGS`, which by now already contains this round's own findings (Phase C appended to
     it before Phase E ever runs): passing the live variable would make the retry's yield recompute
     silently suppress any retry-recovered finding whose location collides with one this round
     already flagged. Omitting `priorFindings` entirely is a *different* mistake — it doesn't break
     any prompt (the outer script's yield/dedup logic reads it, not `buildPrompt()`), but it
     silently resets every retry-recovered finding's dedup history to empty, making them all
     register as fresh cross-file yield regardless of what earlier rounds already saw. **This
     retry does not count as an additional round** for the ">1 round has actually run" test
     below — it completes this round's incomplete data rather than starting a fresh sweep.

     **Merging needs an adapted variant of the dedup logic, not the literal script.** The retry's
     own Phase A/B call already ran its own Synthesize step, so its `findings` are POST-merge
     objects — `pattern_classes` (plural array), no `pattern_class` field — and so is this round's
     existing `findings` array. The literal merge loop at the top of the Phase A/B script
     destructures a singular `pattern_class` off each raw per-agent finding and seeds a fresh
     `Set([pattern_class])`; running that unmodified against two already-synthesized arrays reads
     `pattern_class` as `undefined` on every item, producing `pattern_classes: [undefined]` instead
     of a real union. Adapt it: for a colliding `file`, union the two `pattern_classes` ARRAYS
     directly (`new Set([...existing.pattern_classes, ...incoming.pattern_classes])`) rather than
     seeding from a single string, then apply the same severity/blast_radius escalation and
     `mergeStrings` description/recommendation rules the literal script uses. For a non-colliding
     `file`, just append the retry's finding as-is (it's already shaped correctly). Send the
     merged result back through **Phase C** for disposition like any other finding, then
     recompute finalized yield and update this round's Per-Round Breakdown row in place (don't
     add a new row) — a retry-recovered finding is not applied to code until an approved **Fix**
     disposition goes through Phase D like any other, and append it to `PRIOR_FINDINGS` the same
     way Phase C does. If the retry closes the gap cleanly (`missingClasses` now empty, yield
     still 0), **re-run the CONVERGED check** — a fully successful retry can promote the round's
     verdict to CONVERGED rather than leaving it stuck on INCOMPLETE. If that retry still comes
     back missing, retry at most once more; if that second retry also comes back missing, force
     **Accept** or **Abandon** — don't loop indefinitely on a class that keeps failing
   - Accept the gap as a known limitation. A missing class produced no finding, so don't force
     it into the finding shape (there's no real `severity` or `blast_radius` to report) —
     record a distinct coverage-gap entry instead: `{type: 'coverage_gap', class: '<class
     name>', stage: '<prompt|agent|slot>', note: '<N> retr{y,ies} attempted, still missing' or
     'no retry attempted — accepted on first INCOMPLETE signal' (N=0)}`. **Do NOT hard-code "after
     retries" in the note** — item 1's own three choices (Retry/Accept/Abandon) are all available
     the very first time a class goes missing, so a human can Accept or Abandon with zero retries
     ever having run; a static "after retries" claim would be false in that case and, per the
     Known Limitations rule below ("all MUST appear verbatim in the PR description"), would land,
     unedited, in a real PR description as a false claim about how the gap was investigated. List
     it in Known Limitations alongside (but visually distinct from) real accepted-risk findings;
     it has no `pattern_class`/`blast_radius` to bucket under, so it does not populate the By
     Pattern Class or By Blast Radius tables — those describe findings, not coverage gaps.
   - **Abandon the round**: by the time Phase E is reached, Phase D has already applied any
     approved fixes from this round's Phase C — those are independent, confirmed fixes and stay
     in the tree; "abandon" does not undo them. It means: don't retry the missing class, record
     it as a coverage-gap entry (same shape as Accept, above), skip item 2 below entirely (the
     human has already asked to stop; don't also compute or show a deep-dive escalation), and
     don't start another round — hand the review back to the user as unresolved rather than
     looping further.
2. **If cross-file yield > 0** (check this regardless of whether `missingClasses` is also
   non-empty — do not skip it just because item 1 already fired, *unless* item 1's outcome was
   Abandon, which skips this item entirely — see above), see the NOT-converged / single-round-only
   outcomes below. Both can fire together with INCOMPLETE's Retry or Accept outcomes; see the
   Summary Output's combined badges.

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
  the theme to the user for a judgment call. If the user approves spawning it, use a top-level
  `Agent` call (not `Workflow`/`agent()` — same reasoning as Phase D above, since this runs once in
  the orchestrating session rather than as a per-class scan) with `model: 'fable'`: the generic
  per-class sweep has already run multiple rounds at Sonnet/Opus without converging on this theme —
  exactly the "cheaper models already tried, failure is expensive" case Fable's edge is reserved
  for elsewhere in this skill (see Model Selection above), not a blanket upgrade for every deep-dive
- Possible underlying causes, mentioned only after the escalation: the PR may be too large
  (consider splitting it), a new failure mode has appeared that doesn't fit any existing
  class — draft it per the Pattern-File Update Hook below — or the recurring findings all trace
  back to a single fragile detection/heuristic **mechanism in the code under review** (e.g., a
  regex-based scanner accumulating ad-hoc extensions round after round for each new input shape
  it didn't anticipate), rather than a gap in the review's own pattern-class coverage. In that
  last case, the deep-dive question is architectural, not "which callsite did we miss" — whether
  the code should adopt a more robust mechanism (a proper parser/AST, an existing tool already in
  the repo) instead of only ever extending the current one further. This mirrors
  `/address-pr-issues`' "Mechanism-Level Diminishing Returns" signal, viewed here from the
  round-cap escalation side instead of the reactive-round side.

**If cross-file yield > 0 at the round limit but only one round ever ran** (e.g., a single-round
caller like `/address-pr-issues`'s `--rounds 1` invocation), there is no multi-round trend to
act on — a single round finding and fixing real cross-file issues is normal, not a failure
signal. Report **"Found and fixed N confirmed cross-file findings this round; convergence
unconfirmed — a single round cannot show yield trending to zero"** instead of the deep-dive
escalation. If `missingClasses` was also non-empty this same round, report both — see the
Summary Output's combined "INCOMPLETE + Single round only" badge.

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
**Diff range**: <MERGE_BASE> (<CHANGED_FILE_COUNT> files changed, working-tree-inclusive) — both
printed by Setup Step 3; a CONVERGED verdict is only meaningful alongside the scope it was computed over
**Pattern classes swept**: <list from PATTERN_CLASSES>
**Rounds completed**: <N> / <max>

### Per-Round Breakdown
| Round | Found | Fixed | Known Limitations | False Positives | Cross-File Yield | Missing Classes |
|-------|-------|-------|-------------------|-----------------|------------------|------------------|
| 1 (example) | 3 | 2 | 0 | 1 | 2 | |
| 2 (example) | 1 | 1 | 0 | 0 | 0 | Test Integrity |
<Missing Classes cell: comma-separated unreviewed class names for that round, blank if none —
not a count, unlike its neighbor columns. A missing-class retry (Phase E) folds into the round
that surfaced it — update that row in place, don't add a new one, since the retry isn't itself
a round. Found = Fixed + Known Limitations + False Positives + Contradicts Design (add a column
for the last if any findings get that disposition) — the row's arithmetic should reconcile the
same way By Blast Radius's does, below.>

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
<List of findings classified as "accepted risk", plus any `coverage_gap` entries from Phase E
(visually distinct from the accepted-risk findings) — both MUST appear in the PR description.
Do NOT include planning-skipped findings here — see below; a planning-skipped finding still went
to the fix agent and was normally FIXED, so it is not something left unaddressed.>

### Fix Provenance Notes (round summary only — not a PR-description limitation)
<For each finding where the round-level pass or the per-finding fix-planning gate failed, timed
out, or returned nothing usable, and the finding fell through to the fix agent unplanned: "fix
applied without a planning pass — verify multi-site coverage" (note each as "planning skipped:
<which stage> <failed | timed out | returned nothing usable>"). This describes HOW the fix was
derived, for the human disposing this round, not whether the finding was addressed — it is
confidence/provenance information, distinct from Known Limitations above.>

### Outcome
❌ TEST_FAILURES — this round's test suite is red after fix application; do not push, do not continue to the next round, and do not evaluate CONVERGED/round-limit outcomes below until the suite is green again (see Phase E — checked FIRST, before every other outcome)
✅ CONVERGED — cross-file yield 0 this round (one sample, not a proof); residual risk: open local findings and accepted-risk items above
⚠️  NOT converged — cross-file yield N at round limit after M>1 rounds; escalate to targeted deep-dive on <theme> (see Phase E)
🔵 Single round only — found & fixed N confirmed cross-file findings; convergence unconfirmed (see Phase E)
🟡 INCOMPLETE — N class(es) unreviewed: <names>; retry, accept as known limitation, or abandon (see Phase E)
🟡+⚠️ INCOMPLETE + NOT converged — both a coverage gap and a confirmed finding cluster; resolve the missing class(es) AND still escalate to targeted deep-dive on <theme> (see Phase E)
🟡+🔵 INCOMPLETE + Single round only — a coverage gap and confirmed cross-file findings from the one round that ran; resolve the missing class(es) and treat convergence as unconfirmed (see Phase E)
🟠 ABANDONED — round stopped at the human's request; N class(es) never reviewed: <names>; no further rounds; M approved fix(es) from this round remain applied in the working tree, committed or not per this session's practice — review `git diff`/`git log` before discarding anything (see Phase E)
```

---

## Notes

- **Language-agnostic**: The source file glob covers all common languages. The pattern-class
  heuristics are implementation-language-independent; they describe code logic patterns.
- **Model cost**: Opus agents for the two highest-ROI classes (State Machine, Operator
  Observability) are deliberate. Sonnet handles the rest. Budget one agent per pattern class (the
  count comes from `$PATTERNS_FILE`, so it grows as classes are added), plus up to one Fable
  fix-planning agent per qualifying finding in Phase D.
- **Cascade sweep is mandatory on first find**: The sweep rule is not optional — it prevents
  the "sibling miss" failure mode where a bug class is fixed in the reported instance but its
  identical siblings survive, whether in the same diff or (per Setup Step 5's/Phase D's LSP
  guidance) outside it. Text grep is not the only tool for this: when the sweep is for a named
  code symbol, LSP `findReferences` finds every real call site regardless of import style and
  doesn't false-positive on a comment/string match the way grep can.
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
