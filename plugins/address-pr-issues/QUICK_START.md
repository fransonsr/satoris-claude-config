# Quick Start: Address PR Issues

## One-Command Usage

```bash
# Current branch's PR
/address-pr-issues

# Specific PR number
/address-pr-issues 42
```

---

## The Iteration Reality

**Expect 2-4 iterations before "done"**:

1. ✅ Fix initial issues → ⚠️  New SonarQube issues (methods should be static, etc.)
2. ✅ Fix new issues → ⚠️  More style suggestions from SonarQube
3. ✅ Fix/accept style issues → **Resolve conversations** → Commit → Push
4. ⏳ Wait for CI/CD (30 min) → ⚠️  Copilot adds NEW comments on your changes
5. ✅ Fix significant Copilot suggestions → **Resolve conversations** → Commit → Push → Done

**Critical Rules**:
- **Always resolve conversations BEFORE pushing** (Fix → Resolve → Commit → Push)
- **Local `sonar-scanner` is your best friend** - catches issues in seconds, not 30+ minutes

### The Correct Workflow

```
┌─────────────────────────────────────────┐
│ 1. Fetch issues (Copilot + SonarQube)  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 2. Fix issues (test + sonar-scanner)   │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 3. RESOLVE CONVERSATIONS ⚠️ CRITICAL    │ ← Do this BEFORE commit!
│    - Add comments explaining fixes     │
│    - Mark threads as resolved via API  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 4. Commit changes                       │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 5. Push to GitHub                       │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 6. Wait for CI/CD + new Copilot review │
└────────────────┬────────────────────────┘
                 │
                 └─→ New issues? Return to step 2
```

**Why this order matters**: Reviewers see resolved conversations immediately, commit messages reference already-addressed issues.

---

## Essential Commands

### Fetch Copilot Comments
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

### Fetch SonarQube Issues

**Note**: Enterprise SonarQube instances with SSO may block Web API access. Use dashboard if API returns HTML.

```bash
PROJECT_KEY=$(grep "^sonar.projectKey=" sonar-project.properties | cut -d= -f2)
SONAR_HOST=$(grep "^sonar.host.url=" sonar-project.properties | cut -d= -f2)

# Try API with Bearer token
curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
  "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&pullRequest=42&resolved=false" \
  | jq '.issues[] | {key, message, severity, type, component, line}'

# If that returns HTML (SSO redirect), open dashboard manually:
echo "$SONAR_HOST/dashboard?id=$PROJECT_KEY&pullRequest=42"
```

### Local Validation (Critical!)
```bash
# After EVERY change
mvn clean install -DskipTests && sonar-scanner
```

### Resolve GitHub Thread
```bash
# IMPORTANT: Reply to specific review comment (threaded), not top-level PR comment!

# Add threaded reply
gh api repos/{owner}/{repo}/pulls/comments/$COMMENT_ID/replies \
  -f body="✅ Fixed in $(git rev-parse --short HEAD)"

# Resolve thread
gh api graphql -f query='
  mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
      thread { id isResolved }
    }
  }
' -f threadId="$THREAD_ID"
```

**Get Comment IDs**:
```bash
gh api graphql -f query='...' | jq '.data.repository.pullRequest.reviewThreads.nodes[] | {
  threadId: .id,
  commentId: .comments.nodes[0].databaseId
}'
```

### Mark SonarQube Issue as Won't Fix
```bash
curl -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/issues/do_transition" \
  -d "issue=$ISSUE_KEY" \
  -d "transition=wontfix"

curl -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/issues/add_comment" \
  -d "issue=$ISSUE_KEY" \
  -d "text=Intentional: [reason]"
```

---

## Priority Matrix

| Severity | Examples | Action |
|----------|----------|--------|
| 🔴 **CRITICAL** | Security vulnerabilities, null pointers, resource leaks | Fix immediately |
| 🟡 **HIGH** | Code smells, performance issues, missing tests | Fix now |
| 🟢 **MEDIUM** | Style violations, refactoring suggestions | User decides |
| ⚪ **LOW** | Documentation, minor style | Defer or ignore |

---

## Common Patterns

### Pattern 1: Extracted Method Needs Static

**Issue**: Extract method to reduce complexity
**Result**: SonarQube says "make it static"

```java
// Before
public void processRecord(Record r) {
    // 50 lines of logic...
}

// After extraction
public void processRecord(Record r) {
    validateRecord(r);
    transformRecord(r);
}

private void validateRecord(Record r) { ... }  // ❌ SonarQube: "make static"
private static void validateRecord(Record r) { ... }  // ✅
```

### Pattern 2: Duplicate String Literals

**Issue**: Fix one issue, introduces string duplication
**Solution**: Extract constant

```java
// Iteration 1: Fix resource leak
try (BufferedReader br = ...) {
    if (line.isEmpty()) {
        throw new IllegalArgumentException("Invalid format");  // ❌ SonarQube: duplicate
    }
    if (line.length() < 10) {
        throw new IllegalArgumentException("Invalid format");  // ❌ Duplicate!
    }
}

// Iteration 2: Extract constant
private static final String INVALID_FORMAT_MSG = "Invalid format";
```

### Pattern 3: Copilot Re-Analysis After Commit

**Issue**: Push fix → Copilot analyzes → NEW suggestions on your changes

**Strategy**:
1. Fix initial issues
2. Push
3. **Wait 30 min for CI/CD**
4. Check for new Copilot comments
5. Fix only CRITICAL/HIGH, defer others

---

## Stopping Criteria

**Stop iterating when**:
- ✅ All CRITICAL issues fixed
- ✅ All HIGH issues fixed
- ✅ MEDIUM issues evaluated (fix/won't-fix decided)
- ✅ No new issues from local sonar-scanner
- ✅ Post-commit Copilot comments addressed (if any)

**Don't chase perfection** - 2-3 iterations is typical, 4+ is diminishing returns.

---

## Troubleshooting

### "sonar-scanner: No source files found"
```bash
# Check sonar-project.properties paths
grep "^sonar.sources=" sonar-project.properties
ls -la src/main/java  # Verify paths exist
```

### "GitHub API rate limit"
```bash
gh api rate_limit
# Wait for reset or use personal access token
```

### "Can't resolve review threads"
```bash
# Check permissions
gh api repos/{owner}/{repo}/collaborators/{username}/permission
# Need 'write' or 'admin'
```

### Local vs CI SonarQube results differ
```bash
# Ensure clean build
mvn clean install -DskipTests
sonar-scanner
```

---

## Files Required

✅ **Must have**:
- `sonar-project.properties` (create from template if missing)
- `SONAR_TOKEN` environment variable
- `gh` CLI authenticated

✅ **Nice to have**:
- `.editorconfig` (consistent formatting)
- Pre-commit hooks (catch issues before commit)

---

## Example Session Flow

```
User: /address-pr-issues 42