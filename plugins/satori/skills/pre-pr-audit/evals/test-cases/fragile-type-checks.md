# Eval: string shape used as a type discriminator

Exercises `_check_tostring_equals` and `_check_string_shape_type_proxy`.

## Setup
Two changed Java hunks:
1. `node.toString().equals(other.toString())` on a receiver whose declared type is an interface
   or abstract class.
2. `token.toString().startsWith("\"")` used to decide whether a token is a string literal.

## Pass Criteria
- [ ] Hunk 1 produces a HIGH `Silent Failure` finding.
- [ ] Hunk 2 produces a HIGH `Type/Name Resolution` finding.
- [ ] Both recommendations propose a real type check (`instanceof`, `.getKind()`, or an enum
      discriminator) rather than string comparison.
