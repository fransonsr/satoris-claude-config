#!/usr/bin/env python3
"""SessionStart guard: warn when an MCP server entry in ~/.claude.json drifts from what is expected.

Some tools own an MCP entry and rewrite it on update. For example, sonarqube-cli re-applies its
stdio `sonar run mcp` entry over a hand-set shared `http` one every time the CLI updates. The
symptom is silent (the server's tools are missing or each session starts its own copy), so this
checks the entry at session start and says so.

What to expect lives in a local file, so nothing machine-specific is in this plugin:

    ~/.claude/expected-mcp-servers.json   (override: SATORI_EXPECTED_MCP)

    {"sonarqube": {"type": "http", "url": "http://127.0.0.1:8090/mcp",
                   "hint": "why it drifts", "restore": "command that fixes it"}}

`type` defaults to stdio, as Claude Code does; `url` is compared only when given; `hint` and
`restore` are optional text appended to the warning. The config read is ~/.claude.json
(override: SATORI_CLAUDE_JSON), top-level `mcpServers` only.

Two design constraints, both because this runs on EVERY session start:

  - It fails open and silent. A missing or unreadable file, a malformed expectation, or any
    unexpected error results in no output and exit 0. A hook that breaks or chatters at session
    start is worse than a missed warning.
  - It never prints a secret. An entry is described by its type, its command (stdio) or its URL
    without credentials or query (http), and never its args, env or headers.

It prints at most one JSON object on stdout, and only when something has drifted.
"""

import json
import os
import pathlib
import sys
from typing import Optional
from urllib.parse import urlsplit

CLAUDE_JSON_ENV = "SATORI_CLAUDE_JSON"
DEFAULT_CLAUDE_JSON = "~/.claude.json"
EXPECTED_ENV = "SATORI_EXPECTED_MCP"
DEFAULT_EXPECTED = "~/.claude/expected-mcp-servers.json"
DEFAULT_TYPE = "stdio"
ADVISORY_NOTES = (("hint", "Why:"), ("restore", "Restore:"))


def _path(env_name: str, default: str) -> pathlib.Path:
    return pathlib.Path(os.environ.get(env_name) or default).expanduser()


def _load_mapping(path: pathlib.Path) -> Optional[dict]:
    """The JSON object in `path`, or None if it is missing, unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _safe_url(url: str) -> str:
    """scheme://host[:port]/path, with the credentials and query dropped."""
    parts = urlsplit(url)
    try:
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        port = ""
    return f"{parts.scheme}://{parts.hostname or ''}{port}{parts.path}"


def _describe(entry) -> str:
    """What an entry is, without its args, env or headers: those hold secrets."""
    if not isinstance(entry, dict):
        return "an unreadable entry"
    kind = entry.get("type", DEFAULT_TYPE)
    if kind == DEFAULT_TYPE:
        command = entry.get("command")
        return f"stdio (command: {command})" if isinstance(command, str) else "stdio"
    url = entry.get("url")
    return f"{kind} ({_safe_url(url)})" if isinstance(url, str) else f"{kind} (no url)"


def _matches(want: dict, have) -> bool:
    if not isinstance(have, dict):
        return False
    if have.get("type", DEFAULT_TYPE) != want.get("type", DEFAULT_TYPE):
        return False
    return "url" not in want or have.get("url") == want["url"]


def check(expected: dict, servers: dict) -> list:
    """(name, what) for each expected server that is missing or different. Malformed
    expectations are skipped so one bad entry cannot hide the others."""
    findings = []
    for name, want in expected.items():
        if not isinstance(want, dict):
            continue
        have = servers.get(name)
        if have is None:
            findings.append((name, "is not defined"))
        elif not _matches(want, have):
            findings.append((name, f"is {_describe(have)}"))
    return findings


def advisory(findings: list, expected: dict) -> str:
    lines = []
    for name, what in findings:
        want = expected[name]
        line = f"MCP server '{name}' in ~/.claude.json {what}; expected {_describe(want)}."
        for key, label in ADVISORY_NOTES:
            if isinstance(want.get(key), str):
                line += f" {label} {want[key]}"
        lines.append(line)
    return "\n".join(lines)


def _run() -> int:
    expected = _load_mapping(_path(EXPECTED_ENV, DEFAULT_EXPECTED))
    config = _load_mapping(_path(CLAUDE_JSON_ENV, DEFAULT_CLAUDE_JSON))
    if not expected or config is None:
        return 0
    servers = config.get("mcpServers")
    findings = check(expected, servers if isinstance(servers, dict) else {})
    if findings:
        json.dump({"systemMessage": advisory(findings, expected)}, sys.stdout, ensure_ascii=False)
    return 0


def main() -> int:
    try:
        return _run()
    except Exception:
        # Fail open and silent: this runs at session start, where breaking the session costs far
        # more than a skipped warning.
        return 0


if __name__ == "__main__":
    sys.exit(main())
