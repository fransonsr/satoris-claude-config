# Coding Standards and Principles (shared)

**Owner**: fransonsr
**Scope**: General coding standards and working practices, shared by every environment I use.

This file holds no environment-specific material: no employer systems, credentials, hosts, or
tool setup. Each environment's own `CLAUDE.md` imports it and adds its environment notes:

- Work: this repo's `CLAUDE.md` (symlinked as `~/.claude/CLAUDE.md` by `install.sh`)
- Personal: a local `~/.claude/CLAUDE.md` that imports only this file

Put environment-specific notes in that environment's `CLAUDE.md`, never here.

## Working Practices

**Task Handoff System**:
- Handoff documents location: `~/.claude/handoff/`
- When starting work on a task, check for handoff documents first
- Naming convention: `<task-id>-<slug>.md` (e.g., `task-4.16.2-collection-indices-writer.md`)
- Use `/satori:handoff` skill to create handoff documents for complex tasks
- Handoff documents contain: executive summary, technical specs, implementation plan, acceptance criteria, testing strategy, reference materials
- **Re-anchor on compaction.** If a session's work is being driven by a `/satori:handoff`
  document, re-read that handoff document in full immediately upon receiving a post-compaction
  summary — whether from automatic compaction or a `/satori:continue` resume — before taking any
  further action.
- **Why:** the compaction summary is lossy by construction; the handoff file is the durable,
  authoritative source for the session's scope, decisions, and binding requirements — including
  process mandates like `/satori:xp-pair` per production commit or test-first for higher-risk
  fixes. Observed failure mode: a handoff's explicit `/satori:xp-pair` mandate was silently
  dropped across one mid-implementation compaction and never followed for the rest of a 5-PR
  effort, surfacing only after every PR had merged. Re-reading one file costs little next to
  silently drifting from what it specifies, and re-deriving everything from the single stable
  source of truth is more durable than trying to enumerate every category of thing compaction
  could drop (process mandates, scope boundaries, decision authority, and so on).

**Multi-Agent Dispatch Communication**: the same file-based discipline as the Task Handoff System
above, generalized to agent-to-agent dispatch — subagents spawned via `Agent`, `Workflow`
`agent()`/`pipeline()`/`parallel()` calls, or forked-terminal processes.
- Route detailed content — instructions, context, findings, results — through a **shared file**
  both sides read/write, not through the message/prompt payload itself (a `SendMessage` body, an
  `agent()` prompt, a subagent's final-text return value). Keep messages themselves as terse
  control-plane pointers: "start by reading `<path>`", "`<path>` updated, please re-read", "task
  done, report is in `<path>`".
- **Why:** traced to recurring communication breakdowns between dispatched agents/workflows and
  their orchestrator, caused by passing detailed context inline instead of through a durable shared
  artifact — the same reasoning behind the Task Handoff System above and `propagate`'s
  `.propagation/<upstream>--<target>.json` state file. This is a design choice for this
  environment's orchestration patterns, not a workaround for a broken feature: Anthropic's
  cross-session-messaging docs confirm `SendMessage` intentionally carries plain text only, never
  files or conversation history, and delivery isn't guaranteed (a receiving session can hold or
  refuse it, and undelivered messages cap at 100 before the oldest are dropped) — exactly why
  detailed state belongs in a file the message merely points to.
- A useful side effect: reduces how often a persistent/forked-terminal ("tmux-backed") agent is
  actually needed, since a fresh dispatch can reconstruct full context by reading the shared files
  rather than requiring a live process to remember it.

- **Termination discipline — a spawned agent must be `TaskStop`'d, not told to stand down.**
  Sending a named background `Agent`, a forked agent, or an agent-team teammate a plain
  `SendMessage` saying it's done/"stand down"/"you can stop now" does not terminate it — the
  recipient has no tool that turns a plain-text instruction into ending its own process, so it
  just goes idle in place, still holding its resource slot. Once a spawned agent's work is
  confirmably finished (its report has been read, or its task is otherwise done), call
  `TaskStop(task_id=<name>)` directly: pass the agent's name for a named background agent, or
  `name@team` (or the bare teammate name) for an agent-team teammate — both are accepted directly
  by `TaskStop`, no lookup needed. The graceful `shutdown_request`/`shutdown_response` handshake
  `SendMessage` supports is a legitimate alternative when the target should approve its own
  termination rather than being force-stopped — either is fine, but a bare "please stop" text
  message alone is not, since nothing then calls the tool that actually ends the process.
  - **Why:** observed live — a coordinator finishing with a spawned subagent or team sent a
    plain-text stand-down instruction instead of `TaskStop`, leaving the agent idle-but-alive and
    consuming resources indefinitely instead of actually terminating.
