# Coding Standards and Principles

**Owner**: fransonsr
**Last Updated**: 2026-02-11
**Scope**: All projects in this environment

## Environment Configuration

**Operating System**: WSL (Windows Subsystem for Linux)

**Path Mappings**:
- WSL home from Windows: `\\wsl.localhost\Ubuntu\home\fransonsr`
- Use this path format to open files in Windows browser or applications
- Example: `file:///\\wsl.localhost\Ubuntu\home\fransonsr\file.md`

**Installed Tools**:
- `wslu` - WSL utilities package installed (v3.2.3)
  - Use `wslview <file>` to open files in Windows default applications
  - Works like `xdg-open` but WSL-aware (opens PDFs, URLs, etc. in Windows)
  - **Note**: Original `wslview` uses old WSL1 paths (`\\wsl$`) which don't work in WSL2
  - **Fix**: Created `~/bin/wslview2` wrapper that uses correct WSL2 paths (`\\wsl.localhost`)
  - Aliased `wslview` → `wslview2` in `~/.bashrc` so it "just works"

**Task Handoff System**:
- Handoff documents location: `~/.claude/handoff/`
- When starting work on a task, check for handoff documents first
- Naming convention: `<task-id>-<slug>.md` (e.g., `task-4.16.2-collection-indices-writer.md`)
- Use `/handoff` skill to create handoff documents for complex tasks
- Handoff documents contain: executive summary, technical specs, implementation plan, acceptance criteria, testing strategy, reference materials

## Core Principles

### 1. Testing Pyramid & Testability

**Testing Pyramid Philosophy:**
- **Unit tests (microtests)** should form the bulk of test coverage
- **Integration tests** validate what cannot be tested in isolation
- **End-to-end tests** validate full system behavior
- Test at the lowest possible level for speed and precision

**Testability as Justification for Refactoring:**
- Making code testable is sufficient justification for refactoring
- If code cannot be unit-tested due to architectural constraints, refactor it
- Extract embedded logic (anonymous classes, lambdas) into testable components
- Favor composition and dependency injection over tightly coupled designs

**Example**: Anonymous iterators in Spark `mapPartitions` cannot be unit-tested. Extract them into package-private classes with clear contracts, enabling comprehensive unit tests without Spark infrastructure.

### 2. Test-Complete Development

**Non-Negotiable Rule: Every production code change MUST have corresponding tests**

**Order depends on complexity:**

**Test-First (When design needs thinking through):**
- Complex algorithms or business logic
- Unclear requirements or edge cases
- Behavior changes to critical code paths
- When you need to think through the problem

**Test-After (When design is obvious):**
- Simple CRUD operations
- Obvious bug fixes with known solutions
- Refactoring with clear target state
- Straightforward validation logic
- Constants, getters, trivial utilities

**Required: RED-GREEN-REFACTOR (when test-first):**
- RED: Write failing test, verify it fails for the right reason
- GREEN: Minimal code to pass
- REFACTOR: **NEVER skip** - extract methods, apply SOLID, improve naming

**Required: IMPLEMENT-TEST-REFACTOR (when test-after):**
- IMPLEMENT: Write production code
- TEST: Write comprehensive tests covering happy path + edge cases
- REFACTOR: **NEVER skip** - improve both production and test code

**Mandatory Test Coverage:**
- Happy path (expected inputs/outputs)
- Edge cases (boundary conditions, empty/null inputs)
- Error paths (invalid inputs, exceptions)
- Regression coverage for bugs
- Data integrity checks

**Verification Checkpoint (ALWAYS):**
Before marking work complete, verify:
- [ ] All production code changes have tests
- [ ] Tests cover happy path + edge cases + errors
- [ ] Tests are clear and maintainable ("moist" principle)
- [ ] All tests pass (old + new)
- [ ] Code is refactored (production + tests)

**Test Quality:**
- Tests should be clear, readable, and maintainable
- Each test should test one thing
- Test names describe behavior, not implementation
- Use Given-When-Then or Arrange-Act-Assert patterns

**Relentless Refactoring:**
- Refactor immediately after GREEN/TEST phase, not "later"
- Multiple refactoring passes are normal and encouraged
- Ask: "Can this be clearer? Simpler? More maintainable?"
- Extract methods to give names to concepts
- Each method should do ONE thing at ONE level of abstraction
- If a method needs a comment to explain what it does, extract it into a well-named method instead
- Code should read like well-written prose

### 3. DRY vs "Moist" Principles

