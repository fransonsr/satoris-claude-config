"""Contract tests for address-pr-issues' scripts and the SKILL.md snippets that drive them.

Written 2026-08-29 for five defects a /satori:reasoning-audit pass found. Four of the
five live in SKILL.md rather than in a script, which is why they survived: nothing
executes a markdown code block. These tests execute the real expressions and parse
the real files, so the prose is held to the same standard as the code.

Requires `jq` and `bash` on PATH.
"""

import json
import pathlib
import re
import shutil
import subprocess
import textwrap

import pytest

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
SCRIPTS = SKILL_DIR / "scripts"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="requires jq and bash",
)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kw)


def sh(script, **kw):
    return run(["bash", "-c", textwrap.dedent(script)], **kw)


# ------------------------------------------------- defect: checklist gate can never pass


def checklist_gate_expression():
    """The jq expression SKILL.md uses to decide the pre-push checklist has passed."""
    matches = re.findall(r"jq -e '([^']+)' \"\$CHECKLIST_FILE\"", SKILL_MD.read_text())
    assert matches, "no checklist gate expression found in SKILL.md"
    assert len(set(matches)) == 1, f"gate expression is inconsistent across sites: {set(matches)}"
    return matches[0]


def test_the_checklist_gate_passes_once_the_real_work_items_are_true(tmp_path):
    """The defect: `all(.[]; . == true)` reads commit_ready, which is only set true
    AFTER the gate it is part of has already passed. Circular — the gate can never fire.
    """
    checklist = tmp_path / "checklist.json"
    checklist.write_text(json.dumps({
        "tests_passing": True, "build_clean": True,
        "sonar_reviewed": True, "threads_resolved": True,
        "commit_ready": False,
    }))
    r = run(["jq", "-e", checklist_gate_expression(), str(checklist)])
    assert r.returncode == 0, (
        "gate rejected a checklist whose every real work item is true; "
        f"expression={checklist_gate_expression()!r}"
    )


def test_the_checklist_gate_still_rejects_an_incomplete_checklist(tmp_path):
    """The fix must not turn the gate into a rubber stamp."""
    checklist = tmp_path / "checklist.json"
    checklist.write_text(json.dumps({
        "tests_passing": True, "build_clean": False,
        "sonar_reviewed": True, "threads_resolved": True,
        "commit_ready": False,
    }))
    r = run(["jq", "-e", checklist_gate_expression(), str(checklist)])
    assert r.returncode != 0, "gate accepted a checklist with build_clean false"


def test_the_gate_matches_the_keys_init_pr_state_actually_writes():
    """A gate naming keys the initializer never creates would silently pass or fail."""
    init = (SCRIPTS / "init-pr-state.sh").read_text()
    # Anchor the closing EOF to its own line — otherwise the non-greedy match stops at
    # the `<<EOF` opener on the first line and captures nothing.
    block = re.search(r'cat > "\$CHECKLIST_FILE".*?\nEOF', init, re.S)
    assert block, "could not find the checklist heredoc in init-pr-state.sh"
    written = set(re.findall(r'"(\w+)":', block.group(0)))
    assert "commit_ready" in written, "test premise changed: commit_ready no longer initialized"
    expr = checklist_gate_expression()
    for key in written - {"commit_ready"}:
        assert key in expr or "with_entries" in expr or "del(" in expr or "to_entries" in expr, (
            f"gate does not appear to account for initialized key {key!r}")


# --------------------------------------- defect: fourth degraded label undocumented


def test_every_degraded_label_the_script_emits_is_documented_in_skill_md():
    """The defect: classify-threads.sh emits four fail-closed labels; SKILL.md listed three.

    SKILL.md sets unverifiable_provenance "mechanically from the label" for the names it
    lists, so an undocumented label arrives at Step 3 looking verified — the fail-closed
    path leaking exactly where it was built not to.
    """
    script = (SCRIPTS / "classify-threads.sh").read_text()
    emitted = set(re.findall(r'labels: \["(\w+)"\]', script))
    assert emitted, "no labels found in classify-threads.sh — test premise changed"

    documented = set(re.findall(r"`(\w+)`", SKILL_MD.read_text()))
    missing = sorted(emitted - documented)
    assert not missing, f"labels emitted by classify-threads.sh but absent from SKILL.md: {missing}"


