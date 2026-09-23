"""Tests for audit_checks.py.

The first test of every lens plants a defect and asserts it is caught. A checker
that has never demonstrated it can fail has not demonstrated it does anything —
so the planted-defect case comes first, and "clean input passes" second.
"""

import datetime
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

from audit_checks import (
    CLEAN,
    CANNOT_CHECK,
    FINDINGS,
    MEMORY_FRONTMATTER_CONSEQUENCE,
    MEMORY_UNREADABLE_CONSEQUENCE,
    check_citations,
    check_frontmatter,
    check_memory_contract,
    memory_notes,
    check_self_dated_claims,
    check_skill_structure,
    check_unreferenced_scripts,
    classify_target,
    main,
)

TODAY = datetime.date(2026, 8, 29)


def write(path, content):
    """Write dedented content, creating parent dirs. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


# ---------------------------------------------------------------- lens 3: citations


def test_citation_to_missing_file_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        See `references/schemas.md` for the full schema.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert findings[0].lens == "citations"
    assert "references/schemas.md" in findings[0].message
    assert findings[0].line == 2


def test_citation_that_resolves_but_lacks_the_cited_term_is_caught(tmp_path):
    """The skill-creator fixture: a real file cited for something it does not contain.

    Verified 2026-08-29 against skill-creator's own SKILL.md, which cites
    references/schemas.md for an `assertions` field that file calls `expectations`.
    """
    write(tmp_path / "references" / "schemas.md", """
        # Schemas
        The `expectations` field lists what the run should satisfy.
        """)
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        See `references/schemas.md` for the `assertions` field.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "assertions" in findings[0].message
    assert "does not contain" in findings[0].message


def test_citation_that_resolves_and_contains_the_term_passes(tmp_path):
    write(tmp_path / "references" / "schemas.md", """
        # Schemas
        The `assertions` field lists what the run should satisfy.
        """)
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        See `references/schemas.md` for the `assertions` field.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_prose_in_backticks_is_not_treated_as_a_path(tmp_path):
    """Guards against flagging inline code that merely looks path-like."""
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        Run `git diff --stat` and check `foo` before proceeding.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


# The following classes of token are all NOT citations of a shipped file. Each was a
# real false positive on the first dogfood run against satori's own skills
# (2026-08-29); a checker that complains about correct work gets ignored, which is
# worse than not having it.


def test_template_placeholder_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Output: `~/.claude/handoff/continue/<slug>-CONTINUATION.md`
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_uri_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Test data lives at `s3://bucket/test-data/sample.json`.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_shell_variable_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Written to `$WORKSPACE_DIR/threads.json` at runtime.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_elided_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Template at `~/.claude/plugins/.../handoff/templates/PROGRESS-template.md`
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_bare_basename_found_elsewhere_in_the_skill_is_not_flagged(tmp_path):
    """`pattern_checker.py` cited from SKILL.md is satisfied by scripts/pattern_checker.py."""
    write(tmp_path / "scripts" / "pattern_checker.py", "print('hi')\n")
    doc = write(tmp_path / "SKILL.md", """
        Run `pattern_checker.py` to scan the diff.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_bare_basename_absent_from_the_skill_is_still_flagged(tmp_path):
    """The lens must keep working: a genuinely missing file is still a finding."""
    doc = write(tmp_path / "SKILL.md", """
        Run `nonexistent_helper.py` to scan the diff.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "nonexistent_helper.py" in findings[0].message


def test_home_relative_path_that_exists_is_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write(tmp_path / ".claude" / "real-file.md", "# Real\n")
    doc = write(tmp_path / "SKILL.md", """
        See `~/.claude/real-file.md` for details.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_home_relative_path_that_is_missing_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = write(tmp_path / "SKILL.md", """
        See `~/.claude/absent-file.md` for details.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "absent-file.md" in findings[0].message


def test_brace_placeholder_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Written to `~/.claude/handoff/active/{task-slug}-PROGRESS.md`
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_multi_segment_path_found_deeper_in_the_skill_is_not_flagged(tmp_path):
    """`lib/github-api.sh` cited from SKILL.md is satisfied by scripts/lib/github-api.sh."""
    write(tmp_path / "scripts" / "lib" / "github-api.sh", "echo hi\n")
    doc = write(tmp_path / "SKILL.md", """
        Sourced from `lib/github-api.sh` by every script.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_a_claim_that_a_file_LACKS_a_term_is_not_flagged(tmp_path):
    """Real false positive, 2026-08-29: pre-pr-audit notes what pattern_checker.py has NO
    analysis for. Prose asserting absence must not read as a broken citation."""
    write(tmp_path / "scripts" / "pattern_checker.py", "print('unrelated logic')\n")
    doc = write(tmp_path / "SKILL.md", """
        See `pattern_checker.py` — it has no `isinstance` analysis, so the agent covers it.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_path_inside_a_fenced_code_block_is_not_flagged(tmp_path):
    """Code blocks hold sample commands and template output, not citations."""
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        ```
        Manual verification: run against `/test-data/sample-data.json`
        ```
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_path_under_an_examples_heading_is_not_flagged(tmp_path):
    """`**Examples**:` followed by a bullet list names illustrations, not shipped files."""
    doc = write(tmp_path / "SKILL.md", """
        **Examples**:
        - `active/task-4.16.2-collection-indices-writer.md`
        - `active/bug-123-null-pointer-fix.md`
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_path_introduced_as_an_illustration_is_not_flagged(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        A generic name like `/tmp/pr-body.md` is the obvious filename for the obvious task.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_a_real_citation_after_an_examples_block_is_still_flagged(tmp_path):
    """The suppression must not leak past the example list it applies to."""
    doc = write(tmp_path / "SKILL.md", """
        **Examples**:
        - `active/sample-one.md`

        See `references/missing.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "references/missing.md" in findings[0].message


def test_a_real_citation_after_a_closed_code_fence_is_still_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ```
        run `/tmp/sample.json`
        ```
        See `references/missing.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "references/missing.md" in findings[0].message


def test_absolute_path_is_not_flagged(tmp_path):
    """`/tmp/...` and friends are runtime or system paths, never shipped-file citations."""
    doc = write(tmp_path / "CLAUDE.md", """
        Two agents both wrote to `/tmp/pr-body.md` and clobbered each other.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_illustrative_cue_on_the_previous_line_still_suppresses(tmp_path):
    """Prose wraps, so the cue and the path often land on different lines."""
    doc = write(tmp_path / "CLAUDE.md", """
        Chain a precondition with `&&`, not a separate statement — e.g.
        `validate.py` must actually stop the mutation when it exits non-zero.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_sibling_skill_reference_resolves_from_an_ancestor(tmp_path):
    """`address-pr-issues/SKILL.md` cited from pre-pr-audit/SKILL.md is a real sibling."""
    write(tmp_path / "address-pr-issues" / "SKILL.md", "# Other\n")
    doc = write(tmp_path / "pre-pr-audit" / "SKILL.md", """
        Defers to `address-pr-issues/SKILL.md` for the reactive path.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_a_genuinely_missing_sibling_is_still_flagged(tmp_path):
    doc = write(tmp_path / "pre-pr-audit" / "SKILL.md", """
        Defers to `no-such-skill/SKILL.md` for the reactive path.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1
    assert "no-such-skill/SKILL.md" in findings[0].message


def test_term_check_requires_a_positive_citation_cue(tmp_path):
    """Without 'see'/'per'/'documented in' phrasing, a co-occurring term is not a citation."""
    write(tmp_path / "scripts" / "helper.py", "print('hi')\n")
    doc = write(tmp_path / "SKILL.md", """
        The constants `60` and `MAX_LENGTH` are automated by `scripts/helper.py` already.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


# --------------------------------------------------------- lens 5: self-dated claims


def test_expired_verified_date_is_caught(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-01-01, re-check before trusting if stale**
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert findings[0].lens == "self-dated"
    assert "2026-01-01" in findings[0].message
    assert "240 days" in findings[0].message


def test_fresh_verified_date_passes(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-08-14** — still current.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


def test_fs_eng_verified_pass_convention_is_recognized(tmp_path):
    """cc-plugins' evals/README.md convention: `**Verified:** 2026-03-25 - PASS`."""
    doc = write(tmp_path / "README.md", """
        ### 1. MCP Server: Standalone
        **Verified:** 2026-03-25 - PASS
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-03-25" in findings[0].message


def test_last_tested_table_row_is_recognized(tmp_path):
    """The cc-plugins evals/README.md convention: a `| case | date | PASS |` results table."""
    doc = write(tmp_path / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | baseline-establish | 2026-07-02 | PASS |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert len(findings) == 1
    assert "2026-07-02" in findings[0].message


def test_last_updated_date_is_recognized(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Last Updated**: 2026-01-15
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-01-15" in findings[0].message


def test_a_date_with_no_validation_keyword_is_ignored(tmp_path):
    """A bare date is not a claim about its own freshness."""
    doc = write(tmp_path / "CLAUDE.md", """
        The incident occurred on 2026-01-01 and was resolved the same day.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


def test_malformed_date_does_not_crash(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-13-45** — nonsense date.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


# ------------------------------------------------------ lens 6: unreferenced scripts


def test_script_referenced_by_no_skill_is_caught(tmp_path):
    write(tmp_path / "skills" / "thing" / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        Nothing here invokes the helper.
        """)
    write(tmp_path / "skills" / "thing" / "scripts" / "orphan.py", "print('hi')\n")
    findings = check_unreferenced_scripts(tmp_path)
    assert len(findings) == 1
    assert findings[0].lens == "bypassed-scripts"
    assert "orphan.py" in findings[0].message


def test_referenced_script_passes(tmp_path):
    write(tmp_path / "skills" / "thing" / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        Run `scripts/used.py` to do the thing.
        """)
    write(tmp_path / "skills" / "thing" / "scripts" / "used.py", "print('hi')\n")
    assert check_unreferenced_scripts(tmp_path) == []


def test_a_script_does_not_reference_itself_into_cleanliness(tmp_path):
    """Rule 4: never let the target into its own evidence pool.

    The script names itself in a docstring; that must not count as a reference.
    """
    write(tmp_path / "skills" / "thing" / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        """)
    write(tmp_path / "skills" / "thing" / "scripts" / "selfref.py",
          '"""selfref.py — does a thing."""\n')
    findings = check_unreferenced_scripts(tmp_path)
    assert len(findings) == 1
    assert "selfref.py" in findings[0].message


def test_test_files_are_not_reported_as_unreferenced(tmp_path):
    """A test file is invoked by pytest, not cited from SKILL.md."""
    write(tmp_path / "skills" / "thing" / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        Run `scripts/used.py`.
        """)
    write(tmp_path / "skills" / "thing" / "scripts" / "used.py", "print('hi')\n")
    write(tmp_path / "skills" / "thing" / "scripts" / "test_used.py", "def test_x(): pass\n")
    assert check_unreferenced_scripts(tmp_path) == []


# --------------------------------------------------------- lens 7: frontmatter


def test_invalid_yaml_frontmatter_is_caught(tmp_path):
    """The real xp-pair defect, found 2026-08-29: a flow sequence with an inner colon."""
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: xp-pair
        description: Pairing.
        argument-hint: [task-description | "Task: ... Acceptance Criteria: ..."]
        ---
        # XP Pair
        """)
    findings = check_frontmatter(doc)
    assert len(findings) == 1
    assert findings[0].lens == "frontmatter"
    assert "YAML" in findings[0].message


def test_quoted_argument_hint_passes(tmp_path):
    """argument-hint is a real field current Claude Code accepts (see conventions ref)."""
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: xp-pair
        description: Pairing.
        argument-hint: '[task-description | "Task: ... Acceptance Criteria: ..."]'
        ---
        # XP Pair
        """)
    assert check_frontmatter(doc) == []


def test_unknown_frontmatter_key_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        invented-key: nope
        ---
        """)
    findings = check_frontmatter(doc)
    assert len(findings) == 1
    assert "invented-key" in findings[0].message


def test_description_with_angle_brackets_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: Use for <thing> processing.
        ---
        """)
    findings = check_frontmatter(doc)
    assert any("angle bracket" in f.message for f in findings)


def test_non_kebab_case_name_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: Thing_Name
        description: A thing.
        ---
        """)
    findings = check_frontmatter(doc)
    assert any("kebab-case" in f.message for f in findings)


def test_missing_required_field_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ---
        name: thing
        ---
        """)
    findings = check_frontmatter(doc)
    assert any("description" in f.message for f in findings)


def test_overlong_description_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", f"""
        ---
        name: thing
        description: {"x" * 1100}
        ---
        """)
    findings = check_frontmatter(doc)
    assert any("1024" in f.message for f in findings)


def test_file_with_no_frontmatter_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Just a heading, no frontmatter
        """)
    findings = check_frontmatter(doc)
    assert len(findings) == 1
    assert "frontmatter" in findings[0].message.lower()


# ------------------------------------------------------- lens 7: structure


def test_overlong_skill_md_is_caught(tmp_path):
    body = "\n".join(f"line {i}" for i in range(600))
    skill_dir = tmp_path / "thing"
    write(skill_dir / "SKILL.md", f"---\nname: thing\ndescription: A thing.\n---\n{body}")
    findings = check_skill_structure(skill_dir)
    assert any("500" in f.message for f in findings)


def test_long_reference_without_toc_is_caught(tmp_path):
    skill_dir = tmp_path / "thing"
    write(skill_dir / "SKILL.md", "---\nname: thing\ndescription: A thing.\n---\n# T\n")
    body = "\n".join(f"prose line {i}" for i in range(400))
    write(skill_dir / "references" / "big.md", f"# Big\n{body}")
    findings = check_skill_structure(skill_dir)
    assert any("table of contents" in f.message for f in findings)


def test_short_skill_with_short_references_passes(tmp_path):
    skill_dir = tmp_path / "thing"
    write(skill_dir / "SKILL.md", "---\nname: thing\ndescription: A thing.\n---\n# T\n")
    write(skill_dir / "references" / "small.md", "# Small\nJust a little.\n")
    assert check_skill_structure(skill_dir) == []


# ------------------------------------------------------------ classification


def test_skill_is_classified_by_its_frontmatter(tmp_path):
    skill_dir = tmp_path / "thing"
    write(skill_dir / "SKILL.md", "---\nname: thing\ndescription: A thing.\n---\n# T\n")
    assert classify_target(skill_dir / "SKILL.md") == "skill"


def test_standards_claude_md_is_distinguished_from_project(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        # Coding Standards and Principles
        ## Core Principles
        ### Test-Complete Development
        Every production change MUST have tests. Use SOLID principles.
        Prefer test-first. Refactor relentlessly.
        """)
    assert classify_target(doc) == "standards-claude-md"


def test_project_claude_md_is_distinguished_from_standards(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        # my-service
        ## Commands
        Build: `mvn clean install`
        Test: `mvn test`
        ## Architecture
        `src/main/java` holds the service; entry point is `Application.java`.
        """)
    assert classify_target(doc) == "project-claude-md"


def test_ambiguous_file_is_unclassified_rather_than_guessed(tmp_path):
    """Fail closed: an applicability gate that cannot tell must skip, not guess."""
    doc = write(tmp_path / "CLAUDE.md", """
        # Notes
        Some prose that signals nothing in particular.
        """)
    assert classify_target(doc) == "unclassified"


# -------------------------------------------------------------- exit codes


def test_main_returns_findings_code_on_a_planted_defect(tmp_path, capsys):
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        See `references/gone.md` for details.
        """)
    assert main([str(tmp_path / "SKILL.md")]) == FINDINGS
    assert "references/gone.md" in capsys.readouterr().out


def test_main_returns_clean_on_a_clean_target(tmp_path, capsys):
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        Nothing to see.
        """)
    assert main([str(tmp_path / "SKILL.md")]) == CLEAN
    assert "clean" in capsys.readouterr().out.lower()


def test_main_returns_cannot_check_on_a_missing_target(tmp_path, capsys):
    """Could-not-check is never clean."""
    assert main([str(tmp_path / "does-not-exist.md")]) == CANNOT_CHECK
    assert "CANNOT CHECK" in capsys.readouterr().err


def test_skill_audit_reaches_dates_in_bundled_markdown(tmp_path, capsys):
    """An eval README's stale `Last Tested` row must surface when auditing the skill.

    Auditing only SKILL.md would leave the eval suite's own staleness invisible —
    which is precisely the drift this skill exists to catch.
    """
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        """)
    write(tmp_path / "evals" / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | some-case | 2026-01-01 | PASS |
        """)
    assert main([str(tmp_path), "--max-age-days", "30"]) == FINDINGS
    out = capsys.readouterr().out
    assert "2026-01-01" in out
    assert "evals/README.md" in out


def test_citations_lens_skips_templates_examples_and_changelog(tmp_path, capsys):
    """Those documents hold illustrative paths by design; resolving them is noise.

    Dates still count everywhere — a stale date means the same thing in a CHANGELOG
    as in a SKILL.md — but an unresolvable path in a template is the template
    working as intended.
    """
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        """)
    write(tmp_path / "templates" / "PROGRESS-template.md",
          "Fill in `~/.claude/handoff/active/example-task.md` here.\n")
    write(tmp_path / "examples" / "session.md", "We ran `some-missing-script.sh` next.\n")
    write(tmp_path / "CHANGELOG.md", "- Referenced `old-removed-helper.py` back then.\n")

    assert main([str(tmp_path)]) == CLEAN
    assert "clean" in capsys.readouterr().out.lower()


def test_citations_lens_still_covers_reference_files(tmp_path, capsys):
    """references/ is asserting real paths, so it stays in scope."""
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        """)
    write(tmp_path / "references" / "conventions.md",
          "See `references/absent.md` for the rest.\n")

    assert main([str(tmp_path)]) == FINDINGS
    assert "references/absent.md" in capsys.readouterr().out


def test_reference_file_can_cite_a_script_elsewhere_in_the_skill(tmp_path):
    """A references/ doc citing `audit_checks.py` means scripts/audit_checks.py.

    Resolution has to consider the skill root, not just the citing file's own
    directory, or every reference-to-script citation reads as broken.
    """
    write(tmp_path / "scripts" / "audit_checks.py", "print('hi')\n")
    write(tmp_path / "SKILL.md", "---\nname: t\ndescription: T.\n---\n# T\n")
    doc = write(tmp_path / "references" / "conventions.md", """
        Limits enforced by `audit_checks.py`.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8"), root=tmp_path) == []


def test_sibling_resolution_works_from_a_relative_target_path(tmp_path, monkeypatch):
    """A relative invocation must not truncate the ancestor search."""
    write(tmp_path / "other-skill" / "SKILL.md", "# Other\n")
    write(tmp_path / "this-skill" / "SKILL.md", """
        Defers to `other-skill/SKILL.md` for that path.
        """)
    monkeypatch.chdir(tmp_path)
    relative = pathlib.Path("this-skill") / "SKILL.md"
    assert check_citations(relative, relative.read_text(encoding="utf-8")) == []


def test_a_bare_suffix_is_not_treated_as_a_path(tmp_path):
    """`.py` on its own is a suffix being discussed, not a file being cited."""
    doc = write(tmp_path / "SKILL.md", """
        Both the `.sh` and `.py` variants are supported.
        """)
    assert check_citations(doc, doc.read_text(encoding="utf-8")) == []


def test_skill_audit_does_not_double_report_skill_md(tmp_path, capsys):
    """SKILL.md must be scanned once, not twice, when walking bundled markdown."""
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        Verified 2026-01-01 by hand.
        """)
    assert main([str(tmp_path), "--max-age-days", "30"]) == FINDINGS
    assert capsys.readouterr().out.count("2026-01-01") == 1


def test_main_reports_unclassified_without_claiming_clean(tmp_path, capsys):
    write(tmp_path / "CLAUDE.md", "# Notes\nAmbiguous prose.\n")
    assert main([str(tmp_path / "CLAUDE.md")]) == CANNOT_CHECK
    out = capsys.readouterr()
    assert "unclassified" in (out.out + out.err).lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ============================================================================
# Iteration 2 — fixes for defects the skill-creator eval surfaced (2026-08-29).
# Each of these was a confirmed false positive or blind spot in iteration 1.
# ============================================================================


def test_script_reached_through_a_wrapper_is_not_reported_as_orphaned(tmp_path):
    """The eval's confirmed false positive: resolve-threads-bulk.py IS invoked.

    Its .sh wrapper execs it, and the wrapper is cited from SKILL.md. Greping only
    SKILL.md for the .py's own name reported a live script as orphaned.
    """
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        Run `scripts/resolve-threads-bulk.sh` to resolve in bulk.
        """)
    write(tmp_path / "scripts" / "resolve-threads-bulk.sh",
          'exec python3 "$SCRIPT_DIR/resolve-threads-bulk.py" "$@"\n')
    write(tmp_path / "scripts" / "resolve-threads-bulk.py", "print('hi')\n")
    assert check_unreferenced_scripts(tmp_path) == []


def test_a_script_named_only_by_an_orphaned_wrapper_is_still_reported(tmp_path):
    """Indirection is one level deep, and the wrapper must itself be reachable.

    Otherwise two mutually-referencing orphans vouch for each other.
    """
    write(tmp_path / "SKILL.md", """
        ---
        name: thing
        description: A thing.
        ---
        # Thing
        """)
    write(tmp_path / "scripts" / "orphan-wrapper.sh", 'exec python3 orphan-impl.py "$@"\n')
    write(tmp_path / "scripts" / "orphan-impl.py", "print('hi')\n")
    findings = check_unreferenced_scripts(tmp_path)
    names = " ".join(f.message for f in findings)
    assert "orphan-wrapper.sh" in names
    assert "orphan-impl.py" in names


def test_a_results_row_that_was_never_run_is_reported(tmp_path):
    """The blind spot: an em-dash date cell means 'never run', which is worse than stale.

    DATED_TABLE_ROW needs an ISO date, so the state every un-run suite is in was
    invisible. The em-dash is the cc-plugins convention, so this affects every
    eval README with un-run rows.
    """
    doc = write(tmp_path / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | resource-lifecycle | — | Pending |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "never" in findings[0].message.lower()
    assert findings[0].line == 3


def test_many_never_run_rows_collapse_to_one_finding(tmp_path):
    """Ten identical per-row findings is noise; one with a count is actionable.

    Same reasoning as the novelty-marker collapse — a reader needs to know the suite
    has never run, not to read the same sentence once per case.
    """
    rows = "\n".join(f"| case-{i} | — | Pending |" for i in range(10))
    doc = write(tmp_path / "README.md", f"""
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        {rows}
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    never_run = [f for f in findings if "never been run" in f.message]
    assert len(never_run) == 1
    assert "10" in never_run[0].message


def test_a_results_table_header_and_separator_are_not_reported(tmp_path):
    doc = write(tmp_path / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


def test_a_dated_passing_row_is_still_judged_by_its_date(tmp_path):
    """The never-run check must not swallow the ordinary stale-date case."""
    doc = write(tmp_path / "README.md", """
        | some-case | 2026-01-01 | PASS |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-01-01" in findings[0].message


def test_a_re_verification_on_the_same_line_supersedes_the_older_date(tmp_path):
    """Observed false positive: 'Verified X, re-verified Y' flagged on X at a tight window.

    Only the newest dated claim on a line governs; an older date alongside a newer
    one is history, not a stale claim.
    """
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-01-01, re-verified 2026-08-28** — still current.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


def test_both_dates_stale_on_one_line_still_reports_once(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-01-01, re-verified 2026-02-01** — long ago.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-02-01" in findings[0].message


def test_undated_novelty_markers_are_reported_once_per_file(tmp_path):
    """19 permanent '(NEW)' markers, oldest 4.5 months, went undetected in the eval.

    A marker with no date cannot expire, so it stops carrying information. Reported
    once per file with a count rather than once per line, to stay readable.
    """
    doc = write(tmp_path / "SKILL.md", """
        ## Step 1.6 (NEW)
        Some prose.
        ## Step 2 (NEW)
        More prose.
        ## Step 3 (NEW)
        Yet more.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    novelty = [f for f in findings if "NEW" in f.message]
    assert len(novelty) == 1
    assert "3" in novelty[0].message


def test_a_single_novelty_marker_is_not_reported(tmp_path):
    """One marker on genuinely new content is normal; a thicket of them is the signal."""
    doc = write(tmp_path / "SKILL.md", """
        ## Step 1 (NEW)
        Some prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert [f for f in findings if "NEW" in f.message] == []


def test_a_dated_section_header_is_treated_as_a_self_dated_claim(tmp_path):
    """'## Key Improvement (2026-04-17)' is a self-dated claim in a form lens 5 missed."""
    doc = write(tmp_path / "SKILL.md", """
        ## Key Improvement (2026-01-01)
        Some prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-01-01" in findings[0].message


def test_an_eval_suite_is_classified_rather_than_refused(tmp_path):
    """From the eval: the artifact family that motivated this skill was the one kind
    it could not classify. An eval README under evals/ is now a first-class target."""
    doc = write(tmp_path / "evals" / "README.md", """
        # thing Evals
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | some-case | 2026-03-25 | PASS |
        """)
    assert classify_target(doc) == "eval-suite"


def test_a_readme_outside_evals_is_still_unclassified(tmp_path):
    """The new kind must not become a catch-all for any README."""
    doc = write(tmp_path / "README.md", """
        # Some project
        Ambiguous prose that signals nothing.
        """)
    assert classify_target(doc) == "unclassified"


def test_main_runs_the_self_dated_lens_on_an_eval_suite(tmp_path, capsys):
    write(tmp_path / "evals" / "README.md", """
        # thing Evals
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | some-case | 2026-03-25 | PASS |
        | never-run | — | Pending |
        """)
    assert main([str(tmp_path / "evals" / "README.md")]) == FINDINGS
    out = capsys.readouterr().out
    assert "eval-suite" in out
    assert "2026-03-25" in out
    assert "never" in out.lower()


def test_a_changelog_dated_heading_is_not_a_stale_claim(tmp_path):
    """A CHANGELOG's `## 2026-04-20 - v1.2` heading is history by definition.

    Flagging it as "due for re-check" is a false positive of the same class the
    SONAR_TOKEN invariant already exempts: a changelog records what was true then and
    must not be rewritten to match the present.
    """
    doc = write(tmp_path / "CHANGELOG.md", """
        # Thing Changelog

        ## API Research Notes (2026-01-01)
        Some history.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert findings == [], f"changelog heading flagged as stale: {[f.message for f in findings]}"


def test_a_changelog_still_reports_an_explicit_verified_claim(tmp_path):
    """The exemption is narrow: a `Verified <date>` claim inside a changelog is still a
    claim about current truth, not a record of when something landed."""
    doc = write(tmp_path / "CHANGELOG.md", """
        # Thing Changelog

        ## 2026-01-01 - v1.0
        Behaviour verified 2026-01-01 against the live API.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert len(findings) == 1
    assert "Verified" in findings[0].message or "verified" in findings[0].message


def test_a_non_changelog_dated_heading_is_still_reported(tmp_path):
    """Only CHANGELOGs get the exemption — a dated heading in live guidance still ages."""
    doc = write(tmp_path / "SKILL.md", """
        ## Key Improvement (2026-01-01)
        Prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert len(findings) == 1


# ------------------------------------------------- classification: auto-memory


def test_a_memory_file_is_classified_by_its_metadata_type(tmp_path):
    """Claude Code auto-memory was the one artifact family the skill had to refuse.

    The positive evidence is `metadata.type` in the documented set, read from the
    file — never inferred from the `memory/` path component.
    """
    doc = write(tmp_path / "memory" / "project-some-gotcha.md", """
        ---
        name: project-some-gotcha
        description: A gotcha worth remembering.
        metadata:
          node_type: memory
          type: project
        ---
        The gotcha.
        """)
    assert classify_target(doc) == "auto-memory"


def test_memory_frontmatter_is_not_mistaken_for_a_skill(tmp_path):
    """Memory frontmatter carries `name` + `description` + `metadata`, so it is
    superficially skill-shaped. Classifying it as a skill would run the frontmatter
    lens, whose ALLOWED_FRONTMATTER and description rules memory legitimately
    violates — manufacturing findings against correct work."""
    doc = write(tmp_path / "memory" / "feedback-some-lesson.md", """
        ---
        name: feedback-some-lesson
        description: A lesson learned.
        metadata:
          type: feedback
        ---
        The lesson.
        """)
    assert classify_target(doc) == "auto-memory"


def test_a_memory_directory_is_classified_from_a_file_inside_it(tmp_path):
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", """
        # Memory Index

        - [Some gotcha](project-some-gotcha.md) — the hook
        """)
    write(memory / "project-some-gotcha.md", """
        ---
        name: project-some-gotcha
        description: A gotcha worth remembering.
        metadata:
          type: project
        ---
        The gotcha.
        """)
    assert classify_target(memory) == "auto-memory"


def test_a_bare_memory_index_classifies_on_sibling_evidence(tmp_path):
    """MEMORY.md carries no frontmatter of its own, so its only evidence is a sibling.

    Identifying MEMORY.md's role is name-based on purpose — that filename is the
    harness's own contract, the file it actually loads — while classifying the KIND
    stays evidence-based. The two rules answer different questions.
    """
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        # Memory Index

        - [Some gotcha](project-some-gotcha.md) — the hook
        """)
    write(memory / "project-some-gotcha.md", """
        ---
        name: project-some-gotcha
        description: A gotcha.
        metadata:
          type: project
        ---
        Body.
        """)
    assert classify_target(index) == "auto-memory"


def test_a_stray_frontmatterless_file_beside_memories_is_not_classified(tmp_path):
    """Sibling evidence is not a licence for any neighbouring file.

    Only MEMORY.md may borrow it; otherwise a scratch note dropped into the
    directory would be audited against a contract it never claimed to follow.
    """
    memory = tmp_path / "memory"
    write(memory / "project-some-gotcha.md", """
        ---
        name: project-some-gotcha
        description: A gotcha.
        metadata:
          type: project
        ---
        Body.
        """)
    stray = write(memory / "scratch-notes.md", """
        # Scratch
        Some notes with no frontmatter.
        """)
    assert classify_target(stray) == "unclassified"


def test_an_unrecognized_metadata_type_is_not_memory_evidence(tmp_path):
    """The allowed set is the contract. A file declaring something else has not
    shown it is memory, and guessing would apply the lens where it may not belong."""
    doc = write(tmp_path / "memory" / "whatever.md", """
        ---
        name: whatever
        description: Something else entirely.
        metadata:
          type: changelog
        ---
        Body.
        """)
    assert classify_target(doc) == "unclassified"


def test_a_skill_directory_is_still_a_skill_when_it_holds_memory_shaped_files(tmp_path):
    """Ordering pin: SKILL.md decides a directory before memory evidence is consulted."""
    skill_dir = tmp_path / "thing"
    write(skill_dir / "SKILL.md", "---\nname: thing\ndescription: A thing.\n---\n# T\n")
    write(skill_dir / "notes.md", """
        ---
        name: notes
        description: Notes.
        metadata:
          type: project
        ---
        Body.
        """)
    assert classify_target(skill_dir) == "skill"


# ------------------------------- classification: the legacy top-level `type:` shape
#
# Two real memory files predate the `metadata:` wrapper and carry `type:` at the top
# level. Refusing them would leave the most out-of-contract corpus in the fleet the
# one corpus the contract lens cannot look at — which inverts the point of the gate.


def test_a_legacy_top_level_type_file_is_classified_as_memory(tmp_path):
    """Real shape, from cds-sls-bulk-export/memory/feedback_defensive_programming.md."""
    doc = write(tmp_path / "memory" / "feedback_defensive_programming.md", """
        ---
        name: Defensive Programming Patterns from PR Reviews
        description: Code quality patterns learned from 13 rounds of review feedback
        type: feedback
        originSessionId: fa138b14-5c2c-4c1b-9f6e-a3bb4aaf9af8
        ---
        ## Pattern: Resource Lifecycle Discipline
        """)
    assert classify_target(doc) == "auto-memory"


def test_a_bare_top_level_type_is_not_enough_to_classify(tmp_path):
    """`type:` alone is a common static-site-generator key (Hugo, Docusaurus).

    Accepting it as sufficient evidence would classify an ordinary docs page as
    memory and then report it for "missing metadata.type" — a confident complaint
    about correct work, which is exactly what the applicability gate prevents.
    """
    doc = write(tmp_path / "docs" / "some-page.md", """
        ---
        title: Some Docs Page
        type: reference
        weight: 30
        ---
        # Some page
        """)
    assert classify_target(doc) == "unclassified"


def test_the_legacy_shape_needs_name_and_description_too(tmp_path):
    """The stricter three-key test applies only where the weaker signal forces it;
    a modern file still classifies on metadata.type alone."""
    doc = write(tmp_path / "docs" / "some-page.md", """
        ---
        name: some-page
        type: reference
        ---
        # Some page
        """)
    assert classify_target(doc) == "unclassified"


def test_a_directory_of_only_legacy_files_is_classified(tmp_path):
    memory = tmp_path / "memory"
    write(memory / "reference_quality_checklist_system.md", """
        ---
        name: Quality Checklist System
        description: Three-tier approach to applying PR feedback lessons
        type: reference
        ---
        # Quality Checklist System
        """)
    assert classify_target(memory) == "auto-memory"


# ------------------------------------------- memory-contract: per-file frontmatter


def test_a_memory_file_without_frontmatter_is_reported(tmp_path):
    """Real shape: cds-sls-bulk-export/memory/s3-policy-issue.md has none at all.

    The harness loads memories by their frontmatter, so a file without it is inert
    no matter how good its content is.
    """
    doc = write(tmp_path / "memory" / "s3-policy-issue.md", """
        # S3 Bucket Policy Issue - March 2026
        Cross-account access fails with 403.
        """)
    findings = check_memory_contract(doc)
    assert len(findings) == 1
    assert findings[0].lens == "memory-contract"
    assert "frontmatter" in findings[0].message


def test_invalid_yaml_frontmatter_is_reported_once_and_stops_that_file(tmp_path):
    """Real shape: an unquoted description containing `PR review:` makes PyYAML read
    the colon as a mapping. One finding, then stop — every later check would be
    reporting consequences of the same defect."""
    doc = write(tmp_path / "memory" / "feedback-workflow.md", """
        ---
        name: feedback-workflow
        description: Lessons from PR review: use the REST API, not gh pr edit
        metadata:
          type: feedback
        ---
        Body.
        """)
    findings = check_memory_contract(doc)
    assert len(findings) == 1
    assert "YAML" in findings[0].message


def test_frontmatter_that_is_not_a_mapping_is_reported(tmp_path):
    doc = write(tmp_path / "memory" / "odd.md", """
        ---
        - just
        - a list
        ---
        Body.
        """)
    findings = check_memory_contract(doc)
    assert len(findings) == 1
    assert "mapping" in findings[0].message


def test_a_missing_metadata_type_is_reported(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          node_type: memory
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_missing_name_is_reported(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        description: A thing.
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("name" in m for m in messages), messages


def test_a_missing_description_is_reported(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("description" in m for m in messages), messages


def test_an_unrecognized_metadata_type_names_the_offending_value(tmp_path):
    """The operator needs to know WHICH value was wrong to fix it in one pass."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type: decision
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("decision" in m for m in messages), messages


def test_a_non_kebab_case_name_is_reported(tmp_path):
    """Real value, from feedback_defensive_programming.md."""
    doc = write(tmp_path / "memory" / "feedback_defensive_programming.md", """
        ---
        name: Defensive Programming Patterns from PR Reviews
        description: Patterns learned from review feedback.
        type: feedback
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("kebab-case" in m for m in messages), messages


def test_a_name_that_differs_from_the_filename_stem_is_not_reported(tmp_path):
    """Real pair: aesthetic_philosophy.md carries `name: aesthetic-philosophy`.

    The documented examples show these legitimately differ, so a stem-equality rule
    would manufacture findings against correct work. Pinned so nobody adds one.
    """
    doc = write(tmp_path / "memory" / "aesthetic_philosophy.md", """
        ---
        name: aesthetic-philosophy
        description: What elegant code looks like.
        metadata:
          type: user
        ---
        Body.
        """)
    assert check_memory_contract(doc) == []


def test_a_valid_memory_file_produces_no_findings(tmp_path):
    doc = write(tmp_path / "memory" / "reference-thing.md", """
        ---
        name: reference-thing
        description: A reference fact.
        metadata:
          type: reference
        ---
        The fact.
        """)
    assert check_memory_contract(doc) == []


# ---------------------------- memory-contract: skill constraints must NOT be reused
#
# ALLOWED_FRONTMATTER, REQUIRED_FRONTMATTER and _check_description_field all encode
# SKILL constraints that real memory legitimately violates. Reusing them would
# manufacture findings against correct work on almost every file in the corpus.


def test_extra_metadata_keys_are_not_reported(tmp_path):
    """node_type/originSessionId/modified are written by the harness itself and
    appear on nearly every real memory file."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          node_type: memory
          type: project
          originSessionId: 445dc694-b3ed-4f74-a8ce-69b445ea4e5d
          modified: 2026-09-15
        ---
        Body.
        """)
    assert check_memory_contract(doc) == []


def test_a_description_with_angle_brackets_is_not_reported(tmp_path):
    """Three real descriptions contain `<`/`>`. Only a SKILL description is
    forbidden them — memory is not a skill."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: "Use <repo>-worktrees/<change>/ for in-flight work"
        metadata:
          type: project
        ---
        Body.
        """)
    assert check_memory_contract(doc) == []


def test_five_dash_lines_in_one_file_do_not_break_parsing(tmp_path):
    """Real shape: logging-migration-plugin-notes.md contains five `---` lines.

    Anything stricter than the existing split("---", 2) tolerance breaks on it.
    """
    doc = write(tmp_path / "memory" / "logging-migration-plugin-notes.md", """
        ---
        name: logging-migration-plugin-notes
        description: Running issues found during live migration sessions.
        metadata:
          type: project
        ---
        First section.

        ---

        Second section.

        ---

        Third section.
        """)
    assert check_memory_contract(doc) == []


# ------------------------------- memory-contract: defensive guards (PREVENTION)
#
# Zero of 211 real files exhibit these shapes. They are prevention against what YAML
# permits but this corpus has not yet produced — not reproduction of a measured bug.


def test_a_null_metadata_block_does_not_crash(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_string_metadata_value_does_not_crash(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata: project
        ---
        Body.
        """)
    # Through classify_target, not only check_memory_contract: the contract path reaches
    # no guard at all here ("type" in "project" is merely False), so the check-only
    # version stayed green under every one of the four guards a mutation matrix removed.
    assert classify_target(doc) == "unclassified"
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_list_metadata_value_does_not_crash(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          - type: project
        ---
        Body.
        """)
    # Same reason as the string case above: `"type" in [{...}]` is False with no error,
    # so only the classification path exercises a guard for this shape.
    assert classify_target(doc) == "unclassified"
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_hashable_non_string_metadata_type_is_reported(tmp_path):
    """`type: 1` is handled by set membership alone: `1 in MEMORY_TYPES` is simply False.

    Kept because "reported, not crashed" is the contract for every shape, and split from
    the unhashable case below because this one is the PROVABLY VACUOUS half — a mutation
    matrix over the four defensive guards showed it stays green under all of them. In one
    loop it sat first, so any regression reddening it aborted before the half that
    actually pins a guard ever ran.
    """
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type: 1
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_an_unhashable_metadata_type_is_reported_rather_than_raising(tmp_path):
    """The half that pins the guard: `['project'] in MEMORY_TYPES` raises
    `TypeError: unhashable type: 'list'`, so without `isinstance(declared, str)` in
    `_is_memory_type` the checker crashes instead of answering."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type:
            - project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_non_string_name_does_not_crash(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: 42
        description: A thing.
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("name" in m for m in messages), messages


def test_one_undecodable_file_in_a_corpus_is_a_finding_not_a_refusal(tmp_path, capsys):
    """UnicodeDecodeError is NOT an OSError, and a corpus walk is 211 files across 31
    real scopes. One bad byte must not turn a clean refusal into a traceback.

    Pins the exact exit code: the earlier `in (FINDINGS, CANNOT_CHECK)` accepted either
    outcome and so pinned neither, and its companion "no Traceback in stderr" assertion
    was unreachable — an escaping exception fails at the main() call, never reaching it.

    FINDINGS, not CANNOT_CHECK: the good sibling supplies classification evidence, so the
    corpus runs and the undecodable member is reported. The contrasting case — a decode
    error during classification of the target ITSELF, which exits 2 — is
    `test_a_decode_error_during_classification_exits_cannot_check`. The two names used to
    differ by one word while pinning opposite exit codes, and the one whose name matched
    the CANNOT_CHECK contract was the one that did not test it.
    """
    memory = tmp_path / "memory"
    write(memory / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type: project
        ---
        Body.
        """)
    (memory / "project-broken.md").write_bytes(b"---\nname: x\xff\xfe\ndescription: y\n---\n")
    assert main([str(memory)]) == FINDINGS
    assert "project-broken.md" in capsys.readouterr().out


# ------------------ memory-contract: the Why / How-to-apply convention (aggregate)


def test_feedback_files_missing_why_and_how_are_reported_as_one_finding(tmp_path):
    """54 of 86 real feedback/project files lack these, because the convention
    postdates most of the corpus. Per-file findings would bury every check that
    actually matters under dozens of style complaints."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n")
    for slug in ("one", "two", "three"):
        write(memory / f"feedback-{slug}.md", f"""
            ---
            name: feedback-{slug}
            description: A lesson.
            metadata:
              type: feedback
            ---
            The rule, stated plainly.
            """)
    rationale = [f for f in check_memory_contract(memory) if "How to apply" in f.message]
    assert len(rationale) == 1, [f.message for f in rationale]
    assert "3" in rationale[0].message


def test_a_feedback_file_carrying_both_markers_is_not_counted(tmp_path):
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n")
    write(memory / "feedback-good.md", """
        ---
        name: feedback-good
        description: A lesson.
        metadata:
          type: feedback
        ---
        The rule, stated plainly.

        **Why:** because it went wrong once.

        **How to apply:** whenever the shape recurs.
        """)
    assert [f for f in check_memory_contract(memory) if "How to apply" in f.message] == []


def test_a_why_heading_variant_still_counts_as_present(tmp_path):
    """Real bodies write `**Why this matters**`, `**Why**`, `**Why it moved**`.

    Demanding the literal `**Why:**` would report 21 real files that plainly DO
    carry their reasoning — the noise failure this lens exists to avoid.
    """
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n")
    write(memory / "feedback-variant.md", """
        ---
        name: feedback-variant
        description: A lesson.
        metadata:
          type: feedback
        ---
        The rule, stated plainly.

        **Why this matters**: because it went wrong once.

        **How to apply going forward**: whenever the shape recurs.
        """)
    assert [f for f in check_memory_contract(memory) if "How to apply" in f.message] == []


def test_user_and_reference_types_are_exempt_from_the_rationale_convention(tmp_path):
    """The convention is documented for feedback and project only."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n")
    write(memory / "reference-thing.md", """
        ---
        name: reference-thing
        description: A fact.
        metadata:
          type: reference
        ---
        The fact, with no rationale section.
        """)
    assert [f for f in check_memory_contract(memory) if "How to apply" in f.message] == []


def test_legacy_top_level_keys_are_not_reported_as_unknown(tmp_path):
    """`originSessionId` and `type` sit outside ALLOWED_FRONTMATTER, so reusing the
    SKILL validator would report both real legacy files for keys the harness wrote.

    Added after a mutation check showed the extra-metadata-keys test could not catch
    that reuse on its own: nested metadata keys are invisible to a top-level allowlist,
    so only a legacy file's top-level keys actually exercise the constraint.
    """
    doc = write(tmp_path / "memory" / "feedback_defensive_programming.md", """
        ---
        name: defensive-programming
        description: Patterns learned from review feedback.
        type: feedback
        originSessionId: fa138b14-5c2c-4c1b-9f6e-a3bb4aaf9af8
        ---
        The rule.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert not any("unknown" in m for m in messages), messages
    assert not any("originSessionId" in m for m in messages), messages


def test_a_plain_unbolded_why_line_does_not_satisfy_the_convention(tmp_path):
    r"""The convention is a **bold** Why/How-to-apply line, not any sentence opening
    with the word. `\**` (zero-or-more) instead of `\*\*` silently excused one real
    file whose body merely began a paragraph with "Why" — found by smoke-testing the
    93-file corpus against the count measured beforehand, which differed by exactly one.
    """
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n")
    write(memory / "feedback-prose.md", """
        ---
        name: feedback-prose
        description: A lesson.
        metadata:
          type: feedback
        ---
        The rule, stated plainly.

        Why this happened is a long story told in prose.

        How to apply it is likewise left to the reader.
        """)
    rationale = [f for f in check_memory_contract(memory) if "How to apply" in f.message]
    assert len(rationale) == 1, [f.message for f in rationale]


# ---------------------------------------- memory-contract: corpus-level checks
#
# Fixtures below use a helper because these tests are about the RELATIONSHIP between
# an index and the files beside it; spelling out full frontmatter in each would bury
# the one line that differs.


# The Why/How-to-apply lines are line-anchored, matching how real bodies write them.
# Named once so the ten tests below that are NOT about that convention do not each
# carry two lines of noise obscuring the one line they actually vary.
RATIONALE = "**Why:** reasons.\n\n**How to apply:** always."


def memory_corpus(root, index, **bodies):
    """Write a MEMORY.md plus one `project`-type memory per keyword argument.

    Built without textwrap so a body may span lines: dedent would key on the body's
    own indentation and break the frontmatter alignment.
    """
    write(root / "MEMORY.md", index)
    for slug, body in bodies.items():
        name = slug.replace("_", "-")
        (root / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: A memory.\n"
            f"metadata:\n  type: project\n---\n{body}\n", encoding="utf-8")
    return root


def test_a_memory_index_carrying_frontmatter_is_reported(tmp_path):
    """MEMORY.md is an index, not a memory. Frontmatter on it means it is being
    written as though the harness would load it as content."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", """
        ---
        name: memory-index
        description: The index.
        metadata:
          type: project
        ---
        - [A thing](project-a.md) — hook
        """)
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        **Why:** reasons. **How to apply:** always.
        """)
    messages = [f.message for f in check_memory_contract(memory)]
    assert any("index" in m and "frontmatter" in m for m in messages), messages


def test_orphaned_memories_are_reported_as_one_finding_listing_every_file(tmp_path):
    """Measured 2026-09-16: 28 of 92 files in the RP scope are orphans.

    One finding, because 28 is one problem. The full list, because each orphan is an
    individually actionable keep-or-delete decision and enumerating them is the point
    — a bare count would force a re-run to recover what the audit already knew.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — the hook\n",
        project_kept=RATIONALE,
        project_lost=RATIONALE,
        project_stray=RATIONALE,
    )
    orphan = [f for f in check_memory_contract(memory) if "no entry in MEMORY.md" in f.message]
    assert len(orphan) == 1, [f.message for f in orphan]
    assert "project-lost.md" in orphan[0].message
    assert "project-stray.md" in orphan[0].message
    assert "project-kept.md" not in orphan[0].message


def test_a_filename_named_only_in_prose_does_not_count_as_an_index_entry(tmp_path):
    """Match the link TARGET, not a bare filename substring — otherwise one entry
    mentioning another file in its hook would silently adopt it."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — supersedes project-lost.md\n",
        project_kept=RATIONALE,
        project_lost=RATIONALE,
    )
    orphan = [f for f in check_memory_contract(memory) if "no entry in MEMORY.md" in f.message]
    assert len(orphan) == 1
    assert "project-lost.md" in orphan[0].message


def test_an_index_title_containing_a_bracket_still_resolves_its_link(tmp_path):
    r"""A title with `]` in it defeats a `\[([^\]]*)\]\(` parse, which would report a
    correctly-indexed file as an orphan. Anchor on `](target)` instead."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Fix [sic] the thing](project-kept.md) — the hook\n",
        project_kept=RATIONALE,
    )
    orphan = [f for f in check_memory_contract(memory) if "no entry in MEMORY.md" in f.message]
    assert orphan == [], [f.message for f in orphan]


def test_an_index_entry_pointing_at_a_missing_file_is_reported(tmp_path):
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n- [Gone](project-gone.md) — hook\n",
        project_kept=RATIONALE,
    )
    dead = [f.message for f in check_memory_contract(memory) if "do not exist" in f.message]
    assert len(dead) == 1, [f.message for f in check_memory_contract(memory)]
    assert "project-gone.md" in dead[0], dead[0]
    # The negative half. Resolving against `index` instead of `index.parent` makes BOTH
    # entries unresolvable, and the positive assertion alone stays green while a healthy
    # file is reported as dead.
    assert "project-kept.md" not in dead[0], dead[0]
    assert dead[0].startswith("1 index entry points"), dead[0]


def test_an_index_with_no_entries_is_one_root_cause_not_many_orphans(tmp_path):
    """Real shape: cds-sls-bulk-export's MEMORY.md is a hand-written project-status
    document with zero index links. Reporting N orphans there is technically true but
    describes N symptoms of one cause, and reads as a pile of unrelated defects.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# CDS Bulk Export - Project Memory\n\n**Last Updated**: 2026-04-27\n\n## Current State\nPhase 4 nearly done.\n",
        project_one=RATIONALE,
        project_two=RATIONALE,
    )
    findings = check_memory_contract(memory)
    assert [f for f in findings if "no entry in MEMORY.md" in f.message] == []
    root = [f for f in findings if "no entries" in f.message]
    assert len(root) == 1, [f.message for f in findings]
    assert "2" in root[0].message


def test_two_memories_sharing_one_name_are_reported(tmp_path):
    """`name` is the identity [[wikilinks]] resolve against, so a duplicate makes one
    of the two unreachable by link."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [A](project-a.md) — h\n- [B](project-b.md) — h\n")
    for filename in ("project-a.md", "project-b.md"):
        write(memory / filename, """
            ---
            name: project-shared
            description: A memory.
            metadata:
              type: project
            ---
            **Why:** reasons.

            **How to apply:** always.
            """)
    messages = [f.message for f in check_memory_contract(memory)]
    assert any("project-shared" in m for m in messages), messages


def test_overlong_index_entries_collapse_to_one_note(tmp_path):
    """Measured 2026-09-16: 63 of 66 lines in the real index exceed 150 chars.

    The documented rule is "under ~150 characters" and the tilde is load-bearing, so
    this is a soft budget, not a defect. It is reported once, carrying the count and the
    worst case — and as a NOTE, because a finding moves the exit code and 95% of a
    healthy corpus breaching a soft budget would mean no real index could ever run clean.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n"
        + "".join(f"- [Entry {i}](project-p{i}.md) — {'x' * 200}\n" for i in range(4)),
        **{f"project_p{i}": RATIONALE for i in range(4)},
    )
    assert not [f for f in check_memory_contract(memory) if "150" in f.message]
    budget = [n for n in memory_notes(memory) if "150" in n]
    assert len(budget) == 1, memory_notes(memory)
    assert "4" in budget[0]


def test_an_index_past_the_line_budget_is_noted(tmp_path):
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n" + "\nfiller\n" * 210,
        project_kept=RATIONALE,
    )
    assert not [f for f in check_memory_contract(memory) if "200" in f.message]
    assert len([n for n in memory_notes(memory) if "200" in n]) == 1, memory_notes(memory)


def test_an_over_budget_but_otherwise_healthy_index_exits_clean(tmp_path):
    """The whole point of routing the budget to notes.

    Every real index in this fleet breaches the soft entry budget, so while it was a
    finding no healthy corpus could exit 0 — which makes the exit code useless as a
    gate and is the same complaint that made the single-file index branch a bug.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n"
        + "".join(f"- [Entry {i}](project-p{i}.md) — {'x' * 200}\n" for i in range(4)),
        **{f"project_p{i}": RATIONALE for i in range(4)},
    )
    assert main([str(memory)]) == CLEAN


def test_a_healthy_corpus_produces_no_corpus_findings(tmp_path):
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — a short hook\n",
        project_kept=RATIONALE,
    )
    assert check_memory_contract(memory) == []


# -------------------------------- memory-contract: wikilinks stay INFORMATIONAL


def test_a_dangling_wikilink_is_a_note_and_never_a_finding(tmp_path):
    """The documented contract is explicit: a dangling link "marks something worth
    writing later, not an error". It must not graduate to a defect merely because it
    is mechanically detectable."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n",
        project_kept="See [[not-written-yet]].\n\n" + RATIONALE,
    )
    assert check_memory_contract(memory) == []
    notes = memory_notes(memory)
    assert any("not-written-yet" in n for n in notes), notes


def test_a_wikilink_naming_a_filename_stem_is_not_dangling(tmp_path):
    """Real mismatch: feedback-wsl-parallel-agent-crash.md carries
    `name: wsl-parallel-agent-crash`, and links are written to the STEM.

    Resolving against `name:` alone called 12 of the RP corpus's targets dangling
    when only 4 truly are.
    """
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [A](feedback-wsl-parallel-agent-crash.md) — h\n"
                                "- [B](project-b.md) — h\n")
    write(memory / "feedback-wsl-parallel-agent-crash.md", """
        ---
        name: wsl-parallel-agent-crash
        description: A memory.
        metadata:
          type: feedback
        ---
        **Why:** reasons.

        **How to apply:** always.
        """)
    write(memory / "project-b.md", """
        ---
        name: project-b
        description: A memory.
        metadata:
          type: project
        ---
        See [[feedback-wsl-parallel-agent-crash]].

        **Why:** reasons.

        **How to apply:** always.
        """)
    assert memory_notes(memory) == []


def test_odd_double_bracket_tokens_do_not_crash_or_count(tmp_path):
    """Real tokens in the corpus: `[[ "$STATUS" -eq 0 ]]`, `[[ ]]`, `[[ ... ]]` — bash
    test syntax, in prose as well as in fenced blocks. Counting them as "worth writing
    later" would be nonsense, and `cc-plugins-java-stack#152` must still parse."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n",
        project_kept=('Run `[[ "$STATUS" -eq 0 ]]` and `[[ ]]` and `[[ ... ]]`. '
                      'See [[cc-plugins-java-stack#152]].\n\n' + RATIONALE),
    )
    notes = memory_notes(memory)
    assert any("cc-plugins-java-stack#152" in n for n in notes), notes
    assert not any("STATUS" in n for n in notes), notes


def test_dangling_wikilinks_alone_keep_the_exit_code_clean(tmp_path, capsys):
    """Informational must not change the verdict, or it is a finding by another name."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n",
        project_kept="See [[not-written-yet]].\n\n" + RATIONALE,
    )
    assert main([str(memory)]) == CLEAN
    assert "not-written-yet" in capsys.readouterr().out


# ------------------------- memory-contract: a single file states what did not run


def test_a_single_file_target_says_which_checks_did_not_run(tmp_path):
    """_report prints the same lens name either way, so without this a single-file
    "clean" overstates what was examined."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type: project
        ---
        Body.
        """)
    notes = memory_notes(doc)
    assert any("did not run" in n for n in notes), notes
    assert any("orphan" in n.lower() for n in notes), notes
    # Both halves of the conditional, and the entry the first version of the note omitted
    # — without these, dropping or inverting the conditional stayed green on all 166.
    assert any("index integrity" in n for n in notes), notes
    assert any("the Why/How-to-apply convention" in n for n in notes), notes


def test_a_single_file_target_does_not_run_corpus_checks(tmp_path):
    """Pointing at one memory must not report it as an orphan of its own directory."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n",
        project_lonely=RATIONALE,
    )
    findings = check_memory_contract(memory / "project-lonely.md")
    assert findings == [], [f.message for f in findings]


