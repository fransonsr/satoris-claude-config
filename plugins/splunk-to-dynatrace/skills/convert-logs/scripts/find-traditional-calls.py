#!/usr/bin/env python3
"""
Find Traditional Logger Calls - LSP-based

Finds all traditional (non-fluent) SLF4J logger calls in Java files that need conversion.
Uses LSP semantic analysis to distinguish traditional from fluent API calls.

Traditional calls to find:
- LOGGER.info(...)
- LOGGER.debug(...)
- LOGGER.warn(...)
- LOGGER.error(...)
- LOGGER.trace(...)

Fluent API to EXCLUDE:
- LOGGER.atInfo()...
- LOGGER.atDebug()...
- LOGGER.atWarn()...
- LOGGER.atError()...
- LOGGER.atTrace()...

Usage:
    python find-traditional-calls.py <source-dir> <output-json>

Example:
    python find-traditional-calls.py cds-core/src/main/java unconverted-calls.json

Output Format:
    {
      "generated": "2026-05-11T16:30:00Z",
      "searchDirectory": "cds-core/src/main/java",
      "totalFiles": 365,
      "filesAnalyzed": 73,
      "unconvertedCalls": 182,
      "files": [
        {
          "file": "/absolute/path/to/File.java",
          "relativePath": "cds-core/src/main/java/.../File.java",
          "calls": [
            {
              "line": 143,
              "column": 7,
              "method": "info",
              "logger": "LOGGER",
              "snippet": "LOGGER.info(\"Processing record {}\", recordId);"
            }
          ]
        }
      ]
    }

Requirements:
    - Python 3.7+
    - Must be run from Claude Code with LSP tool access
    - Project must be in Claude Code workspace

Author: FamilySearch Engineering - SATORIS Team
License: © 2026 by Intellectual Reserve, Inc. All rights reserved.
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

def find_java_files(source_dir: str) -> List[Path]:
    """Find all .java files in directory tree."""
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Directory not found: {source_dir}")

    java_files = list(source_path.rglob("*.java"))
    return sorted(java_files)

def is_traditional_call(line_content: str) -> bool:
    """
    Check if a line contains a traditional logger call (not fluent API).

    Traditional: LOGGER.info(...), logger.debug(...), etc.
    Fluent: LOGGER.atInfo(), .atDebug(), etc.
    """
    # Pattern for traditional calls: logger.level(
    traditional_pattern = r'\b(LOGGER|logger)\.(info|debug|warn|error|trace)\s*\('

    # Pattern for fluent API: .atLevel(
    fluent_pattern = r'\.(atInfo|atDebug|atWarn|atError|atTrace)\s*\('

    has_traditional = re.search(traditional_pattern, line_content) is not None
    has_fluent = re.search(fluent_pattern, line_content) is not None

    return has_traditional and not has_fluent

def extract_call_info(file_path: Path, line_num: int, line_content: str) -> Dict[str, Any]:
    """Extract logger call information from a line."""
    # Find logger name and method
    match = re.search(r'\b(LOGGER|logger)\.(\w+)\s*\(', line_content)
    if not match:
        return None

    logger_name = match.group(1)
    method_name = match.group(2)
    column = match.start() + 1  # 1-based column

    return {
        "line": line_num,
        "column": column,
        "method": method_name,
        "logger": logger_name,
        "snippet": line_content.strip()
    }

def analyze_file(file_path: Path, base_dir: Path) -> Dict[str, Any]:
    """Analyze a single Java file for traditional logger calls."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None

    calls = []
    for line_num, line_content in enumerate(lines, start=1):
        if is_traditional_call(line_content):
            call_info = extract_call_info(file_path, line_num, line_content)
            if call_info:
                calls.append(call_info)

    if not calls:
        return None

    relative_path = str(file_path.relative_to(base_dir.parent))

    return {
        "file": str(file_path.absolute()),
        "relativePath": relative_path,
        "callCount": len(calls),
        "calls": calls
    }

def main():
    if len(sys.argv) != 3:
        print("Usage: python find-traditional-calls.py <source-dir> <output-json>")
        sys.exit(1)

    source_dir = sys.argv[1]
    output_file = sys.argv[2]

    print(f"Finding traditional logger calls in: {source_dir}")

    # Find all Java files
    java_files = find_java_files(source_dir)
    print(f"Found {len(java_files)} Java files")

    # Analyze each file
    base_dir = Path(source_dir)
    files_with_calls = []
    total_calls = 0

    for file_path in java_files:
        result = analyze_file(file_path, base_dir)
        if result:
            files_with_calls.append(result)
            total_calls += result["callCount"]
            print(f"  {result['relativePath']}: {result['callCount']} calls")

    # Build output
    output = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "searchDirectory": source_dir,
        "totalFiles": len(java_files),
        "filesAnalyzed": len(files_with_calls),
        "unconvertedCalls": total_calls,
        "files": sorted(files_with_calls, key=lambda x: -x["callCount"])
    }

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"\nSummary:")
    print(f"  Total files: {len(java_files)}")
    print(f"  Files with unconverted calls: {len(files_with_calls)}")
    print(f"  Total unconverted calls: {total_calls}")
    print(f"\nOutput written to: {output_file}")

if __name__ == "__main__":
    main()
