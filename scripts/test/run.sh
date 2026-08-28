#!/bin/bash
#
# test/run.sh — test harness for fleet-source.sh, no framework beyond fleet-source.sh's
# own dependencies (bats isn't installed, and this is a dotfiles repo — not worth
# adding a dependency for). A few hang-regression guards additionally use GNU
# coreutils' `timeout`; each skips itself with a message if `timeout` isn't on PATH
# (e.g. stock macOS), rather than requiring it.
#
# Builds a fixture workspace with its own repos.json + git repos in a temp dir,
# registers a "tf" test fleet against it, then asserts on resolution, selectors,
# each, and JSON output.
#
# Usage:
#   ./test/run.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091 # dynamically-composed path; verified to resolve at runtime
source "$REPO_ROOT/fleet-source.sh"

PASS=0
FAIL=0

ok() {
  PASS=$((PASS + 1))
  echo "  ok - $1"
}

bad() {
  FAIL=$((FAIL + 1))
  echo "  FAIL - $1"
  [[ -n "${2:-}" ]] && echo "        $2"
}

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    ok "$desc"
  else
    bad "$desc" "expected [$expected], got [$actual]"
  fi
}

assert_status() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    ok "$desc"
  else
    bad "$desc" "expected exit $expected, got $actual"
  fi
}

assert_contains() {
  local desc="$1" haystack="$2" needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    ok "$desc"
  else
    bad "$desc" "expected output to contain [$needle]; got:\n$haystack"
  fi
}

# ---------------------------------------------------------------------------
# Fixture workspace
# ---------------------------------------------------------------------------

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

mkdir -p "$FIXTURE/repos/alpha" "$FIXTURE/repos/beta" "$FIXTURE/repos/gamma"

cat >"$FIXTURE/repos/repos.json" <<'JSON'
{
  "groups": {
    "alpha": {
      "description": "test group alpha",
      "repos": [
        {"name": "foo-widget", "description": "d"},
        {"name": "foo-gadget", "description": "d"}
      ]
    },
    "beta": {
      "description": "test group beta",
      "repos": [
        {"name": "bar-service", "description": "d"},
        {"name": "bar-widget", "description": "collides with foo-widget after prefix-strip"}
      ]
    },
    "gamma": {
      "description": "test group gamma",
      "repos": [
        {"name": "mega-widget-pro", "description": "substring collision, not a prefix-strip collision"},
        {"name": "zzz-gadget-zzz", "description": "unrecognized prefix; makes 'gadget' ambiguous at the substring stage so it can only resolve at the stripped-prefix stage"},
        {"name": "half-clone", "description": "directory present on disk but not a git repo"}
      ]
    }
  },
  "org": "test-org",
  "defaultBranch": "main"
}
JSON

# `git init -q -b main` requires the --initial-branch flag added in git 2.28 (Jul
# 2020); the symbolic-ref form works on any git version.
make_repo() {
  local group="$1" name="$2"
  local d="$FIXTURE/repos/$group/$name"
  mkdir -p "$d"
  git -C "$d" init -q
  git -C "$d" symbolic-ref HEAD refs/heads/main
  git -C "$d" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  git -C "$d" remote add origin "https://example.invalid/$name.git"
}

make_repo alpha foo-widget
make_repo alpha foo-gadget
make_repo beta bar-service
make_repo beta bar-widget
make_repo gamma zzz-gadget-zzz
# mega-widget-pro intentionally left uncloned — exercises the "not cloned" path.

# Present on disk but not a git repo at all — exercises the not-a-repo path,
# distinct from "not cloned" (missing entirely).
mkdir -p "$FIXTURE/repos/gamma/half-clone"

# A directory on disk with no manifest entry — exercises doctor's drift check.
mkdir -p "$FIXTURE/repos/alpha/untracked-thing"
git -C "$FIXTURE/repos/alpha/untracked-thing" init -q >/dev/null
git -C "$FIXTURE/repos/alpha/untracked-thing" symbolic-ref HEAD refs/heads/main

# A repo intentionally left on a non-default branch.
git -C "$FIXTURE/repos/beta/bar-service" checkout -q -b some-feature

# A repo with a genuine uncommitted change.
touch "$FIXTURE/repos/beta/bar-widget/untracked-file.txt"

_fleet_register tf --workspace "$FIXTURE" --prefixes 'foo- bar-' --worktree sibling

START_DIR="$PWD"
cd "$REPO_ROOT" || exit 1

# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

echo "resolution:"
assert_eq "exact match" "foo-widget" "$(_fleet_resolve tf foo-widget)"
assert_eq "unique prefix match" "bar-service" "$(_fleet_resolve tf bar-s)"
assert_eq "unique substring match" "bar-service" "$(_fleet_resolve tf service)"
# "gadget" is deliberately ambiguous at the substring stage (foo-gadget AND
# zzz-gadget-zzz both contain it) and resolves only after stripping a fleet
# prefix — zzz-gadget-zzz doesn't strip (no registered prefix matches it), so
# only foo-gadget survives stage 4. This genuinely exercises stage 4's success
# path, not just its ambiguity path.
assert_eq "unique prefix-stripped match" "foo-gadget" "$(_fleet_resolve tf gadget)"
# Ambiguous (rc=2) and no-match (rc=1) are distinct exit codes so _fleet_dispatch
# can tell them apart: an ambiguous name plainly IS a repo (just an ambiguous one),
# so the "not a known command or repo" hint must not fire for it.
_fleet_resolve tf widget >/dev/null 2>&1
assert_status "ambiguous query returns 2, distinct from no-match" "2" "$?"
assert_contains "ambiguous query lists narrowest candidates" \
  "$(_fleet_resolve tf widget 2>&1)" "foo-widget"