# ------------------------- lens 5: the extended date keywords (CROSS-KIND change)
#
# Change 4 widens DATED_CLAIM, which changes behaviour for EVERY artifact kind, not
# just auto-memory. Memory dates its claims overwhelmingly with words the original
# pattern could not see ("confirmed 2026-07-31", "measured 2026-09-15"), so lens 5 —
# the headline lens for this kind — was near-blind on it. The knock-on effects on the
# existing kinds are pinned below rather than left to be discovered later.

ADDED_DATE_KEYWORDS = ("measured", "confirmed", "observed", "re-checked",
                       "rechecked", "re-validated", "as of")


def test_each_added_date_keyword_is_recognized(tmp_path):
    """One test over an explicit list, not seven near-identical ones: the behaviour is
    single ("these words now count"), and the values stay visible in the source."""
    for keyword in ADDED_DATE_KEYWORDS:
        doc = write(tmp_path / "SKILL.md", f"""
            # Thing
            The behaviour was {keyword} 2026-01-01 against the live API.
            """)
        findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
        assert len(findings) == 1, f"{keyword!r} was not recognized as a dated claim"
        assert "2026-01-01" in findings[0].message


def test_an_added_keyword_inside_the_window_does_not_fire(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        The behaviour was measured 2026-08-01 against the live API.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY) == []


