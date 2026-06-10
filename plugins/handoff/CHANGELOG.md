# Changelog

All notable changes to the Handoff skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.1] - 2026-06-10

### Changed

- **Clarified that Claude memory must NOT be used for inter-agent communication**
  - Added prominent warning in Two-File Approach section
  - Progress document is the only feedback channel back to the orchestrator
  - Memory is for durable cross-project preferences, not task-level progress noise

## [2.0.0] - 2026-05-18

### Changed (BREAKING)

- **Implemented Handoff + Progress pattern for inter-agent communication**
  - Handoff documents now specification-only (immutable)
  - Implementing agents create separate progress document (mutable)
  - Clear separation between "what to build" (handoff) and "how we're building it" (progress)

### Added

- **IMPLEMENTATION-PROGRESS-template.md** - Comprehensive template for progress tracking
  - Architectural decision records (date, rationale, impact, files affected)
  - Progress checklist
  - Current blockers section
  - Questions for orchestrating agent
  - Deviations from original spec
  - Notes & observations

- **Inter-Agent Communication Pattern documentation**
  - Two-file approach (handoff + progress)
  - Responsibility model (orchestrating vs implementing agents)
  - Guidelines on when to update handoff vs progress
  - Examples of appropriate use cases

- **Benefits section** documenting advantages:
  - Clean specification (handoff remains focused)
  - Clear progress tracking (evolution captured separately)
  - Better communication (questions don't pollute spec)
  - Audit trail (decisions captured with context)

### Migration Guide

**No migration required** for existing handoff documents. They remain valid as-is since they are one-time use documents.

**For future handoffs** (v2.0.0+):
1. Orchestrating agent creates handoff document (specification only)
2. Implementing agent reads handoff (does not modify)
3. Implementing agent creates progress document on first session
4. Implementing agent updates progress frequently during work
5. Orchestrating agent reviews progress to answer questions

**Key principle**: Handoff = immutable specification, Progress = mutable implementation tracking

### Why This Change?

Through real-world usage in the java-stack-logging-maven-plugin project, we discovered that implementing agents updating handoff documents caused confusion:
- Mixed immutable specifications with mutable progress
- Unclear what was original spec vs what evolved during implementation
- Example: "Filtered (traditional only)" - was this spec or progress?

The two-file approach solves this by maintaining clean separation of concerns.

## [1.0.0] - 2026-05-12

### Added

- Initial release of handoff skill
- Comprehensive handoff document generation
- Verified context with file:line citations
- Explicit unknowns tracking
- Scope boundaries (what to change vs what NOT to change)
- Decision authority guidelines
- Prior work patterns and anti-patterns
- Known gotchas and constraints
- Testable acceptance criteria
- Test strategy justification
- Iteration expectations
- Skill routing recommendations
- Quality validation (file paths, line numbers)
- Integration with CLAUDE.md and coding standards
