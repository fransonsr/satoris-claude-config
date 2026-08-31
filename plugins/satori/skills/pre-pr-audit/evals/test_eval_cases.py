"""Executable form of the ten hand-written eval cases in test-cases/.

Written 2026-08-31. Until now every Results row read `Pending`: the cases had never
been run once, and nothing existed that could run them. Hand-running them would have
produced one dated row and then decayed again — the failure the suite's own README
describes. So the cases are executed here instead, one test per Pass Criteria
checkbox, and the README's table is generated from a real run.

Relationship to scripts/test_pattern_checker.py: that file unit-tests individual
check methods against planted inputs. This file drives the **whole checker** through
its public entry point on a real git repo, exactly as the documented runbook does, so
it also catches wiring problems a unit test cannot — a check that never runs, a diff
filter that excludes everything, a path that resolves differently under the CLI.

Each test names the case file and criteria it implements, so a failure points at the
markdown a reader would consult.
"""

import json
import pathlib
import shutil
import subprocess
import textwrap

import pytest

CHECKER = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "pattern_checker.py"
CASES = pathlib.Path(__file__).resolve().parent / "test-cases"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="requires git")


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one commit — the runbook's 'scratch git repo'."""
    r = tmp_path / "scratch"
    r.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=r, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=r, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=r, check=True)
    return r


def write(repo, rel, source):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(source).lstrip("\n"))
    return rel


