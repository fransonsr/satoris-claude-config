#!/usr/bin/env bash
# Package splunk-to-dynatrace plugin for distribution
# Excludes workspace artifacts and cache files per .packageignore

set -euo pipefail

PLUGIN_NAME="splunk-to-dynatrace"
VERSION=$(grep '"version"' .claude-plugin/plugin.json | sed 's/.*: "\(.*\)".*/\1/')
PACKAGE_NAME="${PLUGIN_NAME}-${VERSION}"
DIST_DIR="dist"

echo "=== Packaging ${PLUGIN_NAME} v${VERSION} ==="

# Create dist directory
mkdir -p "${DIST_DIR}"

# Clean previous packages
rm -f "${DIST_DIR}/${PACKAGE_NAME}".{tar.gz,zip}

# Create temporary staging directory
STAGE_DIR=$(mktemp -d)
STAGE_PATH="${STAGE_DIR}/${PLUGIN_NAME}"
mkdir -p "${STAGE_PATH}"

echo "Staging files to ${STAGE_PATH}..."

# Copy all files, respecting .packageignore
rsync -av \
  --exclude-from=.packageignore \
  --exclude='dist/' \
  --exclude='package.sh' \
  --exclude='.git/' \
  . "${STAGE_PATH}/"

# Verify required files present
echo "Verifying package contents..."
required_files=(
  ".claude-plugin/plugin.json"
  "README.md"
  "LICENSE"
  "CHANGELOG.md"
  "CONTRIBUTING.md"
  "FUTURE_ENHANCEMENTS.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${STAGE_PATH}/${file}" ]]; then
    echo "ERROR: Required file missing: ${file}"
    exit 1
  fi
done

# Verify skills present
echo "Verifying skills..."
skills=(
  "analyze"
  "choose-approach"
  "convert-logs"
  "migrate"
  "setup-logback"
  "validate-dashboards"
)

for skill in "${skills[@]}"; do
  if [[ ! -f "${STAGE_PATH}/skills/${skill}/SKILL.md" ]]; then
    echo "ERROR: Skill missing: ${skill}"
    exit 1
  fi
done

# Count files
file_count=$(find "${STAGE_PATH}" -type f | wc -l)
echo "Package contains ${file_count} files"

# Create tar.gz archive
echo "Creating ${PACKAGE_NAME}.tar.gz..."
tar -czf "${DIST_DIR}/${PACKAGE_NAME}.tar.gz" -C "${STAGE_DIR}" "${PLUGIN_NAME}"

# Create zip archive
echo "Creating ${PACKAGE_NAME}.zip..."
(cd "${STAGE_DIR}" && zip -r -q "${OLDPWD}/${DIST_DIR}/${PACKAGE_NAME}.zip" "${PLUGIN_NAME}")

# Calculate checksums
echo "Generating checksums..."
(cd "${DIST_DIR}" && sha256sum "${PACKAGE_NAME}".{tar.gz,zip} > "${PACKAGE_NAME}.sha256")

# Cleanup staging
rm -rf "${STAGE_DIR}"

# Display results
echo ""
echo "=== Package Complete ==="
echo "Version: ${VERSION}"
echo "Archives:"
ls -lh "${DIST_DIR}/${PACKAGE_NAME}".{tar.gz,zip}
echo ""
echo "Checksums:"
cat "${DIST_DIR}/${PACKAGE_NAME}.sha256"
echo ""
echo "Distribution artifacts in: ${DIST_DIR}/"
