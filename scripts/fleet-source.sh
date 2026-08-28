#!/bin/bash
#
# fleet-source.sh — unified navigation and repo tooling for dev fleets that
# manage their repos with a workspace `repos/repos.json` manifest (see e.g.
# ~/github/records-platform-workspace/repos/ or ~/github/java-stack-workspace/repos/).
#
# Source this file once; it registers one command per fleet (currently `rp`
# and `js`, see the bottom of this file). Each fleet command supports:
#
#   rp                       cd to the fleet's workspace root
#   rp <repo>                cd to a repo (fuzzy match)
#   rp -                     cd to the previously-visited repo
#   rp <command> [args...]   run a fleet subcommand; `rp --help` lists them
#
# This script intentionally does NOT clone repos (see <workspace>/repos/init.sh)
# and does NOT do fleet-wide PR/CI triage (see the rp-fleet/js-fleet skills). It
# owns navigation, the per-repo dev loop (status/build/versions/...), and
# `each` — arbitrary fan-out over a selected subset of the fleet.
#
# Usage:
#   . fleet-source.sh
#
# See `rp --help` / `js --help` after sourcing, or README.md in this repo.
#
# shellcheck disable=SC2178,SC2207
# SC2178: many functions below do `local -n x="_FLEET_..._$f"` — a nameref to a
#         dynamically-named global array/map registered per fleet by _fleet_register.
#         The static analyzer can't resolve the dynamic target name, so it misreports
#         these namerefs as plain-string locals. They are real array/map namerefs.
# SC2207: COMPREPLY=($(compgen -W "..." -- "$cur")) is the standard bash-completion
#         idiom. Repo, command, and group names never contain characters that would
#         make the implied word-splitting unsafe here.

export FLEET_SOURCE_VERSION=1.0.0

# This file relies on bash 4.3+ (associative arrays, `local -n` namerefs,
# ${var^^} case conversion) — stock macOS ships bash 3.2 (Apple hasn't updated
# it since 2007) and can't run any of this. Check once, up front, so the
# failure is one clear message instead of a cascade of unrelated builtin
# errors on every command.
if ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3))); then
  echo "fleet-source.sh requires bash >= 4.3 (found ${BASH_VERSION}). On macOS, install a" >&2
  echo "newer bash with 'brew install bash' and source that one instead of /bin/bash." >&2
  return 1
fi

# ---------------------------------------------------------------------------
# Colors — disabled when stdout isn't a terminal or NO_COLOR is set, so piped
# and --json output is never corrupted by escape codes. Computed by
# _fleet_colors() per invocation (called from status/branch) rather than once
# here at source time — this file is sourced once per shell, from ~/.bashrc,
# so a one-time check would latch colors on for the shell's whole lifetime and
# keep emitting them even when an individual command's stdout is redirected.
# ---------------------------------------------------------------------------
_fleet_colors() {
  if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    _FLEET_C_GREEN=$'\e[1;32m'
    _FLEET_C_RED=$'\e[1;31m'
    _FLEET_C_NONE=$'\e[0m'
  else
    _FLEET_C_GREEN=''
    _FLEET_C_RED=''
    _FLEET_C_NONE=''
  fi
}

# ---------------------------------------------------------------------------
# Fleet registry — populated by _fleet_register calls at the bottom of this
# file. This is the entire per-fleet configuration surface.
# ---------------------------------------------------------------------------
declare -gA _FLEET_WORKSPACE=()   # fleet -> workspace root path
declare -gA _FLEET_PREFIXES=()    # fleet -> space-delimited alias-derivation prefixes
declare -gA _FLEET_WORKTREE=()    # fleet -> "sibling" | "central" worktree layout
declare -gA _FLEET_LOADED=()      # fleet -> "1" once its manifest has been parsed
declare -gA _FLEET_ORG=()         # fleet -> .org from the manifest
declare -gA _FLEET_BRANCH=()      # fleet -> .defaultBranch from the manifest
declare -gA _FLEET_LASTDIR=()     # fleet -> previous directory, for `<fleet> -`

# Command registry — shared across all fleets; one function per command.
declare -gA _FLEET_CMD_DESC=()
declare -gA _FLEET_CMD_FLAGS=()
declare -gA _FLEET_CMD_LONGHELP=()
declare -ga _FLEET_CMD_ORDER=()

# Selector state — set by _fleet_parse_selectors, read by _fleet_selected_repos.
# Plain globals rather than fleet-scoped: only one selector-driven command runs
# at a time, and none of them recurse into another selector-driven command.
declare -ga _SEL_GROUPS=()
declare -g _SEL_GLOB=''
declare -g _SEL_DIRTY=false
declare -g _SEL_BRANCH=''
declare -g _SEL_FROM=''
declare -ga _SEL_REST=()

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# _fleet_register <name> --workspace <path> --prefixes '<p1> <p2> ...' --worktree sibling|central
_fleet_register() {
  local f="$1"
  shift
  local workspace='' prefixes='' worktree='sibling'

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --workspace | --prefixes | --worktree)
        # Bounds-check before consuming a value: with no argument left, `shift 2`
        # silently fails to shift (bash leaves $# and $1 unchanged), spinning this
        # loop forever — and since _fleet_register runs at source time, that hangs
        # every new shell, not just this call. Same class of bug round 1 fixed in
        # _fleet_parse_selectors.
        if [[ $# -lt 2 ]]; then
          echo "fleet-source: _fleet_register: option '$1' requires a value" >&2
          return 1
        fi
        case "$1" in
          --workspace) workspace="$2" ;;
          --prefixes) prefixes="$2" ;;
          --worktree) worktree="$2" ;;
        esac
        shift 2
        ;;
      *)
        echo "fleet-source: _fleet_register: unknown option '$1'" >&2
        return 1
        ;;
    esac
  done

  case "$worktree" in
    sibling | central) ;;
    *)
      echo "fleet-source: _fleet_register: --worktree must be 'sibling' or 'central', got '$worktree'" >&2
      return 1
      ;;
  esac

  # An empty workspace degenerates every downstream "$PWD/" == "${_FLEET_WORKSPACE[$f]}/"*
  # prefix-match into matching every absolute path — reject it here rather than let a
  # missing or blank RP_WORKSPACE/JS_WORKSPACE override silently turn "own repo" checks
  # into no-ops.
  if [[ -z "$workspace" ]]; then
    echo "fleet-source: _fleet_register: --workspace is required" >&2
    return 1
  fi

  # A literal ~ in an env-var override (e.g. RP_WORKSPACE=~/foo) is never shell-expanded,
  # unlike a command-line argument — expand it ourselves so overrides behave consistently.
  # shellcheck disable=SC2088 # these are case patterns matching a literal ~, not an
  # attempted tilde expansion inside quotes.
  case "$workspace" in
    "~") workspace="$HOME" ;;
    "~/"*) workspace="$HOME/${workspace#"~/"}" ;;
  esac

  # A trailing slash breaks every downstream "${_FLEET_WORKSPACE[$f]}/"* prefix-match
  # against $PWD (a doubled slash can never match, since the kernel always normalizes
  # $PWD to single slashes) — strip it so overrides work regardless of how the user
  # wrote them.
  workspace="${workspace%/}"

  _FLEET_WORKSPACE[$f]="$workspace"
  _FLEET_PREFIXES[$f]="$prefixes"
  _FLEET_WORKTREE[$f]="$worktree"

  declare -ga "_FLEET_REPOS_$f"
  declare -gA "_FLEET_GROUP_$f"
  declare -ga "_FLEET_SORTED_PREFIXES_$f"

  eval "${f}() { _fleet_dispatch $f \"\$@\"; }"
  if [[ $- == *i* ]]; then
    eval "_fleet_complete_${f}() { _fleet_complete $f; }"
    complete -F "_fleet_complete_${f}" "$f"
  fi
}

# _fleet_meta <command> <description> [flags] [longhelp]
_fleet_meta() {
  local name="$1" desc="$2" flags="${3:-}" longhelp="${4:-}"
  _FLEET_CMD_DESC[$name]="$desc"
  _FLEET_CMD_FLAGS[$name]="$flags"
  _FLEET_CMD_LONGHELP[$name]="$longhelp"
  _FLEET_CMD_ORDER+=("$name")
}

# ---------------------------------------------------------------------------
# Manifest loading (lazy, cached per fleet) and small pure-bash helpers
# ---------------------------------------------------------------------------

