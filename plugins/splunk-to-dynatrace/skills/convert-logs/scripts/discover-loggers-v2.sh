#!/bin/bash
#
# discover-loggers-v2.sh
# Simplified version that writes JSON directly without jq dependency
#
# ⚠️ DEPRECATED in v2.0.0
#
# This script is SUPERSEDED by the analyze skill's conversion-inventory.json output.
#
# For new workflows:
#   1. Run: /splunk-to-dynatrace:analyze
#   2. Use: .claude/analyze-reports/conversion-inventory.json
#
# This script is kept ONLY for recovery/verification purposes.
# It uses grep/pattern matching which misses 40-60% of logger calls.
# The analyze skill uses LSP for 100% accuracy.
#
# Usage: ./discover-loggers-v2.sh <directory> <output-file>

set -euo pipefail

SEARCH_DIR="${1:-src/main/java}"
OUTPUT_FILE="${2:-logger-inventory.json}"

echo "Logger Discovery Tool"
echo "Searching: $SEARCH_DIR"
echo "Output: $OUTPUT_FILE"
echo ""

# Find all Java files
JAVA_FILES=$(find "$SEARCH_DIR" -name "*.java" -type f 2>/dev/null | sort)
TOTAL_FILES=$(echo "$JAVA_FILES" | wc -l)

echo "Found $TOTAL_FILES Java files"
echo ""

FILES_PROCESSED=0
FILES_WITH_LOGGERS=0
TOTAL_LOGGERS=0
TOTAL_REFERENCES=0

# Start JSON output
cat > "$OUTPUT_FILE" <<EOF
{
  "generated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "searchDirectory": "$SEARCH_DIR",
  "totalFiles": $TOTAL_FILES,
  "files": [
EOF

FIRST_FILE=true

# Process each Java file
for FILE in $JAVA_FILES; do
  FILES_PROCESSED=$((FILES_PROCESSED + 1))

  # Show progress
  if [ $((FILES_PROCESSED % 50)) -eq 0 ]; then
    echo -ne "\rProcessing: ${FILES_PROCESSED}/${TOTAL_FILES} files..."
  fi

  # Skip if doesn't contain Logger
  if ! grep -q "org.slf4j.Logger" "$FILE" 2>/dev/null; then
    continue
  fi

  # Find Logger field declarations
  LOGGER_FIELDS=$(grep -n "Logger.*=" "$FILE" | grep -E "(private|protected|public|static|final)" || true)

  if [ -z "$LOGGER_FIELDS" ]; then
    continue
  fi

  FILES_WITH_LOGGERS=$((FILES_WITH_LOGGERS + 1))

  # Add comma separator
  if [ "$FIRST_FILE" = true ]; then
    FIRST_FILE=false
  else
    echo "," >> "$OUTPUT_FILE"
  fi

  # Get absolute path
  ABS_FILE=$(realpath "$FILE" 2>/dev/null || echo "$FILE")

  # Start file entry
  cat >> "$OUTPUT_FILE" <<EOF
    {
      "file": "$ABS_FILE",
      "relativePath": "$FILE",
      "loggers": [
EOF

  FIRST_LOGGER=true

  # Process each logger field
  while IFS= read -r LOGGER_LINE; do
    LINE_NUM=$(echo "$LOGGER_LINE" | cut -d: -f1)
    LOGGER_NAME=$(echo "$LOGGER_LINE" | sed -n 's/.*Logger[[:space:]]\+\([A-Za-z_][A-Za-z0-9_]*\).*/\1/p')

    if [ -z "$LOGGER_NAME" ]; then
      continue
    fi

    # Find references (exclude declaration line)
    REF_LINES=$(grep -n "${LOGGER_NAME}\." "$FILE" 2>/dev/null | grep -v "^${LINE_NUM}:" | cut -d: -f1 || true)

    if [ -z "$REF_LINES" ]; then
      continue
    fi

    # Convert newlines to comma-separated
    REFERENCES=$(echo "$REF_LINES" | tr '\n' ',' | sed 's/,$//')
    REF_COUNT=$(echo "$REF_LINES" | wc -l)

    TOTAL_LOGGERS=$((TOTAL_LOGGERS + 1))
    TOTAL_REFERENCES=$((TOTAL_REFERENCES + REF_COUNT))

    # Add comma separator
    if [ "$FIRST_LOGGER" = true ]; then
      FIRST_LOGGER=false
    else
      echo "," >> "$OUTPUT_FILE"
    fi

    # Add logger entry
    cat >> "$OUTPUT_FILE" <<EOF
        {
          "name": "$LOGGER_NAME",
          "type": "org.slf4j.Logger",
          "declarationLine": $LINE_NUM,
          "references": [$REFERENCES],
          "referenceCount": $REF_COUNT
        }
EOF
  done <<< "$LOGGER_FIELDS"

  # Close loggers array and file entry
  cat >> "$OUTPUT_FILE" <<EOF
      ]
    }
EOF

done

# Update metadata and close JSON
cat >> "$OUTPUT_FILE" <<EOF
  ],
  "filesWithLoggers": $FILES_WITH_LOGGERS,
  "totalLoggers": $TOTAL_LOGGERS,
  "totalReferences": $TOTAL_REFERENCES
}
EOF

echo -e "\r✓ Processing complete: ${FILES_PROCESSED}/${TOTAL_FILES} files"
echo ""
echo "Summary:"
echo "  Files with loggers: $FILES_WITH_LOGGERS"
echo "  Total loggers: $TOTAL_LOGGERS"
echo "  Total references: $TOTAL_REFERENCES"
echo ""
echo "Output written to: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "  1. Review inventory: jq '.files[] | select(.loggers | length > 0)' $OUTPUT_FILE | less"
echo "  2. Find high-usage loggers: jq '.files[].loggers[] | select(.referenceCount > 10)' $OUTPUT_FILE"
echo "  3. Export to CSV: jq -r '.files[] | .relativePath as \$f | .loggers[] | \"\$f,\(.name),\(.referenceCount)\"' $OUTPUT_FILE"
