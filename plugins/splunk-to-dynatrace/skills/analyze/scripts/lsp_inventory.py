#!/usr/bin/env python3
"""
LSP-based Logger Inventory Generator

Generates structured JSON inventory of all loggers and log call sites in a Java codebase
using Language Server Protocol (jdtls-lsp) for semantic analysis.

Usage:
    python lsp_inventory.py --source src/main/java --output inventory.json
    python lsp_inventory.py --source src/main/java --test src/test/java --output inventory.json

Requirements:
    - Python 3.7+
    - jdtls-lsp plugin running in Claude Code (provides LSP tool)
    - Project must be in Claude Code workspace for LSP to work

Output Format:
    JSON file with:
    - metadata (analysis date, file counts, totals)
    - loggers (all logger declarations with type info)
    - log_calls (all log call sites with context)

Author: FamilySearch Engineering - SATORIS Team
License: © 2026 by Intellectual Reserve, Inc. All rights reserved.
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

#
# NOTE: This script is designed to be invoked by Claude Code's analyze skill.
# The skill will provide LSP query results via the LSP tool.
# This script processes those results and generates structured inventory.
#
# For standalone usage, you would need to:
# 1. Connect to jdtls-lsp server directly
# 2. Send LSP requests (textDocument/documentSymbol, textDocument/references, etc.)
# 3. Process responses
#
# In Claude Code context, the skill handles LSP queries and this script handles
# data structuring and file I/O.
#

@dataclass
class LoggerInfo:
    """Logger field declaration"""
    name: str
    type: str
    file: str
    line: int
    call_count: int = 0

@dataclass
class LogCallInfo:
    """Individual log statement call site"""
    id: int
    file: str
    line: int
    logger_name: str
    level: Optional[str] = None
    pattern: Optional[str] = None
    message_snippet: Optional[str] = None
    parameter_count: int = 0

class LSPInventoryGenerator:
    """
    Generates logger inventory from LSP queries and code reading.

    Workflow:
    1. Receive LSP query results (logger declarations, call sites)
    2. Read code at specific lines for context
    3. Extract log metadata (level, pattern, parameters)
    4. Build structured inventory
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.loggers: List[LoggerInfo] = []
        self.log_calls: List[LogCallInfo] = []
        self.call_id_counter = 1

        # Patterns for extracting log information
        self.level_pattern = re.compile(r'\b(error|warn|info|debug|trace|atError|atWarn|atInfo|atDebug|atTrace)\(', re.IGNORECASE)
        self.param_pattern = re.compile(r',\s*[^,\)]+')  # Count parameters after message

    def add_logger_from_lsp(self, name: str, type_info: str, file_path: str, line: int):
        """
        Add logger from LSP documentSymbol + hover results.

        Args:
            name: Logger field name (LOGGER, log, METRICS_LOGGER, etc.)
            type_info: Type information from LSP hover (contains logger type)
            file_path: Absolute file path
            line: Line number of declaration
        """
        # Verify it's actually a logger type
        if not self._is_logger_type(type_info):
            return

        logger = LoggerInfo(
            name=name,
            type=self._extract_logger_type(type_info),
            file=self._relative_path(file_path),
            line=line
        )
        self.loggers.append(logger)

    def add_log_call_from_lsp(self, logger_name: str, file_path: str, line: int):
        """
        Add log call site from LSP findReferences result.

        Args:
            logger_name: Name of logger field
            file_path: Absolute file path
            line: Line number of log call
        """
        log_call = LogCallInfo(
            id=self.call_id_counter,
            file=self._relative_path(file_path),
            line=line,
            logger_name=logger_name
        )
        self.log_calls.append(log_call)
        self.call_id_counter += 1

        # Update logger call count
        for logger in self.loggers:
            if logger.name == logger_name and logger.file == log_call.file:
                logger.call_count += 1
                break

    def enhance_with_code_context(self, file_path: str, line: int, context_lines: int = 3) -> Dict[str, Any]:
        """
        Read code at specific line to extract log metadata.

        Args:
            file_path: Relative file path
            line: Line number (1-based)
            context_lines: Lines of context before/after

        Returns:
            Dict with extracted metadata (level, pattern, parameters, etc.)
        """
        abs_path = self.project_root / file_path
        if not abs_path.exists():
            return {}

        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Get target line and context
            idx = line - 1  # Convert to 0-based
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            code_block = ''.join(lines[start:end])
            target_line = lines[idx] if idx < len(lines) else ''

            # Extract metadata
            return {
                'level': self._extract_level(target_line),
                'pattern': self._classify_pattern(code_block),
                'message_snippet': self._extract_message(target_line),
                'parameter_count': self._count_parameters(target_line)
            }
        except Exception as e:
            print(f"Warning: Could not read {file_path}:{line} - {e}", file=sys.stderr)
            return {}

    def _is_logger_type(self, type_info: str) -> bool:
        """Check if type info indicates a logger"""
        logger_indicators = ['Logger', 'Log ', 'log4j', 'slf4j', 'logging']
        return any(indicator in type_info for indicator in logger_indicators)

    def _extract_logger_type(self, type_info: str) -> str:
        """Extract clean logger type from hover info"""
        # Common patterns: "org.slf4j.Logger", "org.apache.logging.log4j.Logger"
        lines = type_info.split('\n')
        if lines:
            first_line = lines[0].strip()
            # Remove markdown formatting if present
            first_line = first_line.replace('`', '')
            return first_line
        return "Unknown"

    def _relative_path(self, abs_path: str) -> str:
        """Convert absolute path to project-relative"""
        try:
            return str(Path(abs_path).relative_to(self.project_root))
        except ValueError:
            return abs_path

    def _extract_level(self, line: str) -> Optional[str]:
        """Extract log level from code line"""
        match = self.level_pattern.search(line)
        if match:
            level = match.group(1).upper()
            # Normalize fluent API levels
            level = level.replace('AT', '')
            return level
        return None

    def _classify_pattern(self, code_block: str) -> str:
        """Classify logging pattern"""
        if '.atError(' in code_block or '.atWarn(' in code_block or '.atInfo(' in code_block:
            if '.addKeyValue(' in code_block:
                return 'fluent'
            return 'fluent_simple'
        elif 'log.error(' in code_block or 'log.warn(' in code_block or 'log.info(' in code_block:
            return 'lombok'
        else:
            return 'traditional'

    def _extract_message(self, line: str) -> Optional[str]:
        """Extract log message template (first 60 chars)"""
        # Find string literals in quotes
        matches = re.findall(r'"([^"]*)"', line)
        if matches:
            msg = matches[0]
            return msg[:60] + '...' if len(msg) > 60 else msg
        return None

    def _count_parameters(self, line: str) -> int:
        """Count log parameters (rough estimate)"""
        # Count commas after opening paren (excluding those in strings)
        # This is a rough heuristic
        if '{}' in line:
            return line.count('{}')
        # For fluent API, count addKeyValue calls in vicinity
        if 'addKeyValue' in line:
            return line.count('addKeyValue')
        return 0

    def generate_inventory(self) -> Dict[str, Any]:
        """Generate final inventory JSON structure"""
        return {
            'metadata': {
                'analysis_date': datetime.now().isoformat(),
                'project_root': str(self.project_root),
                'total_files_scanned': len(set(log.file for log in self.log_calls)),
                'total_loggers_found': len(self.loggers),
                'total_log_calls': len(self.log_calls)
            },
            'loggers': [asdict(logger) for logger in self.loggers],
            'log_calls': [asdict(call) for call in self.log_calls]
        }

    def save_inventory(self, output_path: Path):
        """Save inventory to JSON file"""
        inventory = self.generate_inventory()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(inventory, f, indent=2)

        print(f"✓ Inventory saved to: {output_path}")
        print(f"  - {inventory['metadata']['total_loggers_found']} loggers")
        print(f"  - {inventory['metadata']['total_log_calls']} log calls")
        print(f"  - {inventory['metadata']['total_files_scanned']} files")