def audit(repo, *changed):
    """Run the checker exactly as evals/README.md's runbook prescribes."""
    proc = subprocess.run(
        ["python3", str(CHECKER), "--changed-files", "\n".join(changed),
         "--merge-base", "HEAD"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    assert "Scanned 0/" not in proc.stderr, (
        f"checker scanned nothing — the case never exercised it.\nstderr: {proc.stderr}")
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        pytest.fail(f"checker did not emit JSON.\nstdout: {proc.stdout}\nstderr: {proc.stderr}")


def of(findings, category=None, pattern_contains=None):
    out = findings
    if category:
        out = [f for f in out if f["category"] == category]
    if pattern_contains:
        out = [f for f in out if pattern_contains.lower() in f["pattern"].lower()]
    return out


def test_every_case_file_has_an_executable_test():
    """Guard against a case being added to test-cases/ and silently never run.

    This is the failure the whole suite had: documented cases with no runner.
    """
    documented = {p.stem for p in CASES.glob("*.md")}
    covered = {n.replace("test_case__", "").split("__")[0].replace("_", "-")
               for n in globals() if n.startswith("test_case__")}
    missing = sorted(documented - covered)
    assert not missing, f"case file(s) with no executable test: {missing}"


# ─────────────────────────────────────────────── resource-lifecycle.md


def test_case__resource_lifecycle__reports_and_points_at_acquisition(repo):
    f = write(repo, "Job.java", """
        class Job {
            void run() {
                ds.persist();
                work();
            }
        }
        """)
    found = of(audit(repo, f), "Resource Leak")
    assert found, "no Resource Leak finding for persist() with no unpersist()"
    assert found[0]["line"] == 3, "line must point at the acquisition call"
    assert "finally" in found[0]["recommendation"].lower()


def test_case__resource_lifecycle__matching_release_clears_it(repo):
    f = write(repo, "Job.java", """
        class Job {
            void run() {
                ds.persist();
                try { work(); } finally { ds.unpersist(true); }
            }
        }
        """)
    assert of(audit(repo, f), "Resource Leak") == []


# ─────────────────────────────────────────────── try-finally-scope.md


def test_case__try_finally_scope__reports_gap_and_explains_why(repo):
    f = write(repo, "Part.java", """
        class Part {
            void run() {
                ds.persist();
                validate();
                try {
                    work();
                } finally {
                    ds.unpersist();
                }
            }
        }
        """)
    found = of(audit(repo, f), "Try/Finally Scope")
    assert found, "no Try/Finally Scope finding for a statement between persist and try"
    assert "finally" in found[0]["why_it_matters"].lower()


def test_case__try_finally_scope__moving_work_inside_try_clears_it(repo):
    f = write(repo, "Part.java", """
        class Part {
            void run() {
                ds.persist();
                try {
                    validate();
                    work();
                } finally {
                    ds.unpersist();
                }
            }
        }
        """)
    assert of(audit(repo, f), "Try/Finally Scope") == []


# ─────────────────────────────────────────────── edge-cases.md


def test_case__edge_cases__map_get_without_null_check(repo):
    f = write(repo, "Shard.java", """
        class Shard {
            void run() {
                String v = metadataMap.get(shardKey);
                use(v);
            }
        }
        """)
    found = of(audit(repo, f), "Edge Case", "null check")
    assert found, "no Edge Case finding for Map.get() with no null handling"
    assert found[0]["severity"] == "MEDIUM"


def test_case__edge_cases__get_or_default_clears_it(repo):
    f = write(repo, "Shard.java", """
        class Shard {
            void run() {
                String v = metadataMap.getOrDefault(shardKey, "");
                use(v);
            }
        }
        """)
    assert of(audit(repo, f), "Edge Case", "null check") == []


def test_case__edge_cases__to_map_without_merge_function(repo):
    """Known fragile: the arity test counts commas in an 11-line window, so this case
    needs comma-free filler to pass. Recorded in evals/README.md as still-open."""
    f = write(repo, "Meta.java", """
        class Meta {
            void run() {
                var m = list.stream().collect(Collectors.toMap(a, b));
            }
        }
        """)
    found = of(audit(repo, f), "Edge Case", "toMap")
    assert found, "no finding for Collectors.toMap with no merge function"
    assert found[0]["severity"] == "HIGH"
    assert "duplicate" in found[0]["pattern"].lower()


def test_case__edge_cases__merge_function_clears_to_map(repo):
    f = write(repo, "Meta.java", """
        class Meta {
            void run() {
                var m = list.stream().collect(Collectors.toMap(a, b, (x, y) -> x));
            }
        }
        """)
    assert of(audit(repo, f), "Edge Case", "toMap") == []


# ─────────────────────────────────────────────── silent-failures.md


@pytest.mark.parametrize("keyword", [
    "duplicate", "invalid", "corrupt", "conflict", "mismatch", "missing", "malformed",
])
def test_case__silent_failures__every_keyword_fires(repo, keyword):
    f = write(repo, "Val.java", f"""
        class Val {{
            void check(String id) {{
                LOGGER.warn("{keyword} record for {{}}", id);
            }}
        }}
        """)
    found = of(audit(repo, f), "Silent Failure")
    assert found, f"'{keyword}' produced no Silent Failure finding"
    assert found[0]["severity"] == "HIGH"


def test_case__silent_failures__benign_warn_is_ignored(repo):
    f = write(repo, "Val.java", """
        class Val {
            void check() {
                LOGGER.warn("cache warmed in {}ms", 12);
            }
        }
        """)
    assert of(audit(repo, f), "Silent Failure") == []


def test_case__silent_failures__log_shape_fires_too(repo):
    f = write(repo, "Val.java", """
        class Val {
            void check(String id) {
                log.error("duplicate record for {}", id);
            }
        }
        """)
    assert of(audit(repo, f), "Silent Failure"), "log.error shape did not fire"


# ─────────────────────────────────────────────── deduplication.md


def test_case__deduplication__list_add_in_loop(repo):
    f = write(repo, "Agg.java", """
        class Agg {
            void run() {
                for (Record record : records) {
                    resultList.add(record);
                }
            }
        }
        """)
    found = of(audit(repo, f), "Missing Deduplication")
    assert found, "no Missing Deduplication finding for list.add in a loop"
    assert found[0]["severity"] == "MEDIUM"


def test_case__deduplication__contains_guard_clears_it(repo):
    f = write(repo, "Agg.java", """
        class Agg {
            void run() {
                for (Record record : records) {
                    if (!resultList.contains(record)) {
                        resultList.add(record);
                    }
                }
            }
        }
        """)
    assert of(audit(repo, f), "Missing Deduplication") == []


def test_case__deduplication__add_outside_a_loop_is_ignored(repo):
    f = write(repo, "Agg.java", """
        class Agg {
            void run() {
                resultList.add(single);
            }
        }
        """)
    assert of(audit(repo, f), "Missing Deduplication") == []


# ─────────────────────────────────────────────── test-coverage.md


def test_case__test_coverage__new_class_without_test(repo):
    f = write(repo, "src/main/java/demo/RecordProcessor.java", "class RecordProcessor {}\n")
    found = of(audit(repo, f), "Test Coverage")
    assert found, "no Test Coverage finding for a new class with no test"
    assert found[0]["severity"] == "MEDIUM"
    assert "RecordProcessorTest.java" in found[0]["code_snippet"]


def test_case__test_coverage__existing_test_not_updated(repo):
    f = write(repo, "src/main/java/demo/Existing.java", "class Existing {}\n")
    write(repo, "src/test/java/demo/ExistingTest.java", "class ExistingTest {}\n")
    found = of(audit(repo, f), "Test Coverage")
    assert found, "no finding when the class changed but its test did not"
    assert found[0]["severity"] == "LOW"


def test_case__test_coverage__including_the_test_clears_it(repo):
    main = write(repo, "src/main/java/demo/Existing.java", "class Existing {}\n")
    test = write(repo, "src/test/java/demo/ExistingTest.java", "class ExistingTest {}\n")
    assert of(audit(repo, main, test), "Test Coverage") == []


# ─────────────────────────────────────────────── fragile-type-checks.md


def test_case__fragile_type_checks__tostring_equals(repo):
    f = write(repo, "Cmp.java", """
        class Cmp {
            boolean same(Expression node, Expression other) {
                return node.toString().equals(other.toString());
            }
        }
        """)
    found = of(audit(repo, f), "Silent Failure", "toString")
    assert found, "no finding for .toString().equals()"
    assert found[0]["severity"] == "HIGH"
    assert "instanceof" in found[0]["recommendation"]


def test_case__fragile_type_checks__string_shape_as_type(repo):
    f = write(repo, "Tok.java", """
        class Tok {
            boolean isLiteral(Token token) {
                return token.toString().startsWith("\\"");
            }
        }
        """)
    found = of(audit(repo, f), "Type/Name Resolution")
    assert found, "no finding for startsWith on toString() used as a type test"
    assert found[0]["severity"] == "HIGH"
    assert "instanceof" in found[0]["recommendation"]


# ─────────────────────────────────────────────── parallel-derivation.md


def test_case__parallel_derivation__same_constant_in_two_files(repo):
    a = write(repo, "Encoder.java", """
        class Encoder {
            int truncateTo() { return 37; }
        }
        """)
    b = write(repo, "Decoder.java", """
        class Decoder {
            int expectedLength() { return 37; }
        }
        """)
    found = of(audit(repo, a, b), "Parallel Derivation")
    assert found, "no Parallel Derivation finding for 37 hardcoded in two files"
    assert found[0]["severity"] == "MEDIUM"
    assert "Encoder.java" in found[0]["code_snippet"]
    assert "Decoder.java" in found[0]["code_snippet"]


def test_case__parallel_derivation__one_file_only_is_ignored(repo):
    a = write(repo, "Encoder.java", "class Encoder { int t() { return 37; } }\n")
    assert of(audit(repo, a), "Parallel Derivation") == []


def test_case__parallel_derivation__whitelisted_value_is_ignored(repo):
    a = write(repo, "Encoder.java", "class Encoder { int t() { return 256; } }\n")
    b = write(repo, "Decoder.java", "class Decoder { int e() { return 256; } }\n")
    assert of(audit(repo, a, b), "Parallel Derivation") == []


# ─────────────────────────────────────────────── narrow-catch.md


def test_case__narrow_catch__qualified_library_call(repo):
    f = write(repo, "Cfg.java", """
        class Cfg {
            void load(Path p) {
                try {
                    byte[] b = java.nio.file.Files.readAllBytes(p);
                } catch (NoSuchFileException e) {
                    handle(e);
                }
            }
        }
        """)
    found = of(audit(repo, f), "Edge Case", "catch")
    assert found, "no finding for a narrow catch around a qualified JDK call"
    assert found[0]["severity"] == "HIGH"
    assert "NoSuchFileException" in found[0]["pattern"]


def test_case__narrow_catch__broad_catch_is_ignored(repo):
    f = write(repo, "Cfg.java", """
        class Cfg {
            void load(Path p) {
                try {
                    byte[] b = java.nio.file.Files.readAllBytes(p);
                } catch (IOException e) {
                    handle(e);
                }
            }
        }
        """)
    assert of(audit(repo, f), "Edge Case", "catch") == []


def test_case__narrow_catch__unqualified_call_does_not_fire(repo):
    """Documents the known blind spot rather than asserting the ideal.

    Idiomatic Java imports the package, so `Files.readAllBytes(p)` carries no
    `java`/`org.apache` token in the preceding five lines and the check cannot see it.
    evals/README.md records this as still-open; this test pins the CURRENT behaviour so
    that closing the gap is a visible, deliberate change rather than a silent one.
    """
    f = write(repo, "Cfg.java", """
        class Cfg {
            void load(Path p) {
                try {
                    byte[] b = Files.readAllBytes(p);
                } catch (NoSuchFileException e) {
                    handle(e);
                }
            }
        }
        """)
    assert of(audit(repo, f), "Edge Case", "catch") == [], (
        "the unqualified-call blind spot appears to be fixed — if deliberate, update "
        "this test and evals/README.md's still-open list")


# ─────────────────────────────────────────────── python-subprocess-safety.md


def test_case__python_subprocess_safety__all_four_guards_missing(repo):
    f = write(repo, "runner.py", """
        import subprocess

        def build():
            subprocess.run(['mvn', 'test'])
        """)
    found = of(audit(repo, f), "Subprocess Safety")
    patterns = " | ".join(x["pattern"] for x in found)
    assert len(found) == 4, f"expected 4 subprocess findings, got {len(found)}: {patterns}"
    highs = [x for x in found if x["severity"] == "HIGH"]
    mediums = [x for x in found if x["severity"] == "MEDIUM"]
    assert len(highs) == 3 and len(mediums) == 1, (
        f"expected 3 HIGH + 1 MEDIUM, got {len(highs)} HIGH + {len(mediums)} MEDIUM")
    for expected in ("cwd=", "timeout=", "TimeoutExpired", "existence check"):
        assert any(expected in x["pattern"] for x in found), f"no finding mentions {expected}"


def test_case__python_subprocess_safety__all_guards_present_clears_all(repo):
    f = write(repo, "runner.py", """
        import os
        import shutil
        import subprocess

        def build():
            if not shutil.which('mvn'):
                raise RuntimeError('mvn missing')
            try:
                subprocess.run(['mvn', 'test'], cwd='/srv/app', timeout=600)
            except subprocess.TimeoutExpired:
                raise
        """)
    found = of(audit(repo, f), "Subprocess Safety")
    assert found == [], f"guards present but still flagged: {[x['pattern'] for x in found]}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
