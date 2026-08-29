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
| **script** | Executable under a `scripts/` dir, or referenced as one from a SKILL.md |

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
*Applies to: all kinds.*

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
phrasings include a bare "Verified" or "Last Updated" followed by an ISO date, and the
`Verified: <date> - PASS` form used by the fs-eng `cc-plugins` eval README convention. This is the
cheapest lens and the one most likely to fire, because the pattern is already used in this
environment — both this repo's own CLAUDE.md and those org eval documents carry such dates.

A claim past its window is not automatically wrong; it is unverified. Report it as due for
re-check, and let lens 2 handle actually re-verifying it.

### 6. Scripts that exist but are bypassed — `M` (static) + `J` (behavioral)
*Applies to: skills, scripts.*

A script shipped under `scripts/` that no `SKILL.md` in its plugin references — so nothing will
ever invoke it — or a SKILL.md that spells out by hand a procedure one of its own scripts already
implements.

**Why this matters more than it looks**: a script is the durable encoding of reasoning already
done. Edge cases found over prior review rounds, ordering constraints, guard conditions, dedup
rules all live inside it. Work re-derived inline re-litigates every one of those invisibly, and
usually gets a subset right — which is why the script exists. The static half ("is it referenced
at all") is a cheap grep. The behavioral half ("is the agent actually running it when it should")
needs transcript evidence and is out of scope for a static pass; recommend `skill-creator`'s
analyzer for that.

### 7. Structure conventions — `M`
*Applies to: skills.*

Checked against the conventions in `references/skill-conventions.md`, which records where each
limit came from and when it was verified. Frontmatter validity (including strict YAML parse),
`SKILL.md` length, reference-file table-of-contents thresholds, and the
`scripts/`/`references/`/`assets/` directory contract.

Treat that reference file's own limits as subject to lens 1 — they are copied numbers, and one
source we copied from was itself stale (see the file's provenance notes).

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
- **Suppression of illustrative paths is heuristic.** The checker skips fenced code blocks,
  `Examples` lists, and lines carrying phrasing like "e.g." or "a name like" — because the first
  dogfood run reported 40 findings against one skill, nearly all of them correct work. That
  tuning cut it to 2. A path introduced illustratively in phrasing not on that list will still
  be flagged, and a genuinely broken citation inside a code block will be missed.
- **Static only.** Lens 6's behavioral half and any "is this skill actually being used correctly"
  question need transcript or run evidence this pass does not gather.
- **Lens 1 and 2 are judgment lenses**, so two runs over an unchanged target can disagree. The
  mechanical lenses (3, 5, 6-static, 7) are the reproducible core.
- **A clean audit is one sample**, not proof the reasoning is sound — the same caveat
  `/satori:adversarial-review` applies to a zero-yield round.
- **This skill's own thresholds and copied conventions are subject to its own lenses.** Audit it
  with itself periodically; the reference file records provenance so that is possible.
