# Handoff Task Skill

Create comprehensive handoff documents for tasks to be implemented in a fresh Claude Code session.

## Usage

```
/handoff <task-id> <brief-description>
```

**Examples**:
- `/handoff 4.16.3 Implement MasterIndexWriter for top-level indices`
- `/handoff 5.2 Add retry logic to Kafka consumer`
- `/handoff bug-123 Fix null pointer in ChunkWriter`

## What This Skill Does

1. **Gathers Context**:
   - Reads task details from implementation docs
   - Identifies related code files and patterns
   - Reviews existing similar implementations
   - Extracts architectural decisions from CLAUDE.md

2. **Creates Handoff Document** in `~/.claude/handoff/`:
   - Executive summary (What/Why/Status)
   - Technical specifications
   - Implementation plan with phases
   - Code examples following project patterns
   - Acceptance criteria
   - Testing strategy
   - Reference materials

3. **Provides Implementation Guidance**:
   - TDD approach recommendation (test-first vs test-after)
   - When to use `/xp-pair` skill
   - Step-by-step workflow
   - Risk mitigation strategies

## Document Structure

### CRITICAL: Verified Context, Not Assumptions

**❌ BAD**: "The legacy system probably handled nulls"  
**✅ GOOD**: "Checked legacy PersonaFilter.java (commit abc123) - it DOES check for null persona refs at line 67"

A 5-minute verification before handoff saves 30 minutes of pivot during implementation.

### Required Sections

1. **Executive Summary**
   - What: Clear 1-2 sentence description
   - Why: Business/technical justification
   - Status: Current state and blockers
   - Context: How this fits in the larger system

2. **Verified Context** (NOT Assumptions)
   - Known Facts (with verification citations)
     - File paths, line numbers, commit hashes
     - Tested behaviors (not guessed)
     - Performance measurements (not estimates)
   - Explicit Unknowns (needs discovery during implementation)
     - Questions to investigate
     - Where to look for answers
     - Who to ask if needed

3. **Scope Clarity** (Surgical Precision)
   - What to Change (file paths + line numbers)
   - What NOT to Change (explicit boundaries)
   - Decision Authority
     - What implementer decides
     - What requires asking first

4. **Prior Work & Patterns**
   - Similar Patterns in Codebase (with file:line references)
   - Anti-Patterns to AVOID (with reasons)
   - Related PRs (successful and failed attempts)

5. **Technical Specifications**
   - Class/component design
   - API signatures
   - Key algorithms or logic
   - Known Gotchas (edge cases, constraints)

6. **Implementation Plan**
   - Phase-by-phase breakdown
   - Estimated time per phase
   - Dependencies between phases
   - Explicit Test Strategy Justification (why test-first or test-after)

7. **Acceptance Criteria** (Testable)
   - Definition of Done (checkboxes)
   - Specific test names that must pass
   - Manual verification steps
   - Quality gates (Sonar, Copilot)

8. **Iteration Expectations**
   - Expected complexity (LOW/MEDIUM/HIGH)
   - Likely number of feedback rounds
   - When to pause and ask

9. **Skill Routing Recommendations**
   - Use xp-pair? (YES/NO with justification)
   - Use address-pr-issues? (YES/NO)
   - Other skills needed?

10. **Reference Materials**
    - Existing code patterns to follow
    - Legacy code locations (if applicable)
    - Related PRs or issues
    - Documentation links

### Optional Sections (based on complexity)

- **API Changes**: If task requires interface modifications
- **Database Migrations**: If schema changes needed
- **Performance Considerations**: If performance-critical
- **Security Considerations**: If security-sensitive
- **Backward Compatibility**: If breaking changes possible
- **Verification Commands**: Quick copy-paste commands to validate context
- **Common Pitfalls**: Mistakes implementer is likely to make (vs edge cases)

## TDD Approach Guidance

The skill analyzes task complexity and recommends:

**Test-First (RED-GREEN-REFACTOR)** when:
- Complex algorithms or business logic
- Unclear requirements or edge cases
- Behavior changes to critical code paths
- Need to think through the problem

**Test-After (IMPLEMENT-TEST-REFACTOR)** when:
- Simple CRUD operations
- Obvious bug fixes with known solutions
- Refactoring with clear target state
- Straightforward validation logic

