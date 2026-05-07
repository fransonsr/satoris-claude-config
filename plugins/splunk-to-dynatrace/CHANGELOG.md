# Changelog

All notable changes to the Splunk-to-Dynatrace migration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-06

### Added

#### Skills
- **analyze**: Analyzes codebase logging patterns against FamilySearch Observability Standards
  - Scans for SLF4J, Log4j, Lombok log statements
  - Identifies DELETE candidates (logs Dynatrace auto-captures)
  - Detects incorrect log levels (INFO → DEBUG violations)
  - Suggests METRIC conversions (counters, timers)
  - Analyzes field naming trade-offs (three strategies)
  - Generates hierarchical reports with progressive disclosure
  - Includes LSP semantic analysis via bundled Python script
  - Adapts to codebase size (<100, 100-500, 500+ logs)

- **choose-approach**: Interactive migration planning questionnaire
  - 7 questions to understand team context (dashboards, urgency, quality, tests, bandwidth, risk)
  - Scoring algorithm recommends approach (Comprehensive, Quick, Hybrid, Progressive)
  - Generates personalized migration plan with phased workflow
  - Includes effort estimates and risk assessment
  - Teaches Claude Code best practices (session management, task tracking, handoffs, git hygiene)

- **convert-logs**: Converts traditional logs to SLF4J fluent API with structured fields
  - Applies FamilySearch Observability Standards transformations
  - Supports three field naming strategies (standardize, defer, hybrid)
  - Deletes logs Dynatrace auto-captures (with explanation comments)
  - Converts counter/timing logs to Micrometer metrics with cardinality validation
  - Handles exception logging with setCause() method
  - Adds lambda wrapping and guard clauses for performance
  - Incremental conversion support (full, module-by-module, task-by-task)

- **setup-logback**: Generates logback-spring.xml configuration
  - Profile-based appenders (local, integ, staging, prod, canary)
  - Three-phase migration support (Splunk → Dual → Dynatrace)
  - Business event routing (named logger → separate file)
  - Stack trace filtering per observability standards
  - Rolling policies (time-based, compressed)
  - Updates POM dependencies (logstash-logback-encoder)

- **validate-dashboards**: Validates Splunk dashboards for migration
  - Parses dashboard definitions (JSON, XML, saved searches)
  - Extracts field references from SPL queries
  - Assesses breakage risk (green/yellow/red)
  - Generates required dashboard updates (find/replace, rewrites)
  - Converts SPL queries to Dynatrace DQL equivalents
  - Creates Dynatrace dashboard JSON templates

- **migrate**: Full migration orchestration with approval gates
  - Orchestrates all skills in phased workflow
  - Three modes (full automated, module-by-module, task-by-task)
  - Creates and manages migration task list
  - Generates deployment checklists per phase
  - Handles errors and rollback scenarios
  - Produces final migration report

#### Documentation
- **README.md**: Comprehensive plugin overview
  - Emphasizes flexibility (Comprehensive/Quick/Progressive paths)
  - Shows standalone skill value (not all-or-nothing)
  - Progressive enhancement levels (Level 0-5)
  - Claude Code best practices for multi-phase work
  - Session naming guidance (orchestration vs. execution)

- **FUTURE_ENHANCEMENTS.md**: Feature roadmap with prioritization
  - 10 planned enhancements (dashboard creation, alert migration, query translation, etc.)
  - Priority levels (HIGH/MEDIUM/LOW)
  - Timeline estimates (near/mid/long-term)
  - How to suggest new features

- **CONTRIBUTING.md**: Contributor guidelines
  - Development workflow
  - Skill development best practices
  - Testing guidelines
  - Code style standards

- **CHANGELOG.md**: This file

#### References
- **familysearch-observability-standards.md**: FamilySearch Observability Standards v1.3
  - Log level decision tree
  - Required fields by level (ERROR, WARN, INFO, DEBUG)
  - Standard field naming conventions (dot.notation)
  - DELETE candidates (what Dynatrace auto-captures)

#### Bundled Scripts
- **lsp_inventory.py**: Semantic Java analysis via Language Server Protocol
  - Used by analyze skill for semantic code understanding
  - Detects classes, methods, imports, dependencies

- **anti_patterns.json**: Anti-pattern detection rules
  - Used by analyze skill to detect common logging anti-patterns

### Testing
- End-to-end tested on GOFR service (33 logs across 13 files)
- 11 logs converted (3 LEVEL_CHANGE, 1 METRIC, 7 STRUCTURED)
- All tests passing post-conversion (131 unit tests, 52 integration tests)
- Dashboard validation completed (3 dashboards, 5 queries, all GREEN)
- Full build successful with no regressions

### Learnings from GOFR Migration
- Metrics cardinality validation critical (prevents explosion)
- Hybrid field naming reduces dashboard migration burden
- SimpleMeterRegistry better than mocking for metrics tests
- Test assertions must match structured log format
- Logger API standardization (SLF4J vs Log4j2) should be detected early

## [1.0.1] - 2026-05-07

### Fixed
- **Packaging**: choose-approach skill now properly included in distribution archives
  - Previous v1.0.0 package was missing the choose-approach skill directory
  - All 6 skills now verified present in package

### Changed
- Package size increased slightly (101 KB tar.gz, 117 KB zip) due to choose-approach inclusion

## [Unreleased]

### Planned for v1.1.0
- Dashboard creation assistance (Dynatrace API integration)
- Alert migration from Splunk to Dynatrace
- Query translation tool (standalone SPL to DQL converter)

See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for complete roadmap.

---

## Version History

- **1.0.1** (2026-05-07): Packaging fix - include choose-approach skill
- **1.0.0** (2026-05-06): Initial release with 6 skills, comprehensive documentation, end-to-end testing

[1.0.1]: https://github.com/familysearch/satoris-claude-config/releases/tag/v1.0.1
[1.0.0]: https://github.com/familysearch/satoris-claude-config/releases/tag/v1.0.0
