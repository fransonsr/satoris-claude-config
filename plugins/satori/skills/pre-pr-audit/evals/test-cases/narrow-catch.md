# Eval: narrow catch on a library boundary

Exercises `_check_narrow_catch_on_library_api`.

## Setup
A changed Java file that calls a `java.*`/`javax.*`/`org.apache.*` API and catches a specific
non-broad subtype (e.g. `NoSuchFileException`) rather than the documented broader type.

## Pass Criteria
- [ ] A HIGH `Edge Case` finding names the caught type.
- [ ] Catching a broad type (`Exception`, `IOException`, `RuntimeException`) produces no finding.
- [ ] A narrow catch with no library call in the preceding five lines produces no finding.
