#!/usr/bin/env bash
# Install script for Satori's Claude Code configuration
# Creates symlinks from ~/.claude/ to this repository

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Installing Satori's Claude Code Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Repository: $REPO_DIR"
echo "Target:     $CLAUDE_DIR"
echo ""

# Ensure ~/.claude directory exists
if [[ ! -d "$CLAUDE_DIR" ]]; then
  echo "⚠️  ~/.claude directory not found. Creating it..."
  mkdir -p "$CLAUDE_DIR"
fi

# Ensure ~/.claude/plugins/marketplaces directory exists
if [[ ! -d "$CLAUDE_DIR/plugins/marketplaces" ]]; then
  mkdir -p "$CLAUDE_DIR/plugins/marketplaces"
fi

# Function to create symlink with backup
create_symlink() {
  local source="$1"
  local target="$2"
  local name="$3"

  if [[ -L "$target" ]]; then
    # Already a symlink - check if it points to correct location
    local current_target
    current_target=$(readlink "$target")
    if [[ "$current_target" == "$source" ]]; then
      echo "  ✓ $name (already linked)"
      return 0
    else
      echo "  ⚠️  $name (re-linking from $current_target)"
      rm "$target"
    fi
  elif [[ -e "$target" ]]; then
    # Exists but not a symlink - back it up
    echo "  📦 $name (backing up existing file)"
    mv "$target" "${target}.backup-$(date +%Y%m%d-%H%M%S)"
  fi

  ln -s "$source" "$target"
  echo "  ✅ $name (linked)"
}

echo "Installing files:"
echo ""

# Install global CLAUDE.md
if [[ -f "$REPO_DIR/CLAUDE.md" ]]; then
  create_symlink "$REPO_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md" "CLAUDE.md"
fi

# Install marketplace (symlink entire repo to marketplaces directory)
create_symlink "$REPO_DIR" "$CLAUDE_DIR/plugins/marketplaces/satoris-claude-config" "marketplace (satoris-claude-config)"

# Install keybindings if present
if [[ -f "$REPO_DIR/keybindings.json" ]]; then
  create_symlink "$REPO_DIR/keybindings.json" "$CLAUDE_DIR/keybindings.json" "keybindings.json"
fi

# Register the handoff:continue PreCompact hook in ~/.claude/settings.json
# This hook blocks AUTO-compaction and reminds the user to run /handoff:continue first.
# Explicit /compact is always the user's one-word override.
HOOK_SCRIPT="$REPO_DIR/plugins/handoff/hooks/precompact-checkpoint-reminder.sh"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"

if [[ -f "$HOOK_SCRIPT" ]]; then
  chmod +x "$HOOK_SCRIPT"

  if command -v jq &>/dev/null; then
    # Create settings.json if it doesn't exist
    if [[ ! -f "$SETTINGS_FILE" ]]; then
      echo '{}' > "$SETTINGS_FILE"
    fi

    # Check if the hook is already registered (avoid duplicates)
    ALREADY_REGISTERED=$(jq -r '
      .hooks.PreCompact[]?.hooks[]?.command // ""
    ' "$SETTINGS_FILE" 2>/dev/null | grep -F "$HOOK_SCRIPT" || true)

    if [[ -z "$ALREADY_REGISTERED" ]]; then
      TMP=$(mktemp)
      jq --arg cmd "$HOOK_SCRIPT" '
        .hooks.PreCompact = ((.hooks.PreCompact // []) + [{
          "matcher": "auto",
          "hooks": [{"type": "command", "command": $cmd}]
        }])
      ' "$SETTINGS_FILE" > "$TMP" && mv "$TMP" "$SETTINGS_FILE"
      echo "  ✅ PreCompact hook (auto-compaction checkpoint reminder)"
    else
      echo "  ✓ PreCompact hook (already registered)"
    fi
  else
    echo "  ⚠️  PreCompact hook: jq not found — add manually to ~/.claude/settings.json"
    echo "     Command: $HOOK_SCRIPT"
    echo "     See plugins/handoff/README.md for the full JSON snippet"
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your Claude Code configuration is now linked to this repository."
echo ""
echo "To verify:"
echo "  ls -la ~/.claude/CLAUDE.md"
echo "  ls -la ~/.claude/plugins/marketplaces/satoris-claude-config"
echo "  cat ~/.claude/settings.json | jq '.hooks'   # PreCompact hook"
echo ""
echo "To update after making changes:"
echo "  cd $REPO_DIR"
echo "  git add ."
echo "  git commit -m 'description'"
echo "  git push"
echo ""
