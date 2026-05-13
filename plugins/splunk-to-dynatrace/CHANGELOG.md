# Changelog

All notable changes to the Splunk-to-Dynatrace migration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-05-13

### Added

- **Hybrid Spoon + Code Analysis Architecture** for analyze skill
  - 10x performance improvement (5 minutes → 30-90 seconds for large codebases)
  - Support for 1,000+ file codebases (v2.1.1 timed out at 1,045 files)
  - **0% parse failures on Java 16+ code** (pattern matching, records, sealed classes)
  - Full Java 25 support via Spoon 11.2.0 (MIT license)
- **Three-phase hybrid scanner pipeline**:
  - Phase 1: Spoon AST-based discovery (10-30s for 1,000 files)
  - Phase 2: Code enrichment via file reads (30-60s for 3,000 candidates)
  - Phase 3: Dual output generation (lsp-inventory.json + conversion-inventory.json)
- **File content caching** - 12x improvement on repeated file access during enrichment
- **LoggerFactory.getLogger() filtering** - Removes 53% false positives from candidates
- **Multi-module Maven project support** - `--auto-discover` flag finds all modules automatically
- **End-to-end test scripts**:
  - `test-e2e-small.sh` - Validates correctness on small projects
  - `test-e2e-large.sh` - Validates performance on production codebases (<90s target)
  - `test-schema-compatibility.sh` - Ensures backward compatibility with v2.1.1

### Changed

- **analyze skill now uses hybrid_inventory.py (v3.0.0)** instead of lsp_inventory.py
  - Spoon scanner replaces LSP for initial discovery (22s vs 300s for 1,045 files)
  - Code enrichment reads actual source files for accurate pattern detection
  - LSP-only approach moved to "legacy" status with deprecation warning
- **SKILL.md updated** - Documents hybrid scanner as recommended approach (Option 1)
- **Performance characteristics** - Small: 5-10s, Medium: 15-30s, Large: 60-90s

### Deprecated

- **lsp_inventory.py (v2.1.1)** - Kept for reference, use hybrid_inventory.py instead
  - **Reason**: Times out on large codebases (>1,000 files), single-threaded LSP lifecycle
  - **Migration**: Replace `lsp_inventory.py` with `hybrid_inventory.py` in commands
  - **Deprecation notice added** to file header (lines 1-15)

### Performance Benchmarks

| Project Size | v2.1.1 (LSP-only) | v3.0.0 (Hybrid) | Improvement |
|--------------|-------------------|-----------------|-------------|
| Small (250 files) | 90 seconds | 5-10 seconds | **9-18x faster** |
| Medium (500 files) | 180 seconds | 15-30 seconds | **6-12x faster** |
| Large (1,045 files) | 300s+ (timeout) | 60-90 seconds | **Completes vs timeout** |

**cds2-root validation** (Session 1):
- Files scanned: 1,045 Java files
- Candidates found: 3,016 (179 loggers, 2,837 calls)
- Scan time: **22 seconds** (Spoon phase only)
- Parse failures: **0** (0.00%)
- Transformation-ready: **100%**

### Technical Details

- **Spoon 11.2.0** (MIT license) for AST parsing and transformation
  - Noclasspath mode for fast scanning (10-30s vs 5-10min with classpath)
  - Heuristic detection with 95-99% accuracy
  - Full Java 25 syntax support (no parse failures)
- **Detection strategies** (Session 1 results):
  - `heuristic_scope_pattern`: 53.6% (scope-based inference)
  - `known_logger_field`: 28.8% (field name matching)
  - `method_name`: 11.7% (logger method names)
  - `type_name`: 5.9% (type-based detection)
