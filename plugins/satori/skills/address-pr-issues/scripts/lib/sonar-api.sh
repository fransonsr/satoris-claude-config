#!/usr/bin/env bash
# SonarQube API helper functions for PR workflow

set -euo pipefail

# Get SonarQube configuration from sonar-project.properties
get_sonar_config() {
  if [[ ! -f "sonar-project.properties" ]]; then
    echo "ERROR: sonar-project.properties not found" >&2
    return 1
  fi

  SONAR_PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)
  SONAR_HOST=$(grep "^sonar.host.url=" sonar-project.properties | cut -d= -f2)

  if [[ -z "$SONAR_PROJECT_KEY" || -z "$SONAR_HOST" ]]; then
    echo "ERROR: Could not parse sonar.projectKey or sonar.host.url" >&2
    return 1
  fi

  # This environment's SonarQube credential is provisioned under SONARQUBE_CLI_TOKEN (and the
  # matching server as SONARQUBE_CLI_SERVER), not SONAR_TOKEN/SONAR_HOST — fall back to it
  # rather than requiring every session to re-export under this script's name.
  if [[ -z "${SONAR_TOKEN:-}" && -n "${SONARQUBE_CLI_TOKEN:-}" ]]; then
    SONAR_TOKEN="$SONARQUBE_CLI_TOKEN"
  fi

  if [[ -z "${SONAR_TOKEN:-}" ]]; then
    echo "ERROR: SONAR_TOKEN environment variable not set (also checked SONARQUBE_CLI_TOKEN)" >&2
    return 1
  fi
}

# Get quality gate status for a PR
# Usage: get_quality_gate_status <pr_number>
# Returns: JSON with status and conditions
get_quality_gate_status() {
  local pr_number="$1"

  get_sonar_config || return 1

  curl -s -u "$SONAR_TOKEN:" \
    "$SONAR_HOST/api/qualitygates/project_status?projectKey=$SONAR_PROJECT_KEY&pullRequest=$pr_number" \
    2>/dev/null || echo '{"projectStatus": {"status": "ERROR", "error": "API call failed"}}'
}

# Get SonarQube issues for a PR
# Usage: get_pr_issues <pr_number> <severity>
# Severity: BLOCKER, CRITICAL, MAJOR, MINOR, INFO, or impactSeverities: LOW, MEDIUM, HIGH
get_pr_issues() {
  local pr_number="$1"
  local severity="${2:-}"

  get_sonar_config || return 1

  local severity_param=""
  if [[ -n "$severity" ]]; then
    # Check if it's impact severity (new SonarQube API)
    if [[ "$severity" =~ ^(LOW|MEDIUM|HIGH)$ ]]; then
      severity_param="&impactSeverities=$severity"
    else
      severity_param="&severities=$severity"
    fi
  fi

  curl -s -u "$SONAR_TOKEN:" \
    "$SONAR_HOST/api/issues/search?componentKeys=$SONAR_PROJECT_KEY&pullRequest=$pr_number&resolved=false${severity_param}" \
    2>/dev/null
}

# Format quality gate status for display
# Usage: format_quality_gate_status <json_file>
format_quality_gate_status() {
  local json_file="$1"

  local status
  status=$(jq -r '.projectStatus.status' "$json_file" 2>/dev/null || echo "UNKNOWN")

  if [[ "$status" == "OK" ]]; then
    echo "✅ Quality Gate: PASSED"
    return 0
  elif [[ "$status" == "ERROR" ]]; then
    echo "❌ Quality Gate: FAILED"
    echo ""
    echo "Failed Conditions:"
    jq -r '.projectStatus.conditions[] | select(.status == "ERROR") |
      "  - [\(.metricKey)] \(.comparator) \(.errorThreshold) (actual: \(.actualValue))"' \
      "$json_file" 2>/dev/null
    return 1
  else
    echo "⚠️  Quality Gate: $status"
    return 2
  fi
}

# Format issues for display
# Usage: format_issues <json_file>
format_issues() {
  local json_file="$1"

  local count
  count=$(jq '.issues | length' "$json_file" 2>/dev/null || echo "0")

  if [[ "$count" -eq 0 ]]; then
    echo "No issues found"
    return 0
  fi

  echo "Found $count issue(s):"
  echo ""

  jq -r '.issues[] | {
    key,
    message,
    line,
    component: .component | split(":") | last,
    rule,
    severity: (.impacts[0].severity // .severity)
  } | "[\(.severity)] \(.component):\(.line) - \(.message)\n  Rule: \(.rule)\n  Key: \(.key)"' \
    "$json_file" 2>/dev/null
}

# Wait for SonarQube analysis to complete
# Usage: wait_for_analysis <task_id> [max_attempts]
wait_for_analysis() {
  local task_id="$1"
  local max_attempts="${2:-12}"  # Default 60 seconds (12 * 5s)

  get_sonar_config || return 1

  echo "⏳ Waiting for SonarQube server processing..."

  for i in $(seq 1 "$max_attempts"); do
    local status
    status=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
      "$SONAR_HOST/api/ce/task?id=$task_id" 2>/dev/null \
      | jq -r '.task.status' 2>/dev/null || echo "UNKNOWN")

    if [[ "$status" == "SUCCESS" ]]; then
      echo "✅ Analysis complete"
      return 0
    elif [[ "$status" == "FAILED" ]]; then
      echo "❌ Analysis failed - check dashboard"
      return 1
    fi

    echo "   Processing... ($i/$max_attempts)"
    sleep 5
  done

  echo "⚠️  Timeout waiting for analysis (check dashboard manually)"
  return 2
}
