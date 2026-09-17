---
name: reasoning-audit
description: "Periodically re-examine an existing CLAUDE.md, skill, or script for reasoning that has gone stale — thresholds with no evidence, capability claims overtaken by reality, citations that no longer resolve, guards that stopped guarding, and scripts being bypassed. Use when asked to audit, re-check, refresh, or tighten up instructions/skills/scripts, when asked whether guidance is still current, or on a periodic maintenance pass. Read-only and diagnostic: it reports and recommends, and never edits the target."
argument-hint: '[target-path | plugin-name | --fleet]'
---

# Reasoning Audit

Re-examines governing artifacts — `CLAUDE.md` files, `SKILL.md` files, and the scripts they ship —
for **decisions that were correct when written and have quietly stopped being correct.** Not bugs
in a diff: drift in encoded reasoning, with no triggering change to surface it.

**This skill never edits the target.** It produces findings and escalation recommendations. Fixes
happen afterwards, by a human decision, through the normal skills for that (see Escalation).

## Why this exists, and what it is not

Per-change review (`/satori:pre-pr-audit`, `/satori:adversarial-review`) catches defects introduced
by a diff. Nothing catches a design decision going stale on its own. Founding example: pre-pr-audit
shipped a JSON eval file that sat untouched for two months, covering 4 of its checker's 11 methods
while the checker grew — and it turned out to be in a format **no runner in this environment
reads**, so it was unrunnable rather than merely stale. No diff would have surfaced either fact.
(It has since been converted to a hand-runnable, dated suite under pre-pr-audit's own evals
directory.)

Two adjacent skills already cover different axes, and this one defers to both rather than
competing:

| Skill | Its axis | Not this skill's job |
|---|---|---|
| `claude-md-improver` | Is a *project* CLAUDE.md complete as codebase context (commands, architecture, conciseness)? | Completeness scoring |
| `skill-creator` | Does a skill *behave and trigger* correctly, measured by running it? | Behavioral measurement |

This skill's axis is **staleness of encoded reasoning**, which neither covers.

---

## Step 0 — Classify the target (applicability gate)

Lens selection depends entirely on what kind of artifact this is, and getting it wrong produces
confident complaints about correct work. Classify from **evidence in the file**, never from its
path.

Path is actively misleading here. `~/github/satoris-claude-config/CLAUDE.md` sits at a repo root
and looks like a project file; it *is* the user's global `~/.claude/CLAUDE.md` via symlink, and
holds standards/philosophy rather than codebase context. Judging it by the project rubric scores
it poorly for missing build commands and architecture sections it correctly should not have.

| Kind | Positive evidence |
|---|---|
| **project-context CLAUDE.md** | Documents build/test/deploy commands, directory structure, entry points, project-specific conventions for *one* codebase |
| **standards CLAUDE.md** | Documents principles, process mandates, tool/model policy, review checklists; applies across projects; often a symlink target (check with `readlink -f`) |
| **skill** | Has `SKILL.md` with `name`/`description` frontmatter |
| **eval-suite** | Markdown under an `evals/` directory carrying per-case validation dates or a results table |
| **auto-memory** | A `.md` whose frontmatter declares `metadata.type` as one of `user`/`feedback`/`project`/`reference`; a directory holding at least one such file |
| **script** | Executable under a `scripts/` dir, or referenced as one from a SKILL.md |

The `eval-suite` kind was added 2026-08-29 after an eval of this skill surfaced that **the artifact
family which motivated it was the one kind it could not classify** — lens 5 named the
`Verified: <date> - PASS` convention while Step 0 refused any file that used it. A stale eval suite
is the founding example; it should not require a judgment workaround to audit.

The `auto-memory` kind was added 2026-09-16 for the same reason, one artifact family later.
Claude Code auto-memory (`~/.claude/projects/<launch-path>/memory/`) could not be classified at
all, so a 128-file fleet-wide memory audit was blocked behind the applicability gate — the gate
refusing exactly the corpus that most needed reading. Two real shapes qualify: the modern
`metadata.type`, and an older top-level `type:` which must also carry `name` and `description`,
since a bare `type:` is an ordinary key in static-site generators.

**Two different questions, two different rules — do not collapse them.** Deciding the *kind* is
evidence-based: a directory qualifies because a file inside it carries memory frontmatter.
Identifying `MEMORY.md`'s *role inside* an already-classified corpus is name-based, because that
filename is the harness's own contract — it is the file the harness loads. So a frontmatter-less
file classifies only when it is named `MEMORY.md` **and** a sibling supplies the evidence; a stray
note dropped beside the memories never claimed the contract and is not audited against it.

**If classification is undetermined, skip that target and say so** — report it as
`unclassified`, name what evidence was missing, and move on. This is an applicability gate: a rule
enforced where it may not apply produces false findings, which cost more trust than a skipped
target costs coverage. Do not guess a kind in order to have something to report.

