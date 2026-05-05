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
echo ""
echo "To update after making changes:"
echo "  cd $REPO_DIR"
echo "  git add ."
echo "  git commit -m 'description'"
echo "  git push"
echo ""
