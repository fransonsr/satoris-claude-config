# Eval: subprocess call missing its guards

Exercises `_check_python_subprocess_safety` (all four sub-checks).

## Setup
A changed Python file calling `subprocess.run(['mvn', 'test'])` with no `cwd=`, no `timeout=`, no
`except subprocess.TimeoutExpired` handler within ~20 lines, and no `shutil.which(`/
`os.path.exists(` guard in the ~15 lines above.

## Pass Criteria
- [ ] Four findings are reported: missing `cwd=`, missing `timeout=`, missing `TimeoutExpired`
      handler, missing executable guard.
- [ ] The first three are HIGH; the executable guard is MEDIUM.
- [ ] Adding each guard clears its corresponding finding independently.
