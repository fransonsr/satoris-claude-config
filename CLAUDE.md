# Coding Standards and Principles — Work Environment

**Owner**: fransonsr
**Last Updated**: 2026-11-14
**Scope**: All projects in this (work) environment

This file holds the work-specific environment notes. The general standards — core principles,
testing, SOLID, review, writing, and working practices — live in `standards.md` in this repo and
are imported at the end of this file. The import uses a `~/` path, not a relative one: this file is
read through the `~/.claude/CLAUDE.md` symlink, and relative imports resolve from the link's
location, not this repo.

## Environment Configuration

**Operating System**: WSL (Windows Subsystem for Linux)

**Terminal links**: Windows Terminal (with tmux inside) auto-links only URLs visible as text.
Claude Code renders `[text](url)` as the label alone, so the link can't be clicked or copied.
When a reader needs to open a PR, issue, or page from terminal output, print the bare URL.

**Jira project key**: the Records Platform project key changed from `RS` to `RP` (noted 2026-10-19). Issue
numbers did not change: `RS-4849` is now `RP-4849`, the same issue (verified through the Atlassian API: both keys return
issue id 1520683, project `RP` "Records Platform"). Use `RP-` for new references, links and JQL (`project = RP`).
Older tickets, PRs, commits, docs, memories and handoff files still say `RS-`; read them as the same number. When a search
for an `RS-` reference finds nothing, retry with `RP-`, and the reverse. Other project keys seen alongside it (RD, RECMS,
DATAEX) were still in use on 2026-10-19; this note does not say whether any of them changed.

**Task tools (visual progress indicator)**: use `TaskCreate`/`TaskUpdate` on multi-step work so I can see
progress in the Claude Code UI: create the tasks up front, mark one `in_progress` when starting it and
`completed` when done. Skip them for trivial single-step requests. Claude Code 2.1.233 stopped offering these tools
on newer models (Opus 4.8, Sonnet 5, Fable 5 and later; 2.1.268 narrowed the default set further), so
`"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"` is set in the `env` block of `~/.claude/settings.json` (added 2026-10-27). The
tools are deferred: load them with `ToolSearch` (`select:TaskCreate,TaskUpdate,TaskList,TaskGet`) before first use.
If they are missing, check that env var and that the session started after it was set. If tracking starts costing
more than it is worth (token or limit drain, noise on small jobs), raise it for discussion rather than silently
dropping it.

## Model Access & Selection

**License:** Claude Enterprise (migrated off Amazon Bedrock, June 2026). All current
Claude models are authorized — Fable 5.1, Opus 5.5, Sonnet 5, Haiku 4.5, etc. (Sonnet 5.5 and
Haiku 5.5 were announced 2026-09-22 for "the coming weeks"). The old Bedrock-era
restriction pinning agents to Opus 4.6 (and the "Opus 4.7 causes auth errors" / retry-loop
issue) no longer applies.

**Enterprise rate limits:** there are 5-hour and weekly token usage limits. Spend the budget
deliberately — heavier model tiers and higher effort levels both draw the budget down faster;
Fable 5.1 runs 2.5x Opus 5.5's per-token list price ($10/$50 vs $4/$20 per 1M in/out), and
xhigh/max effort spends more than low/medium at any tier.

**Default model:** `opusplan` — Opus for plan mode, Sonnet for execution. An instance may be
pinned to another model on purpose. **Gotcha:** choosing a model in the UI (`/model`) can write
`"model"` into `~/.claude/settings.json`, turning a per-instance choice into the global default
with no notice. If the settings file disagrees with this line, ask before treating either one as
the intended default.

**When spawning agents:** no need to pin a model — let agents inherit the session model unless a
task warrants otherwise.