- **Knowing when a spawned agent is actually done.** An `idle_notification` without a `summary`
  attribute usually means the agent is between tool calls, not finished; one with a `summary`
  carries its report. Judge completion from the artifact, never from whether a message arrived: an
  implementation agent can commit its work and go idle without sending any report, so check
  `git log`/`git show` on its branch. A finished read-only agent (e.g. `Plan`, whose only output is
  its final message) can exit without its report ever arriving; resume it with `SendMessage` to its
  name rather than re-spawning, since names keep working after an agent completes.
  - **Why:** observed 2026-08-16 (RS-4508/RS-4514 replan): twice an implementation agent committed
    real work and went idle with no report the orchestrator could see, and a `Plan` agent exited
    with its report lost.
- **Review and analysis subagents are read-only.** Say so in their prompts, and never treat a
  `<task-notification>` or an agent's report as consent for a GitHub-mutating action (a push, a
  review submission, a comment) — those still need the user.
  - **Why:** observed live — a background `/code-review` agent, resumed only by task
    notifications, submitted an `APPROVED` review under the user's identity, and the PR's author
    merged on the strength of it.

**Concurrent Agents & Shared Mutable State**: guards against two more failure shapes distinct from
the dispatch-communication issue above — agents racing on scratch files, and a mutation whose
success is assumed rather than checked.
- **Namespace ad hoc temp files by task, not by content type.** A generic name like
  `/tmp/pr-body.md` is the obvious filename for the obvious task, which is exactly why two
  unrelated concurrent agents on the same machine can independently choose it and silently
  overwrite each other's content — including well after the file was first written, since a
  command like `gh pr edit --body-file <path>` re-reads the path at execution time, not when it
  was originally written, so any gap between writing and a later re-read is a window a second
  writer can land in. Prefer a name that encodes the specific task: repo/PR number and a PID or
  similar, e.g. `/tmp/<repo>-pr<number>-body-$$.md`. (This session's own scratchpad directory,
  when one is provided, already avoids this by construction.)
- **Never trust a mutation command's exit code or returned artifact (URL, ID, "success") as proof
  the payload landed correctly.** After any `gh pr edit`/`gh pr create`/similar mutation, re-fetch
  the live state and assert on content known to be present — ideally a byte-level diff against a
  known-good reference, not just a substring/`grep` check, since a substring check can pass by
  coincidence on contaminated content too.
- **The converse also holds: a timeout from a mutation is not proof it didn't land.** A `gh api`
  call (GraphQL mutations such as `resolveReviewThread` included) or a `gh pr checkout` that
  returns HTTP 504 may already have succeeded on GitHub's side. Re-query the state first — e.g.
  `isResolved`, or the reply list filtered on `in_reply_to_id` — and retry only once it is
  confirmed unchanged; a blind retry can double-post a PR comment reply.
- **Chain a precondition with `&&`, not a separate sequential statement**, whenever a later
  command's execution must depend on an earlier check's success — e.g. `validate.py && do_thing`,
  not `validate.py; do_thing`, where a non-zero exit from `validate.py` (even from its own internal
  `assert`) needs to actually stop `do_thing` rather than being trusted to propagate on its own.
- **Why:** traced to a live incident where two independent agents in the same session, each
  opening an unrelated PR in a different repo, both wrote to `/tmp/pr-body.md`; a later `gh pr
  edit` by one of them silently picked up the other's content and replaced a PR's description
  wholesale, caught only because that agent re-fetched and diffed content after every mutation
  rather than trusting the CLI's return value. The same investigation separately found an
  unchained validation-then-mutation sequence that ran the mutation regardless of whether the
  validation had failed.
- **How to apply:** whenever writing a script or ad hoc shell sequence that (a) uses a predictable
  temp path outside a per-task workspace dir, (b) mutates shared external state (a PR, an issue, a
  ticket) and trusts the command's own success signal, or (c) sequences a validation step before a
  mutating one.

