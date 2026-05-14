#!/usr/bin/env python3
"""
Python wrapper for Spoon transformer using JPype.

Transforms traditional SLF4J logging to fluent API using Spoon's AST API.
Supports parallel batch transformations with threading (JVM thread-safe).

v3.0.0: Migrated from JavaParser to Spoon for 0% parse failures on Java 16+ code.

Requires:
  - jpype1 (pip install jpype1)
  - spoon-transformer.jar (built via build-spoon-transformer.sh)
"""

import argparse
import json
import sys
import tempfile
import threading
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


# Spoon transformer JAR location
SPOON_VERSION = "11.2.0"
SPOON_JAR = Path(__file__).parent / "spoon-transformer.jar"

# JVM initialization lock
_jvm_lock = threading.Lock()
_jvm_started = False


def start_jvm():
    """Start JVM with Spoon transformer on classpath (once per process)"""
    global _jvm_started

    with _jvm_lock:
        if _jvm_started:
            return

        if not SPOON_JAR.exists():
            print(f"Error: Spoon transformer JAR not found: {SPOON_JAR}", file=sys.stderr)
            print(f"Build it with: cd {SPOON_JAR.parent} && ./build-spoon-transformer.sh", file=sys.stderr)
            sys.exit(1)

        print(f"Starting JVM with Spoon transformer (Spoon {SPOON_VERSION})...")
        # Build classpath: jpype + Spoon transformer (fat JAR includes all dependencies)
        classpath = [str(SPOON_JAR)]

        # Add jpype JAR if installed via system package
        jpype_jar = Path("/usr/share/java/org.jpype.jar")
        if jpype_jar.exists():
            classpath.insert(0, str(jpype_jar))

        jpype.startJVM(classpath=classpath, convertStrings=False)
        _jvm_started = True
        print("✓ JVM started")


