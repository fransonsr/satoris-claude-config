# Eval: data-quality problem logged instead of raised

Exercises `_check_silent_failures`.

## Setup
A changed Java file with `LOGGER.warn(...)` (or `log.warn`/`log.error`) whose message contains a
data-quality keyword
(duplicate, invalid, corrupt, conflict, mismatch, missing, malformed)
and which is followed by normal execution rather than a throw.

The keyword list above must match `DATA_QUALITY_KEYWORDS` in `scripts/pattern_checker.py` exactly.
It did not until 2026-08-30: this case named `missing`/`malformed`, which the implementation
lacked, and omitted `corrupt`/`conflict`/`mismatch`, which it had — so following the case as
written recorded a FAIL against a checker working as designed. `missing` and `malformed` were then
added to the implementation on the merits. `test_pattern_checker.py` now asserts case and code
agree in both directions.

## Pass Criteria
- [ ] A finding is reported at the `LOGGER.warn` line, `HIGH` severity, category `Silent Failure`.
- [ ] `recommendation` proposes failing fast rather than continuing.
- [ ] Every one of the seven keywords above fires when used in the message.
- [ ] A `LOGGER.warn` with no data-quality keyword produces no finding.
- [ ] The `log.warn`/`log.error` shape fires on the same keywords as `LOGGER.warn`.