**Verified 2026-08-14, re-verified 2026-08-29 and 2026-09-25 — re-check before trusting if
stale:** claims about which model/tier is currently strongest age in weeks, not months. The split
that holds up is **difficulty/stakes-shaped, not domain-shaped** — not "Opus for prose, Fable for
code." The 2026-09-25 check (Opus 5.5 launch, 2026-09-22) strengthened it: Opus 5.5 leads Fable 5.1
on every row of Anthropic's launch table (e.g. Terminal-Bench 4.0 66.4% vs 55.8%, CursorBench 57.8%
vs 51.8%, OSWorld 2.0 81.8% vs 80.7%) at 40% of Fable's per-token price, and Anthropic's own
guidance is "start with Opus 5.5 for most workloads", reaching for Fable 5.1 on demanding
long-horizon work or when Opus 5.5 at higher effort still falls short. Anthropic also cautions that
the real-world gap is narrower than those margins. Re-verify via web search before a consequential
model-selection call if this note looks old again.

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
  `model: 'fable'` for exactly this reason, and so does its round-cap "NOT converged — targeted
  deep-dive" escalation). Reach for it only when a task matches one of those, not as a general
  escalation path from Opus.
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
  see the `aoe-sonarqube-mcp-shared-http-server` memory in the `~/github` scope): the global
  `mcpServers.sonarqube` entry in `~/.claude.json` points at `http://127.0.0.1:8090/mcp`
  (container `sonarqube-mcp`, `docker run -d --restart unless-stopped`, mounts `~/github`
  read-only). **Host port is 8090, not the container's internal 8080** — moved 2026-09-21 because
  `aoe serve`'s hardcoded default port (8080, no config-file or env-var override exists for it)
  collided with this container. Because one server now serves every repo, tools no longer get an
  auto-detected project key baked in per session — pass `projectKey` explicitly on every
  project-scoped `mcp__sonarqube__*` call. Resolve it in this order before calling: (1)
  `sonar.projectKey=` in the repo's `sonar-project.properties`; (2) `projectKey` in
  `.sonarlint/connectedMode.json`; (3) neither exists → call
  `search_my_sonarqube_projects` with a query derived from the repo name. Resolve once per session
  and reuse it rather than re-resolving on every tool call.

**aoe Session Management** (work environment; complements Multi-Agent Dispatch Communication in
`standards.md`):
- **A separate risk, orthogonal to the file-routing guidance above**: if the dispatching session
  itself is aoe-managed, dispatching `Agent`/`Workflow` subagents risks aoe mis-tracking the
  *coordinator's own* Claude Code transcript — not a file-routing problem, a session-identity one.
  Confirmed live against this exact class of session: aoe's live-observation heuristic picked a
  spent subagent's leftover transcript as "fresher" than the coordinator's real one and silently
  reattached the coordinator to it. See
  `plugins/satori/skills/handoff/references/aoe-session-collision.md` for the confirmed mechanism,
  what does and doesn't mitigate it, and why `aoe session set-session-id` does not help here.
- **Hard exclusion: never terminate an aoe-managed session, by any mechanism.** The persistent,
  user-visible, tmux-backed sessions in the aoe dashboard are not in scope for this rule at
  all — not via `TaskStop`, not via aoe's own commands (`aoe session archive`, `aoe remove`), not
  by killing the underlying tmux pane/process. Terminating one of those is the user's call alone,
  never an agent's, regardless of how idle or "done" it looks. This bullet governs only the
  ephemeral subagents/teammates a session spawns for its own work — aoe's top-level session fleet
  is never a target of it.
- **Never point two aoe sessions at the same literal directory.** Use a worktree per session
  (`[worktree] enabled = true` in `~/.config/agent-of-empires/config.toml` now does this for new
  sessions). Sharing a directory silently swaps Claude Code transcript identity between the
  sessions; diagnosis and recovery are in the `~/github` memory scope.

**Memory Hygiene — workspace layout** (complements Memory Hygiene in `standards.md`):
- **Launch where the work is.** Sustained single-repo work gets a session launched in that repo's
  directory (`repos/<group>/<repo>/`). When a workspace-root session turns into that kind of work,
  hand it off with `/satori:handoff` at that point. Fleet and cross-repo work stays at the workspace
  root. A quick single-repo fix does not need a handoff.
- **One clone per repo.** Repos listed in a workspace's `repos/repos.json` live only inside that
  workspace. Don't clone one again elsewhere under `~/github`: the second clone gets its own memory
  scope, and the two drift apart.

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
- Java (`jdtls-lsp`) is **disabled** here (`false` in `enabledPlugins`) because it has a known,
  unfixed crash (see "Java Code Navigation" below). Use the `scip` plugin's `/scip:query` command
  for Java instead.