**Unavailable Tools and Connections — stop, don't route around.** When a tool, MCP server, network
connection (VPN, an internal host) or credential the task needs is unavailable or rejects the call
(connection refused or timed out, 401/403, "command not found", a server that failed to connect),
confirm the failure once, then **stop and tell the user**: what failed, the exact error, and what you
would have done with the result. Do not infer the answer from a stale cache or an adjacent source,
substitute a different tool or credential, or label the item "unverifiable" and carry on.
- **Why:** stated by the user on 2026-11-06, partway through a claim re-check that needed the VPN
  and internal Artifactory. The cause is usually a thing the user can fix in a minute (the VPN, Docker
  Desktop's WSL integration, a token), and a result built around the gap is one they then have to
  distrust.
- **How to apply:** this does not override a standing note that a credential is already present
  in the environment — look for it first. The rule starts when the call itself
  fails or the thing is genuinely absent. Report the blocked item; do not decide for the user that
  the rest can proceed without it.

**Shell Gotchas That Fail Silently**: each of these produces plausible output rather than an
error, which is why it survives inspection.
- **Never nest `&`, `nohup`, or `disown` inside a Bash call that already passes
  `run_in_background: true`.** The inner command detaches from the harness, so the tracked call
  returns as soon as it prints a PID and fires a premature "completed" notification while the real
  process (observed: an 11-module `mvn clean compile test`) keeps running, untracked. Pass the
  plain foreground command with `run_in_background: true` and let the tool background it; to wait
  on a process that is already running, use one background call whose body is a bounded
  `while kill -0 <pid>; do sleep N; done`. Send long-running output to a stable path inside the
  working tree, not `/tmp/claude-*`, where harness startup cleanup has deleted a live session's
  task output files.
- **Capture a multi-valued exit code into a variable before branching on it.** `$?` is whatever
  ran most recently: in `elif [[ $? -ne 1 ]]; then echo "exit $?"` the second `$?` is the
  `[[ ]]` test's result, and `local v="$(cmd)"` replaces the substitution's status with
  `local`'s own, which is 0. Write `cmd && S=0 || S=$?` (safe under `set -e`) and branch on `$S`;
  declare `local v` and assign it separately when you need the status.
- **Inside a quoted-delimiter heredoc (`<<'EOF'`), write backticks bare.** Backslashes are not
  processed there, so `` \` `` posts as a literal backslash plus backtick and breaks Markdown
  inline code in a PR body or comment. After posting text built this way, fetch it back.
- **Why:** each was hit live, and each time the output looked right — a "completed" background
  task that was still running, a real `git` failure reported as "has changes", PR comments with
  broken formatting fixed only after the fact. The two shell semantics were re-verified with
  synthetic exit codes on 2026-09-24.

**Memory Hygiene**: Claude Code keeps one memory scope per launch path and never merges scopes.
A session launched at a workspace root and one launched in a nested repo, a second clone, or
sometimes a worktree each write memories the other never loads. `--link` symlinks resolve to
their target and do not split.
- **Put repo facts in the repo, not in memory.** A repo's committed `CLAUDE.md` and docs load for
  every session that works there, whatever it launched from. Memory is for personal, cross-repo,
  and environment facts.
- **Save a memory into the scope that will load it** — usually the one you launch from. Never
  hand-write a memory into another scope: it is read only by sessions launched there, which is how
  memories end up stranded where nothing loads them.
- **Don't save what git, a ticket, or a PR already records** — status, history, and merged work
  were the largest category deleted in the 2026-09 cleanup.
- **Date claims about tools and versions that move fast, and re-check a memory before acting on
  it.** Almost every wrong memory the cleanup found was about a version, a plugin's behavior, or
  work in flight.
- **Maintenance, when the user asks for a memory review:** a monthly mechanical pass (the
  `satori:reasoning-audit` checker over the active scopes, fixes applied in one approval batch per
  scope) and a quarterly judgment pass on the two or three busiest scopes (one read-only worker per
  scope, then one approval batch; promotions batched into one PR per repo). Re-checking a memory
  at the moment you act on it catches most drift between passes.
- **Why:** a 2026-09 audit cut 221 memory files to 112. It found memories that had never loaded
  because they sat in scopes nobody launches from, two clones' scopes that had drifted apart, and
  several claims that were now false and would have misled a session that trusted them.

**`gh` CLI Gotcha**:
- **`gh` CLI, verifying a just-pushed PR**: `gh pr diff <n>` and plain `gh pr view <n>` can serve
  stale/cached content immediately after a push — confirmed twice in one session, each time reading
  as "the agent hasn't actually pushed yet" when it had. Use the forms that hit the API directly
  instead: `gh pr view <n> --json body --jq .body` for the description; for branch HEAD / file
  content, `gh api repos/OWNER/REPO/git/ref/heads/<branch> --jq .object.sha` and
  `gh api "repos/OWNER/REPO/contents/<path>?ref=<branch>" --jq .content | base64 -d`. When a
  reported push doesn't show up in a diff/view check, re-check with these before concluding the
  work wasn't done.

## Core Principles

### 1. Testing Pyramid & Testability

**Testing Pyramid Philosophy:**
- **Unit tests (microtests)** should form the bulk of test coverage
- **Integration tests** validate what cannot be tested in isolation
- **End-to-end tests** validate full system behavior
- Test at the lowest possible level for speed and precision

**Testability as Justification for Refactoring:**
- Making code testable is sufficient justification for refactoring
- If code cannot be unit-tested due to architectural constraints, refactor it
- Extract embedded logic (anonymous classes, lambdas) into testable components
- Favor composition and dependency injection over tightly coupled designs

**Example**: Anonymous iterators in Spark `mapPartitions` cannot be unit-tested. Extract them into package-private classes with clear contracts, enabling comprehensive unit tests without Spark infrastructure.

### 2. Test-Complete Development

**Non-Negotiable Rule: Every production code change MUST have corresponding tests**

**Test-First is the default. Test-After requires ALL of these:**

- [ ] <10 lines of production code
- [ ] Single execution path (no conditionals or loops)
- [ ] No string/collection manipulation
- [ ] No type/name resolution
- [ ] Obvious bug fix with known solution
- [ ] Can enumerate 3+ edge cases right now

**If ANY checkbox is unchecked → Use Test-First**

**Test-After is a privilege earned by simplicity, not a default.**

**Why Test-First for "straightforward" code:**
- Forces edge case enumeration during RED phase
- Reveals incorrect assumptions before implementation
- Prevents writing tests that confirm bias
- Evidence: past work has generated dozens of review-round issues from test-after on code that
  looked "simple" at the time

**When you think "test-after is fine here":**
- This is when you most need test-first
- Show the checklist to user
- Get approval for test-after override

**Required: RED-GREEN-REFACTOR (when test-first):**
- RED: Write failing test, verify it fails for the right reason
- GREEN: Minimal code to pass
- REFACTOR: **NEVER skip** - extract methods, apply SOLID, improve naming

**Required: IMPLEMENT-TEST-REFACTOR (when test-after):**
- IMPLEMENT: Write production code
- TEST: Write comprehensive tests covering happy path + edge cases
- REFACTOR: **NEVER skip** - improve both production and test code

**Mandatory Test Coverage:**
- Happy path (expected inputs/outputs)
- Edge cases (boundary conditions, empty/null inputs)
- Error paths (invalid inputs, exceptions)
- Regression coverage for bugs
- Data integrity checks

**Verification Checkpoint (ALWAYS):**
Before marking work complete, verify:
- [ ] All production code changes have tests
- [ ] Tests cover happy path + edge cases + errors
- [ ] Tests are clear and maintainable ("moist" principle)
- [ ] All tests pass (old + new)
- [ ] Code is refactored (production + tests)

**Test Quality:**
- Tests should be clear, readable, and maintainable
- Each test should test one thing
- Test names describe behavior, not implementation
- Use Given-When-Then or Arrange-Act-Assert patterns

**Relentless Refactoring:**
- Refactor immediately after GREEN/TEST phase, not "later"
- Multiple refactoring passes are normal and encouraged
- Ask: "Can this be clearer? Simpler? More maintainable?"
- Extract methods to give names to concepts
- Each method should do ONE thing at ONE level of abstraction
- If a method needs a comment to explain what it does, extract it into a well-named method instead
- Code should read like well-written prose

### 3. DRY vs "Moist" Principles

**Production Code: DRY (Don't Repeat Yourself)**
- Eliminate duplication ruthlessly
- Extract common logic into reusable functions/classes
- Use abstraction appropriately
- Shared constants, utilities, and helpers

**Test Code: "Moist" (Mostly Optimized for Immediate Simplicity in Tests)**
- **Clarity > Conciseness** in tests
- Duplication is acceptable if it improves readability
- Inline setup in tests if it makes intent clearer
- Each test should be independently understandable
- Avoid excessive abstraction that obscures test intent

**Examples of "Moist" Tests:**

```java
// ✅ GOOD: Clear intent, even with some duplication
@Test
void shouldRejectNegativeFutureBatchSize() {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, -1));
}

