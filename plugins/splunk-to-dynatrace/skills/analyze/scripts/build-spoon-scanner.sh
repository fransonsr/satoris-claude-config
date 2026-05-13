#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/spoon-scanner"
OUTPUT_JAR="$SCRIPT_DIR/spoon-scanner.jar"

echo "=== Building Spoon Logger Scanner ==="

# Check Maven
if ! command -v mvn &> /dev/null; then
    echo "Error: Maven not found. Please install Maven 3.6+."
    exit 1
fi

# Check Java
if ! command -v java &> /dev/null; then
    echo "Error: Java not found. Please install Java 17+."
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | cut -d'.' -f1)
if [ "$JAVA_VERSION" -lt 17 ]; then
    echo "Error: Java 17+ required. Found Java $JAVA_VERSION."
    exit 1
fi

# Build
echo "Building Maven project..."
cd "$PROJECT_DIR"
mvn clean package -q

# Copy JAR
echo "Copying JAR to $OUTPUT_JAR..."
cp target/spoon-scanner-1.0.0.jar "$OUTPUT_JAR"

# Test JAR
echo "Testing JAR..."
java -jar "$OUTPUT_JAR" --help 2>&1 | head -n 1 || true

echo "=== Build complete ==="
echo "JAR: $OUTPUT_JAR"
ls -lh "$OUTPUT_JAR"