def test_confirmed_inside_unconfirmed_is_not_a_dated_claim(tmp_path):
    r"""Without a \b anchor, `confirmed` matches inside "unconfirmed" and the finding
    asserts the opposite of the text: it would report an explicitly UNconfirmed claim
    as a confirmation due for re-check."""
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        This remains unconfirmed 2026-01-01 and needs an owner.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY) == []


def test_reconfirmed_no_longer_matches_which_is_the_accepted_cost(tmp_path):
    r"""The one deliberately accepted loss from the \b anchors, and the name now says so.

    "reconfirmed" IS a confirmation, but it carries no word boundary after its prefix,
    so the anchor that stops `confirmed` matching inside "unconfirmed" also stops it
    matching here. Accepted: an inverted finding is worse than a missed one. The old
    name claimed this was "still a dated claim" — the opposite of what it asserts.
    """
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        The behaviour was reconfirmed 2026-01-01 against the live API.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY) == []


def test_verified_inside_unverified_is_not_a_dated_claim(tmp_path):
    """A PRE-EXISTING defect the anchors fix, not only a guard on the new keywords.

    Verified 2026-09-16: `unverified 2026-01-01` and `invalidated 2026-01-01` both
    match today, reporting a claim as stale-but-made when the text says the opposite.
    Zero live occurrences, so it is prevention — but of a bug that already shipped.
    """
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        This is unverified 2026-01-01, and the earlier result was invalidated 2026-01-01.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY) == []


