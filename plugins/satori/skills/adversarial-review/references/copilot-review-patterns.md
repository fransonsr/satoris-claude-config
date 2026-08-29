# Copilot Review Issue Patterns

This document is a classification of **review lenses** used by adversarial-review agents and
maintained by human reviewers. The adversarial-review skill reads it dynamically and spawns one
parallel agent per class; there is no prioritization or weighting — all lenses run together.

**For agents**: Each class below is a lens — a distinct perspective through which you read the
artifact under review. Apply your assigned class's lens to that artifact. The "How to find" /
"How to apply" section gives you what you need: pattern-based classes list specific heuristics to
grep for or check; holistic classes give judgment questions to read against. Apply only your own
class; the others run as separate agents.

**For maintainers**: After each review round (Copilot, adversarial-review, or other automated
reviewer), use the Update Protocol at the bottom to refine existing classes and propose new ones.

**Lens taxonomy**: Heuristic-based lenses have specific patterns to check; judgment-based lenses
read the artifact holistically and flag what seems wrong (Classes 8 and 10 are judgment-based).

---

## Classifications

### 1. State Machine / Control Flow Logic

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
5. **Spring Boot auto-configuration ordering**: for any `@Conditional*` on an `@AutoConfiguration`
   class (or a `@Bean` method inside one) that references another bean/class NOT owned by the
   same auto-configuration, ask: "is the condition evaluated at auto-configuration *processing*
   time (bean-definition registration — alphabetical by fully-qualified class name unless an
   explicit `@AutoConfiguration(before/after)` edge says otherwise) or at bean-*creation* time?"
   `@ConditionalOnBean`/`@ConditionalOnMissingBean` at the **class level** evaluate during
   processing — if the referenced bean is registered by an auto-configuration that sorts
   alphabetically *after* this one (with no explicit ordering edge), the condition evaluates
   against a bean that doesn't exist yet and silently takes the "absent" branch even when that
   bean will exist once the whole context finishes loading. A test using
   `ApplicationContextRunner.withUserConfiguration(...)` to supply the "other" bean does NOT
   catch this: it registers the bean directly, bypassing the real `AutoConfigurationImportSelector`
   processing order entirely, so the test passes while the real ordering bug survives untested.
   The fix is to resolve the dependency at bean-*creation* time instead (e.g. an
   `ObjectProvider<T>` parameter on the `@Bean` method, resolved via `getIfAvailable()`), which is
   immune to auto-configuration processing order since all bean *definitions* are registered
   before any bean is *created*.

