# pre-pr-audit Evals

Risk tier: 🟢 Low (read-only analysis; the skill proposes fixes but applies none without
approval). Required before merge: every case below PASS or explicitly waived.

Each case exercises one of `scripts/pattern_checker.py`'s check methods end to end — a planted
defect goes in, and the expected finding must come out. **Every case is executable**: run
`python3 -m pytest test_eval_cases.py` from this directory. The markdown in `test-cases/` remains
the human-readable spec; `test_eval_cases.py` is its executable form, one test per Pass Criteria
checkbox. See [Running the suite](#running-the-suite).

## Results

| Test case | Last Tested | Result | Executable tests |
|-----------|-------------|--------|------------------|
| deduplication | 2026-08-31 | PASS | 3 |
| edge-cases | 2026-08-31 | PASS | 4 |
| fragile-type-checks | 2026-08-31 | PASS | 2 |
| narrow-catch | 2026-08-31 | PASS | 3 |
| parallel-derivation | 2026-08-31 | PASS | 3 |
| python-subprocess-safety | 2026-08-31 | PASS | 2 |
| resource-lifecycle | 2026-08-31 | PASS | 2 |
| silent-failures | 2026-08-31 | PASS | 9 |
| test-coverage | 2026-08-31 | PASS | 3 |
| try-finally-scope | 2026-08-31 | PASS | 2 |

**These rows are generated from a real run, not asserted.** Every case is now executed by
`test_eval_cases.py` — one test per Pass Criteria checkbox — so `Last Tested` means the suite
actually ran on that date. Regenerate by running the suite; do not hand-edit the table.

The suite has demonstrated it can report bad news, which is the property that makes a green result
mean anything. Verified 2026-08-31 by mutation: breaking the `DATA_QUALITY_KEYWORDS` list turned 8
tests red; restoring the original leading-slash `'/src/main/java/'` path bug turned the two
test-coverage tests red; disabling the dedup check turned 1 red. Each mutation was reverted.

`/satori:reasoning-audit` also reads the dates here — a `Last Tested` date past its re-check
window, or a row with no date at all, surfaces as a `self-dated` finding.

## Provenance

Converted 2026-08-29 from `evals/evals.json`, which had sat untouched since 2026-06-26 while
`pattern_checker.py` grew from 4 to 11 check methods.

That file was **unrunnable, not merely stale**: its `{id, name, prompt, expected_output, files,
assertions}` shape is read by no runner in this environment — skill-creator's scripts never open
`evals.json`, and its 12 `assertions` arrays were all empty.

**Why this format and not `case.yaml`**: `claude plugin eval` is the first-party runner and would
be the better target — it has a real `--threshold` exit code and a `--ablation with-without`
baseline arm. It is gated behind early access on this account (verified 2026-08-29: both
`claude plugin eval` and `claude plugin eval init` refuse with "currently in early access"), so its
schema cannot be validated here, and authoring unvalidated YAML would repeat exactly the mistake
this conversion fixes. The format below is the `cc-plugins` convention, which is hand-runnable
today.

**Migration target**: once `plugin eval` is available, run `claude plugin eval init` and port these
cases to `case.yaml` — each case's Setup becomes the prompt, and its Pass Criteria become graders.

## Running the suite

```bash
cd evals && python3 -m pytest test_eval_cases.py -v
```

Each test builds a scratch git repo, plants the case's Setup, and invokes the checker through its
CLI exactly as the old hand runbook prescribed — so it also catches wiring faults a unit test
cannot see (a check that never runs, a diff filter that excludes everything, a path that resolves
differently under the CLI). `audit()` asserts the checker did not report `Scanned 0/…`, because a
case that silently scans nothing would otherwise pass.

To run one case: `-k resource_lifecycle`. To regenerate the Results table above, re-run the suite
and update the date — do not hand-edit outcomes.

Two things this suite does NOT establish, both needing a real session:
- that a finding actually reaches the user through `/satori:pre-pr-audit`'s presentation steps;
- that the skill's prose guidance (the non-automated pattern sub-categories) is being followed.

`scripts/test_pattern_checker.py` is the companion unit suite — it tests individual check methods
against planted inputs. This file drives the whole checker end to end. Both are worth keeping: the
unit tests localize a failure, these prove the pipeline works.

## Known coverage gaps

Corrected 2026-08-29 after a `/satori:reasoning-audit` pass found both original bullets factually
wrong. Recorded here rather than quietly rewritten, because a gap list that misstates the gaps is
worse than none — it reads as "we know about this hole and chose not to test it."

- ~~**`--project-patterns` is dead code**~~ — **resolved 2026-08-30.** The flag, its constructor
  parameter, and its call site were removed rather than implemented, and the two SKILL.md sites now
  say plainly that project patterns are agent-side judgement work rather than automated coverage.
  `test_pattern_checker.py` asserts the parameter stays gone.
- **`_check_resource_lifecycle`'s third branch is genuinely uncovered**: `FileInputStream` /
  `BufferedReader` / `Files.newBufferedReader` without try-with-resources (helper at
  `pattern_checker.py:254`, HIGH). `resource-lifecycle.md` exercises only the Spark
  persist/broadcast branches. That is the only branch relevant outside Spark codebases, and the
  largest remaining hole in this suite.
- **No case runs a wholly clean file end to end.** The original bullet claimed no case asserts the
  *absence* of a finding, which is false — at least 6 of the 10 carry a negative-control criterion
  ("produces no finding", "clears the finding"). What is missing is narrower: a file with no planted
  defect at all, which is what would catch a check that fired unconditionally on every input.
- **Java checks run against Python files and nothing asserts either way.** `check_all` gates only
  `_check_python_subprocess_safety` on `.py` (`pattern_checker.py:107`); the other nine run on
  Python source, and SKILL.md deliberately feeds Python in. `_check_edge_cases`' `.get\s*\(` will
  fire on an ordinary `d.get(k)` and emit a Java recommendation.
- ~~**Severity and category are unpinned** in `resource-lifecycle.md` and
  `try-finally-scope.md`~~ — partly closed: `test_eval_cases.py` now pins category for both and
  severity wherever the criteria state one. The markdown criteria themselves still omit severity
  for those two cases.

## Defects found by the 2026-08-29 audit

### Fixed, with tests — `scripts/test_pattern_checker.py`

- **`:442` tested `'/src/main/java/' in file` with a leading slash.** `git diff --name-only`
  returns repo-relative paths, so a single-module Java repo never matched and had silently received
  zero test-coverage findings since the check was written. Now anchored at a path boundary
  (`MAIN_SOURCE_PATH`), so `src/main/java/...`, `./src/...` and `mod/src/...` all match, with the
  module prefix preserved when deriving the test path.
- **`_has_cleanup_in_scope` matched the literal `.unpersist()`**, empty parens included, so the
  common `unpersist(true)` form read as no-cleanup and fired a CRITICAL false positive. Now matches
  the method name plus an open paren, which also keeps `unpersistAllLater()` from satisfying it.

### Still open — these are case bugs or checker bugs a first run will hit

- **`pattern_checker.py:352` counts commas in an 11-line window** to decide `Collectors.toMap`
  arity. Any other comma within ±5 lines suppresses the finding, so the case can pass or fail on
  incidental layout. `test_eval_cases.py` works around it with comma-free filler and says so;
  the real fix is an arity check, not a comma count.
- ~~**`silent-failures.md`'s keyword list disagrees with the implementation**~~ — **resolved
  2026-08-30.** The doc was wrong (its list was invented during the 08-29 conversion, not derived
  from any spec); `missing` and `malformed` were then added to the implementation on the merits.
  Both lists now come from one `DATA_QUALITY_KEYWORDS` constant (`pattern_checker.py:46`), and
  agreement is asserted in both directions.
- **`narrow-catch.md` is satisfiable only by a fully-qualified call.** The check greps the preceding
  5 lines for a `java`/`org.apache` token (`pattern_checker.py:637`), and idiomatic Java puts that in
  an import at the top — so the check almost never fires in production. `test_eval_cases.py` now pins
  the *current* behaviour explicitly, with a message telling you to update both it and this list if
  the gap is ever closed, so a fix is a visible change rather than a silently-passing one.
- **`resource-lifecycle.md`'s "naming the un-released resource" criterion** does not match what the
  checker reports — the pattern string is generic and the variable name appears nowhere. Either
  reword the criterion or make the finding name the variable.
- **`try-finally-scope.md`'s first criterion** says a finding is reported "for the statements
  sitting between" acquisition and `try`; the checker reports the acquisition line and never
  identifies the intervening statements. Worth adding.
