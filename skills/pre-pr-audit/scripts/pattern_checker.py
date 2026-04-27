#!/usr/bin/env python3
"""
Pattern-based code quality checker for pre-PR audits.
Detects common issues that would be caught by Copilot/SonarQube.
"""

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from pathlib import Path


@dataclass
class Issue:
    """Represents a code quality issue found during audit."""
    id: int
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # e.g., "Resource Leak", "Silent Failure", "Edge Case"
    file: str
    line: Optional[int]
    pattern: str  # Description of what was detected
    code_snippet: str
    why_it_matters: str
    recommendation: str
    fix_available: bool
    fix_type: Optional[str] = None  # Type of automated fix available


class PatternChecker:
    """Checks code for common quality issues using pattern matching."""

    def __init__(self, changed_files: List[str], base_branch: str, project_patterns: Optional[str] = None):
        self.changed_files = changed_files
        self.base_branch = base_branch
        self.project_patterns = project_patterns
        self.issues: List[Issue] = []
        self.issue_counter = 1

    def check_all(self) -> List[Issue]:
        """Run all pattern checks and return found issues."""
        for file in self.changed_files:
            if not os.path.exists(file):
                continue

            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            # Get git diff to focus on changed lines
            diff_lines = self._get_changed_lines(file)

            # Run universal checks
            self._check_resource_lifecycle(file, content, lines, diff_lines)
            self._check_silent_failures(file, content, lines, diff_lines)
            self._check_edge_cases(file, content, lines, diff_lines)
            self._check_try_finally_scope(file, content, lines, diff_lines)
            self._check_test_coverage(file)

        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        self.issues.sort(key=lambda x: severity_order.get(x.severity, 999))

        return self.issues

    def _get_changed_lines(self, file: str) -> set:
        """Get line numbers that were changed in this file."""
        try:
            # Get diff with line numbers
            result = subprocess.run(
                ['git', 'diff', f'{self.base_branch}...HEAD', '-U0', file],
                capture_output=True, text=True, check=True
            )

            changed_lines = set()
            for line in result.stdout.split('\n'):
                # Parse unified diff format: @@ -old_start,old_count +new_start,new_count @@
                if line.startswith('@@'):
                    match = re.search(r'\+(\d+)(?:,(\d+))?', line)
                    if match:
                        start = int(match.group(1))
                        count = int(match.group(2)) if match.group(2) else 1
                        changed_lines.update(range(start, start + count))

            return changed_lines
        except subprocess.CalledProcessError:
            return set()

    def _check_resource_lifecycle(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check for resource leaks (acquire without release)."""

        # Check for .persist() without .unpersist()
        if '.persist(' in content:
            persist_lines = [i+1 for i, line in enumerate(lines) if '.persist(' in line and i+1 in diff_lines]
            for line_num in persist_lines:
                # Check if unpersist exists in the same method
                if not self._has_cleanup_in_scope(file, line_num, '.unpersist()', lines):
                    snippet = self._get_code_snippet(lines, line_num, context=2)
                    self.issues.append(Issue(
                        id=self.issue_counter,
                        severity="CRITICAL",
                        category="Resource Leak",
                        file=file,
                        line=line_num,
                        pattern=".persist() without .unpersist() in finally",
                        code_snippet=snippet,
                        why_it_matters="RDDs persist in executor memory until explicitly unpersisted. In long-lived SparkSessions, this causes memory leaks and eventually OOM errors.",
                        recommendation="Add .unpersist() in a finally block to ensure memory is released even if exceptions occur.",
                        fix_available=True,
                        fix_type="add_unpersist_finally"
                    ))
                    self.issue_counter += 1

        # Check for .broadcast() without .destroy()
        if 'broadcast(' in content:
            broadcast_lines = [i+1 for i, line in enumerate(lines) if 'broadcast(' in line and i+1 in diff_lines]
            for line_num in broadcast_lines:
                if not self._has_cleanup_in_scope(file, line_num, '.destroy()', lines):
                    snippet = self._get_code_snippet(lines, line_num, context=2)
                    self.issues.append(Issue(
                        id=self.issue_counter,
                        severity="CRITICAL",
                        category="Resource Leak",
                        file=file,
                        line=line_num,
                        pattern="broadcast() without .destroy() in finally",
                        code_snippet=snippet,
                        why_it_matters="Broadcast variables persist in Spark driver memory until explicitly destroyed. This causes memory leaks in long-lived SparkSessions.",
                        recommendation="Add .destroy() in a finally block at method exit to release driver memory.",
                        fix_available=True,
                        fix_type="add_broadcast_destroy_finally"
                    ))
                    self.issue_counter += 1

        # Check for file operations without try-with-resources
        file_patterns = [
            r'new\s+FileInputStream\(',
            r'new\s+FileOutputStream\(',
            r'new\s+BufferedReader\(',
            r'Files\.newBufferedReader\(',
        ]
        for pattern in file_patterns:
            for i, line in enumerate(lines):
                line_num = i + 1
                if line_num not in diff_lines:
                    continue
                if re.search(pattern, line):
                    # Check if it's in a try-with-resources
                    if not self._in_try_with_resources(lines, i):
                        snippet = self._get_code_snippet(lines, line_num, context=2)
                        self.issues.append(Issue(
                            id=self.issue_counter,
                            severity="HIGH",
                            category="Resource Leak",
                            file=file,
                            line=line_num,
                            pattern="File I/O without try-with-resources",
                            code_snippet=snippet,
                            why_it_matters="File handles that aren't properly closed can cause resource exhaustion and file locking issues.",
                            recommendation="Use try-with-resources or add explicit close() in finally block.",
                            fix_available=True,
                            fix_type="add_try_with_resources"
                        ))
                        self.issue_counter += 1

    def _check_silent_failures(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check for logging errors instead of throwing."""

        warning_patterns = [
            (r'LOGGER\.(warn|atWarn)\(', ['duplicate', 'invalid', 'corrupt', 'conflict', 'mismatch']),
            (r'log\.(warn|error)\(', ['duplicate', 'invalid', 'corrupt', 'conflict', 'mismatch']),
        ]

        for logger_pattern, keywords in warning_patterns:
            for i, line in enumerate(lines):
                line_num = i + 1
                if line_num not in diff_lines:
                    continue
                if re.search(logger_pattern, line, re.IGNORECASE):
                    # Check if line contains data quality keywords
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in keywords):
                        snippet = self._get_code_snippet(lines, line_num, context=3)
                        self.issues.append(Issue(
                            id=self.issue_counter,
                            severity="HIGH",
                            category="Silent Failure",
                            file=file,
                            line=line_num,
                            pattern="Warning log for data quality issue (should throw)",
                            code_snippet=snippet,
                            why_it_matters="Logging data quality issues but continuing execution allows corrupt data to propagate downstream, causing bugs that are hard to trace.",
                            recommendation="Replace warning with throw new IllegalStateException(...) including all relevant details (IDs, counts, etc.) in the exception message.",
                            fix_available=True,
                            fix_type="convert_warn_to_throw"
                        ))
                        self.issue_counter += 1

    def _check_edge_cases(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check for missing edge case handling."""

        # Check for map.get() without null handling
        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue

            # Look for .get( but exclude getOrDefault, Optional wrapping, or null checks
            if re.search(r'\.get\s*\(', line) and not any(pattern in line for pattern in [
                'getOrDefault', 'Optional.ofNullable', 'Objects.requireNonNull'
            ]):
                # Check next few lines for null check
                has_null_check = False
                for j in range(i, min(i+3, len(lines))):
                    if '!= null' in lines[j] or '== null' in lines[j]:
                        has_null_check = True
                        break

                if not has_null_check:
                    snippet = self._get_code_snippet(lines, line_num, context=2)
                    self.issues.append(Issue(
                        id=self.issue_counter,
                        severity="MEDIUM",
                        category="Edge Case",
                        file=file,
                        line=line_num,
                        pattern="Map.get() without null check",
                        code_snippet=snippet,
                        why_it_matters="Map.get() returns null if key doesn't exist. Using the result without checking causes NullPointerException.",
                        recommendation="Use getOrDefault(), wrap in Optional.ofNullable(), or add explicit null check with meaningful error.",
                        fix_available=True,
                        fix_type="add_null_check_or_default"
                    ))
                    self.issue_counter += 1

        # Check for Collectors.toMap() without merge function
        if 'Collectors.toMap(' in content:
            for i, line in enumerate(lines):
                line_num = i + 1
                if line_num not in diff_lines:
                    continue
                if 'Collectors.toMap(' in line:
                    # Count arguments - if only 2, no merge function
                    # Simple heuristic: look for 3rd lambda/method reference
                    context = self._get_code_snippet(lines, line_num, context=5)
                    # Check if there are only 2 arguments (keyMapper, valueMapper) or 3 (with merge function)
                    if context.count(',') == 1:  # Only 2 args
                        snippet = self._get_code_snippet(lines, line_num, context=3)
                        self.issues.append(Issue(
                            id=self.issue_counter,
                            severity="HIGH",
                            category="Edge Case",
                            file=file,
                            line=line_num,
                            pattern="Collectors.toMap() without merge function (duplicate keys will throw)",
                            code_snippet=snippet,
                            why_it_matters="Without a merge function, toMap() throws IllegalStateException on duplicate keys. This crash is runtime-only and hard to debug.",
                            recommendation="Add duplicate key validation before collecting, or provide merge function. Validation is preferred - fail fast with details about which keys are duplicated.",
                            fix_available=True,
                            fix_type="add_duplicate_validation"
                        ))
                        self.issue_counter += 1

    def _check_try_finally_scope(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check for operations between acquire and try block."""

        # Look for pattern: resource.acquire(); operation(); try { ... } finally { cleanup }
        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue

            # Check for persist/broadcast followed by operations before try
            if '.persist(' in line or 'broadcast(' in line:
                # Look ahead for try block
                for j in range(i+1, min(i+10, len(lines))):
                    if re.match(r'\s*try\s*\{', lines[j]):
                        # Check if there are statements between acquire and try
                        statements_between = []
                        for k in range(i+1, j):
                            stripped = lines[k].strip()
                            if stripped and not stripped.startswith('//') and stripped != '{' and stripped != '}':
                                statements_between.append(k+1)

                        if statements_between:
                            snippet = self._get_code_snippet(lines, line_num, context=j-i+2)
                            self.issues.append(Issue(
                                id=self.issue_counter,
                                severity="MEDIUM",
                                category="Try/Finally Scope",
                                file=file,
                                line=line_num,
                                pattern="Operations between resource acquisition and try block",
                                code_snippet=snippet,
                                why_it_matters="If operations between acquire and try throw an exception, the finally block never runs and the resource leaks.",
                                recommendation="Move all exception-throwing operations inside the try block, immediately after the try { opening brace.",
                                fix_available=True,
                                fix_type="move_operations_into_try"
                            ))
                            self.issue_counter += 1
                            break

    def _check_test_coverage(self, file: str):
        """Check if new/modified main classes have corresponding tests."""

        if '/src/main/java/' in file:
            # Construct expected test file path
            test_file = file.replace('/src/main/java/', '/src/test/java/')
            # Handle various test naming conventions
            test_file_base = test_file.replace('.java', '')
            possible_test_files = [
                f"{test_file_base}Test.java",
                f"{test_file_base}Tests.java",
                f"{test_file_base}TestCase.java",
            ]

            test_exists = any(os.path.exists(f) for f in possible_test_files)

            if not test_exists:
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="MEDIUM",
                    category="Test Coverage",
                    file=file,
                    line=None,
                    pattern="New/modified class without corresponding test file",
                    code_snippet=f"Main file: {file}\nExpected test: {possible_test_files[0]}",
                    why_it_matters="Code without tests is prone to regressions and makes refactoring risky. Tests document expected behavior.",
                    recommendation="Create test class with happy path, edge cases, and error path tests.",
                    fix_available=True,
                    fix_type="create_test_skeleton"
                ))
                self.issue_counter += 1
            else:
                # Check if test was also modified
                existing_test = next((f for f in possible_test_files if os.path.exists(f)), None)
                if existing_test:
                    # Check if test file is in changed files list
                    if existing_test not in self.changed_files:
                        self.issues.append(Issue(
                            id=self.issue_counter,
                            severity="LOW",
                            category="Test Coverage",
                            file=file,
                            line=None,
                            pattern="Main class modified but test not updated",
                            code_snippet=f"Main file: {file}\nTest file: {existing_test} (not modified)",
                            why_it_matters="When behavior changes, tests should be updated to reflect new expectations or edge cases.",
                            recommendation=f"Review {existing_test} and update tests to cover changes in {file}.",
                            fix_available=False
                        ))
                        self.issue_counter += 1

    def _has_cleanup_in_scope(self, file: str, line_num: int, cleanup_pattern: str, lines: List[str]) -> bool:
        """Check if cleanup exists in the same method scope."""
        # Simple heuristic: look ahead within the same method (until next method or class closing brace)
        method_depth = 0
        found_cleanup = False

        for i in range(line_num, len(lines)):
            line = lines[i]

            # Track brace depth
            method_depth += line.count('{') - line.count('}')

            # Found cleanup
            if cleanup_pattern in line:
                found_cleanup = True
                break

            # Exited method
            if method_depth < 0:
                break

        return found_cleanup

    def _in_try_with_resources(self, lines: List[str], current_line: int) -> bool:
        """Check if current line is inside a try-with-resources block."""
        # Look backwards for try ( pattern
        for i in range(current_line, max(0, current_line - 10), -1):
            if re.match(r'\s*try\s*\(', lines[i]):
                return True
        return False

    def _get_code_snippet(self, lines: List[str], line_num: int, context: int = 3) -> str:
        """Extract code snippet around a line number."""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)

        snippet_lines = []
        for i in range(start, end):
            marker = " >>> " if i == line_num - 1 else "     "
            snippet_lines.append(f"{marker}{i+1:4d}: {lines[i]}")

        return '\n'.join(snippet_lines)


