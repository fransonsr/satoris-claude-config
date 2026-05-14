#!/bin/bash
# Test script for transform_spoon.py (v3.0.0 - Spoon-based transformer)
#
# Prerequisites:
#   - Java 17+
#   - Maven 3.6+ (for building transformer)
#   - python3-jpype OR: python3 -m venv venv && source venv/bin/activate && pip install jpype1

set -e

cd "$(dirname "$0")"

echo "Testing Spoon transformer (v3.0.0)..."
echo ""

# Check Java
if ! command -v java &> /dev/null; then
    echo "✗ Java not found. Please install Java 17+."
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d'.' -f1)
if [ "$JAVA_VERSION" -lt 17 ]; then
    echo "✗ Java 17+ required. Found Java $JAVA_VERSION."
    exit 1
fi

echo "✓ Java $JAVA_VERSION"

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

# Check transformer JAR
if [ ! -f spoon-transformer.jar ]; then
    echo ""
    echo "✗ spoon-transformer.jar not found"
    echo "Building transformer..."
    ./build-spoon-transformer.sh
fi

echo "✓ spoon-transformer.jar"

echo ""
echo "Running transformer on test fixtures..."
echo ""

# Run transformer
python3 transform_spoon.py \
    --inventory test-fixtures/test-inventory.json \
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