**Production Code: DRY (Don't Repeat Yourself)**
- Eliminate duplication ruthlessly
- Extract common logic into reusable functions/classes
- Use abstraction appropriately
- Shared constants, utilities, and helpers

**Test Code: "Moist" (Mostly Optimized for Immediate Simplicity in Tests)**
- **Clarity > Conciseness** in tests
- Duplication is acceptable if it improves readability
- Inline setup in tests if it makes intent clearer
- Each test should be independently understandable
- Avoid excessive abstraction that obscures test intent

**Examples of "Moist" Tests:**

```java
// ✅ GOOD: Clear intent, even with some duplication
@Test
void shouldRejectNegativeFutureBatchSize() {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, -1));
}

@Test
void shouldRejectZeroFutureBatchSize() {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, 0));
}

// ❌ AVOID: DRY in tests obscures what's being tested
@ParameterizedTest
@ValueSource(ints = {-1, 0})
void shouldRejectInvalidBatchSize(int batchSize) {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, batchSize));
}
// ^ Harder to see which specific values are invalid
```

### 4. SOLID Principles

**S - Single Responsibility Principle**
- Each class should have one reason to change
- One class, one job
- Example: `FutureTracker` tracks futures; `SlsBIProducer` produces messages

**O - Open/Closed Principle**
- Open for extension, closed for modification
- Use configuration objects, strategy patterns
- Example: `SlsBIClientConfig` allows extension without changing constructor

**L - Liskov Substitution Principle**
- Subtypes must be substitutable for base types
- Interface contracts must be honored
- Deprecated methods should maintain behavior

**I - Interface Segregation Principle**
- Clients shouldn't depend on interfaces they don't use
- Small, focused interfaces
- Example: Separate `SlsBIClient` from `SlsBIProducer`

**D - Dependency Inversion Principle**
- Depend on abstractions, not concretions
- High-level modules shouldn't depend on low-level modules
- Example: `client` module doesn't depend on `client-starter`

## TDD Workflow Examples

### Example 1: New Feature

```bash
# 1. Write failing test
@Test
void shouldTrackFutureAndFlushWhenBatchSizeReached() {
    // RED: This test will fail because feature doesn't exist
    FutureTracker tracker = new FutureTracker(2, logger);
    tracker.track(future1, "ctx1");
    tracker.track(future2, "ctx2");
    // Should auto-flush here...
    assertEquals(0, tracker.getPendingCount());
}

# 2. Run test - it fails ✓
# 3. Implement minimal code to make it pass
# 4. Run test - it passes ✓
# 5. Refactor if needed
# 6. Run test - still passes ✓
```

### Example 2: Bug Fix

```bash
# 1. Write test that reproduces the bug
@Test
void shouldHandleNullFutureGracefully() {
    // RED: This test fails (NPE or similar)
    FutureTracker tracker = new FutureTracker(10, logger);
    assertDoesNotThrow(() -> tracker.track(null, "context"));
}

# 2. Fix the bug
# 3. Test passes
# 4. Verify old tests still pass (regression check)
```

### Example 3: Pre-Commit Validation (MANDATORY - ALWAYS)

```bash
# After all tests pass, BEFORE committing to git
mvn clean compile test -pl <module>

# Review output for:
# 1. Compilation: BUILD SUCCESS ✓
# 2. Tests: X/X passing ✓
# 3. Warnings: Review and fix CRITICAL ones

# 🔴 CRITICAL warnings (MUST fix before commit):
# - IntLongMath (integer overflow bugs)
# - DefaultCharset (platform-dependent behavior - always use UTF-8)
# - UnusedVariable (dead code)
# - MissingOverride (contract violations)

# 🟡 MODERATE warnings (SHOULD fix):
# - ClassCanBeStatic (performance/memory)
# - Unused imports/parameters

# 🟢 LOW priority (can defer):
# - MissingSummary (Javadoc style)
# - UnnecessaryParentheses (code style)

# ⚪ IGNORE (third-party):
# - Spark/LZ4/dependency warnings

# Fix critical warnings → Re-run build → Clean build → Commit
```

## Code Review Checklist

**When reviewing code (or when I should flag issues):**

- [ ] Are there tests for new functionality?
- [ ] Do tests follow "moist" principle (clear over clever)?
- [ ] Is production code DRY?
- [ ] Does design follow SOLID principles?
- [ ] Is module dependency direction correct?
- [ ] Are abstractions at the right level?
- [ ] Are error cases tested?
- [ ] Is the code self-documenting?

## Anti-Patterns to Avoid

### Test Smells
- ❌ Tests that test implementation details, not behavior
- ❌ Tests that depend on execution order
- ❌ Tests that share mutable state
- ❌ Tests with mysterious setup in @BeforeEach that obscures intent
- ❌ Tests that require deep knowledge of mocks to understand

### Production Code Smells
- ❌ God classes (violates SRP)
- ❌ Primitive obsession (use value objects)
- ❌ Feature envy (method uses another class's data more than its own)
- ❌ Data clumps (group related primitives into objects)
- ❌ Long parameter lists (use configuration objects)

## Refactoring Checklist

**After achieving GREEN/TEST phase, always refactor using this checklist:**

### Code Structure
- [ ] Is each method doing ONE thing at ONE level of abstraction?
- [ ] Are methods short (<20 lines ideally, <50 lines maximum)?
- [ ] Can any complex logic be extracted into well-named helper methods?
- [ ] Are there any magic numbers/strings that should be constants?
- [ ] Is there duplicated code that can be extracted?

### Naming
- [ ] Do names reveal intent without needing comments?
- [ ] Are variables/methods/classes named for what they are, not how they work?
- [ ] Can you remove comments by improving names?
- [ ] Are abbreviations avoided unless universally understood?

### SOLID Principles
- [ ] Single Responsibility: Does each class/method have one reason to change?
- [ ] Open/Closed: Can behavior be extended without modification?
- [ ] Liskov Substitution: Do subtypes honor their contracts?
- [ ] Interface Segregation: Are interfaces minimal and focused?
- [ ] Dependency Inversion: Do high-level modules depend on abstractions?

### Dependencies & Coupling
- [ ] Are dependencies explicit (constructor injection preferred)?
- [ ] Is coupling loose (depend on interfaces, not implementations)?
- [ ] Can any concrete dependencies be replaced with abstractions?

### Documentation
- [ ] Is non-obvious code documented with WHY, not WHAT?
- [ ] Are public APIs documented with Javadoc?
- [ ] Can any documentation be replaced with better code?

### Test Impact
- [ ] Do tests still pass? (run after each refactoring step)
- [ ] Are tests still readable and maintainable?
- [ ] Do test names still describe behavior accurately?

**Remember**: Refactoring should happen in small steps with tests passing after each step. Commit frequently during refactoring to create safe restore points.

## When to Break the Rules

**Pragmatism over Purism:**

1. **Legacy Code**: When working with untested legacy code, focus on characterization tests first
2. **Performance**: In rare cases, DRY in production might be sacrificed for performance (document why!)
3. **Prototyping**: Quick spikes can skip TDD, but rewrite with tests before committing
4. **Generated Code**: Don't test generated code (but test the generator)

## Tools and Practices

**Testing Tools (Java/Spring):**
- JUnit 5 for test framework
- Mockito for mocking (use sparingly - prefer real objects when possible)
  - **Argument Matcher Best Practice**: Prefer concrete values over matchers in `verify()` and `when()` calls
  - Only use argument matchers (`eq()`, `any()`, `anyString()`, etc.) when necessary
  - If ANY parameter needs a matcher, ALL parameters must use matchers (Mockito requirement)
  - Example:
    ```java
    // ✅ GOOD: Use concrete values when possible
    verify(mockService).processRecord("record-123", ElementType.RECORD);

    // ✅ ACCEPTABLE: All parameters use matchers when one requires it
    verify(mockService).processRecord(anyString(), eq(ElementType.RECORD));

    // ❌ AVOID: Unnecessary use of matchers
    verify(mockService).processRecord(eq("record-123"), eq(ElementType.RECORD));
    ```
- AssertJ for fluent assertions
- TestContainers for integration tests
- ArchUnit for architecture tests (verify SOLID principles)

**Best Practices:**
- Test package structure mirrors source package structure
- Test class names: `<ClassName>Test` or `<ClassName>Should`
- Test method names: `should<ExpectedBehavior>When<Condition>()` or `<methodName>_<scenario>_<expectedResult>()`
- Use descriptive variable names in tests
- Prefer composition over inheritance in production code
- Prefer immutability (final fields, record classes)

**Test Organization - IMPORTANT:**
- **ALWAYS add tests to existing test classes BEFORE creating new ones**
  - If testing `FooClass`, add tests to existing `FooClassTest`
  - Only create new test classes for NEW production classes
  - Avoid proliferation of test classes (e.g., `FooClassConstructorTest`, `FooClassMethodTest`)
  - Keep related tests together - easier to find and maintain
- **Example**:
  ```
  ✅ GOOD: Add constructor tests to existing SlsBIClientImplTest
  ❌ AVOID: Create separate SlsBIClientImplConstructorTest
  ```

## Examples from sls-bi-worker

### Good Test-First Example: FutureTracker

```java
// Complex batch tracking logic - used test-first approach

// Step 1: RED - Write failing test
@Test
void testAutoFlush_WhenBatchSizeReached() {
    FutureTracker tracker = new FutureTracker(10, LOGGER);

    // Track exactly 10 futures (batch size)
    for (int i = 0; i < 10; i++) {
        KinesisResult result = new KinesisResult(true, "shard-001", "seq-" + i, 1);
        tracker.track(Futures.immediateFuture(result), "record-" + i);
    }

    assertEquals(10, tracker.getPendingCount());

    // Step 2: GREEN - flushIfFull should trigger flush
    tracker.flushIfFull();
    assertEquals(0, tracker.getPendingCount());
}

// Step 3: REFACTOR - Extract constants, improve naming if needed
```

### Good Test-After Example: CSV Validation

```java
// Straightforward validation - used test-after approach

// Step 1: IMPLEMENT - Add comma counting validation
int commaCount = 0;
for (int i = 0; i < jsonStart; i++) {
    if (line.charAt(i) == ',') {
        commaCount++;
    }
}
if (commaCount < 3) {
    logMalformedLine("Template line has insufficient columns...");
    return null;
}

// Step 2: TEST - Comprehensive test coverage
@Test
void shouldSkipLineWithInsufficientColumns() {
    String csvLine = "1369,{\"id\":\"test\"}"; // Only 2 columns
    Map<String, String[]> result = reader.readTemplates(prefix);
    assertThat(result.get("1369")).isEmpty();
}

// Step 3: REFACTOR - (minimal needed - already clear)
```

### Good SOLID Example: SlsBIClientConfig

```java
// Single Responsibility: Only holds configuration
// Open/Closed: Can add fields without changing constructor
// Liskov Substitution: N/A (no inheritance)
// Interface Segregation: Minimal interface
// Dependency Inversion: No dependencies on concrete classes

public class SlsBIClientConfig {
    private final boolean includeMetricsInHeaders;
    private final int futureBatchSize;

    public SlsBIClientConfig(boolean includeMetricsInHeaders, int futureBatchSize) {
        if (futureBatchSize <= 0) {
            throw new IllegalArgumentException("futureBatchSize must be positive");
        }
        this.includeMetricsInHeaders = includeMetricsInHeaders;
        this.futureBatchSize = futureBatchSize;
    }

    // ... getters only, immutable
}
```

## Notes to Claude Code

When working on fransonsr's projects:

1. **Every production code change MUST have tests**
   - Choose test-first OR test-after based on complexity
   - Before marking work complete, verify all production code has tests
   - Tests must cover happy path + edge cases + errors

2. **Practice relentless refactoring**
   - Refactor after GREEN/TEST phase, never skip
   - Extract methods when logic is >10-15 lines
   - Apply Single Responsibility Principle aggressively
   - Multiple refactoring passes are normal and encouraged

3. **For complex/unclear problems:**
   - Use test-first approach (RED-GREEN-REFACTOR)
   - Tests help think through requirements and design

4. **For obvious implementations:**
   - Test-after is acceptable (IMPLEMENT-TEST-REFACTOR)
   - Still requires comprehensive test coverage
   - Refactoring still mandatory

5. **Flag violations of SOLID principles** with explanations
   - SRP violations: method/class doing multiple things
   - Long methods (>20 lines) that need extraction
   - Poor naming that obscures intent

6. **Don't over-abstract tests** - clarity is key

7. **Question constructor parameter lists** - suggest config objects

8. **Ensure module dependencies flow in the right direction**

9. **Prefer immutability and value objects**

10. **Write self-documenting code** - comments explain "why", not "what"
    - Suggest extracting methods to replace comments
    - Improve names to eliminate need for documentation

11. **Always validate build before commit**
   - Run `mvn clean compile test` before any commit (not just `mvn test`)
   - Flag critical Error Prone warnings (IntLongMath, DefaultCharset, UnusedVariable, MissingOverride)
   - Don't commit code with compilation errors or test failures
   - Build environment changes (POM, dependencies) require full validation
   - Prevents broken builds and catches bugs before CI/CD
## References

- **TDD**: Kent Beck's "Test Driven Development: By Example"
- **SOLID**: Robert C. Martin's "Clean Code" and "Clean Architecture"
- **DRY**: Andy Hunt & Dave Thomas's "The Pragmatic Programmer"
- **Test Quality**: "Growing Object-Oriented Software, Guided by Tests" by Freeman & Pryce

---

**Remember**: These are guidelines, not absolute laws. Use judgment. The goal is maintainable, correct, well-tested code that communicates intent clearly.
