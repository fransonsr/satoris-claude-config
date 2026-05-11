# Line Number Verification

## Critical Issue

**Question**: Do LSP and JavaParser use the same line numbering convention?

## LSP Protocol Specification

From LSP spec (https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/):
- **Position**: Line and character are **0-based**
- Line 0 = first line of file
- However, many language servers convert to 1-based for display/compatibility

## JavaParser Convention

JavaParser uses **1-based** line numbers:
- `call.getBegin().get().line` returns 1 for first line
- Standard editor convention (most editors show line 1 as first line)

## jdtls (Java LSP) Behavior

Need to verify: Does jdtls return 0-based or 1-based line numbers?

## Test Results

### Our Test File (TestService.java)
```
Line 11 (1-indexed): LOGGER.info(...)
Line 15 (1-indexed): LOGGER.error(...)
```

### JavaParser Reports
- Found line 11 ✅
- Found line 15 ✅
- Uses **1-based** indexing

### LSP Inventory (to be verified)
From `lsp_inventory.py`:
- `add_log_call_from_lsp(logger_name, file_path, line)`
- Line number passed directly from LSP findReferences result
- **Need to verify**: Is this 0-based or 1-based?

## Action Items

1. **Immediate**: Check analyze skill output
   ```bash
   cd /home/fransonsr/github/cds2-root
   /splunk-to-dynatrace:analyze
   jq '.log_calls[0:5] | .[] | {file: .file, line: .line}' \
     .claude/analyze-reports/lsp-inventory.json
   # Compare line numbers to actual file
   ```

2. **If LSP returns 0-based**:
   - Add +1 when storing in inventory: `line + 1`
   - OR subtract 1 when calling JavaParser: `spec['line'] - 1`

3. **If LSP returns 1-based**:
   - No conversion needed ✅
   - LSP and JavaParser match

## Recommendation

**Before Phase 3 integration**, run analyze skill on real codebase and verify:
```bash
# Get a log call from inventory
jq '.log_calls[0] | {file: .file, line: .line, snippet: .message_snippet}' \
  .claude/analyze-reports/lsp-inventory.json

# Manually check that file at that line number
# Line should match editor line number (1-based)
```

If they match, no conversion needed.
If off-by-one, add conversion in `generate_conversion_inventory()`.

## Current Status

✅ JavaParser uses 1-based (verified by successful transformation)
⏳ LSP convention needs verification on real codebase
🚨 **CRITICAL**: Must verify before production use