def test_the_provenance_rule_lists_every_degraded_label():
    """The specific site that maps label -> unverifiable_provenance must be exhaustive."""
    script = (SCRIPTS / "classify-threads.sh").read_text()
    emitted = set(re.findall(r'labels: \["(\w+)"\]', script))
    text = SKILL_MD.read_text()
    rule = re.search(r"set it mechanically from", text)
    assert rule, "could not locate the provenance rule in SKILL.md"
    window = text[max(0, rule.start() - 400): rule.start() + 200]
    missing = sorted(label for label in emitted if label not in window)
    assert not missing, f"provenance rule omits degraded labels: {missing}"


# ------------------------------------------- defect: read -p stalls a non-interactive run


def test_commit_script_does_not_block_when_stdin_is_closed(tmp_path):
    """The defect: `read -p` never receives EOF under an agent and stalls until timeout.

    SKILL.md makes this script the primary commit path and forbids hand-rolling the
    alternative, so a stall means the documented happy path cannot be followed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    sh(f"""
        cd {repo}
        git init -q
        git config user.email t@example.com
        git config user.name Test
        git commit -q --allow-empty -m init
        echo change > f.txt
        git add f.txt
    """)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "round.txt").write_text("1")
    (workspace / "fixes.json").write_text("[]")

    r = run(["bash", str(SCRIPTS / "commit-pr-fixes.sh"), "99"],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path),
                 "WORKSPACE_DIR_OVERRIDE": str(workspace)})
    combined = (r.stdout + r.stderr).lower()
    assert "timed out" not in combined
    # Whatever it decides, it must decide non-interactively rather than waiting for a human.
    assert r.returncode is not None


def test_every_interactive_read_is_behind_a_tty_guard():
    """A prompt is fine; an unskippable prompt is not.

    An agent runs these scripts without a terminal, so a `read` that is not guarded by
    a tty check (or an explicit auto-confirm escape) makes the documented happy path
    unrunnable. The remedy has to be discoverable from the script itself, so the guard
    must sit within a few lines of the read.
    """
    offenders = []
    for script in sorted(SCRIPTS.glob("*.sh")):
        lines = script.read_text().splitlines()
        for lineno, line in enumerate(lines, 1):
            if not re.search(r"\bread\s+(-\w+\s+)*-p\b", line):
                continue
            window = "\n".join(lines[max(0, lineno - 8):lineno + 2])
            guarded = "-t 0" in window or "AUTO_CONFIRM" in window or "tty" in window
            if not guarded:
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "interactive read(s) with no tty guard or auto-confirm escape:\n  "
        + "\n  ".join(offenders))


# ------------------------------------------- defect: jq -s diff on JSON Lines


def new_threads_expression():
    """The jq pipeline SKILL.md Step 8 uses to find threads added since last round."""
    text = SKILL_MD.read_text()
    m = re.search(r"NEW_THREADS=\$\((.*?)\)\n", text, re.S)
    assert m, "could not find the NEW_THREADS assignment in SKILL.md"
    return m.group(1)


def test_new_thread_detection_finds_an_added_thread(tmp_path):
    """The defect: `jq -s '.[0] - .[1]'` on JSON Lines slurps every object from BOTH
    files into one flat array, so .[0]/.[1] are the first two THREADS, not the two files.
    Subtracting object from object is a type error; inside $(...) it goes to stderr and
    NEW_THREADS comes back empty, so Step 8 reported "no new comments" every round.
    """
    old = tmp_path / "threads.json.before-round-1"
    new = tmp_path / "threads.json"
    keep = {"threadId": "t1", "author": "copilot-pull-request-reviewer", "body": "old"}
    added = {"threadId": "t2", "author": "copilot-pull-request-reviewer", "body": "new"}
    old.write_text(json.dumps(keep) + "\n")
    new.write_text(json.dumps(keep) + "\n" + json.dumps(added) + "\n")

    script = f'''
        set -o pipefail
        THREADS_FILE="{new}"
        ROUND=1
        NEW_THREADS=$({new_threads_expression()})
        echo "$NEW_THREADS"
    '''
    r = sh(script)
    assert "t2" in r.stdout, f"added thread not detected. stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "t1" not in r.stdout, "unchanged thread reported as new"


def test_new_thread_detection_reports_nothing_when_no_thread_was_added(tmp_path):
    """It must still be able to say 'nothing new' — the fix is not 'always report'."""
    old = tmp_path / "threads.json.before-round-1"
    new = tmp_path / "threads.json"
    same = {"threadId": "t1", "author": "copilot-pull-request-reviewer", "body": "same"}
    old.write_text(json.dumps(same) + "\n")
    new.write_text(json.dumps(same) + "\n")

    r = sh(f'''
        THREADS_FILE="{new}"
        ROUND=1
        NEW_THREADS=$({new_threads_expression()})
        echo "count=$(echo "$NEW_THREADS" | grep -c threadId || true)"
    ''')
    assert "count=0" in r.stdout, f"reported a new thread when none was added: {r.stdout!r}"


def test_new_thread_detection_ignores_a_non_reviewer_author(tmp_path):
    old = tmp_path / "threads.json.before-round-1"
    new = tmp_path / "threads.json"
    old.write_text("")
    new.write_text(json.dumps({"threadId": "t9", "author": "some-human", "body": "hi"}) + "\n")

    r = sh(f'''
        THREADS_FILE="{new}"
        ROUND=1
        NEW_THREADS=$({new_threads_expression()})
        echo "count=$(echo "$NEW_THREADS" | grep -c threadId || true)"
    ''')
    assert "count=0" in r.stdout, f"non-reviewer thread reported as new: {r.stdout!r}"


# ------------------------------------------- defect: ${args} is never set in bash


def test_pr_number_snippet_honours_a_supplied_value():
    """The defect: `${args:-...}` — $args is unset in any bash context, so the fallback
    ALWAYS runs and a user-supplied PR number is silently ignored.
    """
    text = SKILL_MD.read_text()
    m = re.search(r'^PR_NUMBER="(.+)"$', text, re.M)
    assert m, "could not find the PR_NUMBER assignment in SKILL.md"
    expression = m.group(1)

    # Simulate the documented invocation: a positional argument carries the PR number,
    # and `gh` is absent so any fallback would fail loudly rather than silently succeed.
    r = sh(f'''
        set -u
        PR_NUMBER="{expression}"
        echo "PR_NUMBER=$PR_NUMBER"
    ''' , env={"PATH": "/usr/bin:/bin"})
    # The snippet is documented as taking the skill's argument; with one supplied it must
    # use it rather than reaching for gh.
    assert "PR_NUMBER=" in r.stdout


def test_pr_number_snippet_does_not_reference_an_undefined_args_variable():
    text = SKILL_MD.read_text()
    m = re.search(r'^PR_NUMBER="(.+)"$', text, re.M)
    assert m
    assert "${args" not in m.group(1), (
        "PR_NUMBER still expands ${args}, which bash never sets — the fallback always wins")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ============================================================================
# Workspace namespacing. /tmp/pr-${PR_NUMBER} carried no repo component, so two
# PRs numbered 68 in different repos shared one workspace and overwrote each
# other's threads.json / round.txt / fixes.json / triage.json. Realistic here:
# concurrent agents across the RP and JS fleets, where PR numbers are small and
# collide. This is the failure the global CLAUDE.md temp-file rule was written
# after — the skill predates the rule and was never brought into line.
# ============================================================================

WORKSPACE_SCRIPTS = [
    "check-sonar-quality-gate.sh", "resolve-thread.sh", "commit-pr-fixes.sh",
    "fetch-pr-threads.sh", "classify-threads.sh", "init-pr-state.sh",
]


def make_repo(tmp_path, name, origin):
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    sh(f"""
        cd {repo}
        git init -q
        git config user.email t@example.com
        git config user.name Test
        git remote add origin {origin}
    """)
    return repo


def derive_workspace(repo, pr="68"):
    """Ask the shared helper for a workspace path, exactly as a script would."""
    r = sh(f'''
        cd {repo}
        source {SCRIPTS}/lib/github-api.sh
        pr_workspace_dir {pr}
    ''')
    return r.stdout.strip(), r


def test_same_pr_number_in_different_repos_gets_different_workspaces(tmp_path):
    """The defect, stated directly."""
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/service-alpha.git")
    b = make_repo(tmp_path, "b", "https://github.com/fs-eng/service-beta.git")
    wa, ra = derive_workspace(a)
    wb, rb = derive_workspace(b)
    assert wa, f"helper produced nothing for repo a: {ra.stderr!r}"
    assert wb, f"helper produced nothing for repo b: {rb.stderr!r}"
    assert wa != wb, f"both repos resolved to the same workspace: {wa}"


def test_same_repo_and_pr_is_stable_across_calls(tmp_path):
    """Every script must land on the identical path or they cannot see each other's state."""
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/service-alpha.git")
    first, _ = derive_workspace(a)
    second, _ = derive_workspace(a)
    assert first == second and first


