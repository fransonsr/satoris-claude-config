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
(override: SATORI_CLAUDE_JSON), top-level `mcpServers` only. Both overrides exist for tests, and the
warning always names ~/.claude.json.

Two design constraints, both because this runs on EVERY session start:

  - It fails open and silent. A missing, unreadable or corrupt file, an expectations file that is
    not an object, or any unexpected error results in no output and exit 0. An expectation entry
    that is not a usable mapping (not an object, or a `type` or `url` that is not a string) is
    skipped so it cannot hide the others. A hook that breaks or chatters at session start is worse
    than a missed warning.
  - It limits what it prints. Args, env, headers, and URL credentials and query strings are never
    printed. What is printed, as written, is the type, the stdio command string, the URL scheme,
    host, port and path, and your own hint and restore text, so none of those may hold a secret. A
    URL that cannot be parsed is replaced by a placeholder, not echoed.

It prints at most one JSON object on stdout, and only when something has drifted. The object is
serialized before it is written, ASCII-escaped, so an encoding problem cannot leave half of it on
stdout.

Known limits: it reads the default ~/.claude.json only (not $CLAUDE_CONFIG_DIR/.claude.json), checks
user-scope `mcpServers` only (not project, .mcp.json or plugin-provided servers), and relies on
python3 being on PATH, as the sibling hook does.
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
UNPARSEABLE_URL = "an unparseable url"
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
    """scheme://host[:port]/path, with the credentials and query dropped. A URL that cannot be
    parsed becomes a placeholder, never the raw string, which may hold credentials."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return UNPARSEABLE_URL
    return f"{parts.scheme}://{host}{port}{parts.path}"


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


def _describe_expected(want: dict) -> str:
    """What an expectation requires: its type, and its url only when it constrains one."""
    kind = want.get("type", DEFAULT_TYPE)
    url = want.get("url")
    return f"{kind} ({_safe_url(url)})" if url is not None else kind


def _is_usable(want) -> bool:
    """An expectation is a mapping whose type and url, when present, are strings."""
    return (isinstance(want, dict)
            and isinstance(want.get("type", DEFAULT_TYPE), str)
            and isinstance(want.get("url", ""), str))


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
        if not _is_usable(want):
            continue
        if name not in servers:
            findings.append((name, "is not defined"))
        elif not _matches(want, servers[name]):
            findings.append((name, f"is {_describe(servers[name])}"))
    return findings


def advisory(findings: list, expected: dict) -> str:
    lines = []
    for name, what in findings:
        want = expected[name]
        line = f"MCP server '{name}' in ~/.claude.json {what}; expected {_describe_expected(want)}."
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
        # Serialize first and write once: an encoding problem then fails before any byte is
        # written, and the default ASCII escaping is safe for any stdout encoding.
        sys.stdout.write(json.dumps({"systemMessage": advisory(findings, expected)}))
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
