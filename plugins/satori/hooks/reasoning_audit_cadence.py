#!/usr/bin/env python3
"""SessionStart hook: advise when a /satori:reasoning-audit pass is due.

The audit skill is a rule — it runs when someone remembers to invoke it. This
hook is the mechanism half: it tracks how many satori plugin-version bumps have
landed since the last recorded audit pass and prints one advisory when that
count crosses a threshold. Drift, not the calendar, is the trigger, so it fires
in proportion to how much has actually changed.

Two design constraints, both because this runs on EVERY session start:

  - It fails open and silent. Any unreadable manifest, missing state file, or
    unexpected error results in no output and exit 0. A hook that breaks or
    chatters at session start is worse than a missed advisory.
  - It prints at most one JSON object on stdout, and only when a pass is due.
    Silence is the normal case.

Recording a pass (invoked by the skill itself once an audit completes):

    python3 reasoning_audit_cadence.py --record

State lives at ~/.claude/satori-reasoning-audit.state, overridable with
SATORI_AUDIT_STATE for tests.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
from typing import Optional

DEFAULT_THRESHOLD = 5
STATE_ENV = "SATORI_AUDIT_STATE"
DEFAULT_STATE = "~/.claude/satori-reasoning-audit.state"

# A minor or major bump is a larger change than any run of patch bumps; scoring it
# at the threshold means it always triggers rather than being undercounted.
MAJOR_MINOR_WEIGHT = DEFAULT_THRESHOLD


def parse_version(text) -> Optional[tuple]:
    """Parse 'MAJOR.MINOR.PATCH' into a tuple, or None if it isn't one."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def bumps_since(last: str, current: str) -> Optional[int]:
    """How many version bumps separate last from current, or None if unparseable."""
    old, new = parse_version(last), parse_version(current)
    if old is None or new is None:
        return None
    if new[:2] != old[:2]:
        return max(MAJOR_MINOR_WEIGHT, DEFAULT_THRESHOLD)
    return max(0, new[2] - old[2])


def state_path() -> pathlib.Path:
    override = os.environ.get(STATE_ENV)
    if override:
        return pathlib.Path(override)
    return pathlib.Path(DEFAULT_STATE).expanduser()


def read_state(path: pathlib.Path) -> dict:
    """Read the recorded pass, or {} if absent or corrupt.

    A corrupt state file reads as "never audited" rather than as an error, so a
    garbled file self-heals on the next recorded pass instead of silently
    disabling the cadence forever.
    """
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_pass(path: pathlib.Path, version: str, today: datetime.date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "date": today.isoformat()}))


def read_current_version(plugin_root: pathlib.Path) -> Optional[str]:
    """Read the satori plugin's declared version, or None if unreadable."""
    try:
        data = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def advisory_for(state: dict, current: Optional[str], threshold: int) -> Optional[str]:
    """The advisory to print, or None to stay silent."""
    if current is None:
        return None

    recorded = state.get("version")
    if recorded is None:
        return _message(None, current, None)

    bumps = bumps_since(recorded, current)
    if bumps is None:
        return _message(None, current, None)
    if bumps < threshold:
        return None
    return _message(recorded, current, bumps)


def _message(recorded: Optional[str], current: str, bumps: Optional[int]) -> str:
    if recorded is None:
        since = "never recorded a pass"
    else:
        since = f"{bumps} version bump(s) since the last pass (v{recorded})"
    return (f"🔍 satori is at v{current} and {since} — a /satori:reasoning-audit pass is due. "
            "It is read-only: it reports stale thresholds, unresolvable citations, expired "
            "'Verified' dates, and unreferenced scripts, and never edits the target.")


def main(argv=None) -> int:
    try:
        return _run(argv)
    except Exception:
        # Fail open and silent: this runs at session start, where breaking the
        # session costs far more than a skipped advisory.
        return 0


def _run(argv) -> int:
    args = _parse_args(argv)
    path = state_path()

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        return 0
    current = read_current_version(pathlib.Path(plugin_root))
    if current is None:
        return 0

    if args.record:
        try:
            record_pass(path, current, datetime.date.today())
        except (OSError, ValueError):
            pass  # nothing to say; a failed record retries next time
        return 0

    message = advisory_for(read_state(path), current, args.threshold)
    if message:
        json.dump({"systemMessage": message}, sys.stdout, ensure_ascii=False)
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="reasoning-audit cadence advisory")
    parser.add_argument("--record", action="store_true",
                        help="record that an audit pass just completed")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"version bumps before advising (default {DEFAULT_THRESHOLD})")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
