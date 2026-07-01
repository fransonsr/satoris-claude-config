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

Box numbers below match SKILL.md's actual step/sub-step headers exactly — if a step here doesn't
have a numbered box, it's folded into the box before it, not skipped:

```
┌─────────────────────────────────────────┐
│ 1. Fetch issues (Copilot + SonarQube)  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 1.6. Filter trivial threads (auto)     │ ← classify-threads.sh: silent/
│      LGTM-only threads react+resolve   │   already-resolved auto-handled
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 2. Assess complexity                    │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 2.5. Adversarial review gate (MANDATORY)│ ← does this round warrant
└────────────────┬────────────────────────┘   /adversarial-review first?
                 │
┌────────────────▼────────────────────────┐
│ 3. Prioritize issues                    │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 3.5. Adversarial review (if gated in)  │ ← delegated /adversarial-review
└────────────────┬────────────────────────┘   --rounds 1, before fixing
                 │
┌────────────────▼────────────────────────┐
│ 3.7. Pre-fix sweep (MANDATORY)         │ ← grep the PR's touched files for
│      Fix every instance, not just the  │   the same pattern before fixing —
│      one flagged                        │   always run this step
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 3.8. Show decision summary to user     │ ← process decisions (test
└────────────────┬────────────────────────┘   approach, risk factors) before
                 │                              implementing
┌────────────────▼────────────────────────┐
│ 4. Create implementation plan          │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 4.1. Execute fixes (iterative loop)    │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 4.5. Post-fix cascade sweep (MANDATORY)│ ← re-sweep fixes for cascading
│      Add any hits before committing    │   issues before committing
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 5. Validate locally (sonar-scanner)    │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 6. RESOLVE CONVERSATIONS ⚠️ CRITICAL    │ ← Do this BEFORE commit!
│    - Add comments explaining fixes     │
│    - Mark threads as resolved via API  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 7. Commit & push (protected-branch     │
│    guard checked first)                 │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│ 8. Re-request review & monitor CI/CD   │
└────────────────┬────────────────────────┘
                 │
                 └─→ New issues? Return to step 4.1
```

**Why this order matters**: Reviewers see resolved conversations immediately, commit messages reference already-addressed issues.

---

## Essential Commands

**Use the scripts in `scripts/` for all of these — see SKILL.md's "Use Automation Scripts
First" table.** Don't hand-write `gh api graphql` or SonarQube `curl` calls; a script or
`lib/` function already does it.

### Fetch Copilot Comments + Cache Threads
```bash
./scripts/init-pr-state.sh 42
./scripts/fetch-pr-threads.sh 42 --unresolved-only
```

### Filter Trivial Threads (Step 1.6)
```bash
PR_AUTHOR=$(gh pr view 42 --json author -q .author.login)
./scripts/classify-threads.sh 42 "$PR_AUTHOR"
```
Auto-resolves purely-complimentary threads ("LGTM", "👍") and skips already-resolved ones with
no substantive activity — before you spend any triage effort on them. See SKILL.md Step 1.6.

### Fetch SonarQube Issues
```bash
./scripts/check-sonar-quality-gate.sh 42
```
**Note**: Enterprise SonarQube instances with SSO may block Web API access — the script falls
back to telling you to check the dashboard manually if the API returns HTML.

### Local Validation (Critical!)
```bash
# After EVERY change
mvn clean install -DskipTests && sonar-scanner
```

### Resolve GitHub Thread
```bash
# IMPORTANT: this replies threaded + resolves — never use `gh pr comment` (top-level, doesn't resolve)
./scripts/resolve-thread.sh 42 "$THREAD_ID" "Fixed in $(git rev-parse --short HEAD)"

# Or in bulk:
./scripts/resolve-threads-bulk.sh 42 --threads 'THREAD_ID_1,THREAD_ID_2' --message 'Fixed'
```

**Look up a thread/comment ID** from the cache instead of re-fetching:
```bash
jq -r 'select(.path == "File.java" and .line == 42) | {threadId, commentId}' "$THREADS_FILE"
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
2. Derive DIRECTIONAL_COUNT from Step 2's persisted `triage.json` (see SKILL.md's "Derive
   DIRECTIONAL_COUNT" subsection, end of the Execute Fixes step) — the count of `directional`-
   classified issues you actually fixed this round, not everything triaged
3. Push (after the protected-branch guard passes)
4. If `DIRECTIONAL_COUNT >= 1` (a fix changed what the PR does), actively re-request Copilot
   review — don't just wait for it (see SKILL.md's Re-Request Review step)
5. Wait for CI/CD, then check for new Copilot comments
6. Fix only CRITICAL/HIGH, defer others

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