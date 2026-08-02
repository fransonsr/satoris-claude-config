---
name: xp-pair
description: XP pair programming with navigator (design oversight) and driver (implementation). Use for complex features requiring design oversight, TDD coaching, or high-quality code with continuous review.
argument-hint: [task-description | "Task: ... Acceptance Criteria: ..."]
---

# XP Pair Programming

Creates a two-person XP pairing team:
- **Navigator** (you): Design oversight, architectural decisions, code review, TDD enforcement
- **Driver** (subagent): Implementation, coding, following TDD discipline

## Inputs

`args` is either a bare task description, or a structured payload of the form:
```
Task: <one-line summary of what to build>
Acceptance Criteria:
- <criterion>
- <criterion>
...
```
When the `Acceptance Criteria:` block is present, its first line's `Task:` text becomes the
`TaskCreate` subject in Step 1 below, and the criteria become that task's description checklist
verbatim — skip re-deriving them. When `args` is only a bare description (no `Acceptance
Criteria:` block), the navigator derives the acceptance criteria itself in Step 1, same as before
this structured form existed. `address-pr-issues`' Step 4.1 is the caller that sends the
structured form, via `Skill(xp-pair, args="Task: ...\nAcceptance Criteria:\n- ...")`.

## When to Use

**IMPORTANT: If complexity doesn't warrant pairing, discuss with user first**
- Before spawning a driver, assess if the task truly needs collaborative oversight
- Example: "This looks like straightforward validation. Should I use xp-pair or handle directly?"

**Good use cases:**
- ✅ Complex features requiring design oversight
- ✅ High-risk code (security, data loss potential)
- ✅ Multiple valid design approaches needing discussion
- ✅ Code with unclear requirements needing collaboration

**When you think "this is straightforward" - STOP:**

**Things that SEEM simple but consistently hide bugs:**
- Prefix/suffix stripping
  - Example: Missed super., nested classes, fully-qualified names
- Name matching and resolution
  - Example: Missed collisions, shadowing, package disambiguation
- Type resolution
  - Example: Missed wildcards, fully-qualified patterns, imports
- Collection operations
  - Example: Missed HashMap nondeterminism, duplicates, empty
- Null/empty checks
  - Example: Missed combinations, parent fields, field hiding

**If your change involves ANY of the above → Use xp-pair OR test-first**

**Only skip when ALL of these are true:**
- Change is <20 lines
- Zero string/collection manipulation
- Single execution path (no conditionals)
- Adding logging/comments/constants only
- Can enumerate 3+ edge cases right now

## XP-Pair Decision Checklist

Before deciding to skip xp-pair, complete this checklist:

**Complexity Factors:**
- [ ] >50 lines of code to change
- [ ] >3 files to modify
- [ ] >5 methods to change
- [ ] Involves string/collection manipulation
- [ ] Multiple conditional paths
- [ ] Cross-class interactions
- [ ] Type/name resolution

**If 2+ boxes checked → MUST use xp-pair OR test-first with adversarial review**

**Justification for skipping xp-pair:**
[If skipping, state specific reason and show to user for approval]

## Setup

1. Create a team for this pairing session
2. Spawn a driver subagent with explicit instructions
3. Define acceptance criteria before driver starts coding
4. Review code after each RED-GREEN-REFACTOR cycle

## Instructions

### Step 1: Create Team and Tasks

```
TeamCreate with team_name like "feature-name-dev"
```

Break the work into clear tasks with acceptance criteria:

```
TaskCreate:
  subject: "Implement ConfigParser"
  description: |
    Acceptance Criteria:
    - [ ] Parses --flag arguments into config object
    - [ ] Validates required fields
    - [ ] Provides sensible defaults
    - [ ] Immutable configuration
    - [ ] 15+ tests covering parsing, validation, defaults
```

**Task List Hygiene:**
- Create ONE task per deliverable (avoid duplicates)
- Use generic driver name "driver" when spawning (not feature-specific)
- Driver claims tasks via TaskUpdate, not automatic task creation
- Example: Create tasks #1, #2, #3 first, then spawn "driver" who claims #1

### Step 2: Architecture Planning (Before Implementation)

**Before spawning the driver**, have a brief architecture discussion:

**Questions to address:**
- What are the key design decisions?
- Are there multiple valid approaches to consider?
- What patterns from existing code should be followed?
- **Review data formats and external dependencies** (file structures, API formats, S3 paths, database schemas)
- Any edge cases or gotchas to watch for?

**CRITICAL: Verify Assumptions Before Deciding (Parallel Workflow)**

