# Skill Structure Conventions

Conventions `audit_checks.py` checks skills against, with provenance for each.

**Every limit here is a copied number, and copied numbers are exactly what lens 1 exists to
catch.** Each entry records its source and the date it was verified, so this file can be audited
by the skill that reads it. One source we copied from was already stale at copy time — see
Frontmatter fields below.

## Contents

- [Frontmatter fields](#frontmatter-fields)
- [Field limits](#field-limits)
- [Progressive disclosure and file length](#progressive-disclosure-and-file-length)
- [Directory contract](#directory-contract)
- [Prose conventions](#prose-conventions)
- [What is deliberately not checked](#what-is-deliberately-not-checked)

## Frontmatter fields

| Field | Required | Notes |
|---|---|---|
| `name` | yes | kebab-case, ≤64 chars |
| `description` | yes | ≤1024 chars, no `<` or `>` |
| `argument-hint` | no | **See the correction below** |
| `license` | no | |
| `allowed-tools` | no | |
| `metadata` | no | |
| `compatibility` | no | ≤500 chars |

**Source**: `skill-creator`'s `scripts/quick_validate.py` `ALLOWED_PROPERTIES`, read at
`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator/scripts/quick_validate.py`.
Verified 2026-08-29.

**Correction applied at copy time**: that list omits `argument-hint`, but the field is legitimate —
Claude Code accepts it, and 3 of satori's own 6 skills use it. Running skill-creator's validator
unmodified rejects `address-pr-issues`, `continue`, and `handoff` for using a valid field. This is
why the list is forked here rather than called: a hardcoded allowlist with no cited source and no
validation date is itself a lens-1 finding, and this one was already wrong.

**Frontmatter must parse as strict YAML**, not merely be tolerated by the harness. Real instance
found 2026-08-29: `xp-pair`'s `argument-hint: [task-description | "Task: ... Acceptance Criteria:
..."]` loaded fine at runtime but crashed PyYAML, because `[...]` is read as a flow sequence and
the inner `:` is a syntax error inside it. Quote the whole value when it contains `:` or `[`.

## Field limits

| Limit | Value | Source |
|---|---|---|
| `name` max length | 64 | skill-creator `quick_validate.py`, verified 2026-08-29 |
| `description` max length | 1024 | ditto |
| `compatibility` max length | 500 | ditto |
| Angle brackets in `description` | forbidden | ditto |

## Progressive disclosure and file length

| Limit | Value | Source |
|---|---|---|
| `SKILL.md` ideal max lines | 500 | skill-creator `SKILL.md`, verified 2026-08-29 |
| Reference file needing a table of contents | 300 | ditto |

Past 500 lines, skill-creator's guidance is to "add an additional layer of hierarchy along with
clear pointers" rather than to cut content — the body moves into `references/`, loaded on demand.

**Note on how to read a length finding**: 5 of satori's 6 skills exceed 500 lines, several
substantially. That is a real signal about structure, but it is not a defect to fix reflexively —
these skills encode genuinely complex multi-phase procedures. Treat it as "this is a candidate for
splitting into references," not "this is broken."

## Directory contract

| Directory | Holds |
|---|---|
| `scripts/` | Executable code for deterministic, repetitive tasks |
| `references/` | Documents loaded into context as needed |
| `assets/` | Files used in output — templates, icons, fonts |

**Source**: skill-creator `SKILL.md`, verified 2026-08-29.

A script under `scripts/` that no `SKILL.md` references will never be invoked. See lens 6 in this
skill's `SKILL.md` for why that matters more than it looks.

## Prose conventions

Adopted from skill-creator's `SKILL.md` (verified 2026-08-29), as review heuristics rather than
hard checks — each needs judgment, so `audit_checks.py` does not decide them:

- **Imperative voice** in instructions.
- **All "when to use" information belongs in `description`**, not the body — the body is only read
  after the skill has already triggered.
- **Descriptions should be deliberately pushy**, because Claude tends to *under*-trigger skills.
- **All-caps `ALWAYS`/`NEVER`, or very rigid structures, are a yellow flag** — prefer reframing and
  explaining the reasoning. (Worth weighing against a genuine process mandate: this environment's
  own CLAUDE.md uses emphatic phrasing deliberately for non-negotiable rules. The flag is about
  rigidity substituting for reasoning, not about emphasis itself.)
- **Multi-domain skills** organize by variant under `references/<variant>.md`, so only the relevant
  file is read.

## What is deliberately not checked

- **Whether a skill triggers correctly.** Needs execution across runs; use skill-creator's
  Description Optimization loop.
- **Whether a skill's instructions produce good behavior.** Needs real sessions and grading; use
  `claude plugin eval`.
- **Whether prose is well written.** Out of scope, and not mechanically decidable.
