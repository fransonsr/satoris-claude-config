# Eval: list.add in a loop with no dedup guard

Exercises `_check_deduplication`.

## Setup
A changed Java file where `resultList.add(record)` sits inside a `for`/`while` loop, with no
`Set<`, `.contains(`, or `visited` reference within roughly 20 lines either side.

## Pass Criteria
- [ ] A MEDIUM `Missing Deduplication` finding is reported.
- [ ] Introducing a `Set` or a `.contains()` guard nearby clears the finding.
- [ ] The same `.add(` call OUTSIDE any loop produces no finding.
