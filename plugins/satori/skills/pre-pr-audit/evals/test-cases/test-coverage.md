# Eval: production class with no test file

Exercises `_check_test_coverage` (both branches).

## Setup
1. A new file under `src/main/java/.../RecordProcessor.java` with no corresponding
   `src/test/java/.../RecordProcessorTest.java`.
2. A modified `src/main/java/.../Existing.java` whose `ExistingTest.java` exists but is NOT in the
   changed-files list.

## Pass Criteria
- [ ] Case 1 produces a MEDIUM finding naming the expected test path.
- [ ] Case 2 produces a LOW finding noting the test was not updated alongside the class.
- [ ] Adding the test file to the changed-files list clears case 2.
