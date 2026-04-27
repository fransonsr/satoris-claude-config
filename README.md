# Satori's Claude Code Configuration

Private repository for Claude Code settings, skills, and workflows.

## Contents

- **CLAUDE.md** - Global coding standards and development principles
- **skills/** - Custom Claude Code skills
  - `address-pr-issues/` - PR workflow automation (GitHub Copilot + SonarQube)
  - `pre-pr-audit/` - Proactive code quality checks
  - `xp-pair/` - XP pair programming workflow
  - `handoff/` - Task handoff documentation
- **keybindings.json** - Custom keyboard shortcuts (if any)

## Installation

### First Time Setup

```bash
cd ~/github
git clone git@github.com:yourusername/satoris-claude-config.git
cd satoris-claude-config
./install.sh
```

This creates symlinks from `~/.claude/` to this repository.

### Updating After Changes

```bash
cd ~/github/satoris-claude-config
git pull
./install.sh  # Re-creates symlinks if needed
```

## Making Changes

### After Improving a Skill

```bash
cd ~/github/satoris-claude-config
git add skills/address-pr-issues/
git commit -m "feat(address-pr-issues): Add bulk thread resolution"
git push
```

### After Updating Global Standards

```bash
cd ~/github/satoris-claude-config
git add CLAUDE.md
git commit -m "docs: Add pre-commit quality checklist"
git push
```

## Directory Structure

```
satoris-claude-config/
├── README.md                     # This file
├── .gitignore                    # Excludes sensitive data
├── install.sh                    # Symlink installation script
├── CLAUDE.md                     # Global user instructions
└── skills/
    ├── address-pr-issues/        # PR workflow automation
    │   ├── SKILL.md
    │   ├── CHANGELOG.md
    │   ├── README.md
    │   └── scripts/
    │       ├── lib/
    │       │   ├── github-api.sh
    │       │   └── sonar-api.sh
    │       ├── init-pr-state.sh
    │       ├── fetch-pr-threads.sh
    │       ├── check-sonar-quality-gate.sh
    │       ├── resolve-thread.sh
    │       ├── resolve-threads-bulk.sh
    │       └── commit-pr-fixes.sh
    ├── pre-pr-audit/
    ├── xp-pair/
    └── handoff/
```

## What's NOT Included

- `~/.claude/projects/` - Project-specific memory (not portable)
- `~/.claude/plugins/cache/` - Downloaded plugins (regenerate)
- `~/.claude/handoff/` - Session-specific handoff docs (transient)
- Tokens, credentials, API keys

## Multi-Machine Sync

On your second machine:

```bash
cd ~/github
git clone git@github.com:yourusername/satoris-claude-config.git
cd satoris-claude-config
./install.sh
```

Your skills and standards are now identical across machines!

## Backup Strategy

This repository IS your backup. If you lose your laptop:

1. Get new machine
2. Install Claude Code
3. Clone this repo
4. Run `./install.sh`
5. Your skills are restored

## Version History

See git log for full history of skill evolution:

```bash
git log --oneline skills/address-pr-issues/
```

## License

Private repository - not for public distribution.

---

**Last Updated**: 2026-04-27  
**Maintained By**: Satori (fransonsr)
