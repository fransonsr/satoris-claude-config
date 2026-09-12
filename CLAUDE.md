# Coding Standards and Principles

**Owner**: fransonsr
**Last Updated**: 2026-09-03
**Scope**: All projects in this environment

## Environment Configuration

**Operating System**: WSL (Windows Subsystem for Linux)

## Model Access & Selection

**License:** Claude Enterprise (migrated off Amazon Bedrock, June 2026). All current
Claude models are authorized — Fable 5, Opus 5, Sonnet 5, Haiku 4.5, etc. The old Bedrock-era
restriction pinning agents to Opus 4.6 (and the "Opus 4.7 causes auth errors" / retry-loop
issue) no longer applies.

**Enterprise rate limits:** there are 5-hour and weekly token usage limits. Spend the budget
deliberately — heavier model tiers and higher effort levels both draw the budget down faster;
Fable runs roughly 2x Opus's per-token cost, and xhigh/max effort spends more than low/medium at
any tier.

**Default model:** `opusplan` (set in `~/.claude/settings.json`) — Opus for plan mode, Sonnet
for execution.

**When spawning agents:** no need to pin a model — let agents inherit the session model unless a
task warrants otherwise.

**Verified 2026-08-14, re-verified 2026-08-29 — re-check before trusting if stale:** claims about
which model/tier is currently strongest age in weeks, not months. The 2026-08-29 check confirmed
the picture below still holds, with one refinement: the split that holds up is
**difficulty/stakes-shaped, not domain-shaped**. It is not "Opus for prose, Fable for code" —
Opus 5 leads or ties Fable 5 on nearly every published coding/agentic benchmark (e.g. Frontier-Bench
43.3% vs 33.7%, agentic terminal coding 43% vs 33%) at half Fable's per-token price, with Fable's
only lead (SWE-bench Pro, 80.0 vs 79.2) under a point — within noise. One direct writing comparison
even found Fable's raw prose the sharpest of the three models tested. Re-verify via web search
before a consequential model-selection call if this note looks old again.

