# Copilot Review Issue Patterns

**Purpose**: Classification of issue types that Copilot's PR review has found in this codebase.
Use this as a checklist during pre-PR code review to proactively find and fix these issues.

**How to use**: For each classification below, follow the "How to find" instructions as a sweep
over the code being reviewed. Apply the heuristics even when the code looks correct — these are
the patterns that *seem* fine on first read but are consistently wrong.

**Copilot count**: Number of Copilot review threads attributed to each class across all PRs.
Use this to prioritize which sweeps to run first (highest count = highest ROI).

---

## Classifications

### 1. State Machine / Control Flow Logic
**Copilot count**: ~9 threads

**Description**: The code handles the happy path correctly but failure modes, partial runs,
and retry scenarios produce wrong state transitions or bypass safety guards. Common forms:
- A boolean or variable is computed once for the wrong branch and reused (e.g., `final_state`
  always claiming "MERGED" regardless of which branch was actually taken)
- A fallback path bypasses a safety check that the primary path enforces
- A multi-step operation is not idempotent: re-running after partial success fails because
  step 1 is now invalid (e.g., `cmd_skip(VERIFIED)` called again when already at VERIFIED)
- A warning-only response leaves a system object in a state with no workable forward path

**How to find**:
1. Identify every place a variable is assigned inside an `if/else` branch but read *after*
   the branch. Ask: "if the other branch ran, is this value still correct?"
2. Find every `if X fails: try Y instead` pattern. Ask: "does Y bypass any safety check that
   X enforces? Could X fail *because* the safety check rejected it, not just due to a transient
   error?"
3. Find every multi-step operation (step A then step B). Ask: "if step A already succeeded in
   a prior run and the entry point is called again, what happens when step A is attempted
   again?" Is the operation idempotent?
4. Find every `warn + set_failure_flag` pattern. Ask: "does the object end up in a state that
   has a valid forward path? Or is it stuck?"

**Example — wrong branch variable reuse** (Round 13, fleet_runner.py):
```python
# BEFORE (bug): final_state always "MERGED" when zero_convertible=True,
# even when target_state was not VERIFIED/MERGED or the advance failed midway
final_state = "MERGED" if zero_convertible else target_state
_log(f"  Reconciled {repo_name} → {final_state}")

# AFTER (fix): compute actual_target from the branch taken
actual_target = "MERGED" if (zero_convertible and target_state in ("VERIFIED", "MERGED")) else target_state
if rc != 0:
    _log(f"  Warning: failed to advance {repo_name} to {actual_target}")
else:
    _log(f"  Reconciled {repo_name} → {actual_target}")
```

**Example — fallback bypasses safety guard** (Round 16, fleet_runner.py):
```python
# BEFORE (bug): if cmd_skip rejects the repo (safety guard not met), _advance_to
# bypasses that guard entirely
rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="VERIFIED"))
if rc != 0:
    rc = _advance_to(fleet_state_path, repo_name, "VERIFIED")  # bypasses guard!

# AFTER (fix): cmd_skip failure propagates — no fallback
rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="VERIFIED"))
if rc == 0:
    rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="MERGED"))
```

**Example — non-idempotent multi-step operation** (Round 17, fleet_runner.py):
```python
# BEFORE (bug): always calls cmd_skip(VERIFIED) first; if prior run left repo at
# VERIFIED, this call is invalid and blocks the MERGED step permanently
rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="VERIFIED"))
if rc == 0:
    rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="MERGED"))

# AFTER (fix): check current state, skip steps already done
current_state = entry.get("state", "")
if current_state == "MERGED":
    rc = 0
else:
    if current_state != "VERIFIED":
        rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="VERIFIED"))
    else:
        rc = 0
    if rc == 0:
        rc = fs.cmd_skip(fleet_state_path, _ns(repo=repo_name, target_state="MERGED"))
```

---

### 2. Defensive Guards (null / type / encoding)
**Copilot count**: ~6 threads

**Description**: Code fails to guard against None, unexpected types, or encoding errors in
data read from external sources (files, subprocess output, JSON deserialization). Common forms:
- Calling `.get()` on a value that may be `None` (e.g., `data.get("x", {}).get("y")` when the
  key `"x"` IS present but maps to `null` — the `{}` default doesn't apply)
- Using a value as a string without confirming it is a string (non-string JSON values from
  hand-edited or corrupt files)
- `except` clauses that list `OSError` and `json.JSONDecodeError` but omit `UnicodeDecodeError`
  on file reads
- Trusting `None` as "not present" when `None` could also mean "present but invalid"

**How to find**:
1. Find every `x.get("key", {}).get("nested")` chain. Ask: "if `key` is present in the JSON
   with value `null`, does the default `{}` apply?" (It does NOT — `.get()` returns the actual
   `null`/`None`, ignoring the default.)
