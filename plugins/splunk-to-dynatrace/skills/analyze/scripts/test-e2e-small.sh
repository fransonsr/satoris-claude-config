#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PROJECT="$SCRIPT_DIR/spoon-scanner"  # Use spoon-scanner project as test
OUTPUT_DIR="/tmp/hybrid-test-$(date +%s)"

echo "=== E2E Test: Small Project ==="
echo "Test project: $TEST_PROJECT"
echo "Output directory: $OUTPUT_DIR"
echo

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Run hybrid scanner
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

# Validate JSON structure (required fields)
REQUIRED_FIELDS="metadata loggers log_calls"
for field in $REQUIRED_FIELDS; do
    if ! jq -e ".$field" "$OUTPUT_DIR/lsp-inventory.json" >/dev/null 2>&1; then
        echo "✗ FAILED: Missing required field: $field"
        exit 1
    fi
done
echo "✓ All required fields present (metadata, loggers, log_calls)"

echo
echo "[4/4] Validating enrichment fields..."

# Validate log_calls have enrichment fields (check if we have any calls)
CALLS=$(jq '.log_calls | length' "$OUTPUT_DIR/lsp-inventory.json")

if [ "$CALLS" -gt 0 ]; then
    ENRICHMENT_FIELDS="level pattern message_snippet parameter_count"
    for field in $ENRICHMENT_FIELDS; do
        if ! jq -e ".log_calls[0] | has(\"$field\")" "$OUTPUT_DIR/lsp-inventory.json" | grep -q true; then
            echo "✗ FAILED: Missing enrichment field: $field"
            exit 1
        fi
    done
    echo "✓ Enrichment fields present (level, pattern, message_snippet, parameter_count)"
else
    echo "⚠ WARNING: No log calls found (empty project)"
fi

# Show results
LOGGERS=$(jq '.loggers | length' "$OUTPUT_DIR/lsp-inventory.json")
TRADITIONAL=$(jq '.log_calls | map(select(.pattern == "traditional")) | length' "$OUTPUT_DIR/lsp-inventory.json")

echo
echo "=== Results ==="
echo "Loggers: $LOGGERS"
echo "Log calls: $CALLS"
echo "Traditional pattern: $TRADITIONAL"
echo
echo "✓ ALL TESTS PASSED"
echo
echo "Output files:"
echo "  - $OUTPUT_DIR/lsp-inventory.json"
echo "  - $OUTPUT_DIR/conversion-inventory.json"
