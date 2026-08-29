# Eval: resource acquired without cleanup

Exercises `_check_resource_lifecycle`.

## Setup
A changed Java file that calls `.persist(` (or `.broadcast(`) on a Spark RDD/dataset and never
calls the matching `.unpersist(`/`.destroy(` anywhere in the enclosing method.

## Pass Criteria
- [ ] A finding is reported naming the un-released resource.
- [ ] The finding's `line` points at the acquisition call, not the end of the method.
- [ ] `recommendation` proposes cleanup in a `finally` block.
- [ ] A version of the same file that DOES call the matching release produces no finding.
