#!/usr/bin/env python3
"""
⚠️ DEPRECATED: This file uses JavaParser 3.25.8 which fails on Java 16+ code.

For new transformations, use transform_spoon.py (v3.0.0) with 0% parse failures.

JavaParser limitations:
- Cannot parse Java 16+ syntax (pattern matching, records, sealed classes)
- 0.76% transformation failure rate on modern codebases
- No longer maintained in this plugin

Last working version: v2.0.0
Superseded by: transform_spoon.py (v3.0.0)
Migration: Replace transform_jpype.py with transform_spoon.py in commands

---

Original documentation below:

Python wrapper for JavaParser using JPype.

Transforms traditional SLF4J logging to fluent API using JavaParser's AST API.
Supports parallel batch transformations with threading (JVM thread-safe).

Requires:
  - jpype1 (pip install jpype1)
  - javaparser-core JAR (downloaded automatically or specify path)
"""

import argparse
import json
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

try:
    import jpype
    import jpype.imports
except ImportError:
    print("Error: jpype1 not installed", file=sys.stderr)
    print("Install with: pip install jpype1", file=sys.stderr)
    sys.exit(1)


# JavaParser JAR location
JAVAPARSER_VERSION = "3.25.8"
JAVAPARSER_JAR = Path(__file__).parent / f"javaparser-core-{JAVAPARSER_VERSION}.jar"
JAVAPARSER_URL = f"https://repo1.maven.org/maven2/com/github/javaparser/javaparser-core/{JAVAPARSER_VERSION}/javaparser-core-{JAVAPARSER_VERSION}.jar"

# JVM initialization lock
_jvm_lock = threading.Lock()
_jvm_started = False


def download_javaparser_jar():
    """Download JavaParser JAR if not present"""
    if JAVAPARSER_JAR.exists():
        return

    print(f"Downloading JavaParser {JAVAPARSER_VERSION}...")
    try:
        urllib.request.urlretrieve(JAVAPARSER_URL, JAVAPARSER_JAR)
        print(f"✓ Downloaded to {JAVAPARSER_JAR}")
    except Exception as e:
        print(f"✗ Failed to download JavaParser JAR: {e}", file=sys.stderr)
        print(f"Please download manually from: {JAVAPARSER_URL}", file=sys.stderr)
        sys.exit(1)


def start_jvm():
    """Start JVM with JavaParser on classpath (once per process)"""
    global _jvm_started

    with _jvm_lock:
        if _jvm_started:
            return

        if not JAVAPARSER_JAR.exists():
            download_javaparser_jar()

        print("Starting JVM with JavaParser...")
        # Build classpath: jpype + JavaParser
        classpath = [str(JAVAPARSER_JAR)]

        # Add jpype JAR if installed via system package
        jpype_jar = Path("/usr/share/java/org.jpype.jar")
        if jpype_jar.exists():
            classpath.insert(0, str(jpype_jar))

        jpype.startJVM(classpath=classpath, convertStrings=False)
        _jvm_started = True
        print("✓ JVM started")


