#!/usr/bin/env bash
# PreCompact hook: blocks AUTO-compaction and reminds the user to checkpoint manually.
#
# Context: hooks are shell commands and CANNOT invoke agentic skills.
# This hook converts silent auto-compaction into a visible decision point.
#
# After being blocked, the user can:
#   1. Run /handoff:continue to checkpoint, then /clear and resume — preserving full fidelity
#   2. Run /compact to compact anyway (the one-word override)
#
# Hook input (stdin JSON):
#   {"session_id":"...","transcript_path":"...","cwd":"...","hook_event_name":"PreCompact","trigger":"auto|manual"}
#
# Block response (stdout + exit 0):
#   {"decision":"block","reason":"..."}
#
# This hook is registered via install.sh with matcher "auto" — it only fires for
# automatic compaction, not explicit /compact commands.

set -euo pipefail

INPUT=$(cat)

# Determine the compaction trigger.
# Use jq if available; fall back to grep for environments without jq.
if command -v jq &>/dev/null; then
  TRIGGER=$(printf '%s' "$INPUT" | jq -r '.trigger // ""')
else
  TRIGGER=$(printf '%s' "$INPUT" | grep -o '"trigger":"[^"]*"' | cut -d'"' -f4 || echo "")
fi

# Respect explicit /compact — only block automatic compaction.
# If the matcher in settings.json is set to "auto", this check is redundant but defensive.
if [[ "$TRIGGER" == "manual" ]]; then
  exit 0
fi

# Block and surface the decision point.
printf '%s\n' '{"decision":"block","reason":"Auto-compaction blocked — your session state would be lossy-summarized. To preserve full fidelity: (1) run /handoff:continue to checkpoint, (2) then /clear, (3) paste: Read ~/.claude/handoff/continue/<slug>-CONTINUATION.md and resume. To compact anyway (lossy): run /compact"}'