@Test
void shouldRejectZeroFutureBatchSize() {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, 0));
}

// ❌ AVOID: DRY in tests obscures what's being tested
@ParameterizedTest
@ValueSource(ints = {-1, 0})
void shouldRejectInvalidBatchSize(int batchSize) {
    assertThrows(IllegalArgumentException.class,
        () -> new SlsBIClientConfig(true, batchSize));
}
// ^ Harder to see which specific values are invalid
```

### 4. SOLID Principles

**S - Single Responsibility Principle**
- Each class should have one reason to change
- One class, one job
- Example: `FutureTracker` tracks futures; `SlsBIProducer` produces messages

**O - Open/Closed Principle**
- Open for extension, closed for modification
- Use configuration objects, strategy patterns
- Example: `SlsBIClientConfig` allows extension without changing constructor

**L - Liskov Substitution Principle**
- Subtypes must be substitutable for base types
- Interface contracts must be honored
- Deprecated methods should maintain behavior

**I - Interface Segregation Principle**
- Clients shouldn't depend on interfaces they don't use
- Small, focused interfaces
- Example: Separate `SlsBIClient` from `SlsBIProducer`

**D - Dependency Inversion Principle**
- Depend on abstractions, not concretions
- High-level modules shouldn't depend on low-level modules
- Example: `client` module doesn't depend on `client-starter`

## TDD Workflow Examples

### Example 1: New Feature

```bash
# 1. Write failing test
@Test
void shouldTrackFutureAndFlushWhenBatchSizeReached() {
    // RED: This test will fail because feature doesn't exist
    FutureTracker tracker = new FutureTracker(2, logger);
    tracker.track(future1, "ctx1");
    tracker.track(future2, "ctx2");
    // Should auto-flush here...
    assertEquals(0, tracker.getPendingCount());
}