assert_contains "ambiguous query excludes non-colliding substring match" \
  "$(_fleet_resolve tf widget 2>&1)" "bar-widget"
_out="$(_fleet_resolve tf widget 2>&1)"
if [[ "$_out" == *"mega-widget-pro"* ]]; then
  bad "ambiguous query excludes mega-widget-pro (narrower stage should win)" "$_out"
else
  ok "ambiguous query excludes mega-widget-pro (narrower stage should win)"
fi
_fleet_resolve tf nope >/dev/null 2>&1
assert_status "no-match query returns 1" "1" "$?"

# ---------------------------------------------------------------------------
# Navigation (through the registered `tf` entry point, not internals)
# ---------------------------------------------------------------------------

echo "navigation:"
tf gadget >/dev/null
assert_eq "cd to resolved repo" "$FIXTURE/repos/alpha/foo-gadget" "$PWD"
tf - >/dev/null
assert_eq "cd back to previous dir" "$REPO_ROOT" "$PWD"
tf >/dev/null
assert_eq "cd to workspace root with no args" "$FIXTURE" "$PWD"
cd "$REPO_ROOT" || exit 1

tf mega-widget-pro >/dev/null 2>&1
assert_status "cd to uncloned repo fails" "1" "$?"
assert_eq "cwd unchanged after failed cd" "$REPO_ROOT" "$PWD"

_out="$(tf widget 2>&1)"
if [[ "$_out" == *"is not a known command or repo"* ]]; then
  bad "dispatch does not add the no-match hint to an ambiguous query" "$_out"
else
  ok "dispatch does not add the no-match hint to an ambiguous query"
fi
_out="$(tf statsu 2>&1)"
assert_contains "dispatch adds the no-match hint for a genuine miss" "$_out" "is not a known command or repo"

# ---------------------------------------------------------------------------
# aoe (launch an agent-of-empires session for a repo, resolved by fuzzy name)
#
# Never let these tests reach the REAL `aoe` binary — that would create actual
# session state in the developer's own aoe profile. The "missing tool" case uses a
# PATH with no ~/.local/bin on it (git/jq/bash all live under /usr/bin on this
# fixture's target platforms); every other case prepends a stub `aoe` earlier in
# PATH so it's found first.
# ---------------------------------------------------------------------------

echo "aoe:"

_out="$(tf aoe 2>&1)"
assert_status "aoe: repo name required" "1" "$?"
assert_contains "aoe: missing-repo message names the actual reason" "$_out" "a repo name is required"

tf aoe -h >/dev/null 2>&1
assert_status "aoe: -h exits 0" "0" "$?"

_out="$(PATH=/usr/bin:/bin tf aoe foo-widget 2>&1)"
assert_status "aoe: fails when the aoe binary is not on PATH" "1" "$?"
assert_contains "aoe: missing-binary message names the actual reason" "$_out" "aoe is required"

_out="$(tf aoe nope-such-repo 2>&1)"
assert_status "aoe: unresolvable repo fails" "1" "$?"

_out="$(tf aoe mega-widget-pro 2>&1)"
assert_status "aoe: uncloned repo fails" "1" "$?"
assert_contains "aoe: uncloned-repo message names the actual reason" "$_out" "is not cloned yet"

_out="$(tf aoe half-clone 2>&1)"
assert_status "aoe: not-a-repo dir fails" "1" "$?"
assert_contains "aoe: not-a-repo message names the actual reason" "$_out" "is not a git repository"

AOE_STUB_DIR="$(mktemp -d)"
AOE_STUB_LOG="$AOE_STUB_DIR/log"
export AOE_STUB_LOG
cat >"$AOE_STUB_DIR/aoe" <<'STUB'
#!/bin/bash
printf '%s\n' "$@" >"$AOE_STUB_LOG"
STUB
chmod +x "$AOE_STUB_DIR/aoe"

(PATH="$AOE_STUB_DIR:$PATH" tf aoe foo-widget >/dev/null 2>&1)
assert_status "aoe: succeeds for a cloned repo (stubbed aoe binary)" "0" "$?"
assert_eq "aoe: invokes 'aoe add <path> -l' with a default worktree injected" \
  "add
$FIXTURE/repos/alpha/foo-widget
-l
-w" "$(head -4 "$AOE_STUB_LOG")"
assert_contains "aoe: default worktree branch is named after the repo" "$(cat "$AOE_STUB_LOG")" "foo-widget-"
assert_contains "aoe: default worktree creates a new branch (-b)" "$(cat "$AOE_STUB_LOG")" "-b"
assert_contains "aoe: default worktree bases off the fleet's default branch" \
  "$(cat "$AOE_STUB_LOG")" "--base-branch
main"

(PATH="$AOE_STUB_DIR:$PATH" tf aoe foo-widget -t "My Title" >/dev/null 2>&1)
assert_eq "aoe: -t/--title derives a slugified worktree branch name (deterministic, no timestamp)" \
  "$(printf 'add\n%s\n-l\n-w\nmy-title\n-b\n--base-branch\nmain\n-t\nMy Title\n' "$FIXTURE/repos/alpha/foo-widget")" \
  "$(cat "$AOE_STUB_LOG")"

