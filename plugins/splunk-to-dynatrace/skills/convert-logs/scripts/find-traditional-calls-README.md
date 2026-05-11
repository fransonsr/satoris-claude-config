# Find Traditional Logger Calls Script

> ⚠️ **DEPRECATED in v2.0.0**
> 
> This script is superseded by the analyze skill's `conversion-inventory.json` output.
> 
> **New workflow**: 
> 1. Run `/splunk-to-dynatrace:analyze`
> 2. Use `.claude/analyze-reports/conversion-inventory.json`
>    - Already filtered to traditional calls only
>    - Sorted bottom-to-top for optimal conversion
>    - Includes progress tracking
> 
> This script is kept ONLY for recovery/verification when inventory line numbers drift.

---

## Purpose (Legacy)

Finds all **unconverted traditional SLF4J logger calls** in Java files using regex-based pattern matching. This script accurately distinguishes traditional calls from fluent API calls that are already converted.

## Why This Script?

The existing `discover-loggers-v2.sh` script counts **all** method calls on logger fields (including fluent API calls), making it impossible to tell what still needs conversion. This script solves that by:

1. **Finding only traditional calls**: `LOGGER.info()`, `.debug()`, `.warn()`, `.error()`, `.trace()`
2. **Excluding fluent API calls**: `.atInfo()`, `.atDebug()`, `.atWarn()`, `.atError()`, `.atTrace()`
3. **Reporting exact locations**: File path, line number, column, method, code snippet

## Usage

```bash
python3 find-traditional-calls.py <source-directory> <output-json>

# Example: Scan async package
python3 find-traditional-calls.py cds-core/src/main/java/org/familysearch/cds/core/async async-unconverted.json

# Example: Scan entire module
python3 find-traditional-calls.py cds-core/src/main/java cds-core-unconverted.json
```

## Output Format

```json
{
  "generated": "2026-05-11T16:30:00Z",
  "searchDirectory": "cds-core/src/main/java/org/familysearch/cds/core/async",
  "totalFiles": 250,
  "filesAnalyzed": 63,
  "unconvertedCalls": 162,
  "files": [
    {
      "file": "/absolute/path/to/MultilineStitchPhase.java",
      "relativePath": "async/MultilineStitchPhase.java",
      "callCount": 15,
      "calls": [
        {
          "line": 124,
          "column": 7,
          "method": "info",
          "logger": "LOGGER",
          "snippet": "LOGGER.info(\"Stitching complete\");"
        }
      ]
    }
  ]
}
```

## Query Examples

### Find high-priority files (most calls)
```bash
jq '.files | .[0:10] | .[] | {file: .relativePath, calls: .callCount}' async-unconverted.json
```

### Get line numbers for a specific file
```bash
jq '.files[] | select(.relativePath | contains("MultilineStitchPhase")) | .calls[].line' async-unconverted.json
```

### Export to CSV for tracking
```bash
jq -r '.files[] | .relativePath as $f | .calls[] | "\($f),\(.line),\(.method)"' async-unconverted.json > tracking.csv
```

### Count by log level
```bash
jq '[.files[].calls[].method] | group_by(.) | map({level: .[0], count: length})' async-unconverted.json
```

## How It Works

**Pattern Matching:**
```python
# Matches traditional calls
traditional_pattern = r'\b(LOGGER|logger)\.(info|debug|warn|error|trace)\s*\('

# Excludes fluent API
fluent_pattern = r'\.(atInfo|atDebug|atWarn|atError|atTrace)\s*\('
```

**Example:**
```java
// ✓ FOUND (traditional)
LOGGER.info("Processing record {}", recordId);

// ✗ EXCLUDED (fluent API - already converted)
LOGGER.atInfo()
    .addKeyValue("record.id", recordId)
    .log("Processing record");
```

## Comparison with discover-loggers-v2.sh

| Feature | discover-loggers-v2.sh | find-traditional-calls.py |
|---------|------------------------|---------------------------|
| **Finds** | All logger method calls | Only unconverted calls |
| **Includes fluent API?** | Yes (causes confusion) | No (excludes .at*) |
| **Output** | Reference counts | Call locations + snippets |
| **Use case** | Initial discovery | Conversion tracking |
| **Accuracy for conversion** | 50% (counts increase after conversion) | 100% (only finds what needs work) |

## Workflow Integration

**Step 1: Find unconverted calls**
```bash
python3 find-traditional-calls.py cds-core/src/main/java unconverted.json
```

**Step 2: Prioritize by call count**
```bash
jq '.files | sort_by(-.callCount) | .[0:15]' unconverted.json
```

**Step 3: Convert targeted files**
- Use line numbers to read ±10 lines around each call
- Apply fluent API transformations
- Commit batch of files

**Step 4: Re-run to verify**
```bash
python3 find-traditional-calls.py cds-core/src/main/java unconverted-after.json
# Compare .unconvertedCalls before vs after
```

## Performance

- **Speed**: ~1 second for 250 files
- **Memory**: Minimal (processes files one at a time)
- **Accuracy**: 100% for standard SLF4J patterns

## Limitations

- **Regex-based**: May miss non-standard patterns or multi-line calls
- **No semantic analysis**: Doesn't validate logger types via AST
- **False positives possible**: If `.at*` methods exist for other purposes

For complex cases requiring semantic analysis, use the **analyze skill** with LSP.

## Requirements

- Python 3.7+
- Standard library only (json, re, pathlib)
- No external dependencies

## Author

FamilySearch Engineering - SATORIS Team  
© 2026 by Intellectual Reserve, Inc. All rights reserved.