# 2. Run test - it fails ✓
# 3. Implement minimal code to make it pass
# 4. Run test - it passes ✓
# 5. Refactor if needed
# 6. Run test - still passes ✓
```

### Example 2: Bug Fix

```bash
# 1. Write test that reproduces the bug
@Test
void shouldHandleNullFutureGracefully() {
    // RED: This test fails (NPE or similar)
    FutureTracker tracker = new FutureTracker(10, logger);
    assertDoesNotThrow(() -> tracker.track(null, "context"));
}

# 2. Fix the bug
# 3. Test passes
# 4. Verify old tests still pass (regression check)
```

### Example 3: Pre-Commit Validation (MANDATORY - ALWAYS)

```bash
# After all tests pass, BEFORE committing to git
mvn clean compile test -pl <module>

# Review output for:
# 1. Compilation: BUILD SUCCESS ✓
# 2. Tests: X/X passing ✓
# 3. Warnings: Review and fix CRITICAL ones

# 🔴 CRITICAL warnings (MUST fix before commit):
# - IntLongMath (integer overflow bugs)
# - DefaultCharset (platform-dependent behavior - always use UTF-8)
# - UnusedVariable (dead code)
# - MissingOverride (contract violations)

# 🟡 MODERATE warnings (SHOULD fix):
# - ClassCanBeStatic (performance/memory)
# - Unused imports/parameters

# 🟢 LOW priority (can defer):
# - MissingSummary (Javadoc style)
# - UnnecessaryParentheses (code style)

# ⚪ IGNORE (third-party):
# - Spark/LZ4/dependency warnings

# Fix critical warnings → Re-run build → Clean build → Commit
```

## Code Review Checklist

**When reviewing code (or when I should flag issues):**

- [ ] Are there tests for new functionality?
- [ ] Do tests follow "moist" principle (clear over clever)?
- [ ] Is production code DRY?
- [ ] Does design follow SOLID principles?
- [ ] Is module dependency direction correct?
- [ ] Are abstractions at the right level?
- [ ] Are error cases tested?
- [ ] Is the code self-documenting?

**Reviewing a PR: review locally, on the PR's actual head branch.** Fetch the clone and check out
the PR head (in a worktree if the clone has other work) before reading full files or running
scip/codeql, and confirm `git log -1` matches the PR's latest SHA. Check any claim about code
outside the diff against that checkout, never against a clone sitting on the default branch or
behind `origin`.
- **Why:** on java-stack-identity#717 (2026-10-07) the located clone was on `master` and behind by
  a merged PR. A review comment said an endpoint still put a token in the URL and tagged a
  teammate about it; it had to be retracted. `golden-pr:review`'s preflight only *locates* a clone
  — it does not fetch or check out the PR branch. A CodeQL database downloaded from CI reflects
  the default branch too, so PR-specific questions need a local build or a direct read.

### PR Review Issue Patterns

Review lenses applied in parallel by adversarial-review agents — some heuristic-based (specific
patterns to check), some judgment-based (holistic reading). Full class definitions, examples, and
update protocol: `~/.claude/copilot-review-patterns.md` (fix at the source, not inline). Bundled
snapshot: `plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md`.

**When to use**: Run `/satori:adversarial-review` (invoked automatically by `/satori:pre-pr-audit`
at rounds=3 and `/satori:address-pr-issues` at rounds=1) for a parallel sweep across all lenses
before opening a PR or pushing a fix round.

**When to update**: After every review round — refine the matching class's heuristics when the
issue reveals a new angle; add a new class when the finding surfaces a gap no existing lens would
have caught. Update protocol and "new class" checklist live in `~/.claude/copilot-review-patterns.md`.
After updating, refresh the bundled snapshot:
```bash
cp ~/.claude/copilot-review-patterns.md \
  ~/github/satoris-claude-config/plugins/satori/skills/adversarial-review/references/copilot-review-patterns.md
