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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
    assert findings == [], f"changelog heading flagged as stale: {[f.message for f in findings]}"


def test_a_changelog_still_reports_an_explicit_verified_claim(tmp_path):
    """The exemption is narrow: a `Verified <date>` claim inside a changelog is still a
    claim about current truth, not a record of when something landed."""
    doc = write(tmp_path / "CHANGELOG.md", """
        # Thing Changelog

        ## 2026-01-01 - v1.0
        Behaviour verified 2026-01-01 against the live API.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
    assert len(findings) == 1
    assert "Verified" in findings[0].message or "verified" in findings[0].message


def test_a_non_changelog_dated_heading_is_still_reported(tmp_path):
    """Only CHANGELOGs get the exemption — a dated heading in live guidance still ages."""
    doc = write(tmp_path / "SKILL.md", """
        ## Key Improvement (2026-01-01)
        Prose.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
    messages = [f.message for f in check_memory_contract(doc)]
    assert any("metadata.type" in m for m in messages), messages


def test_a_non_string_metadata_type_does_not_pass_for_the_wrong_reason(tmp_path):
    """`type: 1` must fail as "not one of the allowed values", not slip through
    membership testing or raise on a string operation."""
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


def test_an_undecodable_file_exits_cannot_check_rather_than_crashing(tmp_path, capsys):
    """UnicodeDecodeError is NOT an OSError, and a corpus walk is ~200 read_text()
    calls. One bad byte must not turn a clean refusal into a traceback."""
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
    assert main([str(memory)]) in (FINDINGS, CANNOT_CHECK)
    assert "Traceback" not in capsys.readouterr().err


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
    """The convention is a **bold** Why/How-to-apply line, not any sentence opening
    with the word. `\\**` (zero-or-more) instead of `\\*\\*` silently excused one real
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
            f"metadata:\n  type: project\n---\n{body}\n")
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
    """A title with `]` in it defeats a `\\[([^\\]]*)\\]\\(` parse, which would report a
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
    messages = [f.message for f in check_memory_contract(memory)]
    assert any("project-gone.md" in m for m in messages), messages


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


def test_overlong_index_entries_collapse_to_one_summary_finding(tmp_path):
    """Measured 2026-09-16: 63 of 66 lines in the real index exceed 150 chars.

    A check firing on 95% of a working corpus is noise. The documented rule says
    "under ~150 characters" and the tilde is load-bearing, so this is a soft budget
    worth one observation carrying the count and the worst case — never one finding
    per line.
    """
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n"
        + "".join(f"- [Entry {i}](project-p{i}.md) — {'x' * 200}\n" for i in range(4)),
        **{f"project_p{i}": RATIONALE for i in range(4)},
    )
    budget = [f for f in check_memory_contract(memory) if "150" in f.message]
    assert len(budget) == 1, [f.message for f in budget]
    assert "4" in budget[0].message


def test_an_index_past_the_truncation_limit_is_reported(tmp_path):
    memory = memory_corpus(
        tmp_path / "memory",
        "# Memory Index\n\n- [Kept](project-kept.md) — hook\n" + "\nfiller\n" * 210,
        project_kept=RATIONALE,
    )
    budget = [f for f in check_memory_contract(memory) if "200" in f.message]
    assert len(budget) == 1, [f.message for f in budget]


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
        findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
        assert len(findings) == 1, f"{keyword!r} was not recognized as a dated claim"
        assert "2026-01-01" in findings[0].message


def test_an_added_keyword_inside_the_window_does_not_fire(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        The behaviour was measured 2026-08-01 against the live API.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY) == []


def test_confirmed_inside_unconfirmed_is_not_a_dated_claim(tmp_path):
    """Without a \\b anchor, `confirmed` matches inside "unconfirmed" and the finding
    asserts the opposite of the text: it would report an explicitly UNconfirmed claim
    as a confirmation due for re-check."""
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        This remains unconfirmed 2026-01-01 and needs an owner.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY) == []


def test_confirmed_inside_reconfirmed_is_still_a_dated_claim(tmp_path):
    """The anchor must not over-reach: "reconfirmed" IS a confirmation, and the word
    boundary after the `re` prefix's hyphenless join is absent — so this is the case
    where \\b costs us a true positive, and that is the correct trade.

    Pinned as a deliberate, documented limitation rather than left ambiguous.
    """
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        The behaviour was reconfirmed 2026-01-01 against the live API.
        """)
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY) == []


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
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY) == []


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
    assert check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY) == []


def test_both_dates_stale_across_mixed_keywords_still_reports_the_newest(tmp_path):
    doc = write(tmp_path / "SKILL.md", """
        # Thing
        Confirmed 2026-01-01, re-verified 2026-02-01 against the live API.
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
    assert not any("never been run" in f.message for f in findings), \
        [f.message for f in findings]


def test_an_unrun_row_with_an_ordinary_name_is_still_reported(tmp_path):
    """The suppression above is narrow: a normal un-run row still fires."""
    doc = write(tmp_path / "evals" / "README.md", """
        | Test case | Last Tested | Result |
        |-----------|-------------|--------|
        | ordinary-regression | — | PENDING |
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=90, today=TODAY)
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
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
    assert len(findings) == 1, [f.message for f in findings]
    assert "2026-01-01" in findings[0].message


def test_a_dated_claim_under_an_examples_heading_is_not_reported(tmp_path):
    """The heading form, not just the fence form — both suppress for citations today."""
    doc = write(tmp_path / "SKILL.md", """
        ## Examples
        - A handoff records its baseline as (measured 2026-04-15)
        """)
    findings = check_self_dated_claims(doc, doc.read_text(), max_age_days=30, today=TODAY)
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