def test_only_the_newest_date_governs_across_an_added_and_an_original_keyword(tmp_path):
    """The existing "a maintained claim is not a stale one" rule must survive the
    widening: a line carrying both an added and an original keyword is still judged by
    its newest date.

    Written synthetically on purpose. The spec cites a real line — "confirmed Resolved
    by Jeremy London 2026-07-16, verified during fleet-state.json reconciliation" — but
    measured 2026-09-16 that line matches NOTHING, before or after the change: neither
    keyword falls within the pattern's six-non-word-character reach of the date. It
    cannot pin this property, so a fixture that actually exercises it is used instead.
    """
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        Confirmed 2026-01-01, re-verified 2026-08-20 against the live API.
        """)
    assert check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY) == []


def test_both_dates_stale_across_mixed_keywords_still_reports_the_newest(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        Confirmed 2026-01-01, re-verified 2026-02-01 against the live API.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert len(findings) == 1
    assert "2026-02-01" in findings[0].message


def test_an_eval_readme_dated_only_with_an_added_keyword_now_classifies(tmp_path):
    """Knock-on effect, deliberate and bounded: _has_results_evidence reads DATED_CLAIM,
    so widening it widens eval-suite classification. A file under evals/ whose only
    dated claim says "measured" was unclassified before this change."""
    doc = write(tmp_path / "evals" / "README.md", """
        # thing Evals
        Throughput was measured 2026-03-25 on the reference corpus.
        """)
    assert classify_target(doc) == "eval-suite"


def test_a_file_dated_with_an_added_keyword_outside_evals_stays_unclassified(tmp_path):
    """The widening must stay bounded: the evals/ path component is still required, so
    this does not become a catch-all for any dated markdown file."""
    doc = write(tmp_path / "docs" / "README.md", """
        # Some project
        Throughput was measured 2026-03-25 on the reference corpus.
        """)
    assert classify_target(doc) == "unclassified"


def test_an_unrun_row_whose_name_carries_an_added_keyword_stops_being_reported(tmp_path):
    """Knock-on effect, and the one that REMOVES a finding that fires today.

    _is_unrun_row suppresses itself when _dated_claims_on matches the line, so a row
    with no date whose name column happens to read "confirmed 2026-01-01" now looks
    dated and is no longer reported as never-run. Pinned so the loss is a known,
    deliberate consequence rather than a silent regression discovered later.
    """
    doc = write(tmp_path / "evals" / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | confirmed 2026-01-01 regression | — | PENDING |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert not any("never been run" in f.message for f in findings), \
        [f.message for f in findings]


def test_an_unrun_row_with_an_ordinary_name_is_still_reported(tmp_path):
    """The suppression above is narrow: a normal un-run row still fires."""
    doc = write(tmp_path / "evals" / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | ordinary-regression | — | PENDING |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert any("never been run" in f.message for f in findings), [f.message for f in findings]


# ------------------- lens 5: illustrative context, for each of its three sub-checks
#
# check_citations has skipped fenced blocks, Examples headings and illustrative cues
# since 2026-08-29, when the first dogfood run reported example paths as broken
# citations. check_self_dated_claims never got the same treatment — not by design, but
# because no date keyword had yet landed in an example. Change 4's added keywords made
# it reachable: `(measured 2026-04-15)` inside handoff/SKILL.md's example handoff
# document became 2 findings, and both were false.
#
# The filter governs all three sub-checks, each pinned separately below so the
# suppression is a tested decision rather than a consequence of where it was inserted.


def test_a_dated_claim_inside_a_code_fence_is_not_reported(tmp_path):
    """The real false positive, from handoff/SKILL.md:37 — sample content in the
    example handoff document the skill tells the reader to write."""
    doc = write(tmp_path / "SKILL.md", """
        **Example**:
        ```markdown
        ### Known Facts
        - Performance baseline: 85ms for 10k records (measured 2026-04-15)
        ```
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert findings == [], [f.message for f in findings]


