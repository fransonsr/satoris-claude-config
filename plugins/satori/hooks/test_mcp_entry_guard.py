"""Tests for mcp_entry_guard.py.

This hook runs on every session start, so the tests that matter most are the ones asserting it stays
silent when it cannot tell, never raises, and never prints a secret. A SessionStart hook that crashes,
chatters, or leaks a token into the transcript is worse than no guard at all.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import mcp_entry_guard
from mcp_entry_guard import _run, advisory, check, main

SCRIPT = Path(__file__).with_name("mcp_entry_guard.py")
SHARED = {"type": "http", "url": "http://127.0.0.1:8090/mcp"}
EXPECTED = {"sonarqube": SHARED}


def write_json(path, data):
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Point the hook at throwaway copies of ~/.claude.json and the expected-servers file."""
    claude = tmp_path / "claude.json"
    expected = tmp_path / "expected.json"
    monkeypatch.setenv("SATORI_CLAUDE_JSON", str(claude))
    monkeypatch.setenv("SATORI_EXPECTED_MCP", str(expected))
    return claude, expected


# ---- check(): what counts as a finding ----

def test_a_matching_entry_has_no_findings():
    servers = {"sonarqube": {**SHARED, "headers": {"Authorization": "Bearer x"}}}

    assert check(EXPECTED, servers) == []


def test_a_missing_server_is_a_finding_that_names_it():
    findings = check(EXPECTED, {})

    assert [name for name, _ in findings] == ["sonarqube"]
    assert "not defined" in findings[0][1]


def test_a_stdio_entry_where_http_is_expected_names_the_command():
    servers = {"sonarqube": {"command": "sonar", "args": ["run", "mcp"]}}

    ((name, what),) = check(EXPECTED, servers)

    assert name == "sonarqube"
    assert "stdio" in what
    assert "sonar" in what


def test_a_matching_type_with_a_different_url_is_a_finding():
    servers = {"sonarqube": {"type": "http", "url": "http://127.0.0.1:8080/mcp"}}

    ((_, what),) = check(EXPECTED, servers)

    assert "8080" in what


def test_a_missing_url_is_a_finding_rather_than_an_error():
    ((_, what),) = check(EXPECTED, {"sonarqube": {"type": "http"}})

    assert "url" in what


def test_a_type_mismatch_is_a_finding_even_when_no_url_is_expected():
    ((name, what),) = check({"x": {"type": "http"}}, {"x": {"command": "foo"}})

    assert name == "x"
    assert "stdio" in what


def test_the_same_url_under_a_different_type_is_a_finding():
    servers = {"sonarqube": {"type": "sse", "url": SHARED["url"]}}

    ((_, what),) = check(EXPECTED, servers)

    assert "sse" in what


def test_the_url_is_not_compared_when_the_expectation_has_none():
    assert check({"x": {"type": "stdio"}}, {"x": {"command": "foo"}}) == []


def test_servers_with_no_expectation_are_ignored():
    servers = {"sonarqube": SHARED, "atlassian": {"type": "http", "url": "https://example.test"}}

    assert check(EXPECTED, servers) == []


def test_a_non_mapping_entry_is_a_finding_rather_than_an_error():
    ((_, what),) = check(EXPECTED, {"sonarqube": "oops"})

    assert "unreadable" in what


def test_a_malformed_expectation_is_skipped_and_the_others_still_run():
    expected = {"bad": "http", "sonarqube": SHARED}

    findings = check(expected, {})

    assert [name for name, _ in findings] == ["sonarqube"]


def test_a_malformed_url_on_a_drifted_entry_does_not_hide_the_other_findings():
    expected = {"alpha": {"type": "http", "url": "http://x/mcp"}, "beta": {"type": "http"}}
    servers = {"alpha": {"type": "http", "url": "http://[bad/mcp"}}

    findings = check(expected, servers)

    assert [name for name, _ in findings] == ["alpha", "beta"]