(PATH="$AOE_STUB_DIR:$PATH" tf aoe foo-widget -w "my-own-branch" >/dev/null 2>&1)
assert_eq "aoe: caller's own -w/--worktree suppresses the default injection entirely" \
  "$(printf 'add\n%s\n-l\n-w\nmy-own-branch\n' "$FIXTURE/repos/alpha/foo-widget")" \
  "$(cat "$AOE_STUB_LOG")"

unset AOE_STUB_LOG
rm -rf "$AOE_STUB_DIR"

# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

echo "selectors:"
_fleet_parse_selectors tf -g alpha
assert_eq "parse_selectors: -g captured" "alpha" "${_SEL_GROUPS[0]}"
assert_eq "parse_selectors: no rest args left over" "0" "${#_SEL_REST[@]}"

_fleet_parse_selectors tf -g alpha -g beta status --extra
assert_eq "parse_selectors: repeatable -g" "2" "${#_SEL_GROUPS[@]}"
assert_eq "parse_selectors: non-selector args preserved" "status" "${_SEL_REST[0]}"
assert_eq "parse_selectors: non-selector args preserved (2)" "--extra" "${_SEL_REST[1]}"

_fleet_parse_selectors tf -g bogus >/dev/null 2>&1
assert_status "parse_selectors: unknown group rejected" "1" "$?"

_fleet_parse_selectors tf -g alpha
_selected="$(_fleet_selected_repos tf | tr '\n' ' ')"
assert_eq "selected_repos: -g alpha only" "foo-widget foo-gadget " "$_selected"

_fleet_parse_selectors tf -m 'bar-*'
_selected="$(_fleet_selected_repos tf | tr '\n' ' ')"
assert_eq "selected_repos: -m glob" "bar-service bar-widget " "$_selected"

_fleet_parse_selectors tf --branch some-feature
_selected="$(_fleet_selected_repos tf | tr '\n' ' ')"
assert_eq "selected_repos: --branch" "bar-service " "$_selected"

_fleet_parse_selectors tf --from bar-service
_selected="$(_fleet_selected_repos tf | tr '\n' ' ')"
assert_eq "selected_repos: --from resumes mid-list" \
  "bar-service bar-widget mega-widget-pro zzz-gadget-zzz half-clone " "$_selected"

_fleet_parse_selectors tf --from nonexistent-repo >/dev/null 2>&1
assert_status "parse_selectors: --from validates the repo (fuzzy-resolved)" "1" "$?"

# ---------------------------------------------------------------------------
# each: cwd preservation, fail-fast, keep-going, subcommand sugar
# ---------------------------------------------------------------------------

echo "each:"
_before="$PWD"
tf each -g alpha -- pwd >/dev/null
assert_eq "each: cwd unchanged after shell-command mode" "$_before" "$PWD"

tf each -g alpha status >/dev/null
assert_eq "each: cwd unchanged after subcommand mode" "$_before" "$PWD"

tf each -g bogus -- pwd >/dev/null 2>&1
assert_status "each: rejects unknown group" "1" "$?"

tf each -- false >/dev/null 2>&1
assert_status "each: fails fast on first failure" "1" "$?"

_out="$(tf each -- false 2>&1)"
assert_contains "each: fail-fast stops after repo 1" "$_out" "foo-widget"
if [[ "$_out" == *"foo-gadget"* ]]; then
  bad "each: fail-fast does not continue to repo 2" "$_out"
else
  ok "each: fail-fast does not continue to repo 2"
fi

tf each -k -- false >/dev/null 2>&1
assert_status "each: -k still returns failure overall" "1" "$?"
_out="$(tf each -k -g alpha -- false 2>&1)"
assert_contains "each: -k visits every selected repo" "$_out" "foo-gadget"

_out="$(tf each -g gamma -- pwd 2>&1)"
assert_status "each: skips missing/not-a-repo without failing" "0" "$?"
assert_contains "each: distinct skip message for missing" "$_out" "mega-widget-pro (skipped: missing"
assert_contains "each: distinct skip message for not-a-repo" "$_out" "half-clone (skipped: not a repo"
assert_contains "each: runs the one cloned repo in a mixed group" "$_out" "zzz-gadget-zzz"

tf each --from typo-not-a-repo -- pwd >/dev/null 2>&1
assert_status "each: --from rejects an unresolvable repo" "1" "$?"

tf each -h >/dev/null
assert_status "each: -h exits 0" "0" "$?"

_out="$(tf each git-status-typo 2>&1)"
assert_status "each: unknown subcommand fails" "1" "$?"
assert_contains "each: unknown-subcommand message suggests the -- escape" "$_out" "-- git-status-typo"

# A flag belonging to the shell command after -- (e.g. git commit's own -m) must not
# be misparsed as a fleet selector (-m <glob>) — that would silently select zero
# repos and report success without running anything.
_out="$(tf each -g alpha -- echo -m wip 2>&1)"
assert_status "each --: does not misparse the command's own flags as selectors" "0" "$?"
assert_contains "each --: the command's flag reaches the command, not the selector" "$_out" "-m wip"

tf each -- >/dev/null 2>&1
assert_status "each: bare '--' with no command is rejected" "1" "$?"

_out="$(tf each reload 2>&1)"
assert_status "each: rejects reload as a subcommand (mutates the calling shell)" "1" "$?"
assert_contains "each: reload rejection names the actual reason" "$_out" "mutates the calling shell"

