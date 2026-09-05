"""Tests for scip_query.py.

Written test-first per the task's own complexity signal: `normalize_range()` and
`contains()` have multiple execution paths and boundary-condition-sensitive semantics
(half-open ranges — start inclusive, end exclusive), and `normalize_range()` parses an
externally-defined, empirically-reverse-engineered wire format rather than a documented
one. The SingleLineRange fixtures below are lifted verbatim from a real
`scip print --json` run against a real index (sls-dlq-worker); MultiLineRange has no
real sample in that index but follows the exact same PascalCase-wrapper /
snake_case-field convention already confirmed for SingleLineRange, so it's the same
shape with a second line instead of one.
"""

import json
import subprocess

import pytest

from scip_query import (
    DEFINITION,
    cmd_at,
    cmd_symbol,
    contains,
    iter_occurrences,
    load_index,
    normalize_range,
    role_label,
)


# ---------------------------------------------- normalize_range: real wire-format shapes


def test_single_line_range_from_real_scip_print_output():
    # Verbatim occurrence from `scip print --json` on a real sls-dlq-worker index.
    occ = {
        "TypedRange": {"SingleLineRange": {"line": 10, "start_character": 13, "end_character": 31}},
        "symbol": "scip-java maven maven/org.familysearch.sls/sls-dlq-worker 4.0-SNAPSHOT "
                  "org/familysearch/sls/dlq/worker/config/ObjectMapperConfig#",
        "symbol_roles": 1,
    }
    assert normalize_range(occ) == (10, 13, 10, 31)


def test_multi_line_range_uses_start_and_end_line():
    occ = {"TypedRange": {"MultiLineRange": {
        "start_line": 9, "start_character": 4, "end_line": 21, "end_character": 1,
    }}}
    assert normalize_range(occ) == (9, 4, 21, 1)


def test_single_line_range_omits_start_character_when_it_is_zero():
    """Protobuf JSON drops zero-valued scalars, so a symbol at column 0 has no
    `start_character` key at all. Verbatim shape from `scip print --json` on a real
    records-platform-mcp index, where 86 of 22647 occurrences look like this."""
    occ = {"TypedRange": {"SingleLineRange": {"line": 13, "end_character": 7}}}
    assert normalize_range(occ) == (13, 0, 13, 7)


def test_single_line_range_omits_line_when_it_is_zero():
    """A symbol on the file's first line (line 0) has no `line` key."""
    occ = {"TypedRange": {"SingleLineRange": {"start_character": 4, "end_character": 11}}}
    assert normalize_range(occ) == (0, 4, 0, 11)


def test_multi_line_range_omits_start_character_when_it_is_zero():
    occ = {"TypedRange": {"MultiLineRange": {
        "start_line": 9, "end_line": 21, "end_character": 1,
    }}}
    assert normalize_range(occ) == (9, 0, 21, 1)


def test_multi_line_range_omits_start_line_when_it_is_zero():
    """A declaration spanning from the file's first line has no `start_line` key."""
    occ = {"TypedRange": {"MultiLineRange": {
        "start_character": 4, "end_line": 21, "end_character": 1,
    }}}
    assert normalize_range(occ) == (0, 4, 21, 1)


def test_multi_line_range_omits_end_character_when_it_is_zero():
    occ = {"TypedRange": {"MultiLineRange": {
        "start_line": 9, "start_character": 4, "end_line": 21,
    }}}
    assert normalize_range(occ) == (9, 4, 21, 0)


def test_legacy_three_element_range_array_is_single_line():
    """[line, start_char, end_char] — no TypedRange wrapper at all."""
    occ = {"range": [5, 2, 9]}
    assert normalize_range(occ) == (5, 2, 5, 9)


def test_legacy_four_element_range_array_is_multi_line():
    """[start_line, start_char, end_line, end_char] — no TypedRange wrapper at all."""
    occ = {"range": [5, 2, 7, 4]}
    assert normalize_range(occ) == (5, 2, 7, 4)


def test_unusable_range_shape_raises():
    with pytest.raises(ValueError, match="no usable range"):
        normalize_range({"range": [1]})


# ---------------------------------------------- contains: half-open boundary semantics


def test_single_line_start_boundary_is_inclusive():
    assert contains(5, 10, 5, 20, line=5, col=10) is True


def test_single_line_end_boundary_is_exclusive():
    assert contains(5, 10, 5, 20, line=5, col=20) is False


def test_single_line_one_before_end_is_inside():
    assert contains(5, 10, 5, 20, line=5, col=19) is True


def test_single_line_one_before_start_is_outside():
    assert contains(5, 10, 5, 20, line=5, col=9) is False


def test_single_line_wrong_line_is_outside():
    assert contains(5, 10, 5, 20, line=6, col=15) is False


def test_multi_line_start_line_before_start_char_is_outside():
    assert contains(5, 10, 8, 3, line=5, col=9) is False


def test_multi_line_start_line_at_start_char_is_inside():
    assert contains(5, 10, 8, 3, line=5, col=10) is True


def test_multi_line_end_line_at_end_char_is_outside():
    assert contains(5, 10, 8, 3, line=8, col=3) is False


def test_multi_line_end_line_before_end_char_is_inside():
    assert contains(5, 10, 8, 3, line=8, col=2) is True


def test_multi_line_interior_line_any_column_is_inside():
    assert contains(5, 10, 8, 3, line=6, col=0) is True
    assert contains(5, 10, 8, 3, line=7, col=9999) is True


def test_multi_line_outside_line_range_is_outside():
    assert contains(5, 10, 8, 3, line=4, col=0) is False
    assert contains(5, 10, 8, 3, line=9, col=0) is False