Use the Workflow tool to run discovery agents in parallel before committing to an approach. This keeps the architecture discussion grounded in facts rather than assumptions, without loading all the discovery work into this session's context.

Spawn these agents simultaneously, each receiving the task description and relevant file paths:

- **Legacy code agent**: How did the legacy implementation actually work? What patterns did it use?
- **Data format agent**: What do actual file formats, API responses, or database schemas look like? Read samples from disk or S3.
- **Codebase patterns agent**: What similar patterns exist in the current codebase that the implementation should follow?
- **Handoff/docs agent**: What do handoff documents, READMEs, and inline comments say about constraints or decisions?

Each agent returns a brief findings summary.

**Why this matters**: Assumptions discovered to be wrong during implementation require rework and wasted TDD cycles. Five minutes of parallel verification saves thirty minutes of pivot.

**Generative Design Guidance (Fable)**

The discovery agents above only gather facts — nothing yet turns those facts into an actual
design recommendation; historically the navigator did that synthesis directly, at whatever model
the session happens to be running. Once the discovery agents return, spawn one more agent —
sequential, not parallel with them, since it consumes their output — with `model: 'fable'` for
increased reasoning depth on the design decision itself. It receives:
- The task description
- Every discovery agent's findings summary
- An instruction to resolve and read the pattern file itself: prefer
  `~/.claude/copilot-review-patterns.md`; if absent, fall back to the bundled
  `plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md` snapshot
  (mirroring `adversarial-review`'s own Setup Step 1). Enumerate class names with
  `grep "^### [0-9]" <file>`, pick the classes whose names or `**How to find**` sections match
  this task's characteristics, and read only those sections — the navigator passes the task
  description and discovery findings, never the pattern text itself; the agent selects and reads
  its own sections, for the same context-cost reason `adversarial-review` reads its pattern file
  per-agent rather than per-orchestrator (see that skill's Setup Step 5)

It returns a design recommendation with explicit tradeoffs, plus a "watch out for" list of edge
cases sourced from the matching pattern classes — not just "what to build" but "what has broken
in similar code before." The navigator presents this synthesis as the basis for the discussion
with the user below — it augments, not replaces, the human sign-off this step already requires.

**Example synthesis** (now produced by the design-synthesis agent, presented by the navigator —
using two of the real classes in `copilot-review-patterns.md`, not the informal "Things That SEEM
Simple But AREN'T" list above):
```
"Verification complete:
- Legacy: Uses StringUtils.split(line, ",", 4) — limit param handles commas in data columns
- Data format: S3 key pattern is {prefix}/{yyyy}/{MM}/{dd}/{recordId}.json (confirmed from sample)
- Codebase: CollectionMetadataReader uses DataStorage abstraction — PartitionMetadataReader should match
- Docs: Handoff says 'cross-account S3 access requires DataStorage, not S3Client directly'
- Watch out for (Defensive Guards (null / type / encoding) pattern class): delimiters appearing
  inside data columns, trailing empty fields, and lines with fewer columns than expected —
  also (Semantic Correctness / Logical Completeness): confirm the split's limit parameter still
  matches the schema if the column count ever changes

Decision: Use StringUtils.split approach with DataStorage abstraction."
```

**Examples:**

For a CLI script:
```
"Before we start, let's discuss the approach:
- How should we filter results? Server-side vs client-side?
- What's a good default limit?
- Output format: table, JSON, or both?
- Should we follow the same confirmation pattern as other scripts?"
```

For a web feature:
```
"Before we start, let's discuss the approach:
- Client-side validation or server-side only?
- REST API or GraphQL?
- Optimistic updates or loading states?
- Should we follow the same error handling pattern as the auth module?"
```

For a data processing task:
```
"Before we start, let's discuss the approach:
- Batch processing or streaming?
- Where should validation happen? (source, transform, sink)
- Error handling: fail-fast or collect errors?
- Should we use the same retry pattern as the export job?"
```

This prevents the driver from making architectural decisions post-facto and ensures alignment upfront.

**Model selection**: design-synthesis agent (above) → `fable`. The 4 discovery agents stay on the
session default — omit a `model` override for them — pure fact-finding doesn't need the extra
reasoning depth; only the step that turns facts into a decision does.

### Step 3: Spawn Driver

```
Task(
  subagent_type="general-purpose",
  team_name="<your-team-name>",
  name="driver",
  prompt="<driver instructions below>"
)
```

**Driver Instructions Template:**

```
You are the DRIVER in an XP pair programming session with the navigator.

## Test-Complete Development

**CRITICAL: Every production code change MUST have tests**

**For code with unit test frameworks (Java, Python, JavaScript, etc.):**

**You MUST choose an approach for each task:**

**Approach A: Test-First** (use when design needs thinking through)
- Complex algorithms, unclear requirements, critical code paths
- Follow RED-GREEN-REFACTOR strictly:
  1. RED: Write failing test, verify it fails correctly
  2. GREEN: Minimal code to pass
  3. REFACTOR: Improve quality relentlessly

**Approach B: Test-After** (use when design is obvious)
- Simple CRUD, known bug fixes, straightforward validation
- Follow IMPLEMENT-TEST-REFACTOR:
  1. IMPLEMENT: Write production code
  2. TEST: Write comprehensive tests (happy + edge + error cases)
  3. REFACTOR: Improve both production and test code

**CRITICAL: If unsure which approach, ask navigator before starting**

**For code without unit test frameworks (bash scripts, SQL, IaC, config files):**
- Define acceptance criteria / manual test scenario
- Implement the feature
- Validate (syntax check, static analysis, manual execution)
- Refactor for quality
- Report to navigator

**Mandatory: Every production code change MUST have tests**

**Before reporting task complete:**
- [ ] All production code has corresponding tests
- [ ] Tests cover happy path + edge cases + errors
- [ ] All tests pass (run full test suite)
- [ ] Code is refactored (production + tests)

## Communication Protocol

**After completing each task:**
1. **FIRST**: Use TaskUpdate to mark the task as completed
2. **THEN**: Send completion message to "team-lead"

**For unit-testable code (Test-First approach):** After EACH RED-GREEN-REFACTOR cycle completes, send a message to "team-lead".

**For unit-testable code (Test-After approach):** After IMPLEMENT-TEST-REFACTOR completes, send a message to "team-lead".

**For non-unit-testable code:** After each logical unit (complete feature, script, or tightly coupled set of features), send a message to "team-lead".

**Message format (Test-First):**
```
Test complete: <test-name>
- RED: <what failed and why>
- GREEN: <minimal implementation added>
- REFACTOR: <improvements made>
- Tests passing: X/Y total (X = tests in this module, Y = all project tests)

Ready for next test or review.
```

**Message format (Test-After):**
```
Task complete: <feature-name>

Implementation:
- <what was implemented>

Tests added:
- <test 1: scenario>
- <test 2: scenario>
- <test 3: edge case>

Tests passing: X/Y total
Refactoring: <improvements made>

Ready for review.
```

**Test count reporting:**
- Always include "Tests passing: X/Y total" after each cycle
- X = tests for the module you're working on
- Y = total tests across all modules (if running full test suite)
- Example: "Tests passing: 16/246 total" means 16 tests in your module, 246 across entire project
- Helps navigator track progress and catch test regressions

Then WAIT for navigator response before continuing.

## Decision Making - CRITICAL

NEVER make architectural decisions alone:
- If multiple valid approaches exist → STOP and present options to navigator
- If requirements are ambiguous → ASK for clarification before implementing
- If you're unsure about design → DISCUSS with navigator

**Default to smallest possible scope:**
- Implement pure logic first, add framework integration later
- Defer features that aren't immediately needed (YAGNI principle)
- When in doubt, do less rather than more

Present options like:
"Design decision needed:
Option A: [approach 1 with pros/cons]
Option B: [approach 2 with pros/cons]
Which should I use?"

## Mid-Implementation Scope Changes

If you discover architectural inconsistencies during implementation:
- **STOP** and present the issue to navigator
- Propose scope expansion if related code needs fixing
- Get approval before expanding beyond original task

Example:
"Architectural inconsistency discovered:
- Current task: Implement PartitionMetadataReader using DataStorage
- Issue: CollectionMetadataReader uses S3Client directly (inconsistent)
- Proposal: Refactor both readers together for consistency
- Benefit: Prevents technical debt, ensures uniform abstraction
Should I expand scope to include CollectionMetadataReader?"

**When scope expansion is appropriate:**
- Prevents technical debt accumulation
- Maintains architectural consistency
- Related code is tightly coupled
- Fix now is easier than fix later

**Get navigator approval first** - expanding scope impacts:
- PR size and review complexity
- Testing requirements
- Documentation updates
- Commit scope and clarity

## Your Task

<Paste acceptance criteria here>

Start by writing the first failing test (or first feature for non-unit-testable code).
```

### Step 4: Navigator Workflow (Your Role)

**Pre-Brief the User (Recommended)**

Before the driver starts working, briefly explain the idle notification pattern to avoid confusion:

```
"Starting XP pairing session. You'll see automatic idle notifications between 
driver tool calls - these are normal, please ignore them. Only respond when 
the driver sends a message asking a question or reporting completion."
```

This prevents user confusion and unnecessary interruptions during active work.

**⚠️ IMPORTANT: Understanding Idle Notifications**

Driver will go idle frequently between tool calls and after sending messages. **This is completely normal and expected behavior.**

**When to respond to idle notifications:**
- ✅ Driver sent a message and is waiting for your approval/direction
- ✅ Driver asked a question in previous message
- ✅ Driver completed a milestone and is awaiting next instruction
- ✅ You have feedback or guidance to provide

**When to ignore idle notifications:**
- ⏸️ Driver just started working (give them time to complete the cycle)
- ⏸️ Driver is between tool calls (automatic idle between operations)
- ⏸️ You already responded and driver is processing your message
- ⏸️ You're confident driver knows what to do next

**How to respond:**
- Use `SendMessage` tool with `to: "driver"` parameter
- Keep messages concise and actionable
- Example: "Good refactoring. Continue to next test."

**Handling Scope Changes (Navigator-Initiated)**

If you want to expand scope (e.g., user suggests new validation):

1. **Don't assume** - ask user explicitly:
   ```
   "User identified that CSV column 1 (dbId) could be validated.
   
   Should we:
   A) Add dbId validation (1 more test, data integrity improvement)
   B) Skip it (keep scope minimal, match legacy exactly)
   
   What's your preference?"
   ```

2. **After user approves** - instruct driver with clear scope addition:
   ```
   "Navigator decision: IMPLEMENT dbId validation (Option 1)
   
   Add validation after JSON format check: [specific code/approach]
   Add test: shouldSkipLineWithMismatchedDbId
   
   Follow RED-GREEN-REFACTOR. Report when complete."
   ```

3. **Why this matters**: Scope changes affect PR size, testing effort, and commit clarity. Get explicit user buy-in before expanding driver's work.

### Step 5: Final Review

When driver completes all tests, run a parallel review workflow before the commit decision. This catches issues across multiple dimensions simultaneously without loading all the review work into this session's context.

Use the Workflow tool to spawn these review agents in parallel, each receiving the diff and relevant source files:

- **Architecture compliance agent**: Are abstractions, patterns, and dependencies consistent with the codebase? Any SOLID violations?
- **Test coverage agent**: Are there gaps in happy path, edge case, or error path coverage? Any untested production paths?
- **Documentation drift agent**: Do README files, Javadoc, and inline docs still accurately describe the implementation?
- **Code quality agent**: Naming clarity, method length, SRP, anything that should be refactored before commit?

Merge findings, address any issues with the driver, then proceed to pre-commit validation.

**After workflow review:**
1. Request additional refactoring if needed
2. **Run pre-commit validation (Step 5.5a below) - MANDATORY**
3. **Review documentation (Step 5.5b below) - MANDATORY**
4. Approve and commit work
5. Shut down driver with thanks

### Step 5.5a: Pre-Commit Build Validation (CRITICAL)

**BEFORE committing to git**, ALWAYS run full build validation:

**General Workflow:**
1. Driver reports: "All tests complete"
2. Navigator runs full build with all checks enabled (see project-specific CLAUDE.md for commands)
3. Review compilation errors, test failures, and warnings
4. Request fixes if critical issues found
5. Driver fixes issues → Re-run build
6. Clean build → Approve commit
7. Commit with appropriate message
8. Shut down driver

**What to Check:**
- 🔴 **Compilation errors** - must be zero
- 🔴 **Test failures** - must be zero
- 🟡 **Static analysis warnings** - review and fix critical ones
- 🟢 **Documentation/style warnings** - fix if time permits

**Why This Matters:**
- Prevents committing code with known bugs
- Ensures build environment changes are validated
- Catches issues before CI/CD pipeline
- Maintains code quality standards
- Avoids broken builds in git history

**Note**: See project-specific CLAUDE.md for build commands, warning categories, and critical issue definitions for your tech stack (Maven/Gradle, npm/yarn, etc.).

### Step 5.5b: Documentation Review (CRITICAL)

**BEFORE committing to git**, ALWAYS review and update relevant documentation:

```bash
# Check which documentation might be affected:
# - README files (project, module, or feature-specific)
# - Architecture docs (if design patterns changed)
# - API docs (if public interfaces changed)
# - CLAUDE.md (if lessons learned or patterns emerged)
```

**Documentation Checklist:**
- [ ] Update README with new classes/services/features
- [ ] Update class count if tracking (e.g., "23 total" → "25 total")
- [ ] Document public APIs and their usage patterns
- [ ] Update architecture docs if design changed
- [ ] Document breaking changes or migration steps
- [ ] Keep CLAUDE.md current with lessons learned

**Examples of what to document:**

For new service classes:
```markdown
### I/O Service Classes (2)

**`CollectionMetadataReader`**
- Reads collection metadata CSV files from storage
- Uses DataStorage abstraction for CDS bucket access
- Memory-efficient streaming with BufferedReader
```

For architectural changes:
```markdown
## Architecture Changes

- Refactored to use `DataStorage` abstraction instead of `S3Client`
- Enables future Guarded Consumer migration
- Bucket is now encapsulated in DataStorage implementation
```

**Workflow:**
1. Driver reports: "All tests complete"
2. Navigator runs build validation (Step 5.5a)
3. Navigator reviews documentation needs
4. Driver or Navigator updates documentation
5. Commit both code and documentation together

**Why This Matters:**
- Keeps documentation synchronized with code
- Helps future developers understand design decisions
- Documents lessons learned while context is fresh
- Prevents documentation debt accumulation
- Makes code reviews easier with clear context

## Example Session

**Navigator (you):**
```
Let's implement a cleanup job using XP pairing.

<Creates team>
<Creates tasks with acceptance criteria>
<Spawns driver with instructions>
```

**Driver reports:**
```
Test complete: shouldRejectNullBucket
- RED: Test failed with NullPointerException as expected
- GREEN: Added Objects.requireNonNull(bucket, "bucket cannot be null")
- REFACTOR: Extracted validateBucket() helper method for clarity
- Tests passing: 1/18

Ready for next test or review.
```

**Navigator (you):**
```
Good refactoring. Continue to next test.
```

**Driver asks:**
```
Design decision needed:
Option A: Multi-prefix in config (comma-separated string)
  Pros: Simple CLI, single argument
  Cons: String parsing, config does too much
Option B: Multi-prefix in main class (iterate with config.withPrefix())
  Pros: Config stays simple, SRP maintained
  Cons: More code in main class
Which should I use?
```

**Navigator (you):**
```
Use Option B. Config should handle single prefix only (SRP).
Main class orchestrates multiple prefixes.
```

## Shutdown

When work is complete:

```
SendMessage(
  type="shutdown_request",
  recipient="driver",
  content="Task complete. Great work on TDD and clean code. Thanks!"
)
```

Then:
```
TeamDelete  # Cleans up team resources
```

---

## Incremental PR Strategy (Multi-Task Projects)

For projects with multiple related tasks, consider breaking work into small, reviewable PRs:

### Strategy Options

**Option A: Task-by-Task PRs** (Recommended for team review capacity):
1. Complete Task #1 → Commit → Push → Create PR 1
2. Pause pairing, shut down driver, clean up team
3. Wait for PR 1 review/merge to master
4. Start fresh pairing session for Task #2 → PR 2
5. Repeat for remaining tasks

**Benefits**:
- Small PRs (~200-300 LOC each) = faster reviews
- Reduced merge conflicts (master advances incrementally)
- Fresh context each session (no context bloat)
- Easy rollback if issues found
- Team can review in parallel with your next task

**Option B: Complete All Tasks, Split PRs Later**:
1. Complete all tasks in one pairing session
2. Commit each task separately
3. Create multiple PRs from same branch (stacked PRs)
4. PRs reviewed/merged sequentially

**Benefits**:
- Continuous development flow (no waiting between tasks)
- Driver maintains full context across tasks
- Better for tightly coupled tasks

### Workflow Pattern (Option A)

**Session 1: Task #1**
```
1. TeamCreate → TaskCreate (#1-#5) → Spawn driver
2. Driver completes Task #1
3. Pre-commit validation → Commit → Push → Create PR 1
4. Shutdown driver → TeamDelete
5. Wait for PR 1 merge
```

**Session 2: Task #2** (after PR 1 merged)
```
1. Pull latest master
2. TeamCreate → TaskCreate (#2-#5) → Spawn driver
3. Driver completes Task #2
4. Pre-commit validation → Commit → Push → Create PR 2
5. Shutdown driver → TeamDelete
6. Wait for PR 2 merge
```

**Repeat for Tasks #3-#5**

### Task List Continuity

Tasks carry forward across sessions:
- Task list stored in `~/.claude/tasks/{team-name}/`
- Create all tasks upfront in Session 1 (Task #1-#5)
- Later sessions reference same task IDs
- Mark tasks completed as you go
- Task list provides progress tracking across PRs

### Choosing the Right Strategy

**Use Option A (Task-by-Task) when**:
- Team has limited review capacity (small PRs easier)
- Tasks are loosely coupled (can be reviewed independently)
- Project timeline allows waiting between PRs
- Quality/review thoroughness is priority

**Use Option B (Complete-Then-Split) when**:
- Tasks are tightly coupled (hard to review separately)
- You need continuous context across tasks
- Time-sensitive delivery (can't wait for reviews)
- Team can review stacked PRs

---

## Future Improvements

Track ideas for improving this skill:

### Version 1.1 (Candidate Improvements)
- [x] **Architecture planning step**: Discuss design before implementation (added Step 2)
- [x] **TDD adaptation for non-unit-testable code**: Clarify validation methods when unit test frameworks aren't available
- [x] **Task list hygiene**: Document how to avoid duplicate tasks
- [x] **Incremental PR workflow**: Document strategies for breaking work into small PRs
- [x] **Documentation review step**: Update docs before commit (added Step 5.5b)
- [x] **Architecture validation**: Check for compliance in final review (updated Step 5)
- [x] **Mid-implementation scope changes**: Guidance for expanding scope when architectural issues found
- [x] **Idle notification clarity**: When navigator should/shouldn't respond (updated Step 4)
- [x] **Test count reporting**: Format for progress tracking (updated Communication Protocol)
- [ ] **Ping-pong mode**: Navigator writes test skeleton, driver implements
- [ ] **Acceptance criteria template**: Standard checklist format
- [ ] **Metrics tracking**: Count tests, refactorings, decisions asked
- [ ] **Adjustable cadence**: Config for per-test vs per-batch reporting

### Version 1.2 (Future Ideas)
- [ ] **Strong-style pairing**: Navigator narrates, driver types exactly what's said
- [ ] **Mob programming**: Multiple drivers, one navigator
- [ ] **TDD kata mode**: Practice TDD on well-known problems
- [ ] **Refactoring-only mode**: Driver refactors existing code with navigator guidance

### Learnings from Sessions
*(Add notes here after each pairing session)*

**2026-02-24 - Cleanup Job Implementation:**
- ✅ Per-test reporting worked well (moderate token usage)
- ✅ Driver produced excellent code quality
- ✅ Design discussions were valuable but came late
- 📝 Next time: Discuss architecture before Task 1
- 📝 Consider: Navigator write test skeletons first
- 📝 Issue: Too many idle notifications while waiting for response

**2026-03-04 - EMR Job Control Scripts (Bash/Infrastructure):**
- ✅ Driver produced production-ready code on first submission
- ✅ Per-script reporting worked well for bash (not per-line/per-feature)
- ✅ Driver correctly identified already-complete task (Task 3) - saved time
- ✅ Pre-flight checks and edge case handling were excellent
- 📝 **Fixed**: Added architecture planning step (Step 2) to prevent post-facto decisions
- 📝 **Fixed**: Clarified TDD adaptation for bash/infrastructure (no unit tests)
- 📝 **Fixed**: Documented task list hygiene to avoid duplicates (#1/#5, #2/#6, #3/#7)
- 📝 Observation: Pairing was more "driver implements, navigator approves" than collaborative. Consider stronger-style pairing for learning scenarios.
- 📝 Validation methods for bash: syntax check (bash -n), static analysis (shellcheck), manual execution, error case testing

**2026-03-18 - Bulk Export Tests (Java/Maven):**
- ✅ Driver wrote 195 comprehensive tests (18 test classes)
- ✅ All tests passed when driver ran them
- ❌ **Issue**: Compilation errors discovered after commit due to POM duplicate dependencies
- ❌ **Issue**: Critical Error Prone warnings not caught before commit (overflow bug, charset issues)
- 📝 **Fixed**: Added Step 5.5 - Pre-Commit Build Validation (MANDATORY)
- 📝 Root cause: Maven duplicate dependencies (provided + test scope) - last declaration wins
- 📝 Solution: Use only provided-scope Spark dependencies (sufficient for tests)
- 📝 Lesson: ALWAYS run `mvn clean compile test` before commit, not just `mvn test`
- 📝 Lesson: Review Error Prone warnings - IntLongMath and DefaultCharset are real bugs
- 📝 Workflow change: Navigator runs full build validation BEFORE approving commit

**2026-03-23 - BulkExportConfig (Incremental PR Strategy):**
- ✅ Task #1 complete: BulkExportConfig with 21 tests (220/220 total passing)
- ✅ Clean build validation before commit (zero critical warnings)
- ✅ **New workflow**: Complete Task #1 only → PR 1 → Wait for merge → Continue with Task #2
- ✅ Driver performed excellently: comprehensive tests, clean refactoring, good TDD discipline

**2026-04-15 - Template CSV Fix (Test-First vs Test-After Discovery):**
- ✅ First round: Test-first approach worked well (CSV parsing with 7 tests)
- ❌ Second round: Test-first overhead wasted tokens (constant extraction, javadoc, simple validation)
- 📝 **Issue**: Strict TDD doesn't inform AI design - design is predetermined
- 📝 **Issue**: Without strict TDD instructions, tests often get skipped
- 📝 **Root cause**: TDD value for humans (design discovery) ≠ TDD value for AI (verification + documentation)
- 📝 **Solution**: Test-Complete Development framework
  - Test-first when design needs thinking through (complex algorithms, unclear requirements)
  - Test-after when design is obvious (simple CRUD, straightforward validation)
  - MANDATORY: Every production code change MUST have tests (non-negotiable checkpoint)
- 📝 **Fixed**: Updated CLAUDE.md with Test-Complete Development section
- 📝 **Fixed**: Updated xp-pair skill with Test-First vs Test-After guidance
- 📝 **Added**: Verification checkpoint (production code has tests, tests cover happy/edge/error)
- 📝 **Added**: Navigator should ask user if complexity warrants xp-pair before spawning driver
- 📝 Token savings: ~30% for obvious implementations (test-after vs test-first)
- 📝 Quality maintained: Same test coverage requirements regardless of order
- 📝 **Fixed**: Added "Incremental PR Strategy" section for multi-task projects
- 📝 Benefit: Small PR (~250 LOC) = easy team review vs large PR (~1,500 LOC for all 5 tasks)
- 📝 Pattern: Shutdown driver after each task milestone, fresh session for next task
- 📝 Context management: Task list carries forward, reduces context bloat per session
- 📝 Team preference: Incremental merges reduce merge conflicts and allow parallel work

**2026-03-24 - PartitionMetadataReader (Architecture Validation & Documentation):**
- ✅ Task #3 complete: PartitionMetadataReader with 16 tests (246/246 total passing)
- ✅ Architecture review caught critical issue (S3Client vs DataStorage abstraction)
- ✅ Driver adapted excellently to mid-implementation scope expansion
- ✅ Refactored two readers together (prevented technical debt accumulation)
- ✅ User reminder to keep documentation up-to-date during implementation
- 📝 **Fixed**: Added Step 5.5b - Documentation Review (MANDATORY before commit)
- 📝 **Fixed**: Updated Step 5 to include Architecture Validation checkpoint
- 📝 **Fixed**: Added guidance for mid-implementation scope changes to Driver Instructions
- 📝 **Fixed**: Clarified idle notification response patterns for Navigator
- 📝 **Fixed**: Added test count reporting format to Communication Protocol
- 📝 Lesson: Architecture review in Step 5 is critical - caught DataStorage issue before merge
- 📝 Lesson: Scope expansion is justified when it prevents technical debt
- 📝 Lesson: Documentation updates should happen before commit, not after
- 📝 Pattern: User said "IFF accessing local S3 bucket can use S3Client, else use DataStorage"
- 📝 Insight: Both readers access CDS bucket (cross-account), so both need abstraction

**2026-03-25 - FullExportJob Implementation (Task 4.5 Stage 1-2):**
- ✅ Implemented BulkExportConfig with 3 new parameters (21 tests, 220/220 passing)
- ✅ Implemented FullExportJob main entry point (10 tests, 230/230 passing)
- ✅ Implemented RecordIdReader (13 tests, 243/243 passing)
- ✅ Implemented CdsRecordReader (12 tests, 292/292 passing)
- ✅ All tests passed, documentation updated, clean pre-commit build
- 📝 **Issue**: Idle notifications were excessive when driver was actively working
- 📝 **Issue**: Driver didn't proactively update task status before messaging
- 📝 **Issue**: Data format discovery happened mid-implementation (S3 key pattern)
- 📝 **Issue**: Some scope expansion discussion (pure logic vs Spark integration)
- 📝 **Fixed**: Updated Step 2 to emphasize data format review in architecture planning
- 📝 **Fixed**: Updated Communication Protocol to require TaskUpdate before messaging
- 📝 **Fixed**: Updated Decision Making to emphasize smallest scope (YAGNI)
- 📝 **Fixed**: Updated Step 4 to move idle notification guidance higher
- 📝 **Fixed**: Made Step 5.5a more generic (extracted Java/Maven specifics to project CLAUDE.md)
- 📝 Lesson: Review S3 paths, API formats, file structures BEFORE driver starts coding
- 📝 Lesson: Incremental PR strategy worked well (~1,200 LOC vs ~3,000+ for all stages)
- 📝 Lesson: Pure logic first, framework integration later (RecordIdReader returns List, not Dataset)
- 📝 Observation: Driver performed excellently with TDD discipline and proactive scope decisions

**2026-04-15 - Template CSV Parsing Fix:**
- ✅ Fixed critical bug blocking all bulk export (JsonParseException on CSV commas)
- ✅ 7 new tests + dbId validation improvement (425/425 tests passing)
- ✅ Clean PR created (3 files, +209/-24 lines, zero critical warnings)
- ✅ Driver followed TDD discipline excellently, good design decision escalation
- ✅ User input (dbId validation) incorporated smoothly as scope addition
- ❌ **Issue**: Started with wrong approach (StringUtils.split) - had to pivot mid-implementation
- ❌ **Issue**: Idle notification confusion - user asked multiple times "should I respond?"
- ❌ **Issue**: Message crossing - sent instructions for work already completed
- 📝 **Fixed**: Enhanced Step 2 with "Verify Assumptions" checkpoint and examples
- 📝 **Lesson**: TEST assumptions before committing to approach (5 min verification saves 30 min rework)
- 📝 **Lesson**: Check BOTH handoff doc AND legacy code DURING Step 2 (not after spawning driver)
- 📝 **Lesson**: Should pre-brief user on idle notifications: "automatic between tool calls, ignore unless driver asks question"
- 📝 **Lesson**: Scope changes should be explicit user questions, not assumptions (get approval first)
- 📝 **Lesson**: Read driver's completion message fully before sending new instructions (avoid redundancy)
- 📝 **Pattern**: User question led to meaningful improvement (dbId validation) - encourage user participation!
- 📝 Observation: High-quality output despite friction. Communication issues are addressable with better process.

**2026-04-15 - PR Review Fixes (Copilot + SonarQube):**
- ✅ Fixed 3 review issues (2 Copilot, 1 SonarQube) using TDD discipline
- ✅ 1 new test added (empty column edge case), 426/426 tests passing
- ✅ Commit amended and force-pushed successfully
- ✅ Design decision made upfront (suppress vs parameterize) - avoided wasted work
- ✅ Complete context provided (file paths, line numbers, exact issues from Copilot/SonarQube APIs)
- ✅ Driver provided excellent feedback on skill improvements
- ❌ **Issue**: Task assignments had stale criteria after design decisions (Task #3 said "parameterize" but navigator chose "suppress")
- ❌ **Issue**: TDD discipline applied to non-TDD task (Task #1: constant name change didn't need RED phase)
- ❌ **Issue**: Message ping-pong - approval and next task sent separately caused noise
- 📝 **Lesson**: Pre-classify tasks as "TDD cycle" vs "direct change" to avoid forcing RED phase on trivial changes
- 📝 **Lesson**: Send approval + next task in single message to reduce communication overhead
- 📝 **Lesson**: Update TaskCreate criteria AFTER design decisions to prevent contradictions
- 📝 **Lesson**: Escalating complexity (logging → bug fix → design decision) was good task ordering
- 📝 **Pattern**: Making design calls BEFORE driver starts prevents wasted implementation cycles
- 📝 Driver feedback: "Pre-classify TDD applicability per task", "Single response for approval + next", "Finalize task criteria after navigator decisions"
- 📝 Observation: Short feedback loop (fix review issues, get driver's perspective) led to immediate actionable improvements

---

## Technical Notes

**Token Usage:**
- Per-test reporting: ~1-2 messages per test = moderate usage
- 18 tests × ~200 tokens/message = ~3,600 tokens for communication
- Acceptable for complex features where quality matters

**Team Structure:**
- Team name: `<feature>-dev`
- Navigator: Main agent (you)
- Driver: Subagent with `general-purpose` type (has all tools including Edit, Write)

**Communication:**
- Driver uses SendMessage to team-lead after each cycle
- Navigator responds via text (automatically delivered to driver)
- Use SendMessage for shutdown requests
