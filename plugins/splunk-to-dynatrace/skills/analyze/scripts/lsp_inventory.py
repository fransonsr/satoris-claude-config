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
import subprocess
import platform
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

#
# NOTE: This script now supports both Claude Code integration and standalone usage.
# - In Claude Code: The skill provides LSP query results via the LSP tool
# - Standalone: The script spawns jdtls-lsp server and queries it directly
#
# Standalone usage requires jdtls-lsp installed at:
# - $JDTLS_HOME/bin/jdtls.py
# - ~/.local/share/jdtls/bin/jdtls.py
# - /usr/share/jdtls/bin/jdtls.py
#

# ============================================================================
# JSON-RPC Communication Layer for LSP
# ============================================================================

def send_lsp_message(process: subprocess.Popen, message: dict, debug: bool = False) -> None:
    """Send JSON-RPC message with Content-Length header."""
    payload = json.dumps(message)
    content = f"Content-Length: {len(payload)}\r\n\r\n{payload}"

    if debug:
        # Show abbreviated message for readability
        method = message.get('method', message.get('id', 'notification'))
        print(f"→ LSP: {method}", file=sys.stderr)
        if len(payload) < 500:
            print(f"  {payload}", file=sys.stderr)

    process.stdin.write(content.encode('utf-8'))
    process.stdin.flush()


def read_lsp_message(process: subprocess.Popen, debug: bool = False) -> dict:
    """Read JSON-RPC response (parse headers, then JSON body)."""
    # Read headers until blank line
    headers = {}
    while True:
        line = process.stdout.readline().decode('utf-8').strip()
        if not line:
            break
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()

    # Read content based on Content-Length
    content_length = int(headers.get('Content-Length', 0))
    if content_length > 0:
        content = process.stdout.read(content_length).decode('utf-8')
        response = json.loads(content)

        if debug:
            # Show abbreviated response
            msg_type = 'response' if 'id' in response else 'notification'
            method = response.get('method', response.get('id', '?'))
            print(f"← LSP {msg_type}: {method}", file=sys.stderr)
            if 'error' in response:
                print(f"  ERROR: {response['error']}", file=sys.stderr)

        return response

    return {}


def send_lsp_request(process: subprocess.Popen, method: str, params: dict, request_id: int, debug: bool = False) -> dict:
    """Send LSP request and wait for response."""
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
    }
    send_lsp_message(process, request, debug)

    # Read responses until we get the matching ID
    while True:
        response = read_lsp_message(process, debug)
        if response.get('id') == request_id:
            return response
        # Ignore notifications (no 'id' field)


# ============================================================================
# jdtls Server Management
# ============================================================================

def find_jdtls_installation() -> Optional[Path]:
    """Find jdtls installation directory."""
    # Check environment variable
    if 'JDTLS_HOME' in os.environ:
        path = Path(os.environ['JDTLS_HOME'])
        if path.exists():
            return path

    # Check standard locations
    standard_locations = [
        Path.home() / '.local' / 'share' / 'jdtls',
        Path('/usr/share/jdtls'),
    ]

    for location in standard_locations:
        if location.exists() and (location / 'bin' / 'jdtls.py').exists():
            return location

    return None


def find_equinox_launcher(jdtls_home: Path) -> Optional[Path]:
    """Find equinox launcher JAR."""
    plugins_dir = jdtls_home / 'plugins'
    launcher_pattern = 'org.eclipse.equinox.launcher_*.jar'

    launchers = list(plugins_dir.glob(launcher_pattern))
    if launchers:
        return launchers[0]

    return None