# Bare "wt" (no <change> arg) would ALSO fail for an unrelated reason (wt's own
# missing-argument check), so a bare exit-code assertion here can't tell "each
# correctly refused wt" apart from "wt errored for some other reason once each let
# it through" — pin to the guard's specific message instead.
_out="$(tf each wt somechange 2>&1)"
assert_status "each: rejects wt as a subcommand (mutates the calling shell)" "1" "$?"
assert_contains "each: wt rejection names the actual reason" "$_out" "mutates the calling shell"

# ---------------------------------------------------------------------------
# JSON output validity
# ---------------------------------------------------------------------------

echo "json:"
if command -v jq &>/dev/null; then
  assert_jq() {
    local desc="$1" json="$2" filter="$3"
    if echo "$json" | jq -e "$filter" >/dev/null 2>&1; then
      ok "$desc"
    else
      bad "$desc" "$json"
    fi
  }

  _json="$(tf ls --json)"
  assert_jq "ls --json: valid JSON array with 7 entries" "$_json" '. | length == 7'

  _json="$(tf doctor --json)"
  assert_jq "doctor --json: missing repo reported" "$_json" '.missing == ["mega-widget-pro"]'
  assert_jq "doctor --json: not-a-repo dir reported" "$_json" '.notARepo == ["half-clone"]'
  assert_jq "doctor --json: untracked dir reported" "$_json" '.untracked == ["alpha/untracked-thing"]'
  assert_jq "doctor --json: offBranch is an exact match, not just present" "$_json" \
    '.offBranch == ["bar-service:some-feature"]'
  assert_jq "doctor --json: dirty is an exact match, not just present" "$_json" \
    '.dirty == ["bar-widget"]'

  _json="$(tf where service --json)"
  assert_jq "where --json: returns the resolved path" "$_json" \
    ".path == \"$FIXTURE/repos/beta/bar-service\""
else
  echo "  (skipped — jq not installed)"
fi

# ---------------------------------------------------------------------------
# where / doctor text output
# ---------------------------------------------------------------------------

echo "where/doctor:"
assert_eq "where: prints path without cd" \
  "$FIXTURE/repos/beta/bar-service" "$(tf where service)"
assert_eq "where: cwd unaffected" "$REPO_ROOT" "$PWD"

_out="$(tf doctor)"
assert_contains "doctor: flags uncloned repo" "$_out" "mega-widget-pro"
assert_contains "doctor: flags not-a-repo dir distinctly from uncloned" "$_out" "half-clone"
assert_contains "doctor: flags untracked dir" "$_out" "alpha/untracked-thing"
assert_contains "doctor: flags off-branch repo" "$_out" "bar-service:some-feature"
assert_contains "doctor: flags dirty repo" "$_out" "bar-widget"

_out="$(tf doctor -g alpha)"
if [[ "$_out" == *"half-clone"* ]]; then
  bad "doctor: -g scopes the untracked/not-a-repo scan too" "$_out"
else
  ok "doctor: -g scopes the untracked/not-a-repo scan too"
fi

tf ls --dirtyy >/dev/null 2>&1
assert_status "ls: rejects an unrecognized option" "1" "$?"
tf doctor --jsn >/dev/null 2>&1
assert_status "doctor: rejects an unrecognized option" "1" "$?"

# ---------------------------------------------------------------------------
# ls / update exit-status fixes
# ---------------------------------------------------------------------------

echo "exit status:"
tf ls >/dev/null 2>&1
assert_status "ls: exits 0 in non-JSON mode" "0" "$?"

# foo-widget's remote is the RFC 2606 reserved test TLD "example.invalid",
# guaranteed to never resolve — `git pull` fails fast and deterministically,
# giving a reliable way to test that a real failure propagates. Assert nonzero,
# not a specific literal value: the exact number is git's own exit code for a
# DNS-resolution failure, an implementation detail of git/curl, not something
# fleet-source.sh computes — pinning to "1" would risk a spurious failure on a
# different git version/transport unrelated to any real regression here.
(cd "$FIXTURE/repos/alpha/foo-widget" && tf update >/dev/null 2>&1)
_rc=$?
if [[ "$_rc" -ne 0 ]]; then
  ok "update: returns nonzero when pull fails"
else
  bad "update: returns nonzero when pull fails" "expected nonzero, got 0"
fi

_out="$(tf each -g alpha update 2>&1)"
assert_status "each: propagates an update failure" "1" "$?"
assert_contains "each: reports which repo failed" "$_out" "foo-widget"

# ---------------------------------------------------------------------------
# Isolated fixtures for checks that would otherwise ripple through every
# repo-count-based assertion above if added to the main "tf" fixture.
# ---------------------------------------------------------------------------

echo "isolated fixtures:"
_fleet_register bogus_worktree --workspace /tmp --prefixes '' --worktree nonsense >/dev/null 2>&1
assert_status "_fleet_register: rejects an invalid --worktree value" "1" "$?"

# A value-taking flag with no value left must error, not spin forever: shift 2 on
# $#==1 silently fails to shift, so a missing bounds-check hangs the whole shell at
# source time. The timeout is the regression detector — a hang manifests as this
# whole test run timing out rather than one FAIL line. `timeout` (GNU coreutils)
# isn't part of the "zero dependency" test harness proper — it's an optional guard
# for this one class of regression, so skip it rather than hang the run on a
# machine (e.g. stock macOS) that doesn't have it.
if command -v timeout &>/dev/null; then
  timeout 5 bash -c "source '$REPO_ROOT/fleet-source.sh'; _fleet_register hangtest --prefixes '' --worktree sibling --workspace" >/dev/null 2>&1
  assert_status "_fleet_register: does not hang when a flag's value is omitted" "1" "$?"
