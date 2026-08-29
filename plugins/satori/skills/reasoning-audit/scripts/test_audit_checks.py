"""Tests for audit_checks.py.

The first test of every lens plants a defect and asserts it is caught. A checker
that has never demonstrated it can fail has not demonstrated it does anything —
so the planted-defect case comes first, and "clean input passes" second.
"""

import datetime
import pathlib
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


def test_last_tested_table_row_is_recognized(tmp_path):
    """The cc-plugins evals/README.md convention: a `| case | date | PASS |` results table."""
    doc = write(tmp_path / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | baseline-establish | 2026-07-02 | PASS |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
    assert len(findings) == 1
    assert "2026-07-02" in findings[0].message


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
    assert check_citations(doc, doc.read_text(), root=tmp_path) == []


def test_sibling_resolution_works_from_a_relative_target_path(tmp_path, monkeypatch):
    """A relative invocation must not truncate the ancestor search."""
    write(tmp_path / "other-skill" / "SKILL.md", "# Other\n")
    doc = write(tmp_path / "this-skill" / "SKILL.md", """
        Defers to `other-skill/SKILL.md` for that path.
        """)
    monkeypatch.chdir(tmp_path)
    relative = pathlib.Path("this-skill") / "SKILL.md"
    assert check_citations(relative, relative.read_text()) == []


def test_a_bare_suffix_is_not_treated_as_a_path(tmp_path):
    """`.py` on its own is a suffix being discussed, not a file being cited."""
    doc = write(tmp_path / "SKILL.md", """
        Both the `.sh` and `.py` variants are supported.
        """)
    assert check_citations(doc, doc.read_text()) == []


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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    never_run = [f for f in findings if "never been run" in f.message]
    assert len(never_run) == 1
    assert "10" in never_run[0].message


def test_a_results_table_header_and_separator_are_not_reported(tmp_path):
    doc = write(tmp_path / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


def test_a_dated_passing_row_is_still_judged_by_its_date(tmp_path):
    """The never-run check must not swallow the ordinary stale-date case."""
    doc = write(tmp_path / "README.md", """
        | some-case | 2026-01-01 | PASS |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


def test_both_dates_stale_on_one_line_still_reports_once(tmp_path):
    doc = write(tmp_path / "CLAUDE.md", """
        **Verified 2026-01-01, re-verified 2026-02-01** — long ago.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    novelty = [f for f in findings if "NEW" in f.message]
    assert len(novelty) == 1
    assert "3" in novelty[0].message


def test_a_single_novelty_marker_is_not_reported(tmp_path):
    """One marker on genuinely new content is normal; a thicket of them is the signal."""
    doc = write(tmp_path / "SKILL.md", """
        ## Step 1 (NEW)
        Some prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
    assert [f for f in findings if "NEW" in f.message] == []


def test_a_dated_section_header_is_treated_as_a_self_dated_claim(tmp_path):
    """'## Key Improvement (2026-04-17)' is a self-dated claim in a form lens 5 missed."""
    doc = write(tmp_path / "SKILL.md", """
        ## Key Improvement (2026-01-01)
        Some prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
