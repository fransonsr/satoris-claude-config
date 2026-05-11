#!/bin/bash
# Test script for transform_jpype.py
#
# Prerequisites:
#   sudo apt-get install python3-jpype
# OR
#   python3 -m venv venv && source venv/bin/activate && pip install jpype1

set -e

cd "$(dirname "$0")"

echo "Testing JPype transformer..."
echo ""

# Check jpype installation
if python3 -c "import jpype" 2>/dev/null; then
    echo "✓ jpype is installed"
    python3 -c "import jpype; print(f'  Version: {jpype.__version__}')"
else
    echo "✗ jpype not installed"
    echo ""
    echo "Install with:"
    echo "  sudo apt-get install python3-jpype"
    echo "OR"
    echo "  python3 -m venv venv && source venv/bin/activate && pip install jpype1"
    exit 1
fi

echo ""
echo "Running transformer on test fixtures..."
echo ""

# Run transformer
python3 transform_jpype.py \
    --batch test-fixtures/test-inventory.json \
    --specs test-fixtures/test-specs.json \
    --workers 1 \
    --output test-results.json

echo ""
echo "✓ Transformation complete!"
echo ""

# Show results
if [ -f test-results.json ]; then
    echo "Results:"
    jq '.[] | {file: .file, status: .status, successCount: .successCount, failureCount: .failureCount}' test-results.json
fi

echo ""
echo "Transformed file:"
cat test-fixtures/TestService.java

echo ""
echo "Test complete!"
