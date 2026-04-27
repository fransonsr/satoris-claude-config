# Address PR Issues Skill

Systematically address GitHub Copilot and SonarQube code quality issues on pull requests.

## Overview

This skill automates the workflow of:
1. Reading code quality feedback from GitHub Copilot and SonarQube
2. Prioritizing issues by severity and impact
3. Implementing fixes using TDD methodology
4. Validating changes with local static analysis
5. Resolving conversations to keep PR reviews organized

## Usage

```bash
# Address issues on current branch's PR
/address-pr-issues

# Address issues on specific PR number
/address-pr-issues 42
```

## Key Features

### ✅ Multi-Source Issue Detection
- **GitHub Copilot**: Review comments from GitHub Advanced Security bot
- **SonarQube**: Issues from FamilySearch SonarQube instance
- **Unified View**: Combines and prioritizes issues from both sources

### ✅ Smart Prioritization
- **Automatic categorization**: CRITICAL → HIGH → MEDIUM → LOW
- **User confirmation**: Presents questionable issues for decision
- **Context-aware**: Considers issue location and PR scope

### ✅ Pragmatic Testing Approach
- **Test Coverage Required**: All production code changes must have tests
- **Test-First OR Test-After**: Use judgment based on complexity
  - Test-First: When design needs thinking through
  - Test-After: When fix is obvious (most PR issue fixes)
- **xp-pair Integration**: Uses pairing skill only for complex refactorings (>100 lines, unclear design)

### ✅ Local Validation
- **Pre-commit scanning**: Runs `sonar-scanner` before pushing
- **Iterative fixing**: Catches new issues introduced by fixes
- **Fast feedback**: Avoid CI/CD round-trips

### ✅ Conversation Management
- **Auto-resolve**: Marks fixed issues as resolved
- **Brief explanations**: Adds commit SHA references
- **Won't-fix handling**: Documents decisions with rationale

## Technical Details

### SonarQube Web API Integration

**Note**: Some enterprise SonarQube instances (like churchofjesuschrist.org) use SSO authentication that prevents direct API access via tokens. In these cases, rely on manual dashboard review or wait for GitHub integration comments.

**Wait for analysis completion**:
```bash
# Extract task ID from sonar-scanner output
TASK_URL=$(sonar-scanner 2>&1 | grep "More about the report processing" | sed 's/.*at //')
TASK_ID=$(echo "$TASK_URL" | sed 's/.*id=//')

# Poll task status until complete (max 60 seconds)
for i in {1..12}; do
  STATUS=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/ce/task?id=$TASK_ID" | jq -r '.task.status')
  
  if [ "$STATUS" = "SUCCESS" ]; then
    echo "✅ SonarQube analysis complete"
    break
  elif [ "$STATUS" = "FAILED" ]; then
    echo "❌ SonarQube analysis failed"
    exit 1
  fi
  
  echo "⏳ Waiting for analysis... ($i/12)"
  sleep 5
done
```

**Fetch PR-specific issues**:
```bash
PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)

# Get issues for the PR
curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&pullRequest=$PR_NUMBER&resolved=false" \
  | jq '.issues[] | {severity, type, message, component, line}'

# Get quality gate status
curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "$SONAR_HOST/api/qualitygates/project_status?projectKey=$PROJECT_KEY&pullRequest=$PR_NUMBER" \
  | jq '.projectStatus.status'
```

**Fallback for SSO-protected instances**:
```bash
# If API returns HTML (SSO redirect), use dashboard URL
echo "⚠️  SonarQube Web API not accessible (SSO required)"
echo "   Manual review required: $SONAR_HOST/dashboard?id=$PROJECT_KEY&pullRequest=$PR_NUMBER"
echo ""
read -p "Press Enter after reviewing dashboard..."
```

### GitHub CLI Integration

**Fetching PR comments** (GraphQL API):
```bash
gh api graphql -f query='
  query($owner: String!, $repo: String!, $pr: Int!) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $pr) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
            comments(first: 10) {
              nodes {
                author { login }
                body
                path
                line
              }
            }
          }
        }
      }
    }
  }
' -F owner='{owner}' -F repo='{repo}' -F pr=42
```

**Replying to review comments** (threaded, not top-level):
```bash
# Reply to specific review comment thread
gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
  -f body="✅ Fixed in commit abc123"
```

