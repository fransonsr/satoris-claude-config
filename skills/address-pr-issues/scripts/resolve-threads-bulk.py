#!/usr/bin/env python3
"""
Resolve multiple GitHub review threads at once.
Usage: ./resolve-threads-bulk.py <pr_number> [options]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional


def run_gh_graphql(query: str) -> Dict:
    """Execute a GraphQL query via gh CLI."""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)


def resolve_threads_batch(thread_ids: List[str], batch_size: int = 10) -> tuple[int, int]:
    """
    Resolve multiple threads using batched GraphQL mutations.
    Returns (resolved_count, failed_count).
    """
    resolved = 0
    failed = 0

    # Process in batches
    for i in range(0, len(thread_ids), batch_size):
        batch = thread_ids[i:i + batch_size]

        # Build batched mutation with aliases
        mutations = []
        for j, thread_id in enumerate(batch):
            mutations.append(
                f't{j}: resolveReviewThread(input: {{threadId: "{thread_id}"}}) '
                f'{{ thread {{ id isResolved }} }}'
            )

        query = f"mutation {{ {' '.join(mutations)} }}"

        try:
            run_gh_graphql(query)
            resolved += len(batch)
        except subprocess.CalledProcessError as e:
            # Batch failed, try individually
            print(f"  ⚠️  Batch failed: {e.stderr.strip()}")
            print("  Falling back to individual resolution...")

            for thread_id in batch:
                try:
                    query = f'''
                        mutation {{
                            resolveReviewThread(input: {{threadId: "{thread_id}"}}) {{
                                thread {{ id isResolved }}
                            }}
                        }}
                    '''
                    run_gh_graphql(query)
                    resolved += 1
                except subprocess.CalledProcessError:
                    failed += 1

    return resolved, failed


def load_threads(threads_file: Path) -> List[Dict]:
    """Load threads from NDJSON file (one compact JSON object per line)."""
    threads = []
    with open(threads_file) as f:
        for line in f:
            line = line.strip()
            if line:
                threads.append(json.loads(line))
    return threads


def save_threads(threads: List[Dict], threads_file: Path):
    """Save threads to NDJSON file (one compact JSON object per line)."""
    with open(threads_file, 'w') as f:
        for thread in threads:
            f.write(json.dumps(thread) + '\n')


def filter_threads(
    threads: List[Dict],
    thread_ids: Optional[List[str]] = None,
    filter_path: Optional[str] = None,
    filter_line_range: Optional[tuple[int, int]] = None,
    all_unresolved: bool = False
) -> List[Dict]:
    """Filter threads based on criteria."""
    if thread_ids:
        return [t for t in threads if t['threadId'] in thread_ids]

    if filter_path:
        threads = [t for t in threads if filter_path in t.get('path', '')]

    if filter_line_range:
        start, end = filter_line_range
        threads = [t for t in threads if start <= t.get('line', 0) <= end]

    if all_unresolved:
        threads = [t for t in threads if not t.get('isResolved', True)]

    return threads


def main():
    parser = argparse.ArgumentParser(
        description='Resolve multiple GitHub review threads at once',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Resolve specific threads
  %(prog)s 68 --threads PRRT_abc,PRRT_def --message "Fixed integration tests"

  # Resolve all threads in a file
  %(prog)s 68 --filter-path FullExportJobIntegrationTest.java --message "Fixed tests"

  # Resolve all unresolved threads
  %(prog)s 68 --all-unresolved --message "Addressed all review feedback"
        '''
    )

    parser.add_argument('pr_number', type=int, help='Pull request number')
    parser.add_argument('--threads', help='Comma-separated thread IDs')
    parser.add_argument('--file', dest='id_file', help='File with thread IDs (one per line)')
    parser.add_argument('--filter-path', help='Resolve threads where file path matches pattern')
    parser.add_argument('--filter-line', help='Resolve threads in line range (e.g., 200-300)')
    parser.add_argument('--all-unresolved', action='store_true', help='Resolve ALL unresolved threads')
    parser.add_argument('--message', default='Fixed', help='Message for all resolutions (default: Fixed)')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for GraphQL mutations (default: 10)')

    args = parser.parse_args()

    # Check workspace
    workspace_dir = Path(f"/tmp/pr-{args.pr_number}")
    threads_file = workspace_dir / "threads.json"
    api_caps_file = workspace_dir / "api-capabilities.txt"

    if not threads_file.exists() or not api_caps_file.exists():
        print("⚠️  PR state not initialized. Run init-pr-state.sh first.", file=sys.stderr)
        sys.exit(1)

    # Load threads
    all_threads = load_threads(threads_file)

    # Parse thread IDs if specified
    thread_ids = None
    if args.threads:
        thread_ids = [tid.strip() for tid in args.threads.split(',')]
    elif args.id_file:
        with open(args.id_file) as f:
            thread_ids = [line.strip() for line in f if line.strip()]

    # Parse line range
    filter_line_range = None
    if args.filter_line:
        try:
            start, end = map(int, args.filter_line.split('-'))
            filter_line_range = (start, end)
        except ValueError:
            print("❌ Invalid line range format. Use: start-end (e.g., 200-300)", file=sys.stderr)
            sys.exit(1)

    # Filter threads
    threads_to_resolve = filter_threads(
        all_threads,
        thread_ids=thread_ids,
        filter_path=args.filter_path,
        filter_line_range=filter_line_range,
        all_unresolved=args.all_unresolved
    )

    if not threads_to_resolve:
        print("⚠️  No threads to resolve (filter matched zero threads)", file=sys.stderr)
        sys.exit(0)

    # Display summary
    print(f"📍 Resolving {len(threads_to_resolve)} thread(s) with message: \"{args.message}\"")
    print()

    # Show what we're resolving
    for thread in threads_to_resolve:
        path = thread.get('path', 'unknown')
        line = thread.get('line', 'N/A')
        print(f"  {path}:{line}")
    print()

    # Resolve threads
    if len(threads_to_resolve) > 1:
        print(f"  Using batched GraphQL mutations (batch size: {args.batch_size})")
        print()

    thread_ids_to_resolve = [t['threadId'] for t in threads_to_resolve]
    resolved_count, failed_count = resolve_threads_batch(thread_ids_to_resolve, args.batch_size)

    # Update cache to mark threads as resolved
    if resolved_count > 0:
        resolved_ids = set(thread_ids_to_resolve[:resolved_count])
        for thread in all_threads:
            if thread['threadId'] in resolved_ids:
                thread['isResolved'] = True
        save_threads(all_threads, threads_file)

    # Print summary
    print()
    print("━" * 60)
    print(f"✅ Resolved: {resolved_count} thread(s)")
    if failed_count > 0:
        print(f"❌ Failed: {failed_count} thread(s)")
    print("━" * 60)

    sys.exit(0 if failed_count == 0 else 1)


if __name__ == '__main__':
    main()
