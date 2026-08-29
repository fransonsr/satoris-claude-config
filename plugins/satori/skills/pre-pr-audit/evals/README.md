# pre-pr-audit Evals

Risk tier: 🟢 Low (read-only analysis; the skill proposes fixes but applies none without
approval). Required before merge: every case below PASS or explicitly waived.

Each case exercises one of `scripts/pattern_checker.py`'s check methods end to end — a planted
defect goes in, and the expected finding must come out. Cases are hand-run; see
[Running a case](#running-a-case).

## Results

| Test case | Last Tested | Result |
|-----------|-------------|--------|
| resource-lifecycle | — | Pending |
| try-finally-scope | — | Pending |
| edge-cases | — | Pending |
| silent-failures | — | Pending |
| fragile-type-checks | — | Pending |
| deduplication | — | Pending |
| test-coverage | — | Pending |
| parallel-derivation | — | Pending |
| narrow-catch | — | Pending |
| python-subprocess-safety | — | Pending |

**Every row is Pending because these cases have never been run.** That is the honest state, not a
placeholder to be filled in optimistically. Per the checker discipline: a suite that has never
reported bad news has not demonstrated it can.

`/satori:reasoning-audit` reads the dates in this table — a `Last Tested` date past its re-check
window surfaces as a `self-dated` finding, so letting these rows go stale is itself detectable.

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

## Running a case

1. Create a scratch git repo with the case's Setup applied as an uncommitted change.
2. Run the checker directly against the changed file:
   ```bash
   python3 scripts/pattern_checker.py --changed-files <file> --merge-base HEAD
   ```
3. Check every Pass Criteria box, or record which failed.
4. Update this file's Results row with the date and outcome.

Running the full `/satori:pre-pr-audit` skill instead also satisfies a case, and additionally
tests that the finding reaches the user — but it is slower and needs a real session.

## Known coverage gaps

Corrected 2026-08-29 after a `/satori:reasoning-audit` pass found both original bullets factually
wrong. Recorded here rather than quietly rewritten, because a gap list that misstates the gaps is
worse than none — it reads as "we know about this hole and chose not to test it."

- **`--project-patterns` is not an untested branch — it is dead code.** `project_patterns` is
  accepted at `pattern_checker.py:37`, assigned at `:40`, passed in from `main()` at `:795`, and
  never read again. `_check_resource_lifecycle` takes no such parameter. No case can cover it
  because there is nothing to cover. Meanwhile `SKILL.md:270` passes the flag and `SKILL.md:322-324`
  advertises the capability — so the feature is documented, wired, and inert. Implement it or remove
  it along with those two SKILL.md sites.
- **`_check_resource_lifecycle`'s third branch is genuinely uncovered**: `FileInputStream` /
  `BufferedReader` / `Files.newBufferedReader` without try-with-resources (`:225-253`, HIGH).
  `resource-lifecycle.md` exercises only the Spark persist/broadcast branches. That is the only
  branch relevant outside Spark codebases.
- **No case runs a wholly clean file end to end.** The original bullet claimed no case asserts the
  *absence* of a finding, which is false — at least 6 of the 10 carry a negative-control criterion
  ("produces no finding", "clears the finding"). What is missing is narrower: a file with no planted
  defect at all, which is what would catch a check that fired unconditionally on every input.
- **Java checks run against Python files and nothing asserts either way.** `check_all`
  (`:80-92`) gates only `_check_python_subprocess_safety` on `.py`; the other nine run on Python
  source, and `SKILL.md:170-172` deliberately feeds Python in. `_check_edge_cases`' `.get\s*\(`
  will fire on an ordinary `d.get(k)` and emit a Java recommendation.
- **Severity and category are unpinned** in `resource-lifecycle.md` and `try-finally-scope.md`,
  where the other eight cases pin both. A severity regression in either would pass.

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

- **`:336` counts commas in an 11-line window** to decide `Collectors.toMap` arity. Any other comma
  within ±5 lines suppresses the finding, so `edge-cases.md`'s second half can pass or fail on
  incidental layout. Needs a real arity check, not a comma count.
- **`silent-failures.md`'s documented keyword list disagrees with `:259-260`.** The case names
  "missing" and "malformed", which the implementation lacks; the implementation has "corrupt",
  "conflict", "mismatch", which the case omits. Needs a decision on which is intended before
  either side is edited.
- **`narrow-catch.md` is satisfiable only by a fully-qualified call.** The check greps the preceding
  5 lines for a `java`/`org.apache` token, and idiomatic Java puts that in an import at the top — so
  the check almost never fires in production and the case passes without noticing. The case's third
  criterion is *satisfied by* the blind spot.
- **`resource-lifecycle.md`'s "naming the un-released resource" criterion** does not match what the
  checker reports — the pattern string is generic and the variable name appears nowhere. Either
  reword the criterion or make the finding name the variable.
- **`try-finally-scope.md`'s first criterion** says a finding is reported "for the statements
  sitting between" acquisition and `try`; the checker reports the acquisition line and never
  identifies the intervening statements. Worth adding.
