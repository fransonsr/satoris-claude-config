#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PROJECT="${1:-$SCRIPT_DIR/spoon-scanner}"  # Use spoon-scanner project as test
OUTPUT_DIR="/tmp/hybrid-test-$(date +%s)"

echo "=== Testing Hybrid Inventory Generator ==="
echo "Test project: $TEST_PROJECT"
echo "Output directory: $OUTPUT_DIR"
echo

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Run orchestrator
echo "[1/4] Running hybrid_inventory.py..."
python3 "$SCRIPT_DIR/hybrid_inventory.py" \
  --project-root "$TEST_PROJECT" \
  --auto-discover \
  --output "$OUTPUT_DIR/lsp-inventory.json" \
  --debug

echo
echo "[2/4] Validating outputs exist..."

# Validate outputs exist
if [ ! -f "$OUTPUT_DIR/lsp-inventory.json" ]; then
    echo "✗ FAILED: lsp-inventory.json not created"
    exit 1
fi
echo "✓ lsp-inventory.json exists"

if [ ! -f "$OUTPUT_DIR/conversion-inventory.json" ]; then
    echo "✗ FAILED: conversion-inventory.json not created"
    exit 1
fi
echo "✓ conversion-inventory.json exists"

echo
echo "[3/4] Validating JSON structure..."

# Validate JSON structure
if ! jq empty "$OUTPUT_DIR/lsp-inventory.json" 2>/dev/null; then
    echo "✗ FAILED: lsp-inventory.json is not valid JSON"
    exit 1
fi
echo "✓ lsp-inventory.json is valid JSON"

if ! jq empty "$OUTPUT_DIR/conversion-inventory.json" 2>/dev/null; then
    echo "✗ FAILED: conversion-inventory.json is not valid JSON"
    exit 1
fi
echo "✓ conversion-inventory.json is valid JSON"

# Extract statistics
LOGGERS=$(jq '.loggers | length' "$OUTPUT_DIR/lsp-inventory.json")
CALLS=$(jq '.log_calls | length' "$OUTPUT_DIR/lsp-inventory.json")
UNCONVERTED=$(jq '.metadata.total_unconverted_calls' "$OUTPUT_DIR/conversion-inventory.json")

echo
echo "[4/4] Validating enrichment fields..."

# Validate enrichment fields (check first log call if exists)
if [ "$CALLS" -gt 0 ]; then
    HAS_LEVEL=$(jq '.log_calls[0] | has("level")' "$OUTPUT_DIR/lsp-inventory.json")
    HAS_PATTERN=$(jq '.log_calls[0] | has("pattern")' "$OUTPUT_DIR/lsp-inventory.json")
    HAS_MESSAGE=$(jq '.log_calls[0] | has("message_snippet")' "$OUTPUT_DIR/lsp-inventory.json")
    HAS_PARAMS=$(jq '.log_calls[0] | has("parameter_count")' "$OUTPUT_DIR/lsp-inventory.json")

    if [ "$HAS_LEVEL" != "true" ] || [ "$HAS_PATTERN" != "true" ] || \
       [ "$HAS_MESSAGE" != "true" ] || [ "$HAS_PARAMS" != "true" ]; then
        echo "✗ FAILED: Missing enrichment fields in log_calls[0]"
        jq '.log_calls[0] | keys' "$OUTPUT_DIR/lsp-inventory.json"
        exit 1
    fi
    echo "✓ Enrichment fields present (level, pattern, message_snippet, parameter_count)"
fi

# Validate conversion inventory structure
if [ "$UNCONVERTED" != "null" ] && [ "$UNCONVERTED" -gt 0 ]; then
    HAS_MODULES=$(jq '.modules | length > 0' "$OUTPUT_DIR/conversion-inventory.json")
    if [ "$HAS_MODULES" != "true" ]; then
        echo "✗ FAILED: conversion-inventory.json has no modules despite unconverted calls"
        exit 1
    fi
    echo "✓ Conversion inventory has module hierarchy"
fi

echo
echo "=== Test Results ==="
echo "Loggers found: $LOGGERS"
echo "Log calls found: $CALLS"
echo "Unconverted calls: $UNCONVERTED"
echo
echo "✓ ALL TESTS PASSED"
echo
echo "Output files:"
echo "  - $OUTPUT_DIR/lsp-inventory.json"
echo "  - $OUTPUT_DIR/conversion-inventory.json"
