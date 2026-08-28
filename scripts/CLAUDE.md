# CLAUDE.md

This file provides guidance to Claude Code when working with code in this `scripts/` directory.

## Purpose

`fleet-source.sh` is bash tooling (dotfiles-style, not a build project) for navigating and
operating on FamilySearch dev repo fleets — sourced into an interactive or agent shell, not
executed directly. It moved here from the (now-retired for this purpose) `satoris-bash-cheats`
repo so that Claude Code skills in this marketplace (e.g. `satori:handoff`'s Live Dispatch step)
can depend on it without a cross-repo dependency running the wrong direction — a skill in this
repo should be able to `source` a script that lives in this repo, not reach into an unrelated
personal dotfiles repo. `~/.bashrc` sources it from here; see the repo's own root `README.md` and
`install.sh` for how this marketplace as a whole gets linked into `~/.claude`.

There is no package manifest or CI for this file specifically. There is a small test suite
(`test/run.sh`) and `shellcheck` is expected to pass clean — see below.

## Validating changes

```bash
bash -n fleet-source.sh test/run.sh   # syntax
shellcheck fleet-source.sh test/run.sh  # must exit 0; see the inline "shellcheck disable" comments
                                        # in fleet-source.sh (top of file, plus SC2004/SC2053/SC2088
                                        # near their respective lines) and test/run.sh (SC1091) for why
./test/run.sh                          # builds its own fixture workspace; no external deps beyond git/jq
                                        # (a couple of hang-regression guards additionally use GNU
                                        # coreutils' `timeout` if present, skipping themselves if not)
```

Requires bash >= 4.3 (associative arrays, namerefs) — stock macOS `/bin/bash` is 3.2 and cannot run
this file at all; `fleet-source.sh` checks this itself at source time and errors with a clear message
rather than failing on the first unsupported builtin.

`test/run.sh` has no dependency on the real `rp`/`js` workspaces — it registers its own `tf` test
fleet against a temp-dir fixture (manifest + git repos), so it's safe to run anywhere, anytime.

To manually exercise the real fleets:

```bash
source ./fleet-source.sh
rp --help    # or js --help
rp ls        # requires ~/github/records-platform-workspace/repos/repos.json to exist
```

## Architecture: `fleet-source.sh`

One engine, one command per registered fleet (currently `rp` = Records Platform, `js` = Java Stack;
see the `_fleet_register` calls at the bottom of the file). Each fleet reads its repo inventory from
that fleet's workspace `repos/repos.json` manifest — see
`~/github/records-platform-workspace/repos/` and `~/github/java-stack-workspace/repos/` — rather than
from a hardcoded list. The manifest schema is identical across fleets (`.groups.<group>.repos[].name`,
top-level `.org` and `.defaultBranch`); only the group names differ (`services`/`libraries`/`meta`/`tools`
vs `core`/`libraries`/`tools`/`meta`), which is why one implementation serves both.

**Scope boundary — don't reintroduce what these already own:**
- `<workspace>/repos/init.sh` / `update.sh` / `status.sh` / `worktree.sh` — cloning, fleet-wide pull,
  fleet-wide status, worktree create/rm.
- The `rp-fleet:*` / `js-fleet:*` skills — PR, issue, and CI triage across the fleet.
- `fleet-source.sh` owns navigation, the per-repo dev loop, and `each` (arbitrary fan-out over a
  selected subset). There is deliberately no `clone` command here.

This replaced four earlier per-fleet scripts (`rs-source.sh`, `js-source.sh`, `idx-source.sh`,
`gtd-source.sh`, all deleted) that hardcoded repo lists and resolved paths under a flat `$WORKDIR`
that no longer matched the real (workspace-based) checkouts.

### Per-fleet configuration — the entire per-fleet surface

```bash
_fleet_register rp \
  --workspace "${RP_WORKSPACE:-$HOME/github/records-platform-workspace}" \
  --prefixes 'records-storage- records-platform- records- slsdata- sls- cds-' \
  --worktree sibling        # repos/<group>/<repo>-worktrees/<change>/

_fleet_register js \
  --workspace "${JS_WORKSPACE:-$HOME/github/java-stack-workspace}" \
  --prefixes 'java-stack-' \
  --worktree central        # repos/.worktrees/<change>/<repo>/
```

Adding a third fleet is one more `_fleet_register` call — no other file needs editing. The two
worktree layouts genuinely differ per fleet (verified against each workspace's own `worktree.sh`),
hence the `sibling`/`central` discriminator rather than a shared constant.

### Command registry — the reason usage/completion can't drift

Every command is one function, `_fleet_cmd_<name>`, paired with a `_fleet_meta` call declaring its
description, flags, and (optionally) long help, right next to the implementation:

```bash
_fleet_meta build 'Build the repo (mvn clean install)' '-k --keep-existing -l --local-m2-repository'
_fleet_cmd_build() { ... }
```

The dispatcher resolves commands via `declare -F "_fleet_cmd_$cmd"`; root usage
(`rp --help`) is generated from `_FLEET_CMD_ORDER`/`_FLEET_CMD_DESC`; completion enumerates the same
registry. **Adding a command means adding one `_fleet_meta` + `_fleet_cmd_<name>` pair** — there is no
second place (a `case` statement, a completion list, a usage heredoc) that can fall out of sync,
which is what caused real bugs in the predecessor scripts (e.g. one dispatched `versions` to the
wrong fleet's completion function entirely).

Commands with a hyphen in their name (`dep-tree`, `build-status`, `aoe-orchestrator`) are legal bash
function names (`_fleet_cmd_dep-tree`) — this is intentional, not a typo, and mirrors the subcommand
name exactly.

### Manifest loading — lazy, cached, and why `_fleet_dispatch` loads it up front

`_fleet_ensure_loaded <fleet>` parses `repos.json` via `jq` on first use per fleet and caches the
result in dynamically-named globals (`_FLEET_REPOS_<fleet>`, `_FLEET_GROUP_<fleet>`,
`_FLEET_SORTED_PREFIXES_<fleet>`), reached via `local -n` namerefs. `<fleet> reload` forces a re-read
after editing the manifest.

**Load-bearing gotcha, hit during development and worth remembering**: several helpers
(`_fleet_resolve`, `_fleet_repo_path`, ...) are called as `x=$(helper ...)` — command substitution,
which forks a **subshell**. Any manifest-cache population a subshell performs is local to that
subshell and vanishes the instant it exits. If the *first* call to `_fleet_ensure_loaded` for a given
invocation happened inside such a subshell, the parent shell's cache would stay empty and a
subsequent direct call (e.g. `_fleet_cd_repo`) would fail to find anything. The fix — and the reason
`_fleet_dispatch` calls `_fleet_ensure_loaded "$f"` directly, near the top, before any subshelled
helper runs — is to guarantee the *real* shell process's cache is warm before anything that might fork
depends on it. If you add a new top-level command path that bypasses `_fleet_dispatch`, call
`_fleet_ensure_loaded` yourself before using any manifest-derived helper.

### Nameref pitfalls with dynamic names

`local -n x="_FLEET_REPOS_$f"` (dynamic target, interpolated with a variable) is safe and used
throughout. **Never** pass a nameref target *by name* from one function to another when the target
string could equal the nameref variable's own name — bash treats that as a circular reference and
silently fails to bind (a runtime warning, not an error, so it's easy to miss). This was hit for real
during development: a helper took `<array-name>` string parameters and did `local -n args="$args_name"`,
while its caller's own local array was *also* named `args` — since the caller passed the literal
string `"args"`, the nameref ended up pointing at a name equal to itself. The fix used elsewhere in
this file (`_fleet_parse_selectors`) is to avoid by-name array handoff entirely: take `"$@"` directly
and expose results through fixed global scratch variables (`_SEL_GROUPS`, `_SEL_REST`, etc.) instead
of caller-chosen array names.

### Selectors — one vocabulary shared by `ls`, `each`, and `doctor`

`_fleet_parse_selectors <fleet> [args...]` consumes `-g <group>` (repeatable), `-m <glob>`, `--dirty`,
`--branch <b>`, `--from <repo>` and sets `_SEL_*` globals; `_fleet_selected_repos <fleet>` prints the
resulting repo subset in manifest order. Any command wanting selector support parses with the former
and iterates with the latter — no per-command reimplementation.

`doctor`'s on-disk-not-in-manifest bucket is the one exception `--from` doesn't reach: those
directories have no manifest-derived order to resume from (the comment above that scan says so
explicitly), so `--from` scopes every other bucket but leaves that one unfiltered regardless of the
value passed.

### Resolution — fuzzy, no hand-maintained alias table

`_fleet_resolve <fleet> <query>` tries, in order: exact name → unique prefix → unique substring →
unique match after stripping a fleet prefix (longest-first). It tries **every** stage and returns the
first with exactly one match; on failure it reports ambiguity using whichever candidate set is
genuinely **smallest by size**, compared explicitly — not just the first stage tried that happens to
be non-empty. The two are not the same thing: exact ⊆ prefix ⊆ substring is one nesting chain, and
stripped ⊆ substring is a second, but stripped and prefix are not comparable to each other, so a
fixed stage-precedence order can report a wider set (substring) when a strictly narrower one
(prefix) was also non-empty. This was a real bug, not a hypothetical one — caught by a second
adversarial-review round after the first round's fix already existed and had a passing test; the
existing test only happened to exercise a case where the two approaches agree. There is intentionally
no alias table to hand-maintain; every fleet gains free aliases (`rp gedcomx`, `js jdbc`) purely from
the manifest and the fleet's prefix list.

### `aoe` and `aoe-orchestrator` — launching an external tool, not wrapping it

`aoe <repo>` resolves `<repo>` through the same `_fleet_resolve` fuzzy matching as plain
navigation, then execs `aoe add <path> -l "$@"` — everything after `<repo>` is forwarded
verbatim to `aoe add`, unparsed, except that a worktree is now always created by default (see
below) unless the caller's own forwarded args already specify one. This deliberately does **not**
hardcode `aoe add`'s own flag surface (`-t`/`--title`, `-w`/`--worktree`, `--tool`, ...) beyond that
one default: duplicating it here would be exactly the "second place that can drift" the command
registry section above already argues against, except one level up — against the external tool's
CLI instead of this file's own registry.

**Every session `aoe`/`aoe-orchestrator` launches gets its own aoe-managed worktree by default.**
This isn't cosmetic — it's the fix for a real, confirmed bug: aoe identifies which live Claude Code
conversation belongs to a given tmux pane by watching Claude Code's own transcript directory, which
is keyed purely by working-directory path. Two aoe sessions sharing one literal directory (the
un-worktreed case) share that directory's transcript pool too, and aoe's poller can misattribute
which conversation belongs to which pane — confirmed in production across several sessions sharing
`java-stack-workspace`. Giving every session its own worktree (hence its own directory, hence its
own distinct Claude Code project slug) eliminates the precondition entirely, independent of whether
aoe's own poller ever gets fixed upstream.

**The worktree must be created via aoe's own `-w`/`-b` flags, not raw `git worktree add`.** aoe's
own lifecycle tooling (`aoe remove --delete-worktree`, trash-relocation, `set-worktree-name`) is
gated on `worktree_info.managed_by_aoe = true`, which is only set when aoe itself creates the
worktree. A worktree created by hand and merely handed to `aoe add` shows up as a "Manual worktree"
in aoe's own bookkeeping and is invisible to `aoe worktree cleanup`'s orphan sweep — defeating the
entire point of relying on aoe to manage it. If you ever need a bounded pool of reused worktree
slots instead of one fresh worktree per invocation, that reuse has to go through aoe's own commands
too, not a custom `git worktree add`/`checkout --detach` cycle — this was tried and rejected during
design for exactly this reason.

`aoe-orchestrator` is the equivalent entry point for tasks whose scope isn't known to a single
member repo yet — it worktrees the **workspace repo itself** (never a member repo, since none is
known yet) rather than resolving `<repo>` through `_fleet_resolve`.

`_fleet_require_cloned <fleet> <name> <path>` was extracted out of `_fleet_cd_repo` (which
now just calls it) so `aoe` can reuse the identical missing/not-a-repo guard without
`cd`-ing into the repo the way `_fleet_cd_repo` does — `aoe` only needs the path, not the
caller's `$PWD` changed.

Tests for `aoe`/`aoe-orchestrator` must never invoke the real `aoe` binary — doing so would create
actual session state in whoever runs `test/run.sh`'s own aoe profile. `test/run.sh` covers the
success path with a stub `aoe` script prepended onto `PATH` (so `command -v aoe` in
`_fleet_require_tool` finds the stub first) that just records its argv, and covers the
missing-tool guard with a `PATH` that excludes `~/.local/bin` — never with `command -v aoe`
absent by chance.

### Per-repo commands act on the current directory; `each` is the only one that changes directories

`status`, `branch`, `update`, `build`, `clean`, `graph`, `dep-tree`, `build-status`, `versions` all
assume they're already inside the target repo (plain `git`/`mvn`/`gh`, no `-C`, no `cd`). `ls`/`doctor`
use `git -C <path>` to query repos elsewhere in the fleet without moving the shell — `info` is a
narrower case: it only ever reports on whatever repo the caller is currently standing in (via
`_fleet_repo_at "$f" "$PWD"`), not an arbitrary repo by name. Only
`each` needs a real `cd`, and it does that inside a subshell (`( cd "$path" && ... )`) specifically so
the caller's own `$PWD` is never touched — verified by an explicit test assertion.

The commands that trust `_FLEET_BRANCH[$f]` (the *invoked* fleet's default branch) — `status`,
`branch -c`, `update`, `versions` — call two guards first: `_fleet_require_repo` (fails unless `$PWD`
is a real git checkout — using `git rev-parse --is-inside-work-tree`, not an empty branch name, since
detached HEAD also produces an empty branch name and is a valid state, not an error) and
`_fleet_require_own_repo` (fails unless `$PWD` is under fleet `$f`'s own workspace, so invoking `js
status` from inside an `rp` repo errors instead of silently checking the wrong fleet's default branch
name). `_fleet_repo_state <path>` classifies a manifest repo's disk state as `missing` /
`not-a-repo` / `ok` via `git -C "$path" rev-parse --show-toplevel` compared for equality against
`$path` itself — deliberately **not** `--is-inside-work-tree`, which walks up the directory tree and
would (and once did) misreport an uncloned member-repo directory as "ok" by matching the workspace's
own enclosing git repo instead. `--show-toplevel` is still worktree-safe, since a linked worktree's
toplevel is its own root, not the main checkout's. `ls`, `doctor`, `each`, and `_fleet_cd_repo` all
route through it rather than each testing `-d "$path/.git"` differently.

`_fleet_ensure_loaded` rejects a manifest where the same repo name appears twice — whether in two
different groups (the second would silently overwrite the first in `group_map`, making that group's
real on-disk repo permanently unreachable through the tool) or twice within the *same* group (a
plausible copy-paste mistake, which would otherwise double-append the one physical repo into
`repos_arr` with no error) — same fail-loud philosophy as the `.org`/`.defaultBranch`/`.groups`
validation above it.

`_FLEET_C_GREEN`/`_FLEET_C_RED`/`_FLEET_C_NONE` are computed by `_fleet_colors()`, called at the top
of `status`/`branch`, not once at source time — this file is sourced once per shell (from
`~/.bashrc`), so a one-time `[[ -t 1 ]]`/`NO_COLOR` check would latch colors on for the shell's whole
lifetime regardless of what a *specific* invocation's stdout is doing (piped, redirected to a file
under `each > log.txt`, etc.).