def test_a_non_string_type_or_url_in_an_expectation_is_skipped():
    expected = {"bad_type": {"type": 5}, "bad_url": {"type": "http", "url": 123}, "sonarqube": SHARED}

    findings = check(expected, {})

    assert [name for name, _ in findings] == ["sonarqube"]


def test_a_null_entry_is_unreadable_rather_than_missing():
    ((_, what),) = check(EXPECTED, {"sonarqube": None})

    assert "unreadable" in what
    assert "not defined" not in what


def test_a_non_string_command_or_url_is_described_without_error():
    expected = {"a": {"type": "http"}, "b": {"type": "http", "url": "http://x/mcp"}}
    servers = {"a": {"command": 5}, "b": {"type": "http", "url": 123}}

    described = dict(check(expected, servers))

    assert described["a"] == "is stdio"
    assert described["b"] == "is http (no url)"


# ---- advisory(): wording, and never leaking a secret ----

def test_the_advisory_names_the_server_and_what_was_expected():
    text = advisory(check(EXPECTED, {}), EXPECTED)

    assert "sonarqube" in text
    assert "expected http (http://127.0.0.1:8090/mcp)" in text


def test_the_advisory_appends_the_hint_and_restore_command_when_configured():
    expected = {"sonarqube": {**SHARED, "hint": "the CLI rewrites it", "restore": "claude mcp add x"}}

    text = advisory(check(expected, {}), expected)

    assert "the CLI rewrites it" in text
    assert "claude mcp add x" in text


def test_one_advisory_covers_several_findings():
    expected = {"alpha": {"type": "http"}, "beta": {"type": "http"}}

    text = advisory(check(expected, {}), expected)

    assert "alpha" in text
    assert "beta" in text


def test_a_stdio_description_never_includes_args_or_env_values():
    servers = {"sonarqube": {"command": "sonar", "args": ["--token", "SEKRET-ARG"],
                             "env": {"T": "SEKRET-ENV"}}}

    assert "SEKRET" not in advisory(check(EXPECTED, servers), EXPECTED)


def test_an_http_description_never_includes_headers():
    servers = {"sonarqube": {"type": "http", "url": "http://elsewhere:9/mcp",
                             "headers": {"Authorization": "Bearer SEKRET-HDR"}}}

    assert "SEKRET" not in advisory(check(EXPECTED, servers), EXPECTED)


def test_credentials_and_query_in_a_url_are_masked():
    servers = {"sonarqube": {"type": "http",
                             "url": "http://user:SEKRET-USER@other-host:9/mcp?token=SEKRET-Q"}}

    text = advisory(check(EXPECTED, servers), EXPECTED)

    assert "other-host" in text
    assert "SEKRET" not in text


def test_a_malformed_url_is_described_as_unparseable_and_not_echoed():
    servers = {"sonarqube": {"type": "http", "url": "http://user:SEKRET@[bad/mcp"}}

    text = advisory(check(EXPECTED, servers), EXPECTED)

    assert "unparseable" in text
    assert "SEKRET" not in text


def test_a_malformed_expected_url_still_produces_an_advisory():
    expected = {"sonarqube": {"type": "http", "url": "http://[bad/mcp"}}

    text = advisory(check(expected, {}), expected)

    assert "sonarqube" in text
    assert "unparseable" in text


def test_an_invalid_port_is_described_as_unparseable_rather_than_raising():
    servers = {"sonarqube": {"type": "http", "url": "http://host:abc/mcp"}}

    assert "unparseable" in advisory(check(EXPECTED, servers), EXPECTED)


def test_an_ipv6_host_keeps_its_brackets():
    servers = {"sonarqube": {"type": "http", "url": "http://[::1]:9/mcp"}}

    assert "http://[::1]:9/mcp" in advisory(check(EXPECTED, servers), EXPECTED)


def test_an_expectation_without_a_url_does_not_claim_the_server_has_none():
    expected = {"x": {"type": "http"}}

    text = advisory(check(expected, {}), expected)

    assert "expected http." in text
    assert "no url" not in text


