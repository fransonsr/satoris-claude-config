# Example Session: Cleanup Job Implementation

Date: 2026-02-24
Feature: EMR Cleanup Job for S3 export data

## Setup

**User:** "Let's implement the cleanup job using XP pairing"

**Navigator:** Created team `cleanup-job-dev` with 4 tasks:
1. Create module structure
2. Implement CleanupConfig
3. Implement CleanupService
4. Implement CleanupJob main class

Spawned driver with explicit instructions and acceptance criteria.

## Task 2: CleanupConfig Implementation

**Driver (first report):**
```
Test complete: shouldParseBucketArgument
- RED: Test failed - fromArgs() not implemented
- GREEN: Added fromArgs() method with basic argument parsing
- REFACTOR: None needed yet (keeping it simple)
- Tests passing: 1/18

Ready for next test or review.
```

**Navigator:** "Good. Continue with next validation test."

**Driver (second report):**
```
Test complete: shouldRejectNullBucket
- RED: Test passed unexpectedly - need validation
- GREEN: Added validateBucket() check in fromArgs()
- REFACTOR: Extracted validateBucket() as private static helper
- Tests passing: 2/18

Ready for next test or review.
```

**Navigator:** "Excellent refactoring. Keep going."

**Driver (multiple tests later):**
```
Test complete: shouldDefaultKeepCountToTwo
- RED: Test failed - keepCount was 0
- GREEN: Changed default from 0 to 2
- REFACTOR: Extracted DEFAULT_KEEP_COUNT constant
- Tests passing: 7/18

Ready for next test or review.
```

**Navigator:** "All defaults look good. Continue through remaining tests."

## Task 3: CleanupService Implementation

**Driver (asks question):**
```
Test complete: shouldIdentifyExportDirectoriesFromObjectKeys
- Tests passing: 9/26

Design question: Should findExportDirectories() return just directory names,
or should it return a map with directory → file list?

Option A: Return List<String> of directory names (simpler, single responsibility)
Option B: Return Map<String, List<String>> (more info, but doing too much)

Which approach should I use?
```

**Navigator:**
```
Use Option A. Keep findExportDirectories() focused on one thing: finding directories.

The cleanup() method can call listObjects() again if it needs file lists.
It's okay to list twice - keeps SRP clean.
```

**Driver:**
```
Understood. Continuing with Option A.

Test complete: shouldReturnEmptyListWhenNoExportsExist
- RED: Test failed - null pointer
- GREEN: Added empty list check
- REFACTOR: None needed (already clean)
- Tests passing: 10/26

Ready for next test or review.
```

## Task 4: CleanupJob Main Class

**Driver (asks question):**
```
Design decision needed:
How should multi-prefix cleanup work?

Option A: CleanupJob orchestrates multiple prefixes
  - Calls service.cleanup() once per prefix
  - Config stays simple (single prefix only)
  - Pros: SRP maintained, Config is simpler
  - Cons: More orchestration code in main class

Option B: Comma-separated prefixes in config
  - Parse "outputFull_,recordIds_,LogFiles_" in CleanupConfig
  - Config handles splitting and validation
  - Pros: Simple CLI (one argument)
  - Cons: Config does too much, string parsing complexity

Which should I use?
```

**Navigator:**
```
Use Option A.

Reasoning:
- CleanupConfig should model a single cleanup operation (one prefix)
- Main class orchestrates multiple operations (composition)
- Keeps config simple and immutable
- Better SRP: Config = configuration, Job = orchestration
```

**Driver:**
```
Implementing Option A.

Test complete: shouldRunCleanupForAllDefaultPrefixPatterns
- RED: Test failed - only ran for one prefix
- GREEN: Added loop in run() method to iterate prefixes
- REFACTOR: Extracted determinePrefixPatterns() and isCustomPrefixSpecified()
- Tests passing: 32/34

Ready for next test or review.
```

## Final Review

**Driver:** "All 34 tests passing. Ready for review."

**Navigator:**
```
<Reviews all code>

Code quality is excellent:
- Proper TDD discipline throughout
- Good method names (reveal intent)
- Strong SRP (each class/method does one thing)
- Comprehensive test coverage
- Clean refactoring

Approved! Let me do one refactoring pass to remove the duplicate constant.
```

**Navigator refactoring:**
```
Removed DEFAULT_PREFIX_PATTERN constant (duplicated knowledge)
Changed isCustomPrefixSpecified() to check against list instead

All 34 tests still passing.
```

**Navigator:** "Great work! Shutting down driver."

## Outcome

- **Lines of code:** ~400 production, ~600 test
- **Tests:** 34 passing (18 config, 10 service, 6 job)
- **Time:** ~45 minutes of pairing
- **Quality:** Production-ready, clean, well-tested
- **Token usage:** ~4,000 tokens for driver communication

## What Worked Well

✅ Clear acceptance criteria upfront
✅ Per-test reporting (good balance of feedback vs overhead)
✅ Driver asked for architectural decisions (Options A vs B)
✅ Clean refactoring after GREEN
✅ Navigator caught duplicate constant in final review

## What Could Improve

📝 Architecture discussion came during Task 4 (should have been upfront)
📝 Too many idle notifications while navigator reviewing
📝 Could try navigator writing test skeletons first (ping-pong)

## Learnings Added to Skill

Updated `~/.claude/skills/xp-pair/SKILL.md` with:
- Note about discussing architecture before Task 1
- Validate: Per-test reporting works well
- Future: Consider ping-pong mode (navigator writes tests)
- Future: Suppress idle notifications when waiting for response
