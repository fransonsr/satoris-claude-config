---
name: index
description: Manage a SCIP (Sourcegraph Code Intelligence Protocol) index for the current repo as a crash-proof, file-based alternative to jdtls-lsp for Java code navigation — setup, build/refresh, status, cleanup, and go-to-definition/find-references queries. Use whenever a Java repo needs symbol-level lookups (definition, references, structure) and jdtls-lsp is unavailable, crashing, or the LSP tool has no working Java server for this environment. Also use when the user asks to "index this repo", "set up scip", "build a scip index", or wants "find references"/"go to definition" without a live language server.
argument-hint: <setup|run|refresh|status|cleanup|query> [args]
---

# scip: Repo Code Index

Manages a [SCIP](https://github.com/scip-code/scip) index for **one repo at a time** — whatever
repo the current working directory is inside. SCIP is a precomputed, file-based index of
definitions and references: `scip-java` builds it once (a real build, not a live server), and it's
queried afterward without any running process. Nothing accumulates mutable state across sessions,
which is the structural reason this exists as a Java alternative to `jdtls-lsp` — jdtls's Eclipse
workspace doesn't shut down cleanly between sessions and eventually crashes replaying stale state
against files a `mvn clean` already removed. There's no server here to accumulate that state.

**Scope**: Java (validated) and Kotlin (`scip-java` supports it per its own docs, but this was
never tested this session — treat it as unverified the same way Gradle is, below). This does not
cover Python — `pyright-lsp` (via the `LSP` tool) remains the mandated tool for Python symbol-level
questions; nothing here changes that.

## When to Use This Skill

- The current repo is Java/Kotlin and `jdtls-lsp` is unavailable, crashing, or not enabled for
  this environment.
- A user or agent needs go-to-definition, find-references, or workspace-symbol-style lookups in a
  Java repo without a live language server.
- Trigger phrases: "index this repo", "set up scip", "build a scip index", "find references to
  X" / "go to definition of X" (Java context), "is there a scip index for this repo".

## Operations

All scripts live at `${CLAUDE_PLUGIN_ROOT}/skills/index/scripts/` and resolve the current repo via
`git rev-parse --show-toplevel` — run them from inside the repo you want to operate on. The index
itself always lives outside the repo, at `~/.cache/scip/<repo-basename>/index.scip`, specifically
so it never shows up as an untracked file in `git status`.

| Operation | Script | What it does |
|---|---|---|
| `setup` | `scripts/setup.sh` | Installs `scip` and `scip-java` if either is missing. Idempotent — a repeat run with both present is a fast no-op. |
| `run` | `scripts/index.sh` | Builds the index (or overwrites an existing one). |
| `refresh` | `scripts/index.sh` | Same script as `run` — there is no incremental mode, so "refresh" and "run" are the same operation under two names. |
| `status` | `scripts/status.sh` | Read-only: reports whether an index exists, its path/size/age, and `scip stats` output. Never builds anything, never touches the network. |
| `cleanup` | `scripts/cleanup.sh` | Removes `~/.cache/scip/<repo>/` entirely. Never touches the repo's own working tree. |
| `query at <file>:<line>:<col>` | `scripts/query.sh` | Find every reference to (and the definition of) the symbol at a 1-based file:line:col position — the go-to-definition/find-references replacement for `jdtls-lsp`. |
| `query symbol <substring>` | `scripts/query.sh` | Find every occurrence whose SCIP symbol identifier contains a substring — useful when you know a method/class name but not a location. |

```bash
SCRIPTS="${CLAUDE_PLUGIN_ROOT}/skills/index/scripts"

bash "$SCRIPTS/setup.sh"
bash "$SCRIPTS/index.sh"                                    # run / refresh
bash "$SCRIPTS/status.sh"
bash "$SCRIPTS/cleanup.sh"
bash "$SCRIPTS/query.sh" at src/main/java/org/example/Foo.java:41:15
bash "$SCRIPTS/query.sh" symbol "Foo#refresh"
```

`query`'s output format (tab-separated, one hit per line):

```
src/main/java/org/example/Foo.java:41:15	definition	scip-java maven . . org/example/Foo#refresh().
src/test/java/org/example/FooTest.java:20:13	reference	scip-java maven . . org/example/Foo#refresh().
```

## Workflow

1. **First time in a repo**: run `setup`, then `run`. `run` is a real build under the hood (e.g.
   `mvn clean verify -DskipTests` for Maven) — it can take a while and is not something to call
   silently or repeatedly. Don't call it from `status` or as a side effect of a query.
2. **Querying**: prefer `query at file:line:col` when you have a cursor position (most accurate —
   resolves the exact symbol, then finds every occurrence of it). Use `query symbol <substring>`
   when you only know a name.
3. **No index yet**: `query` fails clearly and tells you to run `run` first — it will not build one
   for you implicitly.
4. **Code changed since the last index**: there's no staleness check. If lookups look wrong or
   incomplete after a meaningful change, re-run `refresh` (or `run`) before trusting a query.
5. **Done with a repo, or the index looks corrupted**: `cleanup`, then `run` again if needed.

## Known Constraints

- **Maven-only, validated.** The plain `scip-java index --output <path>` invocation — no
  module-scoping flags — was validated against a single-module repo and a 6-module Maven reactor.
  Gradle repos are auto-detected by `scip-java` per its own docs, but that path is **unverified
  here**. If `run`/`refresh` fails on a Gradle repo, treat it as a real gap, not something to paper
  over with an untested flag — surface the failure rather than guessing at Gradle-specific flags.
- **No module-scoping flags by default, on purpose.** Adding `-pl`/`-am` "just in case" would
  misfire on repos with a different module layout than the ones tested. Only add them if the plain
  invocation genuinely fails, and say so explicitly if it does.
- **`run`/`refresh` are build-cost operations, not free ones.** There is no incremental/watch mode.
- **Coursier (used only to install `scip-java`) has no prebuilt linux-arm64 binary** as of this
  writing. `setup` fails clearly on that platform combination with a pointer to install Coursier
  manually, rather than silently doing the wrong thing.
- **`status`'s `scip stats` call may print `Couldn't count lines of code: stat : no such file or
  directory` to stderr.** This is `scip` itself failing to resolve the project root's source tree
  for a line-of-code count, not a fault in `status.sh` — the rest of the stats output (documents,
  definitions, occurrences) is unaffected. Observed on real indexes this skill was validated
  against; harmless.
- **The `scip` CLI's JSON output does not follow standard protobuf JSON naming** — most fields are
  snake_case, but the range `oneof` wrapper uses PascalCase keys (`TypedRange` /
  `SingleLineRange` / `MultiLineRange`). This was found empirically, not from docs, and is encoded
  directly in `scripts/scip_query.py`'s `normalize_range()` — re-verify against real
  `scip print --json` output before trusting this again if the `scip` version changes.
- **Out of scope by design**: Python code intelligence (still `pyright-lsp` via the `LSP` tool) and
  CodeQL (a different tool solving a different problem — security-pattern queries over a
  heavyweight database, not navigation). Neither belongs in this skill.

## Tests

`scripts/test_scip_query.py` covers the query-parsing logic (range normalization, boundary-
condition containment checks, role labeling, index-cache staleness) with real captured
`scip print --json` fixtures where possible. `scripts/test_scip_script_contracts.py` exercises the
orchestration scripts (`common.sh`, `status.sh`, `cleanup.sh`, `setup.sh`'s already-installed fast
path, `query.sh`) against real or realistic fixtures — it deliberately excludes `index.sh`'s actual
build and `setup.sh`'s actual install path, since both require a real network/build and belong in
manual end-to-end verification instead.

```bash
cd "${CLAUDE_PLUGIN_ROOT}/skills/index/scripts" && python3 -m pytest -v
```
