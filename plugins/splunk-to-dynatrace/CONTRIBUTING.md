# Contributing to Splunk-to-Dynatrace Plugin

Thank you for your interest in contributing to the Splunk-to-Dynatrace migration plugin!

## Getting Started

### Prerequisites

- Claude Code CLI or Desktop App
- Familiarity with SLF4J/Logback logging frameworks
- Basic understanding of Splunk and Dynatrace observability platforms
- Python 3.8+ (for skill scripts)
- Java 11+ (for testing against Java codebases)

### Repository Structure

```
splunk-to-dynatrace/
├── .claude-plugin/
│   └── plugin.json          # Plugin metadata
├── skills/
│   ├── analyze/             # Log analysis skill
│   ├── choose-approach/     # Migration planning skill
│   ├── convert-logs/        # Log conversion skill
│   ├── migrate/             # Full orchestration skill
│   ├── setup-logback/       # Configuration generation skill
│   └── validate-dashboards/ # Dashboard validation skill
├── references/
│   └── familysearch-observability-standards.md
├── README.md                # User-facing documentation
├── FUTURE_ENHANCEMENTS.md   # Feature roadmap
└── CONTRIBUTING.md          # This file
```

## How to Contribute

### Reporting Issues

If you encounter a bug or have a feature request:

1. Check [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) to see if it's already planned
2. Search existing issues (if repository is public)
3. Create a new issue with:
   - Clear description of the problem or enhancement
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Use case and user value (for enhancements)
   - Example code or logs (if applicable)

### Suggesting Enhancements

See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for planned features and how to suggest new ones.

**Enhancement Proposal Template**:

```markdown
## Enhancement: [Name]

**User Value**: [Why this matters, who benefits]

**Use Case**: [Specific scenario where this helps]

**Proposed Solution**: [How you envision this working]

**Alternatives Considered**: [Other approaches evaluated]

**Dependencies**: [What this requires or blocks]

**Estimated Effort**: [Rough guess: days/weeks]
```

### Contributing Code

#### Development Workflow

1. **Fork and Clone** (if public repository)
2. **Create Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Changes**:
   - Follow skill development guidelines (see below)
   - Update documentation (README.md, skill SKILL.md)
   - Add examples if applicable

4. **Test Your Changes**:
   - Test skill on sample codebase
   - Verify skill triggers appropriately
   - Check for edge cases

5. **Commit**:
   ```bash
   git commit -m "feat: Add X feature

   - Detailed description
   - Why this change is needed
   - Any breaking changes"
   ```

6. **Submit Pull Request**:
   - Reference related issues
   - Describe what changed and why
   - Include testing notes

#### Skill Development Guidelines

**Skill Structure**:

```
skills/your-skill/
├── SKILL.md              # Required: Skill documentation
├── scripts/              # Optional: Executable scripts
│   └── helper.py
├── references/           # Optional: Reference documents
│   └── patterns.md
└── evals/                # Optional: Test cases
    └── evals.json
```

**SKILL.md Frontmatter** (Required):

```yaml
---
name: your-skill
description: What this skill does and when to use it (100-200 words). Be specific about triggering phrases and contexts. Include "when to use" guidance here, not in body.
---
```

**Documentation Best Practices**:

1. **Progressive Disclosure**: Keep SKILL.md under 500 lines. Move detailed content to references.
2. **Clear Triggering**: Include triggering phrases in description (helps Claude know when to invoke)
3. **Examples**: Show concrete input/output examples
4. **Error Handling**: Document failure modes and recovery
5. **Dependencies**: List required tools, files, or context

**Script Guidelines**:

- Python 3.8+ compatible
- Include shebang: `#!/usr/bin/env python3`
- Executable: `chmod +x script.py`
- Docstrings for functions/classes
- Error handling with meaningful messages
- Accept arguments via `sys.argv` or argparse

**Testing Your Skill**:

1. Create test cases in `skills/your-skill/evals/evals.json`:
   ```json
   {
     "skill_name": "your-skill",
     "evals": [
       {
         "id": 1,
         "prompt": "Test case prompt",
         "expected_output": "What should happen",
         "files": []
       }
     ]
   }
   ```

2. Test manually:
   ```bash
   # In Claude Code session
   /splunk-to-dynatrace:your-skill [args]
   ```

3. Verify skill triggers on appropriate prompts

### Documentation Updates

Documentation improvements are always welcome:

- Clarify confusing sections
- Add examples
- Fix typos or grammatical errors
- Improve organization

**Documentation Standards**:
- Use GitHub-flavored Markdown
- Include code examples with syntax highlighting
- Use relative links for cross-references
- Keep line length under 120 characters

### Code Style

**Python**:
- PEP 8 style guide
- Type hints where helpful
- Descriptive variable names
- Functions < 50 lines

**Markdown**:
- ATX-style headers (`#` not underlines)
- Fenced code blocks with language tags
- Consistent bullet styles (- not *)

**Commit Messages**:
- Format: `type(scope): subject`
- Types: feat, fix, docs, refactor, test, chore
- Subject: imperative mood, lowercase, no period
- Body: explain why, not what

Examples:
```
feat(analyze): Add cardinality detection for metrics conversion

Detects high-cardinality fields before metrics conversion to prevent
Micrometer explosion. Uses simple heuristics (field name patterns, data types).

Closes #42
```

```
docs: Update README with session naming best practices

Clarifies orchestration vs. execution session usage and naming conventions.
Addresses user feedback from GOFR migration.
```

## Development Setup

### Local Testing

1. **Clone repository**:
   ```bash
   git clone <repo-url>
   cd satoris-claude-config/plugins/splunk-to-dynatrace
   ```

2. **Test skills locally**:
   ```bash
   # In Claude Code session, reference local path
   /splunk-to-dynatrace:analyze
   ```

3. **Iterate on changes**:
   - Edit SKILL.md or scripts
   - Test in Claude Code session
   - Verify behavior matches expectations

### Testing Against Sample Codebases

Create test fixtures in `skills/your-skill/test-fixtures/`:

```
test-fixtures/
├── sample-java-app/
│   └── src/main/java/...
└── expected-outputs/
    └── analysis-report.md
```

## Release Process

(For maintainers)

1. **Version Bump**: Update version in `.claude-plugin/plugin.json`
2. **Update CHANGELOG**: Document changes since last release
3. **Tag Release**: `git tag v1.1.0`
4. **Package**: Create distribution package (exclude workspace, cache)
5. **Publish**: Push to plugin registry or distribution channel

## Questions?

- Review [README.md](README.md) for plugin usage
- Check [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for planned features
- Contact: FamilySearch Engineering - SATORIS Team

## License

© 2026 by Intellectual Reserve, Inc. All rights reserved.

By contributing, you agree that your contributions will be licensed under the same terms as this project.
