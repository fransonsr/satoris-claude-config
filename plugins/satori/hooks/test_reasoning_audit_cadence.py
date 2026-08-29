"""Tests for reasoning_audit_cadence.py.

This hook runs on every session start, so the tests that matter most are the ones
asserting it stays silent and never raises. A SessionStart hook that crashes or
chatters is worse than no cadence signal at all.
"""

import datetime
import json

import pytest

from reasoning_audit_cadence import (
    DEFAULT_THRESHOLD,
    advisory_for,
    bumps_since,
    main,
    read_current_version,
    read_state,
    record_pass,
)

TODAY = datetime.date(2026, 8, 29)


def write_plugin_json(root, version):
    manifest = root / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"name": "satori", "version": version}))
    return root


def write_state(path, version, date="2026-01-01"):
    path.write_text(json.dumps({"version": version, "date": date}))
    return path


# ------------------------------------------------------------- version math


def test_counts_patch_bumps():
    assert bumps_since("1.0.9", "1.0.12") == 3


def test_same_version_is_zero_bumps():
    assert bumps_since("1.0.12", "1.0.12") == 0


def test_a_minor_version_change_counts_as_due_regardless_of_patch():
    """A minor bump is a bigger change than any number of patches; don't undercount it."""
    assert bumps_since("1.0.12", "1.1.0") >= DEFAULT_THRESHOLD


def test_a_major_version_change_counts_as_due():
    assert bumps_since("1.0.12", "2.0.0") >= DEFAULT_THRESHOLD


def test_a_backwards_version_is_not_negative():
    """A downgrade (or a rewritten history) must not produce a negative count."""
    assert bumps_since("1.0.12", "1.0.9") == 0


def test_unparseable_version_returns_none():
    assert bumps_since("not-a-version", "1.0.12") is None
    assert bumps_since("1.0.12", "") is None


# ------------------------------------------------------------------ state


def test_missing_state_reads_as_empty(tmp_path):
    assert read_state(tmp_path / "absent.state") == {}


def test_corrupt_state_reads_as_empty_rather_than_raising(tmp_path):
    path = tmp_path / "corrupt.state"
    path.write_text("{ not json")
    assert read_state(path) == {}


def test_record_pass_then_read_round_trips(tmp_path):
    path = tmp_path / "cadence.state"
    record_pass(path, "1.0.12", TODAY)
    state = read_state(path)
    assert state["version"] == "1.0.12"
    assert state["date"] == "2026-08-29"


def test_record_pass_creates_missing_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "deeper" / "cadence.state"
    record_pass(path, "1.0.12", TODAY)
    assert read_state(path)["version"] == "1.0.12"


# --------------------------------------------------------------- advisory


def test_never_audited_is_due():
    message = advisory_for({}, "1.0.12", DEFAULT_THRESHOLD)
    assert message is not None
    assert "never" in message.lower()


def test_no_bumps_since_last_pass_is_silent():
    assert advisory_for({"version": "1.0.12"}, "1.0.12", DEFAULT_THRESHOLD) is None


def test_below_threshold_is_silent():
    assert advisory_for({"version": "1.0.9"}, "1.0.12", 5) is None


def test_at_threshold_is_due():
    message = advisory_for({"version": "1.0.7"}, "1.0.12", 5)
    assert message is not None
    assert "5" in message


def test_advisory_names_the_command_to_run():
    """A notice the reader cannot act on is noise; name the invocation."""
    message = advisory_for({}, "1.0.12", DEFAULT_THRESHOLD)
    assert "reasoning-audit" in message


def test_corrupt_recorded_version_is_treated_as_never_audited():
    """Self-healing: a garbled state file must not disable the cadence forever."""
    message = advisory_for({"version": "garbage"}, "1.0.12", DEFAULT_THRESHOLD)
    assert message is not None


def test_unknown_current_version_is_silent():
    """Nothing useful to say if we cannot tell what version is installed."""
    assert advisory_for({"version": "1.0.7"}, None, DEFAULT_THRESHOLD) is None


# ------------------------------------------------- reading the plugin manifest


def test_reads_version_from_the_plugin_manifest(tmp_path):
    write_plugin_json(tmp_path, "1.0.12")
    assert read_current_version(tmp_path) == "1.0.12"


def test_missing_manifest_returns_none(tmp_path):
    assert read_current_version(tmp_path) is None


def test_corrupt_manifest_returns_none_rather_than_raising(tmp_path):
    manifest = tmp_path / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{ not json")
    assert read_current_version(tmp_path) is None


# ----------------------------------------------------------------- main


def test_main_emits_a_system_message_when_due(tmp_path, capsys, monkeypatch):
    write_plugin_json(tmp_path, "1.0.12")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(tmp_path / "cadence.state"))

    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "systemMessage" in payload
    assert "reasoning-audit" in payload["systemMessage"]


def test_main_is_silent_when_not_due(tmp_path, capsys, monkeypatch):
    write_plugin_json(tmp_path, "1.0.12")
    state = write_state(tmp_path / "cadence.state", "1.0.12")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(state))

    assert main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_record_writes_state_and_stays_silent(tmp_path, monkeypatch):
    write_plugin_json(tmp_path, "1.0.12")
    state_path = tmp_path / "cadence.state"
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(state_path))

    assert main(["--record"]) == 0
    assert read_state(state_path)["version"] == "1.0.12"


def test_main_stays_silent_and_succeeds_with_no_plugin_root(tmp_path, capsys, monkeypatch):
    """Fail open: a hook that breaks the session is worse than a missed advisory."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(tmp_path / "cadence.state"))

    assert main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_stays_silent_when_state_path_is_unwritable(tmp_path, monkeypatch):
    """--record on an unwritable path must not raise into the session.

    A regular file stands in for the state file's parent directory, so mkdir
    fails with NotADirectoryError.
    """
    write_plugin_json(tmp_path, "1.0.12")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file\n")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(blocker / "cadence.state"))

    assert main(["--record"]) == 0


def test_main_emits_valid_json_only(tmp_path, capsys, monkeypatch):
    """The harness parses stdout; anything non-JSON breaks it."""
    write_plugin_json(tmp_path, "1.0.12")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("SATORI_AUDIT_STATE", str(tmp_path / "cadence.state"))

    main([])
    out = capsys.readouterr().out
    json.loads(out)  # raises if anything extra was printed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
