"""Tests for audit_checks.py.

The first test of every lens plants a defect and asserts it is caught. A checker
that has never demonstrated it can fail has not demonstrated it does anything —
so the planted-defect case comes first, and "clean input passes" second.
"""

import datetime
import textwrap

import pytest

from audit_checks import (
    CLEAN,
    CANNOT_CHECK,
    FINDINGS,
    check_citations,
    check_frontmatter,
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
    path.write_text(textwrap.dedent(content).lstrip("\n"))
    return path


# ---------------------------------------------------------------- lens 3: citations


def test_citation_to_missing_file_is_caught(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        See `references/schemas.md` for the full schema.
        """)
    findings = check_citations(doc, doc.read_text())
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
    findings = check_citations(doc, doc.read_text())
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
    assert check_citations(doc, doc.read_text()) == []


def test_prose_in_backticks_is_not_treated_as_a_path(tmp_path):
    """Guards against flagging inline code that merely looks path-like."""
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        Run `git diff --stat` and check `foo` before proceeding.
        """)
    assert check_citations(doc, doc.read_text()) == []


# The following classes of token are all NOT citations of a shipped file. Each was a
# real false positive on the first dogfood run against satori's own skills
# (2026-08-29); a checker that complains about correct work gets ignored, which is
# worse than not having it.


def test_template_placeholder_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Output: `~/.claude/handoff/continue/<slug>-CONTINUATION.md`
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_uri_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Test data lives at `s3://bucket/test-data/sample.json`.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_shell_variable_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Written to `$WORKSPACE_DIR/threads.json` at runtime.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_elided_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Template at `~/.claude/plugins/.../handoff/templates/PROGRESS-template.md`
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_bare_basename_found_elsewhere_in_the_skill_is_not_flagged(tmp_path):
    """`pattern_checker.py` cited from SKILL.md is satisfied by scripts/pattern_checker.py."""
    write(tmp_path / "scripts" / "pattern_checker.py", "print('hi')\n")
    doc = write(tmp_path / "SKILL.md", """
        Run `pattern_checker.py` to scan the diff.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_bare_basename_absent_from_the_skill_is_still_flagged(tmp_path):
    """The lens must keep working: a genuinely missing file is still a finding."""
    doc = write(tmp_path / "SKILL.md", """
        Run `nonexistent_helper.py` to scan the diff.
        """)
    findings = check_citations(doc, doc.read_text())
    assert len(findings) == 1
    assert "nonexistent_helper.py" in findings[0].message


def test_home_relative_path_that_exists_is_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write(tmp_path / ".claude" / "real-file.md", "# Real\n")
    doc = write(tmp_path / "SKILL.md", """
        See `~/.claude/real-file.md` for details.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_home_relative_path_that_is_missing_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = write(tmp_path / "SKILL.md", """
        See `~/.claude/absent-file.md` for details.
        """)
    findings = check_citations(doc, doc.read_text())
    assert len(findings) == 1
    assert "absent-file.md" in findings[0].message


def test_brace_placeholder_path_is_not_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        Written to `~/.claude/handoff/active/{task-slug}-PROGRESS.md`
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_multi_segment_path_found_deeper_in_the_skill_is_not_flagged(tmp_path):
    """`lib/github-api.sh` cited from SKILL.md is satisfied by scripts/lib/github-api.sh."""
    write(tmp_path / "scripts" / "lib" / "github-api.sh", "echo hi\n")
    doc = write(tmp_path / "SKILL.md", """
        Sourced from `lib/github-api.sh` by every script.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_a_claim_that_a_file_LACKS_a_term_is_not_flagged(tmp_path):
    """Real false positive, 2026-08-29: pre-pr-audit notes what pattern_checker.py has NO
    analysis for. Prose asserting absence must not read as a broken citation."""
    write(tmp_path / "scripts" / "pattern_checker.py", "print('unrelated logic')\n")
    doc = write(tmp_path / "SKILL.md", """
        See `pattern_checker.py` — it has no `isinstance` analysis, so the agent covers it.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_path_inside_a_fenced_code_block_is_not_flagged(tmp_path):
    """Code blocks hold sample commands and template output, not citations."""
    doc = write(tmp_path / "SKILL.md", """
        # Skill
        ```
        Manual verification: run against `/test-data/sample-data.json`
        ```
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_path_under_an_examples_heading_is_not_flagged(tmp_path):
    """`**Examples**:` followed by a bullet list names illustrations, not shipped files."""
    doc = write(tmp_path / "SKILL.md", """
        **Examples**:
        - `active/task-4.16.2-collection-indices-writer.md`
        - `active/bug-123-null-pointer-fix.md`
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_path_introduced_as_an_illustration_is_not_flagged(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        A generic name like `/tmp/pr-body.md` is the obvious filename for the obvious task.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_a_real_citation_after_an_examples_block_is_still_flagged(tmp_path):
    """The suppression must not leak past the example list it applies to."""
    doc = write(tmp_path / "SKILL.md", """
        **Examples**:
        - `active/sample-one.md`

        See `references/missing.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text())
    assert len(findings) == 1
    assert "references/missing.md" in findings[0].message


def test_a_real_citation_after_a_closed_code_fence_is_still_flagged(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        ```
        run `/tmp/sample.json`
        ```
        See `references/missing.md` for the schema.
        """)
    findings = check_citations(doc, doc.read_text())
    assert len(findings) == 1
    assert "references/missing.md" in findings[0].message


def test_absolute_path_is_not_flagged(tmp_path):
    """`/tmp/...` and friends are runtime or system paths, never shipped-file citations."""
    doc = write(tmp_path / "CLAUDE.md", """
        Two agents both wrote to `/tmp/pr-body.md` and clobbered each other.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_illustrative_cue_on_the_previous_line_still_suppresses(tmp_path):
    """Prose wraps, so the cue and the path often land on different lines."""
    doc = write(tmp_path / "CLAUDE.md", """
        Chain a precondition with `&&`, not a separate statement — e.g.
        `validate.py` must actually stop the mutation when it exits non-zero.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_sibling_skill_reference_resolves_from_an_ancestor(tmp_path):
    """`address-pr-issues/SKILL.md` cited from pre-pr-audit/SKILL.md is a real sibling."""
    write(tmp_path / "address-pr-issues" / "SKILL.md", "# Other\n")
    doc = write(tmp_path / "pre-pr-audit" / "SKILL.md", """
        Defers to `address-pr-issues/SKILL.md` for the reactive path.
        """)
    assert check_citations(doc, doc.read_text()) == []


def test_a_genuinely_missing_sibling_is_still_flagged(tmp_path):
    doc = write(tmp_path / "pre-pr-audit" / "SKILL.md", """
        Defers to `no-such-skill/SKILL.md` for the reactive path.
        """)
    findings = check_citations(doc, doc.read_text())
    assert len(findings) == 1
    assert "no-such-skill/SKILL.md" in findings[0].message


def test_term_check_requires_a_positive_citation_cue(tmp_path):
    """Without 'see'/'per'/'documented in' phrasing, a co-occurring term is not a citation."""
    write(tmp_path / "scripts" / "helper.py", "print('hi')\n")
    doc = write(tmp_path / "SKILL.md", """
        The constants `60` and `MAX_LENGTH` are automated by `scripts/helper.py` already.
        """)
    assert check_citations(doc, doc.read_text()) == []


# --------------------------------------------------------- lens 5: self-dated claims


def test_expired_verified_date_is_caught(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-01-01, re-check before trusting if stale**
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert findings[0].lens == "self-dated"
    assert "2026-01-01" in findings[0].message
    assert "240 days" in findings[0].message


def test_fresh_verified_date_passes(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-08-14** — still current.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


def test_fs_eng_verified_pass_convention_is_recognized(tmp_path):
    """cc-plugins' evals/README.md convention: `**Verified:** 2026-03-25 - PASS`."""
    doc = write(tmp_path / "README.md", """
        ### 1. MCP Server: Standalone
        **Verified:** 2026-03-25 - PASS
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-03-25" in findings[0].message


def test_last_updated_date_is_recognized(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Last Updated**: 2026-01-15
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    assert len(findings) == 1
    assert "2026-01-15" in findings[0].message


def test_a_date_with_no_validation_keyword_is_ignored(tmp_path):
    """A bare date is not a claim about its own freshness."""
    doc = write(tmp_path / "CLAUDE.md", """
        The incident occurred on 2026-01-01 and was resolved the same day.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


def test_malformed_date_does_not_crash(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-13-45** — nonsense date.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


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


def test_main_reports_unclassified_without_claiming_clean(tmp_path, capsys):
    write(tmp_path / "CLAUDE.md", "# Notes\nAmbiguous prose.\n")
    assert main([str(tmp_path / "CLAUDE.md")]) == CANNOT_CHECK
    out = capsys.readouterr()
    assert "unclassified" in (out.out + out.err).lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
