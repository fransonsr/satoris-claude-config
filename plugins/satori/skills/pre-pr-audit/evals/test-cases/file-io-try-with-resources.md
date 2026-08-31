# Eval: file I/O opened without try-with-resources

Exercises `_check_resource_lifecycle`'s **third branch** — the `file_patterns` loop and its
`_in_try_with_resources` helper (`scripts/pattern_checker.py:240-262`, helper at `:795`).

Added 2026-08-31. This branch was the largest hole in the suite: `resource-lifecycle.md` covers
only the two Spark branches (`persist`/`unpersist`, `broadcast`/`destroy`), leaving the one branch
that matters in any non-Spark Java codebase untested since the check was written.

## Setup

A changed Java file that opens a file resource with one of the four detected constructors —
`new FileInputStream(`, `new FileOutputStream(`, `new BufferedReader(`, `Files.newBufferedReader(`
— outside a `try (...)` resource block.

The helper looks backwards at most **10 lines** from the opening call for a line matching
`^\s*try\s*\(`, so the same-line idiom
`try (FileInputStream in = new FileInputStream(f)) {` is recognized.

## Pass Criteria

- [ ] A HIGH `Resource Leak` finding is reported, with pattern
      `File I/O without try-with-resources`.
- [ ] `recommendation` names try-with-resources or an explicit `close()` in `finally`.
- [ ] All four detected constructors fire.
- [ ] Wrapping the call in `try (...)` clears the finding.
- [ ] A file with no resource construction produces no finding.
- [ ] The finding is distinguishable from the two Spark branches, which share the
      `Resource Leak` category but use different `pattern` strings and CRITICAL severity.

## Known limitation — verified 2026-08-31, not a test failure

**An explicit `close()` in a `finally` block still fires.** This is correct resource management:

```java
FileInputStream in = null;
try {
    in = new FileInputStream(f);
    use(in);
} finally {
    if (in != null) in.close();
}
```

`_in_try_with_resources` only recognizes the `try (...)` form, so the pre-Java-7 idiom — still
common in older codebases, and still correct — is reported as a leak. The executable test pins this
current behaviour rather than asserting the ideal, so closing the gap would be a visible, deliberate
change rather than a silently-passing one.

Whether to close it is a judgment call, not an obvious fix: broadening the helper to accept any
`finally` containing a `close()` would weaken it, since a `close()` on the wrong variable, or one
reachable only on some paths, would then satisfy it. Left open deliberately.
