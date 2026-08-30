"""Tests for pattern_checker.py.

Written 2026-08-29 in response to two defects a /satori:reasoning-audit pass found,
both of which had shipped silently because nothing ever executed this checker's own
eval suite. Each defect gets a planted-input test first — a checker that has never
demonstrated it can fail on a real input has not demonstrated it does anything.
"""

import pathlib
import re
import textwrap

import pytest

from pattern_checker import DATA_QUALITY_KEYWORDS, PatternChecker


def checker(changed_files=None):
    """A PatternChecker with no git dependency — the checks under test take explicit args."""
    return PatternChecker(changed_files or [], merge_base="HEAD")


def java(source):
    return textwrap.dedent(source).lstrip("\n").splitlines()


# ---------------------------------------------- defect 1: leading-slash path test


def test_single_module_repo_path_produces_a_test_coverage_finding(tmp_path, monkeypatch):
    """The defect: '/src/main/java/' with a leading slash never matches a repo-relative path.

    `git diff --name-only` returns `src/main/java/...` in a single-module repo, so every
    such repo has silently received zero test-coverage findings.
    """
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "src" / "main" / "java" / "demo" / "RecordProcessor.java"
    main_file.parent.mkdir(parents=True)
    main_file.write_text("class RecordProcessor {}\n")

    c = checker()
    c._check_test_coverage("src/main/java/demo/RecordProcessor.java")

    assert len(c.issues) == 1
    assert c.issues[0].category == "Test Coverage"
    assert "RecordProcessorTest.java" in c.issues[0].code_snippet


def test_multi_module_repo_path_still_produces_a_finding(tmp_path, monkeypatch):
    """The nested form worked before the fix and must keep working."""
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "mod" / "src" / "main" / "java" / "demo" / "Foo.java"
    main_file.parent.mkdir(parents=True)
    main_file.write_text("class Foo {}\n")

    c = checker()
    c._check_test_coverage("mod/src/main/java/demo/Foo.java")
    assert len(c.issues) == 1