def spawn_jdtls_server(project_root: Path, debug: bool = False) -> subprocess.Popen:
    """
    Spawn jdtls-lsp server for LSP queries.

    Returns subprocess with stdin/stdout for JSON-RPC communication.
    """
    # Find jdtls installation
    jdtls_home = find_jdtls_installation()
    if not jdtls_home:
        print("ERROR: jdtls-lsp server not found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Searched locations:", file=sys.stderr)
        print("  - $JDTLS_HOME", file=sys.stderr)
        print("  - ~/.local/share/jdtls/", file=sys.stderr)
        print("  - /usr/share/jdtls/", file=sys.stderr)
        print("", file=sys.stderr)
        print("Pattern-based matching is NOT used because it misses 40-60% of log statements.", file=sys.stderr)
        print("Install jdtls-lsp or use Claude Code which includes it.", file=sys.stderr)
        sys.exit(1)

    # Find launcher JAR
    launcher_jar = find_equinox_launcher(jdtls_home)
    if not launcher_jar:
        print(f"ERROR: Cannot find equinox launcher in {jdtls_home}/plugins/", file=sys.stderr)
        sys.exit(1)

    # Determine config directory (Linux/Mac/Windows)
    system = platform.system()
    if system == 'Linux':
        config_dir = jdtls_home / 'config_linux'
    elif system == 'Darwin':
        config_dir = jdtls_home / 'config_mac'
    elif system == 'Windows':
        config_dir = jdtls_home / 'config_win'
    else:
        config_dir = jdtls_home / 'config_linux'  # Default fallback

    # Create workspace directory
    cache_dir = Path.home() / '.cache' / 'jdtls'
    workspace_hash = hashlib.sha1(str(project_root).encode()).hexdigest()[:8]
    workspace_dir = cache_dir / f'lsp-inventory-{workspace_hash}'
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Find Java executable
    java_exec = 'java'
    if 'JAVA_HOME' in os.environ:
        java_home = Path(os.environ['JAVA_HOME'])
        java_candidate = java_home / 'bin' / 'java'
        if java_candidate.exists():
            java_exec = str(java_candidate)

    # Build command (based on jdtls.py logic)
    cmd = [
        java_exec,
        '-Declipse.application=org.eclipse.jdt.ls.core.id1',
        '-Dosgi.bundles.defaultStartLevel=4',
        '-Declipse.product=org.eclipse.jdt.ls.core.product',
        '-Dosgi.checkConfiguration=true',
        f'-Dosgi.sharedConfiguration.area={config_dir}',
        '-Dosgi.sharedConfiguration.area.readOnly=true',
        '-Dosgi.configuration.cascaded=true',
        '-Xms1G',
        '-Xmx2G',  # Increase heap for large projects
        '--add-modules=ALL-SYSTEM',
        '--add-opens', 'java.base/java.util=ALL-UNNAMED',
        '--add-opens', 'java.base/java.lang=ALL-UNNAMED',
        '-jar', str(launcher_jar),
        '-data', str(workspace_dir)
    ]

    # Start subprocess with stdio pipes
    if debug:
        print(f"Starting jdtls-lsp server with workspace: {workspace_dir}", file=sys.stderr)
        print(f"Command: {' '.join(cmd[:10])}...", file=sys.stderr)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if debug else subprocess.DEVNULL,  # Show errors in debug mode
        cwd=str(project_root)
    )

    return process


# ============================================================================
# LSP Session Management
# ============================================================================

def initialize_lsp_session(process: subprocess.Popen, project_root: Path, request_id: int, debug: bool = False) -> dict:
    """Send LSP initialize request with enhanced capabilities."""
    params = {
        "processId": os.getpid(),
        "rootUri": f"file://{project_root.absolute()}",
        "capabilities": {
            "workspace": {
                "workspaceFolders": True,
                "symbol": {
                    "symbolKind": {
                        "valueSet": list(range(1, 27))  # All symbol kinds
                    }
                }
            },
            "textDocument": {
                "documentSymbol": {
                    "hierarchicalDocumentSymbolSupport": True,
                    "symbolKind": {
                        "valueSet": list(range(1, 27))
                    }
                },
                "hover": {
                    "contentFormat": ["markdown", "plaintext"]
                },
                "references": {
                    "dynamicRegistration": False
                }
            }
        },
        "initializationOptions": {
            "settings": {
                "java": {
                    "autobuild": {"enabled": True},
                    "maven": {"downloadSources": False},
                    "referencesCodeLens": {"enabled": False},
                    "implementationsCodeLens": {"enabled": False}
                }
            }
        }
    }

    response = send_lsp_request(process, "initialize", params, request_id, debug)

    # Check for errors
    if "error" in response:
        raise RuntimeError(f"LSP initialization failed: {response['error']}")

    if debug:
        print("✓ LSP initialized successfully", file=sys.stderr)

    # Send initialized notification
    send_lsp_message(process, {
        "jsonrpc": "2.0",
        "method": "initialized",
        "params": {}
    }, debug)

    return response


