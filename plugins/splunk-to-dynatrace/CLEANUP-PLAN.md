# Splunk-to-Dynatrace Plugin v2.0.0 - Cleanup Plan

**Date**: 2026-05-11  
**Goal**: Clean up plugin for v2.0.0 release - remove outdated files, update documentation

---

## Files to DELETE

### 1. Incorrect Implementation
- [ ] `skills/convert-logs/scripts/transform_ast.py` 
  - **Reason**: libcst is for Python AST, not Java - completely wrong tool
  - **Status**: Never worked, abandoned approach

### 2. Incomplete Java Implementation
- [ ] `skills/convert-logs/scripts/java-transformer/` (entire directory)
  - **Reason**: Incomplete, has compilation errors, superseded by JPype approach
  - **Files**: `LogTransformer.java`, `pom.xml`, `build.sh`

### 3. Old Release Notes
- [ ] `v1.1.0-RELEASE-NOTES.md`
- [ ] `v1.2.0-RELEASE-NOTES.md`
  - **Reason**: Move content to CHANGELOG.md, delete originals

### 4. Status Documents
- [ ] `PLUGIN-COMPLETE.md`
  - **Reason**: Outdated, says v1.0.0 complete, no longer relevant

---

## Files to DEPRECATE (Keep but Mark)

### 1. Old Discovery Scripts
- [ ] `skills/convert-logs/scripts/discover-loggers-v2.sh`
  - **New**: Load conversion-inventory.json from analyze skill
  - **Keep as**: Recovery/verification tool only
  - **Mark**: Add deprecation notice at top

- [ ] `skills/convert-logs/scripts/find-traditional-calls.py`
  - **New**: conversion-inventory.json from analyze skill
  - **Keep as**: Recovery/verification tool only
  - **Mark**: Add deprecation notice at top

- [ ] `skills/convert-logs/scripts/find-traditional-calls-README.md`
  - **Update**: Add deprecation notice

### 2. Alternative Transformer
- [ ] `skills/convert-logs/scripts/transform.py`
  - **New**: transform_jpype.py (in-process, no subprocess overhead)
  - **Keep as**: Fallback if JPype has issues
  - **Mark**: Add deprecation notice

---

## Files to UPDATE

### Plugin Metadata
- [ ] `.claude-plugin/plugin.json` → v2.0.0
- [ ] `CHANGELOG.md` → Add v2.0.0 entry with breaking changes

### Main Documentation
- [ ] `README.md` → Update for v2.0.0
  - What's New section
  - Architecture diagram (hybrid LLM+JavaParser)
  - Performance metrics
  - Installation (jpype requirement)
  - Migration guide from v1.x

- [ ] `INSTALL.md` → Update dependencies
  - Add: python3-jpype installation
  - Update: analyze skill v1.4.0 requirement

### Status/Reference
- [ ] `IMPLEMENTATION-STATUS.md` → Finalize
  - Mark Phase 1-3 complete
  - Update metrics
  - Remove "in progress" language

- [ ] `skills/convert-logs/scripts/TRANSFORMER-README.md` → Update
  - Emphasize transform_jpype.py as primary
  - Mark transform.py as fallback
  - Remove libcst section entirely
  - Mark java-transformer section as deleted

- [ ] `skills/convert-logs/scripts/verify-line-numbers.md` → Finalize
  - Add verification results
  - Confirm 1-based (no conversion needed)
  - Mark as RESOLVED

### Skill Documentation
- [ ] `skills/analyze/SKILL.md` → Already updated ✓
- [ ] `skills/convert-logs/SKILL.md` → Already updated ✓

---

## Files to KEEP AS-IS

### Reference Material
- `references/familysearch-observability-standards.md`
- `CONTRIBUTING.md`
- `FUTURE_ENHANCEMENTS.md`

### Scripts (Still Useful)
- `package.sh` - Plugin packaging
- `verify-plugin.sh` - Plugin verification
- `skills/analyze/scripts/lsp_inventory.py` - Core functionality
- `skills/analyze/scripts/anti_patterns.json` - Standards reference
- `skills/analyze/scripts/example_queries.sh` - Usage examples
- `skills/convert-logs/scripts/transform_jpype.py` - PRIMARY transformer
- `skills/convert-logs/scripts/requirements.txt` - Dependencies
- `skills/convert-logs/scripts/test-*` - Test fixtures

### Other Skills
- `skills/choose-approach/SKILL.md`
- `skills/migrate/SKILL.md`
- `skills/setup-logback/SKILL.md`
- `skills/validate-dashboards/SKILL.md`

---

## Action Items

1. **Delete**: Remove incorrect/incomplete implementations
2. **Deprecate**: Add notices to superseded but still useful files
3. **Update**: Version numbers, documentation, examples
4. **Consolidate**: Move release notes to CHANGELOG.md
5. **Test**: Verify plugin after cleanup

---

## Post-Cleanup Verification

```bash
# Check plugin structure
ls -la .claude-plugin/

# Verify no broken references
grep -r "transform_ast\|LogTransformer.java" skills/

# Check version consistency
grep -r "v2.0.0\|2.0.0" .

# Test skills load
cat .claude-plugin/plugin.json | jq '.skills'
```