2. Find every place a value from JSON deserialization is used as a specific type (string
   comparison, arithmetic, iteration). Ask: "is there an `isinstance` guard before use?"
3. Find every `except (OSError, json.JSONDecodeError)` on a file read. Ask: "is
   `UnicodeDecodeError` included?" (It is not a subclass of either.)
4. Find every `if value is not None` guard. Ask: "could this value be a non-None but still
   invalid type (int, dict, list)?" If so, `isinstance(value, expected_type)` is stronger.

**Example — null JSON value bypasses default** (Round 8, fleet_runner.py / fleet_state.py):
```python
# BEFORE (bug): if JSON has "metadata": null, data.get("metadata", {}) returns None
# (the key IS present), and None.get("generator") raises AttributeError
generator = data.get("metadata", {}).get("generator")

# AFTER (fix): explicit isinstance guard
metadata = data.get("metadata")
if not isinstance(metadata, dict):
    return None
return metadata.get("generator")
```

**Example — missing UnicodeDecodeError** (Round 10, fleet_runner.py):
```python
# BEFORE (bug): invalid UTF-8 bytes raise UnicodeDecodeError, which is not OSError
except (OSError, json.JSONDecodeError):
    return None

# AFTER (fix)
except (OSError, json.JSONDecodeError, UnicodeDecodeError):
    return None
```

**Example — isinstance stronger than is not None** (Round 13, fleet_state.py):
```python
# BEFORE (bug): None is blocked, but integer 0 or dict {} would pass and be
# compared as strings later
if entry.get("estimatedCalls") == 0 and inventory_generator is not None and inventory_generator != "fleet-runner":
    return True

# AFTER (fix): isinstance rejects None AND all non-string types
if entry.get("estimatedCalls") == 0 and isinstance(inventory_generator, str) and inventory_generator != "fleet-runner":
    return True
```

---

### 3. Operator Observability / Error Message Accuracy
**Copilot count**: ~7 threads

**Description**: Log messages, blockReasons, and exception messages assert a specific root
cause that may not be correct. An operator reading the message gets a wrong diagnosis and
wastes time investigating the wrong thing. Common forms:
- An `except SomeError` handler names a specific subsystem in the message, but the same
  exception type can be raised by other subsystems in the same `try` block
- A `blockReason` string asserts a specific cause (e.g., "remote-tracking ref missing") when
  the underlying command can fail for multiple reasons
- A log message names the "intended" final state rather than the actual state reached
- A rejection message omits key variables (e.g., the generator value) that would tell the
  operator why the rejection occurred

**How to find**:
1. Find every `except SomeError as e: log("subsystem X failed: {e}")`. List all statements
   in the `try` block that can raise `SomeError`. If more than one subsystem is listed, the
   message must be generic or the try block must be split.
2. Find every `blockReason` or error string that contains "because" or asserts a specific
   cause. Ask: "are there other reasons the same condition could occur?"
3. Find every rejection message in a guard function (`cmd_skip`, `cmd_advance`, etc.). Ask:
   "does it include the actual values that caused the rejection, or just the rule?"
4. Find every log line that names a state. Ask: "is this the state we actually reached, or
   the state we intended to reach?"
5. Find every error or block message that names a specific value (e.g., a branch name, an
   encoding, a file format) when the code handles a more general range. Ask: "if a user runs
   this with a different value in that range, will the message still be accurate?" (e.g.,
   "check out master" is wrong for repos with `main` as default; "Invalid JSON" is wrong for
   UTF-8 decoding failures.)

**Example — OSError handler overstates cause** (Round 18, fleet_runner.py):
```python
# BEFORE (bug): subprocess.run() can also raise OSError (e.g., mvn not found),
# but the message claims it was a log file problem
except OSError as e:
    _log(f"  Cannot create log file: {e}")
    blockReason = f"cannot create log file: {e}"

# AFTER (fix): generic message covers both log setup and subprocess launch
except OSError as e:
    _log(f"  OSError during mvn clean install (log setup or launch): {e}")
    blockReason = f"mvn clean install I/O error: {e}"
```

**Example — rejection message omits key variable** (Round 20, fleet_state.py):
```python
# BEFORE (bug): operator can't tell if skip was rejected due to estimatedCalls,
# riskFlags, or inventory_generator — all three are checked
print(
    f"skip rejected: {repo_name} has estimatedCalls={entry.get('estimatedCalls')!r} "
    f"and no no-conversion risk flag "
    f"(need estimatedCalls=0 or one of {sorted(_NO_CONVERSION_FLAGS)})",
)

# AFTER (fix): include all values that feed the decision
print(
    f"skip rejected: {repo_name} does not qualify as no-conversion — "
    f"estimatedCalls={entry.get('estimatedCalls')!r}, "
    f"inventory_generator={inventory_generator!r}, "
    f"riskFlags={entry.get('riskFlags') or []}; "
    f"need estimatedCalls=0 from a trusted inventory source, "
    f"or one of {sorted(_NO_CONVERSION_FLAGS)}",
)
```

