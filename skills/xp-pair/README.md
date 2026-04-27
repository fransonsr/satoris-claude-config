# XP Pair Programming Skill

User-level skill for XP pair programming with navigator (you) and driver (subagent).

## Usage

In any repository/session:

```
/xp-pair Implement the cleanup job with multi-prefix support
```

Or let Claude invoke it automatically when you say:
```
"Let's use XP pairing to implement the authentication module"
```

## What Gets Created

1. **Team**: Named like `feature-name-dev`
2. **Tasks**: With explicit acceptance criteria
3. **Driver subagent**: Follows TDD, reports after each test
4. **Navigator (you)**: Reviews code, makes decisions, guides design

## How It Works

1. **Driver implements** following RED-GREEN-REFACTOR
2. **Driver reports** after each test cycle
3. **Navigator reviews** and approves or discusses
4. **Repeat** until feature complete

## Communication Protocol

**Driver → Navigator (after each test):**
```
Test complete: shouldValidateBucket
- RED: Test failed as expected
- GREEN: Added validation
- REFACTOR: Extracted helper method
- Tests passing: 5/18
Ready for next test or review.
```

**Navigator → Driver (response):**
```
"Looks good, continue"
"Wait, let's review that refactoring"
"Approved, move to next test"
```

## Tracking Improvements

The skill file includes a **Future Improvements** section where you can track:
- Version 1.1 candidate improvements
- Version 1.2 future ideas
- Learnings from each session

**To add a learning:**

1. Edit `~/.claude/skills/xp-pair/SKILL.md`
2. Find the "Learnings from Sessions" section
3. Add a dated note:

```markdown
**2026-02-25 - Auth Module:**
- ✅ Architecture discussion before coding worked great
- 📝 Driver needed more guidance on test naming
- 📝 Consider: Provide test naming guidelines upfront
```

## Improving the Skill

### Quick Fix (Edit SKILL.md)

```bash
# Open in your editor
code ~/.claude/skills/xp-pair/SKILL.md

# Or with Claude
"Please update the xp-pair skill to include test naming guidelines"
```

### Version Control (Recommended)

Create a git repo for your skills:

```bash
cd ~/.claude/skills
git init
git add xp-pair/
git commit -m "Initial XP pair skill"

# After improvements
git commit -am "Add test naming guidelines"
```

This gives you:
- ✅ Version history
- ✅ Ability to revert changes
- ✅ Share skills across machines

### Iterate Based on Usage

After each pairing session:
1. Add learnings to "Learnings from Sessions"
2. Move validated improvements from "Candidate" to skill instructions
3. Add new ideas to "Future Ideas"

Example evolution:

**Session 1:** Basic per-test reporting works
**Session 2:** Architecture discussion before coding improves quality → add to instructions
**Session 3:** Test naming inconsistent → add guidelines
**Session 4:** Idle notifications annoying → note for future fix

## Sharing

**With your team:**
```bash
# From your machine
cp -r ~/.claude/skills/xp-pair ~/shared-skills/

# Teammates install
cp -r ~/shared-skills/xp-pair ~/.claude/skills/
```

**Via git:**
```bash
# Your skills repo
cd ~/.claude/skills
git remote add origin git@github.com:yourname/claude-skills.git
git push

# Teammates clone
git clone git@github.com:yourname/claude-skills.git ~/.claude/skills
```

**As a plugin** (advanced):
1. Create plugin structure following [plugin guide](https://code.claude.com/docs/en/plugins.md)
2. Publish to plugin marketplace
3. Others install with `/install your-plugin`

## File Locations

```
~/.claude/skills/xp-pair/
├── SKILL.md          # Main skill definition (instructions for Claude)
├── README.md         # This file (documentation for you)
└── examples/         # (optional) Example sessions
```

## When to Use vs Not Use

**Use for:**
- Complex features needing design oversight
- Teaching/learning TDD
- High-risk code
- Unclear requirements

**Skip for:**
- Simple CRUD
- Bug fixes
- Documentation
- Time-sensitive work

## Technical Details

**Token usage:** ~200 tokens/test × 18 tests = ~3,600 tokens for communication (acceptable for quality)

**Roles:**
- Navigator: Main agent (has full context)
- Driver: Subagent `general-purpose` type (has Edit, Write, Read, Bash tools)

**Team lifecycle:**
- TeamCreate → spawn driver → implement → review → shutdown driver → TeamDelete
