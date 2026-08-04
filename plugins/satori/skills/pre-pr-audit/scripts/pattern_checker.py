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
import sys
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

    def __init__(self, changed_files: List[str], merge_base: str, project_patterns: Optional[str] = None):
        self.changed_files = changed_files
        self.merge_base = merge_base
        self.project_patterns = project_patterns
        self.issues: List[Issue] = []
        self.issue_counter = 1
        self.scanned_count = 0
        self._diff_cache: Dict[str, tuple] = {}

    def check_all(self) -> List[Issue]:
        """Run all pattern checks and return found issues."""
        self.scanned_count = 0
        skipped_missing = 0
        unreadable = 0
        diff_failed = 0
        self._diff_cache: Dict[str, tuple] = {}  # file -> (content, lines, diff_lines) — one
        # read/diff per file across this whole run; _check_parallel_derivation_constants reuses it
        # below instead of re-reading and re-diffing every file a second time.
        for file in self.changed_files:
            if not os.path.exists(file):
                skipped_missing += 1
                continue

            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
            except (UnicodeDecodeError, OSError) as e:
                print(f"⚠️  Could not read {file} ({e}) — skipping this file.", file=sys.stderr)
                unreadable += 1
                continue

            # Get git diff to focus on changed lines. Counted as "scanned" regardless of whether
            # the diff itself succeeded — the file's content was read and checks did run against
            # it; `diff_failed` tracks the degraded-diff-info case separately so the two are never
            # conflated in the summary below.
            diff_lines, diff_ok = self._get_changed_lines(file, lines)
            if not diff_ok:
                diff_failed += 1
            self.scanned_count += 1
            self._diff_cache[file] = (content, lines, diff_lines)

            # Run universal checks
            self._check_resource_lifecycle(file, content, lines, diff_lines)
            self._check_silent_failures(file, content, lines, diff_lines)
            self._check_edge_cases(file, content, lines, diff_lines)
            self._check_try_finally_scope(file, content, lines, diff_lines)
            self._check_deduplication(file, content, lines, diff_lines)
            self._check_test_coverage(file)
            self._check_tostring_equals(file, content, lines, diff_lines)
            self._check_string_shape_type_proxy(file, content, lines, diff_lines)
            self._check_narrow_catch_on_library_api(file, content, lines, diff_lines)

            # Python-specific checks
            if file.endswith('.py'):
                self._check_python_subprocess_safety(file, content, lines, diff_lines)

        # Cross-file checks (run after per-file loop)
        self._check_parallel_derivation_constants()

        # Scan scope, unconditionally — so "no issues found" and "nothing was actually scanned"
        # are never confused with each other (an empty --changed-files, every path missing on
        # disk, or every file failing to read/diff all reach a clean-looking empty result). Buckets
        # sum to len(changed_files): scanned + skipped_missing + unreadable == total (diff_failed
        # is a subset of scanned, not a fourth bucket, since those files were still checked).
        detail = []
        if skipped_missing:
            detail.append(f"{skipped_missing} missing on disk")
        if unreadable:
            detail.append(f"{unreadable} unreadable")
        if diff_failed:
            detail.append(f"{diff_failed} diff-failed (checked with no line filter — see warnings above)")
        print(f"Scanned {self.scanned_count}/{len(self.changed_files)} requested file(s)"
              + (f" ({', '.join(detail)})" if detail else ""),
              file=sys.stderr)

        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        self.issues.sort(key=lambda x: severity_order.get(x.severity, 999))

        return self.issues

    def _get_changed_lines(self, file: str, lines: List[str]) -> tuple:
        """Get (line numbers changed in this file, whether diff resolution succeeded).

        All lines count as "changed" for an untracked file. `ok=False` on any failure means the
        caller should treat the returned (empty) set as degraded information, not as "verified no
        changes" — distinguishing "diff genuinely found nothing" from "diff computation failed".
        """
        # A brand-new, never-`git add`ed file has no tracked history at merge_base to diff against
        # — `git diff` against it succeeds with empty output, which would otherwise read as "zero
        # changed lines" and make every diff_lines-gated check silently skip the file entirely.
        # This is the same untracked-file blind spot round 4's file-enumeration fix closed one
        # layer up; close it here too, or a brand-new file is enumerated but never actually checked.
        try:
            is_untracked = subprocess.run(
                ['git', 'ls-files', '--others', '--exclude-standard', '--', file],
                capture_output=True, text=True, check=True
            ).stdout.strip() != ''
        except (subprocess.CalledProcessError, OSError, UnicodeDecodeError) as e:
            # A failed tracked/untracked check must not silently default to "tracked" — that would
            # route a brand-new file into the git-diff branch below, which is blind to it. Degrade
            # to "treat as untracked" (checks the whole file) instead, the safer of the two guesses.
            print(f"⚠️  git ls-files --others -- {file} failed ({e}) — treating {file} as untracked "
                  f"(checking the whole file) rather than guessing it's tracked.", file=sys.stderr)
            return set(range(1, len(lines) + 1)), False
        if is_untracked:
            return set(range(1, len(lines) + 1)), True
        try:
            # Two-dot form (no second ref) against the pinned merge-base, NOT a three-dot
            # `{base}...HEAD` commit range — three-dot diffs commit-to-commit and can never see
            # uncommitted working-tree changes, the same bug SKILL.md's own diff-range computations
            # were fixed to avoid (commit 842ced8). merge_base is resolved once by the caller.
            result = subprocess.run(
                ['git', 'diff', self.merge_base, '-U0', '--', file],
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

            return changed_lines, True
        except subprocess.CalledProcessError as e:
            print(f"⚠️  git diff {self.merge_base} -U0 -- {file} failed (exit {e.returncode}): "
                  f"{e.stderr.strip() if e.stderr else '(no stderr)'} — treating {file} as having "
                  f"no changed lines; every diff_lines-gated check will silently skip it.",
                  file=sys.stderr)
            return set(), False
        except UnicodeDecodeError as e:
            print(f"⚠️  git diff output for {file} could not be decoded as UTF-8 ({e}) — "
                  f"treating {file} as having no changed lines; every diff_lines-gated check will "
                  f"silently skip it.", file=sys.stderr)
            return set(), False

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

    def _check_deduplication(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check for list.add() in loops without deduplication (Set or contains() check)."""

        # Pattern: list.add() inside loops without Set or contains() check
        # This is a general pattern that Copilot commonly flags

        for i, line in enumerate(lines):
            line_num = i + 1

            # Skip lines not in diff
            if line_num not in diff_lines:
                continue

            # Check for list.add() pattern
            if '.add(' in line and 'list' in line.lower():
                # Look for enclosing loop (for/while) in previous ~10 lines
                start_idx = max(0, i - 10)
                context_lines = lines[start_idx:i+1]
                has_loop = any(re.search(r'\b(for|while)\s*\(', ctx) for ctx in context_lines)

                if has_loop:
                    # Check if there's Set usage or contains() check nearby
                    # Look within ~20 lines before and after
                    check_start = max(0, i - 20)
                    check_end = min(len(lines), i + 20)
                    scope_lines = lines[check_start:check_end]

                    has_set = any('Set<' in l or 'HashSet' in l or 'TreeSet' in l for l in scope_lines)
                    has_contains = any('.contains(' in l for l in scope_lines)
                    has_visited = any('visited' in l.lower() for l in scope_lines)

                    if not (has_set or has_contains or has_visited):
                        snippet = self._get_code_snippet(lines, line_num, context=3)
                        self.issues.append(Issue(
                            id=self.issue_counter,
                            severity="MEDIUM",
                            category="Missing Deduplication",
                            file=file,
                            line=line_num,
                            pattern="list.add() in loop without deduplication check",
                            code_snippet=snippet,
                            why_it_matters="Adding to a list in a loop without checking for duplicates can create unwanted duplicate entries, especially if the same item is encountered multiple times.",
                            recommendation="Use Set<> instead of List<>, or add a .contains() check before adding, or track visited items in a Set.",
                            fix_available=False
                        ))
                        self.issue_counter += 1

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

    def _check_tostring_equals(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Flag .toString().equals() on non-primitive receivers — fragile on polymorphic types."""
        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue
            if re.search(r'\.toString\(\)\.equals\(', line):
                snippet = self._get_code_snippet(lines, line_num, context=2)
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="HIGH",
                    category="Silent Failure",
                    file=file,
                    line=line_num,
                    pattern=".toString().equals() on potentially polymorphic type",
                    code_snippet=snippet,
                    why_it_matters=(
                        "When the receiver's declared type is an interface or abstract class with "
                        "known subclasses (e.g., expression trees, AST nodes, query builders), "
                        "toString() output differs across subtypes. Equality on toString() silently "
                        "fails for decorated or wrapped instances that represent the same value."
                    ),
                    recommendation=(
                        "Use instanceof checks, a type discriminator (.getKind(), .getClass()), "
                        "or an explicit type-safe equality method instead of comparing toString() output."
                    ),
                    fix_available=False
                ))
                self.issue_counter += 1

    def _check_string_shape_type_proxy(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Flag startsWith/endsWith on toString() used as a type discriminator."""
        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue
            if re.search(r'\.toString\(\)\.(startsWith|endsWith)\(', line):
                snippet = self._get_code_snippet(lines, line_num, context=2)
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="HIGH",
                    category="Type/Name Resolution",
                    file=file,
                    line=line_num,
                    pattern="startsWith/endsWith on toString() used as type discriminator",
                    code_snippet=snippet,
                    why_it_matters=(
                        "Using string shape (e.g., starts with '\"', ends with ')') to detect type "
                        "is fragile. Multiple distinct types can produce the same string shape "
                        "(e.g., a string concatenation expression also starts and ends with '\"' "
                        "in some representations). Use .getKind(), instanceof, or an enum discriminator."
                    ),
                    recommendation=(
                        "Replace shape-based type detection with a proper type check: "
                        "instanceof, .getKind() == Kind.STRING_LITERAL, or an equivalent "
                        "type-safe discriminator provided by the API."
                    ),
                    fix_available=False
                ))
                self.issue_counter += 1

    def _check_parallel_derivation_constants(self):
        """Flag same numeric literal appearing in multiple changed files (parallel derivation smell)."""
        constant_locations: Dict[str, List[tuple]] = {}

        # Reuse check_all's per-file cache — this check ran a SECOND read+diff of every file
        # (once here, once in check_all's own loop) until this fix; a file missing/unreadable/
        # diff-failed was already logged and counted once there, so don't re-derive or re-warn.
        for file, (_content, lines, diff_lines) in self._diff_cache.items():
            for i, line in enumerate(lines):
                line_num = i + 1
                if line_num not in diff_lines:
                    continue
                for match in re.finditer(r'\b(\d{2,4})\b', line):
                    val = match.group(1)
                    if int(val) in {10, 16, 32, 64, 100, 128, 256, 512, 1000, 1024}:
                        continue
                    if val not in constant_locations:
                        constant_locations[val] = []
                    constant_locations[val].append((file, line_num, self._get_code_snippet(lines, line_num, context=1)))

        for val, locations in constant_locations.items():
            files_involved = {loc[0] for loc in locations}
            if len(files_involved) >= 2:
                snippet = '\n'.join(f"  {loc[0]}:{loc[1]}\n{loc[2]}" for loc in locations[:4])
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="MEDIUM",
                    category="Parallel Derivation",
                    file=locations[0][0],
                    line=locations[0][1],
                    pattern=f"Numeric constant {val} appears in {len(files_involved)} files — possible parallel derivation",
                    code_snippet=snippet,
                    why_it_matters=(
                        f"The same value ({val}) is hardcoded independently in multiple files. "
                        "If this controls truncation, padding, or a derived key, the two "
                        "computations must agree exactly. Independent copies can silently diverge "
                        "when one is updated and the other is not."
                    ),
                    recommendation=(
                        f"Extract {val} to a shared constant in a single location. "
                        "Both files should import and use the same constant."
                    ),
                    fix_available=False
                ))
                self.issue_counter += 1

    def _check_narrow_catch_on_library_api(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Flag catch blocks for specific RuntimeException subtypes on library/JDK boundaries."""
        specific_catch_pattern = re.compile(
            r'\bcatch\s*\(\s*([A-Z][A-Za-z]*Exception|[A-Z][A-Za-z]*Error)\s+\w+\s*\)'
        )
        broad_types = {
            'Exception', 'RuntimeException', 'IOException', 'Error',
            'Throwable', 'SQLException', 'InterruptedException'
        }
        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue
            match = specific_catch_pattern.search(line)
            if match:
                caught_type = match.group(1)
                if caught_type in broad_types:
                    continue
                context_start = max(0, i - 5)
                context_lines = lines[context_start:i]
                has_library_call = any(
                    re.search(r'\b(java|javax|com\.sun|org\.slf4j|org\.apache|com\.google)\b', ctx)
                    for ctx in context_lines
                )
                if has_library_call:
                    snippet = self._get_code_snippet(lines, line_num, context=4)
                    self.issues.append(Issue(
                        id=self.issue_counter,
                        severity="HIGH",
                        category="Edge Case",
                        file=file,
                        line=line_num,
                        pattern=f"catch ({caught_type}) on library/JDK call — may miss sibling exception types",
                        code_snippet=snippet,
                        why_it_matters=(
                            f"Catching {caught_type} specifically may not cover all exception subtypes "
                            "that the library or JDK throws. The API contract often only documents "
                            "'may throw RuntimeException' without committing to a specific subtype. "
                            "A different JDK implementation or library version can throw a sibling "
                            "exception that escapes the catch."
                        ),
                        recommendation=(
                            "Catch the broadest exception type the API documents (often RuntimeException "
                            "or Exception), or catch multiple sibling types. Verify the API's Javadoc "
                            "to confirm which exception subtypes are possible."
                        ),
                        fix_available=False
                    ))
                    self.issue_counter += 1

    def _check_python_subprocess_safety(self, file: str, content: str, lines: List[str], diff_lines: set):
        """Check subprocess.run/Popen calls for cwd, timeout, TimeoutExpired handler, and executable guard."""
        call_pattern = re.compile(r'\bsubprocess\.(run|Popen)\s*\(')

        for i, line in enumerate(lines):
            line_num = i + 1
            if line_num not in diff_lines:
                continue
            if not call_pattern.search(line):
                continue

            # Gather context window for the call site
            window_start = max(0, i - 15)
            window_end = min(len(lines), i + 11)
            window = lines[window_start:window_end]
            window_text = '\n'.join(window)

            # Check for cwd= argument (HIGH — wrong directory silently breaks command)
            if 'cwd=' not in window_text[:window_text.find('\n', window_text.find(lines[i]))+200 if '\n' in window_text else len(window_text)]:
                # More precisely: check within ~10 lines after the call for cwd=
                call_context = '\n'.join(lines[i:min(i + 10, len(lines))])
                if 'cwd=' not in call_context:
                    snippet = self._get_code_snippet(lines, line_num, context=3)
                    self.issues.append(Issue(
                        id=self.issue_counter,
                        severity="HIGH",
                        category="Subprocess Safety",
                        file=file,
                        line=line_num,
                        pattern="subprocess call missing cwd= argument",
                        code_snippet=snippet,
                        why_it_matters="Without cwd=, the subprocess inherits the caller's working directory, which may differ from the expected directory and silently produce wrong results.",
                        recommendation="Add cwd= to specify the working directory explicitly.",
                        fix_available=False
                    ))
                    self.issue_counter += 1

            # Check for timeout= argument (HIGH — process can hang indefinitely)
            call_context = '\n'.join(lines[i:min(i + 10, len(lines))])
            if 'timeout=' not in call_context:
                snippet = self._get_code_snippet(lines, line_num, context=3)
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="HIGH",
                    category="Subprocess Safety",
                    file=file,
                    line=line_num,
                    pattern="subprocess call missing timeout= argument",
                    code_snippet=snippet,
                    why_it_matters="Without timeout=, the subprocess can hang indefinitely, blocking the process forever.",
                    recommendation="Add timeout= to limit how long the subprocess can run.",
                    fix_available=False
                ))
                self.issue_counter += 1

            # Check for TimeoutExpired handler (HIGH — unhandled hang on timeout)
            broader_context = '\n'.join(lines[max(0, i - 5):min(len(lines), i + 20)])
            if 'subprocess.TimeoutExpired' not in broader_context:
                snippet = self._get_code_snippet(lines, line_num, context=3)
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="HIGH",
                    category="Subprocess Safety",
                    file=file,
                    line=line_num,
                    pattern="subprocess call missing except subprocess.TimeoutExpired handler",
                    code_snippet=snippet,
                    why_it_matters="Without a TimeoutExpired handler, a timed-out subprocess raises an unhandled exception.",
                    recommendation="Add `except subprocess.TimeoutExpired` to handle the case where the subprocess exceeds its timeout.",
                    fix_available=False
                ))
                self.issue_counter += 1

            # Check for executable guard: shutil.which( or os.path.exists( within ~15 lines above (MEDIUM)
            guard_context = '\n'.join(lines[max(0, i - 15):i])
            if 'shutil.which(' not in guard_context and 'os.path.exists(' not in guard_context:
                snippet = self._get_code_snippet(lines, line_num, context=3)
                self.issues.append(Issue(
                    id=self.issue_counter,
                    severity="MEDIUM",
                    category="Subprocess Safety",
                    file=file,
                    line=line_num,
                    pattern="subprocess call missing executable existence check (shutil.which or os.path.exists)",
                    code_snippet=snippet,
                    why_it_matters="Calling a nonexistent or uninstalled executable raises FileNotFoundError at runtime with no helpful context.",
                    recommendation="Add `shutil.which('executable')` or `os.path.exists(path)` guard before the subprocess call.",
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
    parser.add_argument('--merge-base', required=True, help='Merge-base commit to diff against (two-dot form — includes uncommitted working-tree changes)')
    parser.add_argument('--project-patterns', help='Project-specific patterns from CLAUDE.md')
    parser.add_argument('--output', default='json', choices=['json', 'text'], help='Output format')

    args = parser.parse_args()

    # Parse changed files
    changed_files = [f.strip() for f in args.changed_files.split('\n') if f.strip()]

    # Run checks
    checker = PatternChecker(changed_files, args.merge_base, args.project_patterns)
    issues = checker.check_all()

    # Output results
    if args.output == 'json':
        print(json.dumps([asdict(issue) for issue in issues], indent=2))
    else:
        if not issues:
            if checker.scanned_count == 0:
                print(f"⚠️  0 files scanned — nothing was checked (requested {len(changed_files)}).")
            else:
                print(f"✅ No issues found in {checker.scanned_count} file(s)!")
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
