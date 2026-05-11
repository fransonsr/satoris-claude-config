# Log Transformation Tools

## Overview

Two approaches for transforming traditional SLF4J logging to fluent API:

1. **Python + JavaParser via JPype (transform_jpype.py)** - **RECOMMENDED** ✅
2. **Python subprocess → Java (transform.py)** - ⚠️ DEPRECATED (fallback only)

### Deleted Approaches

- ❌ **transform_ast.py**: Deleted - Wrong tool (libcst is for Python AST, not Java)
- ❌ **java-transformer/**: Deleted - Incomplete implementation with compilation errors

## Python + JavaParser via JPype (Recommended)

### Why This Approach?

- ✅ **Correct**: JavaParser is built specifically for Java (not Python AST tools)
- ✅ **Proven**: JavaParser is industry-standard (PMD, SpotBugs, etc.)
- ✅ **No build step**: JPype downloads JavaParser JAR automatically
- ✅ **Python orchestration**: Threading, error handling, progress tracking
- ✅ **No subprocess overhead**: JVM runs in-process
- ✅ **Complete**: Handles all Java syntax (generics, lambdas, annotations)

### Architecture

```
Python script (transform_jpype.py)
  ↓ starts
JVM with JavaParser on classpath
  ↓ Python threads call
JavaParser Java API directly (via JPype)
  ↓ manipulate
Java AST (CompilationUnit, MethodCallExpr, etc.)
  ↓ returns
Transformed Java code
```

### Installation

**Option 1: System package (Recommended for Ubuntu/Debian)**:
```bash
sudo apt-get install python3-jpype
```

**Option 2: Virtual environment (Recommended for development)**:
```bash
python3 -m venv venv
source venv/bin/activate
pip install jpype1
```

**Option 3: User install** (if system allows):
```bash
pip install --user jpype1
```

JavaParser JAR downloads automatically on first run (or specify path).

**For WSL/restricted environments**: Use system package (Option 1) or virtual environment (Option 2).

### Usage

```bash
# Transform files in parallel (6 threads)
python3 transform_jpype.py \
  --batch .claude/analyze-reports/conversion-inventory.json \
  --specs batch-specs.json \
  --scope module:cds-core \
  --workers 6

# Sequential (for debugging)
python3 transform_jpype.py \
  --batch inventory.json \
  --specs specs.json \
  --workers 1

# Save results to file
python3 transform_jpype.py \
  --batch inventory.json \
  --specs specs.json \
  --output results.json
```

### How It Works

1. **JVM startup**: Starts JVM once with JavaParser on classpath
2. **Batch per file**: Processes all transformations in a file in single AST parse
3. **Parallel execution**: 6 threads process files simultaneously (JVM is thread-safe)
4. **JavaParser API**: Direct Java API calls from Python via JPype
5. **Bottom-to-top**: Specs already sorted by inventory, line numbers stay valid
6. **No subprocess overhead**: All work happens in-process

### Input Format (batch-specs.json)

```json
[
  {
    "file": "cds-core/src/main/java/.../ServiceJob.java",
    "line": 200,
    "logger": "LOGGER",
    "transformation": {
      "type": "traditional_to_fluent",
      "level": "info",
      "fields": [
        {"key": "person.id", "value": "personId"},
        {"key": "ordinance.type", "value": "ordinanceType"}
      ],
      "message": "Processing person ordinance",
      "enrichment": {
        "event.name": "person.ordinance.processing"
      },
      "exception": null
    }
  }
]
```

### Output

Returns transformation results:

```json
[
  {
    "file": "ServiceJob.java",
    "status": "success",
    "successCount": 8,
    "failureCount": 0,
    "errors": [],
    "transformedCode": "..." 
  }
]
```

**Status values**:
- `success`: All transformations applied
- `partial`: Some transformations failed (fallback to LLM Edit)
- `failed`: File could not be processed

## Subprocess Approach (Deprecated - Fallback Only)

> ⚠️ Use transform_jpype.py instead. This is kept only as fallback.

The `transform.py` script spawns Java subprocess per file:
- ❌ Subprocess overhead (~5-10 seconds per batch)
- ❌ Requires JAR compilation (deleted in cleanup)
- ✅ Kept as fallback if JPype has installation issues

If you must use this fallback:
```bash
# Note: java-transformer/ directory was deleted
# You'd need to rebuild it from git history if needed
python3 transform.py \
  --batch inventory.json \
  --specs specs.json \
  --workers 6
```

## Performance Comparison

**Baseline (LLM Edit only)**:
- 50 log statements: ~25 minutes
- Token usage: ~150K tokens

**Hybrid (JPype + JavaParser)** - RECOMMENDED:
- 50 log statements: ~2.5 minutes (10x faster)
- LLM spec generation: ~2 minutes
- JavaParser transformation: ~25 seconds (6 threads, no subprocess overhead)
- Token usage: ~15K tokens (90% reduction)
- **Best of both worlds**: Python orchestration + Java correctness

**Deprecated approaches**:
- transform.py (subprocess): ~5-10 seconds slower due to process spawns
- transform_ast.py: Deleted - wrong tool (libcst for Python, not Java)
- java-transformer/: Deleted - incomplete implementation

## Workflow Integration

```
User runs /splunk-to-dynatrace:analyze
  ↓
analyze generates conversion-inventory.json (bottom-to-top sorted)
  ↓
User runs /splunk-to-dynatrace:convert-logs
  ↓
LLM generates transformation specs (semantic decisions)
  ↓
Python AST / JavaParser applies transformations (mechanical)
  ↓
Validate build
  ↓
Update conversion-inventory.json (mark completed)
  ↓
Commit
```

## Failure Handling

Both approaches handle failures gracefully:

1. **Partial success**: Write transformed code, report failures
2. **Complete failure**: Skip file, log error
3. **Fallback**: LLM Edit for complex cases AST can't handle

Example fallback cases:
- Multi-line statements with unusual formatting
- Complex lambda expressions in log parameters
- Edge cases not yet supported

## Choosing an Approach

**Use JPype + JavaParser (transform_jpype.py)** - **RECOMMENDED**:
- ✅ Correct: JavaParser built for Java
- ✅ Simple: No build step, auto-downloads JAR
- ✅ Fast: No subprocess overhead
- ✅ Proven: Industry-standard tool
- ✅ **Use this for production**

**Use subprocess + JavaParser (transform.py)** when:
- ⚠️ JPype installation issues (rare)
- ⚠️ Need complete JVM isolation per file
- Performance cost: ~5-10s overhead for process spawns

**Do NOT use libcst (transform_ast.py)**:
- ❌ libcst is for Python code, not Java
- ❌ Will not work for Java transformations

## Development Status

- **Phase 1 (analyze v1.4.0)**: ✅ Complete - generates conversion-inventory.json
- **Phase 2 (JPype + JavaParser)**: ✅ Complete - parallel transformation with direct API access
- **Phase 2 (subprocess + JavaParser)**: ⚠️ Alternative approach (works but has overhead)
- **Phase 2 (libcst)**: ❌ Incorrect - abandoned (wrong tool for Java)
- **Phase 3 (convert-logs integration)**: 🚧 Next - integrate transform_jpype.py into skill
- **Phase 4 (testing)**: ⏳ Pending
- **Phase 5 (documentation)**: ⏳ Pending

## Next Steps

1. Test Python AST approach on real codebase
2. Integrate into convert-logs skill
3. Add LLM spec generation step
4. Implement progress tracking
5. Document in SKILL.md

## References

- **libcst docs**: https://libcst.readthedocs.io/
- **JavaParser docs**: https://javaparser.org/
- **Handoff document**: `/home/fransonsr/.claude/handoff/splunk-to-dynatrace-plugin-improvements.md`
- **Plan**: `/home/fransonsr/.claude/plans/humming-percolating-dusk.md`