else
  echo "  (skipped — 'timeout' not installed)"
fi

# --workspace missing entirely, or explicitly empty (e.g. `RP_WORKSPACE= rp ls`), must
# both be rejected — an empty workspace turns every "$PWD/" == "${_FLEET_WORKSPACE[$f]}/"*
# own-repo prefix-match into matching every absolute path.
_fleet_register noworkspace --prefixes '' --worktree sibling >/dev/null 2>&1
assert_status "_fleet_register: rejects a missing --workspace" "1" "$?"
_fleet_register noworkspace --workspace '' --prefixes '' --worktree sibling >/dev/null 2>&1
assert_status "_fleet_register: rejects an explicitly empty --workspace" "1" "$?"

# Defense in depth: even if a fleet's workspace were somehow blanked out after
# registration, _fleet_require_own_repo (which status/branch/update/versions all call)
# must fail closed rather than let its prefix-match degenerate into "everywhere is home".
EMPTYWS_FIXTURE="$(mktemp -d)"
mkdir -p "$EMPTYWS_FIXTURE/repos/g/r"
cat >"$EMPTYWS_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [{"name": "r", "description": "d"}]}}, "org": "x", "defaultBranch": "main"}
JSON
git -C "$EMPTYWS_FIXTURE/repos/g/r" init -q >/dev/null
git -C "$EMPTYWS_FIXTURE/repos/g/r" symbolic-ref HEAD refs/heads/main
git -C "$EMPTYWS_FIXTURE/repos/g/r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
_fleet_register emptywstest --workspace "$EMPTYWS_FIXTURE" --prefixes '' --worktree sibling
# Load the manifest first so _fleet_ensure_loaded's own empty-workspace guard (which
# only runs before the manifest is cached) is already satisfied — isolating the
# assertion to _fleet_require_own_repo's own guard, not that earlier one.
emptywstest ls >/dev/null 2>&1
_FLEET_WORKSPACE[emptywstest]=""
_out="$(cd "$EMPTYWS_FIXTURE/repos/g/r" && emptywstest status 2>&1)"
assert_status "_fleet_require_own_repo: fails closed when workspace is blank" "1" "$?"
assert_contains "_fleet_require_own_repo: names the actual reason" "$_out" "no workspace configured"
rm -rf "$EMPTYWS_FIXTURE"

# A workspace path with a trailing slash must not break the "is $PWD inside the
# workspace" prefix-match every guard/check relies on (a doubled slash can never
# match $PWD, which the kernel always normalizes to single slashes).
TRAILING_FIXTURE="$(mktemp -d)"
mkdir -p "$TRAILING_FIXTURE/repos/g/r"
cat >"$TRAILING_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [{"name": "r", "description": "d"}]}}, "org": "x", "defaultBranch": "main"}
JSON
git -C "$TRAILING_FIXTURE/repos/g/r" init -q >/dev/null
git -C "$TRAILING_FIXTURE/repos/g/r" symbolic-ref HEAD refs/heads/main
git -C "$TRAILING_FIXTURE/repos/g/r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
_fleet_register trailingtest --workspace "$TRAILING_FIXTURE/" --prefixes '' --worktree sibling
(cd "$TRAILING_FIXTURE/repos/g/r" && trailingtest status >/dev/null 2>&1)
assert_status "trailing slash on workspace path does not break status's own-repo check" "0" "$?"
rm -rf "$TRAILING_FIXTURE"

# Duplicate repo name across two groups would silently overwrite the first group's
# entry in the flat name->group map, making its real on-disk repo unreachable.
DUP_FIXTURE="$(mktemp -d)"
mkdir -p "$DUP_FIXTURE/repos/g1" "$DUP_FIXTURE/repos/g2"
cat >"$DUP_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {
  "g1": {"description": "d", "repos": [{"name": "dup", "description": "d"}]},
  "g2": {"description": "d", "repos": [{"name": "dup", "description": "d"}]}
}, "org": "x", "defaultBranch": "main"}
JSON
_fleet_register duptest --workspace "$DUP_FIXTURE" --prefixes '' --worktree sibling
duptest ls >/dev/null 2>&1
assert_status "duplicate repo name across groups is rejected at load time" "1" "$?"
rm -rf "$DUP_FIXTURE"

# The workspace is registered under a symlinked path, but the caller reaches the same
# repo through the real (symlink-resolved) path — a plain string prefix match between
# $PWD and the registered workspace would reject this even though it's genuinely the
# same physical repo. Own-repo checks must resolve both sides first.
SYMLINK_REAL="$(mktemp -d)"
mkdir -p "$SYMLINK_REAL/repos/g/r"
cat >"$SYMLINK_REAL/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [{"name": "r", "description": "d"}]}}, "org": "x", "defaultBranch": "main"}
JSON
git -C "$SYMLINK_REAL/repos/g/r" init -q >/dev/null
git -C "$SYMLINK_REAL/repos/g/r" symbolic-ref HEAD refs/heads/main
git -C "$SYMLINK_REAL/repos/g/r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
SYMLINK_LINK="$(mktemp -u)"
ln -s "$SYMLINK_REAL" "$SYMLINK_LINK"
_fleet_register symlinktest --workspace "$SYMLINK_LINK" --prefixes '' --worktree sibling
_out="$(cd "$SYMLINK_REAL/repos/g/r" && symlinktest status 2>&1)"
assert_status "own-repo check resolves a symlinked workspace against the real path" "0" "$?"
_out="$(cd "$SYMLINK_REAL/repos/g/r" && symlinktest info 2>&1)"
assert_status "info resolves a symlinked workspace against the real path" "0" "$?"
rm -rf "$SYMLINK_REAL"
rm -f "$SYMLINK_LINK"

