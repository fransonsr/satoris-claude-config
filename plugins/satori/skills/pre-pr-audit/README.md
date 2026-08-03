---
name: pre-pr-audit
description: Proactive code quality audit before creating a pull request - runs a mandatory multi-round adversarial pattern review plus pattern matching and optional SonarQube analysis to identify resource leaks, edge case gaps, test coverage issues, and code quality problems. Automatically fixes issues when possible. Use this skill whenever the user is about to create a PR, push code, or wants to check code quality before committing. Also use when they mention "before PR", "pre-commit check", "quality check", or "catch issues early".
---

# Pre-PR Code Quality Audit

Catch Copilot and SonarQube issues **before** creating a PR by running defensive programming checks, a mandatory multi-round adversarial pattern review, and optional static analysis on changed files.

**This file is an overview, not the procedure.** `SKILL.md` in this directory is the source of
truth for the actual step-by-step workflow. This file previously carried a full, independently
maintained copy of the procedure (a v1.1.0 snapshot that predated the mandatory adversarial
review entirely) and had drifted badly — it now covers only the rationale and a pointer.

- **Full step-by-step procedure**: see `SKILL.md`
- **Complementary reactive skill**: `/address-pr-issues` (this skill is proactive, before a PR
  exists; that one is reactive, after one does)

## Why This Skill Exists: PR #6 (13 Rounds → 2-5 Rounds)

`java-stack-logging-maven-plugin`'s PR #6 went through **13 rounds** of Copilot feedback:

- **Round 10**: Mixed debug logging patterns (some used `getLog().debug()`, others `if (debug) getLog().info("[DEBUG]")`)
- **Round 10**: Missing `isDirectory()` check before scanning source roots
- **Round 10**: Hard-coded pattern filtering (should be in an enum method)
- **Round 11**: File path collision in multi-module projects (relative vs absolute paths)
- **Round 11**: Brittle test for JSON indentation
- **Round 12**: More debug logging inconsistencies in related methods
- **Round 13**: Test fixture missing an `absolutePath` field used in production

A proactive consistency pass — pattern uniformity, test fixture completeness, centralization,
edge-case coverage, and Maven-specific checks — would have caught 8-11 of these before the PR
ever opened, an estimated 60-85% reduction in rounds. That case study is the reason this skill's
checks (`SKILL.md` Steps 4-4.9) exist in their current form, including the later addition of the
mandatory adversarial pattern review (Step 4.7) once reactive rounds kept recurring even with the
consistency checks alone.

## Workflow at a Glance

This is a condensed overview, not a step-number mapping — `SKILL.md`'s actual step numbers
(Step 1 through Step 8, with sub-steps 4.5-4.9) don't correspond 1:1 to the list below. For full
detail, read `SKILL.md`'s "Workflow Overview" and the named step headings it points to (e.g.
"Adversarial Pattern Review" is `SKILL.md` Step 4.7, not item 2 below):

1. Determine base branch, identify changed files, load project patterns from CLAUDE.md
2. Adversarial Pattern Review (direct, mandatory) — run to a terminal outcome, BEFORE the batch below, never concurrently
3. Run pattern-based, consistency, Maven-plugin, spec-completeness, and coherence-walk checks (parallel Workflow batch, once adversarial-review is done touching the tree)
4. Present findings interactively, offer to fix
5. Optional SonarQube analysis
6. Final summary and recommendations, record the audited tree + outcome marker

**This skill records a tree-hash + outcome marker on every run** (`CLEAN` or `NOT_CLEAN`) so a
later re-invocation on unchanged content can skip re-paying the cost of the mandatory adversarial
review sweep — but only when the prior run's recorded outcome was `CLEAN`; see `SKILL.md`'s "When
to Use This Skill" self-check and Step 8 for the exact mechanism.