---

## The lenses

Each lens states what it looks for and which target kinds it applies to. `M` marks the ones the
bundled checker decides mechanically; `J` marks the ones needing judgment on top of the checker's
evidence.

### 1. Unsupported thresholds and heuristics — `J`
*Applies to: all kinds.*

A hardcoded number, cutoff, or heuristic with no cited evidence and no last-validated date. The
number may still be right; the point is that nothing records *why* it was that value or when
anyone last checked. Examples in scope: round caps, "3+ occurrences" triggers, severity cutoffs,
size limits, retry counts.

Report the number, its location, and what evidence is absent — not a proposed new value. Choosing
a replacement is a separate decision requiring data this pass does not gather.

### 2. Capability claims overtaken by reality — `J`
*Applies to: all kinds.*

Claims about what a model, tool, or API can do, how it is invoked, or which option is best. These
decay in weeks. Two real instances, both found 2026-08-29 in this repo's own CLAUDE.md: a worked
LSP example using a call shape the actual `LSP` tool does not accept (`method=`/`symbol=` versus
the real `operation`/`filePath`/`line`/`character`), and a model-routing heuristic ("Fable for
code") that current benchmarks contradict.

Verify against a live source — the tool's own schema, `--help`, a web search — and cite what was
checked. An unverified suspicion is reportable as such; state it as unverified.

### 3. Citations that no longer resolve — `M`
*Applies to: all kinds — for auto-memory, the `[[wikilink]]` form only.*

For auto-memory the file-path half is **out of scope**: memory cites paths in other repositories by
nature, so the cross-repo limitation below would become the dominant output — the
40-findings-of-correct-work failure this skill's own tuning notes record. The wikilink half is
covered under `memory-contract`, and a dangling `[[link]]` is reported as information, never a
finding: the documented contract says it marks something worth writing later.

A reference to another file, section, heading, or field that either does not exist, or exists and
does not say what it is cited as saying. The second form is the dangerous one: the link resolves,
so nothing looks broken.

Regression fixture (verified 2026-08-29, in Anthropic's own `skill-creator` plugin): that skill's
own SKILL.md cites its schemas reference document for an `assertions` field; the file it points to
documents that field under a different name and never mentions `assertions` at all. A real file,
cited for something it does not contain. Any implementation of this lens should catch that case —
`scripts/test_audit_checks.py` carries it as a test.

### 4. Guards that stopped guarding — `J`
*Applies to: skills, scripts.*

A mechanism built as a safety net — an eval suite, a hook, a validation step, a test — that has
drifted from what it is supposed to protect, or that cannot fail. Signals: it covers a fraction of
the surface it names; nothing executes it on any cadence; it is in a format no available runner
reads; its assertions are empty; it has never reported a problem.

The sharpest question, from the checker discipline: **when did this last report bad news?** If the
answer is "never," it has not demonstrated it can.

### 5. Expiring self-dated claims — `M`
*Applies to: all kinds.*

Text carrying its own validation date or re-check window, where that window has passed. Recognized
phrasings: a bare "Verified"/"Last Updated"/"Last Tested" plus an ISO date; a results-table row with
a date cell; a dated section header like `## Key Improvement (2026-04-17)`; and — added
2026-08-29 — two shapes the first version missed entirely:

- **A results row with no date at all** (`| case | — | Pending |`). This is *worse* than stale: the
  case has never run. The em-dash is the `cc-plugins` convention, so every un-run eval README in the
  org previously read as clean. Reported once per file with a count.
- **Undated `(NEW)` markers**, reported once per file past a couple of them. A marker with no date
  cannot expire, so a thicket of them stops distinguishing new content from settled content — one
  skill carried 19, the oldest 4.5 months old, labelling its central mechanism.

A claim past its window is not automatically wrong; it is unverified. Report it as due for
re-check, and let lens 2 handle actually re-verifying it. Only the **newest** date on a line
governs: "Verified X, re-verified Y" is a maintained claim, not a stale one.

**Tune the window to the content.** The checker's 90-day default is three times looser than this
repo's own standard for model claims ("age in weeks, not months"). Pass `--max-age-days 30` — or
tighter — when auditing model/tool capability content, or lens 5 will report clean on a section its
own file says decays in weeks. **Use `--max-age-days 30` for auto-memory**, which is dense with
exactly that content: tool paths, model routing, and CLI behaviour that decays in weeks.

The date keywords were widened 2026-09-16 (`measured`, `confirmed`, `observed`, `re-checked`,
`rechecked`, `re-validated`, `as of`) because memory dates its claims overwhelmingly in those words
and this lens — the headline lens for that kind — was near-blind on it. The change affects every
kind; measured on this repo, it removed no findings from any other artifact and added none once
illustrative content was excluded.

### 6. Scripts that exist but are bypassed — `M` (static) + `J` (behavioral)
*Applies to: skills, scripts.*

A script shipped under `scripts/` that no `SKILL.md` in its plugin references — so nothing will
ever invoke it — or a SKILL.md that spells out by hand a procedure one of its own scripts already
implements.

**Reference-following goes one level deep, through wrappers.** A `.sh` that `exec`s a `.py` is the
common shape, and greping SKILL.md only for the `.py`'s own name reported a live script as orphaned
(confirmed false positive, 2026-08-29 — the checker's first real finding turned out to be wrong).
Indirection stops at one level and the wrapper must itself be directly referenced, so two
mutually-referencing orphans cannot vouch for each other.

**Why this matters more than it looks**: a script is the durable encoding of reasoning already
done. Edge cases found over prior review rounds, ordering constraints, guard conditions, dedup
rules all live inside it. Work re-derived inline re-litigates every one of those invisibly, and
usually gets a subset right — which is why the script exists. The static half ("is it referenced
at all") is a cheap grep. The behavioral half ("is the agent actually running it when it should")
needs transcript evidence and is out of scope for a static pass; recommend `skill-creator`'s
analyzer for that.

### 7. Structure conventions — `M`
*Applies to: skills; realized for auto-memory as the `memory-contract` lens.*

Checked against the conventions in `references/skill-conventions.md`, which records where each
limit came from and when it was verified. Frontmatter validity (including strict YAML parse),
`SKILL.md` length, reference-file table-of-contents thresholds, and the
`scripts/`/`references/`/`assets/` directory contract.

Treat that reference file's own limits as subject to lens 1 — they are copied numbers, and one
source we copied from was itself stale (see the file's provenance notes).

### 7a. `memory-contract` — lens 7 for auto-memory — `M`
*Applies to: auto-memory only.*

Memory has its own contract, and the skill conventions do not transfer: real memory frontmatter
carries extra `metadata` keys the harness writes (`node_type`, `originSessionId`, `modified`), and
descriptions containing `<`/`>` are fine where a skill's would not be. Checking memory against the
skill rubric manufactures findings against correct work, so this lens is built separately.

Per file: frontmatter present, valid YAML and a mapping (otherwise one finding, and that file stops
there); `name`, `description` and `metadata.type` present with `type` in the allowed set; `name`
kebab-case. **`name` is deliberately not required to match the filename stem** — 78 of ~211 real
files legitimately differ, so that rule would produce 78 false findings.

Per corpus: `MEMORY.md` carries no frontmatter; every memory has an index entry; every index entry
resolves; index length and entry width against a soft budget; no two files share a `name`.

Reporting shape is load-bearing here, because the counts are large and mostly benign:

| Check | Shape | Why |
|---|---|---|
| Orphaned memories | One finding, **full filename list** | 28 of 92 in one real scope. One problem, but each orphan is an individual keep-or-delete call, so the list is the payload |
| `MEMORY.md` has no entries | One root-cause finding, **instead of** the orphan list | A file named `MEMORY.md` need not be an index; one real scope's is a hand-written status doc. N symptoms would misdescribe one cause |
| Missing `**Why:**`/`**How to apply:**` | One aggregate finding with a count | 33 of 86 real files, because the convention postdates the corpus. Matched on the bold marker with variant wording allowed (`**Why this matters**` counts) — demanding the literal string would report 21 files that plainly do carry their reasoning |
| Index length and entry width | One summary finding, count plus worst case | 63 of 66 lines exceeded the budget in a healthy corpus; per-line findings would be pure noise |
| Dangling `[[links]]` | **Informational, never a finding** | The contract says a dangling link marks something worth writing later. Resolved against `name:` values *or* filename stems, since authors link by the stem |

A single-file target runs only the per-file checks and says which corpus checks did not run, so
`clean` never overstates what was examined.

---

## Escalation — what to recommend, and when

The audit reports; it does not fix. When a finding is better handled by an existing skill, say so
explicitly and name the invocation, so the user decides rather than discovering the option later.

| Finding shape | Recommend | Why not do it here |
|---|---|---|
| Project CLAUDE.md missing/stale commands, architecture, env setup | `claude-md-improver` | Its rubric is built for exactly this. **Do not recommend it for a standards CLAUDE.md** — the rubric assumes codebase context and will push the file toward the wrong shape |
| Skill mis-triggers, or a behavior claim needs measuring | `skill-creator` (Description Optimization) | Requires executing the skill across runs; a static pass cannot see triggering |
| A skill's behavior claims are unverified, or "does this still beat not having it" | `claude plugin eval --threshold 0.9 --ablation with-without` | Real sessions + LLM grading; the only mechanism here with a non-zero exit code, and the only one that can produce a no-plugin baseline delta |
| A bash script with no static analysis | `shellcheck <path>` | No bash LSP exists in this environment; shellcheck is installed |
| A finding that is an actual code defect in a script | `/satori:pre-pr-audit` or `/satori:adversarial-review` | Those own diff-scoped defect review |
| A stale, duplicate, superseded or orphaned auto-memory entry | **Edit the memory files directly** (and `MEMORY.md` with them) | There is no skill for this, and **not** `claude-md-improver` — its rubric is for CLAUDE.md files and would push memory toward the wrong shape, the same mistake that entry's own warning guards against for standards CLAUDE.md |

Recommend at most what the findings justify. `claude plugin eval` spawns real sessions and draws
down the token budget; it earns its cost on a skill whose behavior is genuinely in question, not
as a routine step on every audited skill.

---

## Scope and state

**One invocation audits a bounded, named set of targets** — a single file, one plugin's skills, or
an explicitly chosen list. Auditing everything at once produces a report nobody reads, which is
the same failure as not auditing at all.

For a multi-target pass, keep state in a gitignored `.reasoning-audit/` directory alongside the
`rp-fleet:refit` convention (one consolidated finding-or-clean report per target, resumable across
sessions, no edits and no PRs). A fleet-wide sweep should be dispatched *through* `refit` rather
than reimplementing its dispatch and resume machinery here.

## Cadence

Trigger off accumulated drift, not the calendar: **satori plugin-version bumps since the last
recorded audit pass**. A calendar trigger fires during quiet periods and stays silent during
churn; version bumps track how much has actually changed.

This is wired as a mechanism, not a reminder. `hooks/reasoning_audit_cadence.py` runs on
`SessionStart` (registered in `hooks/hooks.json`) and prints one advisory when the bump count
crosses its threshold — default 5, overridable with `--threshold`. It is silent otherwise, and it
fails open and silent on any error, because a hook that breaks session start costs more than a
missed advisory.

**Closing the loop is part of running this skill**: once an audit pass completes, record it, or
the advisory will keep firing every session.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reasoning_audit_cadence.py" --record
```

State lives at `~/.claude/satori-reasoning-audit.state`. A corrupt or missing state file reads as
"never audited" rather than as an error, so it self-heals on the next recorded pass instead of
disabling the cadence silently.

## Output

A status block, then findings. Every line computed from what was actually checked, never asserted
from what the skill intends to check:

```
  TARGET      plugins/satori/skills/adversarial-review  (kind: skill)
  LENSES      7 applied, 0 skipped
  CHECKER     scripts/audit_checks.py — exit 1 (findings)
  FINDINGS    mechanical 3   judgment 2   unclassified 0
  ESCALATIONS skill-creator (1: triggering unverified)
  NEXT        review the 3 mechanical findings below; none are auto-fixed
```

Then per finding: `path:line`, which lens fired, the evidence actually checked, and — for `J`
lenses — whether the claim was verified against a live source or is an unverified suspicion.
State that distinction once, plainly; do not stack hedges.

A target with no findings reports **clean for the lenses that ran**, naming which were skipped and
why. "Clean" without that qualifier overstates what a static pass can establish.

## Known limitations

- **The citations lens still reports cross-repo references as unresolvable.** A skill that cites a
  file in another repository (a fleet workspace's repo manifest or its CLAUDE.md) has no local file
  to resolve against. Those findings are real in the sense that the path cannot be verified from
  here, and noise in the sense that nothing is wrong. Triage them as unverifiable rather than
  broken.
- **Suppression of illustrative content is heuristic, and now governs two lenses.** The checker
  skips fenced code blocks, `Examples` lists, and lines carrying phrasing like "e.g." or "a name
  like" — because the first dogfood run reported 40 findings against one skill, nearly all of them
  correct work. That tuning cut it to 2. Extended to lens 5 on 2026-09-16, when the widened date
  keywords reached a `(measured <date>)` baseline inside the example handoff document that
  `handoff/SKILL.md` instructs the reader to write, and reported it twice as a 154-day-old claim.
  The cost runs both ways in both lenses: content introduced illustratively in phrasing not on
  that list is still flagged, and a genuinely broken citation — or a genuinely stale date, an
  un-run results row, or a thicket of undated novelty markers — written inside a code block is
  missed.
- **Static only.** Lens 6's behavioral half and any "is this skill actually being used correctly"
  question need transcript or run evidence this pass does not gather.
- **Lens 1 and 2 are judgment lenses**, so two runs over an unchanged target can disagree. The
  mechanical lenses (3, 5, 6-static, 7) are the reproducible core.
- **A clean audit is one sample**, not proof the reasoning is sound — the same caveat
  `/satori:adversarial-review` applies to a zero-yield round.
- **This skill's own thresholds and copied conventions are subject to its own lenses.** Audit it
  with itself periodically; the reference file records provenance so that is possible.