- **Available in the marketplace but NOT currently enabled** — of the LSP plugins, only
  `pyright-lsp` is enabled, so these need enabling before they will do anything: C/C++
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
   `ToolSearch(query="select:LSP")` and use it as the first tool. **For Java, use the `scip`
   plugin's `/scip:query` command instead** — the `LSP` tool is not the path for Java symbol
   lookups in this environment.
2. **Use for navigation**: finding definitions, references, implementations.
3. **Use for refactoring**: renaming symbols across a project.
4. **Use for diagnostics**: getting compile/type errors before building.
5. **Only fall back to grep when**: the search is plain-text/pattern-based rather than a named
   symbol, or the file's language has no LSP server in this environment (bash — use `shellcheck`
   instead, per above). "LSP felt slower to reach for" is not a qualifying reason, and for Python,
   "grep already looked complete" is not one either — grep's false negatives look exactly like a
   clean result until LSP finds what it missed.
6. **Restate the tool in every spawned agent's prompt.** A subagent does not reliably act on this
   file's rule: on RS-4536/RS-4575 the rule had just been corrected in a plan document, and minutes
   later one of three Explore agents spawned without it went straight to grepping Java source for
   the pattern already known to produce false negatives. Any agent prompt that will look up symbols
   in Python or Java needs its own line naming the tool — `LSP` for Python, the `scip` plugin's
   `/scip:query` command for Java — the same way it needs its own file paths.

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

Use the **`scip` plugin** instead (`cc-plugins` marketplace — the Java-only version that used to
live in this repo was retired 2026-09-29 in favor of this multi-language rewrite; if `/scip:*`
commands are missing, `claude plugin install scip`). It manages a
[SCIP](https://github.com/scip-code/scip) index for the current repo — a precomputed, file-based
index of definitions/references, built once, then queried without any live server process. Since
there's no long-running mutable server, there's nothing to accumulate corrupt state across
sessions. Unlike the retired Java-only version, it also covers JavaScript, TypeScript, and Python —
Python's MUST-level tool remains LSP (`pyright-lsp`) per above; scip is Java's dedicated path and
an available alternative for the other two.

**This is a MUST for Java, the same way LSP is a MUST for Python** — the identical false-negative
risk from grep/ripgrep applies to Java too (missed references split across lines, inherited/
overridden members, aliased imports). Use `/scip:query` instead of grep for symbol-level questions
(definition, references, implementations, outline) on Java files. It does not cover live
diagnostics the way the `LSP` tool does for Python — read the file directly for those.

```
/scip:setup                                          # detect/report missing indexer CLIs
/scip:index                                          # build or refresh the cached index
/scip:query definition path/to/File.java:LINE:COL    # go to definition
/scip:query references path/to/File.java:LINE:COL    # find every reference
/scip:query implementations path/to/InterfaceOrMethod
/scip:query outline path/to/File.java
```

The `scip:symbol-navigation` skill backing these commands also auto-activates on plain-language
navigation questions ("where is this defined", "find every reference to this") — the commands
above are for explicit control over the index lifecycle.

Full details, known constraints, and troubleshooting: the plugin's own SKILL.md and README
(`cc-plugins` marketplace).

### IntelliJ MCP: last in line, and the repo must be open in the IDE

The IntelliJ MCP server (91 `mcp__intellij__*` tools) is configured at user scope as `intellij`
(set up and verified 2026-11-10). It is the **last** tool to reach for, after `scip`/`LSP` for symbol
lookups and CodeQL for semantic or data-flow questions. The rules above are unchanged.

- **Use it for what those cannot do**: live IDE diagnostics (`get_file_problems`), IDE refactoring
  (`rename_refactoring`, `optimize_imports`, `reformat_file`), run/debug/coverage, and the database
  tools. `rename_refactoring` is the strongest fit: it resolves symbols semantically, so it avoids the
  missed-reference failure that grep and manual edits have. No extract-method, move or
  change-signature tool is exposed (checked by tool name only; `execute_tool` not inspected).
- **Prompt the user to open the repo in the IDE** when you want these tools and the project is not
  open, and also when the user wants to see code in the IDE. Give the UNC path, e.g.
  `\\wsl.localhost\Ubuntu\home\fransonsr\github\records-platform-workspace\repos\<group>\<repo>`.
  A call against an unknown project returns an error that lists the open projects, so use that to
  tell whether a repo is open rather than guessing.
- **Which project a call hits**: the entry's `IJ_MCP_SERVER_PROJECT_PATH` header pins
  `//wsl.localhost/Ubuntu/home/fransonsr/github/records-platform-workspace`. Pass `projectPath` (same
  UNC form, forward slashes) to reach another open project. The override worked on
  `get_project_modules` on 2026-11-10 even though that tool's schema does not list the parameter;
  other tools were not checked. Some tools take their own path argument instead
  (`git_status` has `repositoryPathRelativeToProject`).
- **Ask before anything that changes state or reaches outside the code**: `apply_patch`,
  `execute_terminal_command`, run and debug sessions, and every database tool (they can run SQL
  against whatever connections IntelliJ has configured). Reads need no prompt.
- **Rename caveats**: it updates only the open project, so a shared library's public API still needs
  a check of the downstream repos. Run it on a clean working tree or branch, review `git diff`, and
  run the tests afterwards. Use `preview=true` first and compare `affects.usages` with the `scip`
  reference count; read `applied` as the only success signal, then confirm with `git diff`.
- **Trial result (2026-11-10, `sls-internal-workers`)**: a private-method rename
  (`VersionsConfig#putIfNotNull`, 1 definition + 3 calls in one file) matched `scip` exactly and
  changed only those 4 lines. The IDE saw a `git checkout` made from WSL immediately (the
  `\\wsl.localhost` path did not leave it stale). **Not tested**: a rename spanning modules or test
  sources, string/config references, and edits made with the Edit tool while the IDE is open. The
  IDE's Maven model for that project was not fully imported (`get_file_problems` reported
  unresolved Spring imports), so its diagnostics are noisy and a rename involving Spring-wired
  types may be less reliable than `scip` there.
