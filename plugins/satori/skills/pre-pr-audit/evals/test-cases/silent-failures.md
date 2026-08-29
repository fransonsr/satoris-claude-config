# Eval: data-quality problem logged instead of raised

Exercises `_check_silent_failures`.

## Setup
A changed Java file with `LOGGER.warn(...)` whose message contains a data-quality keyword
(duplicate, missing, invalid, malformed) and which is followed by normal execution rather than a
throw.

## Pass Criteria
- [ ] A finding is reported at the `LOGGER.warn` line.
- [ ] `recommendation` proposes failing fast rather than continuing.
- [ ] A `LOGGER.warn` with no data-quality keyword produces no finding.