# ---------------------------------------------- role_label


def test_role_label_definition_bit_set():
    assert role_label(DEFINITION) == "definition"


def test_role_label_definition_bit_combined_with_other_bits():
    assert role_label(DEFINITION | 0x8) == "definition"


def test_role_label_no_definition_bit_is_reference():
    assert role_label(0) == "reference"
    assert role_label(0x8) == "reference"


# ---------------------------------------------- iter_occurrences


def test_iter_occurrences_skips_entries_without_a_symbol():
    index = {
        "documents": [
            {
                "relative_path": "a/Foo.java",
                "occurrences": [
                    {"TypedRange": {"SingleLineRange": {"line": 0, "start_character": 0, "end_character": 3}}},
                    {"TypedRange": {"SingleLineRange": {"line": 1, "start_character": 0, "end_character": 3}},
                     "symbol": "foo"},
                ],
            }
        ]
    }
    results = list(iter_occurrences(index))
    assert len(results) == 1
    assert results[0][1]["symbol"] == "foo"


def test_iter_occurrences_yields_path_for_each_document():
    index = {
        "documents": [
            {"relative_path": "a/Foo.java", "occurrences": [{"symbol": "foo", "range": [0, 0, 1]}]},
            {"relative_path": "b/Bar.java", "occurrences": [{"symbol": "bar", "range": [0, 0, 1]}]},
        ]
    }
    paths = [path for path, _ in iter_occurrences(index)]
    assert paths == ["a/Foo.java", "b/Bar.java"]


# ---------------------------------------------- cmd_at / cmd_symbol


def _index_with_definition_and_reference():
    definition = {
        "range": [40, 14, 33],
        "symbol": "scip-java maven . . org/example/Service#refresh().",
        "symbol_roles": DEFINITION,
    }
    reference = {
        "range": [19, 12, 19],
        "symbol": "scip-java maven . . org/example/Service#refresh().",
    }
    return {
        "documents": [
            {"relative_path": "src/main/java/org/example/Service.java", "occurrences": [definition]},
            {"relative_path": "src/test/java/org/example/ServiceTest.java", "occurrences": [reference]},
        ]
    }


def test_cmd_at_finds_definition_and_reference(capsys):
    index = _index_with_definition_and_reference()
    cmd_at(index, "Service.java", 41, 15)
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "src/main/java/org/example/Service.java:41:15\tdefinition\t"
        "scip-java maven . . org/example/Service#refresh().",
        "src/test/java/org/example/ServiceTest.java:20:13\treference\t"
        "scip-java maven . . org/example/Service#refresh().",
    ]


def test_cmd_at_no_symbol_at_location_exits_nonzero(capsys):
    index = _index_with_definition_and_reference()
    with pytest.raises(SystemExit) as exc_info:
        cmd_at(index, "Service.java", 1, 1)
    assert exc_info.value.code == 1
    assert "No symbol found" in capsys.readouterr().err


def test_cmd_symbol_matches_by_substring(capsys):
    index = _index_with_definition_and_reference()
    cmd_symbol(index, "refresh")
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    assert all("refresh" in line for line in out)


def test_cmd_symbol_no_match_exits_nonzero(capsys):
    index = _index_with_definition_and_reference()
    with pytest.raises(SystemExit) as exc_info:
        cmd_symbol(index, "nonexistent-substring")
    assert exc_info.value.code == 1
    assert "No occurrences matching" in capsys.readouterr().err


# ---------------------------------------------- load_index


def test_load_index_reads_json_suffix_directly(tmp_path):
    payload = {"documents": []}
    json_path = tmp_path / "index.json"
    json_path.write_text(json.dumps(payload))
    assert load_index(json_path) == payload


def test_load_index_regenerates_cache_when_missing(tmp_path, monkeypatch):
    scip_path = tmp_path / "index.scip"
    scip_path.write_bytes(b"fake-scip-binary-content")

    captured_cmd = {}

    def fake_run(cmd, **_kwargs):
        captured_cmd["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"documents": []}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = load_index(scip_path)

    assert result == {"documents": []}
    assert captured_cmd["cmd"] == ["scip", "print", "--json", str(scip_path)]
    assert (tmp_path / "index.json").exists()


def test_load_index_reuses_fresh_json_cache_without_regenerating(tmp_path, monkeypatch):
    scip_path = tmp_path / "index.scip"
    scip_path.write_bytes(b"fake-scip-binary-content")
    json_path = tmp_path / "index.json"
    json_path.write_text(json.dumps({"documents": ["cached"]}))

    # Cache newer than the .scip file it was generated from.
    import os
    scip_mtime = scip_path.stat().st_mtime
    os.utime(json_path, (scip_mtime + 10, scip_mtime + 10))

    def fail_if_called(_cmd, **_kwargs):
        raise AssertionError("subprocess.run should not be called when the cache is fresh")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    assert load_index(scip_path) == {"documents": ["cached"]}


def test_load_index_regenerates_stale_json_cache(tmp_path, monkeypatch):
    import os

    scip_path = tmp_path / "index.scip"
    scip_path.write_bytes(b"fake-scip-binary-content")
    json_path = tmp_path / "index.json"
    json_path.write_text(json.dumps({"documents": ["stale"]}))

    # Cache older than the .scip file it was supposedly generated from.
    scip_mtime = scip_path.stat().st_mtime
    os.utime(json_path, (scip_mtime - 10, scip_mtime - 10))

    def fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"documents": ["fresh"]}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert load_index(scip_path) == {"documents": ["fresh"]}