def wait_for_workspace_ready(process: subprocess.Popen, request_id: int, timeout: int = 120, debug: bool = False) -> int:
    """
    Wait for jdtls workspace to finish indexing.

    Polls workspace/symbol query until it returns non-empty results or timeout.

    Returns: Updated request_id after polling
    """
    start_time = time.time()
    if debug:
        print("Waiting for jdtls workspace indexing...", file=sys.stderr)

    while time.time() - start_time < timeout:
        # Poll with workspace/symbol query
        response = send_lsp_request(process, "workspace/symbol", {"query": ""}, request_id, debug=False)  # Don't spam debug logs
        request_id += 1

        if debug:
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:  # Report every 5 seconds
                print(f"[{elapsed}s] Polling workspace readiness...", file=sys.stderr)

        # Check for error
        if "error" in response:
            if debug:
                print(f"  Error: {response['error'].get('message')}", file=sys.stderr)
            time.sleep(2)
            continue

        # Check for valid result
        result = response.get("result")
        if result is not None and len(result) > 0:
            if debug:
                print(f"✓ Workspace ready after {int(time.time() - start_time)}s ({len(result)} symbols indexed)", file=sys.stderr)
            return request_id

        time.sleep(2)

    raise TimeoutError(f"jdtls workspace not ready after {timeout}s")


def validate_lsp_communication(process: subprocess.Popen, project_root: Path, request_id: int, debug: bool = False) -> int:
    """
    Validate LSP communication with a known test file.

    For cds2-root, tests ServiceJob.java which should have LOGGER at line 51.

    Returns: Updated request_id
    """
    # Find a known test file
    test_candidates = [
        project_root / "cds-core/src/main/java/org/familysearch/cds/core/async/ServiceJob.java",
        # Add more common paths as fallback
    ]

    test_file = None
    for candidate in test_candidates:
        if candidate.exists():
            test_file = candidate
            break

    if not test_file:
        if debug:
            print("⚠ No test file found for LSP validation, proceeding anyway...", file=sys.stderr)
        return request_id

    # Query symbols (we'll define the enhanced query_document_symbol below)
    file_uri = f"file://{test_file.absolute()}"
    symbols = query_document_symbol(process, file_uri, request_id, debug)
    request_id += 1

    # Check for expected logger
    logger_found = any(
        s.get("name") == "LOGGER" and s.get("kind") in [8, 14, "Field", "Constant"]
        for s in symbols
    )

    if logger_found:
        if debug:
            print(f"✓ LSP validation successful (found known logger in {test_file.name})", file=sys.stderr)
    else:
        print(f"ERROR: LSP validation failed - known logger not found in {test_file}", file=sys.stderr)
        print(f"Found {len(symbols)} symbols, but no LOGGER field", file=sys.stderr)
        if debug and len(symbols) > 0:
            print("Sample symbols:", file=sys.stderr)
            for sym in symbols[:5]:
                print(f"  - {sym.get('name')} ({sym.get('kind')})", file=sys.stderr)
        raise RuntimeError("LSP communication broken - cannot proceed")

    return request_id


def shutdown_lsp_session(process: subprocess.Popen, request_id: int):
    """Send LSP shutdown and exit."""
    send_lsp_request(process, "shutdown", {}, request_id)

    send_lsp_message(process, {
        "jsonrpc": "2.0",
        "method": "exit",
        "params": {}
    })

    process.wait(timeout=5)


# ============================================================================
# LSP Query Functions
# ============================================================================

def flatten_symbols(symbols: List[dict]) -> List[dict]:
    """Flatten hierarchical symbol structure."""
    flat = []
    for symbol in symbols:
        flat.append(symbol)
        # Recursively flatten children
        if 'children' in symbol:
            flat.extend(flatten_symbols(symbol['children']))
    return flat


def query_document_symbol(process: subprocess.Popen, file_uri: str, request_id: int, debug: bool = False) -> List[dict]:
    """Query textDocument/documentSymbol for all symbols in file."""
    params = {
        "textDocument": {
            "uri": file_uri
        }
    }

    response = send_lsp_request(process, "textDocument/documentSymbol", params, request_id, debug)

    # Check for error
    if "error" in response:
        error_msg = response["error"].get("message", "Unknown error")
        if debug:
            print(f"  ✗ documentSymbol error: {error_msg}", file=sys.stderr)
        return []

    # Check for valid result
    result = response.get("result")
    if result is None:
        return []

    # Handle hierarchical symbols (flatten if needed)
    symbols = flatten_symbols(result)
    return symbols