**Resolving review threads**:
```bash
gh api graphql -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
      thread { id isResolved }
    }
  }
' -f threadId="$THREAD_ID"
```

**Important**: Use `pulls/comments/$COMMENT_ID/replies` for threaded replies, NOT `gh pr comment` which creates top-level comments.

### SonarQube API Integration

**Prerequisites**:
- `SONAR_TOKEN` environment variable set
- `sonar-project.properties` configured

**Fetching PR issues**:
```bash
PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)
SONAR_HOST=$(grep "^sonar.host.url=" sonar-project.properties | cut -d= -f2)

curl -s -u "$SONAR_TOKEN:" \
  "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&pullRequest=$PR_NUMBER&resolved=false" \
  | jq '.issues[] | {key, message, severity, type, component, line}'
```

**Marking issues as won't-fix**:
```bash
curl -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/issues/do_transition" \
  -d "issue=$ISSUE_KEY" \
  -d "transition=wontfix"
```

**Available SonarQube transitions**:
- `confirm` - Confirm issue
- `resolve` - Mark as resolved
- `reopen` - Reopen issue
- `wontfix` - Won't fix
- `falsepositive` - False positive

### Local SonarQube Scanning

**Run analysis** (requires compiled code):
```bash
# Build project
mvn clean install -DskipTests

# Run scanner
sonar-scanner

# Results uploaded to SonarQube server
# Check dashboard: https://sonarqube.churchofjesuschrist.org/dashboard?id=$PROJECT_KEY
```

**Preview mode** (local-only, no upload):
```bash
sonar-scanner -Dsonar.analysis.mode=preview
```

## Configuration

### SonarQube Project Setup

If `sonar-project.properties` doesn't exist, create it:

```properties
# SonarQube Project Configuration
sonar.host.url=https://sonarqube.churchofjesuschrist.org/
sonar.scanner.skipJreProvisioning=true

sonar.projectKey=fs-eng_<repo-name>_maven-build
sonar.projectName=<Repository Name>
sonar.projectVersion=1.0

# Source directories (adjust for multi-module projects)
sonar.sources=src/main/java
sonar.tests=src/test/java

# Java version
sonar.java.source=17
sonar.java.target=17

# Compiled binaries (required for accurate analysis)
sonar.java.binaries=target/classes
sonar.java.test.binaries=target/test-classes

# Encoding
sonar.sourceEncoding=UTF-8

# Exclusions
sonar.exclusions=**/target/**,**/*.xml,**/*.json
```

**For multi-module Maven projects**:
```properties
sonar.sources=module1/src/main/java,module2/src/main/java
sonar.tests=module1/src/test/java,module2/src/test/java
sonar.java.binaries=module1/target/classes,module2/target/classes
```

### GitHub CLI Authentication

Ensure `gh` is authenticated:
```bash
gh auth status

# If not authenticated:
gh auth login
```

### Environment Variables

Required:
- `SONAR_TOKEN` - SonarQube authentication token

Optional:
- `GH_TOKEN` - GitHub personal access token (if not using `gh auth`)

## Critical Workflow Rule

**ALWAYS resolve GitHub conversations BEFORE pushing commits.**

This is not optional - it's a core part of the workflow:
1. Fix issues
2. Run tests and local sonar-scanner
3. **Resolve conversations** (comment + mark as resolved)
4. Commit changes
5. Push to GitHub

**Why**: Keeps PR clean, shows reviewers what's been addressed, cleaner git history.

## Workflow Details

### 1. Issue Collection Phase

**Collect from multiple sources**:
- GitHub review threads (Copilot bot comments)
- SonarQube pull request analysis
- Inline code comments from reviewers

**Parse and structure**:
```json
{
  "source": "copilot|sonarqube",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "type": "bug|vulnerability|code_smell|coverage",
  "file": "path/to/file.java",
  "line": 42,
  "message": "Issue description",
  "threadId": "MDEyOlJldmlld1RocmVhZDE=" // GitHub only
  "issueKey": "PROJ-123" // SonarQube only
}
```

### 2. Prioritization Phase

**Automatic CRITICAL classification**:
- Security vulnerabilities (CWE-*)
- Null pointer dereferences with high confidence
- Resource leaks (streams, connections, locks)
- Data loss risks
- Infinite loops or recursion