def transform_file(args: Tuple[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Transform all log calls in a single file using Spoon transformer.

    Args:
        args: (file_path, specs_for_file)

    Returns:
        TransformationResult dict
    """
    file_path, specs = args

    try:
        # Import Java classes (after JVM started)
        from org.familysearch.logging.transformer import SpoonLoggerTransformer
        from java.nio.file import Paths, Files
        from java.nio.charset import StandardCharsets

        # Convert specs to Spoon transformer format
        spoon_specs = []
        for spec in specs:
            t = spec['transformation']
            spoon_spec = {
                'file': file_path,
                'line': spec['line'],
                'logger': spec['logger'],
                'level': t['level'].lower(),
                'fields': t.get('fields', []),
                'message': t['message'],
                'exception': t.get('exception', None),
                'framework': spec.get('framework', 'slf4j'),  # v3.0.2
                'fluentConversion': True  # v3.0.2 - default to true
            }
            spoon_specs.append(spoon_spec)

        # Write specs to temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(spoon_specs, tmp)
            specs_file = tmp.name

        try:
            # Create Java Path objects
            input_path = Paths.get(file_path)
            specs_path = Paths.get(specs_file)

            # Call SpoonLoggerTransformer main method
            # Build args array: --input file --specs specs.json
            args_array = jpype.JArray(jpype.JString)(
                ["--input", str(file_path), "--specs", specs_file]
            )

            # Capture transformed output by reading from temp file
            output_file = tempfile.mktemp(suffix='.java')
            args_array = jpype.JArray(jpype.JString)(
                ["--input", str(file_path), "--specs", specs_file, "--output", output_file]
            )

            # Run transformer
            SpoonLoggerTransformer.main(args_array)

            # Read transformed code
            output_path = Paths.get(output_file)
            transformed_code = str(Files.readString(output_path, StandardCharsets.UTF_8))

            # Clean up temp output
            Files.deleteIfExists(output_path)

            return {
                'file': file_path,
                'status': 'success',
                'successCount': len(specs),
                'failureCount': 0,
                'errors': [],
                'transformedCode': transformed_code
            }

        except Exception as e:
            # Transformation failed
            return {
                'file': file_path,
                'status': 'failed',
                'error': str(e),
                'successCount': 0,
                'failureCount': len(specs),
                'errors': [f'Transformation error: {e}'],
                'transformedCode': None
            }
        finally:
            # Clean up temp specs file
            Path(specs_file).unlink(missing_ok=True)

    except Exception as e:
        return {
            'file': file_path,
            'status': 'failed',
            'error': str(e),
            'successCount': 0,
            'failureCount': len(specs),
            'errors': [f'Setup error: {e}'],
            'transformedCode': None
        }


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


def filter_inventory_by_framework(inventory: Dict[str, Any], target_frameworks: List[str]) -> Dict[str, Any]:
    """Filter conversion inventory to only non-SLF4J frameworks."""
    filtered_modules = []

    for module in inventory['modules']:
        filtered_packages = []

        for package in module['packages']:
            filtered_files = []

            for file_entry in package['files']:
                filtered_calls = [
                    call for call in file_entry['calls']
                    if call.get('framework') in target_frameworks
                ]

                if filtered_calls:
                    file_entry_copy = file_entry.copy()
                    file_entry_copy['calls'] = filtered_calls
                    filtered_files.append(file_entry_copy)

            if filtered_files:
                package_copy = package.copy()
                package_copy['files'] = filtered_files
                filtered_packages.append(package_copy)

        if filtered_packages:
            module_copy = module.copy()
            module_copy['packages'] = filtered_packages
            filtered_modules.append(module_copy)

    inventory_copy = inventory.copy()
    inventory_copy['modules'] = filtered_modules
    return inventory_copy


def count_calls(inventory: Dict[str, Any]) -> int:
    """Count total log calls in inventory."""
    count = 0
    for module in inventory['modules']:
        for package in module['packages']:
            for file_entry in package['files']:
                count += len(file_entry['calls'])
    return count


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
    success_count = sum(1 for r in results if r['status'] == 'success')
    partial_count = sum(1 for r in results if r['status'] == 'partial')
    failed_count = sum(1 for r in results if r['status'] == 'failed')

    print(f"\n=== Transformation Results ===")
    print(f"✓ Success: {success_count} files")
    if partial_count > 0:
        print(f"⚠ Partial: {partial_count} files")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count} files")

    total_transformed = sum(r['successCount'] for r in results)
    total_failed = sum(r['failureCount'] for r in results)
    print(f"\nLog statements: {total_transformed} transformed, {total_failed} failed")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Transform traditional logging to fluent API using Spoon (v3.0.2)"
    )
    parser.add_argument(
        '--specs',
        type=Path,
        required=True,
        help='Transformation specs JSON file (LLM-generated)'
    )
    parser.add_argument(
        '--inventory',
        type=Path,
        help='Conversion inventory JSON (default: .claude/analyze-reports/conversion-inventory.json)'
    )
    parser.add_argument(
        '--scope',
        type=str,
        help='Scope filter (module:name or package:name)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=6,
        help='Number of parallel threads (default: 6)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file for transformation results JSON'
    )

    # Framework migration options (v3.0.2)
    parser.add_argument(
        '--migrate-frameworks',
        action='store_true',
        help='Migrate non-SLF4J frameworks to SLF4J'
    )
    parser.add_argument(
        '--frameworks',
        nargs='+',
        choices=['log4j', 'log4j2', 'logback', 'commons-logging', 'jul'],
        help='Specific frameworks to migrate (default: all non-SLF4J)'
    )

    args = parser.parse_args()

    # Default inventory path
    if not args.inventory:
        args.inventory = Path('.claude/analyze-reports/conversion-inventory.json')

    if not args.inventory.exists():
        print(f"Error: Inventory not found: {args.inventory}", file=sys.stderr)
        print("Run: analyze skill with hybrid_inventory.py first", file=sys.stderr)
        sys.exit(1)

    if not args.specs.exists():
        print(f"Error: Specs file not found: {args.specs}", file=sys.stderr)
        sys.exit(1)

    # Load LLM specs
    with open(args.specs) as f:
        llm_specs_list = json.load(f)

    # Convert to dict keyed by (file, line)
    llm_specs = {}
    for spec in llm_specs_list:
        key = (spec['file'], spec['line'])
        llm_specs[key] = spec

    print(f"Loaded {len(llm_specs)} transformation specs")

    # Load inventory for framework filtering
    with open(args.inventory) as f:
        inventory = json.load(f)

    # Framework migration filtering (v3.0.2)
    if args.migrate_frameworks:
        target_frameworks = args.frameworks or ['log4j', 'log4j2', 'logback', 'commons-logging', 'jul']
        original_count = count_calls(inventory)
        inventory = filter_inventory_by_framework(inventory, target_frameworks)
        filtered_count = count_calls(inventory)

        print(f"\nFramework migration mode: {', '.join(target_frameworks)}")
        print(f"Found {filtered_count} calls to migrate (filtered from {original_count} total)")

        # Write filtered inventory to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(inventory, tmp)
            filtered_inventory_path = Path(tmp.name)
    else:
        filtered_inventory_path = args.inventory

    # Start JVM
    start_jvm()

    # Apply transformations
    results = apply_batch_transformations(
        filtered_inventory_path,
        llm_specs,
        scope=args.scope,
        workers=args.workers
    )

    # Clean up temp file if created
    if args.migrate_frameworks and filtered_inventory_path != args.inventory:
        filtered_inventory_path.unlink(missing_ok=True)

    # Write results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results written to {args.output}")

    # Exit code based on failures
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == '__main__':
    main()
