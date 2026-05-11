#!/usr/bin/env python3
"""
Python wrapper around JavaParser-based log transformer (subprocess approach).

⚠️ DEPRECATED in v2.0.0 - Use transform_jpype.py instead

This script spawns Java subprocess for each file (overhead ~5-10 seconds per batch).
The new transform_jpype.py uses JPype for in-process JVM (no subprocess overhead).

Kept as FALLBACK if JPype installation has issues.

For new workflows, use: transform_jpype.py

---

Supports parallel batch transformations across files using multiprocessing.

Usage:
  python3 transform.py --batch conversion-inventory.json --specs batch-specs.json --workers 6
  python3 transform.py --batch conversion-inventory.json --scope module:cds-core
"""

import argparse
import json
import multiprocessing as mp
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Any

TRANSFORMER_JAR = Path(__file__).parent / "java-transformer/target/log-transformer-1.0.0.jar"
DEFAULT_WORKER_COUNT = 6  # Conservative default (4-8 range)


def transform_file(args: Tuple[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Worker function: Transform all calls in a single file.

    Args:
        args: (file_path, specs_for_file)

    Returns:
        TransformationResult dict
    """
    file_path, specs = args

    # Build batch spec
    batch_spec = {
        'file': file_path,
        'transformations': specs  # Already sorted bottom-to-top
    }

    # Write temp batch spec file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        spec_path = Path(f.name)
        json.dump(batch_spec, f, indent=2)

    # Call JavaParser transformer
    try:
        result = subprocess.run([
            'java', '-jar', str(TRANSFORMER_JAR),
            str(spec_path),
            file_path
        ], capture_output=True, text=True, check=True, timeout=60)

        # Parse JSON result
        result_data = json.loads(result.stdout)
        result_data['status'] = 'success' if result_data['failureCount'] == 0 else 'partial'
        return result_data

    except subprocess.CalledProcessError as e:
        return {
            'file': file_path,
            'status': 'failed',
            'error': e.stderr if e.stderr else str(e),
            'successCount': 0,
            'failureCount': len(specs),
            'errors': [f"Process failed: {e}"],
            'transformedCode': None
        }
    except subprocess.TimeoutExpired:
        return {
            'file': file_path,
            'status': 'timeout',
            'error': 'JavaParser timed out after 60s',
            'successCount': 0,
            'failureCount': len(specs),
            'errors': ['Timeout after 60 seconds'],
            'transformedCode': None
        }
    except json.JSONDecodeError as e:
        return {
            'file': file_path,
            'status': 'failed',
            'error': f'Could not parse JavaParser output: {e}',
            'successCount': 0,
            'failureCount': len(specs),
            'errors': [f'JSON parse error: {e}'],
            'transformedCode': None
        }
    finally:
        spec_path.unlink(missing_ok=True)


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
                                  scope: str = None, workers: int = DEFAULT_WORKER_COUNT) -> List[Dict[str, Any]]:
    """
    Apply transformations in parallel across files.

    Args:
        inventory_path: Path to conversion-inventory.json
        llm_specs: Dict mapping (file, line) -> transformation spec
        scope: Optional filter (module:foo, package:bar)
        workers: Number of parallel workers

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

    # Parallel transformation
    print(f"Processing {len(file_to_specs)} files with {workers} workers...")

    if workers == 1:
        # Sequential for debugging
        results = [transform_file(item) for item in file_to_specs.items()]
    else:
        # Parallel execution
        with mp.Pool(workers) as pool:
            results = pool.map(transform_file, file_to_specs.items())

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
    print(f"  - {len([r for r in results if r['status'] in ['failed', 'timeout']])} files failed")

    return results


def main():
    parser = argparse.ArgumentParser(description='Apply log transformations using JavaParser')
    parser.add_argument('--batch', type=Path, required=True,
                        help='conversion-inventory.json for batch processing')
    parser.add_argument('--specs', type=Path, required=True,
                        help='LLM-generated transformation specs JSON file')
    parser.add_argument('--scope', help='Scope filter (e.g., module:cds-core, package:org.familysearch...)')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKER_COUNT,
                        help=f'Number of parallel workers (default: {DEFAULT_WORKER_COUNT})')
    parser.add_argument('--output', type=Path, help='Output file for results JSON')

    args = parser.parse_args()

    # Check JAR exists
    if not TRANSFORMER_JAR.exists():
        print(f"✗ Error: {TRANSFORMER_JAR} not found", file=sys.stderr)
        print("Run build.sh first to build the transformer JAR", file=sys.stderr)
        sys.exit(1)

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


if __name__ == '__main__':
    main()