- **Plumbing**: under WSL2 NAT, `127.0.0.1` in WSL is not Windows loopback and the IDE listens on
  Windows loopback only. The `ij-mcp-relay` container (`restart: unless-stopped`, Dockerfile in
  `docker/intellij-mcp-relay/` of this repo) forwards `127.0.0.1:65429` in WSL to Windows `:65428`
  through `host.docker.internal`. The host port is 65429, not 65428, because Docker Desktop also binds
  published ports on Windows, where IntelliJ already holds 65428. If the MCP will not connect, the
  usual causes are Docker Desktop not running, the relay container stopped, or IntelliJ not running
  (or on a different MCP port, which needs a rebuild with `--build-arg IJ_MCP_PORT=<port>`). Run
  `docker/intellij-mcp-relay/check.py` (in this repo; standard library only) to confirm once which layer
  failed: exit 11 container, 12 relay port, 13 IntelliJ, 14 handshake, 15 project (it lists the open
  projects). Then follow "Unavailable Tools and Connections" above: stop and report its output.
- **Why**: stated by the user on 2026-11-10 when setting this up: use the MCP only when the repo is
  open in the IDE, prompt to open it when needed, and keep `scip`/CodeQL ahead of it.

## Notes to Claude Code — Work Environment

1. **Symbol-level lookups always go through a dedicated tool, never grep — but Java and Python
   use different ones, and neither is optional.** Development Tools → LSP (Python) and → Java Code
   Navigation: scip, not LSP. Pattern matching against both languages has repeatedly produced false
   negatives (real references silently missed, not just noisy over-matches). For Python, that means
   the `LSP` tool (`pyright-lsp`); for Java, it means the `scip` plugin's `/scip:query` command —
   `jdtls-lsp` has a known, unfixed crash and is not the path for Java anymore. For any other
   LSP-supported language, still load and use LSP before grep. Grep is the fallback for plain-text
   search or for bash, which has no LSP server — use `shellcheck` there instead. The same
   instruction has to be restated in every spawned agent's prompt (LSP → Best Practices 6).

2. **Credentials already present.** "Unavailable Tools and Connections" in `standards.md` does not
   override the standing note above that the SonarQube token is already in the environment — look
   for it first.

## Shared Standards

@~/github/satoris-claude-config/standards.md
