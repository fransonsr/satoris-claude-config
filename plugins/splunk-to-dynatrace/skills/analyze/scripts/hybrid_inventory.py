#!/usr/bin/env python3
"""
Hybrid Logger Inventory Generator

Orchestrates Spoon discovery + code enrichment pipeline.
Version: 3.0.1 (hybrid architecture + Spoon type validation + multi-framework support)

Usage:
    python3 hybrid_inventory.py --project-root . --auto-discover --output inventory.json
    python3 hybrid_inventory.py --project-root . --source src/main/java --output inventory.json

Architecture:
    Phase 1: Run Spoon scanner → candidates.json (fast: 22s for 3,000 candidates)
    Phase 2: Enrich with code snippets → extract level, pattern, message (slower: file I/O)
    Phase 3: Generate final inventories → lsp-inventory.json + conversion-inventory.json

Author: FamilySearch Engineering - SATORIS Team
License: © 2026 by Intellectual Reserve, Inc. All rights reserved.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate hybrid logger inventory using Spoon + code analysis'
    )
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path.cwd(),
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--source',
        type=Path,
        action='append',
        help='Source directory to scan (repeatable, e.g., src/main/java src/test/java)'
    )
    parser.add_argument(
        '--auto-discover',
        action='store_true',
        help='Auto-discover all Maven modules and source directories'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output file path for lsp-inventory.json'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )

    args = parser.parse_args()

    # Validation
    if not args.project_root.exists():
        parser.error(f"Project root does not exist: {args.project_root}")

    if not args.auto_discover and not args.source:
        parser.error("Must specify either --auto-discover or --source")

    return args


def run_spoon_scanner(args: argparse.Namespace) -> Path:
    """
    Run Spoon scanner as subprocess.

    Returns:
        Path to candidates.json output file
    """
    script_dir = Path(__file__).parent
    jar_path = script_dir / "spoon-scanner.jar"

    if not jar_path.exists():
        raise FileNotFoundError(
            f"Spoon scanner JAR not found: {jar_path}\n"
            f"Run: cd {script_dir} && ./build-spoon-scanner.sh"
        )

    # Create temp file for candidates
    fd, candidates_file = tempfile.mkstemp(suffix='.json', prefix='candidates-')
    os.close(fd)  # Close file descriptor, Spoon will write to it

    # Build command
    cmd = [
        'java',
        '-jar',
        str(jar_path),
        str(args.project_root),
        candidates_file
    ]

    if args.auto_discover:
        cmd.append('--auto-discover')
    else:
        for source in args.source:
            cmd.extend(['--source', str(source)])

    if args.debug:
        cmd.append('--debug')

    # Run scanner
    if args.debug:
        print(f"  Command: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )

        if args.debug:
            print(result.stdout, file=sys.stderr)

        print(f"✓ Spoon scanner complete: {candidates_file}", file=sys.stderr)
        return Path(candidates_file)

    except subprocess.CalledProcessError as e:
        print(f"✗ Spoon scanner failed:", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"✗ Spoon scanner timed out (>300s)", file=sys.stderr)
        sys.exit(1)


def load_candidates(candidates_file: Path) -> Dict[str, Any]:
    """
    Load candidates.json from Spoon scanner.

    Returns:
        Dict with 'metadata' and 'candidates' keys
    """
    if not candidates_file.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_file}")

    with open(candidates_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    metadata = data.get('metadata', {})
    candidates = data.get('candidates', [])

    print(f"  Loaded {len(candidates)} candidates", file=sys.stderr)
    print(f"    - {metadata.get('declarations', 0)} logger declarations", file=sys.stderr)
    print(f"    - {metadata.get('calls', 0)} logger calls", file=sys.stderr)

    return data


def normalize_path(spoon_path: str, project_root: Path) -> str:
    """
    Convert Spoon's absolute path to project-relative path.

    Args:
        spoon_path: Absolute path from Spoon
        project_root: Project root directory

    Returns:
        Relative path string
    """
    abs_path = Path(spoon_path)
    try:
        return str(abs_path.relative_to(project_root))
    except ValueError:
        # Path not under project_root - return as-is
        return spoon_path


def read_code_snippet_cached(file_path: Path, line: int,
                            cache: Dict[Path, List[str]]) -> str:
    """
    Read code snippet at specific line with caching for performance.

    Args:
        file_path: Absolute path to source file
        line: Line number (1-based)
        cache: File content cache (file_path -> lines)

    Returns:
        Code snippet as string (±3 lines around target)
    """
    if file_path not in cache:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cache[file_path] = f.readlines()
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
            cache[file_path] = []

    lines = cache[file_path]
    if not lines:
        return ""

    # Get target line and context
    idx = line - 1  # Convert to 0-based
    start = max(0, idx - 3)
    end = min(len(lines), idx + 4)
    return ''.join(lines[start:end])


def is_logger_statement(candidate: dict, code_snippet: str) -> bool:
    """
    Filter out non-logger calls using Spoon's type information.

    Args:
        candidate: Candidate dict from Spoon (includes typeName = receiver type)
        code_snippet: Code context

    Returns:
        True if this is a log statement, False otherwise
    """
    # Skip factory calls
    if ('LoggerFactory.getLogger' in code_snippet or
        'Logger.getLogger' in code_snippet or
        'LogManager.getLogger' in code_snippet or
        'LogFactory.getLog' in code_snippet):
        return False

    # Check methodName from Spoon (all supported frameworks)
    method = candidate.get('methodName', '')
    valid_methods = [
        # SLF4J, Log4j, Logback
        'error', 'warn', 'info', 'debug', 'trace', 'fatal',
        # Log4j 2.x fluent API
        'atError', 'atWarn', 'atInfo', 'atDebug', 'atTrace', 'atFatal',
        # Java Util Logging (JUL)
        'severe', 'warning', 'config', 'fine', 'finer', 'finest'
    ]
    if method not in valid_methods:
        return False

    # NEW: Check receiver type from Spoon (v3.0.1) - multi-framework support
    receiver_type = candidate.get('typeName', '')  # Spoon provides this now
    if receiver_type:
        # If type is known, verify it's a logger from any supported framework
        is_logger = (
            'Logger' in receiver_type or       # SLF4J, Log4j, Logback, JUL
            'slf4j' in receiver_type or        # SLF4J
            'log4j' in receiver_type or        # Log4j 1.x, 2.x
            'logback' in receiver_type or      # Logback
            'commons.logging' in receiver_type or  # Apache Commons Logging
            'java.util.logging' in receiver_type   # Java Util Logging
        )
        if not is_logger:
            return False  # Definitely not a logger call (e.g., AbstractTask, ServiceJobPhase)

    # If type is unknown (None/empty), we still accept it (conservative)
    # The Spoon scanner marks these with needsValidation=true
    return True


def extract_level(code_snippet: str, method_name: Optional[str]) -> Optional[str]:
    """
    Extract log level from code snippet.

    Strategy:
    1. Use methodName from Spoon if available (info, warn, error, etc.)
    2. Search for level keywords in code snippet

    Supports multiple frameworks:
    - SLF4J/Log4j/Logback: error, warn, info, debug, trace, fatal
    - Log4j 2.x fluent: atError, atWarn, atInfo, atDebug, atTrace, atFatal
    - Java Util Logging: severe, warning, config, fine, finer, finest

    Args:
        code_snippet: Code context (±3 lines)
        method_name: Method name from Spoon (e.g., "info", "atWarn", "severe")

    Returns:
        Log level (ERROR, WARN, INFO, DEBUG, TRACE, FATAL) or None
    """
    # JUL to standard level mapping
    jul_mapping = {
        'SEVERE': 'ERROR',
        'WARNING': 'WARN',
        'CONFIG': 'INFO',
        'FINE': 'DEBUG',
        'FINER': 'DEBUG',
        'FINEST': 'TRACE'
    }

    # Strategy 1: Use Spoon method name
    if method_name:
        level = method_name.upper().replace('AT', '')

        # Check standard levels
        if level in ['ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE', 'FATAL']:
            return level

        # Map JUL levels to standard
        if level in jul_mapping:
            return jul_mapping[level]

    # Strategy 2: Search in code snippet
    level_pattern = re.compile(
        r'\b(error|warn|info|debug|trace|fatal|'
        r'atError|atWarn|atInfo|atDebug|atTrace|atFatal|'
        r'severe|warning|config|fine|finer|finest)\(',
        re.IGNORECASE
    )
    match = level_pattern.search(code_snippet)
    if match:
        level = match.group(1).upper().replace('AT', '')

        # Map JUL levels to standard
        if level in jul_mapping:
            return jul_mapping[level]

        return level

    return None


def read_code_snippet_expanded(file_path: Path, line: int,
                               cache: Dict[Path, List[str]],
                               context_lines: int = 10) -> str:
    """
    Read expanded code snippet for multi-line pattern detection.

    Args:
        file_path: Absolute path to source file
        line: Line number (1-based)
        cache: File content cache
        context_lines: Lines of context before/after (default 10)

    Returns:
        Code snippet as string
    """
    if file_path not in cache:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                cache[file_path] = f.readlines()
        except Exception:
            cache[file_path] = []

    lines = cache[file_path]
    if not lines:
        return ""

    idx = line - 1
    start = max(0, idx - context_lines)
    end = min(len(lines), idx + context_lines + 1)
    return ''.join(lines[start:end])


def classify_pattern(code_snippet: str, file_path: Path, line: int,
                    cache: Dict[Path, List[str]]) -> str:
    """
    Classify logging pattern with expanded context for multi-line chains.

    Patterns:
    - fluent: Fluent API with structured logging (.atInfo().addKeyValue(...).log())
    - fluent_simple: Fluent API without structured logging (.atInfo().log())
    - lombok: Lombok @Slf4j (log.info(...))
    - traditional: Traditional SLF4J (LOGGER.info(...))

    Args:
        code_snippet: Code context (±3 lines from call site)
        file_path: File path for expanded reading
        line: Line number for expanded reading
        cache: File content cache

    Returns:
        Pattern name
    """
    # Check for fluent API in immediate context (±3 lines)
    if '.atError(' in code_snippet or '.atWarn(' in code_snippet or '.atInfo(' in code_snippet:
        if '.addKeyValue(' in code_snippet:
            return 'fluent'
        return 'fluent_simple'

    # Check for Lombok
    if 'log.error(' in code_snippet or 'log.warn(' in code_snippet or 'log.info(' in code_snippet:
        return 'lombok'

    # For potential traditional calls, check wider context (±10 lines)
    # to catch multi-line fluent chains
    expanded_snippet = read_code_snippet_expanded(file_path, line, cache, context_lines=10)

    fluent_keywords = ['atTrace', 'atDebug', 'atInfo', 'atWarn', 'atError']
    if any(keyword in expanded_snippet for keyword in fluent_keywords):
        # Found fluent API in wider context - this is a multi-line chain
        if '.addKeyValue(' in expanded_snippet:
            return 'fluent'
        return 'fluent_simple'

    # Default: traditional
    return 'traditional'


def extract_message(code_snippet: str) -> Optional[str]:
    """
    Extract log message template.

    Args:
        code_snippet: Code context (±3 lines)

    Returns:
        First string literal (truncated to 60 chars) or None
    """
    # Find string literals in quotes
    matches = re.findall(r'"([^"]*)"', code_snippet)
    if matches:
        msg = matches[0]
        return msg[:60] + '...' if len(msg) > 60 else msg
    return None


def count_parameters(code_snippet: str) -> int:
    """
    Count parameters in log call.

    Strategy: Count {} placeholders or addKeyValue() calls.

    Args:
        code_snippet: Code context (±3 lines)

    Returns:
        Parameter count
    """
    # Count placeholders
    if '{}' in code_snippet:
        return code_snippet.count('{}')

    # Count addKeyValue for fluent API
    if 'addKeyValue' in code_snippet:
        return code_snippet.count('addKeyValue')

    return 0


def enrich_candidates(candidates_data: Dict[str, Any],
                     project_root: Path,
                     debug: bool) -> Dict[str, Any]:
    """
    Enrich candidates with code snippet analysis.

    Reads code at each candidate location to extract:
    - Log level (error, warn, info, debug, trace)
    - Pattern (traditional, fluent_api, fluent_simple, lombok)
    - Message snippet (first string literal, truncated to 60 chars)
    - Parameter count (commas in method call)

    Returns:
        Dict with 'loggers' and 'log_calls' in lsp-inventory.json format
    """
    candidates = candidates_data.get('candidates', [])
    file_cache: Dict[Path, List[str]] = {}  # Cache file contents

    # Separate declarations and calls
    declarations = [c for c in candidates if c['type'] == 'LOGGER_DECLARATION']
    calls = [c for c in candidates if c['type'] == 'LOGGER_CALL']

    # Build loggers list
    loggers = []
    for decl in declarations:
        rel_path = normalize_path(decl['file'], project_root)
        loggers.append({
            'name': decl['name'],
            'type': decl.get('typeName', 'org.slf4j.Logger'),
            'framework': decl.get('framework', 'unknown'),  # slf4j, log4j, log4j2, logback
            'file': rel_path,
            'line': decl['line'],
            'call_count': 0  # Will be updated when processing calls
        })

    # Build log_calls list with enrichment
    log_calls = []
    filtered_count = 0

    for call in calls:
        # Read code snippet
        abs_path = Path(call['file'])
        code_snippet = read_code_snippet_cached(abs_path, call['line'], file_cache)

        # Filter non-log-statements
        if not is_logger_statement(call, code_snippet):
            filtered_count += 1
            continue

        # Extract metadata
        rel_path = normalize_path(call['file'], project_root)
        enriched_call = {
            'id': len(log_calls) + 1,
            'file': rel_path,
            'line': call['line'],
            'logger_name': call.get('name', 'LOGGER'),
            'level': extract_level(code_snippet, call.get('methodName')),
            'pattern': classify_pattern(code_snippet, abs_path, call['line'], file_cache),
            'message_snippet': extract_message(code_snippet),
            'parameter_count': count_parameters(code_snippet),
            # Preserve Spoon metadata for validation and conversion
            'receiver_type': call.get('typeName'),  # org.slf4j.Logger, org.apache.log4j.Logger, etc.
            'framework': call.get('framework', 'unknown'),  # slf4j, log4j, log4j2, logback
            'detection_strategy': call.get('detectionStrategy'),  # known_logger_field, method_name_with_type, etc.
            'needs_validation': call.get('needsValidation', False)
        }

        log_calls.append(enriched_call)

        # Update logger call count
        for logger in loggers:
            if (logger['name'] == enriched_call['logger_name'] and
                logger['file'] == enriched_call['file']):
                logger['call_count'] += 1
                break

        if debug and len(log_calls) % 100 == 0:
            print(f"  Enriched {len(log_calls)}/{len(calls)} calls...", file=sys.stderr)

    print(f"✓ Enriched {len(log_calls)} log calls", file=sys.stderr)
    if filtered_count > 0:
        print(f"  ℹ Filtered {filtered_count} non-log statements (e.g., LoggerFactory.getLogger)", file=sys.stderr)

    return {
        'loggers': loggers,
        'log_calls': log_calls
    }


def write_lsp_inventory(inventory: Dict[str, Any], output_path: Path):
    """
    Write lsp-inventory.json (backward compatible with v2.1.1).

    Format:
    {
      "metadata": {...},
      "loggers": [...],
      "log_calls": [...]
    }
    """
    output = {
        "metadata": {
            "analysis_date": datetime.now().isoformat(),
            "scanner": "spoon+hybrid",
            "version": "3.0.1",
            "total_loggers": len(inventory['loggers']),
            "total_calls": len(inventory['log_calls'])
        },
        "loggers": inventory['loggers'],
        "log_calls": inventory['log_calls']
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"  - {output['metadata']['total_loggers']} loggers", file=sys.stderr)
    print(f"  - {output['metadata']['total_calls']} log calls", file=sys.stderr)


def extract_module_name(file_path: str) -> str:
    """Extract module name from file path (first component)."""
    parts = Path(file_path).parts
    return parts[0] if parts else 'unknown'


def extract_package_name(file_path: str) -> str:
    """Extract package name from file path (between 'java' and filename)."""
    parts = Path(file_path).parts
    try:
        java_idx = parts.index('java') if 'java' in parts else -1
        if java_idx >= 0 and java_idx < len(parts) - 1:
            package_parts = parts[java_idx + 1:-1]  # Exclude filename
            return '.'.join(package_parts) if package_parts else 'default'
    except (ValueError, IndexError):
        pass
    return 'default'


def count_files(hierarchy: Dict) -> int:
    """Count total files in hierarchy."""
    count = 0
    for module in hierarchy.values():
        for package in module.values():
            count += len(package)
    return count


def print_framework_summary(inventory: Dict[str, Any]):
    """
    Print summary of logging framework usage.

    Args:
        inventory: Enriched inventory with loggers and log_calls
    """
    # Count logger declarations by framework
    logger_frameworks = {}
    for logger in inventory['loggers']:
        framework = logger.get('framework', 'unknown')
        logger_frameworks[framework] = logger_frameworks.get(framework, 0) + 1

    # Count log calls by framework
    call_frameworks = {}
    for call in inventory['log_calls']:
        framework = call.get('framework', 'unknown')
        call_frameworks[framework] = call_frameworks.get(framework, 0) + 1

    print("\n[Framework Summary]", file=sys.stderr)

    # Sort by count (descending)
    sorted_calls = sorted(call_frameworks.items(), key=lambda x: x[1], reverse=True)

    if sorted_calls:
        print("  Logger Calls by Framework:", file=sys.stderr)
        for framework, count in sorted_calls:
            percentage = (count / len(inventory['log_calls']) * 100) if inventory['log_calls'] else 0
            framework_display = framework if framework != 'unknown' else 'unknown (type not resolved)'
            print(f"    - {framework_display}: {count} calls ({percentage:.1f}%)", file=sys.stderr)

    # Report non-SLF4J frameworks (migration candidates)
    non_slf4j = {k: v for k, v in call_frameworks.items() if k not in ['slf4j', 'unknown']}
    if non_slf4j:
        total_non_slf4j = sum(non_slf4j.values())
        print(f"\n  ⚠ Found {total_non_slf4j} calls using non-SLF4J frameworks (migration candidates):", file=sys.stderr)
        for framework, count in sorted(non_slf4j.items(), key=lambda x: x[1], reverse=True):
            print(f"    - {framework}: {count} calls", file=sys.stderr)
        print("  💡 Consider migrating these to SLF4J facade for framework independence", file=sys.stderr)


def write_conversion_inventory(inventory: Dict[str, Any],
                               output_path: Path,
                               project_root: Path):
    """
    Write conversion-inventory.json (for convert-logs skill).

    Filters to traditional pattern only, sorts bottom-to-top within files.

    Format:
    {
      "metadata": {...},
      "modules": [
        {
          "name": "module-name",
          "packages": [
            {
              "name": "package.name",
              "files": [
                {
                  "file": "/abs/path/to/File.java",
                  "relativePath": "module/src/main/java/package/File.java",
                  "callCount": 5,
                  "calls": [...]
                }
              ]
            }
          ]
        }
      ]
    }
    """
    # Filter to traditional pattern only
    traditional_calls = [
        call for call in inventory['log_calls']
        if call.get('pattern') == 'traditional'
    ]

    if not traditional_calls:
        print("  ℹ No traditional log calls found - all logs already converted!", file=sys.stderr)
        # Create empty inventory file
        output = {
            "metadata": {
                "analysis_date": datetime.now().isoformat(),
                "project_root": str(project_root),
                "total_files": 0,
                "total_unconverted_calls": 0,
                "partitioning": "module"
            },
            "modules": []
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        return

    # Group by module → package → file
    hierarchy: Dict[str, Dict[str, Dict[str, List]]] = {}
    for call in traditional_calls:
        file_path = call['file']

        # Extract module and package
        module = extract_module_name(file_path)
        package = extract_package_name(file_path)

        # Initialize hierarchy
        if module not in hierarchy:
            hierarchy[module] = {}
        if package not in hierarchy[module]:
            hierarchy[module][package] = {}
        if file_path not in hierarchy[module][package]:
            hierarchy[module][package][file_path] = []

        hierarchy[module][package][file_path].append(call)

    # Sort calls within each file by line number (descending = bottom-to-top)
    for module in hierarchy.values():
        for package in module.values():
            for file_calls in package.values():
                file_calls.sort(key=lambda c: c['line'], reverse=True)

    # Build output structure
    output = {
        "metadata": {
            "analysis_date": datetime.now().isoformat(),
            "project_root": str(project_root),
            "total_files": count_files(hierarchy),
            "total_unconverted_calls": len(traditional_calls),
            "partitioning": "module"
        },
        "modules": []
    }

    # Convert hierarchy to output format
    for module_name, packages in hierarchy.items():
        module_entry = {
            "name": module_name,
            "packages": []
        }

        for package_name, files in packages.items():
            package_entry = {
                "name": package_name,
                "files": []
            }

            for file_path, calls in files.items():
                abs_path = project_root / file_path
                file_entry = {
                    "file": str(abs_path),
                    "relativePath": file_path,
                    "callCount": len(calls),
                    "calls": [
                        {
                            "line": call['line'],
                            "column": 0,
                            "method": call.get('level', 'info').lower() if call.get('level') else 'info',
                            "logger": call.get('logger_name', 'LOGGER'),
                            "snippet": call.get('message_snippet', ''),
                            "context": {
                                "level": call.get('level', 'INFO'),
                                "pattern": call.get('pattern', 'traditional'),
                                "parameter_count": call.get('parameter_count', 0)
                            },
                            "status": "pending",
                            "converted_at": None,
                            "commit": None,
                            # Spoon metadata for validation and conversion
                            "receiver_type": call.get('receiver_type'),
                            "framework": call.get('framework', 'unknown'),
                            "detection_strategy": call.get('detection_strategy'),
                            "needs_validation": call.get('needs_validation', False)
                        }
                        for call in calls
                    ]
                }
                package_entry["files"].append(file_entry)

            module_entry["packages"].append(package_entry)

        output["modules"].append(module_entry)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"  - {output['metadata']['total_unconverted_calls']} unconverted calls", file=sys.stderr)
    print(f"  - {output['metadata']['total_files']} files", file=sys.stderr)
    print(f"  - {len(output['modules'])} modules", file=sys.stderr)


def main():
    """Main entry point."""
    args = parse_args()

    print("=== Hybrid Logger Inventory Generator v3.0.1 ===", file=sys.stderr)
    print(f"Project root: {args.project_root}", file=sys.stderr)

    # Phase 1: Run Spoon scanner
    print("\n[Phase 1] Running Spoon scanner...", file=sys.stderr)
    candidates_file = run_spoon_scanner(args)

    # Phase 2: Load and enrich candidates
    print("\n[Phase 2] Enriching candidates with code context...", file=sys.stderr)
    candidates = load_candidates(candidates_file)
    enriched_inventory = enrich_candidates(candidates, args.project_root, args.debug)

    # Phase 3: Generate outputs
    print("\n[Phase 3] Generating final inventories...", file=sys.stderr)
    write_lsp_inventory(enriched_inventory, args.output)

    conversion_output = args.output.parent / "conversion-inventory.json"
    write_conversion_inventory(enriched_inventory, conversion_output, args.project_root)

    # Print framework summary
    print_framework_summary(enriched_inventory)

    print("\n=== Complete ===", file=sys.stderr)
    print(f"✓ LSP inventory: {args.output}", file=sys.stderr)
    print(f"✓ Conversion inventory: {conversion_output}", file=sys.stderr)


if __name__ == "__main__":
    main()