def main():
    parser = argparse.ArgumentParser(description='Pattern-based code quality checker')
    parser.add_argument('--changed-files', required=True, help='Newline-separated list of changed files')
    parser.add_argument('--base-branch', required=True, help='Base branch to compare against')
    parser.add_argument('--project-patterns', help='Project-specific patterns from CLAUDE.md')
    parser.add_argument('--output', default='json', choices=['json', 'text'], help='Output format')

    args = parser.parse_args()

    # Parse changed files
    changed_files = [f.strip() for f in args.changed_files.split('\n') if f.strip()]

    # Run checks
    checker = PatternChecker(changed_files, args.base_branch, args.project_patterns)
    issues = checker.check_all()

    # Output results
    if args.output == 'json':
        print(json.dumps([asdict(issue) for issue in issues], indent=2))
    else:
        if not issues:
            print("✅ No issues found!")
        else:
            print(f"Found {len(issues)} issue(s):\n")
            for issue in issues:
                print(f"#{issue.id} [{issue.severity}] {issue.category}")
                print(f"  File: {issue.file}:{issue.line or 'N/A'}")
                print(f"  Pattern: {issue.pattern}")
                print(f"  Fix available: {'Yes' if issue.fix_available else 'No'}")
                print()


if __name__ == '__main__':
    main()