# A malformed entry (empty/null name, or an empty group key) must be named in a
# per-entry warning, not just silently dropped with the fleet still reporting success
# on its other, valid repos.
MALFORMED_FIXTURE="$(mktemp -d)"
mkdir -p "$MALFORMED_FIXTURE/repos/g"
cat >"$MALFORMED_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {
  "g": {"description": "d", "repos": [
    {"name": "good-repo", "description": "d"},
    {"name": "", "description": "empty name"},
    {"name": null, "description": "null name"}
  ]},
  "": {"description": "d", "repos": [{"name": "orphaned", "description": "empty group key"}]}
}, "org": "x", "defaultBranch": "main"}
JSON
# Regression guard: an earlier draft of the malformed-entry warning put the jq
# program's closing quote and its trailing "$manifest" argument on separate lines
# inside a $(...) — a bare newline there acts as a statement separator, splitting
# it into a bare `jq -r '<program>'` (which then blocks reading stdin) and a second
# no-op statement, hanging every shell that sources this file. Guard with its own
# timeout so a regression here fails this one line instead of hanging the whole run.
if command -v timeout &>/dev/null; then
  timeout 5 bash -c "source '$REPO_ROOT/fleet-source.sh'; _fleet_register hangload --workspace '$MALFORMED_FIXTURE' --prefixes '' --worktree sibling; hangload ls" >/dev/null 2>&1
  assert_status "manifest loading: malformed-entry scan does not hang on load" "0" "$?"
else
  echo "  (skipped — 'timeout' not installed)"
fi

_fleet_register malformedtest --workspace "$MALFORMED_FIXTURE" --prefixes '' --worktree sibling
_out="$(malformedtest ls 2>&1)"
assert_status "malformed entries: fleet still loads on its valid repo" "0" "$?"
assert_contains "malformed entries: warns about the empty-name entry" "$_out" "name=<empty>"
assert_contains "malformed entries: warns about the empty group key" "$_out" "group=<empty>"
assert_contains "malformed entries: still resolves the valid repo" "$_out" "good-repo"
rm -rf "$MALFORMED_FIXTURE"

# Two different resolution stages can tie at the same smallest non-empty size with
# disjoint membership: querying "foo" against foo-one/foo-two (prefix matches, size
# 2) and sls-foo/cds-foo (stripped-prefix matches, size 2 once their registered
# prefixes are removed) must report all four as ambiguous, not silently keep only
# whichever stage the comparison happened to check last.
TIE_FIXTURE="$(mktemp -d)"
mkdir -p "$TIE_FIXTURE/repos/g"
cat >"$TIE_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [
  {"name": "foo-one", "description": "d"},
  {"name": "foo-two", "description": "d"},
  {"name": "sls-foo", "description": "d"},
  {"name": "cds-foo", "description": "d"}
]}}, "org": "x", "defaultBranch": "main"}
JSON
_fleet_register tietest --workspace "$TIE_FIXTURE" --prefixes 'sls- cds-' --worktree sibling
_out="$(_fleet_resolve tietest foo 2>&1)"
_status=$?
assert_status "tied candidate sets: still reports ambiguous (not a false unique match)" "2" "$_status"
for _name in foo-one foo-two sls-foo cds-foo; do
  assert_contains "tied candidate sets: union includes $_name" "$_out" "$_name"
done
rm -rf "$TIE_FIXTURE"

# -k/--keep-branch on the default branch itself would commit straight to it with no
# fresh versions-* branch protecting against exactly that.
VERSIONS_FIXTURE="$(mktemp -d)"
mkdir -p "$VERSIONS_FIXTURE/repos/g/r"
cat >"$VERSIONS_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [{"name": "r", "description": "d"}]}}, "org": "x", "defaultBranch": "main"}
JSON
git -C "$VERSIONS_FIXTURE/repos/g/r" init -q >/dev/null
git -C "$VERSIONS_FIXTURE/repos/g/r" symbolic-ref HEAD refs/heads/main
git -C "$VERSIONS_FIXTURE/repos/g/r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
_fleet_register verstest --workspace "$VERSIONS_FIXTURE" --prefixes '' --worktree sibling
# The fixture has no pom.xml, so an unrelated mvn failure would ALSO exit 1 here —
# a bare exit-code assertion can't distinguish "the -k-on-default-branch guard
# fired" from "it didn't, and something else downstream failed instead" (verified
# by deleting the guard and re-running: the assertion still passed, for the wrong
# reason). Pin to the guard's specific message.
_out="$(cd "$VERSIONS_FIXTURE/repos/g/r" && verstest versions -k -s -l 2>&1)"
assert_status "versions -k refuses on the default branch" "1" "$?"
assert_contains "versions -k rejection names the actual reason" "$_out" "cannot be used on the default branch"
rm -rf "$VERSIONS_FIXTURE"