def test_an_unrun_results_row_inside_a_code_fence_is_not_reported(tmp_path):
    """Sub-check 2. A documented EXAMPLE of a results table is not a suite that has
    never run — it is documentation of the convention."""
    doc = write(tmp_path / "SKILL.md", """
        Record results in this shape:
        ```markdown
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | some-case | — | PENDING |
        ```
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert findings == [], [f.message for f in findings]


def test_novelty_markers_inside_a_code_fence_are_not_reported(tmp_path):
    """Sub-check 3, and the one that needed real thought: _check_novelty_markers reads
    whole text rather than lines, so it had to be handed the prose lines explicitly
    instead of inheriting the filter from a per-line loop."""
    doc = write(tmp_path / "SKILL.md", """
        Mark new steps like this:
        ```markdown
        ## Step 1.6 (NEW)
        ## Step 2 (NEW)
        ## Step 3 (NEW)
        ```
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    assert findings == [], [f.message for f in findings]


def test_novelty_markers_outside_a_fence_are_still_counted_and_fenced_ones_are_not(tmp_path):
    """The filter must not disable the check — only scope it. Three real markers plus
    two fenced samples must report three, not five."""
    doc = write(tmp_path / "SKILL.md", """
        ## Step 1.6 (NEW)
        ## Step 2 (NEW)
        ## Step 3 (NEW)
        Document them like this:
        ```markdown
        ## Step N (NEW)
        ## Step M (NEW)
        ```
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=90, today=TODAY)
    novelty = [f for f in findings if "NEW" in f.message]
    assert len(novelty) == 1
    assert "3 undated" in novelty[0].message, novelty[0].message


def test_a_dated_claim_after_a_closed_fence_is_still_reported(tmp_path):
    """Fence state must reset, or one example block would silence the rest of the file.

    Mirrors the equivalent guard the citations lens already carries.
    """
    doc = write(tmp_path / "SKILL.md", """
        ```markdown
        - Performance baseline: 85ms (measured 2026-04-15)
        ```
        The live behaviour was measured 2026-01-01 against the API.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert len(findings) == 1, [f.message for f in findings]
    assert "2026-01-01" in findings[0].message


def test_a_dated_claim_under_an_examples_heading_is_not_reported(tmp_path):
    """The heading form, not just the fence form — both suppress for citations today."""
    doc = write(tmp_path / "SKILL.md", """
        ## Examples
        - A handoff records its baseline as (measured 2026-04-15)
        """)
    findings = check_self_dated_claims(doc, doc.read_text(encoding="utf-8"), max_age_days=30, today=TODAY)
    assert findings == [], [f.message for f in findings]


def test_the_orphan_finding_agrees_in_number(tmp_path):
    """Found by smoke-testing real data: the message read "1 memory have no entry".

    Operator-facing text, so worth pinning — a reader who catches a checker in visibly
    broken output discounts the findings it reports alongside it.
    """
    one = memory_corpus(
        tmp_path / "single",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n",
        project_kept=RATIONALE, project_lost=RATIONALE,
    )
    orphan = [f for f in check_memory_contract(one) if "no entry" in f.message][0]
    assert "1 memory has no entry" in orphan.message, orphan.message

    many = memory_corpus(
        tmp_path / "several",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n",
        project_kept=RATIONALE, project_lost=RATIONALE, project_gone=RATIONALE,
    )
    orphan = [f for f in check_memory_contract(many) if "no entry" in f.message][0]
    assert "2 memories have no entry" in orphan.message, orphan.message


# ================================================================ review round 1
#
# Group A — real bugs found by the adversarial review.


def test_a_bare_memory_index_as_a_single_target_is_clean(tmp_path):
    """The headline defect: MEMORY.md classifies as auto-memory BECAUSE it has no
    frontmatter, then the per-file contract reported it FOR having no frontmatter.

    The condition that admits the target was the condition that failed it, and the two
    branches demanded contradictory states — adding frontmatter to silence it would
    break the directory branch. The existing classification test builds exactly this
    fixture and stops at classification, which is why 149 green tests never saw it.
    """
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        # Memory Index

        - [Some gotcha](project-some-gotcha.md) — the hook
        """)
    write(memory / "project-some-gotcha.md", """
        ---
        name: project-some-gotcha
        description: A gotcha.
        metadata:
          type: project
        ---
        Body.
        """)
    assert main([str(index)]) == CLEAN


def test_a_memory_index_carrying_frontmatter_is_reported_as_a_single_target(tmp_path):
    """The index check the single-file branch should apply: frontmatter must be ABSENT.

    Inverted from the per-file rule, which is the whole reason the shared path was wrong.
    """
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        ---
        name: memory-index
        description: The index.
        metadata:
          type: project
        ---
        - [A thing](project-a.md) — hook
        """)
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(index)]
    assert any("index" in m and "frontmatter" in m for m in messages), messages