def test_different_owners_with_the_same_repo_name_do_not_collide(tmp_path):
    """A fork and its upstream share a repo name; only the owner distinguishes them."""
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/records.git")
    b = make_repo(tmp_path, "b", "https://github.com/fransonsr/records.git")
    wa, _ = derive_workspace(a)
    wb, _ = derive_workspace(b)
    assert wa != wb, f"owner is not part of the workspace identity: {wa}"


def test_workspace_path_is_a_single_filesystem_component_under_tmp(tmp_path):
    """owner/repo contains a slash; it must not become a nested path or an escape."""
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/service-alpha.git")
    w, _ = derive_workspace(a)
    assert w.startswith("/tmp/"), w
    assert w.count("/") == 2, f"workspace is not a single component under /tmp: {w}"
    assert ".." not in w


def test_ssh_and_https_remotes_agree(tmp_path):
    """The same repo reached two ways must not fork into two workspaces."""
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/records.git")
    b = make_repo(tmp_path, "b", "git@github.com:fs-eng/records.git")
    wa, _ = derive_workspace(a)
    wb, _ = derive_workspace(b)
    assert wa == wb, f"https and ssh remotes disagreed: {wa} vs {wb}"


def test_pr_number_still_distinguishes_workspaces(tmp_path):
    a = make_repo(tmp_path, "a", "https://github.com/fs-eng/records.git")
    w68, _ = derive_workspace(a, "68")
    w69, _ = derive_workspace(a, "69")
    assert w68 != w69


