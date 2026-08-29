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

- `_check_resource_lifecycle`'s project-pattern branch (`project_patterns` argument) is not
  covered by any case below.
- No case asserts the *absence* of a finding on clean input, so a checker method that fired
  unconditionally would still pass every case here. Worth adding.