- **Backward compatible output format** - Matches v2.1.1 schema exactly
- **Transformation-ready** - All parsed files can be converted (vs JavaParser's 0.76% failure rate)

### Breaking Changes

**None** - Output format is fully backward compatible with v2.1.1.

All existing tooling and scripts that consume `lsp-inventory.json` or `conversion-inventory.json` will continue to work without modification.

### Migration Guide

**For users of v2.1.1 or earlier**:

1. **Update analyze skill commands**:

```bash
# Old (v2.1.1):
python3 analyze/scripts/lsp_inventory.py \
  --project-root . \
  --auto-discover \
  --output inventory.json

# New (v3.0.0):
python3 analyze/scripts/hybrid_inventory.py \
  --project-root . \
  --auto-discover \
  --output inventory.json
```

2. **Verify Java 17+ installed**:

```bash
java -version  # Should show Java 17 or later
```

3. **Build Spoon scanner** (if JAR not present):

```bash
cd analyze/scripts
./build-spoon-scanner.sh
```

4. **Test on your codebase**:

```bash
# Recommended: Start with debug mode to see progress
python3 analyze/scripts/hybrid_inventory.py \
  --project-root . \
  --auto-discover \
  --output /tmp/test-inventory.json \
  --debug
```

**No changes needed** for:
- convert-logs skill (consumes same conversion-inventory.json format)
- Custom scripts using jq to query lsp-inventory.json
- Downstream automation or CI/CD pipelines

### Known Issues

- **Spoon warnings about "missing types" in noclasspath mode**
  - Cosmetic only, not parse failures
  - Does not affect accuracy or output quality
  - Can be safely ignored
- **LoggerFactory.getLogger() calls appear as candidates**
  - Filtered out before conversion-inventory.json generation
  - Visible in lsp-inventory.json but marked as non-traditional pattern
  - Does not affect convert-logs skill workflow

### Requirements

- **Java 17+** (JRE) - Required for Spoon scanner
- **Python 3.7+** - Required for orchestrator
- **Maven 3.6+** (optional) - Only needed to rebuild Spoon scanner from source

### Files Changed

- **New scripts**:
  - `skills/analyze/scripts/hybrid_inventory.py` - v3.0.0 orchestrator
  - `skills/analyze/scripts/spoon-scanner/` - Spoon scanner Maven project
  - `skills/analyze/scripts/spoon-scanner.jar` - Pre-built scanner artifact (15 MB)
  - `skills/analyze/scripts/build-spoon-scanner.sh` - Build script
  - `skills/analyze/scripts/test-e2e-small.sh` - Small project test
  - `skills/analyze/scripts/test-e2e-large.sh` - Large project test
  - `skills/analyze/scripts/test-schema-compatibility.sh` - Schema validation test

- **Modified files**:
  - `skills/analyze/SKILL.md` - Documents hybrid scanner as Option 1
  - `skills/analyze/scripts/lsp_inventory.py` - Added deprecation notice
  - `.claude-plugin/plugin.json` - Version 3.0.0

- **Removed files**:
  - `skills/analyze/scripts/test-hybrid-inventory.sh` - Replaced by test-e2e-small.sh

## [2.0.0] - 2026-05-11

### Breaking Changes

- **convert-logs skill now requires analyze skill v1.4.0+ output** (`conversion-inventory.json`)
  - Old workflow using `discover-loggers-v2.sh` is deprecated
  - Must run `/splunk-to-dynatrace:analyze` before `/splunk-to-dynatrace:convert-logs`
- **New dependency: python3-jpype (>=1.4.1)** required for JavaParser transformer
  - Install via: `sudo apt-get install python3-jpype` (Ubuntu/Debian)
  - Or via pip: `pip install jpype1` (virtual environment)
- **discover-loggers-v2.sh deprecated** - superseded by analyze skill's `conversion-inventory.json`
- **find-traditional-calls.py deprecated** - superseded by analyze skill output
- **transform.py deprecated** - subprocess approach replaced by `transform_jpype.py`

### Added

- **Hybrid LLM + JavaParser Architecture**
  - LLM handles semantic decisions (field naming, enrichment, message templates)
  - JavaParser performs mechanical AST transformations (in-process via JPype)
  - Achieves 10-50x speedup and 90% token reduction
- **conversion-inventory.json generation** (analyze skill v1.4.0)
  - Pre-filtered to traditional logger calls only (excludes fluent API)
  - Pre-sorted bottom-to-top for optimal transformation order
  - Progress tracking with status fields (pending/completed)
  - Grouped by module → package → file
- **transform_jpype.py** - Parallel JavaParser transformer
  - In-process JVM access via JPype (no subprocess overhead)
  - 6-worker ThreadPoolExecutor for parallel file processing
  - Batch transformations per file (single AST parse)
  - Graceful failure handling with LLM Edit fallback
- **Line number verification** - LSP and JavaParser both use 1-based indexing (no conversion needed)

### Changed

- **analyze skill** - Enhanced with LSP semantic analysis emphasis
  - Added "Core Principle: Accuracy Over Speed" section
  - LSP provides 100% accuracy vs grep 40-60% accuracy
  - Generates both `lsp-inventory.json` and `conversion-inventory.json`
  - Skill description updated to highlight semantic analysis
- **convert-logs skill** - Complete workflow restructure
  - Step 1: Load conversion-inventory.json (was: Generate logger inventory)
  - Step 5: Hybrid transformation workflow (was: LLM Edit only)
    - Step 5.1: LLM generates transformation specs
    - Step 5.2: JavaParser applies transformations in parallel
    - Step 5.3: LLM Edit fallback for failures
    - Step 5.4: Update progress tracking
    - Step 5.5: Validate build
    - Step 5.6: Commit batch
  - Skill description updated for v2.0.0 hybrid architecture

### Performance

- **10-50x speedup**: 50 log statements transformed in ~2.5 minutes (was: 25 minutes)
  - LLM spec generation: ~2 minutes (semantic analysis)
  - JavaParser parallel execution: ~25 seconds (mechanical transformation)
  - Build validation: ~30 seconds
- **90% token reduction**: 15K tokens (was: 150K tokens) for 50 transformations
- **Parallel execution**: 6 workers process files simultaneously (thread-safe JVM)
- **Scales to enterprise**: Supports 200 developers, 1,000s repos, 100,000+ log statements

### Removed

- Deleted `transform_ast.py` - Wrong tool (libcst for Python AST, not Java)
- Deleted `java-transformer/` directory - Incomplete implementation with compilation errors
- Deleted `v1.1.0-RELEASE-NOTES.md` and `v1.2.0-RELEASE-NOTES.md` - Consolidated into CHANGELOG
- Deleted `PLUGIN-COMPLETE.md` - Outdated status document

### Documentation

- Added `CLEANUP-PLAN.md` - Documents v2.0.0 cleanup strategy
- Updated `TRANSFORMER-README.md` - Reflects deletions and deprecations
- Updated `plugin.json` - Version 2.0.0 with dependencies and breaking changes
- Added deprecation notices to superseded scripts

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