def query_hover(process: subprocess.Popen, file_uri: str, line: int, character: int, request_id: int, debug: bool = False) -> str:
    """Query textDocument/hover for type info at position."""
    params = {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character}
    }

    response = send_lsp_request(process, "textDocument/hover", params, request_id, debug)

    # Check for error
    if "error" in response:
        if debug:
            print(f"  ✗ hover error: {response['error'].get('message')}", file=sys.stderr)
        return ""

    # Extract hover text from response
    result = response.get("result")
    if result is None:
        return ""

    contents = result.get("contents", {})

    # Handle different content formats
    if isinstance(contents, str):
        return contents
    elif isinstance(contents, dict):
        return contents.get("value", "")
    elif isinstance(contents, list):
        return " ".join(str(c) for c in contents)

    return ""


def query_references(process: subprocess.Popen, file_uri: str, line: int, character: int, request_id: int, debug: bool = False) -> List[dict]:
    """Query textDocument/references for all usages of symbol."""
    params = {
        "textDocument": {"uri": file_uri},
        "position": {"line": line, "character": character},
        "context": {"includeDeclaration": True}
    }

    response = send_lsp_request(process, "textDocument/references", params, request_id, debug)

    # Check for error
    if "error" in response:
        if debug:
            print(f"  ✗ references error: {response['error'].get('message')}", file=sys.stderr)
        return []

    # Check for valid result
    result = response.get("result")
    if result is None:
        return []

    return result


# ============================================================================
# Multi-Module Discovery
# ============================================================================

def discover_modules(project_root: Path) -> List[Path]:
    """
    Find all Maven/Gradle modules in project.

    Returns list of module root directories.
    """
    modules = []

    # Find all pom.xml and build.gradle files
    pom_files = list(project_root.rglob("pom.xml"))
    gradle_files = list(project_root.rglob("build.gradle"))

    for build_file in pom_files + gradle_files:
        module_root = build_file.parent

        # Check for source directories
        main_java = module_root / "src" / "main" / "java"
        test_java = module_root / "src" / "test" / "java"

        if main_java.exists() or test_java.exists():
            modules.append(module_root)

    # If no modules found, treat project root as single module
    if not modules:
        modules.append(project_root)

    print(f"Discovered {len(modules)} modules:", file=sys.stderr)
    for mod in sorted(modules):
        rel_path = mod.relative_to(project_root) if mod != project_root else Path('.')
        print(f"  - {rel_path}", file=sys.stderr)

    return modules


def get_module_name(file_path: Path, project_root: Path) -> str:
    """Extract module name from file path."""
    try:
        rel_path = file_path.relative_to(project_root)
        parts = rel_path.parts

        # First directory component is module name
        if len(parts) > 0 and parts[0] != 'src':
            return parts[0]

        return "root"
    except ValueError:
        return "unknown"


def discover_java_files(source_dirs: List[Path]) -> List[Path]:
    """Find all .java files in source directories."""
    java_files = []

    for source_dir in source_dirs:
        if source_dir.exists():
            files = list(source_dir.rglob("*.java"))
            java_files.extend(files)

    print(f"Found {len(java_files)} Java files", file=sys.stderr)
    return java_files


# ============================================================================
# Helper Functions for Logger Discovery
# ============================================================================

def extract_type_from_hover(hover_text: str) -> str:
    """Extract clean type name from hover text."""
    lines = hover_text.split('\n')
    if lines:
        first_line = lines[0].strip()
        # Remove markdown formatting
        first_line = first_line.replace('`', '').replace('java', '').strip()
        return first_line
    return "Unknown"


def get_symbol_kind_name(kind: int) -> str:
    """Convert symbol kind number to name."""
    kinds = {
        1: "File", 2: "Module", 3: "Namespace", 4: "Package",
        5: "Class", 6: "Method", 7: "Property", 8: "Field",
        9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
        13: "Variable", 14: "Constant", 15: "String", 16: "Number"
    }
    return kinds.get(kind, str(kind))