**Example — auto-configuration-ordering false negative** (java-stack-incubator quiesce starter,
Round 1→Round 2 of an adversarial review):
```java
// BEFORE (bug, introduced as Round 1's OWN fix for a different finding):
// class-level condition evaluates during bean-definition registration, alphabetically before
// the Spring Boot auto-configuration that actually registers a MeterRegistry bean in a real app
@AutoConfiguration
@ConditionalOnClass(MeterRegistry.class)
@ConditionalOnBean(MeterRegistry.class)   // false in every real app — evaluated too early
public class QuiesceMetricsAutoConfiguration { ... }

// AFTER (fix): resolve at bean-creation time instead, immune to processing order
@Bean
@ConditionalOnMissingBean
QuiesceMetricsRecorder quiesceMetricsRecorder(ObjectProvider<MeterRegistry> meterRegistries) {
    MeterRegistry meterRegistry = meterRegistries.getIfAvailable();
    return meterRegistry != null ? new MicrometerQuiesceMetricsRecorder(meterRegistry) : QuiesceMetricsRecorder.NOOP;
}
```
The Round 1 fix's own test used `.withUserConfiguration(MeterRegistryConfig.class)` — registering
the `MeterRegistry` bean directly rather than through a real auto-configuration — so it passed
while silently disabling metrics in every real deployment. Caught in Round 2 by adding a fixture
auto-configuration deliberately named to sort alphabetically *after* this one (e.g.
`ZzzMeterRegistryAutoConfiguration`) and registering it via `AutoConfigurations.of(...)` alongside
the class under test, which exercises the real processing order instead of bypassing it.

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
3. **Spec-code coherence**: For any feature described in a README, design doc, runbook, or
   instruction doc (a Claude Code skill's SKILL.md is one instance of this) alongside its
   implementing code, verify the documented behavior matches the implementation. (e.g., "jira
   ticket embedded in branch name" — is `_branch_name()` actually doing that?)
4. **Changelog coverage**: If any commit in this PR fixes a doc/code artifact from an earlier
   commit in the same PR (e.g., correcting a CHANGELOG entry, fixing a SKILL.md line), verify
   the fix is reflected back in the CHANGELOG entry for the original feature.
5. **ADF / external-format rendering**: For any code that generates content for Jira or Confluence
   ADF (Atlassian Document Format), verify that text nodes do NOT use Markdown syntax (`[text](url)`,
   `**bold**`, etc.) — ADF text nodes render Markdown syntax literally. Use raw URLs for auto-linking.
6. **Escalate on safety rationale or absolute claims**: if a doc-accuracy finding concerns a
   safety/correctness rationale (a comment justifying why a risk is accepted, or an invariant the
   code is claimed to guarantee) or contains an absolute claim ("gives no path to X", "certainly
   was not created", "can never happen"), do not close it as a wording fix. Trace the actual code
   paths the claim depends on before reclassifying — the false sentence is usually the symptom of
   a wrong invariant, not stale prose, and a future reader will reason from the (false) sentence to
   conclude a change is safe when it isn't.

**Provenance note (heuristic 6)**: derived from a single sls-locking-service PR (RS-4420) where a
"Documentation Accuracy" lens hit three real correctness defects in a row, each initially read as
a wording nit: (a) two store methods compared a canonicalized key against a raw one — the doc said
they used "the UUID key" as if interchangeable; (b) a comment claimed a network create-or-fail
call "certainly was not created" on failure, which is false for a request that times out after the
server-side write succeeds, leaking a lock for the rest of its TTL; (c) an accepted-risk paragraph
justified an ABA window with "the create API gives no path to this," true of that one API but false
of three other real paths (an admin bulk-delete, a same-key bulk-unlock, and TTL expiry) that
reach the identical state. All three were reachable, none were cosmetic, and the common tell was
that the "doc" in question was a safety rationale or contained an unqualified absolute rather than
a plain behavioral description.

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

### 8. Semantic Correctness / Logical Completeness

**Description**: Code or documentation that claims to handle a condition but covers only a
subset of the intended domain, or where two parts of the same codebase make assumptions about
each other that are internally inconsistent. No mechanical heuristic enumerates these — the
reviewer reads with fresh eyes and asks "does this actually do what it says?"

Common forms:
- A validator accepts a broader input set than the validation is meant to enforce (e.g., a
  regex using `.+` standing in for a specific structured format like `PROJECT-NNN`)
- A conditional fall-through claims to represent "safe" or "OK" but silently omits a case
  that should be blocked (e.g., detecting "ahead" but not "diverged")
- Two parts of the same codebase make different assumptions about the same value (e.g., one
  writes it in mixed case, the other validates it as uppercase-only)
- Two sections of a document (SKILL.md, a spec, a README) give contradictory instructions
  about the same thing — Documentation Accuracy covers doc/code drift; this class covers
  doc/doc inconsistency within a single file

**How to find** (judgment-based, not heuristic-based):
1. For every validation gate, guard condition, or regex: state in one sentence what the
   *intended* input domain is. Then read the actual code. Does it accept exactly that domain,
   or something broader?
2. For every conditional fall-through path (code that reaches "success" without any condition
   matching): ask "is this a known-safe default, or an unexamined case?"
3. For every value that flows through more than one system boundary (e.g., written by one
   function, validated by another): ask "do both sides agree on the format/casing/encoding?"
4. For every multi-section document: read two sections that describe related behavior and ask
   "do they agree? Could a reader follow both and end up with contradictory actions?"

**Example — regex too permissive** (Round 10, fleet_runner.py):
```python
# BEFORE (bug): .+ accepts any non-empty prefix, not just Jira keys like LOGGING-42
slug_in_branch = bool(
    re.fullmatch(rf"logging-migration/{_slug}-{_date}", branch_name)
    or re.fullmatch(rf"logging-migration/.+-{_slug}-{_date}", branch_name)
)

# AFTER (fix): constrain prefix to actual Jira key format
_jira_key = r"[A-Z][A-Z0-9]*-\d+"
slug_in_branch = bool(
    re.fullmatch(rf"logging-migration/{_slug}-{_date}", branch_name)
    or re.fullmatch(rf"logging-migration/{_jira_key}-{_slug}-{_date}", branch_name)
)
```

**Example — silent fall-through on unsafe state** (Round 10, fleet_runner.py):
```python
# BEFORE (bug): ahead_count > 0 falls through as "Synced OK" — doesn't detect
# the case where origin also has commits not in local (diverged, not just ahead)
elif ahead_count == "0":
    # ... fast-forward ...
# else: ahead_count > 0 — fall through to Synced OK

# AFTER (fix): explicitly detect divergence before declaring Synced OK
else:
    behind = subprocess.run(["git", "rev-list", "--count", f"HEAD..{remote_ref}"], ...)
    if behind.returncode == 0 and int(behind.stdout.strip()) > 0:
        reason = f"repo is diverged from {remote_ref} ..."
        _log(f"  BLOCKED: {reason}")
        # ... block ...
    # else: ahead only — no divergence, Synced OK
```

**Example — writer/validator case mismatch** (Round 11, fleet_runner.py):
```python
# BEFORE (bug): R10 added [A-Z][A-Z0-9]*-\d+ validator, but _branch_name()
# interpolated jira_ticket raw — lowercase input → branch the validator rejects
def _branch_name(repo_name, jira_ticket=None, today=None):
    if jira_ticket:
        return f"logging-migration/{jira_ticket}-{slug}-{today}"

# AFTER (fix): normalize at the write site so validator and writer agree
    if jira_ticket:
        return f"logging-migration/{jira_ticket.strip().upper()}-{slug}-{today}"
```

---

### 7. Test Integrity

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

### 9. Operator Spec Completeness

**Description**: A procedural document — a runbook, playbook, migration guide, onboarding doc,
API integration guide, or a Claude Code skill's SKILL.md — is reviewed as an *operator
specification*: executable, complete, and internally consistent. "Operator" here means anyone
following the document's instructions step by step, not specifically an SRE or ops role. Issues
arise when the document accurately described the original scope but was not fully updated when
scope broadened, phases were renamed, or new decision branches were added. Unlike Documentation
Accuracy (class 6, which covers code/doc drift and doc/doc inconsistency in prose files), this
class covers gaps that appear specifically when reading a **step-by-step operator spec** as
though you are about to follow it for the first time.

*Provenance: empirical — derived from 22 Copilot threads on PR #106, a prose-only change to a
Claude Code skill's SKILL.md. The five failure modes below are not specific to Claude Code
skills — they generalize to any procedural document where a reader executes instructions in
order: a deployment runbook, an incident-response playbook, a customer onboarding guide, an
API migration doc. SKILL.md is simply the artifact type where this class was first observed.*

Common forms:
- **Stale scope language**: The PR broadens scope (e.g., adds a new call category), but step
  headers, scope statements, idempotency notes, skip conditions, and report section labels
  were updated inconsistently — some caught, others missed. Copilot finds them one at a time
  across successive rounds.
- **Rename cascade miss**: A phase or term is renamed (e.g., "LLM pass" → "LLM and semantic
  pass"), but the sweep is incomplete: mid-step instructions, routing conditions, idempotency
  notes, and report labels retain the old name.
- **Operator executability gap**: A step says "evaluate each X call" without providing a
  command to enumerate X; or a file reference is a bare filename when a fully-qualified path
  is needed for an operator to proceed without additional research.
- **Branch completeness gap**: A decision point documents the "found candidates" path but omits
  the "no candidates found" exit; or a subsequent step applies to all action types when it
  should be scoped to a subset (e.g., CONVERT/METRIC only, not DELETE/LEVEL_CHANGE).
- **Term undefined at use**: A variable used as a routing signal (M, semantic review list,
  needsLlmReview) is referenced in a later step without being anchored to where it was first
  computed and named. The name used in Step 4 must match the label introduced in Step 3.

**How to find**:

1. **Scope-broadening sweep**: If this PR broadens the scope of the document's subject (e.g., a
   skill, a service, a migration procedure), grep the entire document for the old scope terms
   (e.g., `NEEDS_LLM_REVIEW`, `LLM pass`). For each hit: is it still accurate after the
   broadening, or should it now include the new scope? Apply in one pass — do not wait for
   Copilot to find them one at a time.

2. **Rename cascade**: If a phase or pass was renamed, grep the entire document for the old
   name. Update every hit: step headers, mid-step instructions, skip conditions, idempotency
   notes, and report section labels. A partial rename (some hits updated, others not) produces
   one Copilot thread per missed hit.

3. **Operator executability**: For every step that says "evaluate each X" or "review all Y",
   ask: "can an operator enumerate X/Y from a shell command?" If not, add a `jq` or `grep`
   snippet. For every file reference in the spec, verify it is a fully-qualified path (with
   directory prefix) — bare filenames require the operator to know the directory.

4. **Branch completeness**: For every conditional in a step ("if candidates found / if not"),
   verify both branches have documented actions. Check: zero-result exit conditions ("if no
   candidates, proceed to Step N"), action-type-specific restrictions ("for CONVERT and METRIC
   only — skip for DELETE and LEVEL_CHANGE"), and routing across combined conditions (e.g.,
   "semantic candidates present AND needsLlmReview=0 → skip to Step N").

5. **Term definition at first use**: Find every variable name used as a routing signal in
   later steps (e.g., "M from Step 3", "needsLlmReview", "semantic review list"). Trace back
   to where each is first computed. Verify that step labels the variable with the name used
   later. If Step 3 introduces M as "the count of NEEDS_LLM_REVIEW calls", later steps must
   consistently call it M (not `needsLlmReview` the jq field name, or "the output of jq").

**Root cause note**: These issues arise because procedural specs are typically reviewed for
*accuracy* (does the text match what was intended?) rather than for *executability and
completeness* (can an operator follow these steps step-by-step without gaps?). The five
heuristics above simulate what Copilot does when it reads the spec as an operator.

**Example — stale scope language** (PR #106, Rounds 3–7, ~9 threads):
```markdown
# BEFORE (bug): "LLM pass" retained in idempotency section after scope broadened to
# include semantic review of TRANSFORMED calls
LLM pass: Only processes NEEDS_LLM_REVIEW calls from transform-report.json.

# AFTER (fix): renamed to reflect combined scope
LLM and semantic pass: Processes NEEDS_LLM_REVIEW calls AND TRANSFORMED calls flagged
in Step 3.5 for semantic review.
```

**Example — operator executability gap** (PR #106, Rounds 6 and 9, ~2 threads):
```markdown
# BEFORE (bug): bare filename (no path); no jq to enumerate TRANSFORMED calls
For each TRANSFORMED call in transform-report.json:

# AFTER (fix): fully-qualified path + jq snippet for enumeration
For each TRANSFORMED call in .claude/analyze-reports/transform-report.json:
  jq '[.[] | select(.action == "TRANSFORMED") | {file, line}]' "$REPORT"
```

**Example — branch completeness gap** (PR #106, Rounds 8, 10, 11, ~4 threads):
```markdown
# BEFORE (bug): routing for needsLlmReview=0 with semantic candidates undocumented;
# field-mapping steps in Step 7 applied to all action types

# AFTER (fix):
# - "If needsLlmReview (M from Step 3) is 0: skip Step 4 directly to Step 5."
# - Steps 3–4 in Step 7: "(CONVERT and METRIC actions only — skip for DELETE and LEVEL_CHANGE)"
```

**Example — term undefined at use** (PR #106, Rounds 3 and 11, ~2 threads):
```markdown
# BEFORE (bug): Step 3.5 computed M implicitly; Step 4 referenced "needsLlmReview"
# (the jq field) and Step 11 routing used "M" without tying them together

# AFTER (fix): Step 3 labels the count as M; Step 4 intro says "needsLlmReview (M
# from Step 3)"; Step 7 routing consistently uses "needsLlmReview (M from Step 3)"
```

---

### 10. Spec Operator Walkthrough

**Description**: A procedural document — a runbook, playbook, migration guide, onboarding doc,
API integration guide, or a Claude Code skill's SKILL.md — is read *linearly, top to bottom, by
someone who has never seen it and has no foreknowledge of what was intended*: an operator about
to follow it for the first time. The reviewer flags every place they would get stuck, have to
guess, or hit a branch with no documented path forward. This is a **judgment-based lens with no
heuristics**, and that is the entire point: where Class 9 (Operator Spec Completeness) enumerates
five *known* failure modes and greps for them, this class catches the novel and cascading gaps
those heuristics did not anticipate — the confusion that only surfaces when you actually try to
execute the document as written, in order, without skipping ahead.

*Provenance: proactive — designed during adversarial-review architecture review before first observed occurrence.*

**Domain context the reviewer needs** (safe to provide — this is *what the artifact is*, not a
list of how it tends to fail):
- A procedural document is an operator specification: a deployment runbook, an incident
  playbook, an onboarding guide, an API integration doc, and a Claude Code skill's SKILL.md are
  all instances of this artifact type. It is meant to be *executed* — a person or agent reads
  it step by step and performs each action it describes. "Following it" means doing exactly what
  each step says, in the order written, using only information available at that point in the doc.
- The reader has no access to the author's intent, the PR description, the surrounding code, or
  any prior version. Their only input is the words on the page, read in sequence.
- An operator "gets stuck" when a step cannot be performed without information that has not yet
  appeared: an undefined term, a value referenced before it is computed, a decision with no
  documented option for the situation at hand, or an instruction that assumes knowledge the
  document never supplied.

**Why this is a separate class, not a sixth heuristic in Class 9**: Giving one agent both Class 9's
five failure-mode heuristics *and* this walk instruction contaminates the walk. The agent's
attention is already shaped by "stale scope language, rename cascade, executability gap, branch
gap, undefined term" — so it finds instances of *those* patterns rather than reading with genuinely
fresh eyes. The adversarial-review architecture runs one agent per class in parallel, with no agent
seeing another's findings, which naturally prevents this cross-contamination. So this walk runs as
its own agent (Class 10), in parallel with the Class 9 heuristic agent. The two are **complementary,
not overlapping**: Class 9 catches the failure modes we have already seen and named; Class 10
catches what those named modes did not anticipate. Overlap between their findings is expected and
fine — the synthesizer deduplicates by the `file` string (already formatted as `path:line` or
`path:startLine-endLine`).

**Boundary**: Provide the Class 10 agent the *domain context* above (what a procedural document
is, what being an operator means) but **never** Class 9's failure-mode list. The known-failure-mode
list is the contaminating part; the domain context is not.

**How to apply** (judgment-based, not heuristic-based):

1. Read only the sections of the spec that changed in this diff (and the minimal surrounding
   context needed for them to make sense), from the top of the first changed section downward, in
   document order. Do not jump ahead to resolve a question a later section might answer — if you
   had to jump ahead, that itself is a finding.
2. At each step, ask: *"Can I perform this action right now, using only what I have read so far?"*
   If the answer is no, stop and record where and why.
3. At each decision point or branch, ask: *"For the situation I am actually in, is there a
   documented path? What do I do if the condition is false / the list is empty / none of the
   options apply?"* If there is no path for a situation that can occur, record it.
4. At each term, variable, label, or referenced artifact, ask: *"Has this been defined or produced
   earlier in what I have read? Do I know what it means and where it came from?"* If a term is used
   before it is introduced, record it.
5. Record anything that would cause genuine confusion in execution: ambiguous instructions, two
   readings of the same sentence, a step that silently assumes the output of a step that was
   skipped, an ordering that requires a later result to perform an earlier action.

Express findings as the operator's lived experience — *"At Step 4 I am told to 'process the
flagged calls,' but nothing earlier told me how calls get flagged or where the flags are
recorded, so I cannot proceed without guessing"* — not as a heuristic class name.

**Relationship to other classes**:
- **Class 9 (Operator Spec Completeness)**: complementary peer. Class 9 = known failure modes,
  found by grep/enumeration. Class 10 = unanticipated gaps, found by reading as a naive operator.
  Run both, in parallel, as separate agents. Do not merge.
- **Class 6 (Documentation Accuracy)**: Class 6 checks whether the doc *matches the code/other
  docs* (the reviewer cross-references an external source of truth). Class 10 reads the doc *in
  isolation* and asks only whether it is internally followable; it needs no external referent.
- **Class 8 (Semantic Correctness / Logical Completeness)**: same judgment-based spirit, different
  target. Class 8 reads code/spec asking "does this do what it claims?"; Class 10 reads a spec
  asking "could a first-time operator actually execute this, in order, without getting stuck?"

**Example — gap a fresh-eyes walk catches that Class 9's heuristics miss**:

Class 9's term-definition heuristic (Check 5) traces *named routing signals* ("M from Step 3",
"needsLlmReview") back to their definitions. It is looking for a specific shape: a named variable
reused across steps. Consider a spec that reads:

```markdown
## Step 5: Reconcile the field mappings

Compare the proposed field names against the established conventions and resolve any conflicts
before proceeding to Step 6.
```

Class 9's heuristics find nothing here: there is no old scope term, no renamed phase, no
"evaluate each X" without a command, no missing if/else branch, and no *named* routing variable
left undefined. But an operator walking the spec linearly stops cold: *"Which 'established
conventions'? The document never told me they existed, never told me where they are recorded, and
never told me how to tell that two names 'conflict.' I have read every prior step and I still do
not know what file or list to open or what rule to apply. I cannot perform this step without
guessing."* The gap is a silent dependency on context the document assumes but never supplied —
exactly the kind of issue that only surfaces when a reader with no foreknowledge tries to *do*
the step, and exactly what the heuristic enumeration was not built to detect.

---

### 11. Cross-File Rule Consistency

**Description**: When the same rule, procedure, value constraint, contract term, or worked
example is stated in more than one file, every restatement is a latent divergence from its
canonical source. When the canonical file is updated, restatements must be updated in cascade —
and frequently aren't. This lens compares each restatement against the file that owns the rule by
definition. It is exclusively **cross-file**: file A defines the rule, files B/C restate it, and
they have drifted apart.

The canonical source is not always a doc. When a project ships an executable script, library
function, config schema, or type definition that implements or defines something, and the
project's own instructional text (a README, a design doc, a quick-start, a Claude Code skill's
SKILL.md) re-derives that same thing inline — a full API call sequence, a polling loop, a query,
a copy of a schema's fields — that inline block is a restatement of the canonical
implementation, exactly as prone to drift as a doc-to-doc restatement. Treat the script/function/
schema as the canonical source and the inline block as the restatement. This applies to any
multi-file codebase, not just skills: a Java module's README restating a config default that
lives in a properties file, or two services' READMEs both restating a shared API contract, are
the same class of finding.

*Lens type: heuristic-based.*

*Provenance: empirical — PR #108 needed 8 Copilot rounds; 6 were cross-file restatement drift in
the logging-migration `choose` skill (SCORING.md / FLEET-STATE-SCHEMA.md / EXAMPLE-PLAN.md diverged
from choose/SKILL.md). The per-file logic/correctness lenses never compared a rule across files, so
the drift survived local review. Extended after `address-pr-issues/SKILL.md` was found to
reproduce its own `fetch_pr_threads()` script logic inline in three separate places — one of which
had already silently drifted (see doc-vs-script example below).*

**How to find**:

1. **Build the restatement map.** For every rule, procedure, value constraint, contract term, or
   worked example that appears in more than one touched file, identify the **canonical source** —
   the file that owns the rule by definition (often a primary spec, README, or design doc; a
   Claude Code skill's SKILL.md is one instance), not a file that copied it. A multi-file project
   typically has: a primary spec/README (canonical procedures + contracts), reference docs
   (lookup tables / schemas re-stating those procedures), and consumer docs (re-stating contract
   terms they consume) — a multi-file Claude Code skill follows the same shape with SKILL.md as
   the primary spec and `references/*.md` as the reference docs. **Also check
   `scripts/`/`lib/`/`src/`**: if a script, library function, config schema, or type definition
   exists that performs or defines the same thing an instructional block spells out step-by-step
   (a GraphQL query, a REST call sequence, a retry/polling loop, a config contract), that
   implementation is canonical and the inline block is a restatement — flag it even though "file
   A defines the rule" here means "code A implements/defines the thing," not prose. A doc that
   explicitly warns readers not to hand-write an operation (e.g. a "use scripts first" table)
   while still containing that exact hand-written operation elsewhere in the same file is a
   strong, self-contained signal.

2. **Classify each restatement: pointer or copy.** A *pointer* defers to the canonical source
   ("see choose/SKILL.md Q7"). A *restatement* re-encodes the rule's content (prose, a table row, a
   code block, an example). Only restatements can diverge; pointers cannot.

3. **Diff each restatement against canonical** and assign severity:
   - **HIGH** — logic/behavior diverges: an operator following the restatement would *do something
     different* from canonical (e.g., the restatement collapses two distinct failure modes into one
     branch, or omits a guard canonical enforces).
   - **MEDIUM** — wording/scope diverges without (yet) changing behavior: a table that adds or drops
     a column, an example missing an edge case, or imprecise phrasing of an otherwise-correct rule
     ("stored as-is with cloudId: null" vs. "ticket keys stored without verification").
   - **LOW** — DRY-only: the restatement currently matches verbatim, so nothing is wrong *today*,
     but the duplication is a latent cascade risk. Flag for conversion to summary + pointer. (This
     is the only non-divergence finding in this class.)

4. **Cascade across all restatements.** When this PR changed a canonical file, sweep *every* file
   that restates *any* changed rule before reporting — do not stop at the first diverged
   restatement. A missed sibling restatement is a miss.

   **The sweep must search beyond the current diff, not just the files already touched by it.**
   A sibling restatement is exactly as likely to live in a file this change never opens as in one
   it did — restatement drift, by definition, comes from files that were never updated in lockstep
   with the canonical source. Grep the whole repo (or module) for the literal phrase/value/name
   being corrected, not just the diff's own file list; scoping the sweep to "files this PR already
   touches" silently excludes the exact files most likely to still be wrong.

**Provenance note (step 4's repo-wide-sweep addition)**: java-stack-incubator quiesce starter,
Round 2 of an adversarial review fixed a stale "2-5s poll cadence" claim in `SPEC.md` §6.2 (the
canonical source), correctly rewording it to describe the shipped single-default behavior. The
fix's own doc-fallout sweep believed it was thorough but was scoped to files the round's diff had
already touched — it missed the identical stale phrase in two files that commit never opened:
`Ec2InstanceMetadataClient.java`'s class Javadoc and `QuiesceImdsPollingProperties.java`'s field
Javadoc, both restating the same now-corrected claim. Both survived undetected for a full
additional round, caught only when Round 3's reviewer ran a literal grep for the corrected phrase
across the whole module rather than trusting the prior round's own "doc fallout, swept" claim.

**Example — HIGH (logic divergence)** (PR #108, logging-migration choose):
```
File: choose/references/SCORING.md:74–77
Canonical: choose/SKILL.md → Q7=F implementation
Issue: SCORING.md step 1 collapses two distinct failure modes — "MCP not installed" and
  "atlassianUserInfo call fails" — into a single "if API call fails" branch. SKILL.md
  distinguishes them with different interaction behaviors (no interaction vs. retry/skip prompt).
Severity: HIGH — an operator following SCORING.md handles MCP-unavailable with a user prompt
  instead of silently storing keys as-is with cloudId: null.
```

**Example — LOW (DRY-only, no current divergence)**:
```
File: migrate/SKILL.md:120–135
Canonical: choose/SKILL.md → fleet-state.json contract
Issue: migrate/SKILL.md reproduces the full fleet-state.json field table verbatim rather than
  summarizing + pointing to choose/SKILL.md. It matches today, but any future edit to the contract
  in choose/SKILL.md will silently diverge here.
Severity: LOW — convert the duplicated table to a one-line summary + pointer to choose/SKILL.md.
```

**Example — doc-vs-script, already diverged once (address-pr-issues)**:
```
File: address-pr-issues/SKILL.md — three separate inline `gh api graphql` blocks reproducing the
  PR review-thread fetch query (a manual fallback in Step 1, "OLD METHOD" in Step 6, a re-fetch
  in Step 8)
Canonical: scripts/lib/github-api.sh → fetch_pr_threads()
Issue: when a pagination bug was fixed in fetch_pr_threads() (added pageInfo{hasNextPage
  endCursor} + a stderr warning when a PR exceeds 100 threads), the inline duplicates in SKILL.md
  did not get the fix automatically — they had to be located and patched by hand in a follow-up
  change (CHANGELOG.md v1.5.0). The duplication looked like a DRY-only nit until it produced a
  real functional gap: rounds run against the stale inline copy silently under-counted threads.
Severity: when the canonical side is executable, default to MEDIUM even with no divergence found
  yet — a script fix doesn't force anyone to notice or re-sync inline copies (they still parse
  and run), unlike a broken build. Fix: replace the inline block with a call to the script/
  function, or a one-line pointer to it if the block is illustrative rather than operational.
```

**Relationship to adjacent classes**:
- **Class 6 (Documentation Accuracy)**: doc-vs-code (and doc/doc within one file) against an
  external source of truth. Class 11 is doc-vs-doc *across files*, where one doc is the declared
  canonical owner of the rule.
- **Class 8 (Semantic Correctness / Logical Completeness)**: two sections of *the same file*
  contradicting each other. Class 11 is two *different files* disagreeing about a rule one owns.
- **Class 9 (Operator Spec Completeness)**: a *single* SKILL.md's internal completeness after a
  scope/rename change. Class 11 checks whether that SKILL.md's changes propagated to the *other*
  files that restate its rules.

---

### 12. Code Smells / SOLID & Structural Quality

**Description**: Code that behaves correctly today but is structurally unsound — a method or
class doing more than one job, a design closed against extension, tight coupling to concretions,
or a named code smell (God class, primitive obsession, feature envy, data clump, long parameter
list) that will make the next change harder or riskier than it needs to be. Unlike the
correctness-focused classes above, this lens does not ask "does this do what it claims?" — it asks
"will this be easy to safely change later?" The canonical definitions of every check below live in
`~/.claude/CLAUDE.md` (this environment's global coding-standards file, loaded into every project);
this class applies them as a review lens rather than restating them.

*Lens type: heuristic-based.*

*Provenance: proactive — none of the other existing classes check structural/design quality; all are
correctness-bug lenses (state machine bugs, defensive guards, error messages, documentation drift,
etc.). `~/.claude/CLAUDE.md` already defines a full Refactoring Checklist, a SOLID Principles
section, and an Anti-Patterns catalog, but no adversarial-review lens applied them. Added directly
from that gap, not from an observed PR round. If a project's own CLAUDE.md defines an equivalent
checklist instead (or in addition), apply that project's version — the check is "does this
project's stated design-quality bar exist and hold," not specifically this file's wording.*

**How to find**:

0. **Locate the checklist to apply**: check the reviewed project's own CLAUDE.md first (repo root,
   or nearest ancestor) for an equivalent Refactoring Checklist / Anti-Patterns / SOLID Principles
   section. If the project has one, use it in place of (or alongside, if it adds project-specific
   items) the sections below — the goal is "does this project's own stated design-quality bar
   hold," not specifically this file's wording. Fall back to `~/.claude/CLAUDE.md` (this
   environment's global coding-standards file) only when the project defines no such section of
   its own. The rest of this section names `~/.claude/CLAUDE.md`'s section headings as the default
   reference; substitute the project's own section names when step 0 finds one.
1. **Method length & extraction**: for every new or changed method, does it satisfy
   `~/.claude/CLAUDE.md` → `## Refactoring Checklist` → `### Code Structure`'s length and
   extraction thresholds? If not, flag for extraction.
2. **Magic numbers/strings**: for every new or changed literal used in a conditional, threshold,
   or repeated more than once, ask: "should this be a named constant?"
3. **Duplicated logic**: does a new or changed block closely mirror logic that already exists
   elsewhere in the same file or module? (This is about duplicated *implementation*, not a
   restated *rule* across files or docs — see Relationship to adjacent classes below for the
   boundary with Class 11.)
4. **SOLID principles** (`~/.claude/CLAUDE.md` → `## Core Principles` → `### 4. SOLID Principles`),
   for every new or substantially modified class:
   - **SRP**: does it have more than one unrelated reason to change (e.g., it both parses input
     and persists results, or both computes business logic and formats output)?
   - **OCP**: does adding a new case require editing an existing `if`/`switch` chain rather than
     extending via configuration, a strategy, or polymorphism?
   - **LSP**: does an override narrow the base contract — throwing where the base guarantees a
     value, returning `null` where the base guarantees non-null, or requiring stricter
     preconditions than the base declares?
   - **ISP**: does an interface force an implementor to provide a method it cannot meaningfully
     support (an empty body, an `UnsupportedOperationException`)?
   - **DIP**: does a high-level module construct or directly reference a concrete low-level
     implementation (`new SomeConcreteClass()`, a static call, a service locator) instead of
     depending on an injected abstraction?
5. **Named smells** (definitions: `~/.claude/CLAUDE.md` → `## Anti-Patterns to Avoid` → `###
   Production Code Smells`): does the change introduce or extend an instance of God class,
   primitive obsession, feature envy, a data clump, or a long parameter list?
6. **Dependency & coupling**: are dependencies received via constructor injection, or reached via
   a static/global, an inline `new` of a concrete class, or a service locator? Is coupling to an
   interface/abstraction, or to a concrete implementation?

**Severity & blast_radius calibration** (this lens finds design-improvability, not confirmed
defects — the generic severity/blast_radius rules embedded in every adversarial-review agent
prompt default toward "confirmed bug" framing that doesn't fit here):
- **Severity**: default LOW; use MEDIUM only when the structural issue will make a specific,
  already-planned upcoming change materially harder or riskier. Reserve HIGH/CRITICAL for cases
  where the structural issue itself causes or masks a correctness problem (at which point a
  correctness-focused class above likely already covers it too).
- **blast_radius**: default `local`. Report `cross_file` only when the *identical* structural
  defect is provably duplicated in another file's source (e.g., the same God-class split needed in
  two places) — "other callers of this constructor exist elsewhere" describes an opportunity for a
  cleaner design, not a defect spreading across files, and is not on its own grounds for
  `cross_file`.
- **Disposition**: adversarial-review's Phase C has no separate bucket for "deferred design
  improvement" — a Class 12 finding a reviewer defers still goes through the standard **Accepted
  risk** disposition like any other finding, and lands in the PR description's Known Limitations
  the same way. The `blast_radius` default above (`local`) is what actually keeps most Class 12
  findings out of a round's confirmed cross-file yield and out of that PR-description obligation
  in the first place; reserve `cross_file` — and therefore inclusion in the yield count — for the
  rare case where the same structural defect is genuinely duplicated elsewhere, not for every
  finding this lens produces.

**Example — feature envy resolved by moving the method** (illustrative):
```java
// BEFORE: applyDiscount reads two of Customer's fields to decide something about
// Customer — the logic belongs on Customer, not on the class computing invoice totals
class InvoiceProcessor {
    void applyDiscount(Customer customer, Invoice invoice) {
        if (customer.getLoyaltyYears() > 5 && customer.getTotalSpend() > 10000) {
            invoice.setTotal(invoice.getTotal() * 0.9);
        }
    }
}

// AFTER: the eligibility check moves to the class whose data it actually uses
class Customer {
    boolean isEligibleForLoyaltyDiscount() {
        return loyaltyYears > 5 && totalSpend > 10000;
    }
}
class InvoiceProcessor {
    void applyDiscount(Customer customer, Invoice invoice) {
        if (customer.isEligibleForLoyaltyDiscount()) {
            invoice.setTotal(invoice.getTotal() * 0.9);
        }
    }
}
```

**Example — data clump / long parameter list resolved by a config object** (illustrative):
```java
// BEFORE: five parameters always travel together and will grow with the next field addition
void createShipment(String street, String city, String state, String zip, String country) { ... }

// AFTER: the recurring group becomes its own value object
void createShipment(Address address) { ... }
```

**Relationship to adjacent classes**:
- **Class 1 (State Machine / Control Flow Logic)** and **Class 8 (Semantic Correctness / Logical
  Completeness)**: both ask whether code *behaves correctly*. This class assumes the code already
  behaves correctly and asks whether it is *well-designed* — whether the next change will be easy
  or risky. A method can pass every check in Classes 1 and 8 while still being a 200-line God
  method; that's this class's finding, not theirs.
- **Class 11 (Cross-File Rule Consistency)**: also flags duplication, but Class 11's target is a
  *stated rule, procedure, or contract* restated across files (docs, or a script reproduced
  inline) that can drift from its canonical source. This class's duplication check (item 3 above)
  is about repeated *implementation logic within the same file or module* that should be
  extracted into a shared method — no cross-file canonical source is involved.
- **Class 6 (Documentation Accuracy)**: checks whether a project's own docs match its code or
  other docs. This class doesn't check that — it reads CLAUDE.md only to source its checklist
  definitions (step 0 above), then evaluates the structure of the *code* itself, not documentation.

---

## Update Protocol

This is a **living document** — its lenses accumulate across all projects and all PRs, not just
the session in which a lens was first observed. Every review round is an opportunity to sharpen
the existing lenses and discover gaps that warrant a new one.

**After every review round (Copilot, adversarial-review, or other automated reviewer)**:

**Step 1 — Refine existing classes.** For each finding, identify which class's lens it belongs to.
If the finding reveals a sharper angle, tighter boundary, or clearer heuristic for that class,
update the class's "How to find" / "How to apply" section. Add a new before/after example if it
illustrates a nuance not already captured.

**Step 2 — Propose new classes.** After reviewing all findings as a whole, ask: *"Did any finding
surface a gap that no existing lens would have caught — a reading mode or perspective entirely
absent from the current class list?"* If yes, draft a new class. The criterion for a new class
vs. extending an existing one:
- **New class**: the gap warrants a distinct agent with a different reading mode or perspective
  (e.g., Class 10 reads holistically in document order; no existing class did that)
- **Extend existing**: the finding is a new instance or sharper example of an existing lens; add
  it as an additional example or refine the heuristic

**Step 3 — Sync CLAUDE.md.** `~/.claude/CLAUDE.md`'s "PR Review Issue Patterns" section is a
pointer only, by design — it does not enumerate class names or descriptions, since doing so would
itself be a Class 11 restatement of this file's own class list, drifting the same way every other
cross-file restatement does. When a class is added, renamed, or materially changed, no edit to
that pointer's *text* is needed; just verify `~/.claude/copilot-review-patterns.md` and
`plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md` are still the two
paths CLAUDE.md names, and its `cp` command between them still resolves correctly.

**Note — a third, plugin-cached copy can exist outside both paths above**: an installed Claude
Code plugin can cache its own snapshot of this file, separate from either path Step 3 names.
`adversarial-review/SKILL.md`'s own Setup Step 1 resolves — and echoes — exactly which copy a
given review actually reads; check that echoed path (not this Note, which doesn't implement that
resolution) before trusting a review's verdict on a class added or changed since the cache was
last refreshed.

**When adding a new class**, include:
- Name
- Description
- Lens type (heuristic-based or judgment-based)
- "How to find" or "How to apply" section appropriate to the lens type
- At least one concrete example
- Provenance note
- Relationship to the nearest adjacent class (to prevent overlap drift)

*Last updated: 2026-08-29.*