---

### 4. Provenance / Identity Discrimination
**Copilot count**: ~3 threads

**Description**: A single string value (e.g., a `generator` field) is used to distinguish
"trusted" from "untrusted" provenance, but two different code paths both write the same
string — one representing a legitimate result and one representing a stub or placeholder.
The guard rejects both when it should only reject the stub.

**How to find**:
1. Find every string constant used as a provenance marker (e.g., `"fleet-runner"`, `"manual"`).
   Search for all places that *write* that string. Ask: "do all write sites represent the same
   semantic provenance?"
2. Find every `!= "some-marker"` or `== "some-marker"` guard. List every code path that writes
   that marker value. Are they all equivalent from the guard's perspective?
3. When a guard was introduced to distrust a specific source, ask: "is there any legitimate
   code path that also writes this same marker and should be trusted?"

**Example — two write sites, one marker** (Round 20, fleet_runner.py / fleet_state.py):
```python
# BEFORE (bug): _do_auto_advance_no_java writes "fleet-runner" for legitimate
# no-Java repos, but _is_no_conversion_repo distrusts "fleet-runner" as a stub
"generator": "fleet-runner"   # written by _do_auto_advance_no_java — legitimate!
# ...
if inventory_generator != "fleet-runner":  # rejects both stub AND legitimate no-Java
    return True

# AFTER (fix): use a distinct marker for the legitimate write site
"generator": "fleet-runner-prereq"   # _do_auto_advance_no_java — trusted
"generator": "fleet-runner"          # pre-analysis stub — still distrusted
```

---

### 5. Infrastructure / Environment Handling
**Copilot count**: ~3 threads

**Description**: Code assumes a "standard" environment that may not hold in deployment.
Common forms:
- Paths not expanded (tilde `~` prefix not resolved before passing to `Path()` or `open()`)
- Git commands that assume local tracking branches exist (which they don't in minimal/shallow
  clones where only `origin/<branch>` refs exist)
- Executable assumptions (hard-coded paths, commands that may not be on PATH)

**How to find**:
1. Find every `Path(some_string)` or `open(some_string)` where `some_string` comes from
   user config, a JSON file, or a command-line argument. Ask: "could this contain `~` or
   `$VAR`?" If yes, apply `os.path.expandvars(os.path.expanduser(...))` first.
2. Find every `git log <branch>..HEAD` or `git diff <branch>` command. Ask: "does this
   assume a local tracking branch exists? Use `origin/<branch>` to reference the remote-
   tracking ref, which exists even in shallow clones."
3. Find every subprocess call that invokes an executable by name. Ask: "is there a `which`
   check before the call? What happens if the executable is missing?"

**Example — tilde not expanded** (Round 11, fleet_state.py):
```python
# BEFORE (bug): Path("~/clones/repo") does not expand tilde
inventory_path = Path(clone_path) / ".claude" / "analyze-reports" / "conversion-inventory.json"

# AFTER (fix)
inventory_path = (
    Path(os.path.expandvars(os.path.expanduser(clone_path)))
    / ".claude" / "analyze-reports" / "conversion-inventory.json"
)
```

**Example — bare branch ref fails in minimal clone** (Round 9, fleet_runner.py):
```python
# BEFORE (bug): 'master' local branch may not exist in a minimal clone
result = subprocess.run(["git", "log", f"{base}..HEAD", "--oneline"], ...)

# AFTER (fix): use remote-tracking ref, which always exists after fetch
result = subprocess.run(["git", "log", f"origin/{base}..HEAD", "--oneline"], ...)
```

---

### 6. Documentation Accuracy
**Copilot count**: ~3 threads

**Description**: Docstrings, comments, or inline documentation describe behavior that doesn't
match the implementation. Misleads future readers and can cause incorrect edits. Most common
when implementation was changed but the adjacent comment was not updated.

**How to find**:
1. For every docstring that describes a transformation, algorithm, or allowed value set: read
   the actual implementation and verify the claim. Pay special attention to:
   - Character sets in regex patterns (e.g., "non-alphanumeric" when `_.:-` are also kept)
   - Listed allowed/disallowed values (e.g., generator strings) that may have been extended
   - State transition descriptions that no longer match the state machine
2. For every `# trusted / distrusted` comment listing specific values: verify the list matches
   the code.