# ============================================================================
# Main Logger Discovery Orchestration
# ============================================================================

def discover_loggers_via_lsp(source_dirs: List[Path], project_root: Path, auto_discover: bool = False, debug: bool = False) -> dict:
    """
    Discover all loggers using LSP semantic analysis.

    Returns dict with loggers and log_calls (with module attribution).
    """
    # 1. Discover modules if auto-discover enabled
    if auto_discover:
        modules = discover_modules(project_root)
        source_dirs = []
        for module in modules:
            main_java = module / "src" / "main" / "java"
            test_java = module / "src" / "test" / "java"
            if main_java.exists():
                source_dirs.append(main_java)
            if test_java.exists():
                source_dirs.append(test_java)

        print(f"Auto-discovered {len(source_dirs)} source directories", file=sys.stderr)

    # 2. Find all Java files
    java_files = discover_java_files(source_dirs)

    # 3. Spawn jdtls server
    jdtls_process = spawn_jdtls_server(project_root, debug)

    # 4. Initialize LSP session
    request_id = 1
    if debug:
        print("Initializing LSP session...", file=sys.stderr)
    init_response = initialize_lsp_session(jdtls_process, project_root, request_id, debug)
    request_id += 1

    # Validate initialization
    if "error" in init_response:
        raise RuntimeError(f"LSP initialization failed: {init_response['error']}")

    # 5. Wait for workspace readiness (REPLACES time.sleep(5))
    request_id = wait_for_workspace_ready(jdtls_process, request_id, timeout=120, debug=debug)

    # 6. Validate LSP communication with test file
    request_id = validate_lsp_communication(jdtls_process, project_root, request_id, debug)

    # 7. For each Java file, discover loggers
    loggers = []
    log_calls = []

    logger_pattern = re.compile(r'(LOGGER|logger|LOG|log|.*_LOGGER|.*_LOG|.*Logger|.*Log)$')

    if debug:
        print(f"Discovering loggers in {len(java_files)} files...", file=sys.stderr)
    else:
        print("Discovering loggers...", file=sys.stderr)

    for i, java_file in enumerate(java_files):
        if (i + 1) % 100 == 0:
            print(f"Processed {i+1}/{len(java_files)} files: {len(loggers)} loggers, {len(log_calls)} calls", file=sys.stderr)

        file_uri = f"file://{java_file.absolute()}"

        # Query all symbols (pass debug=False to avoid spamming logs)
        symbols = query_document_symbol(jdtls_process, file_uri, request_id, debug=False)
        request_id += 1

        # Filter to Field/Constant symbols with logger-like names
        for symbol in symbols:
            symbol_kind = symbol.get('kind')
            symbol_name = symbol.get('name', '')

            # SymbolKind: Field=8, Constant=14 (but use names for compatibility)
            kind_name = symbol.get('kind') if isinstance(symbol.get('kind'), str) else get_symbol_kind_name(symbol.get('kind'))

            if kind_name in ['Field', 'Constant', '8', '14']:
                if logger_pattern.match(symbol_name):
                    # Get position
                    location = symbol.get('location', {}).get('range', {}).get('start', {})
                    line = location.get('line', 0)
                    character = location.get('character', 0)

                    # Get type info (pass debug=False to avoid spamming)
                    hover_text = query_hover(jdtls_process, file_uri, line, character, request_id, debug=False)
                    request_id += 1

                    # Check if it's a Logger type
                    if 'Logger' in hover_text or 'Log' in hover_text or 'slf4j' in hover_text:
                        # Found a logger!
                        logger_info = {
                            "name": symbol_name,
                            "type": extract_type_from_hover(hover_text),
                            "file": str(java_file.absolute()),
                            "line": line + 1,  # LSP uses 0-based, we use 1-based
                            "module": get_module_name(java_file, project_root)
                        }
                        loggers.append(logger_info)

                        if debug and len(loggers) <= 5:  # Show first few discoveries
                            print(f"  Found logger: {symbol_name} in {java_file.name}", file=sys.stderr)

                        # Find all references (pass debug=False to avoid spamming)
                        references = query_references(jdtls_process, file_uri, line, character, request_id, debug=False)
                        request_id += 1

                        # Add each reference as a log call
                        for ref in references:
                            ref_range = ref.get('range', {}).get('start', {})
                            ref_line = ref_range.get('line', 0) + 1  # Convert to 1-based
                            ref_uri = ref.get('uri', '')
                            ref_file = ref_uri.replace('file://', '')
                            ref_path = Path(ref_file)

                            # Skip the declaration line itself
                            if ref_line != logger_info["line"] or ref_file != logger_info["file"]:
                                log_calls.append({
                                    "logger_name": symbol_name,
                                    "file": ref_file,
                                    "line": ref_line,
                                    "module": get_module_name(ref_path, project_root)
                                })

    print(f"Processed {len(java_files)}/{len(java_files)} files: {len(loggers)} loggers, {len(log_calls)} calls", file=sys.stderr)

    # 6. Shutdown jdtls server
    print("Shutting down LSP session...", file=sys.stderr)
    shutdown_lsp_session(jdtls_process, request_id)

    return {
        "loggers": loggers,
        "log_calls": log_calls
    }


