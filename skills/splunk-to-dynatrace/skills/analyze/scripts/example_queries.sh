#!/bin/bash
#
# Example jq queries for exploring LSP inventory.json
#
# Usage:
#   ./example_queries.sh /path/to/inventory.json
#   or from .claude/analyze-reports/:
#   ../../../skills/splunk-to-dynatrace/analyze/scripts/example_queries.sh lsp-inventory.json
#
# Requirements: jq (https://jqlang.github.io/jq/)
#

INVENTORY_FILE="${1:-.claude/analyze-reports/lsp-inventory.json}"

if [ ! -f "$INVENTORY_FILE" ]; then
    echo "Error: Inventory file not found: $INVENTORY_FILE"
    echo "Usage: $0 [path/to/inventory.json]"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed"
    echo "Install: sudo apt-get install jq  # or brew install jq"
    exit 1
fi

echo "=== LSP Inventory Query Examples ==="
echo "Inventory file: $INVENTORY_FILE"
echo

# Query 1: Summary statistics
echo "1. Summary Statistics"
echo "   Command: jq '.metadata' $INVENTORY_FILE"
jq '.metadata' "$INVENTORY_FILE"
echo

# Query 2: All logger types
echo "2. Logger Types Distribution"
echo "   Command: jq -r '.loggers | group_by(.type) | map({type: .[0].type, count: length}) | .[]' $INVENTORY_FILE"
jq -r '.loggers | group_by(.type) | map({type: .[0].type, count: length}) | .[]' "$INVENTORY_FILE"
echo

# Query 3: Log levels distribution
echo "3. Log Levels Distribution"
echo "   Command: jq -r '.log_calls | group_by(.level) | map({level: .[0].level, count: length}) | .[]' $INVENTORY_FILE"
jq -r '.log_calls | group_by(.level) | map({level: .[0].level, count: length}) | .[]' "$INVENTORY_FILE"
echo

# Query 4: Files with most log statements
echo "4. Top 5 Files by Log Statement Count"
echo "   Command: jq -r '.log_calls | group_by(.file) | map({file: .[0].file | split(\"/\")[-1], count: length}) | sort_by(-.count) | .[0:5] | .[]' $INVENTORY_FILE"
jq -r '.log_calls | group_by(.file) | map({file: .[0].file | split("/")[-1], count: length}) | sort_by(-.count) | .[0:5] | .[]' "$INVENTORY_FILE"
echo

# Query 5: Traditional vs Fluent API usage
echo "5. Logging Pattern Distribution"
echo "   Command: jq -r '.log_calls | group_by(.pattern) | map({pattern: .[0].pattern, count: length}) | .[]' $INVENTORY_FILE"
jq -r '.log_calls | group_by(.pattern) | map({pattern: .[0].pattern, count: length}) | .[]' "$INVENTORY_FILE"
echo

# Query 6: Find all ERROR level logs
echo "6. All ERROR Level Log Locations"
echo "   Command: jq -r '.log_calls | map(select(.level == \"ERROR\")) | .[] | \"\\(.file):\\(.line)\"' $INVENTORY_FILE"
jq -r '.log_calls | map(select(.level == "ERROR")) | .[] | "\(.file):\(.line)"' "$INVENTORY_FILE"
echo

# Query 7: Loggers with no calls (unused)
echo "7. Unused Loggers (declared but never called)"
echo "   Command: jq -r '.loggers | map(select(.call_count == 0)) | .[] | \"\\(.file):\\(.line) - \\(.name)\"' $INVENTORY_FILE"
jq -r '.loggers | map(select(.call_count == 0)) | .[] | "\(.file):\(.line) - \(.name)"' "$INVENTORY_FILE" || echo "   (None found - all loggers are used)"
echo

# Query 8: Log calls by specific logger
echo "8. All Log Calls for RETRY_LOGGER (example)"
echo "   Command: jq -r '.log_calls | map(select(.logger_name == \"RETRY_LOGGER\")) | .[] | \"\\(.file):\\(.line) [\\(.level)]\"' $INVENTORY_FILE"
jq -r '.log_calls | map(select(.logger_name == "RETRY_LOGGER")) | .[] | "\(.file):\(.line) [\(.level)]"' "$INVENTORY_FILE" || echo "   (RETRY_LOGGER not found in this codebase)"
echo

echo "=== Custom Query Template ==="
echo "jq -r '.log_calls | map(select(YOUR_FILTER)) | .[]' $INVENTORY_FILE"
echo
echo "Examples:"
echo "  - Find INFO logs: select(.level == \"INFO\")"
echo "  - Find logs in specific file: select(.file | contains(\"FileName\"))"
echo "  - Find logs with params: select(.parameter_count > 0)"
echo "  - Find traditional pattern: select(.pattern == \"traditional\")"
echo
