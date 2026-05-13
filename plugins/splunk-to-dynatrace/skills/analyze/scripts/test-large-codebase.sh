#!/bin/bash
set -euo pipefail

# Default to CDS2_ROOT env var if set, otherwise require argument
CDS_ROOT="${CDS2_ROOT:-}"
if [ -z "$CDS_ROOT" ] && [ "$#" -ge 1 ]; then
    CDS_ROOT="$1"
fi

if [ -z "$CDS_ROOT" ]; then
    echo "Usage: $0 <path-to-cds2-root>"
    echo "  or set CDS2_ROOT environment variable"
    echo ""
    echo "This script tests the Spoon scanner on a large codebase (cds2-root with 1,045 Java files)."
    echo "It validates:"
    echo "  - 0 parse failures (vs JavaParser's 8 failures)"
    echo "  - 985+ logger candidates found"
    echo "  - Completes in <60 seconds"
    exit 1
fi

if [ ! -d "$CDS_ROOT" ]; then
    echo "Error: Directory not found: $CDS_ROOT"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAR_FILE="$SCRIPT_DIR/spoon-scanner.jar"
OUTPUT_FILE="/tmp/cds-scan-$(date +%s).json"

if [ ! -f "$JAR_FILE" ]; then
    echo "Error: JAR not found at $JAR_FILE"
    echo "Run ./build-spoon-scanner.sh first"
    exit 1
fi

echo "=== Testing Spoon Scanner on cds2-root ==="
echo "Project: $CDS_ROOT"
echo "JAR: $JAR_FILE"
echo "Output: $OUTPUT_FILE"
echo ""

# Time the scan
echo "Starting scan..."
START=$(date +%s)
java -jar "$JAR_FILE" "$CDS_ROOT" "$OUTPUT_FILE" --auto-discover 2>&1 | tee /tmp/scanner-stderr.log
END=$(date +%s)

DURATION=$((END - START))

# Check for parse errors in stderr
PARSE_ERRORS=$(grep -i "error\|exception\|failed" /tmp/scanner-stderr.log | grep -v "SLF4J" | wc -l || true)

echo ""
echo "=== Validating Results ==="

# Check results with jq
if ! command -v jq &> /dev/null; then
    echo "Warning: jq not installed. Skipping JSON validation."
    echo "Install jq to enable validation: sudo apt-get install jq"
else
    TOTAL=$(jq '.metadata.total_candidates' "$OUTPUT_FILE")
    DECLARATIONS=$(jq '.metadata.declarations' "$OUTPUT_FILE")
    CALLS=$(jq '.metadata.calls' "$OUTPUT_FILE")

    echo "Duration: ${DURATION}s"
    echo "Total candidates: $TOTAL"
    echo "Declarations: $DECLARATIONS"
    echo "Calls: $CALLS"
    echo "Parse errors: $PARSE_ERRORS"
    echo ""

    # Validate metrics
    FAILED=0

    if [ "$DURATION" -gt 60 ]; then
        echo "❌ FAILED: Scan took too long (${DURATION}s > 60s)"
        FAILED=1
    else
        echo "✅ PASSED: Duration within limit (${DURATION}s < 60s)"
    fi

    if [ "$TOTAL" -lt 985 ]; then
        echo "❌ FAILED: Too few candidates ($TOTAL < 985)"
        FAILED=1
    else
        echo "✅ PASSED: Found sufficient candidates ($TOTAL >= 985)"
    fi

    if [ "$PARSE_ERRORS" -gt 0 ]; then
        echo "❌ FAILED: Parse errors detected ($PARSE_ERRORS errors)"
        FAILED=1
    else
        echo "✅ PASSED: No parse errors (0% failure rate)"
    fi

    echo ""
    if [ "$FAILED" -eq 0 ]; then
        echo "=== ALL CHECKS PASSED ==="
        echo "Spoon scanner successfully scanned cds2-root with:"
        echo "  - 0% parse failure rate (vs JavaParser's 0.76%)"
        echo "  - $TOTAL candidates found"
        echo "  - ${DURATION}s scan time"
        exit 0
    else
        echo "=== SOME CHECKS FAILED ==="
        exit 1
    fi
fi