# ============================================================================
# Existing Data Classes and Processing
# ============================================================================

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


def generate_conversion_inventory(lsp_inventory: Dict[str, Any], output_path: Path, project_root: Path):
    """
    Generate conversion-inventory.json from lsp-inventory.json.

    Filters to traditional calls only, sorts bottom-to-top within files,
    partitions by module → package → file hierarchy.

    Args:
        lsp_inventory: The full LSP inventory dict
        output_path: Where to write conversion-inventory.json
        project_root: Project root for path calculations
    """
    # Filter to traditional pattern only
    traditional_calls = [
        call for call in lsp_inventory['log_calls']
        if call.get('pattern') == 'traditional'
    ]

    if not traditional_calls:
        print("✓ No traditional log calls found - all logs already converted!")
        return

    # Group by module → package → file
    hierarchy = {}
    for call in traditional_calls:
        file_path = call['file']

        # Extract module from file path (e.g., "cds-core/src/main/java/..." → "cds-core")
        parts = Path(file_path).parts
        module = parts[0] if len(parts) > 0 else 'unknown'

        # Extract package from file path (e.g., "org/familysearch/cds/core/...")
        # Look for pattern: src/main/java/<package-path>/File.java
        try:
            src_idx = parts.index('java') if 'java' in parts else -1
            if src_idx >= 0 and src_idx < len(parts) - 1:
                package_parts = parts[src_idx + 1:-1]  # Exclude filename
                package = '.'.join(package_parts) if package_parts else 'default'
            else:
                package = 'default'
        except (ValueError, IndexError):
            package = 'default'

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
    def extract_logger_name(call):
        """Extract logger name from call"""
        return call.get('logger_name', 'LOGGER')

    def count_files(h):
        """Count total files in hierarchy"""
        count = 0
        for module in h.values():
            for package in module.values():
                count += len(package)
        return count

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
                file_entry = {
                    "file": str(project_root / file_path),
                    "relativePath": file_path,
                    "callCount": len(calls),
                    "calls": [
                        {
                            "line": call['line'],
                            "column": 0,
                            "method": call.get('level', 'info').lower() if call.get('level') else 'info',
                            "logger": extract_logger_name(call),
                            "snippet": call.get('message_snippet', ''),
                            "context": {
                                "level": call.get('level', 'INFO'),
                                "pattern": call.get('pattern', 'traditional'),
                                "parameter_count": call.get('parameter_count', 0)
                            },
                            "status": "pending",
                            "converted_at": None,
                            "commit": None
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

    print(f"✓ Conversion inventory saved to: {output_path}")
    print(f"  - {output['metadata']['total_unconverted_calls']} unconverted calls")
    print(f"  - {output['metadata']['total_files']} files")
    print(f"  - {len(output['modules'])} modules")


def main():
    """
    Main entry point with enhanced LSP discovery.

    Supports three modes:
    1. --source/--test: Specify source directories for single-module projects
    2. --auto-discover: Auto-detect all modules in multi-module projects
    3. --input-lsp-results: Process pre-generated LSP results (backward compatible)
    """
    import argparse

    parser = argparse.ArgumentParser(description='Generate LSP-based logger inventory')
    parser.add_argument('--project-root', type=Path, default=Path.cwd(),
                        help='Project root directory')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output JSON file path')

    # NEW: Source-based discovery
    parser.add_argument('--source', type=Path, action='append',
                        help='Source directory to scan (e.g., src/main/java)')
    parser.add_argument('--test', type=Path, action='append',
                        help='Test directory to scan (e.g., src/test/java)')
    parser.add_argument('--auto-discover', action='store_true',
                        help='Auto-discover all modules in multi-module project')

    # Debug mode
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging (shows LSP communication)')

    # EXISTING: Pre-generated results
    parser.add_argument('--input-lsp-results', type=Path,
                        help='JSON file with LSP query results')

    args = parser.parse_args()
    generator = LSPInventoryGenerator(args.project_root)

    # NEW CODE PATH: Generate LSP results internally
    if args.source or args.auto_discover:
        source_dirs = []

        if args.auto_discover:
            if not args.debug:
                print(f"Auto-discovering modules in: {args.project_root}")
            lsp_results = discover_loggers_via_lsp([], args.project_root, auto_discover=True, debug=args.debug)
        else:
            # Collect source directories
            if args.source:
                source_dirs.extend([args.project_root / s for s in args.source])
            if args.test:
                source_dirs.extend([args.project_root / t for t in args.test])

            if not args.debug:
                print(f"Discovering loggers via LSP in: {[str(d) for d in source_dirs]}")
            lsp_results = discover_loggers_via_lsp(source_dirs, args.project_root, auto_discover=False, debug=args.debug)

        # Process results (existing code)
        for logger_data in lsp_results.get('loggers', []):
            generator.add_logger_from_lsp(
                name=logger_data['name'],
                type_info=logger_data['type'],
                file_path=logger_data['file'],
                line=logger_data['line']
            )

        for call_data in lsp_results.get('log_calls', []):
            generator.add_log_call_from_lsp(
                logger_name=call_data['logger_name'],
                file_path=call_data['file'],
                line=call_data['line']
            )

        # Enhance with code context (existing)
        print("Enhancing with code context...", file=sys.stderr)
        for log_call in generator.log_calls:
            context = generator.enhance_with_code_context(log_call.file, log_call.line)
            log_call.level = context.get('level')
            log_call.pattern = context.get('pattern')
            log_call.message_snippet = context.get('message_snippet')
            log_call.parameter_count = context.get('parameter_count', 0)

    # EXISTING CODE PATH: Use pre-generated results
    elif args.input_lsp_results and args.input_lsp_results.exists():
        with open(args.input_lsp_results, 'r') as f:
            lsp_results = json.load(f)

        for logger_data in lsp_results.get('loggers', []):
            generator.add_logger_from_lsp(
                name=logger_data['name'],
                type_info=logger_data['type'],
                file_path=logger_data['file'],
                line=logger_data['line']
            )

        for call_data in lsp_results.get('log_calls', []):
            generator.add_log_call_from_lsp(
                logger_name=call_data['logger_name'],
                file_path=call_data['file'],
                line=call_data['line']
            )

        for log_call in generator.log_calls:
            context = generator.enhance_with_code_context(log_call.file, log_call.line)
            log_call.level = context.get('level')
            log_call.pattern = context.get('pattern')
            log_call.message_snippet = context.get('message_snippet')
            log_call.parameter_count = context.get('parameter_count', 0)

    # FAIL if neither mode provided
    else:
        print("Error: Must provide --source, --auto-discover, or --input-lsp-results", file=sys.stderr)
        print("", file=sys.stderr)
        print("For single-module project:", file=sys.stderr)
        print("  python3 lsp_inventory.py --source src/main/java --output inventory.json", file=sys.stderr)
        print("", file=sys.stderr)
        print("For multi-module project (auto-detect):", file=sys.stderr)
        print("  python3 lsp_inventory.py --auto-discover --output inventory.json", file=sys.stderr)
        print("", file=sys.stderr)
        print("For processing pre-generated LSP results:", file=sys.stderr)
        print("  python3 lsp_inventory.py --input-lsp-results results.json --output inventory.json", file=sys.stderr)
        sys.exit(1)

    # Save outputs (existing code)
    generator.save_inventory(args.output)

    conversion_output = args.output.parent / 'conversion-inventory.json'
    lsp_inventory = generator.generate_inventory()
    generate_conversion_inventory(lsp_inventory, conversion_output, generator.project_root)


if __name__ == '__main__':
    main()
