#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDS_ROOT="/home/fransonsr/github/cds2-root"
OUTPUT_DIR="/tmp/hybrid-cds-$(date +%s)"

echo "=== E2E Test: Large Project (cds2-root) ==="
echo "Project: $CDS_ROOT"
echo "Output directory: $OUTPUT_DIR"
echo

# Validate cds2-root exists
if [ ! -d "$CDS_ROOT" ]; then
    echo "✗ FAILED: cds2-root not found at $CDS_ROOT"
    echo "Expected: /home/fransonsr/github/cds2-root"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Time the execution
START=$(date +%s)

echo "[1/3] Running hybrid_inventory.py..."
python3 "$SCRIPT_DIR/hybrid_inventory.py" \
  --project-root "$CDS_ROOT" \
  --auto-discover \
  --output "$OUTPUT_DIR/lsp-inventory.json"

END=$(date +%s)
DURATION=$((END - START))

echo
echo "[2/3] Validating outputs..."

# Validate outputs
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

# Extract statistics
LOGGERS=$(jq '.loggers | length' "$OUTPUT_DIR/lsp-inventory.json")
CALLS=$(jq '.log_calls | length' "$OUTPUT_DIR/lsp-inventory.json")
TRADITIONAL=$(jq '.log_calls | map(select(.pattern == "traditional")) | length' "$OUTPUT_DIR/lsp-inventory.json")

echo
echo "[3/3] Validating results..."

# Performance check
if [ "$DURATION" -gt 90 ]; then
    echo "⚠ WARNING: Execution took ${DURATION}s (target: <90s)"
    # Don't fail - just warn
else
    echo "✓ Performance: ${DURATION}s (target: <90s)"
fi

# Sanity checks (based on Session 1 results: 179 loggers, 2,837 candidates → 1,180 actual log calls after filtering)
if [ "$LOGGERS" -lt 100 ]; then
    echo "✗ FAILED: Too few loggers ($LOGGERS < 100)"
    exit 1
fi
echo "✓ Loggers: $LOGGERS (>100)"

if [ "$CALLS" -lt 1000 ]; then
    echo "✗ FAILED: Too few calls ($CALLS < 1000)"
    exit 1
fi
echo "✓ Log calls: $CALLS (>1000)"

echo
echo "=== Results ==="
echo "Duration: ${DURATION}s"
echo "Loggers: $LOGGERS"
echo "Log calls: $CALLS"
echo "Traditional: $TRADITIONAL"
echo
echo "✓ ALL TESTS PASSED"
echo
echo "Output files:"
echo "  - $OUTPUT_DIR/lsp-inventory.json"
echo "  - $OUTPUT_DIR/conversion-inventory.json"