## XP-Pair Usage Guidance

The skill identifies scenarios requiring `/xp-pair`:

**Use XP-Pair For**:
- API changes affecting multiple classes
- Complex RDD/Spark transformations
- Architectural design decisions
- Refactoring with unclear structure

**Don't Use XP-Pair For**:
- Unit tests following established patterns
- Simple CRUD implementations
- String manipulation or formatting logic

## File Naming Convention

Handoff documents are saved as:
```
~/.claude/handoff/<task-id>-<slug>.md
```

Examples:
- `task-4.16.2-collection-indices-writer.md`
- `bug-123-null-pointer-fix.md`
- `feature-kafka-retry-logic.md`

## Self-Check Before Finalizing Handoff

Run these commands to verify document quality (executable verification):

### Verify All File Paths Exist
```bash
# Extract and verify file paths from handoff document
grep -oP '`[^`]+\.java`' ~/.claude/handoff/task-*.md | sed 's/`//g' | while read file; do
  [ -f "$file" ] || echo "❌ MISSING: $file"
done
# Expected output: Nothing (all files exist) or specific missing files
```

### Verify No TODOs Remain
```bash
# Check for unfinished sections
grep -i "TODO" ~/.claude/handoff/task-*.md && echo "❌ ERROR: Unfinished sections" || echo "✅ No TODOs"
```

### Verify All Commit Hashes Are Real
```bash
# Extract and validate commit hashes
grep -oP 'commit [a-f0-9]{7}' ~/.claude/handoff/task-*.md | while read _ hash; do
  git log --oneline | grep -q "$hash" || echo "❌ INVALID COMMIT: $hash"
done
```

### Verify Line Numbers Are Current (Manual Check)
For each file:line reference, spot-check that line numbers haven't shifted due to recent commits:
```bash
# Example: Verify PersonaFilter.java:45-67 still contains filter logic
sed -n '45,67p' PersonaFilter.java | grep -q "filter" && echo "✅ Lines match" || echo "❌ Lines shifted"
```

**Output Goal**: Must be 0 errors before handoff is ready.

---

## Handoff Document Quality Checklist

Before finalizing, the skill verifies:

### Critical Quality Gates (MUST HAVE)
- [ ] **Verified context** (NOT assumptions) - with file:line citations or commit hashes
- [ ] **Explicit unknowns** listed (what needs discovery)
- [ ] **Scope boundaries** clear (what to change + what NOT to change)
- [ ] **Decision authority** explicit (what implementer decides vs asks)
- [ ] **Acceptance criteria testable** (specific test names, checklists)

### Essential Content (REQUIRED)
- [ ] Executive summary is clear and concise
- [ ] Prior work referenced (similar patterns + anti-patterns with reasons)
- [ ] Technical specifications include code examples
- [ ] Known gotchas documented (edge cases, constraints)
- [ ] Implementation plan has estimated effort per phase
- [ ] Test strategy justified (why test-first or test-after)
- [ ] Iteration expectations set (complexity, likely rounds)
- [ ] Skill routing recommendations (xp-pair yes/no with justification)

### Supporting Materials (HELPFUL)
- [ ] Reference materials link to actual code files with line numbers
- [ ] Related PRs referenced (successful + failed attempts)
- [ ] Legacy code locations cited (if applicable)
- [ ] Risks identified with mitigation strategies
- [ ] Manual verification steps included

### Self-Contained Verification
- [ ] Implementer can start without reading conversation history
- [ ] All file paths are absolute and verified to exist
- [ ] All line number references checked for accuracy
- [ ] All commit hashes or PR numbers are real (not placeholders)
- [ ] No "TODO: fill this in" sections remain

---

## For Implementers: Handoff Reception Checklist

When you receive a handoff, run this quick sanity check before starting work (15 minutes investment saves hours):

### Context (5 min)
- [ ] Read Executive Summary - understand what/why
- [ ] Scan Known Facts - spot-check 2-3 file:line references exist
- [ ] Review Explicit Unknowns - note what to discover during implementation

### Scope (3 min)
- [ ] Identify files to change (exact line ranges clear?)
- [ ] Identify boundaries (what NOT to change is explicit?)
- [ ] Understand decision authority (when to ask vs decide)

### Approach (5 min)
- [ ] Test strategy makes sense (test-first or test-after justification clear?)
- [ ] Skill routing appropriate (xp-pair needed or handle directly?)
- [ ] Prior work examples accessible (can find referenced files?)

### Ready Check (2 min)
- [ ] Acceptance criteria testable (can verify each checkbox?)
- [ ] Gotchas understandable (edge cases/constraints clear?)
- [ ] Stop conditions clear (know when to ask for help?)

**If any checkbox fails**: Ask clarifying questions BEFORE starting implementation.

**Total time**: 15 minutes (saves hours of mid-implementation confusion)

## Integration with Project Standards

The skill automatically incorporates project-specific patterns from:

- **CLAUDE.md**: Architectural decisions, naming conventions
- **~/.claude/CLAUDE.md**: Coding standards (SOLID, TDD, refactoring)
- **Existing code**: Patterns from similar implementations
- **Documentation**: Links to relevant architecture docs

## Example Output Structure

```markdown
# Handoff Document: Task X.Y.Z - Component Name

**Date**: YYYY-MM-DD
**Task**: Brief description
**Priority**: CRITICAL/HIGH/MEDIUM/LOW
**Estimated Effort**: X days/weeks
**Complexity**: LOW/MEDIUM/HIGH

---

## Executive Summary

**What**: One-sentence description

**Why**: Justification

**Status**: Current state

**Context**: System architecture context

---

## Verified Context

### Known Facts ✅
- Current implementation: `PersonaFilter.java:45-67` checks persona IDs
- Performance baseline: 85ms for 10k records (measured 2026-04-15)
- Legacy behavior: `LegacyFilter.java:78` (commit abc123) DOES handle null refs

### Explicit Unknowns ❓
- Does production data contain null resource URIs? → Check S3 sample: `s3://bucket/test-data/sample.json`
- Is this code path hit during incremental sync? → Ask team lead (John Doe)
- What's the acceptable performance degradation? → Product owner approval needed

---

## Scope Clarity

### What to Change 🎯
- File: `PersonaFilter.java`
  - Lines 45-67: Add null checks before filter operation
  - Lines 78-92: Add null check for resourceUri extraction
- File: `PersonaFilterTest.java`
  - Add 3 new test methods (null persona, null URI, edge cases)

### What NOT to Change 🚫
- DO NOT refactor entire filter chain (out of scope, separate PR planned)
- DO NOT change public API signatures (breaks downstream consumers)
- DO NOT optimize sort algorithm (performance acceptable, premature optimization)

### Decision Authority

**You Decide**:
- Implementation details (method names, local variables)
- Test structure (Given-When-Then vs Arrange-Act-Assert)
- Refactoring within scope (extract methods, improve naming)

**Ask First**:
- Changing public API signatures
- Adding new dependencies (even test dependencies)
- Performance tradeoffs (accuracy vs speed)
- Scope expansion (found related bug - fix now or separate PR?)

---

## Prior Work & Patterns

### Follow These Patterns ✅
- `CollectionMetadataReader.java:78-92` - CSV parsing with null checks
- `ChunkWriter.java:155-170` - Explicit close() for non-AutoCloseable
- CLAUDE.md section 2.3 - JSpecify null-safety annotations

### AVOID These Patterns ❌
- PR #45 approach (had performance issues, reverted in PR #52)
- Using `Stream.filter(Objects::nonNull)` (team prefers explicit checks for clarity)
- Lombok `@Builder` (team preference for explicit constructors)

### Related PRs
- PR #63 - Similar filtering logic (successful pattern)
- PR #45 - Performance issue (learn from mistakes)
- PR #52 - Revert of #45 (explains why)

---

## Quick Verification Commands

Copy-paste commands to validate context during implementation:

### Verify Performance Baseline
```bash
# Run existing implementation against test data
mvn test -Dtest=PersonaFilterBenchmark
# Expected: 85ms for 10k records
```

### Check Production Data Format
```bash
# Sample production records (anonymized)
aws s3 cp s3://bucket/test-data/sample.json - --profile dev | head -20
```

### Verify Legacy Behavior
```bash
# Legacy commit with null handling
git show abc123:LegacyFilter.java | grep -A 10 "null check"
```

### Verify Referenced Files Exist
```bash
# Check that all file paths in handoff are current
test -f PersonaFilter.java && echo "✅ PersonaFilter.java exists" || echo "❌ File missing"
test -f PersonaFilterTest.java && echo "✅ PersonaFilterTest.java exists" || echo "❌ File missing"
```

---

## Technical Specifications

### Class Design
[Code examples]

### Known Gotchas 🔥
- Empty strings (not just null) cause silent failures → check `StringUtils.isBlank()`
- Duplicate persona IDs in Set cause size mismatch → use List for comparison
- CSV column 3 can contain commas → use `split(regex, limit)` not `split(regex)`

### Constraints
- Must maintain Java 17 compatibility (no JDK 21+ features like pattern matching)
- Can't use lombok (@Builder) - team preference for explicit constructors
- Test coverage required: happy path + edge cases + errors (minimum 3 tests per method)
- No external dependencies (use existing libraries only)

### Common Pitfalls (Mistakes You'll Be Tempted to Make)

❌ **Pitfall #1**: Using `Stream.filter(Objects::nonNull)` for clarity
- **Why tempting**: Concise, idiomatic Java
- **Why wrong**: Team prefers explicit checks (readability over brevity)
- **Correct pattern**: `if (value == null) { continue; }`

❌ **Pitfall #2**: Adding AssertJ dependency for better assertions
- **Why tempting**: Project already uses AssertJ in other modules
- **Why wrong**: This module intentionally uses JUnit only (dependency minimization)
- **Correct pattern**: `assertEquals(expected, actual)`

❌ **Pitfall #3**: Fixing related bug you discovered while implementing
- **Why tempting**: It's right there! Fix it now!
- **Why wrong**: Scope creep, harder to review, unclear commit history
- **Correct pattern**: Note it, create separate issue/PR

---

## Implementation Plan

### Phase 1: [Name] (X hours)
[Description and tasks]

### Phase 2: [Name] (X days)
[Description and tasks]

### Test Strategy Justification

**Use Test-First (RED-GREEN-REFACTOR)** because:
- Requirements unclear (test helps clarify edge cases)
- Privacy-critical code (comprehensive coverage required)
- Multiple valid approaches (test defines contract first)

**NOT Test-After** because:
- Design is NOT obvious (need to explore via tests)
- Edge cases non-trivial (null, empty, duplicates)

---

## Acceptance Criteria (Testable)

### Definition of Done ✅
- [ ] Test: `shouldRemoveRelationshipsWithNullPersonaId()` passes
- [ ] Test: `shouldRemoveRelationshipsWithNullResourceUri()` passes
- [ ] Test: `shouldHandleEmptyPersonaIds()` passes
- [ ] All existing tests still pass (481/481)
- [ ] SonarQube: No new BLOCKER/CRITICAL issues (check before PR)
- [ ] GitHub Copilot: Address all blocking issues (max 2 feedback rounds expected)
- [ ] Manual verification: Run against `/test-data/sample-data.json` (10k records, <100ms)
- [ ] Code review: Self-review checklist complete (see CLAUDE.md)

### Success Metrics
- Code coverage: >80% for PersonaFilter (existing baseline: 75%)
- Performance: <100ms for 10k records (existing: 85ms, allow 15ms degradation)
- No regressions: All 481 existing tests pass

---

## Iteration Expectations

### Expected Complexity: LOW
- Straightforward null checks (pattern established)
- Well-understood requirements
- No architectural changes

### Expected Iterations
- **Likely**: 1-2 rounds (implementation → Copilot feedback → address)
- **If blockers**: Pause and ask (missing test data, unclear legacy behavior)
- **Don't spin**: If stuck >30min on same issue, ask for guidance

### Stop and Ask If:
- **Time**: Spent >30min stuck on same issue (not making progress)
- **Scope**: Discovered related bug (fix now or separate PR?)
- **Design**: Found 3+ valid approaches (need architectural input)
- **Data**: Production data format doesn't match assumptions
- **Tests**: Can't figure out how to test behavior (need test design help)
- **Dependencies**: Need to add new library (requires approval)

### Monitoring
- After commit: Wait 10 min for Copilot feedback
- Expected feedback: Possibly style suggestions (low priority)
- Address BLOCKER/CRITICAL issues immediately
- INFO/MINOR issues: Can defer to separate cleanup PR

---

## Skill Routing Recommendations

### Use `/xp-pair`? **NO**
- Complexity: LOW (straightforward null checks)
- Pattern established (similar to PR #63)
- No architectural decisions needed

**Switch to xp-pair IF**:
- Complexity increases (unexpected edge cases)
- Design becomes unclear (multiple refactoring attempts)

### Use `/address-pr-issues`? **NO**
- Not responding to PR feedback (creating new PR)
- Use AFTER first Copilot feedback if issues complex

### Other Skills? **NO**
- No security-review needed (not security-critical)
- No simplify needed (straightforward implementation)

---

## Reference Materials

### Existing Code Patterns
- File: `path/to/pattern.java`
  - Lines X-Y: Relevant pattern

### Legacy Code Reference (if applicable)
- Repository: legacy-repo
- Commit: abc123
- Key class: LegacyClass.java:67 (null check implementation)

---

## Risk Mitigation

### Risk 1: Production data contains unexpected null combinations
**Likelihood**: Medium (we've only checked DEV data)
**Impact**: High (privacy leak if filter fails)
**Detection**: Integration test against prod sample (run before merge)
**Mitigation**:
- Add defensive `Objects.requireNonNull()` at method entry
- Log warning for null combinations (monitors can alert)
- Fall back to conservative filter (remove rather than leak)

**Code Example**:
```java
if (personaId == null || resourceUri == null) {
  LOGGER.warn("Null values in filter - removing relationship: persona={}, uri={}",
              personaId, resourceUri);
  return true; // Remove this relationship (fail safe)
}
```

---

## Development Workflow

1. Read existing code (PersonaFilter.java, PersonaFilterTest.java)
2. Verify context (check legacy code commit abc123)
3. Write failing tests (RED phase)
4. Implement null checks (GREEN phase)
5. Refactor (extract methods if >15 lines)
6. Run full test suite (`mvn clean test`)
7. Commit and wait for Copilot feedback
8. Address blocking issues
9. Mark acceptance criteria complete

---

## Next Steps After Completion

**Task X.Y.Z+1**: [Next task description]

---

## Questions for Product Owner

1. [Question 1]
2. [Question 2]
```

## Implementation Notes

### Context Gathering Strategy

1. **Search for task in docs**:
   - Check `docs/implementation/implementation-tasks.md`
   - Search for task ID in all markdown files
   - Read related sections (±50 lines context)

2. **Identify code patterns**:
   - Find similar classes in codebase
   - Extract common patterns (constructor, methods, tests)
   - Note naming conventions

3. **Review architecture**:
   - Read relevant sections of CLAUDE.md
   - Check for architectural decisions affecting task
   - Note any constraints or guidelines

4. **Legacy code analysis** (if applicable):
   - Check if legacy implementation exists
   - Extract key logic and patterns
   - Note differences to avoid or improvements to make

### Document Generation Process

1. **Template Selection**: Choose template based on task type
   - Feature implementation
   - Bug fix
   - Refactoring
   - Infrastructure/tooling

2. **Content Population**: Fill template with gathered context

3. **Validation**: Run quality checklist

4. **Output**: Write to `~/.claude/handoff/` with standardized filename

## Error Handling

If task details are unclear or missing:
- Prompt user for clarification
- Suggest reading specific documentation
- Offer to search codebase for related context

If no similar patterns found:
- Note this in handoff document
- Recommend architectural review
- Suggest prototyping approach

## Success Criteria

A good handoff document enables a fresh Claude session to:
- Understand the task without reading the full conversation history
- Know exactly what to implement and how
- Have clear acceptance criteria for completion
- Follow project patterns and standards
- Know when to use TDD vs test-after
- Know when to use `/xp-pair` skill
- Mitigate risks proactively

## Future Enhancements

- [ ] Automatically create GitHub issue from handoff doc
- [ ] Link to related Jira tickets
- [ ] Generate task checklist in task management system
- [ ] Validate handoff doc against project templates
- [ ] Auto-update status in implementation-tasks.md

---

**Skill Version**: 1.0
**Last Updated**: 2026-04-22
**Maintainer**: fransonsr
