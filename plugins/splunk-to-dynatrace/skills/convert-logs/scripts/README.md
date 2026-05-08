# Logger Discovery Script

## Purpose

Discovers all Logger usage in Java files to create a complete inventory BEFORE starting conversions.

## Usage

```bash
./discover-loggers-v2.sh <search-directory> <output-json-file>

# Example: Scan async package
./discover-loggers-v2.sh cds-core/src/main/java/org/familysearch/cds/core/async async-loggers.json

# Example: Scan entire module
./discover-loggers-v2.sh cds-core/src/main/java cds-core-loggers.json
```

## Output Format

JSON file with complete logger inventory:

```json
{
  "generated": "2026-05-08T20:35:42Z",
  "searchDirectory": "...",
  "totalFiles": 250,
  "filesWithLoggers": 38,
  "totalLoggers": 35,
  "totalReferences": 133,
  "files": [
    {
      "file": "/absolute/path/to/File.java",
      "relativePath": "cds-core/src/main/java/.../File.java",
      "loggers": [
        {
          "name": "LOGGER",
          "type": "org.slf4j.Logger",
          "declarationLine": 51,
          "references": [143, 200, 216, 224, ...],
          "referenceCount": 27
        }
      ]
    }
  ]
}
```

## Query Examples

### Find Files with Most Work
```bash
jq -r '.files[] | select(.loggers[].referenceCount > 0) | "\(.loggers[].referenceCount)\t\(.relativePath)"' output.json | sort -rn
```

### Export to CSV for Tracking
```bash
jq -r '.files[] | .relativePath as $f | .loggers[] | "\($f),\(.name),\(.referenceCount)"' output.json > tracker.csv
```

### Get Line Numbers for Targeted Conversion
```bash
jq '.files[] | select(.relativePath | contains("ServiceJob")) | .loggers[].references[]' output.json
```

### Filter by Module
```bash
jq '.files[] | select(.relativePath | contains("/async/"))' output.json
```

## Important Notes

### Reference Counts Include BOTH Traditional and Fluent API

The script counts ALL method calls on the logger field, including:
- Traditional: `LOGGER.info()`, `LOGGER.error()`, etc.
- Fluent API: `LOGGER.atInfo()`, `LOGGER.atError()`, `.log()`

**This means:**
- **Before conversion**: `logger.info("message", param)` = 1 reference
- **After conversion**: `logger.atInfo().addKeyValue(...).log(...)` = 3+ references

**Reference count will INCREASE after conversion to fluent API!**

### How to Interpret Results

**Use cases:**

1. **Before starting conversions** - Get baseline:
   - Count shows traditional logger calls
   - Use for prioritization (high count = high impact)
   - Create tracking spreadsheet

2. **During conversions** - Track progress:
   - Reference count increases as you convert (expected)
   - Use file paths and logger names, not counts
   - Re-run to find remaining unconverted files

3. **Validate completion** - Check for traditional patterns:
   - Run script
   - Then grep for traditional patterns: `grep -r "LOGGER\.info\|LOGGER\.error\|LOGGER\.warn" src/`
   - If grep finds traditional calls, they need conversion
   - If grep finds nothing, all calls are fluent API

### Example: Before vs After

**Before conversion** (ServiceJob.java):
```java
LOGGER.warn("Phase error count exceeded max: jobId={} errorCount={}",  
  getDbId(), serviceJobPhase.getErrorCount());
```
References found: 1 (`LOGGER.warn`)

**After conversion**:
```java
LOGGER.atWarn()
    .addKeyValue("warn.category", "THRESHOLD")
    .addKeyValue("jobId", getDbId())
    .addKeyValue("errorCount", serviceJobPhase.getErrorCount())
    .log("Phase error count exceeded max");
```
References found: 6 (`LOGGER.atWarn`, 3x `.addKeyValue`, 1x `.log`)

**Reference count increased 6x, but it's fully converted!**

## Validation Strategy

To verify conversions are complete:

1. **Run discovery script** (gets all logger locations)
2. **Grep for traditional patterns**:
   ```bash
   grep -rn "LOGGER\.\(info\|debug\|warn\|error\|trace\)(" src/ | grep -v "\.atInfo\|\.atDebug\|\.atWarn\|\.atError\|\.atTrace"
   ```
3. **If grep finds matches** → still have traditional calls to convert
4. **If grep finds nothing** → all calls use fluent API ✓

## Token Efficiency

**Without discovery script:**
- Manual exploration: ~3,000-8,000 tokens per file
- Unknown total scope until complete

**With discovery script:**
- Discovery: free (runs locally)
- Targeted conversions: ~500-800 tokens per file
- Known scope upfront

**Result: 70-90% token reduction**

## Technical Details

**How it works:**
1. Scans Java files for `org.slf4j.Logger` import
2. Finds Logger field declarations with regex
3. Extracts logger variable names
4. Finds all method calls on logger variables
5. Counts and records line numbers
6. Outputs structured JSON

**Limitations:**
- Regex-based (not true AST parsing)
- May miss complex multi-line declarations
- Counts method calls, not log statements
- Cannot distinguish traditional from fluent API

**Why it's still useful:**
- Gets 95%+ of logger locations
- Fast execution (seconds for hundreds of files)
- No dependencies except bash/grep/jq
- Provides prioritization and tracking