SHADOW_FIXTURE="$(mktemp -d)"
mkdir -p "$SHADOW_FIXTURE/repos/g"
cat >"$SHADOW_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [
  {"name": "status", "description": "shadows the status command"},
  {"name": "-h", "description": "shadows the dispatch-reserved -h token"}
]}}, "org": "x", "defaultBranch": "main"}
JSON
# Clone the "status" fixture repo — an uncloned repo lands in doctor's "missing"
# bucket too, which previously let this assertion pass even with the
# shadowed-command detection loop deleted entirely (verified by breaking it and
# re-running: the old substring-only assertion still passed). "-h" is deliberately
# left uncloned: shadowed-command detection is purely name-based against the
# command registry, independent of clone state, so the exact-match JSON assertion
# below covers it either way — no need to clone it too.
d="$SHADOW_FIXTURE/repos/g/status"
mkdir -p "$d"
git -C "$d" init -q && git -C "$d" symbolic-ref HEAD refs/heads/main
git -C "$d" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
_fleet_register shadowtest --workspace "$SHADOW_FIXTURE" --prefixes '' --worktree sibling
# jq is a hard dependency of _fleet_ensure_loaded itself (unconditionally, not just
# for --json) — a text-mode fallback here would never really exercise this without
# jq; skip like the main "json:" section above instead of asserting on a
# code path that can't be reached the way it's written.
if command -v jq &>/dev/null; then
  _json="$(shadowtest doctor --json)"
  assert_jq "doctor: shadowedByCommand pins the actual feature, not a substring hit" "$_json" \
    '.shadowedByCommand == ["status", "-h"]'
else
  echo "  (skipped — jq not installed)"
fi
rm -rf "$SHADOW_FIXTURE"

# ---------------------------------------------------------------------------
# aoe-orchestrator — unlike every fixture above, the WORKSPACE root itself must be
# a real git repo here (aoe-orchestrator worktrees the workspace, not a member repo).
# The stubbed `aoe` actually shells out to real git for `add`/`worktree cleanup`, so
# occupancy/reclaim logic (which queries git directly, not aoe) is exercised for
# real rather than mocked away.
# ---------------------------------------------------------------------------

echo "aoe-orchestrator:"

ORCH_FIXTURE="$(mktemp -d)"
mkdir -p "$ORCH_FIXTURE/repos/g/r"
cat >"$ORCH_FIXTURE/repos/repos.json" <<'JSON'
{"groups": {"g": {"description": "d", "repos": [{"name": "r", "description": "d"}]}}, "org": "x", "defaultBranch": "main"}
JSON
git -C "$ORCH_FIXTURE/repos/g/r" init -q && git -C "$ORCH_FIXTURE/repos/g/r" symbolic-ref HEAD refs/heads/main
git -C "$ORCH_FIXTURE/repos/g/r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$ORCH_FIXTURE" init -q && git -C "$ORCH_FIXTURE" symbolic-ref HEAD refs/heads/main
git -C "$ORCH_FIXTURE" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
_fleet_register orchtest --workspace "$ORCH_FIXTURE" --prefixes '' --worktree sibling

AOE_STUB_DIR="$(mktemp -d)"
AOE_STUB_LOG="$AOE_STUB_DIR/log"
AOE_STUB_LIST_JSON="$AOE_STUB_DIR/list.json"
echo '[]' >"$AOE_STUB_LIST_JSON"
export AOE_STUB_LOG AOE_STUB_LIST_JSON
AOE_ORCH_WORKSPACE="$ORCH_FIXTURE"
export AOE_ORCH_WORKSPACE

# A stubbed `aoe` that actually shells out to git for `add` (fails like real aoe
# would if the branch already exists, otherwise creates a real worktree) and
# `worktree cleanup -f` (removes any worktree of $AOE_ORCH_WORKSPACE not referenced
# by a live/archived path in $AOE_STUB_LIST_JSON) — see the comment above.
cat >"$AOE_STUB_DIR/aoe" <<'STUB'
#!/bin/bash
case "$1" in
  add)
    printf '%s\n' "$@" >>"$AOE_STUB_LOG"
    ws="$2"
    branch="" base=""
    for ((i = 1; i <= $#; i++)); do
      arg="${!i}"
      nexti=$((i + 1))
      [[ "$arg" == "-w" ]] && branch="${!nexti}"
      [[ "$arg" == "--base-branch" ]] && base="${!nexti}"
    done
    if git -C "$ws" show-ref --verify --quiet "refs/heads/$branch"; then
      echo "Error: a branch named '$branch' already exists" >&2
      exit 1
    fi
    wtpath="${ws}-orch-wt-${branch}"
    git -C "$ws" worktree add -q -b "$branch" "$wtpath" "${base:-HEAD}" >&2 || exit 1
    echo "Added session: $branch"
    exit 0
    ;;
  list)
    cat "$AOE_STUB_LIST_JSON"
    ;;
  worktree)
    if [[ "$2" == "cleanup" ]]; then
      live_paths="$(jq -r '.[] | select(.state != "trashed") | .path' "$AOE_STUB_LIST_JSON")"
      git -C "$AOE_ORCH_WORKSPACE" worktree list --porcelain | awk '
        /^worktree / { p = $2 }
        /^branch /   { print p "\t" $2 }
      ' | while IFS=$'\t' read -r wtp wtref; do
        [[ "$wtp" == "$AOE_ORCH_WORKSPACE" ]] && continue
        if ! grep -qxF "$wtp" <<<"$live_paths"; then
          git -C "$AOE_ORCH_WORKSPACE" worktree remove --force "$wtp" 2>/dev/null
          git -C "$AOE_ORCH_WORKSPACE" branch -D "${wtref#refs/heads/}" 2>/dev/null
        fi
      done
    fi
    exit 0
    ;;