# Sort args longest-first (stable insertion sort; small N, no subprocess).
_fleet_sort_longest_first() {
  local -a arr=("$@")
  local i j tmp
  local n=${#arr[@]}
  for ((i = 1; i < n; i++)); do
    tmp="${arr[i]}"
    j=$((i - 1))
    while ((j >= 0)) && ((${#arr[j]} < ${#tmp})); do
      arr[j + 1]="${arr[j]}"
      ((j--))
    done
    arr[j + 1]="$tmp"
  done
  printf '%s\n' "${arr[@]}"
}

_fleet_ensure_loaded() {
  local f="$1"
  [[ -n "${_FLEET_LOADED[$f]:-}" ]] && return 0

  local workspace="${_FLEET_WORKSPACE[$f]:-}"
  if [[ -z "$workspace" ]]; then
    echo "fleet: unknown fleet '$f'" >&2
    return 1
  fi
  local manifest="$workspace/repos/repos.json"

  if ! command -v jq &>/dev/null; then
    echo "fleet: jq is required. Install it with: apt-get install jq  OR  brew install jq" >&2
    return 1
  fi
  if [[ ! -f "$manifest" ]]; then
    echo "fleet: manifest not found: $manifest" >&2
    echo "       either the '$f' workspace repo hasn't been cloned there yet, or it lives" >&2
    echo "       elsewhere and ${f^^}_WORKSPACE wasn't exported before the source line for" >&2
    echo "       fleet-source.sh in ~/.bashrc (it is read once, at source time)" >&2
    return 1
  fi

  # Validate the document once, up front, and keep stderr — otherwise a JSON syntax
  # error anywhere in the file gets misreported as ".org missing or null" (jq -e fails
  # for both "key really is null" and "file won't parse" and the message can't tell
  # them apart if it discards jq's own diagnostic).
  local jq_err
  jq_err=$(jq -e . "$manifest" 2>&1 >/dev/null) || {
    echo "fleet: $manifest is not valid JSON: $jq_err" >&2
    return 1
  }

  local org branch
  org=$(jq -e -r '.org' "$manifest" 2>/dev/null) || {
    echo "fleet: .org missing or null in $manifest" >&2
    return 1
  }
  branch=$(jq -e -r '.defaultBranch' "$manifest" 2>/dev/null) || {
    echo "fleet: .defaultBranch missing or null in $manifest" >&2
    return 1
  }
  # Windows jq emits CRLF; strip trailing CR so values are clean.
  org=${org%$'\r'}
  branch=${branch%$'\r'}
  # jq -e only treats false/null as failure — a present-but-empty string passes
  # untouched and would then corrupt every branch comparison downstream (every repo
  # reported "off branch ()", `git checkout ""` failing with a confusing message).
  if [[ -z "$org" ]]; then
    echo "fleet: .org is empty in $manifest" >&2
    return 1
  fi
  if [[ -z "$branch" ]]; then
    echo "fleet: .defaultBranch is empty in $manifest" >&2
    return 1
  fi

  # A group key or repo name that's empty/null gets silently filtered out of the
  # `raw` extraction below (necessarily — bash's `read` can't reliably recover an
  # empty first field from a tab-delimited line; see the comment at that loop).
  # Report each dropped entry by name here, before filtering, so one malformed
  # entry doesn't vanish without a trace just because the fleet as a whole still
  # loads fine on its other repos.
  local malformed
  # The closing quote and trailing "$manifest" 2>/dev/null MUST stay on the same
  # line as each other: a bare newline inside $(...) right after a quoted string
  # closes acts as a statement separator, silently splitting this into two
  # commands — a bare `jq -r '<program>'` (which then blocks reading stdin,
  # hanging every shell that sources this file) and a second no-op statement.
  # Verified by reproduction; matches the pattern the working query below uses.
  malformed=$(jq -r '.groups | to_entries[] as $g | $g.value.repos[]
                | select(($g.key == "") or (.name == null) or (.name == ""))
                | "group=" + (if $g.key == "" then "<empty>" else $g.key end)
                       + " name=" + (if (.name == null or .name == "") then "<empty>" else .name end)' "$manifest" 2>/dev/null)
  if [[ -n "$malformed" ]]; then
    while IFS= read -r entry; do
      [[ -n "$entry" ]] && echo "fleet: skipping malformed repo entry in $manifest ($entry) — group key and repo name must both be non-empty" >&2
    done < <(tr -d '\r' <<<"$malformed")
  fi

  # Capture (rather than pipe into a process substitution) so a malformed .groups
  # can be detected and reported instead of silently yielding zero repos that then
  # get cached as a successfully "loaded" fleet.
  local raw
  # Reject an empty group key here too, not just an empty repo name: bash's `read`
  # with IFS=tab strips a LEADING tab as whitespace rather than treating it as an
  # empty first field, so an empty-string group key would decode with the repo
  # NAME landing in the group variable and the real name silently empty — dropping
  # that repo with no error, invisible whenever at least one other group loads fine.
  raw=$(jq -r '.groups | to_entries[] as $g | $g.value.repos[]
                | select($g.key != "" and .name != null and .name != "")
                | "\($g.key)\t\(.name)"' "$manifest" 2>&1) || {
    echo "fleet: failed to parse .groups/.repos in $manifest: $raw" >&2
    return 1
  }

  local -n repos_arr="_FLEET_REPOS_$f"
  local -n group_map="_FLEET_GROUP_$f"
  repos_arr=()
  group_map=()

  local group name
  while IFS=$'\t' read -r group name; do
    [[ -z "$name" ]] && continue
    # group_map is keyed by name alone, fleet-wide; a name appearing twice — in two
    # different groups, or twice within the SAME group (a plausible copy-paste
    # mistake) — would let the second entry silently double up: across groups, the
    # first group's actual on-disk repo becomes permanently unreachable; within one
    # group, the single physical repo gets treated as two competing entries with an
    # identical name (ambiguous against itself, run twice under `each`).
    if [[ -n "${group_map[$name]:-}" ]]; then
      if [[ "${group_map[$name]}" != "$group" ]]; then
        echo "fleet: repo '$name' appears in multiple groups (${group_map[$name]}, $group) in $manifest — repo names must be unique across groups" >&2
      else
        echo "fleet: repo '$name' is listed twice in group '$group' in $manifest" >&2
      fi
      return 1
    fi
    repos_arr+=("$name")
    # group_map is an associative-array nameref; $ on the key is required here.
    # shellcheck disable=SC2004
    group_map[$name]="$group"
  done < <(tr -d '\r' <<<"$raw")

  if [[ ${#repos_arr[@]} -eq 0 ]]; then
    echo "fleet: no repos found in $manifest — check .groups[].repos" >&2
    return 1
  fi

  _FLEET_ORG[$f]="$org"
  _FLEET_BRANCH[$f]="$branch"

  local -n sorted_prefixes="_FLEET_SORTED_PREFIXES_$f"
  local -a raw_prefixes=()
  read -ra raw_prefixes <<<"${_FLEET_PREFIXES[$f]}"
  sorted_prefixes=()
  if [[ ${#raw_prefixes[@]} -gt 0 ]]; then
    local p
    while IFS= read -r p; do
      [[ -n "$p" ]] && sorted_prefixes+=("$p")
    done < <(_fleet_sort_longest_first "${raw_prefixes[@]}")
  fi

  _FLEET_LOADED[$f]=1
}

_fleet_groups() {
  local f="$1"
  _fleet_ensure_loaded "$f" || return 1
  local -n group_map="_FLEET_GROUP_$f"
  local -A seen=()
  local g
  for g in "${group_map[@]}"; do
    seen[$g]=1
  done
  printf '%s\n' "${!seen[@]}" | sort
}

_fleet_repo_path() {
  local f="$1" name="$2"
  local -n group_map="_FLEET_GROUP_$f"
  local group="${group_map[$name]:-}"
  if [[ -z "$group" ]]; then
    echo "fleet: '$name' is not in the '$f' manifest — run '$f reload' after editing repos/repos.json" >&2
    return 1
  fi
  echo "${_FLEET_WORKSPACE[$f]}/repos/$group/$name"
}

# `git branch --show-current` prints nothing (exit 0) on BOTH detached HEAD (a normal,
# valid state) and "not a repo at all" (an error state) — report detached HEAD with an
# explicit sentinel instead of an empty string so callers can't conflate the two.
_fleet_repo_branch() {
  local branch
  branch=$(git -C "$1" branch --show-current 2>/dev/null)
  if [[ -n "$branch" ]]; then
    echo "$branch"
  elif git -C "$1" rev-parse --is-inside-work-tree &>/dev/null; then
    echo "(detached: $(git -C "$1" rev-parse --short HEAD 2>/dev/null))"
  fi
}

_fleet_repo_is_dirty() {
  [[ -n "$(git -C "$1" status --porcelain 2>/dev/null)" ]]
}

# Classify a repo path as: missing (doesn't exist), not-a-repo (exists but isn't a git
# checkout — e.g. residue of an interrupted init.sh), or ok. Uses `git rev-parse
# --is-inside-work-tree` rather than testing for a ".git" directory so linked git
# worktrees (where .git is a *file*, not a directory) classify correctly too.
_fleet_repo_state() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo missing
    return
  fi
  # `git rev-parse --is-inside-work-tree` walks UP the directory tree looking for a
  # .git — and both real workspaces are themselves git repos, so a directory that
  # was never actually cloned (a stub, an interrupted init.sh) would resolve to the
  # WORKSPACE's own git state and be misclassified "ok" instead of "not-a-repo".
  # Anchor to the exact path instead: --show-toplevel returns $path itself for a
  # real repo root (including a linked worktree, whose toplevel is its own root,
  # not the main repo's), but returns an ANCESTOR path when $path is just a plain
  # directory nested inside a repo.
  local toplevel
  if toplevel=$(git -C "$path" rev-parse --show-toplevel 2>/dev/null) && [[ "$toplevel" == "$path" ]]; then
    echo ok
  else
    echo not-a-repo
  fi
}

_fleet_repo_is_cloned() {
  [[ "$(_fleet_repo_state "$1")" == "ok" ]]
}

# Resolves $1 to its physical (symlink-free) path via a subshell cd, so "is $PWD
# inside this workspace" prefix-matches still work when the workspace itself is a
# symlink, or the caller reached the same repo through a different symlinked route
# — bash's $PWD tracks the logical path as typed, not the resolved physical one.
# Falls back to the literal path if it can't be entered (doesn't exist yet, e.g. an
# uncloned repo or workspace) — callers' fallback comparison against the literal
# path is already correct in that case.
_fleet_realpath() {
  (cd "$1" 2>/dev/null && pwd -P) || echo "$1"
}

# Fail with a clear message unless $PWD is actually inside a git repository. Several
# per-repo commands used to infer this from an empty branch name, which is also what a
# valid detached HEAD produces — use git's own signal instead.
_fleet_require_repo() {
  git rev-parse --is-inside-work-tree &>/dev/null || {
    echo "fleet: $1: not inside a git repository ($PWD)" >&2
    return 1
  }
}

# Fail unless $PWD is inside fleet $1's own workspace. Per-repo commands trust
# _FLEET_BRANCH[$f] (the *invoked* fleet's default branch) without this check, they'd
# silently act on the wrong branch name if run from inside a different fleet's repo.
_fleet_require_own_repo() {
  local f="$1" cmd="$2"
  # An empty workspace would make the pattern below "/"* — matching every absolute
  # path — so fail closed instead of silently treating everywhere as "own repo".
  if [[ -z "${_FLEET_WORKSPACE[$f]}" ]]; then
    echo "fleet: $cmd: fleet '$f' has no workspace configured" >&2
    return 1
  fi
  case "$(_fleet_realpath "$PWD")/" in
    "$(_fleet_realpath "${_FLEET_WORKSPACE[$f]}")/"*) return 0 ;;
    *)
      echo "fleet: $cmd: $PWD is not inside the '$f' fleet workspace (${_FLEET_WORKSPACE[$f]})" >&2
      return 1
      ;;
  esac
}

# Fail with a clear, fleet-style message unless $1 is on PATH — mirrors the jq check in
# _fleet_ensure_loaded, which every command implicitly relies on but only jq itself
# enforced; mvn/gh call sites used to fail with a raw "command not found" instead.
_fleet_require_tool() {
  local tool="$1" hint="$2"
  command -v "$tool" &>/dev/null || {
    echo "fleet: $tool is required. $hint" >&2
    return 1
  }
}

# ---------------------------------------------------------------------------
# Fuzzy resolution — exact, then unique prefix, then unique substring, then
# unique match after stripping a fleet prefix. Tries every stage (narrowest
# first, i.e. this order) and returns the first stage with exactly one match;
# ambiguity is reported from the narrowest stage that had any candidates.
# ---------------------------------------------------------------------------

_fleet_ambiguous() {
  local f="$1" query="$2"
  shift 2
  local -n group_map="_FLEET_GROUP_$f"
  echo "fleet: ambiguous '$query' — $# matches:" >&2
  local name
  for name in "$@"; do
    printf '  %-30s (%s)\n' "$name" "${group_map[$name]}" >&2
  done
}

_fleet_resolve() {
  local f="$1" query="$2"
  _fleet_ensure_loaded "$f" || return 1
  local -n repos_arr="_FLEET_REPOS_$f"
  local -n sorted_prefixes="_FLEET_SORTED_PREFIXES_$f"

  local -a exact=() prefix_matches=() substr_matches=() stripped_matches=()
  local name stripped p

  for name in "${repos_arr[@]}"; do
    [[ "$name" == "$query" ]] && exact+=("$name")
  done
  [[ ${#exact[@]} -eq 1 ]] && { echo "${exact[0]}"; return 0; }

  for name in "${repos_arr[@]}"; do
    [[ "$name" == "$query"* ]] && prefix_matches+=("$name")
  done
  [[ ${#prefix_matches[@]} -eq 1 ]] && { echo "${prefix_matches[0]}"; return 0; }

  for name in "${repos_arr[@]}"; do
    [[ "$name" == *"$query"* ]] && substr_matches+=("$name")
  done
  [[ ${#substr_matches[@]} -eq 1 ]] && { echo "${substr_matches[0]}"; return 0; }

  for name in "${repos_arr[@]}"; do
    stripped="$name"
    for p in "${sorted_prefixes[@]}"; do
      if [[ "$name" == "$p"* ]]; then
        stripped="${name#"$p"}"
        break
      fi
    done
    [[ "$stripped" == "$query" ]] && stripped_matches+=("$name")
  done
  [[ ${#stripped_matches[@]} -eq 1 ]] && { echo "${stripped_matches[0]}"; return 0; }

  # Report ambiguity from whichever non-empty set is genuinely smallest — not a fixed
  # stage-precedence order. exact/prefix/substr nest (exact ⊆ prefix ⊆ substr) and
  # stripped ⊆ substr too, but prefix and stripped are NOT comparable to each other,
  # so a fixed "stripped, then substr, then prefix, then exact" order can report a
  # wider set (substr) when a narrower one (prefix) was also available — compare
  # sizes explicitly instead. When two stages TIE at the same smallest size with
  # disjoint membership, union their candidates (deduplicated) rather than keeping
  # only whichever was checked last — both tied stages' candidates are equally
  # valid ambiguity, and dropping one silently understates it.
  #
  # Written flat (not as a helper taking an array name) deliberately: a nameref
  # passed by name between functions is the exact circular-reference hazard
  # documented elsewhere in this file — not worth reintroducing for four call sites.
  local -a best=()
  local best_size=-1
  local -A best_seen=()
  local n

  if [[ ${#exact[@]} -gt 0 ]]; then
    if [[ $best_size -eq -1 || ${#exact[@]} -lt $best_size ]]; then
      best=("${exact[@]}")
      best_size=${#exact[@]}
      best_seen=()
      for n in "${best[@]}"; do best_seen[$n]=1; done
    elif [[ ${#exact[@]} -eq $best_size ]]; then
      for n in "${exact[@]}"; do [[ -z "${best_seen[$n]:-}" ]] && { best+=("$n"); best_seen[$n]=1; }; done
    fi
  fi
  if [[ ${#prefix_matches[@]} -gt 0 ]]; then
    if [[ $best_size -eq -1 || ${#prefix_matches[@]} -lt $best_size ]]; then
      best=("${prefix_matches[@]}")
      best_size=${#prefix_matches[@]}
      best_seen=()
      for n in "${best[@]}"; do best_seen[$n]=1; done
    elif [[ ${#prefix_matches[@]} -eq $best_size ]]; then
      for n in "${prefix_matches[@]}"; do [[ -z "${best_seen[$n]:-}" ]] && { best+=("$n"); best_seen[$n]=1; }; done
    fi
  fi
  if [[ ${#stripped_matches[@]} -gt 0 ]]; then
    if [[ $best_size -eq -1 || ${#stripped_matches[@]} -lt $best_size ]]; then
      best=("${stripped_matches[@]}")
      best_size=${#stripped_matches[@]}
      best_seen=()
      for n in "${best[@]}"; do best_seen[$n]=1; done
    elif [[ ${#stripped_matches[@]} -eq $best_size ]]; then
      for n in "${stripped_matches[@]}"; do [[ -z "${best_seen[$n]:-}" ]] && { best+=("$n"); best_seen[$n]=1; }; done
    fi
  fi
  if [[ ${#substr_matches[@]} -gt 0 ]]; then
    if [[ $best_size -eq -1 || ${#substr_matches[@]} -lt $best_size ]]; then
      best=("${substr_matches[@]}")
      best_size=${#substr_matches[@]}
      best_seen=()
      for n in "${best[@]}"; do best_seen[$n]=1; done
    elif [[ ${#substr_matches[@]} -eq $best_size ]]; then
      for n in "${substr_matches[@]}"; do [[ -z "${best_seen[$n]:-}" ]] && { best+=("$n"); best_seen[$n]=1; }; done
    fi
  fi

  if [[ ${#best[@]} -gt 0 ]]; then
    _fleet_ambiguous "$f" "$query" "${best[@]}"
    return 2
  fi
  echo "fleet: no repo matches '$query' in fleet '$f' — if you just edited repos/repos.json, run '$f reload'" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Selectors — shared by ls, each, and doctor.
# ---------------------------------------------------------------------------

# _fleet_parse_selectors <fleet> [args...]
# Consumes -g/-m/--dirty/--branch/--from from the given args, setting _SEL_*;
# anything else is left (in order) in the global _SEL_REST array.
#
# Deliberately takes args positionally rather than an array-name-plus-nameref:
# bash treats `local -n x="$name"` as a circular reference whenever the
# caller's own local variable happens to be named the same as the nameref
# variable itself (e.g. both call it "args") — a real gotcha hit during
# development, not a hypothetical one. Globals for the parsed state sidestep
# it entirely.
_fleet_parse_selectors() {
  local f="$1"
  shift
  local -a args=("$@")

  _SEL_GROUPS=()
  _SEL_GLOB=''
  _SEL_DIRTY=false
  _SEL_BRANCH=''
  _SEL_FROM=''
  _SEL_REST=()

  local i=0
  local n=${#args[@]}
  while ((i < n)); do
    case "${args[i]}" in
      # An explicit --opt=value / -g=value form, so a genuinely dash-leading value
      # (e.g. a branch literally named "-foo") has a real way to reach the parser —
      # the bare "-g -foo" form below can never accept it, since it's ambiguous with
      # a missing value followed by another flag.
      -g=* | -m=* | --branch=* | --from=*)
        local opt="${args[i]%%=*}" val="${args[i]#*=}"
        if [[ -z "$val" ]]; then
          echo "fleet: option '$opt' requires a non-empty value" >&2
          return 1
        fi
        case "$opt" in
          -g) _SEL_GROUPS+=("$val") ;;
          -m) _SEL_GLOB="$val" ;;
          --branch) _SEL_BRANCH="$val" ;;
          --from) _SEL_FROM="$val" ;;
        esac
        i=$((i + 1))
        ;;
      -g | -m | --branch | --from)
        local opt="${args[i]}"
        if ((i + 1 >= n)); then
          echo "fleet: option '$opt' requires a value" >&2
          return 1
        fi
        if [[ "${args[i + 1]}" == -* ]]; then
          echo "fleet: option '$opt' got '${args[i + 1]}', which looks like a flag — use '$opt=${args[i + 1]}' if it really starts with '-'" >&2
          return 1
        fi
        if [[ -z "${args[i + 1]}" ]]; then
          echo "fleet: option '$opt' requires a non-empty value" >&2
          return 1
        fi
        case "$opt" in
          -g) _SEL_GROUPS+=("${args[i + 1]}") ;;
          -m) _SEL_GLOB="${args[i + 1]}" ;;
          --branch) _SEL_BRANCH="${args[i + 1]}" ;;
          --from) _SEL_FROM="${args[i + 1]}" ;;
        esac
        i=$((i + 2))
        ;;
      --dirty)
        _SEL_DIRTY=true
        i=$((i + 1))
        ;;
      --)
        # Stop parsing selectors here — everything from '--' onward (including '--'
        # itself) belongs to the caller's own subcommand/shell command, not to us.
        # Without this, a flag like -m in "each -- git commit -m wip" would be
        # silently consumed as a fleet selector instead of passed through, and the
        # command would appear to succeed having quietly selected zero repos.
        _SEL_REST+=("${args[@]:i}")
        break
        ;;
      *)
        _SEL_REST+=("${args[i]}")
        i=$((i + 1))
        ;;
    esac
  done

  if [[ ${#_SEL_GROUPS[@]} -gt 0 ]]; then
    local valid g found
    valid=$(_fleet_groups "$f") || return 1
    for g in "${_SEL_GROUPS[@]}"; do
      found=false
      while IFS= read -r vg; do
        [[ "$vg" == "$g" ]] && { found=true; break; }
      done <<<"$valid"
      if ! $found; then
        echo "fleet: unknown group '$g' for '$f' — valid groups: $(tr '\n' ' ' <<<"$valid")" >&2
        return 1
      fi
    done
  fi

  # Resolve --from through the same fuzzy matcher every other repo-name argument goes
  # through, so a typo or fuzzy name errors instead of silently selecting zero repos.
  if [[ -n "$_SEL_FROM" ]]; then
    _SEL_FROM=$(_fleet_resolve "$f" "$_SEL_FROM") || return 1
  fi
}

# Prints selected repo names (one per line), in manifest order, honoring the
# current _SEL_* selector state.
_fleet_selected_repos() {
  local f="$1"
  _fleet_ensure_loaded "$f" || return 1
  local -n repos_arr="_FLEET_REPOS_$f"
  local -n group_map="_FLEET_GROUP_$f"

  local started=true
  [[ -n "$_SEL_FROM" ]] && started=false

  local name
  for name in "${repos_arr[@]}"; do
    if ! $started; then
      [[ "$name" == "$_SEL_FROM" ]] && started=true
      $started || continue
    fi

    if [[ ${#_SEL_GROUPS[@]} -gt 0 ]]; then
      local match=false g
      for g in "${_SEL_GROUPS[@]}"; do
        [[ "${group_map[$name]}" == "$g" ]] && { match=true; break; }
      done
      $match || continue
    fi

    if [[ -n "$_SEL_GLOB" ]]; then
      # shellcheck disable=SC2053 # intentional glob match, not a literal string compare
      [[ "$name" == $_SEL_GLOB ]] || continue
    fi

    local path
    path=$(_fleet_repo_path "$f" "$name") || continue

    if $_SEL_DIRTY; then
      _fleet_repo_is_cloned "$path" || continue
      _fleet_repo_is_dirty "$path" || continue
    fi

    if [[ -n "$_SEL_BRANCH" ]]; then
      _fleet_repo_is_cloned "$path" || continue
      [[ "$(_fleet_repo_branch "$path")" == "$_SEL_BRANCH" ]] || continue
    fi

    echo "$name"
  done
}

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

_fleet_cd_root() {
  local f="$1"
  _fleet_ensure_loaded "$f" || return 1
  local prev="$PWD"
  cd "${_FLEET_WORKSPACE[$f]}" || return 1
  _FLEET_LASTDIR[$f]="$prev"
}

# Fail with a clear message unless manifest repo $name (fleet $f, already resolved to
# $path) is actually cloned and a real git repo. Shared by _fleet_cd_repo and any
# command that needs to operate on a repo without cd'ing into it first (e.g. aoe).
_fleet_require_cloned() {
  local f="$1" name="$2" path="$3"
  case "$(_fleet_repo_state "$path")" in
    missing)
      echo "fleet: $name is not cloned yet at $path" >&2
      echo "       run: ${_FLEET_WORKSPACE[$f]}/repos/init.sh" >&2
      return 1
      ;;
    not-a-repo)
      echo "fleet: $path exists but is not a git repository (interrupted clone?)" >&2
      echo "       run: ${_FLEET_WORKSPACE[$f]}/repos/init.sh" >&2
      return 1
      ;;
  esac
}

_fleet_cd_repo() {
  local f="$1" name="$2"
  local path
  path=$(_fleet_repo_path "$f" "$name") || return 1
  _fleet_require_cloned "$f" "$name" "$path" || return 1
  local prev="$PWD"
  cd "$path" || return 1
  _FLEET_LASTDIR[$f]="$prev"
}

_fleet_cd_previous() {
  local f="$1"
  local prev="${_FLEET_LASTDIR[$f]:-}"
  if [[ -z "$prev" ]]; then
    echo "fleet: no previous directory recorded for '$f'" >&2
    return 1
  fi
  local cur="$PWD"
  cd "$prev" || return 1
  _FLEET_LASTDIR[$f]="$cur"
}

# Finds which manifest repo a given path is inside (path or an ancestor of
# it matches a repo root); used by `info`.
_fleet_repo_at() {
  local f="$1" path="$2"
  _fleet_ensure_loaded "$f" || return 1
  local -n repos_arr="_FLEET_REPOS_$f"
  local name repo_path real_path
  real_path="$(_fleet_realpath "$path")"
  for name in "${repos_arr[@]}"; do
    repo_path=$(_fleet_repo_path "$f" "$name") || continue
    case "$real_path/" in
      "$(_fleet_realpath "$repo_path")/"*) echo "$name"; return 0 ;;
    esac
  done
  return 1
}

# ---------------------------------------------------------------------------
# Command dispatch, usage, and completion
# ---------------------------------------------------------------------------

_fleet_cmd_usage() {
  local f="$1" cmd="$2"
  echo "usage: $f $cmd ${_FLEET_CMD_FLAGS[$cmd]:-}"
  echo
  echo "${_FLEET_CMD_DESC[$cmd]}"
  if [[ -n "${_FLEET_CMD_LONGHELP[$cmd]:-}" ]]; then
    echo
    echo "${_FLEET_CMD_LONGHELP[$cmd]}"
  fi
}

_fleet_usage() {
  local f="$1"
  cat <<-EOF
	USAGE: $f [-h|--help] <repo> | <command> [args...]

	Navigate and operate on the '$f' fleet's repos.
	  workspace: ${_FLEET_WORKSPACE[$f]}

	NAVIGATION:
	  $f                cd to the workspace root
	  $f <repo>         cd to a repo (fuzzy: exact, prefix, substring, or fleet-prefix-stripped)
	  $f -              cd to the previously-visited repo

	COMMANDS:
	EOF
  local cmd
  for cmd in "${_FLEET_CMD_ORDER[@]}"; do
    printf '  %-14s %s\n' "$cmd" "${_FLEET_CMD_DESC[$cmd]}"
  done
  cat <<-EOF

	Run '$f <command> -h' for command-specific help.
	Cloning is handled by ${_FLEET_WORKSPACE[$f]}/repos/init.sh, not this tool.
	EOF
}

_fleet_dispatch() {
  local f="$1"
  shift
  local cmd="${1:-}"

  case "$cmd" in
    -h | --help)
      _fleet_usage "$f"
      return 0
      ;;
  esac

  # Load the manifest once here, directly in this shell process — not inside a
  # command substitution. Several helpers below (_fleet_resolve, _fleet_repo_path,
  # ...) are invoked as `x=$(...)`, which forks a subshell; any manifest-cache
  # population a subshell performs is local to that subshell and vanishes when
  # it exits. Loading up front guarantees every helper this dispatch calls —
  # subshelled or not — sees an already-warm cache in the real shell.
  _fleet_ensure_loaded "$f" || return 1

  case "$cmd" in
    '')
      _fleet_cd_root "$f"
      return $?
      ;;
    -)
      _fleet_cd_previous "$f"
      return $?
      ;;
  esac
  shift

  if declare -F "_fleet_cmd_$cmd" >/dev/null 2>&1; then
    "_fleet_cmd_$cmd" "$f" "$@"
    return $?
  fi

  local resolved rc
  resolved=$(_fleet_resolve "$f" "$cmd")
  rc=$?
  if [[ "$rc" -eq 0 ]]; then
    _fleet_cd_repo "$f" "$resolved"
    return $?
  fi
  # _fleet_resolve already printed its own diagnostic. rc=2 means "matched several" —
  # the name plainly IS a repo, just an ambiguous one, so the candidate list already
  # printed is the actionable next step; adding "not a known command or repo" there
  # would flatly contradict it. Only add that hint for genuine no-match (rc=1), since
  # the overwhelmingly likely way to reach that is a mistyped *command*, not a repo.
  if [[ "$rc" -eq 1 ]]; then
    echo "fleet: '$cmd' is not a known command or repo in '$f' — run '$f --help' to list commands" >&2
  fi
  return 1
}

_fleet_complete() {
  local f="$1"
  local cur
  cur="${COMP_WORDS[COMP_CWORD]}"

  if ((COMP_CWORD == 1)); then
    local -a names=()
    if _fleet_ensure_loaded "$f" 2>/dev/null; then
      local -n repos_arr="_FLEET_REPOS_$f"
      names=("${repos_arr[@]}")
    fi
    COMPREPLY=($(compgen -W "${_FLEET_CMD_ORDER[*]} ${names[*]} -h --help" -- "$cur"))
    return
  fi

  local cmd="${COMP_WORDS[1]}"

  if [[ "$cmd" == "wt" ]]; then
    local -a changes=()
    local workspace="${_FLEET_WORKSPACE[$f]}"
    local d
    if [[ "${_FLEET_WORKTREE[$f]}" == "central" ]]; then
      for d in "$workspace"/repos/.worktrees/*/; do
        [[ -d "$d" ]] && changes+=("$(basename "$d")")
      done
    else
      for d in "$workspace"/repos/*/*-worktrees/*/; do
        [[ -d "$d" ]] && changes+=("$(basename "$d")")
      done
    fi
    COMPREPLY=($(compgen -W "${changes[*]}" -- "$cur"))
    return
  fi

  # Everything else derives from the command's own registered flags — never a second,
  # hand-maintained list — so completion cannot drift from what a command actually
  # accepts the way a hardcoded per-command flag string could.
  local flags="${_FLEET_CMD_FLAGS[$cmd]:-}"
  if [[ -z "$flags" ]]; then
    return
  fi

  if [[ "${COMP_WORDS[COMP_CWORD - 1]}" == "-g" && "$flags" == *"-g"* ]]; then
    COMPREPLY=($(compgen -W "$(_fleet_groups "$f" 2>/dev/null | tr '\n' ' ')" -- "$cur"))
    return
  fi

  # Strip descriptive placeholders (e.g. "<subcommand>|<shell command>") out of a
  # longhelp-style flags string — only real flag tokens are useful as completions.
  local -a words=()
  local w
  for w in $flags; do
    [[ "$w" == -* || "$w" == "--" ]] && words+=("$w")
  done
  COMPREPLY=($(compgen -W "${words[*]}" -- "$cur"))
}

# ---------------------------------------------------------------------------
# Discovery commands
# ---------------------------------------------------------------------------

_fleet_meta where "Print a repo's absolute path (no cd)" '<repo> --json'
_fleet_cmd_where() {
  local f="$1"
  shift
  local query='' as_json=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" where; return 0 ;;
      --json) as_json=true; shift ;;
      -*)
        echo "fleet: where: unrecognized option '$1'" >&2
        return 1
        ;;
      *)
        if [[ -n "$query" ]]; then
          echo "fleet: where: too many arguments (already have '$query', got '$1')" >&2
          return 1
        fi
        query="$1"
        shift
        ;;
    esac
  done

  if [[ -z "$query" ]]; then
    echo "fleet: where: a repo name is required" >&2
    _fleet_cmd_usage "$f" where
    return 1
  fi

  _fleet_ensure_loaded "$f" || return 1
  local name path
  name=$(_fleet_resolve "$f" "$query") || return 1
  path=$(_fleet_repo_path "$f" "$name") || return 1

  if $as_json; then
    jq -n --arg name "$name" --arg path "$path" '{name: $name, path: $path}'
  else
    echo "$path"
  fi
}

# Lowercases and replaces every run of non-alphanumeric characters with a single "-",
# trimming leading/trailing "-" — used to turn a free-form -t/--title into a git-branch-
# safe worktree name. Falls back to "session" rather than an empty string.
_fleet_slugify() {
  local s="${1,,}"
  s="$(sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' <<<"$s")"
  echo "${s:-session}"
}

# Populates the global _FLEET_AOE_WT_ARGS array with the -w/-b/--base-branch flags to
# inject ahead of the caller's own forwarded args, unless those args already specify
# -w/--worktree themselves (which always wins — nothing is injected in that case). A
# global scratch variable, not a by-name nameref handoff — see "Nameref pitfalls" in
# CLAUDE.md for why that pattern is avoided here.
_fleet_aoe_default_worktree_args() {
  local f="$1" default_name="$2"
  shift 2

  _FLEET_AOE_WT_ARGS=()

  local -a args=("$@")
  local i title=""
  for ((i = 0; i < ${#args[@]}; i++)); do
    case "${args[i]}" in
      -w | --worktree) return 0 ;;
      -t | --title) title="${args[i + 1]:-}" ;;
    esac
  done

  local branch
  if [[ -n "$title" ]]; then
    branch="$(_fleet_slugify "$title")"
  else
    branch="${default_name}-$(date +%Y%m%d%H%M%S)"
  fi

  _FLEET_AOE_WT_ARGS=(-w "$branch" -b)
  [[ -n "${_FLEET_BRANCH[$f]:-}" ]] && _FLEET_AOE_WT_ARGS+=(--base-branch "${_FLEET_BRANCH[$f]}")
}

_fleet_meta aoe 'Launch an aoe agent session for a repo, always in its own aoe-managed worktree' '<repo> [args forwarded to "aoe add"]' \
  'Resolves <repo> the same way plain navigation does (fuzzy: exact, prefix, substring, or
fleet-prefix-stripped), then runs "aoe add <path> -l" to create and launch an
Agent-of-Empires session rooted there. Every session gets its own aoe-managed worktree
by default (via aoe'"'"'s own -w/-b flags, never raw git commands, so aoe'"'"'s own cleanup
tooling actually sees it) unless the forwarded args already include -w/--worktree, in
which case that takes precedence and nothing is injected. The default branch name comes
from -t/--title if given (slugified), otherwise "<repo>-<timestamp>". This is not
cosmetic: aoe identifies which live Claude Code conversation belongs to a pane by
watching the shared, cwd-keyed transcript directory, and two sessions sharing one
un-worktreed directory can have their conversations misattributed to each other — see
CLAUDE.md. Anything after <repo> is forwarded verbatim to "aoe add" (e.g. --tool,
--base-branch) — see "aoe add --help".'
_fleet_cmd_aoe() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" aoe; return 0 ;;
  esac

  local query="${1:-}"
  if [[ -z "$query" ]]; then
    echo "fleet: aoe: a repo name is required" >&2
    _fleet_cmd_usage "$f" aoe
    return 1
  fi
  shift

  _fleet_require_tool aoe "Install it and make sure its directory is on PATH." || return 1
  _fleet_ensure_loaded "$f" || return 1

  local name path
  name=$(_fleet_resolve "$f" "$query") || return 1
  path=$(_fleet_repo_path "$f" "$name") || return 1
  _fleet_require_cloned "$f" "$name" "$path" || return 1

  _fleet_aoe_default_worktree_args "$f" "$name" "$@"
  aoe add "$path" -l "${_FLEET_AOE_WT_ARGS[@]}" "$@"
}

# Prints the on-disk path of the worktree checked out on branch $2 in repo $1, or
# nothing if no such worktree exists.
_fleet_aoe_orch_slot_path() {
  local workspace="$1" branch="$2"
  git -C "$workspace" worktree list --porcelain | awk -v b="refs/heads/$branch" '
    /^worktree / { p = $2 }
    $0 == "branch " b { print p; exit }
  '
}

# Prints "<title> (<state>)" for the live or archived (non-trashed) aoe session whose
# path is $1, or nothing if none.
_fleet_aoe_orch_occupant() {
  aoe list --json --state=all 2>/dev/null \
    | jq -r --arg p "$1" '.[] | select(.path == $p and .state != "trashed") | "\(.title) (\(.state))"' \
    | head -1
}

_fleet_meta aoe-orchestrator \
  'Launch an aoe session in an isolated orchestrator worktree of the workspace repo itself (scope not yet known to one member repo)' \
  '[--list] [-n <count>] [args forwarded to "aoe add"]' \
  'Unlike "aoe <repo>", which resolves to one member repo, this worktrees the fleet
workspace repo itself — never a member repo, since scope is not yet known — into a
small, reused pool of slots, each on branch "orchestrator-<n>" (default pool size 5,
override with -n/--count). Slots are created and reclaimed entirely through aoe'"'"'s own
-w/-b flags, never raw git commands — see CLAUDE.md for why that distinction matters
for aoe'"'"'s own cleanup tooling. Occupancy is checked against git'"'"'s own worktree list
(does a worktree for this branch exist) cross-referenced with "aoe list --json" (does a
live or archived session still use that path) — not by title, so -t/--title in your own
forwarded args is free to set whatever display title you want per session. If a slot'"'"'s
branch/worktree exists but no live or archived session claims it (a prior session was
removed without --delete-worktree/--delete-branch), runs "aoe worktree cleanup -f" once
to reclaim it before retrying that slot. If every slot is genuinely occupied, reports
which session holds each one and exits rather than silently growing the pool —
archive/remove one, or pass a larger -n. "<fleet> aoe-orchestrator --list" shows slot
occupancy without claiming one. Anything after the recognized flags is forwarded
verbatim to "aoe add" (e.g. -t/--title, --tool) — see "aoe add --help".'
_fleet_cmd_aoe-orchestrator() {
  local f="$1"
  shift

  local list_only=false
  local count=5
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" aoe-orchestrator; return 0 ;;
      --list)
        list_only=true
        shift
        ;;
      -n | --count)
        if [[ $# -lt 2 ]]; then
          echo "fleet: aoe-orchestrator: '$1' requires a value" >&2
          return 1
        fi
        count="$2"
        shift 2
        ;;
      --)
        shift
        break
        ;;
      *) break ;;
    esac
  done

  _fleet_require_tool aoe "Install it and make sure its directory is on PATH." || return 1
  _fleet_require_tool jq "Install it with: apt-get install jq  OR  brew install jq" || return 1
  _fleet_ensure_loaded "$f" || return 1

  local workspace="${_FLEET_WORKSPACE[$f]}"
  _fleet_repo_is_cloned "$workspace" || {
    echo "fleet: aoe-orchestrator: workspace repo not found at $workspace" >&2
    return 1
  }

  local -a base_branch_args=()
  [[ -n "${_FLEET_BRANCH[$f]:-}" ]] && base_branch_args=(--base-branch "${_FLEET_BRANCH[$f]}")

  local i slot_branch slot_path occupant cleaned_once=false claimed=false
  for ((i = 1; i <= count; i++)); do
    slot_branch="orchestrator-$i"
    slot_path=$(_fleet_aoe_orch_slot_path "$workspace" "$slot_branch")
    occupant=""
    [[ -n "$slot_path" ]] && occupant=$(_fleet_aoe_orch_occupant "$slot_path")

    if $list_only; then
      if [[ -n "$occupant" ]]; then
        printf '  %-16s busy — %s\n' "$slot_branch" "$occupant"
      elif [[ -n "$slot_path" ]]; then
        printf '  %-16s free (abandoned worktree present — will reclaim on next claim)\n' "$slot_branch"
      else
        printf '  %-16s free\n' "$slot_branch"
      fi
      continue
    fi

    [[ -n "$occupant" ]] && continue

    local out status
    out=$(aoe add "$workspace" -w "$slot_branch" -b "${base_branch_args[@]}" -l "$@" 2>&1)
    status=$?

    if [[ $status -ne 0 ]] && [[ -n "$slot_path" ]] && ! $cleaned_once; then
      # Branch/worktree existed but no session claims it — orphaned by a prior removal
      # that skipped --delete-worktree/--delete-branch. Reclaim once, then retry.
      echo "fleet: aoe-orchestrator: $slot_branch looks abandoned, reclaiming via 'aoe worktree cleanup -f'..." >&2
      aoe worktree cleanup -f >&2
      cleaned_once=true
      out=$(aoe add "$workspace" -w "$slot_branch" -b "${base_branch_args[@]}" -l "$@" 2>&1)
      status=$?
    fi

    if [[ $status -eq 0 ]]; then
      echo "$out"
      claimed=true
      break
    fi

    echo "fleet: aoe-orchestrator: failed to claim $slot_branch:" >&2
    echo "$out" >&2
  done

  $list_only && return 0
  $claimed && return 0

  echo "fleet: aoe-orchestrator: all $count slots busy or failed:" >&2
  for ((i = 1; i <= count; i++)); do
    slot_branch="orchestrator-$i"
    slot_path=$(_fleet_aoe_orch_slot_path "$workspace" "$slot_branch" 2>/dev/null)
    occupant=""
    [[ -n "$slot_path" ]] && occupant=$(_fleet_aoe_orch_occupant "$slot_path" 2>/dev/null)
    printf '  %-16s %s\n' "$slot_branch" "${occupant:-?}" >&2
  done
  echo "fleet: aoe-orchestrator: archive/remove one, or pass -n <larger count>" >&2
  return 1
}

_fleet_meta ls 'List repos (name, group, branch, dirty)' '-g -m --dirty --branch --from --json'
_fleet_cmd_ls() {
  local f="$1"
  shift
  _fleet_parse_selectors "$f" "$@" || return 1

  local as_json=false a
  for a in "${_SEL_REST[@]}"; do
    case "$a" in
      -h | --help) _fleet_cmd_usage "$f" ls; return 0 ;;
      --json) as_json=true ;;
      *)
        echo "fleet: ls: unrecognized option '$a'" >&2
        return 1
        ;;
    esac
  done

  _fleet_ensure_loaded "$f" || return 1
  local -n group_map="_FLEET_GROUP_$f"

  local name path branch dirty state
  local -a json_items=()
  while IFS= read -r name; do
    path=$(_fleet_repo_path "$f" "$name") || continue
    state=$(_fleet_repo_state "$path")
    if [[ "$state" == "ok" ]]; then
      branch=$(_fleet_repo_branch "$path")
      if _fleet_repo_is_dirty "$path"; then dirty=true; else dirty=false; fi
    else
      branch="(${state//-/ })"
      # Not measured, not "clean" — a repo that isn't on disk at all is not the
      # same thing as a clean checkout, and a consumer filtering on dirty==false
      # should not silently treat "missing" the same as "verified clean".
      dirty=''
    fi

    if $as_json; then
      json_items+=("$(jq -n --arg name "$name" --arg group "${group_map[$name]}" \
        --arg branch "$branch" --arg dirty "$dirty" \
        '{name: $name, group: $group, branch: $branch,
          dirty: ($dirty | if . == "" then null else (. == "true") end)}')")
    else
      local dirty_col='-'
      [[ -n "$dirty" ]] && dirty_col=$($dirty && echo dirty || echo clean)
      printf '%-40s %-12s %-24s %s\n' "$name" "${group_map[$name]}" "$branch" "$dirty_col"
    fi
  done < <(_fleet_selected_repos "$f")

  if $as_json; then
    printf '%s\n' "${json_items[@]}" | jq -s '.'
  fi
}

_fleet_meta info 'Show info about the repo in the current directory' '--json'
_fleet_cmd_info() {
  local f="$1"
  shift
  case "${1:-}" in -h | --help) _fleet_cmd_usage "$f" info; return 0 ;; esac
  local as_json=false
  if [[ -n "${1:-}" ]]; then
    if [[ "$1" == "--json" ]]; then
      as_json=true
    else
      echo "fleet: info: unrecognized option '$1'" >&2
      return 1
    fi
  fi

  _fleet_ensure_loaded "$f" || return 1
  local name
  if ! name=$(_fleet_repo_at "$f" "$PWD"); then
    case "$(_fleet_realpath "$PWD")/" in
      "$(_fleet_realpath "${_FLEET_WORKSPACE[$f]}")/"*)
        echo "fleet: $PWD is inside the '$f' workspace but not a recognized repo root — this could be a worktree checkout, a repo not yet in the manifest, or a stale manifest cache (try '$f reload')" >&2
        ;;
      *)
        echo "fleet: $PWD is not inside a known '$f' repo" >&2
        ;;
    esac
    return 1
  fi
  # _fleet_repo_at is a purely lexical path check; it says nothing about whether git
  # is actually there. Without this, a manifest directory that exists on disk but was
  # never cloned (state "not-a-repo" — the same state ls/doctor/each all detect)
  # reports a confident, wrong "clean, on no branch" result instead of erroring.
  _fleet_require_repo info || return 1

  local -n group_map="_FLEET_GROUP_$f"
  local branch dirty default_branch ahead behind
  branch=$(_fleet_repo_branch "$PWD")
  if _fleet_repo_is_dirty "$PWD"; then dirty=true; else dirty=false; fi
  default_branch="${_FLEET_BRANCH[$f]}"

  # Left unset (rather than defaulted to 0/0) when origin/<default> doesn't exist —
  # never fetched, a different remote name, or a wrong .defaultBranch in the
  # manifest — so that genuinely unmeasured state isn't reported as the same value
  # a real, in-sync repo would have.
  ahead=''
  behind=''
  if git rev-parse --verify "origin/$default_branch" &>/dev/null; then
    read -r ahead behind < <(git rev-list --left-right --count "HEAD...origin/$default_branch" 2>/dev/null)
  fi

  if $as_json; then
    jq -n --arg name "$name" --arg group "${group_map[$name]}" --arg branch "$branch" \
      --argjson dirty "$dirty" --arg ahead "$ahead" --arg behind "$behind" \
      '{name: $name, group: $group, branch: $branch, dirty: $dirty,
        ahead: ($ahead | if . == "" then null else tonumber end),
        behind: ($behind | if . == "" then null else tonumber end)}'
  else
    echo "repo:      $name (${group_map[$name]})"
    echo "branch:    $branch"
    echo "dirty:     $dirty"
    if [[ -z "$ahead" ]]; then
      echo "ahead/behind origin/$default_branch: unknown (no such ref — try 'git fetch')"
    else
      echo "ahead/behind origin/$default_branch: $ahead/$behind"
    fi
  fi
}

_fleet_meta doctor 'Report manifest vs. disk drift and missing tooling' '-g -m --dirty --branch --from --json'
_fleet_cmd_doctor() {
  local f="$1"
  shift
  _fleet_parse_selectors "$f" "$@" || return 1

  local as_json=false a
  for a in "${_SEL_REST[@]}"; do
    case "$a" in
      -h | --help) _fleet_cmd_usage "$f" doctor; return 0 ;;
      --json) as_json=true ;;
      *)
        echo "fleet: doctor: unrecognized option '$a'" >&2
        return 1
        ;;
    esac
  done

  _fleet_ensure_loaded "$f" || return 1
  local workspace="${_FLEET_WORKSPACE[$f]}"
  local -n group_map="_FLEET_GROUP_$f"

  local -a missing=() not_a_repo=() off_branch=() dirty=()
  local name path branch state
  local examined=0

  while IFS= read -r name; do
    examined=$((examined + 1))
    path=$(_fleet_repo_path "$f" "$name") || continue
    state=$(_fleet_repo_state "$path")
    case "$state" in
      missing) missing+=("$name"); continue ;;
      not-a-repo) not_a_repo+=("$name"); continue ;;
    esac
    branch=$(_fleet_repo_branch "$path")
    [[ "$branch" != "${_FLEET_BRANCH[$f]}" ]] && off_branch+=("$name:$branch")
    _fleet_repo_is_dirty "$path" && dirty+=("$name")
  done < <(_fleet_selected_repos "$f")

  local -a scan_groups=()
  if [[ ${#_SEL_GROUPS[@]} -gt 0 ]]; then
    scan_groups=("${_SEL_GROUPS[@]}")
  else
    local -A seen_group=()
    while IFS= read -r a; do
      scan_groups+=("$a")
      seen_group[$a]=1
    done < <(_fleet_groups "$f")
    # Union with actual on-disk group directories: _fleet_groups only knows about
    # groups the manifest itself declares, so a group directory created before
    # it's registered in repos.json would otherwise be invisible to drift
    # detection — and -g can't be used to force it either, since group validation
    # only accepts names _fleet_groups already knows about.
    local d dname
    for d in "$workspace/repos"/*/; do
      [[ -d "$d" ]] || continue
      dname="${d%/}"
      dname="${dname##*/}"
      [[ -n "${seen_group[$dname]:-}" ]] || scan_groups+=("$dname")
    done
  fi

  # -m/--dirty/--branch narrow this scan the same way they narrow the manifest-repo
  # scan above, for consistency. --from doesn't apply here: it means "resume a
  # manifest-ordered run," and these are directories with no manifest order at all.
  local -a untracked=()
  local group groupdir entry entry_path
  for group in "${scan_groups[@]}"; do
    groupdir="$workspace/repos/$group"
    [[ -d "$groupdir" ]] || continue
    for entry in "$groupdir"/*/; do
      [[ -d "$entry" ]] || continue
      entry="${entry%/}"
      entry="${entry##*/}"
      # Compare against the SPECIFIC group being scanned, not manifest membership in
      # any group — a repo name misplaced under the wrong group folder on disk is
      # drift too, and membership-anywhere would silently miss it.
      [[ "${group_map[$entry]:-}" == "$group" ]] && continue

      if [[ -n "$_SEL_GLOB" ]]; then
        # shellcheck disable=SC2053
        [[ "$entry" == $_SEL_GLOB ]] || continue
      fi
      entry_path="$groupdir/$entry"
      if $_SEL_DIRTY; then
        _fleet_repo_is_cloned "$entry_path" || continue
        _fleet_repo_is_dirty "$entry_path" || continue
      fi
      if [[ -n "$_SEL_BRANCH" ]]; then
        _fleet_repo_is_cloned "$entry_path" || continue
        [[ "$(_fleet_repo_branch "$entry_path")" == "$_SEL_BRANCH" ]] || continue
      fi
      untracked+=("$group/$entry")
    done
  done

  # A manifest repo whose name collides with a registered command word — or with one
  # of dispatch's other reserved tokens (-h/--help/-) — can never be reached via
  # `<fleet> <name>`, since dispatch always tries those first. Scoped to the same
  # selected subset as every other doctor bucket (unlike a plain repos_arr scan,
  # which would ignore -g/-m/--dirty/--branch already applied to this invocation).
  local -a shadowed=()
  while IFS= read -r name; do
    if declare -F "_fleet_cmd_$name" >/dev/null 2>&1; then
      shadowed+=("$name")
    else
      case "$name" in
        -h | --help | -) shadowed+=("$name") ;;
      esac
    fi
  done < <(_fleet_selected_repos "$f")

  local -a missing_tools=()
  local t
  for t in jq git gh mvn; do
    command -v "$t" &>/dev/null || missing_tools+=("$t")
  done
  # grep is always on PATH, but the -P (PCRE) flag branch --filter-pr needs is a GNU
  # extension not guaranteed to exist (e.g. macOS's stock BSD grep rejects it).
  echo | grep -qP '' 2>/dev/null || missing_tools+=("grep -P (PCRE support, needed by 'branch --filter-pr')")

  if $as_json; then
    jq -n \
      --argjson examined "$examined" \
      --arg missing "$(printf '%s\n' "${missing[@]}")" \
      --arg notARepo "$(printf '%s\n' "${not_a_repo[@]}")" \
      --arg untracked "$(printf '%s\n' "${untracked[@]}")" \
      --arg offBranch "$(printf '%s\n' "${off_branch[@]}")" \
      --arg dirty "$(printf '%s\n' "${dirty[@]}")" \
      --arg shadowed "$(printf '%s\n' "${shadowed[@]}")" \
      --arg missingTools "$(printf '%s\n' "${missing_tools[@]}")" \
      '{
        examined: $examined,
        missing: ($missing | split("\n") | map(select(length > 0))),
        notARepo: ($notARepo | split("\n") | map(select(length > 0))),
        untracked: ($untracked | split("\n") | map(select(length > 0))),
        offBranch: ($offBranch | split("\n") | map(select(length > 0))),
        dirty: ($dirty | split("\n") | map(select(length > 0))),
        shadowedByCommand: ($shadowed | split("\n") | map(select(length > 0))),
        missingTools: ($missingTools | split("\n") | map(select(length > 0)))
      }'
  else
    echo "fleet: $f  workspace: $workspace"
    echo
    if [[ ${#missing[@]} -gt 0 ]]; then
      echo "Not cloned (run ${workspace}/repos/init.sh):"
      printf '  %s\n' "${missing[@]}"
    fi
    if [[ ${#not_a_repo[@]} -gt 0 ]]; then
      echo "Present but not a git repo (re-run ${workspace}/repos/init.sh):"
      printf '  %s\n' "${not_a_repo[@]}"
    fi
    if [[ ${#untracked[@]} -gt 0 ]]; then
      echo "On disk, not in manifest:"
      printf '  %s\n' "${untracked[@]}"
    fi
    if [[ ${#off_branch[@]} -gt 0 ]]; then
      echo "Not on default branch (${_FLEET_BRANCH[$f]}):"
      printf '  %s\n' "${off_branch[@]}"
    fi
    if [[ ${#dirty[@]} -gt 0 ]]; then
      echo "Dirty:"
      printf '  %s\n' "${dirty[@]}"
    fi
    if [[ ${#shadowed[@]} -gt 0 ]]; then
      echo "Repo names shadowed by a command (unreachable via '$f <name>'):"
      printf '  %s\n' "${shadowed[@]}"
    fi
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
      echo "Missing tools:"
      printf '  %s\n' "${missing_tools[@]}"
    fi
    if [[ $((${#missing[@]} + ${#not_a_repo[@]} + ${#untracked[@]} + ${#off_branch[@]} + ${#dirty[@]} + ${#shadowed[@]} + ${#missing_tools[@]})) -eq 0 ]]; then
      if ((examined == 0)); then
        echo "No repos matched the given selectors — nothing was examined."
      else
        echo "All clear ($examined repo(s) examined)."
      fi
    fi
  fi
}

_fleet_meta reload 'Re-read repos.json after editing the manifest'
_fleet_cmd_reload() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" reload; return 0 ;;
    "") ;;
    *)
      echo "fleet: reload: unrecognized option '$1'" >&2
      return 1
      ;;
  esac
  unset '_FLEET_LOADED[$f]'
  _fleet_ensure_loaded "$f"
}

# ---------------------------------------------------------------------------
# Worktree navigation
# ---------------------------------------------------------------------------

_fleet_meta wt 'cd into a worktree for a change' '<change> [<repo>]'
_fleet_cmd_wt() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" wt; return 0 ;;
    -*)
      echo "fleet: wt: unrecognized option '$1'" >&2
      return 1
      ;;
  esac

  local change="${1:-}" repo="${2:-}"
  if [[ -z "$change" ]]; then
    _fleet_cmd_usage "$f" wt
    return 1
  fi

  _fleet_ensure_loaded "$f" || return 1
  local workspace="${_FLEET_WORKSPACE[$f]}"
  local style="${_FLEET_WORKTREE[$f]}"

  if [[ -n "$repo" ]]; then
    repo=$(_fleet_resolve "$f" "$repo") || return 1
    local -n group_map="_FLEET_GROUP_$f"
    local group="${group_map[$repo]}"
    local target
    if [[ "$style" == "central" ]]; then
      target="$workspace/repos/.worktrees/$change/$repo"
    else
      target="$workspace/repos/$group/$repo-worktrees/$change"
    fi
    if [[ ! -d "$target" ]]; then
      echo "fleet: no worktree '$change' for '$repo' (looked in: $target)" >&2
      return 1
    fi
    local prev="$PWD"
    cd "$target" || return 1
    _FLEET_LASTDIR[$f]="$prev"
    return 0
  fi

  if [[ "$style" == "central" ]]; then
    local target="$workspace/repos/.worktrees/$change"
    if [[ ! -d "$target" ]]; then
      echo "fleet: no worktree dir for change '$change' (looked in: $target)" >&2
      return 1
    fi
    local prev="$PWD"
    cd "$target" || return 1
    _FLEET_LASTDIR[$f]="$prev"
  else
    local -a found=()
    local g wtdir
    while IFS= read -r g; do
      for wtdir in "$workspace/repos/$g"/*-worktrees/"$change"; do
        [[ -d "$wtdir" ]] && found+=("$wtdir")
      done
    done < <(_fleet_groups "$f")

    case "${#found[@]}" in
      0)
        echo "fleet: no worktrees found for change '$change' (looked in: $workspace/repos/*/*-worktrees/$change)" >&2
        return 1
        ;;
      1)
        local prev="$PWD"
        cd "${found[0]}" || return 1
        _FLEET_LASTDIR[$f]="$prev"
        ;;
      *)
        echo "fleet: '$change' has worktrees in multiple repos — specify one:" >&2
        printf '  %s\n' "${found[@]}" >&2
        return 1
        ;;
    esac
  fi
}

# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------

_fleet_meta each 'Run a subcommand or shell command across selected repos' \
  '-g -m --dirty --branch --from -k --keep-going -- <subcommand>|<shell command>' \
  'Selectors (-g, -m, --dirty, --branch, --from) narrow the repo set. Everything after
them is either a known subcommand (run via the fleet, e.g. "status") or, after --, an
arbitrary shell command run inside each selected repo. Runs serially in manifest order
and stops at the first failure unless -k/--keep-going is given, in which case a summary
of failed repos is printed at the end. The caller'"'"'s working directory is never changed.'
_fleet_cmd_each() {
  local f="$1"
  shift
  _fleet_parse_selectors "$f" "$@" || return 1

  local keep_going=false mode='' sub_name=''
  local -a shell_cmd=() sub_args=()

  local i=0
  local n=${#_SEL_REST[@]}
  while ((i < n)); do
    case "${_SEL_REST[i]}" in
      -h | --help)
        _fleet_cmd_usage "$f" each
        return 0
        ;;
      -k | --keep-going)
        keep_going=true
        i=$((i + 1))
        ;;
      --)
        mode='shell'
        i=$((i + 1))
        shell_cmd=("${_SEL_REST[@]:i}")
        break
        ;;
      *)
        if [[ -z "$mode" ]]; then
          mode='cmd'
          sub_name="${_SEL_REST[i]}"
          i=$((i + 1))
          sub_args=("${_SEL_REST[@]:i}")
          break
        fi
        i=$((i + 1))
        ;;
    esac
  done

  if [[ -z "$mode" ]]; then
    _fleet_cmd_usage "$f" each
    return 1
  fi
  if [[ "$mode" == "shell" && ${#shell_cmd[@]} -eq 0 ]]; then
    echo "fleet: each: '--' requires a command" >&2
    _fleet_cmd_usage "$f" each
    return 1
  fi
  if [[ "$mode" == "cmd" ]]; then
    if ! declare -F "_fleet_cmd_$sub_name" >/dev/null 2>&1; then
      echo "fleet: each: '$sub_name' is not a fleet subcommand; use '-- $sub_name ...' to run it as a shell command. Subcommands: ${_FLEET_CMD_ORDER[*]}" >&2
      return 1
    fi
    # each runs subcommands in a subshell specifically so the caller's cwd survives
    # ("( cd "$path" && ... )"). That means anything whose whole purpose is to mutate
    # the CALLING shell's own state — the manifest cache, cwd — silently no-ops under
    # fan-out while still reporting success, since the mutation happens in a subshell
    # that vanishes.
    case "$sub_name" in
      reload | wt)
        echo "fleet: each: '$sub_name' mutates the calling shell and has no effect under fan-out; run '$f $sub_name' directly instead" >&2
        return 1
        ;;
    esac
  fi

  _fleet_ensure_loaded "$f" || return 1

  local -a failures=()
  local name path status state
  local selected=0 visited=0

  while IFS= read -r name; do
    selected=$((selected + 1))
    path=$(_fleet_repo_path "$f" "$name") || continue
    state=$(_fleet_repo_state "$path")
    if [[ "$state" != "ok" ]]; then
      echo "==> $name (skipped: ${state//-/ } — run ${_FLEET_WORKSPACE[$f]}/repos/init.sh)"
      continue
    fi
    visited=$((visited + 1))

    echo "==> $name"
    if [[ "$mode" == "cmd" ]]; then
      (cd "$path" && "_fleet_cmd_$sub_name" "$f" "${sub_args[@]}")
    else
      (cd "$path" && "${shell_cmd[@]}")
    fi
    status=$?

    if ((status != 0)); then
      failures+=("$name")
      if ! $keep_going; then
        echo "fleet: each: '$name' failed (exit $status); stopping (use -k to continue)" >&2
        return 1
      fi
    fi
  done < <(_fleet_selected_repos "$f")

  if [[ ${#failures[@]} -gt 0 ]]; then
    echo "each: ${#failures[@]} repo(s) failed: ${failures[*]}" >&2
    return 1
  fi
  # A selector that matches zero repos (a typo'd -m glob, or every match skipped as
  # missing/not-a-repo) would otherwise "succeed" having run nothing — indistinguish-
  # able from a real, intentional no-op run over an empty subset.
  if ((visited == 0)); then
    if ((selected == 0)); then
      echo "fleet: each: no repos matched the given selectors" >&2
    else
      echo "fleet: each: $selected repo(s) matched, but none were cloned — nothing ran" >&2
    fi
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Per-repo commands (act on the current working directory)
# ---------------------------------------------------------------------------

_fleet_meta status 'Report git status of the current repo, flagging a non-default branch'
_fleet_cmd_status() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" status; return 0 ;;
    "") ;;
    *)
      echo "fleet: status: unrecognized option '$1'" >&2
      return 1
      ;;
  esac

  _fleet_require_repo status || return 1
  _fleet_require_own_repo "$f" status || return 1
  _fleet_ensure_loaded "$f" || return 1
  _fleet_colors

  local branch
  # _fleet_repo_branch (not a raw `git branch --show-current`) so a detached HEAD
  # renders as the "(detached: <sha>)" sentinel instead of printing no banner at
  # all — round 2 fixed this exact empty-branch conflation in `info`; `status` was
  # the sibling call site that sweep missed, and it's the command most likely to
  # be run fleet-wide under `each`.
  branch=$(_fleet_repo_branch "$PWD")
  if [[ "$branch" != "${_FLEET_BRANCH[$f]}" ]]; then
    # Red for "off the default branch" matches branch -c's convention for the
    # identical condition — the two commands used to disagree (this one used
    # green, which reads as "nominal" and is exactly the wrong signal for the
    # anomaly this line exists to flag, especially scanning `each status` output).
    echo "${_FLEET_C_RED}On branch: $branch${_FLEET_C_NONE}"
  fi
  git status
}

_fleet_meta branch 'Report on the repo'"'"'s branches' \
  '-a --all -c --current -m --merged -n --no-merged -r --remotes -f --filter-pr'
_fleet_cmd_branch() {
  local f="$1"
  shift
  local current=false filterpr=false
  local -a options=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" branch; return 0 ;;
      -a | --all) options+=(--all); shift ;;
      -c | --current) current=true; shift ;;
      -m | --merged) options+=(--merged); shift ;;
      -n | --no-merged) options+=(--no-merged); shift ;;
      -r | --remotes) options+=(--remotes); shift ;;
      -f | --filter-pr) filterpr=true; shift ;;
      *)
        echo "fleet: branch: unrecognized option '$1'" >&2
        return 1
        ;;
    esac
  done

  if $current; then
    _fleet_require_repo branch || return 1
    _fleet_require_own_repo "$f" branch || return 1
    _fleet_ensure_loaded "$f" || return 1
    _fleet_colors
    local cur
    cur=$(git branch --show-current 2>/dev/null)
    if [[ -z "$cur" ]]; then
      echo "${_FLEET_C_RED}(detached HEAD)${_FLEET_C_NONE}"
    elif [[ "$cur" == "${_FLEET_BRANCH[$f]}" ]]; then
      echo "${_FLEET_C_GREEN}${cur}${_FLEET_C_NONE}"
    else
      echo "${_FLEET_C_RED}${cur}${_FLEET_C_NONE}"
    fi
  elif $filterpr; then
    _fleet_require_repo branch || return 1
    if ! echo | grep -qP '' 2>/dev/null; then
      echo "fleet: branch --filter-pr requires a PCRE-capable grep (grep -P)" >&2
      return 1
    fi
    # Capture git's output and status explicitly rather than piping straight into
    # grep -v: grep -v's own exit status (1 when it filters every line — a perfectly
    # legitimate "nothing left after filtering" result) would otherwise be
    # indistinguishable from git itself failing, and under `each` a legitimate empty
    # result would abort the whole fan-out.
    local out
    out=$(git -P branch "${options[@]}") || return $?
    printf '%s\n' "$out" | grep -v -P -e '^\s*((remotes/)?origin/)?pr/\d+'
    return 0
  else
    _fleet_require_repo branch || return 1
    git -P branch "${options[@]}"
  fi
}

_fleet_meta update 'Checkout and pull the default branch' '-c --clean-merged'
_fleet_cmd_update() {
  local f="$1"
  shift
  local clean_merged=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" update; return 0 ;;
      -c | --clean-merged) clean_merged=true; shift ;;
      *)
        echo "fleet: update: unrecognized option '$1'" >&2
        return 1
        ;;
    esac
  done

  _fleet_require_repo update || return 1
  _fleet_require_own_repo "$f" update || return 1
  _fleet_ensure_loaded "$f" || return 1
  local branch="${_FLEET_BRANCH[$f]}"

  if [[ -n "$(git status --porcelain)" ]]; then
    echo "fleet: update: working directory not clean; commit or stash before checking out $branch" >&2
    return 1
  fi
  # Pre-check the ref so a wrong .defaultBranch in the manifest gets a message that
  # names the source and the actual value, instead of git's raw "pathspec did not
  # match any file(s)" — every other precondition in this file gets an explicit
  # "fleet: ..." message; a manifest value handed straight to an external tool with
  # no framing was the one place that wasn't true.
  if ! git rev-parse --verify --quiet "refs/heads/$branch" &>/dev/null && \
     ! git rev-parse --verify --quiet "refs/remotes/origin/$branch" &>/dev/null; then
    echo "fleet: update: default branch '$branch' (from ${_FLEET_WORKSPACE[$f]}/repos/repos.json .defaultBranch) does not exist here; this repo is on '$(git branch --show-current)'" >&2
    return 1
  fi

  local rc=0
  git checkout "$branch" && git pull || rc=$?

  if $clean_merged && ((rc == 0)); then
    local b
    local -a cleanup_failed=()
    while IFS= read -r b; do
      [[ -z "$b" || "$b" == "$branch" ]] && continue
      git branch -d "$b" || cleanup_failed+=("$b")
    done < <(git branch --merged "$branch" --format='%(refname:short)')
    if [[ ${#cleanup_failed[@]} -gt 0 ]]; then
      echo "fleet: update: could not delete merged branch(es): ${cleanup_failed[*]}" >&2
      rc=1
    fi
  fi
  return "$rc"
}

_fleet_meta build 'Build the repo (mvn clean install)' '-k --keep-existing -l --local-m2-repository'
_fleet_cmd_build() {
  local f="$1"
  shift
  local mvn_clean=true local_m2=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" build; return 0 ;;
      -k | --keep-existing) mvn_clean=false; shift ;;
      -l | --local-m2-repository) local_m2=true; shift ;;
      *)
        echo "fleet: build: unrecognized option '$1'" >&2
        return 1
        ;;
    esac
  done

  _fleet_require_tool mvn "Install it with: sdk install maven  OR  brew install maven" || return 1

  if [[ ! -f pom.xml ]]; then
    echo "fleet: build: no pom.xml in $PWD" >&2
    return 1
  fi

  if $mvn_clean; then
    mvn clean || return 1
  fi

  local -a mvn_opts=(install)
  $local_m2 && mvn_opts=(-Dmaven.repo.local=target/m2-repo "${mvn_opts[@]}")
  mvn "${mvn_opts[@]}"
}

_fleet_meta clean 'Run mvn clean in the repo'
_fleet_cmd_clean() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" clean; return 0 ;;
    "") ;;
    *)
      echo "fleet: clean: unrecognized option '$1'" >&2
      return 1
      ;;
  esac
  _fleet_require_tool mvn "Install it with: sdk install maven  OR  brew install maven" || return 1
  if [[ ! -f pom.xml ]]; then
    echo "fleet: clean: no pom.xml in $PWD" >&2
    return 1
  fi
  mvn clean
}

_fleet_meta graph 'Generate a Maven dependency graph' '-d --duplicates -v --versions'
_fleet_cmd_graph() {
  local f="$1"
  shift
  local -a mvn_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" graph; return 0 ;;
      -d | --duplicates) mvn_args+=(-DshowDuplicates); shift ;;
      -v | --versions) mvn_args+=(-DshowVersions); shift ;;
      *)
        echo "fleet: graph: unrecognized option '$1'" >&2
        return 1
        ;;
    esac
  done

  _fleet_require_tool mvn "Install it with: sdk install maven  OR  brew install maven" || return 1
  if [[ ! -f pom.xml ]]; then
    echo "fleet: graph: no pom.xml in $PWD" >&2
    return 1
  fi
  mvn depgraph:graph "${mvn_args[@]}"
}

_fleet_meta dep-tree 'Write the Maven dependency tree to target/dependency-tree.txt'
_fleet_cmd_dep-tree() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" dep-tree; return 0 ;;
    "") ;;
    *)
      echo "fleet: dep-tree: unrecognized option '$1'" >&2
      return 1
      ;;
  esac
  _fleet_require_tool mvn "Install it with: sdk install maven  OR  brew install maven" || return 1
  if [[ ! -f pom.xml ]]; then
    echo "fleet: dep-tree: no pom.xml in $PWD" >&2
    return 1
  fi
  if ! mkdir -p target; then
    echo "fleet: dep-tree: cannot create target/ in $PWD" >&2
    return 1
  fi
  # Maven writes its whole log, including [ERROR] lines, to stdout, not stderr — a
  # bare redirect to the output file makes a failure completely silent to the caller.
  if ! mvn dependency:tree >target/dependency-tree.txt 2>&1; then
    echo "fleet: dep-tree: mvn failed in $PWD; see target/dependency-tree.txt" >&2
    [[ -s target/dependency-tree.txt ]] && tail -20 target/dependency-tree.txt >&2
    return 1
  fi
}

_fleet_meta build-status 'Show recent GitHub Actions runs for the repo'
_fleet_cmd_build-status() {
  local f="$1"
  shift
  case "${1:-}" in
    -h | --help) _fleet_cmd_usage "$f" build-status; return 0 ;;
    "") ;;
    *)
      echo "fleet: build-status: unrecognized option '$1'" >&2
      return 1
      ;;
  esac
  _fleet_require_repo build-status || return 1
  _fleet_require_tool gh "Install it with: https://cli.github.com" || return 1
  gh run list --limit 5
}

_fleet_meta versions 'Bump Maven dependency versions, build, commit, push, and open a PR' \
  '-p --parent -k --keep-branch -l --local -s --skip-build -d --draft-pr -t --title' \
  'By default: checkout the default branch, pull, checkout a new branch, update Maven
property versions (and the parent pom too, with -p), do a sanity build, commit, push,
and open a PR.'
_fleet_cmd_versions() {
  local f="$1"
  shift
  local parent_pom=false keep_branch=false local_only=false build=true draft_pr=false
  local pr_title="Update versions"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h | --help) _fleet_cmd_usage "$f" versions; return 0 ;;
      -p | --parent) parent_pom=true; shift ;;
      -k | --keep-branch) keep_branch=true; shift ;;
      -l | --local) local_only=true; shift ;;
      -s | --skip-build) build=false; shift ;;
      -d | --draft-pr) draft_pr=true; shift ;;
      -t | --title)
        # Bounds-check the value, same class of gap round 1 closed in
        # _fleet_parse_selectors: "-t -d" used to silently swallow both the title
        # (becoming "-d") AND --draft-pr (never seen by this loop again).
        if [[ $# -lt 2 || "$2" == -* ]]; then
          echo "fleet: versions: option '$1' requires a title value" >&2
          return 1
        fi
        pr_title="$2"
        shift 2
        ;;
      *)
        echo "fleet: versions: unrecognized option '$1'" >&2
        return 1
        ;;
    esac
  done

  _fleet_require_repo versions || return 1
  _fleet_require_own_repo "$f" versions || return 1
  _fleet_require_tool mvn "Install it with: sdk install maven  OR  brew install maven" || return 1
  $local_only || _fleet_require_tool gh "Install it with: https://cli.github.com" || return 1

  _fleet_ensure_loaded "$f" || return 1
  local default_branch="${_FLEET_BRANCH[$f]}"
  local current_branch
  current_branch=$(git branch --show-current)
  if [[ -z "$current_branch" ]]; then
    echo "fleet: versions: detached HEAD; checkout a branch first" >&2
    return 1
  fi
  local branch_name="$current_branch"
  local dirty
  dirty=$(git status --porcelain)

  if ! $keep_branch; then
    if [[ -n "$dirty" ]]; then
      { echo "fleet: versions: working directory not clean:"; echo "  ${dirty//$'\n'/$'\n'  }"; } >&2
      return 1
    fi
    branch_name="versions-${RANDOM}"
    if [[ "$current_branch" != "$default_branch" ]]; then
      git checkout "$default_branch" || return 1
    fi
    git pull || return 1
    git checkout -b "$branch_name" || return 1
  else
    # -k means "reuse the versions branch I'm already on" — it is meaningless (and
    # dangerous) on the default branch itself: without a fresh versions-* branch,
    # nothing below keeps this commit off the default branch. The commit further
    # down is a shared `git commit -am`, which would sweep any unrelated dirty
    # tracked file into the version bump — so this path requires a clean tree same
    # as the default path, it just skips creating a new branch and the
    # checkout-default+pull dance.
    if [[ "$current_branch" == "$default_branch" ]]; then
      echo "fleet: versions: -k/--keep-branch cannot be used on the default branch ($default_branch)" >&2
      return 1
    fi
    if [[ -n "$dirty" ]]; then
      { echo "fleet: versions: working directory not clean:"; echo "  ${dirty//$'\n'/$'\n'  }"; } >&2
      return 1
    fi
    echo "Keeping current branch [$branch_name]."
  fi

  local -a mvn_goals=(versions:update-properties versions:commit)
  $parent_pom && mvn_goals=(versions:update-parent "${mvn_goals[@]}")
  if ! mvn -U "${mvn_goals[@]}"; then
    # Recommend discarding the WORKING TREE first, before any branch switch — a
    # checkout-then-delete (the old advice here) can carry the partial edit onto
    # the branch you switch to instead of discarding it. Under -k, branch_name is
    # the caller's own pre-existing branch, not one this run created — telling them
    # to -D it would be actively dangerous, not a discard instruction.
    if $keep_branch; then
      echo "fleet: versions: dependency update failed on your branch $branch_name; nothing was created to discard here — inspect with 'git status', discard the partial bump with 'git checkout -- .' if needed" >&2
    else
      echo "fleet: versions: dependency update failed; discard the partial bump first (git checkout -- . && git clean -fd '*.versionsBackup'), then git checkout $default_branch && git branch -D $branch_name" >&2
    fi
    return 1
  fi

  # A prior run may have already committed the bump and then failed at push or PR
  # creation — that branch still carries real, unpushed work, so "the working tree
  # is clean" alone is not "there is nothing to do here": re-checking whether HEAD
  # is already ahead of the default branch is what makes a retry resume instead of
  # silently reporting success while a pushed-but-PR-less branch sits forgotten.
  local ahead_of_default
  ahead_of_default=$(git rev-list --count "$default_branch"..HEAD 2>/dev/null || echo 0)
  local tree_dirty
  [[ -n "$(git status --porcelain)" ]] && tree_dirty=true || tree_dirty=false

  if ! $tree_dirty && [[ "$ahead_of_default" -eq 0 ]]; then
    echo "No modifications to the branch."
    if ! $keep_branch; then
      if ! git checkout "$default_branch"; then
        echo "fleet: versions: could not switch back to $default_branch; still on $branch_name (no changes to lose — retry the checkout, or delete it manually with 'git branch -D $branch_name')" >&2
        return 1
      fi
      if ! git branch -d "$branch_name"; then
        echo "fleet: versions: switched to $default_branch but could not delete $branch_name — it had no changes, so 'git branch -D $branch_name' is safe" >&2
        return 1
      fi
    fi
    return 0
  fi

  if $tree_dirty; then
    if $build; then
      _fleet_cmd_build "$f" || {
        echo "fleet: versions: build failed; the version bump is applied but uncommitted on branch $branch_name" >&2
        echo "       resume: git commit -am 'Update versions' && $f versions -k -s" >&2
        echo "       discard: git checkout -- ." >&2
        return 1
      }
    else
      echo "Skipping sanity build."
    fi

    if $local_only; then
      echo "Skipping git commit and PR creation."
      return 0
    fi

    git commit -am "Update versions" || {
      echo "fleet: versions: commit failed; the version bump is still uncommitted on branch $branch_name" >&2
      return 1
    }
  elif $local_only; then
    echo "Branch $branch_name already has a commit not yet pushed; skipping push/PR creation (--local)."
    return 0
  else
    echo "Branch $branch_name already has a commit not yet pushed or PR'd — resuming from there."
  fi

  local -a gh_opts=()
  $draft_pr && gh_opts+=(--draft)
  if ! git push -u origin "$branch_name"; then
    echo "fleet: versions: push failed; branch $branch_name has a local commit not yet pushed — re-run to retry" >&2
    return 1
  fi
  if ! gh pr create "${gh_opts[@]}" --body "" --title "$pr_title"; then
    echo "fleet: versions: push succeeded but PR creation failed; branch $branch_name is pushed — re-run to retry the PR, or run 'gh pr create' manually" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Fleet registration
# ---------------------------------------------------------------------------

_fleet_register rp \
  --workspace "${RP_WORKSPACE:-$HOME/github/records-platform-workspace}" \
  --prefixes 'records-storage- records-platform- records- slsdata- sls- cds-' \
  --worktree sibling        # repos/<group>/<repo>-worktrees/<change>/

_fleet_register js \
  --workspace "${JS_WORKSPACE:-$HOME/github/java-stack-workspace}" \
  --prefixes 'java-stack-' \
  --worktree central        # repos/.worktrees/<change>/<repo>/