def test_a_single_index_target_still_notes_its_own_budget(tmp_path):
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md",
                  "# Memory Index\n\n"
                  + "".join(f"- [Entry {i}](project-p{i}.md) — {'x' * 200}\n" for i in range(3)))
    for i in range(3):
        write(memory / f"project-p{i}.md", f"""
            ---
            name: project-p{i}
            description: A memory.
            metadata:
              type: project
            ---
            Body.
            """)
    assert not [f for f in check_memory_contract(index) if "150" in f.message]
    notes = memory_notes(index)
    assert len([n for n in notes if "150" in n]) == 1, notes
    # An index target DOES get index integrity, so claiming it was skipped would be a
    # false statement about a check that just ran.
    assert not any("index integrity" in n for n in notes), notes


def test_a_single_index_target_resolves_dead_entries_against_its_directory(tmp_path):
    """A dead entry is a claim the index itself makes, so it is in scope for an index
    target — unlike orphan detection, which is about files the index omits."""
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        # Memory Index

        - [Kept](project-kept.md) — hook
        - [Gone](project-gone.md) — hook
        """)
    write(memory / "project-kept.md", """
        ---
        name: project-kept
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    dead = [f.message for f in check_memory_contract(index) if "do not exist" in f.message]
    assert len(dead) == 1, [f.message for f in check_memory_contract(index)]
    assert "project-gone.md" in dead[0], dead[0]
    # Same negative half as the corpus test: `index` in place of `index.parent` as the
    # resolution base leaves this green while reporting project-kept.md as dead too.
    assert "project-kept.md" not in dead[0], dead[0]
    assert dead[0].startswith("1 index entry points"), dead[0]