# ---- main(): fail open, and what it prints ----

def test_a_matching_config_prints_nothing(files, capsys):
    claude, expected = files
    write_json(expected, EXPECTED)
    write_json(claude, {"mcpServers": {"sonarqube": SHARED}})

    assert main() == 0
    assert capsys.readouterr().out == ""


def test_a_mismatch_prints_one_json_system_message(files, capsys):
    claude, expected = files
    write_json(expected, EXPECTED)
    write_json(claude, {"mcpServers": {"sonarqube": {"command": "sonar", "args": ["run", "mcp"]}}})

    assert main() == 0
    out = capsys.readouterr().out
    assert "stdio" in json.loads(out)["systemMessage"]


def test_a_config_with_no_mcp_servers_key_is_a_finding(files, capsys):
    claude, expected = files
    write_json(expected, EXPECTED)
    write_json(claude, {})

    main()

    assert "not defined" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_no_expected_servers_file_is_silent(files, capsys):
    claude, _ = files
    write_json(claude, {"mcpServers": {}})

    assert _run() == 0
    assert capsys.readouterr().out == ""


def test_a_missing_claude_json_is_silent(files, capsys):
    _, expected = files
    write_json(expected, EXPECTED)

    assert _run() == 0
    assert capsys.readouterr().out == ""


def test_a_corrupt_claude_json_is_silent(files, capsys):
    claude, expected = files
    write_json(expected, EXPECTED)
    claude.write_text("{not json")

    assert _run() == 0
    assert capsys.readouterr().out == ""


def test_a_corrupt_expected_file_is_silent(files, capsys):
    claude, expected = files
    expected.write_text("{not json")
    write_json(claude, {"mcpServers": {}})

    assert _run() == 0
    assert capsys.readouterr().out == ""


def test_an_expected_file_that_is_not_a_mapping_is_silent(files, capsys):
    claude, expected = files
    write_json(expected, ["sonarqube"])
    write_json(claude, {"mcpServers": {}})

    assert _run() == 0
    assert capsys.readouterr().out == ""


def test_an_unexpected_error_is_swallowed(files, capsys, monkeypatch):
    claude, expected = files
    write_json(expected, EXPECTED)
    write_json(claude, {"mcpServers": {}})

    def boom(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp_entry_guard, "check", boom)

    assert main() == 0
    assert capsys.readouterr().out == ""


def test_the_script_run_directly_exits_zero_and_prints_the_advisory(tmp_path):
    claude = write_json(tmp_path / "claude.json", {"mcpServers": {}})
    expected = write_json(tmp_path / "expected.json", EXPECTED)

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=10,
        env={"SATORI_CLAUDE_JSON": str(claude), "SATORI_EXPECTED_MCP": str(expected), "PATH": ""},
    )

    assert proc.returncode == 0
    assert "sonarqube" in json.loads(proc.stdout)["systemMessage"]


def run_script_with_hint(tmp_path, hint, extra_env=None):
    claude = write_json(tmp_path / "claude.json", {"mcpServers": {}})
    expected = write_json(tmp_path / "expected.json", {"x": {"type": "http", "hint": hint}})
    env = {"SATORI_CLAUDE_JSON": str(claude), "SATORI_EXPECTED_MCP": str(expected), "PATH": "",
           **(extra_env or {})}
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, timeout=10, env=env)


def test_a_lone_surrogate_in_the_hint_still_yields_valid_json(tmp_path):
    proc = run_script_with_hint(tmp_path, "bad \ud800 char")

    assert proc.returncode == 0
    assert "x" in json.loads(proc.stdout)["systemMessage"]


def test_a_non_ascii_hint_on_an_ascii_only_stdout_still_yields_valid_json(tmp_path):
    proc = run_script_with_hint(tmp_path, "rewritten — see memory", {"PYTHONIOENCODING": "ascii"})

    assert proc.returncode == 0
    assert "—" in json.loads(proc.stdout)["systemMessage"]
