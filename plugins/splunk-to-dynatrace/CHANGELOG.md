# Changelog

All notable changes to the Splunk-to-Dynatrace migration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-05-08

### Added

#### convert-logs skill
- **Automated logger discovery script** (`scripts/discover-loggers-v2.sh`)
  - Generates complete logger inventory BEFORE conversions
  - Outputs JSON with file paths, logger names, declaration lines, reference counts
  - Enables prioritization by reference count (high-impact files first)
  - Query examples for analysis (jq)
  - CSV export for progress tracking
  - 95%+ accuracy with regex-based approach
  - Fast execution (seconds for hundreds of files)

- **Workflow optimization** (Step 1: Generate Logger Inventory - REQUIRED FIRST)
  - Discovery-first approach replaces manual exploration
  - Know complete scope before starting conversions
  - Targeted LSP queries only at known locations
  - 70-90% token reduction vs manual exploration
  - Deterministic, repeatable workflow

- **Comprehensive script documentation** (`scripts/README.md`)
  - Explains reference count behavior (increases after fluent API conversion)
  - Query cookbook for inventory analysis
  - Validation strategies (grep for traditional patterns)
  - Token efficiency calculations
  - Use cases (discovery, prioritization, tracking, validation)

### Changed

#### convert-logs skill
- **Workflow restructure**:
  - Step 1: Generate Logger Inventory (NEW - REQUIRED FIRST)
  - Step 2: Load Context (includes inventory from Step 1)
  - Step 3: Targeted LSP Queries (uses inventory for optimization)
  - Step 4: Identify Conversion Scope (query inventory)
  - Step 5: Perform Conversions (efficient with inventory)

- **LSP discovery moved to Step 3** (optional verification)
  - Primary approach: inventory-first with targeted reads
  - LSP for verification or complex inheritance cases
  - Token efficiency comparison table added

- **Documentation improvements**:
  - Added efficiency comparison tables (tokens per file)
  - Query examples for prioritization
  - Workflow diagrams with token costs
  - Reference count interpretation guide

### Performance

- **Token efficiency**: 70-90% reduction per file
  - Manual exploration: 3,000-8,000 tokens/file
  - Discovery + targeted: 500-800 tokens/file
- **Discovery speed**: 250 files in ~5 seconds
- **Coverage**: 95%+ of logger locations

### Technical Details

- Discovery script uses bash/grep/jq (minimal dependencies)
- Regex-based pattern matching (not AST parsing)
- Counts method calls on logger fields (traditional + fluent API)
- Reference counts increase after conversion (expected behavior)

## [1.1.0] - 2026-05-07

### Added

#### Library Repository Support
- **Repository type detection**: Skills now detect library vs application repositories
  - User prompt: "Is this a library or an application repository?"
  - Stored in `.claude/workspace/repository-type.txt` for cross-skill reference
  - Workflows branch based on repository type

#### analyze skill
- **SLF4J facade validation** (libraries only)
  - Validates no logging backend dependencies in compile/runtime scope (only slf4j-api allowed)
  - Checks for backend-specific imports in production code (ch.qos.logback, org.apache.logging.log4j)
  - Generates `08-slf4j-facade-validation.md` with pass/fail status and remediation steps
  - **Critical for libraries**: Ensures consumer applications control logging backend
- **Library-specific reports**:
  - `06-downstream-impact.md`: Consumer coordination requirements, deployment sequence, rollback planning
  - `07-consumer-readiness-checklist.md`: Per-consumer validation checklist
  - Library README variant: Emphasizes consumer coordination, includes SLF4J validation status
- **Consumer application tracking**: Prompts user to list consuming applications

#### convert-logs skill
- **SLF4J facade enforcement** (libraries only)
  - Pre-conversion validation of SLF4J-only usage
  - Detects and converts backend-specific Logger declarations to SLF4J
  - Example: `ch.qos.logback.classic.Logger` → `org.slf4j.Logger`
- **Post-conversion consumer reminder**: Reminds user about downstream coordination after conversion

#### setup-logback skill
- **Library guidance workflow** (alternative to logback generation)
  - Generates `.claude/workspace/consumer-logback-guidance.md` instead of logback-spring.xml
  - Consumer guidance includes: required actions, validation steps, deployment sequence, rollback plan
  - Library summary variant: Documents guidance generation (not logback config)
- **Repository type detection**: Branches to library workflow automatically

#### Best Practices Emphasis
- **Task tracking strongly recommended**: For library migrations with multiple consumers
- **Generic email template generation** (optional): Template for notifying consumer teams
- **SLF4J facade principle**: Consistently emphasizes separation of logging API (SLF4J) from implementation (logback, log4j2)

### Changed

- **plugin.json**: Version bumped to 1.1.0, description updated to include library support

### Migration Notes

- **No breaking changes**: Application repositories continue working exactly as before (v1.0.2 behavior)
- **New workflows**: Library repositories get specialized workflow with consumer coordination
- **Backward compatible**: Existing analyze reports and workflows unaffected

---

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

## [1.0.2] - 2026-05-07

### Fixed
- **Skill naming**: choose-approach skill now has correct `splunk-to-dynatrace:` prefix in name field
  - Was: `name: choose-approach`
  - Now: `name: splunk-to-dynatrace:choose-approach`
  - Matches naming convention of all other skills in the plugin

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

- **1.0.2** (2026-05-07): Naming fix - correct skill name prefix
- **1.0.1** (2026-05-07): Packaging fix - include choose-approach skill
- **1.0.0** (2026-05-06): Initial release with 6 skills, comprehensive documentation, end-to-end testing

[1.0.2]: https://github.com/familysearch/satoris-claude-config/releases/tag/v1.0.2
[1.0.1]: https://github.com/familysearch/satoris-claude-config/releases/tag/v1.0.1
[1.0.0]: https://github.com/familysearch/satoris-claude-config/releases/tag/v1.0.0