def test_a_decode_error_during_classification_exits_cannot_check(tmp_path, capsys):
    """classify_target runs before and outside main's widened guard, so a decode error
    during classification escaped as a traceback whose exit status is 1 — the value the
    module docstring reserves for FINDINGS. "Cannot check" must never read as a result.

    The distinguishing input, which the old name did not carry: the TARGET's own read
    fails, so nothing classifies it. Contrast
    `test_one_undecodable_file_in_a_corpus_is_a_finding_not_a_refusal`, where a readable
    sibling classifies the corpus and the bad file is reported instead.
    """
    doc = tmp_path / "CLAUDE.md"
    doc.write_bytes(b"# Coding Standards\n## Core Principles\ntest-first \xff\xfe SOLID\n")
    assert main([str(doc)]) == CANNOT_CHECK
    assert "CANNOT CHECK" in capsys.readouterr().err


def test_the_checker_decodes_utf8_regardless_of_the_ambient_locale(tmp_path):
    """9 read_text(encoding="utf-8") calls carried no encoding=, so decoding followed the locale.

    Verified 2026-09-17: under LC_ALL=C the locale encoding is ANSI_X3.4-1968 and a
    valid UTF-8 file raises UnicodeDecodeError. Not hypothetical — real memory files are
    full of em dashes and accented names, so under a C locale the checker failed on
    essentially the whole corpus. Run as a subprocess because the locale is process-wide.
    """
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", """
        # Memory Index

        - [Café](project-cafe.md) — naïve façade — em dash included
        """)
    write(memory / "project-cafe.md", """
        ---
        name: project-cafe
        description: A memory about a café.
        metadata:
          type: project
        ---
        Prose with an em dash — and accents: é, ü, ñ.
        """)
    checker = pathlib.Path(__file__).parent / "audit_checks.py"
    env = {**os.environ, "LC_ALL": "C", "LANG": "C",
           "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    # sys.executable, not "python3" off PATH: under a venv, uv/pipx, or a CI matrix the
    # two differ, and the child would then be an interpreter that may not even have
    # PyYAML — surfacing as "Traceback in stderr" and blaming the locale fix.
    # encoding="utf-8" on the parent side too: `text=True` alone decodes the child's
    # output with the PARENT's locale, which under this very env is ANSI_X3.4-1968, so
    # the em dash in the checker's own output raised UnicodeDecodeError inside
    # subprocess before any assertion ran.
    done = subprocess.run([sys.executable, str(checker), str(memory)],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert "UnicodeDecodeError" not in done.stderr, done.stderr
    assert "Traceback" not in done.stderr, done.stderr
    # A positive assertion, so the test cannot pass on a subprocess that never reached
    # the checker, and an exact code — the fixture is deterministic, so a tuple pins
    # nothing. The body carries no **Why:**/**How to apply:**, so the rationale
    # aggregate fires and the run is FINDINGS every time.
    assert "finding(s) in" in done.stdout, done.stdout
    assert done.returncode == FINDINGS, f"rc={done.returncode} err={done.stderr}"


def test_a_legacy_shape_with_null_required_values_does_not_classify(tmp_path):
    """The legacy gate asked whether the KEYS were present, not whether they carried
    anything — so `name:` and `description:` with null values satisfied the very gate
    that exists to keep non-memory files out. A live instance of the "present but None"
    family we had labelled prevention-only."""
    doc = write(tmp_path / "docs" / "some-page.md", """
        ---
        name:
        description:
        type: reference
        ---
        # An ordinary docs page
        """)
    assert classify_target(doc) == "unclassified"


def test_an_illustrative_cue_does_not_leak_across_a_code_fence(tmp_path):
    """`previous` was assigned only on the fall-through branch, so after a fence the
    two-line lookback compared against a stale line from before it — suppressing real
    findings an arbitrary distance later."""
    doc = write(tmp_path / "SKILL.md", """
        Consider for example the following block.
        ```markdown
        filler
        ```
        See `references/gone.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1, [f.message for f in findings]
    assert "references/gone.md" in findings[0].message


def test_an_illustrative_cue_does_not_leak_past_an_examples_block(tmp_path):
    """Same mechanism via the Examples-heading path, which also `continue`s.

    The cue must sit BEFORE the heading: without one there, `previous` is still "" and
    the test passes whether or not the bug is present — which is how it read on first
    write, and exactly the vacuity the review flagged elsewhere.
    """
    doc = write(tmp_path / "SKILL.md", """
        Introduced for example like this.
        ## Examples
        - a sample entry

        See `references/gone.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text(encoding="utf-8"))
    assert len(findings) == 1, [f.message for f in findings]
    assert "references/gone.md" in findings[0].message


def test_an_unreadable_file_is_not_reported_as_specifically_a_decode_error(tmp_path):
    """One message covered every _read_text_or_none failure, including ones that are not
    decode errors at all, so it asserted more than the check established."""
    memory = tmp_path / "memory"
    write(memory / "project-ok.md", """
        ---
        name: project-ok
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    unreadable = memory / "project-unreadable.md"
    unreadable.write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    unreadable.chmod(0o000)
    # The precondition, checked rather than assumed. mode 000 does not stop a read as
    # root (CAP_DAC_OVERRIDE — the Docker default user), under /mnt/c or /mnt/d on WSL
    # (drvfs silently ignores the chmod), or on native Windows. In all three the file
    # stays readable and this test fails pointing at the checker's error reporting when
    # the fixture is what never became unreadable.
    try:
        unreadable.read_text(encoding="utf-8")
    except OSError:
        pass
    else:
        unreadable.chmod(0o644)
        pytest.skip("filesystem or uid does not enforce mode 000")
    try:
        messages = [f.message for f in check_memory_contract(memory)]
        relevant = [m for m in messages if "could not be read" in m]
        assert relevant, messages
        assert "UTF-8" not in relevant[0], relevant[0]
    finally:
        unreadable.chmod(0o644)


def test_an_unhashable_metadata_type_does_not_crash_the_rationale_check(tmp_path):
    """Covers the type-check in `_lacks_rationale`, which a mutation matrix showed no
    test could redden. Removing it leaves `declared_type not in MEMORY_RATIONALE_TYPES`,
    and for an unhashable value that raises TypeError instead of answering — the same
    shape as the classification guard, found the same way."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [Odd](project-odd.md) — hook\n")
    (memory / "project-odd.md").write_text(
        "---\nname: project-odd\ndescription: A memory.\n"
        "metadata:\n  type:\n    - feedback\n---\nBody with no rationale.\n",
        encoding="utf-8")
    findings = check_memory_contract(memory)
    assert any("metadata.type" in f.message for f in findings), [f.message for f in findings]


def test_a_broken_frontmatter_file_is_not_also_counted_as_lacking_rationale(tmp_path):
    """One defect, one finding: a file whose frontmatter cannot be parsed must not also
    appear in the rationale aggregate, since its type was never established."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [Broken](project-broken.md) — hook\n")
    (memory / "project-broken.md").write_text(
        "---\nname: project-broken\ndescription: Lessons from PR review: a colon\n"
        "metadata:\n  type: feedback\n---\nBody with no rationale.\n",
        encoding="utf-8")
    findings = check_memory_contract(memory)
    assert any("YAML" in f.message for f in findings), [f.message for f in findings]
    assert not any("How to apply" in f.message for f in findings), [f.message for f in findings]


def test_the_rationale_finding_truncates_its_sample_and_says_how_many_remain(tmp_path):
    """Covers the `and N more` branch, which no test reached: with the sample size at 3,
    a corpus of 5 must name three files and account for the other two."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n" + "".join(f"- [E{i}](project-p{i}.md) — hook\n" for i in range(5)),
        **{f"project_p{i}": "The rule, with no reasoning." for i in range(5)},
    )
    rationale = [f for f in check_memory_contract(memory) if "How to apply" in f.message]
    assert len(rationale) == 1, [f.message for f in rationale]
    assert "and 2 more" in rationale[0].message, rationale[0].message


def test_a_legacy_shape_with_a_non_string_name_does_not_classify(tmp_path):
    """`name: 42` passes a presence-or-null gate and reaches the contract check as a
    classified memory. isinstance is the right test for `name`, matching the discipline
    `_check_memory_name` already applies two functions away.

    Scoped to `name` in round 2: the same isinstance on `description` rejected a real but
    incomplete legacy memory along with the docs page, which
    `test_a_legacy_memory_with_a_blank_description_is_reported_not_refused` pins.
    """
    doc = write(tmp_path / "docs" / "some-page.md", """
        ---
        name: 42
        description: A page.
        type: reference
        ---
        # An ordinary docs page
        """)
    assert classify_target(doc) == "unclassified"


def test_a_legacy_shape_with_a_non_string_description_classifies_and_is_reported(tmp_path):
    """The accepted cost of loosening `description` back to a presence test, stated as a
    test rather than left implicit: such a file is now CLASSIFIED — and then reported by
    the contract check, which is the outcome the gate was wrongly pre-empting.

    Reporting a doubtful file beats refusing its whole corpus at exit 2, which is what
    declassification actually costs when the file sits in a real memory directory.
    """
    doc = write(tmp_path / "docs" / "some-page.md", """
        ---
        name: some-page
        description:
          - a
          - b
        type: reference
        ---
        # An ordinary docs page
        """)
    assert classify_target(doc) == "auto-memory"
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("description must be a string, got list" in m for m in messages), messages


def test_a_tilde_prefixed_target_is_expanded_rather_than_called_missing(tmp_path, monkeypatch):
    """[14], which the brief's triage did not list in either the fix or the deferred set.

    A `~` the shell did not expand — from a config file, a hook, or a quoted argument —
    made the target report as non-existent rather than as unexpanded, which sends the
    operator looking for a missing file instead of a quoting bug.
    """
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [A](project-a.md) — hook\n")
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Exact, not `in (CLEAN, FINDINGS)`: the fixture is deterministic — project-a.md's
    # body carries no **Why:**/**How to apply:**, so the rationale aggregate fires — and
    # a two-value tuple tolerates a future change that flips the fixture either way.
    assert main(["~/memory"]) == FINDINGS


