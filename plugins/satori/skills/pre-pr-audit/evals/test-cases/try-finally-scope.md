# Eval: work between acquisition and try

Exercises `_check_try_finally_scope`.

## Setup
A changed Java file that calls `.persist(`, then runs one or more statements, and only then opens
a `try { ... } finally { <cleanup> }`.

## Pass Criteria
- [ ] A finding is reported for the statements sitting between acquisition and `try`.
- [ ] `why_it_matters` explains that a throw in that gap skips the `finally` cleanup.
- [ ] Moving those statements inside the `try` clears the finding.