3. **Spec-code coherence**: For any feature described in a SKILL.md or instruction doc alongside
   its implementing code, verify the documented behavior matches the implementation. (e.g., "jira
   ticket embedded in branch name" — is `_branch_name()` actually doing that?)
4. **Changelog coverage**: If any commit in this PR fixes a doc/code artifact from an earlier
   commit in the same PR (e.g., correcting a CHANGELOG entry, fixing a SKILL.md line), verify
   the fix is reflected back in the CHANGELOG entry for the original feature.
5. **ADF / external-format rendering**: For any code that generates content for Jira or Confluence
   ADF (Atlassian Document Format), verify that text nodes do NOT use Markdown syntax (`[text](url)`,
   `**bold**`, etc.) — ADF text nodes render Markdown syntax literally. Use raw URLs for auto-linking.

**Example — regex docstring mismatch** (Round 15, fleet_runner.py):
```python
# BEFORE (bug): regex preserves _.:-  but docstring says "non-alphanumeric → _"
def _repo_slug(repo_name):
    """Return a filesystem-safe slug for a repo name (non-alphanumeric → _)."""
    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", repo_name)

# AFTER (fix): docstring names the actual preserved set
def _repo_slug(repo_name):
    """Return a filesystem-safe slug for a repo name (chars outside [a-zA-Z0-9_.:-] → _)."""
    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", repo_name)
```

---

### 7. Test Integrity
**Copilot count**: ~2 threads

**Description**: Tests assert the buggy behavior rather than the correct behavior, or use
argument matching patterns that pass for the wrong reason. Common forms:
- A test was written before a bug was fixed and never updated — it now documents the bug
- Mock dispatch uses substring matching (`"keyword" in cmd`) when token-exact matching
  (`cmd[:N] == [...]`) is required to avoid false positives
- Unused variables left in test setup (dead references to real objects)

**How to find**:
1. For every test that covers a recently changed code path: read both the test and the code.
   Ask: "does this test assert the *correct* behavior, or the behavior that existed *before*
   the fix?" If both have the same value, the test may not be testing the fix.
2. For every mock `side_effect` that dispatches based on `cmd`: check whether the matching
   uses `cmd[:N] == [...]` (token-exact) vs `"string" in " ".join(cmd)` (substring). Substring
   matching can accidentally match the wrong command.
3. Search for unused variable assignments in test methods (variables assigned but never read).

**Example — test asserting the bug** (Round 13, test_fleet_state.py):
```python
# BEFORE (bug): test was written when None → True was the (buggy) behavior
def test_is_no_conversion_repo_returns_true_for_real_zero(self):
    entry = _repo_entry("ANALYZED", estimated_calls=0)
    self.assertTrue(fs._is_no_conversion_repo(entry, inventory_generator=None))  # wrong!

# AFTER (fix): assert the correct behavior (None = distrust = False)
def test_is_no_conversion_repo_returns_false_for_none_generator(self):
    entry = _repo_entry("ANALYZED", estimated_calls=0)
    self.assertFalse(fs._is_no_conversion_repo(entry, inventory_generator=None))
```

---

## Update Protocol

This is a **living document** — it accumulates patterns across all projects and all PRs, not
just the session in which a pattern was first observed. Every Copilot review round is an
opportunity to improve it.

**After every Copilot (or other automated reviewer) PR review round**:
1. For each thread addressed, identify which classification it belongs to and increment its count.
2. If the issue reveals a sharper or more general heuristic for an existing class, update the
   "How to find" steps for that class.
3. If a thread introduces a pattern that does not fit any existing class, **add a new
   classification** with: description, "How to find" steps, and at least one before/after
   example. Place it in count order once the count is known, or at the bottom until then.
4. Update the count summary table and the `last updated` date.
5. If the CLAUDE.md summary (under "Code Review Checklist → PR Review Issue Patterns") has
   drifted from the counts or class list here, sync it.

**When to add a new classification vs. extend an existing one**:
- New class: the pattern requires a meaningfully different detection strategy ("how to find")
  than any existing class
- Extend existing: same detection strategy applies, the new issue is just another instance
  of the pattern; add it as an additional example if it clarifies a nuance

**Copilot count summary** (last updated: 2026-06-26, through PR #101 Round 6):

| Classification | Count |
|---|---|
| State Machine / Control Flow Logic | ~14 |
| Operator Observability / Error Message Accuracy | ~12 |
| Defensive Guards (null / type / encoding) | ~7 |
| Documentation Accuracy | ~8 |
| Infrastructure / Environment Handling | ~4 |
| Provenance / Identity Discrimination | ~3 |
| Test Integrity | ~2 |
| **Total** | **~50** |
