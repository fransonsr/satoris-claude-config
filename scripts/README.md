# scripts/

Bash tooling for navigating and operating on FamilySearch dev repo fleets.

## `fleet-source.sh`

Source this file to get one command per registered fleet — currently `rp` (Records
Platform) and `js` (Java Stack). Each reads its repo inventory from that fleet's
workspace `repos/repos.json` manifest (see
[records-platform-workspace](https://github.com/fs-eng/records-platform-workspace) /
[java-stack-workspace](https://github.com/fs-eng/java-stack-workspace)), so the repo
list, groups, and default branch are never hand-maintained here — adding a repo to the
manifest is the only change needed.

This tool does **not** clone repos (see `<workspace>/repos/init.sh`) and does **not**
do fleet-wide PR/CI triage (see the `rp-fleet`/`js-fleet` skills). It owns navigation,
the per-repo dev loop (`status`, `build`, `versions`, ...), and `each` — arbitrary
fan-out over a selected subset of the fleet.

It lives in this marketplace repo (rather than the personal `satoris-bash-cheats`
dotfiles repo it moved from) so that `satori:handoff`'s Live Dispatch step can source
it directly without a dependency running the wrong way — a skill depending on a script
in its own repo, not reaching into an unrelated one.

### Setup

1. Clone this repo itself, if you haven't already — the `source` line in step 4 below
   assumes it lives at `~/github/satoris-claude-config`; if you clone it elsewhere,
   adjust that line's path to match.
2. Clone the workspace repo(s) for the fleet(s) you'll use — `fleet-source.sh` reads
   `<workspace>/repos/repos.json` from them, and won't work until at least one exists:
   ```bash
   git clone git@github.com:fs-eng/records-platform-workspace ~/github/records-platform-workspace
   git clone git@github.com:fs-eng/java-stack-workspace ~/github/java-stack-workspace
   ```
3. Run each workspace's own `repos/init.sh` to clone the fleet's actual member repos
   (step 2 only clones the workspace *meta*-repo, which contains `repos.json` — the
   real repos `rp <repo>`, `each`, and every per-repo command depend on come from
   `init.sh`):
   ```bash
   ~/github/records-platform-workspace/repos/init.sh
   ~/github/java-stack-workspace/repos/init.sh
   ```
4. Add to `~/.bashrc`, **above** the interactive-shell guard — structurally, any early
   `return` gated on whether `$-` contains `i` (commonly `case $- in *i*) ;; *)
   return;; esac`, but the exact wording varies) — so the commands are also available
   to non-interactive/agent shells. By default `rp` uses
   `~/github/records-platform-workspace` and `js` uses
   `~/github/java-stack-workspace`; if yours live elsewhere, set the override **before**
   the `source` line — `RP_WORKSPACE`/`JS_WORKSPACE` are read once, when the file is
   sourced, not looked up later, so an override placed after `source` is silently
   ignored:
   ```bash
   export RP_WORKSPACE="/path/to/records-platform-workspace"   # only if not the default above
   export JS_WORKSPACE="/path/to/java-stack-workspace"         # only if not the default above
   . ~/github/satoris-claude-config/scripts/fleet-source.sh     # adjust if cloned elsewhere (step 1)
   ```
   `NO_COLOR` is different: unlike the two workspace variables above, it isn't baked in
   at source time — `status`/`branch` re-check `${NO_COLOR:-}` on every invocation via
   `_fleet_colors()`, so it can be set or unset at any time, in an already-sourced
   shell, and takes effect on the very next command (`export NO_COLOR=1`, or
   per-invocation `NO_COLOR=1 rp status`). Colors are also auto-disabled when stdout
   isn't a terminal, even without `NO_COLOR`.

### Usage

```
rp                       cd to the workspace root
rp <repo>                cd to a repo (fuzzy: exact, prefix, substring, or
                          fleet-prefix-stripped — e.g. `rp gedcomx`, `js jdbc`)
rp -                      cd to the previously-visited repo
rp <command> [args...]    run a fleet subcommand
rp --help                 list all commands
rp <command> -h           command-specific help
```

Discovery: `ls`, `where`, `info`, `doctor` (all support `--json`), but they don't share
a calling convention — `where <repo>` requires a repo-name argument, `info` takes none
(it always reports on the current directory only), and `ls`/`doctor` take selector
flags. `where <repo>` prints that repo's absolute path and does **not** `cd` there (use
`rp <repo>` to actually navigate, or `cd "$(rp where <repo>)"` to compose it). Run `rp
ls` with no `-g` to see every repo's group; `doctor` instead reports **drift** —
manifest repos that are missing on disk, present but not a git repo, off the default
branch, or dirty; on-disk directories absent from the manifest; repo names that collide
with a registered command; and missing required tools — or tab-complete `rp each -g
<tab>`.

Selectors `-g <group>`, `-m <glob>`, `--dirty`, `--branch <b>` narrow `ls`, `each`, and
`doctor` to a subset by filtering. `--from <repo>` is different — it's not a filter,
it's a resume point: it skips every repo up to the named one in manifest order, then
includes it and everything after, for resuming a fan-out that stopped partway through.
`--from` does **not** scope `doctor`'s on-disk-not-in-manifest bucket — those
directories have no manifest order to resume from, so `doctor --from <repo>` still
reports all of them regardless of `<repo>`.

Per-repo (act on the current directory): `status`, `branch`, `update`, `build`, `clean`, `graph`,
`dep-tree`, `build-status`, `versions`. `branch -c` shows the current branch (colored);
`branch --filter-pr` excludes numbered `pr/<N>` branches (and `origin/pr/<N>`) from the
listing — not arbitrary names nested under `pr/`.

`aoe <repo>` resolves `<repo>` with the same fuzzy matching as plain navigation and runs
`aoe add <path> -l` to launch an Agent of Empires session rooted there, without first
`cd`-ing there yourself — always in its own aoe-managed worktree by default (see
`CLAUDE.md`'s "aoe and aoe-orchestrator" section for why). Anything after `<repo>` is
forwarded verbatim to `aoe add` — pass your own `-w`/`--worktree` to override the
default worktree name/branch; e.g. `rp aoe mcp -t "my task"` or `js aoe jdbc -w
my-branch -b`; see `aoe add --help` for the full flag surface. Requires the `aoe` CLI
on `PATH`.

`aoe-orchestrator [-n <count>] [--list]` is the equivalent entry point when you don't
yet know which member repo a task will touch — it worktrees the workspace repo itself
rather than resolving a specific `<repo>`. `--list` shows the current pool without
claiming a slot.

Fan-out: `each [selector] <subcommand>` or `each [selector] -- <shell command>` runs
across every selected repo, serially, stopping on the first failure unless
`-k`/`--keep-going` is given. `reload` and `wt` can't be used as an `each` subcommand —
both mutate the calling shell, which has no effect inside `each`'s per-repo subshells.
Flag position matters: everything **before** the subcommand name belongs to `each`
itself; everything **after** is forwarded verbatim to the subcommand's own parser.
`each build -k` therefore gets `build`'s `-k`/`--keep-existing` (skip mvn clean), not
`each`'s own keep-going-on-failure — `each` still stops at the first failing repo. Same
collision with `versions -k`/`--keep-branch`. Put `each`'s own `-k` first if you want
both: `each -k build -k`.

Worktrees: `wt <change> [<repo>]` cds into a worktree for `<change>` — the same
identifier you passed to `<workspace>/repos/worktree.sh` when creating it. Omitting
`<repo>` behaves differently per fleet's worktree layout: for `sibling` fleets (`rp`),
it searches every group for a `<change>` worktree and auto-cds if exactly one exists,
otherwise lists the candidates to disambiguate; for `central` fleets (`js`), it lands in
`<change>`'s shared container directory (`repos/.worktrees/<change>/`), not any single
repo's checkout. Note this is unrelated to `aoe`/`aoe-orchestrator`'s own worktrees,
which aoe manages itself rather than through `<workspace>/repos/worktree.sh`.

Maintenance: `reload` re-reads `repos.json` in the current shell after you edit the
manifest — an already-sourced shell caches it, so a newly-added repo won't show up
until `reload` runs (or a new shell starts).

Tab-completion (`rp <tab><tab>`, `rp each -g <tab><tab>`, ...) is registered for
interactive shells only — it has no effect in the non-interactive/agent shells the
Setup step above also enables command dispatch for.

Everything above works identically for `js`, except worktree layout — see the `wt`
paragraph above, where omitting `<repo>` behaves differently for `js` (`central`) than
for `rp` (`sibling`).

### Dependencies

bash >= 4.3 (uses associative arrays and namerefs — stock macOS `/bin/bash` is 3.2 and
won't run this; install a newer bash, e.g. `brew install bash`, and adjust your
shebang/PATH), jq, git, and (for `build`/`clean`/`graph`/`dep-tree`/`versions`) mvn, and
(for `build-status`/`versions`) the GitHub CLI (`gh`), authenticated to GitHub. `branch
--filter-pr` requires a PCRE-capable `grep` (`grep -P`). `aoe`/`aoe-orchestrator`
require the `aoe` CLI.

### Tests

```
./test/run.sh              # builds its own fixture workspace; no deps beyond the ones above
shellcheck fleet-source.sh test/run.sh
```

A couple of hang-regression guards inside `test/run.sh` additionally use GNU coreutils'
`timeout`, if present, to bound a test that would otherwise hang the whole run on
failure — each skips itself with a message if `timeout` isn't on PATH (e.g. stock
macOS) rather than requiring it.
