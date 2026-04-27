#!/usr/bin/env bash
# Wrapper script that delegates to Python implementation for better maintainability
# Usage: ./resolve-threads-bulk.sh <pr_number> [options]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/resolve-threads-bulk.py" "$@"