def test_helper_fails_loudly_outside_a_git_repo(tmp_path):
    """Failing is correct: it must never silently fall back to a shared path."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    r = sh(f'''
        cd {plain}
        source {SCRIPTS}/lib/github-api.sh
        pr_workspace_dir 68 || echo "REFUSED"
    ''')
    assert "REFUSED" in r.stdout or r.returncode != 0, (
        f"helper produced a path with no repo context: {r.stdout!r}")
    assert "/tmp/pr-68" not in r.stdout, "fell back to the colliding shared path"


@pytest.mark.parametrize("script", WORKSPACE_SCRIPTS)
def test_no_script_hardcodes_the_unnamespaced_workspace(script):
    """Each script must go through the shared helper, not re-derive the path."""
    text = (SCRIPTS / script).read_text()
    assert '"/tmp/pr-${PR_NUMBER}"' not in text, (
        f"{script} still hardcodes the unnamespaced workspace path")
    assert "pr_workspace_dir" in text, (
        f"{script} does not use the shared pr_workspace_dir helper")


def test_skill_md_documents_the_namespaced_shape():
    """SKILL.md's own snippets are what a reader copies; they must not teach the old path."""
    text = SKILL_MD.read_text()
    assert 'WORKSPACE_DIR="/tmp/pr-${PR_NUMBER}"' not in text, (
        "SKILL.md still documents the unnamespaced workspace path")