```

## Writing for Humans: Short-Form Artifacts

**Scope**: artifacts a person reads start-to-finish in one sitting — PR descriptions, Jira tickets,
Confluence pages, release notes, changelog entries, incident write-ups, PR review replies.

**Not in scope.** These are read by lookup, by a machine, or under diagnostic pressure, and none of
them get shorter:

- **Agent-resumed artifacts** — everything under `~/.claude/handoff/` (including `-PROGRESS.md`
  docs), `/satori:continue` continuation docs, audit manifests, PR-state workspace JSON,
  agent-to-agent contracts, and the word-budgeted Intent Brief. In these, an explicit "none yet" is
  required content, not a placeholder to trim.
- **Test code, code comments, and Javadoc** — DRY vs "Moist" and the Refactoring Checklist govern
  there; "Clarity > Conciseness" still holds.
- **Log, exception, and operator-facing error strings** — these optimize for diagnosis, not brevity
  (see the Operator Observability lens in `copilot-review-patterns.md`).
- **SKILL.md, README, and spec/reference documents** — reference material, consulted by lookup
  rather than read start-to-finish.

**Universal rules, whatever the artifact:**

- **Audience test**: write for a person who was not in this conversation. If a sentence exists to
  help an LLM re-derive context rather than to help a person understand the change, cut it from
  here — and route it (below) rather than delete it.
- **No process narration**: skip "I checked A, then B, then realized C" unless a specific dead end
  is itself a decision the reader needs.
- **No restating metadata**: the title, linked ticket, and diff are already on screen.
- **State confidence once**, in plain language — "confirmed via X" or "likely — worth checking Y".
  No stacked hedging.
- **Proportional length**: a typo, dep bump, or config tweak gets 1–2 sentences, not a filled-out
  template. A PR description is not a design doc; a Jira ticket is not an investigation log.

**These rules never override an existing obligation:**

- **Mandated disclosures.** Proportional length never removes content another skill marks MUST or
  verbatim for that artifact: Known Limitations, accepted-risk findings, and coverage gaps appear
  in full in the PR description even for a one-sentence change. Omission is a claim it was
  addressed.
- **Verbatim blocks are copied, not rewritten.** If such a block reads badly, fix it at its source
  in the round summary before it is copied — never by editing it in the PR description.
- **A review reply's disposition is payload, not metadata.** The prefix (Fixed / Won't fix /
  Already decided) and its cited commit, round, or reason are the substance of the reply; never cut
  them under the no-restating-metadata rule.
- **A skill's own scale-to-situation rule wins.** This section authorizes compressing prose, never
  skipping an accountability step.

**Default shape for defect/change artifacts** (bug tickets, PR descriptions, incident write-ups):

1. **Problem**, from the reader's vantage point — what a real user sees or experiences. Lead with
   symptom and impact, not internals.
2. **Brief technical analysis** — root cause and the key decision points, only enough for the
   reader to trust the conclusion.
3. **Solution** — enough detail that someone else could implement or verify it.
4. **Summary** — optional, only if the artifact is long enough to need one.

**Other artifact kinds keep their native shape**: feature/story ticket = need → outcome →
acceptance criteria; ADR = context → decision → consequences; runbook = purpose → content; release
notes = terse bullets, no analysis section.

**Where a skill already owns an artifact's template, that template wins on structure and this
section governs voice** — `/golden-pr:create` for PR descriptions. For PR review replies,
`address-pr-issues`' Reply Tone contract and reply templates control; this section adds only the
audience test and the no-narration and no-stacked-hedging rules on top.

### Context Routing

Compressing an artifact for a human does not discard context; it files it where its actual reader
will look. Every rule above assumes the cut material lands somewhere:

| Context being cut | Goes to |
|---|---|
| Change-level rationale that outlives the PR but doesn't warrant a handoff doc | **Commit message body** — travels with the change forever; `git log`/`git blame` are the authoritative lookup path |
| Resumable working state — what's done, what's next, dead ends, verbatim next action | **Handoff or `/satori:continue` doc** — verbose by design |
| Durable cross-session facts — surprising constraints, validated approaches, gotchas | **Auto-memory** |
| The full investigation path a reviewer doesn't need but the issue's history should keep | **A comment on the linked ticket**, not the PR body |

Terseness that strands context is a regression, not an improvement. Wanting to keep detail in a PR
description "so a future agent can reason about it" is the signal to write a commit body or a
handoff doc — not to pad the PR.

**Remember**: the human artifact and the agent artifact are different documents with different
readers. One document trying to serve both serves neither.

## Decision Override Protocol

### When I Think Something is "Straightforward"

**⚠️ STOP. This is a red flag.**

"Straightforward" is the word I use before:
- Missing edge cases
- Skipping test-first
- Avoiding adversarial review
- Writing tests that confirm my bias instead of challenging it

Repeatedly, on past work, the tasks that took the most review rounds to converge were the ones
first described as straightforward, obvious, or simple — string/prefix handling, name matching,
and type resolution especially. Treat the word itself as a stop sign, not a status report.

### Protocol When Tempted to Skip Process

1. **Re-read the complexity assessment questions** from the `satori:address-pr-issues` skill
2. **Complete the checklist** - don't skip it
3. **Show my reasoning to user**: 
   ```
   This seems straightforward to me because [reason].
   However, it involves [risk factors].
   Recommend: [process step]
   Proceed with override? (yes/no)
   ```
4. **If user says "use the process"** - use it without debate

### Remember

- Test-after confirms my understanding, doesn't challenge it
- Test-first forces me to enumerate edge cases upfront
- Adversarial review questions assumptions I didn't know I had
- **Default to process, not judgment**

### Process Decision Defaults

**When in doubt:**
- Use test-first (not test-after)
- Spawn adversarial reviewer (not skip)
- Use `/satori:xp-pair` (not solo) — for production code; doc- or prose-only changes don't need it
- Run `/satori:pre-pr-audit` (before every PR)

Prefer false positives (extra process) over false negatives (missed bugs).

## Anti-Patterns to Avoid

### Test Smells
- ❌ Tests that test implementation details, not behavior
- ❌ Tests that depend on execution order
- ❌ Tests that share mutable state
- ❌ Tests with mysterious setup in @BeforeEach that obscures intent
- ❌ Tests that require deep knowledge of mocks to understand

### Production Code Smells
- ❌ God classes (violates SRP)
- ❌ Primitive obsession (use value objects)
- ❌ Feature envy (method uses another class's data more than its own)
- ❌ Data clumps (group related primitives into objects)
- ❌ Long parameter lists (use configuration objects)

## Refactoring Checklist

**After achieving GREEN/TEST phase, always refactor using this checklist:**

### Code Structure
- [ ] Is each method doing ONE thing at ONE level of abstraction?
- [ ] Are methods short (<20 lines ideally, <50 lines maximum)?
- [ ] Can any complex logic be extracted into well-named helper methods? (A cohesive block past
      ~10-15 lines wants its own name — that's the extraction trigger; the 20/50 figures above are
      the finished method's total length. Different measures, not competing limits.)
- [ ] Are there any magic numbers/strings that should be constants?
- [ ] Is there duplicated code that can be extracted?

### Naming
- [ ] Do names reveal intent without needing comments?
- [ ] Are variables/methods/classes named for what they are, not how they work?
- [ ] Can you remove comments by improving names?
- [ ] Are abbreviations avoided unless universally understood?

### SOLID Principles
- [ ] Single Responsibility: Does each class/method have one reason to change?
- [ ] Open/Closed: Can behavior be extended without modification?
- [ ] Liskov Substitution: Do subtypes honor their contracts?
- [ ] Interface Segregation: Are interfaces minimal and focused?
- [ ] Dependency Inversion: Do high-level modules depend on abstractions?

### Dependencies & Coupling
- [ ] Are dependencies explicit (constructor injection preferred)?
- [ ] Is coupling loose (depend on interfaces, not implementations)?
- [ ] Can any concrete dependencies be replaced with abstractions?

### Documentation
- [ ] Is non-obvious code documented with WHY, not WHAT?
- [ ] Are public APIs documented with Javadoc?
- [ ] Can any documentation be replaced with better code?

### Test Impact
- [ ] Do tests still pass? (run after each refactoring step)
- [ ] Are tests still readable and maintainable?
- [ ] Do test names still describe behavior accurately?

**Remember**: Refactoring should happen in small steps with tests passing after each step. Commit frequently during refactoring to create safe restore points.

## When to Break the Rules

**Pragmatism over Purism:**

1. **Legacy Code**: When working with untested legacy code, focus on characterization tests first
2. **Performance**: In rare cases, DRY in production might be sacrificed for performance (document why!)
3. **Prototyping**: Quick spikes can skip TDD, but rewrite with tests before committing
4. **Generated Code**: Don't test generated code (but test the generator)

## Tools and Practices

**Testing Tools (Java/Spring):**
- JUnit 5 for test framework
- Mockito for mocking (use sparingly - prefer real objects when possible)
  - **Argument Matcher Best Practice**: Prefer concrete values over matchers in `verify()` and `when()` calls
  - Only use argument matchers (`eq()`, `any()`, `anyString()`, etc.) when necessary
  - If ANY parameter needs a matcher, ALL parameters must use matchers (Mockito requirement)
  - Example:
    ```java
    // ✅ GOOD: Use concrete values when possible
    verify(mockService).processRecord("record-123", ElementType.RECORD);

    // ✅ ACCEPTABLE: All parameters use matchers when one requires it
    verify(mockService).processRecord(anyString(), eq(ElementType.RECORD));

    // ❌ AVOID: Unnecessary use of matchers
    verify(mockService).processRecord(eq("record-123"), eq(ElementType.RECORD));
    ```
- AssertJ for fluent assertions
- TestContainers for integration tests
- ArchUnit for architecture tests (verify SOLID principles)

**Best Practices:**
- Test package structure mirrors source package structure
- Test class names: `<ClassName>Test` or `<ClassName>Should`
- Test method names: `should<ExpectedBehavior>When<Condition>()` or `<methodName>_<scenario>_<expectedResult>()`
- Use descriptive variable names in tests
- Prefer composition over inheritance in production code
- Prefer immutability (final fields, record classes)

**Test Organization - IMPORTANT:**
- **ALWAYS add tests to existing test classes BEFORE creating new ones**
  - If testing `FooClass`, add tests to existing `FooClassTest`
  - Only create new test classes for NEW production classes
  - Avoid proliferation of test classes (e.g., `FooClassConstructorTest`, `FooClassMethodTest`)
  - Keep related tests together - easier to find and maintain
- **Example**:
  ```
  ✅ GOOD: Add constructor tests to existing SlsBIClientImplTest
  ❌ AVOID: Create separate SlsBIClientImplConstructorTest
  ```

## Examples from sls-bi-worker

### Good Test-After Example: CSV Validation

```java
// Straightforward validation - used test-after approach

