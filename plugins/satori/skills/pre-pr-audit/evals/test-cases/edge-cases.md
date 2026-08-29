# Eval: missing null and duplicate-key handling

Exercises `_check_edge_cases` (both branches).

## Setup
Two changed Java hunks:
1. `metadataMap.get(key)` whose result is used with no null check, no `getOrDefault`, and no
   `Optional.ofNullable` within the following two lines.
2. `Collectors.toMap(keyMapper, valueMapper)` with no third merge-function argument.

## Pass Criteria
- [ ] The `Map.get()` hunk produces a MEDIUM `Edge Case` finding.
- [ ] The `toMap` hunk produces a HIGH finding mentioning duplicate keys.
- [ ] Rewriting hunk 1 with `getOrDefault` clears its finding.
- [ ] Adding a merge function to hunk 2 clears its finding.
