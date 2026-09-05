#!/usr/bin/env python3
"""Query a SCIP index by exact symbol identity instead of text pattern matching.

Usage:
  scip_query.py at <file>:<line>:<col> --index path/to/index.scip
  scip_query.py symbol <substring> --index path/to/index.scip

Line/col are 1-based, matching how editors and Claude Code report positions.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFINITION = 0x1


def load_index(index_path: Path) -> dict:
    """Return the parsed SCIP index as JSON, regenerating the JSON cache if stale."""
    if index_path.suffix == ".json":
        with open(index_path) as f:
            return json.load(f)

    json_path = index_path.with_suffix(".json")
    if not json_path.exists() or json_path.stat().st_mtime < index_path.stat().st_mtime:
        result = subprocess.run(
            ["scip", "print", "--json", str(index_path)],
            capture_output=True, text=True, check=True,
        )
        json_path.write_text(result.stdout)
    with open(json_path) as f:
        return json.load(f)


def normalize_range(occ: dict):
    """Return (start_line, start_char, end_line, end_char), all 0-based.

    `scip print --json` does NOT follow standard protobuf JSON naming: most fields are
    snake_case, matching the .proto schema's raw field names, but the `oneof` range
    wrapper is emitted with Go-struct-style PascalCase wrapper keys (TypedRange /
    SingleLineRange / MultiLineRange), each containing snake_case sub-fields. This was
    found empirically by inspecting real `scip print --json` output, not documented
    anywhere — don't trust the .proto schema's implied JSON shape without re-checking
    real CLI output if the `scip` version changes.

    Every sub-field is read with a 0 default because protobuf JSON omits zero-valued
    scalars entirely: a symbol starting at column 0 has no `start_character` key, and one
    on the file's first line has no `line`/`start_line` key. Indexing these directly
    raises KeyError on ordinary input — observed on a real records-platform-mcp index,
    where 86 of 22647 occurrences omit `start_character`.
    """
    typed = occ.get("TypedRange", {})
    if "SingleLineRange" in typed:
        r = typed["SingleLineRange"]
        line = r.get("line", 0)
        return line, r.get("start_character", 0), line, r.get("end_character", 0)
    if "MultiLineRange" in typed:
        r = typed["MultiLineRange"]
        return (r.get("start_line", 0), r.get("start_character", 0),
                r.get("end_line", 0), r.get("end_character", 0))
    r = occ.get("range", [])
    if len(r) == 3:
        return r[0], r[1], r[0], r[2]
    if len(r) == 4:
        return r[0], r[1], r[2], r[3]
    raise ValueError(f"occurrence has no usable range: {occ}")


def contains(start_line, start_char, end_line, end_char, line, col) -> bool:
    if start_line == end_line:
        return line == start_line and start_char <= col < end_char
    if line == start_line:
        return col >= start_char
    if line == end_line:
        return col < end_char
    return start_line < line < end_line


def role_label(symbol_roles: int) -> str:
    return "definition" if symbol_roles & DEFINITION else "reference"


def iter_occurrences(index: dict):
    for doc in index.get("documents", []):
        path = doc["relative_path"]
        for occ in doc.get("occurrences", []):
            if "symbol" in occ:
                yield path, occ


def print_hits(hits):
    for path, line0, col0, role, symbol in sorted(hits):
        print(f"{path}:{line0 + 1}:{col0 + 1}\t{role}\t{symbol}")


def cmd_at(index: dict, file_arg: str, line_arg: int, col_arg: int):
    line0, col0 = line_arg - 1, col_arg - 1
    target_symbol = None
    for path, occ in iter_occurrences(index):
        if not path.endswith(file_arg):
            continue
        start_line, start_char, end_line, end_char = normalize_range(occ)
        if contains(start_line, start_char, end_line, end_char, line0, col0):
            target_symbol = occ["symbol"]
            break

    if target_symbol is None:
        print(f"No symbol found at {file_arg}:{line_arg}:{col_arg}", file=sys.stderr)
        sys.exit(1)

    print(f"# symbol: {target_symbol}", file=sys.stderr)
    hits = [
        (path, *normalize_range(occ)[:2], role_label(occ.get("symbol_roles", 0)), occ["symbol"])
        for path, occ in iter_occurrences(index)
        if occ["symbol"] == target_symbol
    ]
    print_hits(hits)


def cmd_symbol(index: dict, substring: str):
    hits = [
        (path, *normalize_range(occ)[:2], role_label(occ.get("symbol_roles", 0)), occ["symbol"])
        for path, occ in iter_occurrences(index)
        if substring in occ["symbol"]
    ]
    if not hits:
        print(f"No occurrences matching symbol substring: {substring!r}", file=sys.stderr)
        sys.exit(1)
    print_hits(hits)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", required=True, type=Path, help="path to .scip or cached .json index")
    sub = parser.add_subparsers(dest="command", required=True)

    at_parser = sub.add_parser("at", help="find all references to the symbol at file:line:col")
    at_parser.add_argument("location", help="file:line:col (1-based)")

    symbol_parser = sub.add_parser("symbol", help="find all occurrences whose symbol contains a substring")
    symbol_parser.add_argument("substring")

    args = parser.parse_args()
    index = load_index(args.index)

    if args.command == "at":
        file_arg, line_arg, col_arg = args.location.rsplit(":", 2)
        cmd_at(index, file_arg, int(line_arg), int(col_arg))
    elif args.command == "symbol":
        cmd_symbol(index, args.substring)


if __name__ == "__main__":
    main()