def transform_file(args: Tuple[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Transform all log calls in a single file using JavaParser.

    Args:
        args: (file_path, specs_for_file)

    Returns:
        TransformationResult dict
    """
    file_path, specs = args

    try:
        # Import Java classes (after JVM started)
        from com.github.javaparser import JavaParser, StaticJavaParser
        from com.github.javaparser.ast.expr import MethodCallExpr, NameExpr, StringLiteralExpr
        from java.nio.file import Paths
        from java.util import Optional

        # Parse Java file
        java_path = Paths.get(file_path)
        parse_result = StaticJavaParser.parse(java_path)
        cu = parse_result

        successes = []
        failures = []

        # Apply each transformation (bottom-to-top order maintained)
        for spec in specs:
            try:
                transformed = transform_log_statement(cu, spec)
                if transformed:
                    successes.append(spec['line'])
                else:
                    failures.append(spec['line'])
            except Exception as e:
                print(f"Warning: Failed to transform line {spec['line']}: {e}", file=sys.stderr)
                failures.append(spec['line'])

        # Convert to string
        transformed_code = str(cu)

        return {
            'file': file_path,
            'status': 'success' if len(failures) == 0 else 'partial',
            'successCount': len(successes),
            'failureCount': len(failures),
            'errors': [f"Line {line}: Could not transform" for line in failures],
            'transformedCode': transformed_code
        }

    except Exception as e:
        return {
            'file': file_path,
            'status': 'failed',
            'error': str(e),
            'successCount': 0,
            'failureCount': len(specs),
            'errors': [f'Parse or transformation error: {e}'],
            'transformedCode': None
        }


def transform_log_statement(cu, spec: Dict[str, Any]) -> bool:
    """
    Transform a single log statement in the compilation unit.

    Args:
        cu: JavaParser CompilationUnit
        spec: Transformation specification

    Returns:
        True if transformation succeeded, False otherwise
    """
    from com.github.javaparser.ast.expr import MethodCallExpr, NameExpr, StringLiteralExpr

    # Find all MethodCallExpr nodes
    method_calls = cu.findAll(MethodCallExpr)

    target_line = spec['line']
    target_logger = spec['logger']
    target_level = spec['transformation']['level'].lower()

    # Find the target log call
    target_call = None
    for call in method_calls:
        if not call.getBegin().isPresent():
            continue

        line = call.getBegin().get().line
        if line != target_line:
            continue

        # Check if it's the right logger and method
        if not call.getScope().isPresent():
            continue

        scope = call.getScope().get()
        if not isinstance(scope, NameExpr):
            continue

        if str(scope.getNameAsString()) != target_logger:
            continue

        if str(call.getNameAsString()).lower() != target_level:
            continue

        target_call = call
        break

    if target_call is None:
        return False

    # Build fluent API call
    fluent_call = build_fluent_call(spec)

    # Replace the old call with the new one
    target_call.replace(fluent_call)

    return True


def build_fluent_call(spec: Dict[str, Any]):
    """
    Build fluent API call chain from transformation spec.

    Args:
        spec: Transformation specification

    Returns:
        JavaParser MethodCallExpr representing fluent chain
    """
    from com.github.javaparser.ast.expr import MethodCallExpr, NameExpr, StringLiteralExpr
    from com.github.javaparser.ast import NodeList

    t = spec['transformation']
    logger = spec['logger']
    level = t['level']

    # Start with LOGGER.atInfo()
    logger_expr = NameExpr(logger)
    chain = MethodCallExpr(logger_expr, f"at{level.capitalize()}")

    # Add .addKeyValue() for each field
    if t.get('fields'):
        for field in t['fields']:
            key_literal = StringLiteralExpr(field['key'])
            value_expr = NameExpr(field['value'])

            args = NodeList()
            args.add(key_literal)
            args.add(value_expr)

            chain = MethodCallExpr(chain, "addKeyValue", args)

    # Add enrichment fields
    if t.get('enrichment'):
        for key, value in t['enrichment'].items():
            key_literal = StringLiteralExpr(key)
            value_literal = StringLiteralExpr(value)

            args = NodeList()
            args.add(key_literal)
            args.add(value_literal)

            chain = MethodCallExpr(chain, "addKeyValue", args)

    # Add .setCause() if exception present
    if t.get('exception'):
        exception_expr = NameExpr(t['exception'])
        args = NodeList()
        args.add(exception_expr)
        chain = MethodCallExpr(chain, "setCause", args)

    # Add .log("message")
    message_literal = StringLiteralExpr(t['message'])
    args = NodeList()
    args.add(message_literal)
    chain = MethodCallExpr(chain, "log", args)

    return chain


def filter_inventory_by_scope(inventory: Dict[str, Any], scope: str) -> Dict[str, Any]:
    """Filter inventory by scope (module:name or package:name)"""
    if scope.startswith("module:"):
        module_name = scope.split(":", 1)[1]
        inventory['modules'] = [m for m in inventory['modules'] if m['name'] == module_name]
    elif scope.startswith("package:"):
        package_name = scope.split(":", 1)[1]
        for module in inventory['modules']:
            module['packages'] = [p for p in module['packages']
                                  if package_name in p['name']]
    return inventory


def apply_batch_transformations(inventory_path: Path, llm_specs: Dict[Tuple[str, int], Dict[str, Any]],
                                  scope: str = None, workers: int = 6) -> List[Dict[str, Any]]:
    """
    Apply transformations in parallel across files using threading.

    Note: Uses ThreadPoolExecutor (not multiprocessing) because JVM is thread-safe
    but cannot be shared across processes.

    Args:
        inventory_path: Path to conversion-inventory.json
        llm_specs: Dict mapping (file, line) -> transformation spec
        scope: Optional filter (module:foo, package:bar)
        workers: Number of parallel threads

    Returns:
        List of transformation results
    """
    # Load inventory
    with open(inventory_path) as f:
        inventory = json.load(f)

    # Filter by scope if specified
    if scope:
        inventory = filter_inventory_by_scope(inventory, scope)

    # Group specs by file
    file_to_specs: Dict[str, List[Dict[str, Any]]] = {}
    for module in inventory['modules']:
        for package in module['packages']:
            for file_entry in package['files']:
                file_path = file_entry['relativePath']

                # Build transformation specs for this file's pending calls
                specs = []
                for call in file_entry['calls']:
                    if call['status'] != 'pending':
                        continue

                    # Get LLM-generated spec for this call
                    key = (file_path, call['line'])
                    if key in llm_specs:
                        specs.append(llm_specs[key])

                if specs:
                    file_to_specs[file_path] = specs

    if not file_to_specs:
        print("No pending transformations found.")
        return []

    # Parallel transformation using threads (JVM is thread-safe)
    print(f"Processing {len(file_to_specs)} files with {workers} threads...")

    if workers == 1:
        # Sequential for debugging
        results = [transform_file(item) for item in file_to_specs.items()]
    else:
        # Parallel execution with threads
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(transform_file, file_to_specs.items()))

    # Write transformed files
    for result in results:
        if result['status'] in ['success', 'partial'] and result.get('transformedCode'):
            try:
                with open(result['file'], 'w', encoding='utf-8') as f:
                    f.write(result['transformedCode'])
            except Exception as e:
                print(f"✗ Failed to write {result['file']}: {e}", file=sys.stderr)
                result['status'] = 'failed'
                result['errors'].append(f"Write failed: {e}")

    # Summary
    total_success = sum(r['successCount'] for r in results)
    total_failed = sum(r['failureCount'] for r in results)

    print(f"\n✓ Transformation complete:")
    print(f"  - {total_success} calls transformed successfully")
    print(f"  - {total_failed} calls failed (will fall back to LLM Edit)")
    print(f"  - {len([r for r in results if r['status'] == 'success'])} files fully transformed")
    print(f"  - {len([r for r in results if r['status'] == 'partial'])} files partially transformed")
    print(f"  - {len([r for r in results if r['status'] == 'failed'])} files failed")

    return results


def main():
    parser = argparse.ArgumentParser(description='Apply log transformations using JavaParser via JPype')
    parser.add_argument('--batch', type=Path, required=True,
                        help='conversion-inventory.json for batch processing')
    parser.add_argument('--specs', type=Path, required=True,
                        help='LLM-generated transformation specs JSON file')
    parser.add_argument('--scope', help='Scope filter (e.g., module:cds-core, package:org.familysearch...)')
    parser.add_argument('--workers', type=int, default=6,
                        help='Number of parallel threads (default: 6)')
    parser.add_argument('--output', type=Path, help='Output file for results JSON')

    args = parser.parse_args()

    # Start JVM with JavaParser
    start_jvm()

    # Load LLM specs
    with open(args.specs) as f:
        specs_list = json.load(f)

    # Convert specs list to dict keyed by (file, line)
    llm_specs = {}
    for spec in specs_list:
        key = (spec['file'], spec['line'])
        llm_specs[key] = spec

    # Run batch transformation
    results = apply_batch_transformations(
        args.batch,
        llm_specs,
        args.scope,
        args.workers
    )

    # Save results if output specified
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results saved to: {args.output}")
    else:
        # Print results to stdout
        print(json.dumps(results, indent=2))

    # Shutdown JVM
    jpype.shutdownJVM()


if __name__ == '__main__':
    main()