def test_dot_prefixed_path_produces_a_finding(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "src" / "main" / "java" / "demo" / "Foo.java"
    main_file.parent.mkdir(parents=True)
    main_file.write_text("class Foo {}\n")

    c = checker()
    c._check_test_coverage("./src/main/java/demo/Foo.java")
    assert len(c.issues) == 1


def test_existing_test_file_suppresses_the_missing_test_finding(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "src" / "main" / "java" / "demo" / "Foo.java"
    main_file.parent.mkdir(parents=True)
    main_file.write_text("class Foo {}\n")
    test_file = tmp_path / "src" / "test" / "java" / "demo" / "FooTest.java"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("class FooTest {}\n")

    c = checker(changed_files=["src/main/java/demo/Foo.java",
                               "src/test/java/demo/FooTest.java"])
    c._check_test_coverage("src/main/java/demo/Foo.java")
    assert c.issues == []


def test_existing_but_unmodified_test_file_produces_the_low_finding(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main_file = tmp_path / "src" / "main" / "java" / "demo" / "Foo.java"
    main_file.parent.mkdir(parents=True)
    main_file.write_text("class Foo {}\n")
    test_file = tmp_path / "src" / "test" / "java" / "demo" / "FooTest.java"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("class FooTest {}\n")

    c = checker(changed_files=["src/main/java/demo/Foo.java"])
    c._check_test_coverage("src/main/java/demo/Foo.java")
    assert len(c.issues) == 1
    assert c.issues[0].severity == "LOW"


def test_a_non_java_path_is_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = checker()
    c._check_test_coverage("scripts/helper.py")
    assert c.issues == []


def test_a_test_source_file_is_not_itself_audited(tmp_path, monkeypatch):
    """A file already under src/test/java must not be asked for its own test."""
    monkeypatch.chdir(tmp_path)
    c = checker()
    c._check_test_coverage("src/test/java/demo/FooTest.java")
    assert c.issues == []


# ------------------------------------------ defect 2: literal empty-paren cleanup match


def test_unpersist_with_an_argument_counts_as_cleanup():
    """The defect: matching the literal '.unpersist()' misses the common blocking form.

    `ds.unpersist(true)` is cleanup; reading it as no-cleanup fired a CRITICAL false
    positive on correct code.
    """
    lines = java("""
        void run() {
            ds.persist();
            try {
                work();
            } finally {
                ds.unpersist(true);
            }
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".unpersist()", lines) is True


def test_unpersist_without_an_argument_still_counts_as_cleanup():
    lines = java("""
        void run() {
            ds.persist();
            ds.unpersist();
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".unpersist()", lines) is True


def test_destroy_with_an_argument_counts_as_cleanup():
    """The same fix must apply to the broadcast/destroy pair, not just unpersist."""
    lines = java("""
        void run() {
            var b = sc.broadcast(x);
            b.destroy(false);
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".destroy()", lines) is True


def test_absent_cleanup_is_still_reported_as_absent():
    """The fix must not make every input look clean."""
    lines = java("""
        void run() {
            ds.persist();
            work();
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".unpersist()", lines) is False


def test_cleanup_in_a_later_method_does_not_count():
    """Scope still matters: cleanup after the enclosing method closes is not cleanup."""
    lines = java("""
        void run() {
            ds.persist();
        }
        void other() {
            ds.unpersist();
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".unpersist()", lines) is False


def test_a_similarly_named_method_does_not_count_as_cleanup():
    """Guard against loosening the match so far that unrelated names satisfy it."""
    lines = java("""
        void run() {
            ds.persist();
            ds.unpersistAllLater();
        }
        """)
    assert checker()._has_cleanup_in_scope("F.java", 1, ".unpersist()", lines) is False



# --------------------------------- dead --project-patterns flag (removed 2026-08-30)


def test_no_dead_project_patterns_parameter():
    """`--project-patterns` was accepted, assigned, and never read — while SKILL.md
    advertised the capability, so the feature read as implemented-but-untested rather
    than absent. Removed rather than implemented, per the owner's call.

    This asserts on the source because a never-read parameter is invisible to a
    behavioral test by definition — that is exactly how it survived.
    """
    source = pathlib.Path(__file__).with_name("pattern_checker.py").read_text()
    assert "project_patterns" not in source, (
        "project_patterns is back; if it is being implemented, this test should be "
        "replaced by one that exercises the behavior")
    assert "--project-patterns" not in source


def test_checker_still_constructs_with_two_arguments():
    """The removal must not leave a signature nobody can call."""
    c = PatternChecker([], merge_base="HEAD")
    assert c.issues == []


# ---------------------------------- silent-failure keyword coverage (2026-08-30)
# The eval case documented `duplicate, missing, invalid, malformed`; the
# implementation had `duplicate, invalid, corrupt, conflict, mismatch` since the
# April initial commit. The doc list was invented during yesterday's eval
# conversion and never checked against the code — so the doc was wrong. Separately,
# `missing` and `malformed` belong in the check on the merits: both are textbook
# "data-quality problem logged instead of raised", which is the stated purpose.


def warn_line(message):
    """A changed LOGGER.warn line, with the whole file in the diff."""
    return [f'        LOGGER.warn("{message}", id);']


def findings_for(message):
    c = checker()
    lines = warn_line(message)
    c._check_silent_failures("F.java", "\n".join(lines), lines, {1})
    return c.issues


KEYWORDS_THAT_MUST_FIRE = [
    "duplicate", "invalid", "corrupt", "conflict", "mismatch",  # original set
    "missing", "malformed",                                     # added 2026-08-30
]


@pytest.mark.parametrize("keyword", KEYWORDS_THAT_MUST_FIRE)
def test_data_quality_keyword_is_detected(keyword):
    issues = findings_for(f"{keyword} record encountered, skipping")
    assert len(issues) == 1, f"'{keyword}' produced no Silent Failure finding"
    assert issues[0].severity == "HIGH"
    assert issues[0].category == "Silent Failure"


def test_a_warn_with_no_data_quality_keyword_produces_no_finding():
    """The check must stay targeted — not every warn is a swallowed data-quality error."""
    assert findings_for("cache warmed in {}ms") == []


def test_both_logger_shapes_share_one_keyword_list():
    """The two lists were duplicated verbatim in the source, so an edit to one would
    silently stop checking the other logger style. They now reference one constant —
    assert that by identity, not by comparing two parsed literals."""
    c = checker()
    lines = warn_line("x")
    c._check_silent_failures("F.java", "\n".join(lines), lines, {1})  # exercises the block
    source = pathlib.Path(__file__).with_name("pattern_checker.py").read_text()
    assert source.count("DATA_QUALITY_KEYWORDS)") == 2, (
        "both warning_patterns entries must reference the shared constant")
    assert "['duplicate'" not in source, "an inline keyword literal is back"


def test_the_eval_case_documents_exactly_the_implemented_keywords():
    """The defect that started this: doc and code naming different sets.

    Asserting agreement in both directions means neither can drift again without a
    failing test.
    """
    implemented = set(DATA_QUALITY_KEYWORDS)

    case = pathlib.Path(__file__).parent.parent / "evals" / "test-cases" / "silent-failures.md"
    text = case.read_text()
    documented = set()
    listed = re.search(r"data-quality keyword\s*\n?\(([^)]*)\)", text, re.S)
    if listed:
        documented = {k.strip().strip("`") for k in listed.group(1).replace("\n", " ").split(",")}
    assert documented == implemented, (
        f"eval case and implementation disagree.\n  documented: {sorted(documented)}\n"
        f"  implemented: {sorted(implemented)}")

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
