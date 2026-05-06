#!/usr/bin/env bash
# Verify splunk-to-dynatrace plugin structure and completeness
# Run before packaging to ensure all required components present

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PLUGIN_DIR}"

echo "=== Plugin Verification ==="
echo "Directory: ${PLUGIN_DIR}"
echo ""

ERRORS=0

# Function to check file exists
check_file() {
  local file=$1
  local description=$2
  if [[ -f "${file}" ]]; then
    echo "✓ ${description}: ${file}"
  else
    echo "✗ MISSING ${description}: ${file}"
    ((ERRORS++))
  fi
}

# Function to check directory exists
check_dir() {
  local dir=$1
  local description=$2
  if [[ -d "${dir}" ]]; then
    echo "✓ ${description}: ${dir}"
  else
    echo "✗ MISSING ${description}: ${dir}"
    ((ERRORS++))
  fi
}

# Check plugin metadata
echo "--- Plugin Metadata ---"
check_file ".claude-plugin/plugin.json" "Plugin manifest"

# Check documentation
echo ""
echo "--- Documentation ---"
check_file "README.md" "Main README"
check_file "LICENSE" "License file"
check_file "CHANGELOG.md" "Changelog"
check_file "CONTRIBUTING.md" "Contributing guide"
check_file "FUTURE_ENHANCEMENTS.md" "Feature roadmap"
check_file ".packageignore" "Package ignore file"

# Check references
echo ""
echo "--- Reference Materials ---"
check_dir "references" "References directory"
check_file "references/familysearch-observability-standards.md" "Observability standards"

# Check skills
echo ""
echo "--- Skills ---"
skills=(
  "analyze"
  "choose-approach"
  "convert-logs"
  "migrate"
  "setup-logback"
  "validate-dashboards"
)

for skill in "${skills[@]}"; do
  check_dir "skills/${skill}" "Skill: ${skill}"
  check_file "skills/${skill}/SKILL.md" "Skill doc: ${skill}"
done

# Check bundled scripts
echo ""
echo "--- Bundled Scripts ---"
check_dir "skills/analyze/scripts" "Analyze scripts directory"
check_file "skills/analyze/scripts/lsp_inventory.py" "LSP inventory script"
check_file "skills/analyze/scripts/anti_patterns.json" "Anti-patterns config"

# Check for workspace artifacts (should be excluded)
echo ""
echo "--- Workspace Check (should be clean) ---"
if find . -name "*workspace*" -o -name "__pycache__" -o -name "*.pyc" | grep -q .; then
  echo "⚠ WARNING: Found workspace artifacts or cache files:"
  find . -name "*workspace*" -o -name "__pycache__" -o -name "*.pyc"
  echo "Run cleanup: rm -rf skills/*/workspace __pycache__ **/*.pyc"
else
  echo "✓ No workspace artifacts found"
fi

# Validate JSON files
echo ""
echo "--- JSON Validation ---"
if command -v python3 &> /dev/null; then
  for json_file in $(find . -name "*.json" -not -path "*/workspace/*" -not -path "*/__pycache__/*"); do
    if python3 -m json.tool "${json_file}" > /dev/null 2>&1; then
      echo "✓ Valid JSON: ${json_file}"
    else
      echo "✗ INVALID JSON: ${json_file}"
      ((ERRORS++))
    fi
  done
else
  echo "⚠ python3 not available, skipping JSON validation"
fi

# Check Python script executability
echo ""
echo "--- Script Executability ---"
for script in $(find skills/*/scripts -name "*.py" 2>/dev/null); do
  if [[ -x "${script}" ]]; then
    echo "✓ Executable: ${script}"
  else
    echo "⚠ Not executable: ${script} (chmod +x recommended)"
  fi
done

# Summary
echo ""
echo "=== Verification Summary ==="
if [[ ${ERRORS} -eq 0 ]]; then
  echo "✓ Plugin structure valid (${ERRORS} errors)"
  echo ""
  echo "Ready to package! Run: ./package.sh"
  exit 0
else
  echo "✗ Plugin has ${ERRORS} error(s)"
  echo "Fix errors before packaging"
  exit 1
fi
