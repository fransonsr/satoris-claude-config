"""Tests for pattern_checker.py.

Written 2026-08-29 in response to two defects a /satori:reasoning-audit pass found,
both of which had shipped silently because nothing ever executed this checker's own
eval suite. Each defect gets a planted-input test first — a checker that has never
demonstrated it can fail on a real input has not demonstrated it does anything.
"""

import textwrap

import pytest

from pattern_checker import PatternChecker


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