def main():
    """
    Main entry point.

    Note: This script is typically invoked by Claude Code's analyze skill,
    which provides LSP query results. For standalone use, you would need
    to connect to jdtls-lsp server directly.
    """
    import argparse

    parser = argparse.ArgumentParser(description='Generate LSP-based logger inventory')
    parser.add_argument('--project-root', type=Path, default=Path.cwd(),
                        help='Project root directory (default: current directory)')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output JSON file path')
    parser.add_argument('--input-lsp-results', type=Path,
                        help='JSON file with LSP query results (if running standalone)')

    args = parser.parse_args()

    # Initialize generator
    generator = LSPInventoryGenerator(args.project_root)

    # If LSP results provided, process them
    if args.input_lsp_results and args.input_lsp_results.exists():
        with open(args.input_lsp_results, 'r') as f:
            lsp_results = json.load(f)

        # Process logger declarations
        for logger_data in lsp_results.get('loggers', []):
            generator.add_logger_from_lsp(
                name=logger_data['name'],
                type_info=logger_data['type'],
                file_path=logger_data['file'],
                line=logger_data['line']
            )

        # Process log call sites
        for call_data in lsp_results.get('log_calls', []):
            generator.add_log_call_from_lsp(
                logger_name=call_data['logger_name'],
                file_path=call_data['file'],
                line=call_data['line']
            )

        # Enhance with code context
        for log_call in generator.log_calls:
            context = generator.enhance_with_code_context(log_call.file, log_call.line)
            log_call.level = context.get('level')
            log_call.pattern = context.get('pattern')
            log_call.message_snippet = context.get('message_snippet')
            log_call.parameter_count = context.get('parameter_count', 0)

    else:
        print("Error: This script requires LSP query results.", file=sys.stderr)
        print("In Claude Code context, the analyze skill provides these results.", file=sys.stderr)
        print("For standalone use, provide --input-lsp-results with LSP query output.", file=sys.stderr)
        sys.exit(1)

    # Save inventory
    generator.save_inventory(args.output)


if __name__ == '__main__':
    main()