- **Haiku** is the tier for high-volume, mechanical, low-judgment work: simple lookups, log/data
  parsing, classification, boilerplate edits repeated across many files — especially the individual
  fan-out legs of a `parallel()`/`pipeline()` call in the `Workflow` tool, where a dozen cheap agents
  running concurrently beats one expensive agent running serially. The bar for reaching for it is
  "is this task simple," not "is this task urgent." Three figures corrected 2026-08-30, because the
  originals silently drifted as Sonnet's price and version moved:
  - **Cost: about half Sonnet 5's, not a third.** Haiku 4.5 is $1/$5 per 1M in/out; Sonnet 5 is
    $2/$10. The "a third" figure was true against Sonnet 4.6 ($3/$15) and was overtaken by Sonnet
    5's price. Sonnet 5 is the tier actually in play here, since `opusplan` runs Sonnet for
    execution.
  - **Quality: Anthropic's published claim was that Haiku 4.5 matches *Sonnet 4*** — not the
    current Sonnet. Against later Sonnets there is a real gap (Haiku 4.5 scores 73.3% on SWE-bench
    Verified vs Sonnet 4.6's 79.6%, and Sonnet 5 is ahead of 4.6). Treat "~90% of Sonnet's quality"
    as unverified against Sonnet 5.
  - **Context: Haiku 4.5 has a 200K window; Opus/Sonnet/Fable have 1M.** This bites exactly the
    workloads named above — log/data parsing and wide `parallel()` fan-out are the cases most
    likely to exceed 200K, where a Haiku leg hits a wall a Sonnet leg would not.

  **This applies to a plain `Agent` call too, not just Workflow's fan-out** — `Workflow` itself
  requires the user to have explicitly opted into multi-agent orchestration, so it won't fire just
  because a task would benefit. When spawning any bounded, mechanical, low-judgment subagent
  outside Workflow — a single lookup, a repeated boilerplate edit across N files, a
  classification/log-parsing pass — pin `model="haiku"` rather than letting it inherit. (And plenty
  of simple lookups don't need a subagent at all — doing it inline with Read/Grep/LSP is often more
  efficient than spawning any agent, Haiku included.)
- **Sonnet** covers routine search/exploration/mechanical work that still needs real judgment —
  the current session default, and the right choice when a task doesn't clearly call for a tier
  above or below it.
- **Opus** is the default ceiling for hard reasoning — pin it for genuinely complex agentic coding
  or enterprise-grade work.
- **Fable is not "a smarter Opus," and not "the code-reasoning model."** Don't pin Fable expecting
  better results on typical dev work, and don't route to it by domain (code vs. prose) — see the
  Verified note above. Its actual edge is narrow and behavioral: genuinely multi-day autonomous
  runs, dense technical-image/vision work, specialized long-horizon scientific research, and — by
  the same "hardest reasoning, expensive failure" logic — a single narrowly-scoped synthesis or
  deep-dive task after cheaper models have already had multiple attempts and haven't converged
  (e.g. `/satori:adversarial-review`'s Phase D fix-planning pass already reaches for
  `model: 'fable'` for exactly this reason; its round-cap "NOT converged — targeted deep-dive"
  escalation is the same shape and a natural candidate to extend this to). Reach for it only when
  a task matches one of those, not as a general escalation path from Opus.
- **Effort level** is a separate, cheaper-to-try dial than switching model tier: `low`/`medium`/
  `high`/`xhigh`/`max`. **This environment deliberately runs `xhigh` globally** —
  `"effortLevel": "xhigh"` in `~/.claude/settings.json` — so the effective baseline is `xhigh`, not
  the `high` default. That is a chosen operating point, not drift: don't "correct" it back to
  `high`, and read the rate-limit paragraph above with it in mind, since `xhigh` is the reason the
  budget draws down faster than a stock setup.
  - **Three surfaces set it, and they are not equivalent.** Session-wide:
    `effortLevel` in `settings.json`, the `/effort` command, or `CLAUDE_CODE_EFFORT_LEVEL`
    (`max` is session-only, not settable in `settings.json`). Per-agent: the `Workflow` tool's
    `effort` option. The plain `Agent` tool exposes no `effort`, so per-*call* effort really is
    Workflow-only — but effort itself is always adjustable, which the earlier wording got wrong.
  - **Gotchas** (open Claude Code issues, verified 2026-08-30): `effortLevel` is not always applied
    at startup, and `/model` can silently overwrite it. Confirm with `/effort` rather than trusting
    the settings file.
  - Dropping to `low`/`medium` for genuinely routine work still saves meaningfully with no
    perceptible quality loss, and raising effort is still worth trying before reaching for a
    pricier model.
- **A common combined pattern**: Sonnet or Opus decomposes a problem and orchestrates, while many
  Haiku instances run the resulting subtasks in parallel — Anthropic's own recommended pairing for
  Haiku, and a natural fit for this environment's `Workflow` `pipeline()`/`parallel()` helpers. If
  you spot a bulk/fleet-shaped task up front (checking N independent things), saying "use a
  workflow" gets the Haiku fan-out payoff directly rather than relying on it being inferred —
  `Workflow` won't self-trigger on task shape alone.
- **Reading usage stats**: don't judge Haiku/Fable usage by raw percentage alone. Fable staying
  near-zero is expected and healthy given how narrow its edge is. The more useful signal is whether
  Sonnet/Opus subagents are being spawned for tasks that were clearly mechanical enough for Haiku —
  that's the actual sign this guidance isn't being followed, not a low Fable number.

Pin a model only when the task clearly calls for it:
```
Agent(model="opus", ...)     # reserve for hard reasoning; omit to inherit
Agent(model="haiku", ...)    # high-volume, mechanical, or parallel-fan-out work — inside or outside Workflow
```

### Fable-Specific Prompting Patterns

Fable's behavior differs enough from Opus/Sonnet that prompts tuned for those models tend to under-
or over-shoot on it (reasoning-in-response refusals, over-surveying, unrequested actions, rare
early-stopping). The full set of behavioral tuning patterns from Anthropic's Fable prompting guide
lives in `~/.claude/fable-prompting-patterns.md`.

**When to use**: read that file whenever a task actually pins Fable — which, per the tier guidance
above, should be rare. It is not needed for Opus/Sonnet/Haiku work.

**Path Mappings**:
- WSL home from Windows: `\\wsl.localhost\Ubuntu\home\fransonsr`
- Use this path format to open files in Windows browser or applications
- Example: `file:///\\wsl.localhost\Ubuntu\home\fransonsr\file.md`
- `~/.claude/CLAUDE.md` is itself a symlink → `~/github/satoris-claude-config/CLAUDE.md` (this
  file, in this repo). Tools that refuse to write through symlinks (e.g. Claude Code's Edit tool)
  need the resolved target path passed explicitly — use `readlink -f ~/.claude/CLAUDE.md` to get it.

**Installed Tools**:
- `wslu` - WSL utilities package installed (v3.2.3)
  - Use `wslview <file>` to open files in Windows default applications
  - Works like `xdg-open` but WSL-aware (opens PDFs, URLs, etc. in Windows)
  - **Note**: Original `wslview` uses old WSL1 paths (`\\wsl$`) which don't work in WSL2
  - **Fix**: Created `~/bin/wslview2` wrapper that uses correct WSL2 paths (`\\wsl.localhost`)
  - Aliased `wslview` → `wslview2` in `~/.bashrc` so it "just works"
- `session-generator` - FamilySearch (not AWS) access-token CLI (`~/github/session-generator`,
  installed on PATH via `~/.local/bin`)
  - Get a bare token: `session-generator -p -u <username> -q | grep "^prod:" | cut -d: -f3`
    (swap `-p`/`prod:` for `-b`/`beta:` or `-i`/`integration:` for other environments)
  - **Gotcha**: `-q` (quiet mode) prints `env:user:token` per line, NOT a bare token — capturing
    the raw line as a bearer credential produces a malformed token that fails downstream auth
    (e.g. CAS) with the same generic error a garbage string would, easy to misdiagnose as a real
    outage rather than a parsing mistake
- **SonarQube**: server URL and auth token are already present in the environment — applies to all
  `fs-eng` repositories. Don't report "no Sonar token"/"can't authenticate" as a blocker; the
  credential is there, look for it (e.g. via the `sonarqube-cli`/`sonar-*` skills' normal auth path)
  rather than assuming it's missing. `SONARQUBE_CLI_TOKEN` lives in GNOME Keyring (`secret-tool
  lookup service sonarqube-cli username fransonsr`), exported in `~/.bashrc` *above* the
  interactive-shell guard so non-interactive/agent shells get it too (previously it lived after the
  guard and silently went missing for spawned-agent shells specifically — fixed 2026-07-29).
  **Gotcha**: `export VAR=$(secret-tool lookup ...)` only evaluates once, at shell startup — after
  rotating the token in the keyring, any shell/session already running (including an in-progress
  Claude Code session) keeps the stale value until it gets a fresh one. If auth fails right after a
  known-good rotation, suspect a stale shell before suspecting the new token.
- **SonarQube MCP is a single shared HTTP container, not one-per-session** (fixed 2026-09-12,
  see `[[aoe-sonarqube-mcp-shared-http-server]]` in memory): the global `mcpServers.sonarqube`
  entry in `~/.claude.json` points at `http://127.0.0.1:8080/mcp` (container `sonarqube-mcp`,
  `docker run -d --restart unless-stopped`, mounts `~/github` read-only). Because one server now
  serves every repo, tools no longer get an auto-detected project key baked in per session — pass
  `projectKey` explicitly on every project-scoped `mcp__sonarqube__*` call. Resolve it in this
  order before calling: (1) `sonar.projectKey=` in the repo's `sonar-project.properties`; (2)
  `projectKey` in `.sonarlint/connectedMode.json`; (3) neither exists → call
  `search_my_sonarqube_projects` with a query derived from the repo name. Resolve once per session
  and reuse it rather than re-resolving on every tool call.
- **`gh` CLI, verifying a just-pushed PR**: `gh pr diff <n>` and plain `gh pr view <n>` can serve
  stale/cached content immediately after a push — confirmed twice in one session, each time reading
  as "the agent hasn't actually pushed yet" when it had. Use the forms that hit the API directly
  instead: `gh pr view <n> --json body --jq .body` for the description; for branch HEAD / file
  content, `gh api repos/OWNER/REPO/git/ref/heads/<branch> --jq .object.sha` and
  `gh api "repos/OWNER/REPO/contents/<path>?ref=<branch>" --jq .content | base64 -d`. When a
  reported push doesn't show up in a diff/view check, re-check with these before concluding the
  work wasn't done.

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
- **A separate risk, orthogonal to the file-routing guidance above**: if the dispatching session
  itself is aoe-managed, dispatching `Agent`/`Workflow` subagents risks aoe mis-tracking the
  *coordinator's own* Claude Code transcript — not a file-routing problem, a session-identity one.
  Confirmed live against this exact class of session: aoe's live-observation heuristic picked a
  spent subagent's leftover transcript as "fresher" than the coordinator's real one and silently
  reattached the coordinator to it. See
  `plugins/satori/skills/handoff/references/aoe-session-collision.md` for the confirmed mechanism,
  what does and doesn't mitigate it, and why `aoe session set-session-id` does not help here.
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
  **Hard exclusion: never terminate an aoe-managed session, by any mechanism.** The persistent,
  user-visible, tmux-backed sessions in the aoe dashboard are not in scope for this rule at
  all — not via `TaskStop`, not via aoe's own commands (`aoe session archive`, `aoe remove`), not
  by killing the underlying tmux pane/process. Terminating one of those is the user's call alone,
  never an agent's, regardless of how idle or "done" it looks. This bullet governs only the
  ephemeral subagents/teammates a session spawns for its own work — aoe's top-level session fleet
  is never a target of it.
  - **Why:** observed live — a coordinator finishing with a spawned subagent or team sent a
    plain-text stand-down instruction instead of `TaskStop`, leaving the agent idle-but-alive and
    consuming resources indefinitely instead of actually terminating.

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

## Development Tools

### LSP (Language Server Protocol) Integration

**Status**: ✅ Available for Python. **Default-first, not a fallback tried after grep**: whenever
a question is about a named symbol — where it's defined, everywhere it's called, a file's
structure, or whether a file has live errors — reach for LSP *before* grep/ripgrep, not only after
a grep-based attempt already came up short. Verified working in this environment 2026-08-29
(Python via `pyright-lsp`). **Java does not use this tool** — see "Java Code Navigation: scip, not
LSP" below for why and what to use instead.

**For Python specifically, this is a MUST, not a preference.** Pattern matching (grep/ripgrep)
against Python has repeatedly produced **false negatives** — real references silently missed, not
just noisy over-matches — because grep can't see semantics: it misses references split across
lines, inherited/overridden members, indirect calls through an interface or a differently-imported
alias, and any match whose surrounding tokens don't literally contain the search string. A false
negative here is worse than a false positive: it reports a symbol as unused, or a rename as
complete, when it isn't. An agent must use LSP instead of grep/ripgrep for symbol-level questions
(definition, references, structure, diagnostics) on Python files — not "prefer," not "reach for
first," but use it, full stop; grep is not an acceptable substitute even under time pressure.

**Supported Languages** (one shared `LSP` tool dispatches to whichever server matches the file
type — `ToolSearch(query="select:LSP")` loads it):
- Python (`pyright-lsp`) — confirmed working; this environment routes all Python symbol-level
  questions through it.
- Java (`jdtls-lsp`) remains registered as an LSP server here, but is **not** the recommended tool
  for Java anymore — it has a known, unfixed crash (see "Java Code Navigation" below). Don't reach
  for it via the `LSP` tool for Java; use the `scip:index` skill instead.
- **Available in the marketplace but NOT currently enabled** — `enabledPlugins` holds only the two
  above (`jdtls-lsp`, `pyright-lsp`), so these need enabling before they will do anything: C/C++
  (`clangd-lsp`), C# (`csharp-lsp`), Go (`gopls-lsp`), Kotlin (`kotlin-lsp`), Lua (`lua-lsp`), PHP
  (`php-lsp`), Ruby (`ruby-lsp`), Rust (`rust-analyzer-lsp`), Swift (`swift-lsp`),
  TypeScript/JavaScript (`typescript-lsp`). Verified 2026-08-29. This bullet previously read "Also
  enabled," which would lead an agent to reach for LSP on a Go or TypeScript file, get nothing, and
  conclude LSP is broken rather than not enabled for that language.
- **Bash/shell has no LSP server in this environment.** Use `shellcheck <file>` (installed at
  `/usr/bin/shellcheck`) for static analysis instead — it catches unused vars, quoting bugs, and
  unsafe patterns. It's a linter, not a language server, so there's no goToDefinition/
  findReferences equivalent for shell; grep remains the right tool for plain text search in
  scripts.

**When to Use LSP vs Other Tools** (Python; for Java see "Java Code Navigation" below):

| Task | Use LSP | Use grep/find | Use Read |
|------|---------|---------------|----------|
| Find all references to a symbol (Python) | ✅ LSP (accurate) | ❌ grep — false positives **and** false negatives (misses real, semantically-valid references) | ❌ |
| Go to definition | ✅ LSP (accurate) | ⚠️ grep (multiple matches) | ❌ |
| Find symbol in workspace | ✅ LSP (fast, accurate) | ⚠️ find + grep (slower) | ❌ |
| Understand file structure | ✅ LSP (symbols/outline) | ❌ | ⚠️ Read (must read whole file) |
| Get diagnostics/errors | ✅ LSP (real-time) | ❌ | ❌ |
| Type hierarchy/implementations | ✅ LSP (accurate) | ❌ grep (unreliable) | ❌ |
| Rename refactoring | ✅ LSP (safe) | ❌ grep — false negatives (misses cases, leaves stale references behind) | ❌ |
| Bash script static analysis | ❌ no bash LSP server | ⚠️ grep (pattern-only) | ❌ — use `shellcheck` |
| Search file contents (plain text, not a symbol) | ❌ | ✅ grep (faster) | ❌ |
| List directory contents | ❌ | ✅ find (better) | ❌ |
| Read specific lines | ❌ | ❌ | ✅ Read (best) |

**Best Practices**:
1. **For Python, use LSP instead of grep for symbol-level questions — this is required, not
   merely first-choice.** For any other supported language (once enabled), still load LSP before
   reaching for grep. If the task involves a named symbol rather than plain text, call
   `ToolSearch(query="select:LSP")` and use it as the first tool. **For Java, use the `scip:index`
   skill instead** — the `LSP` tool is not the path for Java symbol lookups in this environment.
2. **Use for navigation**: finding definitions, references, implementations.
3. **Use for refactoring**: renaming symbols across a project.
4. **Use for diagnostics**: getting compile/type errors before building.
5. **Only fall back to grep when**: the search is plain-text/pattern-based rather than a named
   symbol, or the file's language has no LSP server in this environment (bash — use `shellcheck`
   instead, per above). "LSP felt slower to reach for" is not a qualifying reason, and for Python,
   "grep already looked complete" is not one either — grep's false negatives look exactly like a
   clean result until LSP finds what it missed.

**Example Workflow** (matches the actual `LSP` tool schema: `operation` plus
`filePath`/`line`/`character`, or `query` for `workspaceSymbol`):
```markdown
# At start of coding session
Load LSP tool: ToolSearch(query="select:LSP")

# When exploring code
- Find where a symbol is defined: LSP(operation="goToDefinition", filePath="...", line=N, character=N)
- Find all usages: LSP(operation="findReferences", filePath="...", line=N, character=N)
- See file/class structure: LSP(operation="documentSymbol", filePath="path/to/file.py", line=1, character=1)
- Search by name across the workspace: LSP(operation="workspaceSymbol", query="methodName", filePath="...", line=1, character=1)
- Check for errors: diagnostics surface automatically as a system reminder after editing a file

# When making changes
- Before renaming: use findReferences to find every call site
- After changes: re-check diagnostics
- Final validation: run the build/test suite

# For bash scripts (no LSP server available)
- Static analysis: shellcheck path/to/script.sh
```

**Note**: LSP is a deferred tool - use ToolSearch to load it before first use in a session.

**Common Use Cases** (Python, via the `LSP` tool):

1. **Consistency Checking** (e.g., PR #6 Round 10):
   ```
   Instead of: grep -n "debug" src/
   Use: LSP(operation="findReferences", ...) on the specific symbol to find actual calls (not comments)
   ```

2. **Test Coverage Analysis** (e.g., PR #6 Round 13):
   ```
   Instead of: grep "setAbsolutePath" src/main/
   Use: LSP(operation="findReferences", ...) on setAbsolutePath to see all actual usages
   ```

3. **Refactoring Impact** (e.g., PR #6 Round 15):
   ```
   Before renaming totalFilesScanned → totalFilesWithFindings:
   - LSP(operation="findReferences", ...) on totalFilesScanned shows all locations
   - More reliable than grep (handles indirect references and aliasing)
   ```

### Java Code Navigation: scip, not LSP

**Java does not use the `LSP` tool.** `jdtls-lsp` (Claude Code's built-in Java language server)
has a known, unfixed crash: its Eclipse workspace doesn't shut down cleanly between Claude Code
sessions, so on the next startup it replays stale delta-tree state that references a Maven
`target/` file a routine `mvn clean` already removed, throwing `ObjectNotFoundException` and
crashing the server. The two upstream issues that map to this (no clean LSP-server shutdown/reuse
across sessions, no way to exclude build directories from file-watching) are real and open, but
both were closed by GitHub's stale-bot as `not_planned` — there is no upstream fix coming.

Use the **`scip:index` skill** instead: it manages a [SCIP](https://github.com/scip-code/scip)
index for the current repo — a precomputed, file-based index of definitions/references, built once
via `scip-java`, then queried without any live server process. Since there's no long-running
mutable server, there's nothing to accumulate corrupt state across sessions.

**This is a MUST for Java, the same way LSP is a MUST for Python** — the identical false-negative
risk from grep/ripgrep applies to Java too (missed references split across lines, inherited/
overridden members, aliased imports). Use `scip:index`'s `query` operation instead of grep for
symbol-level questions (definition, references) on Java files. `scip:index` does not cover file
structure or live diagnostics the way the `LSP` tool does for Python — read the file directly for
those.

```bash
SCRIPTS="${CLAUDE_PLUGIN_ROOT}/skills/index/scripts"   # the scip plugin's index skill

bash "$SCRIPTS/setup.sh"                                 # once per machine
bash "$SCRIPTS/index.sh"                                 # once per repo — a real build, not fast
bash "$SCRIPTS/query.sh" at path/to/File.java:LINE:COL   # go to definition / find references
bash "$SCRIPTS/query.sh" symbol "ClassName#methodName"   # find by name when you don't have a location
```

Full details, known constraints (Maven-validated only; Gradle auto-detection unverified; module-
scoping flags deliberately omitted from the default build), and troubleshooting: the `scip:index`
skill's own SKILL.md.

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
- Use `/satori:xp-pair` (not solo)
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

6. **Symbol-level lookups always go through a dedicated tool, never grep — but Java and Python
   use different ones, and neither is optional.** Development Tools → LSP (Python) and → Java Code
   Navigation: scip, not LSP. Pattern matching against both languages has repeatedly produced false
   negatives (real references silently missed, not just noisy over-matches). For Python, that means
   the `LSP` tool (`pyright-lsp`); for Java, it means the `scip:index` skill's `query` operation —
   `jdtls-lsp` has a known, unfixed crash and is not the path for Java anymore. For any other
   LSP-supported language, still load and use LSP before grep. Grep is the fallback for plain-text
   search or for bash, which has no LSP server — use `shellcheck` there instead.

7. **Already stated in full elsewhere** — go there rather than working from a summary: relentless
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
