# Eval: same constant hardcoded in two files

Exercises `_check_parallel_derivation_constants`.

## Setup
Two changed files that each independently hardcode the same non-common numeric literal (e.g. `37`
as a truncation length in one and as an expected length in the other). Avoid the whitelisted
values (10, 16, 32, 64, 100, 128, 256, 512, 1000, 1024).

## Pass Criteria
- [ ] One MEDIUM `Parallel Derivation` finding is reported for the shared constant.
- [ ] `code_snippet` lists both locations.
- [ ] The same literal appearing in only ONE changed file produces no finding.
- [ ] A whitelisted value (e.g. `256`) in both files produces no finding.