// Step 1: IMPLEMENT - Add comma counting validation
int commaCount = 0;
for (int i = 0; i < jsonStart; i++) {
    if (line.charAt(i) == ',') {
        commaCount++;
    }
}
if (commaCount < 3) {
    logMalformedLine("Template line has insufficient columns...");
    return null;
}

// Step 2: TEST - Comprehensive test coverage
@Test
void shouldSkipLineWithInsufficientColumns() {
    String csvLine = "1369,{\"id\":\"test\"}"; // Only 2 columns
    Map<String, String[]> result = reader.readTemplates(prefix);
    assertThat(result.get("1369")).isEmpty();
}

// Step 3: REFACTOR - (minimal needed - already clear)
```

## Notes to Claude Code

Everything above applies when working on fransonsr's projects. This section is not a recap of it —
it holds only the pointers worth having at the end of the file, plus the two clarifications that
live nowhere else.

1. **Tests are non-negotiable, and "done" has a definition.** Core Principles §2 — the rule itself,
   the Mandatory Test Coverage list, and the Verification Checkpoint to run before calling any work
   complete.

2. **Test-first vs. test-after is decided by the checklist, not by how the code feels.** Core
   Principles §2. Test-after requires *all six* boxes; a single unchecked box means test-first. If
   the word "straightforward" is doing the deciding, see the Decision Override Protocol instead.

3. **Flag SOLID violations, with the explanation attached.** Core Principles §4 for the principles;
   the Refactoring Checklist's SOLID sub-list for the questions to read code against.

4. **The two method-length numbers measure different things.** Extract a cohesive block of logic
   into its own named method once it passes ~10-15 lines; a finished method's *total* length should
   still land under 20 lines ideally, 50 maximum. The extraction trigger and the length ceiling are
   not competing limits (Refactoring Checklist → Code Structure).

5. **Build-environment changes need unscoped validation.** The Pre-Commit Validation recipe in TDD
   Workflow Examples → Example 3 runs `mvn clean compile test -pl <module>`; when the change touches
   a POM, a dependency, or build configuration, drop the `-pl` scope and validate the full build.

6. **Already stated in full elsewhere** — go there rather than working from a summary: relentless
   refactoring as part of the cycle (Core Principles §2); don't over-abstract tests (§3, "Moist");
   long constructor parameter lists → config objects (Anti-Patterns → Production Code Smells);
   module dependency direction (Code Review Checklist); immutability and value objects (Tools and
   Practices → Best Practices); self-documenting code, comments explaining WHY not WHAT
   (Refactoring Checklist → Naming, Documentation).

## References

- **TDD**: Kent Beck's "Test Driven Development: By Example"
- **SOLID**: Robert C. Martin's "Clean Code" and "Clean Architecture"
- **DRY**: Andy Hunt & Dave Thomas's "The Pragmatic Programmer"
- **Test Quality**: "Growing Object-Oriented Software, Guided by Tests" by Freeman & Pryce

---

**Remember**: These are guidelines, not absolute laws. Use judgment. The goal is maintainable, correct, well-tested code that communicates intent clearly.
