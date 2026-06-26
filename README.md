# Satori's Claude Code Configuration

Private repository for Claude Code settings, skills, and workflows.

## Contents

- **CLAUDE.md** - Global coding standards and development principles
- **plugins/satori/** - The `satori` plugin — all development workflow skills as peers:
  - `xp-pair` — XP pair programming (navigator + driver workflow)
  - `handoff` — Create comprehensive handoff documents for task continuity
  - `continue` — Resume from a handoff document in a fresh session
  - `pre-pr-audit` — Proactive code quality audit before creating a PR
  - `address-pr-issues` — Systematically address GitHub Copilot and SonarQube PR issues
  - `adversarial-review` — Multi-round parallel adversarial pattern review (invoked by pre-pr-audit and address-pr-issues, or standalone)
- **keybindings.json** - Custom keyboard shortcuts

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
git add plugins/satori/skills/address-pr-issues/
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
├── README.md                        # This file
├── .gitignore                       # Excludes sensitive data
├── install.sh                       # Symlink installation script
├── CLAUDE.md                        # Global user instructions
└── plugins/
    └── satori/
        ├── .claude-plugin/
        │   └── plugin.json
        └── skills/
            ├── xp-pair/             # XP pair programming
            │   ├── SKILL.md
            │   ├── README.md
            │   ├── VALUE_PROPOSITION
            │   └── examples/
            ├── handoff/             # Task handoff documents
            │   ├── SKILL.md
            │   ├── README.md
            │   ├── VALUE_PROPOSITION
            │   ├── CHANGELOG.md
            │   └── templates/
            ├── continue/            # Resume from handoff
            │   └── SKILL.md
            ├── pre-pr-audit/        # Pre-PR code quality audit
            │   ├── SKILL.md
            │   ├── README.md
            │   ├── VALUE_PROPOSITION
            │   ├── evals/
            │   └── scripts/
            │       └── pattern_checker.py
            ├── address-pr-issues/   # PR issue remediation
            │   ├── SKILL.md
            │   ├── README.md
            │   ├── VALUE_PROPOSITION
            │   ├── CHANGELOG.md
            │   ├── QUICK_START.md
            │   ├── examples/
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
            └── adversarial-review/  # Multi-round adversarial pattern review
                ├── SKILL.md
                └── references/
                    └── copilot-review-patterns.md
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
git log --oneline plugins/satori/skills/address-pr-issues/
```

## License

Private repository - not for public distribution.

---

**Last Updated**: 2026-06-26
**Maintained By**: Satori (fransonsr)