esac
STUB
chmod +x "$AOE_STUB_DIR/aoe"

# Happy path: no worktrees exist yet, no sessions reported — claims slot 1.
(PATH="$AOE_STUB_DIR:$PATH" orchtest aoe-orchestrator >/dev/null 2>&1)
assert_status "aoe-orchestrator: succeeds when the pool is empty" "0" "$?"
assert_contains "aoe-orchestrator: claims orchestrator-1 first" "$(cat "$AOE_STUB_LOG")" "orchestrator-1"
assert_contains "aoe-orchestrator: passes the fleet's default branch as --base-branch" \
  "$(cat "$AOE_STUB_LOG")" "--base-branch
main"
: >"$AOE_STUB_LOG"

# Busy slot: orchestrator-1 already has a real worktree (the happy-path test above
# claimed it via the stub) and the stubbed list now reports a live session at that
# exact path — must skip to orchestrator-2, not re-claim orchestrator-1.
busy_path="${ORCH_FIXTURE}-orch-wt-orchestrator-1"
cat >"$AOE_STUB_LIST_JSON" <<JSON
[{"title": "some in-flight task", "path": "$busy_path", "state": "live"}]
JSON
(PATH="$AOE_STUB_DIR:$PATH" orchtest aoe-orchestrator >/dev/null 2>&1)
assert_status "aoe-orchestrator: succeeds by moving past a busy slot" "0" "$?"
_log="$(cat "$AOE_STUB_LOG")"
if [[ "$_log" == *"orchestrator-1"* ]]; then
  bad "aoe-orchestrator: does not re-claim a slot with a live session on it" "$_log"
else
  ok "aoe-orchestrator: does not re-claim a slot with a live session on it"
fi
assert_contains "aoe-orchestrator: claims orchestrator-2 instead" "$_log" "orchestrator-2"
: >"$AOE_STUB_LOG"

# --list: reports occupancy without ever invoking `aoe add`.
_out="$(PATH="$AOE_STUB_DIR:$PATH" orchtest aoe-orchestrator --list 2>&1)"
assert_contains "aoe-orchestrator --list: reports the busy slot" "$_out" "orchestrator-1"
assert_contains "aoe-orchestrator --list: reports a free slot" "$_out" "orchestrator-2"
assert_eq "aoe-orchestrator --list: never calls 'aoe add'" "" "$(cat "$AOE_STUB_LOG")"

# Abandoned slot: orchestrator-2 already has a real worktree/branch (the "busy slot"
# test above successfully claimed it via the stub), but list.json still only
# references orchestrator-1's path — orchestrator-2 is now orphaned (worktree exists,
# no session claims it), and must be reclaimed via "aoe worktree cleanup -f" and
# retried rather than skipped.
(PATH="$AOE_STUB_DIR:$PATH" orchtest aoe-orchestrator -n 2 >/dev/null 2>&1)
assert_status "aoe-orchestrator: reclaims and retries an abandoned slot" "0" "$?"
assert_contains "aoe-orchestrator: retried orchestrator-2 after reclaiming it" \
  "$(cat "$AOE_STUB_LOG")" "orchestrator-2"
: >"$AOE_STUB_LOG"

# All slots busy: with a pool of 1 and orchestrator-1 occupied, must fail without
# ever calling `aoe add`, and name the occupant in its error output.
_out="$(PATH="$AOE_STUB_DIR:$PATH" orchtest aoe-orchestrator -n 1 2>&1)"
assert_status "aoe-orchestrator: fails when every slot in the pool is busy" "1" "$?"
assert_contains "aoe-orchestrator: names the occupying session when all slots are busy" \
  "$_out" "some in-flight task"
assert_eq "aoe-orchestrator: never calls 'aoe add' when every slot is busy" "" "$(cat "$AOE_STUB_LOG")"

unset AOE_STUB_LOG AOE_STUB_LIST_JSON AOE_ORCH_WORKSPACE
rm -rf "$AOE_STUB_DIR" "$ORCH_FIXTURE" "${ORCH_FIXTURE}-orch-wt-orchestrator-1" "${ORCH_FIXTURE}-orch-wt-orchestrator-2"

# ---------------------------------------------------------------------------
# Command / usage / completion coverage — every registered command has usage
# text and appears in root usage, so root usage can never drift from the
# command registry (the whole point of the registry idiom).
# ---------------------------------------------------------------------------

echo "registry coverage:"
_usage="$(tf --help)"
_missing=0
for cmd in "${_FLEET_CMD_ORDER[@]}"; do
  if [[ "$_usage" != *"$cmd"* ]]; then
    bad "root usage lists every registered command" "missing: $cmd"
    _missing=1
  fi
done
[[ "$_missing" -eq 0 ]] && ok "root usage lists every registered command"

_missing=0
for cmd in "${_FLEET_CMD_ORDER[@]}"; do
  if ! declare -F "_fleet_cmd_$cmd" >/dev/null 2>&1; then
    bad "every registered command has an implementation" "missing: _fleet_cmd_$cmd"
    _missing=1
  fi
done
[[ "$_missing" -eq 0 ]] && ok "every registered command has an implementation"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

cd "$START_DIR" || true
echo
echo "passed: $PASS, failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