def test_a_dollar_var_target_is_expanded_rather_than_called_missing(tmp_path, monkeypatch):
    """The other half of `expandvars(expanduser(...))`. Only the `~` half was covered, so
    the expansion that the ENAMETOOLONG guard exists to contain had no test at all."""
    memory = tmp_path / "memory"
    write(memory / "MEMORY.md", "# Memory Index\n\n- [A](project-a.md) — hook\n")
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        **Why:** reasons.

        **How to apply:** always.
        """)
    monkeypatch.setenv("AUDIT_MEMDIR", str(tmp_path))
    assert main(["$AUDIT_MEMDIR/memory"]) == CLEAN


def test_an_unclosed_frontmatter_block_carries_its_consequence(tmp_path):
    """[12]'s second defect: the consequence table held only the `absent` key, so an
    unclosed, invalid-YAML or non-mapping memory got no consequence clause at all —
    though the comment beside it said the file is inert whatever it contains, which is
    true of every one of those shapes.

    One test per shape rather than one loop over three: an `assert` aborts the loop, so
    a regression in the first shape hid whether the other two still held.
    """
    doc = write(tmp_path / "unclosed" / "project-a.md", "---\nname: project-a\n")
    findings = check_memory_contract(doc)
    assert len(findings) == 1, [f.message for f in findings]
    assert "inert" in findings[0].message, findings[0].message


def test_an_invalid_yaml_block_carries_its_consequence(tmp_path):
    doc = write(tmp_path / "invalid-yaml" / "project-a.md",
                "---\ndescription: Lessons from PR review: a colon\n---\nbody\n")
    findings = check_memory_contract(doc)
    assert len(findings) == 1, [f.message for f in findings]
    assert "inert" in findings[0].message, findings[0].message


def test_a_non_mapping_frontmatter_block_carries_its_consequence(tmp_path):
    doc = write(tmp_path / "not-a-mapping" / "project-a.md", "---\n- just a list\n---\nbody\n")
    findings = check_memory_contract(doc)
    assert len(findings) == 1, [f.message for f in findings]
    assert "inert" in findings[0].message, findings[0].message


# ================================================================ review round 2
#
# Group A — the index branch's own blind spots.


def test_an_entry_less_index_as_a_single_target_is_a_finding(tmp_path):
    """Round 1's headline bug with the sign flipped.

    The entry-less test lived in the corpus path only, so the single-file index branch
    could not tell an index from a hand-written status document and blessed it. Verified
    live on `-home-fransonsr-github-cds-sls-bulk-export/memory/MEMORY.md`, which has zero
    `](target)` entries: the file target exited 0 while the directory target exited 1 on
    the check `_check_memory_index` calls the highest-signal one in the lens.
    """
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        # CDS Bulk Export - Project Memory

        **Last Updated**: 2026-04-27

        ## Current State
        Phase 4 nearly done.
        """)
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    assert main([str(index)]) == FINDINGS
    messages = [f.message for f in check_memory_contract(index)]
    assert any("no entries" in m for m in messages), messages


def test_an_entry_less_index_is_reported_once_for_a_corpus_target(tmp_path):
    """The file-local check and the corpus enrichment are one finding, not two.

    The corpus form carries the count of stranded memories, which the file alone cannot
    know; sharing the check must not turn that into a duplicate pair saying the same
    thing with and without a number.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# Not an index at all\n\nProse only.\n",
        project_one=RATIONALE,
        project_two=RATIONALE,
    )
    root = [f for f in check_memory_contract(memory) if "no entries" in f.message]
    assert len(root) == 1, [f.message for f in root]
    assert "2" in root[0].message, root[0].message


def test_a_single_index_targets_scope_note_names_the_per_file_contract(tmp_path):
    """An index target never opens the memories beside it, so the per-file contract runs
    on nothing at all — the one gap `clean` would otherwise hide for this route."""
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", "# Memory Index\n\n- [A](project-a.md) — hook\n")
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    note = " ".join(memory_notes(index))
    assert "per-file" in note, note
    assert "index integrity" not in note, note


def test_a_single_memory_targets_scope_note_names_index_integrity(tmp_path):
    """The other direction of the same conditional: a non-index single file DOES lose
    index integrity, and the note must say so. Without both halves pinned, dropping the
    conditional altogether stays green."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A thing.
        metadata:
          type: project
        ---
        Body.
        """)
    note = " ".join(memory_notes(doc))
    assert "index integrity" in note, note
    assert "the Why/How-to-apply convention" in note, note


# Group B — a path that cannot be stat'd must be refused, not crash the run.


def test_an_over_long_expansion_is_refused_rather_than_crashing(tmp_path, monkeypatch, capsys):
    """`Path.exists()` re-raises every OSError but ENOENT/ENOTDIR/EBADF/ELOOP, so the
    expansion this fix introduced is itself a way to reach ENAMETOOLONG — and the
    traceback's exit status is 1, the value reserved for FINDINGS."""
    monkeypatch.setenv("AUDIT_LONG", "a" * 400)
    assert main(["$AUDIT_LONG/memory"]) == CANNOT_CHECK
    assert "CANNOT CHECK" in capsys.readouterr().err


def test_a_missing_target_names_the_spelling_that_was_typed(tmp_path, monkeypatch, capsys):
    """The operator-facing payload of the expansion fix: a `~` or `$VAR` that expanded to
    nothing must report both what was typed and what it became, or the message sends them
    looking for a missing file instead of at a quoting bug."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["~/nope"]) == CANNOT_CHECK
    err = capsys.readouterr().err
    assert "~/nope" in err, err
    assert str(tmp_path / "nope") in err, err


def test_an_index_entry_too_long_to_stat_is_reported_as_dead(tmp_path):
    """A malformed index entry is precisely what the dead-entry check exists to report,
    so it must not abort the whole run. Before the guard, one such entry degraded the
    audit to `CANNOT CHECK: <directory> could not be read`, losing every other finding
    and blaming the directory for one bad line in MEMORY.md."""
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n"
        f"- [Long]({'z' * 400}.md) — hook\n",
        project_kept=RATIONALE,
    )
    assert main([str(memory)]) == FINDINGS
    messages = [f.message for f in check_memory_contract(memory)]
    dead = [m for m in messages if "do not exist" in m]
    assert len(dead) == 1, messages
    assert "z" * 400 in dead[0], dead[0]


# Group C — one standard for a required field, across the gate and the contract.


def test_a_legacy_memory_with_a_blank_description_is_reported_not_refused(tmp_path):
    """Provenance (b): a real but incomplete legacy memory, not a docs page.

    Tightening the gate to isinstance rejected both provenances when only the docs page
    should be rejected — so a legacy memory with a blank `description` stopped being
    reported ("required field 'description' is absent", exit 1) and started being refused
    as unclassified (exit 2). The contract check already owns that defect; the gate must
    not pre-empt it.
    """
    memory = tmp_path / "memory"
    write(memory / "project-modern.md", """
        ---
        name: project-modern
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    legacy = write(memory / "feedback-legacy.md", """
        ---
        type: feedback
        name: feedback-legacy
        description:
        ---
        Body.
        """)
    assert classify_target(legacy) == "auto-memory"
    messages = [f.message for f in check_memory_contract(legacy)]
    assert any("'description' is absent" in m for m in messages), messages


def test_a_list_valued_description_is_reported_by_the_contract_check(tmp_path):
    """`name` is type-checked two functions away and `description` is not, so a modern
    memory whose description is a list exits CLEAN from the lens that exists to report
    exactly that — while the same value in a SKILL.md is reported."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description:
          - a
          - b
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("description must be a string, got list" in m for m in messages), messages


def test_an_int_valued_description_is_reported_by_the_contract_check(tmp_path):
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: 42
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("description must be a string, got int" in m for m in messages), messages


# Group D — one definition of the index role, used by every branch that asks.


def test_an_index_carrying_non_memory_frontmatter_is_reported_as_a_single_target(tmp_path):
    """The gate that admitted the target was the negation of the check the branch runs.

    `_looks_like_memory_index` refused any MEMORY.md starting with `---`, which is the
    exact input the "carries frontmatter" finding exists to report — so a single-file
    target exited 2 "unclassified" while the directory target exited 1 with the finding.
    One file, two verdicts, decided by how you point at it.
    """
    memory = tmp_path / "memory"
    index = write(memory / "MEMORY.md", """
        ---
        title: My hand-written index
        updated: 2026-09-01
        ---
        - [A thing](project-a.md) — hook
        """)
    write(memory / "project-a.md", """
        ---
        name: project-a
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    assert classify_target(index) == "auto-memory"
    assert main([str(index)]) == FINDINGS
    messages = [f.message for f in check_memory_contract(index)]
    assert any("frontmatter" in m and "index" in m for m in messages), messages


def test_a_memory_md_with_no_memory_siblings_is_audited_as_a_memory(tmp_path):
    """Role is not the filename alone. A MEMORY.md carrying valid memory frontmatter,
    with nothing beside it to make it an index, kept its per-file findings before the
    branch was added and must keep them after — routing on the name alone dropped both.
    """
    lone = write(tmp_path / "solo" / "MEMORY.md", """
        ---
        name: Not Kebab Case At All
        description:
        metadata:
          type: project
        ---
        Body.
        """)
    messages = [f.message for f in check_memory_contract(lone)]
    assert any("'description' is absent" in m for m in messages), messages
    assert any("kebab-case" in m for m in messages), messages


# Group E — a message must not assert a cause the check did not establish.


def test_an_unreadable_memory_does_not_blame_its_frontmatter(tmp_path):
    """Five producers of `problem`, not four: collapsing the kind-keyed table to one
    string widened the frontmatter clause onto a file whose frontmatter was never
    reached. An operator is sent to inspect a YAML block in a file that cannot be opened.
    """
    memory = tmp_path / "memory"
    write(memory / "project-ok.md", """
        ---
        name: project-ok
        description: A memory.
        metadata:
          type: project
        ---
        Body.
        """)
    (memory / "project-binary.md").write_bytes(b"\xff\xfe\x00broken")
    unreadable = [f for f in check_memory_contract(memory)
                  if "could not be read" in f.message]
    assert len(unreadable) == 1, [f.message for f in check_memory_contract(memory)]
    assert MEMORY_FRONTMATTER_CONSEQUENCE not in unreadable[0].message, unreadable[0]
    assert MEMORY_UNREADABLE_CONSEQUENCE in unreadable[0].message, unreadable[0]
    assert unreadable[0].line is None, unreadable[0]


def test_a_valid_type_nested_wrongly_is_not_told_its_value_is_out_of_range(tmp_path):
    """Live on the bulk-export corpus: "type is declared at the top level as 'feedback'
    ... so it must be one of: feedback, project, reference, user". The value IS one of
    them; the nesting is the defect, and the appended clause misdirects to the value."""
    doc = write(tmp_path / "memory" / "feedback-thing.md", """
        ---
        type: feedback
        name: feedback-thing
        description: A memory.
        ---
        Body.
        """)
    type_findings = [f.message for f in check_memory_contract(doc) if "type" in f.message]
    assert len(type_findings) == 1, type_findings
    assert "top level" in type_findings[0], type_findings[0]
    assert "must be one of" not in type_findings[0], type_findings[0]


def test_an_unknown_type_value_still_names_the_allowed_set(tmp_path):
    """The other half of the same conditional: when the value really is out of range,
    naming the allowed set is the whole point of the message."""
    doc = write(tmp_path / "memory" / "project-thing.md", """
        ---
        name: project-thing
        description: A memory.
        metadata:
          type: gotcha
        ---
        Body.
        """)
    type_findings = [f.message for f in check_memory_contract(doc) if "type" in f.message]
    assert len(type_findings) == 1, type_findings
    assert "must be one of" in type_findings[0], type_findings[0]


def test_a_refused_directory_names_only_the_evidence_a_directory_can_carry(tmp_path, capsys):
    """For a directory, `classify_target` consults exactly two things — a SKILL.md, and a
    file carrying memory frontmatter. Naming project-context and standards markers in the
    refusal reports two reasons that were never evaluated; 11 of 31 real scopes refuse
    this way."""
    empty = tmp_path / "memory"
    empty.mkdir()
    (empty / "stray-note.md").write_text("Just a note.\n", encoding="utf-8")
    assert main([str(empty)]) == CANNOT_CHECK
    err = capsys.readouterr().err
    assert "memory frontmatter" in err, err
    assert "standards markers" not in err, err
    assert "project-context markers" not in err, err