**User confirmation for**:
- Style/formatting issues in existing code
- Refactoring suggestions without clear benefit
- Over-engineering recommendations
- Legacy code issues (not modified in this PR)

### 3. Implementation Phase

**Decision tree**:
```
Is change simple (<20 lines)?
├─ Yes → Implement directly with TDD
└─ No → Is change complex (>100 lines)?
    ├─ Yes → Use xp-pair skill
    └─ No → Use TDD, consider xp-pair
```

**TDD approach selection**:
- **Test-First**: Complex logic, unclear requirements, behavior changes
- **Test-After**: Obvious bugs, simple validation, straightforward refactoring

### 4. Validation Phase

**Multi-level validation**:
1. **Unit tests**: `mvn test -pl <module>`
2. **Local SonarQube**: `sonar-scanner` (catches new issues)
3. **Integration tests**: If applicable
4. **Build verification**: `mvn clean install`

**If new issues found** → Return to Implementation Phase

### 5. Resolution Phase

**For each fixed issue**:
1. Commit changes with descriptive message
2. Push to PR branch
3. Add comment to GitHub thread: "✅ Fixed in {commit-sha}"
4. Resolve GitHub review thread via API
5. (SonarQube auto-resolves on next analysis)

**For won't-fix issues**:
1. Document rationale in PR comment
2. Resolve GitHub thread (mark as acknowledged)
3. Mark SonarQube issue as "wontfix" via API

## Best Practices

### ✅ DO

- **Run local scans** before pushing (save CI/CD time)
- **Batch similar fixes** in one commit (easier review)
- **Document won't-fix decisions** (help future reviewers)
- **Test thoroughly** (avoid introducing new issues)
- **Keep conversations resolved** (track progress)

### ❌ DON'T

- **Skip local validation** (causes CI/CD ping-pong)
- **Mix unrelated fixes** (confuses reviewers)
- **Resolve without fixing** (unless explicitly won't-fix)
- **Ignore CRITICAL issues** (security/correctness first)
- **Over-refactor** (stay focused on PR scope)

## Troubleshooting

### Issue: GitHub API rate limit exceeded

**Solution**: Check rate limit status
```bash
gh api rate_limit
```

Wait for reset or use authenticated requests with higher limits.

### Issue: SonarQube token invalid

**Solution**: Verify token
```bash
curl -u "$SONAR_TOKEN:" \
  "https://sonarqube.churchofjesuschrist.org/api/authentication/validate"
```

Expected response: `{"valid":true}`

### Issue: Can't resolve review threads

**Cause**: Insufficient permissions

**Solution**: Check collaborator permissions
```bash
gh api repos/{owner}/{repo}/collaborators/{username}/permission
```

Requires `write` or `admin` access.

### Issue: sonar-scanner fails with "No source files"

**Cause**: Incorrect paths in `sonar-project.properties`

**Solution**: Verify source paths exist
```bash
# Check paths in sonar-project.properties
grep "^sonar.sources=" sonar-project.properties

# Verify directories exist
ls -la src/main/java
```

### Issue: Local SonarQube scan shows different results than CI

**Cause**: Stale compiled classes

**Solution**: Clean build before scanning
```bash
mvn clean install -DskipTests
sonar-scanner
```

## Future Enhancements

Ideas for improving this skill:

1. **AI-powered prioritization**: Use LLM to assess issue severity contextually
2. **Batch operations**: Resolve multiple threads in one API call
3. **Auto-comment templates**: Reusable explanations for common issues
4. **Issue pattern detection**: Learn from past fixes
5. **Cross-repo learning**: Apply fixes from similar issues in other projects
6. **Metrics tracking**: Record time to fix, issue recurrence
7. **Integration with project memory**: Remember decisions about won't-fix issues

## Related Skills

- **xp-pair**: Use for complex refactorings
- **review**: Complement with manual PR review
- **security-review**: Deep dive on security issues

## References

- [GitHub GraphQL API](https://docs.github.com/en/graphql)
- [SonarQube Web API](https://docs.sonarqube.org/latest/extend/web-api/)
- [GitHub CLI Manual](https://cli.github.com/manual/)
- [SonarScanner Documentation](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/)

## Version History

- **1.0.0** (2026-04-16): Initial implementation
  - GitHub Copilot comment parsing
  - SonarQube API integration
  - Local sonar-scanner validation
  - Review thread resolution
  - TDD-based fix implementation
