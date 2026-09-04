"""Contract tests for the scip skill's orchestration scripts (common.sh, status.sh,
cleanup.sh, setup.sh, index.sh, query.sh).

These exercise the actual scripts via subprocess rather than re-deriving their logic in
Python — a script that has never been executed by a test has not demonstrated it works,
regardless of how straightforward it reads. Deliberately does not exercise a real
`scip-java` build or `setup.sh`'s install path: both make a full build / a real network
install, which belongs in manual end-to-end verification (see the handoff's Testable
Acceptance Criteria), not a fast test suite. `index.sh`'s own failure-detection logic
(does the output file actually exist after `scip-java` exits) is exercised below against
a stub `scip-java` on `PATH` — no real build required to prove that check works.

Requires `bash`, `git`, and `jq` on PATH.
"""

import json
import os
import shutil
import subprocess
import textwrap
import time

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_SH = os.path.join(SCRIPTS_DIR, "lib", "common.sh")
STATUS_SH = os.path.join(SCRIPTS_DIR, "status.sh")
CLEANUP_SH = os.path.join(SCRIPTS_DIR, "cleanup.sh")
SETUP_SH = os.path.join(SCRIPTS_DIR, "setup.sh")
INDEX_SH = os.path.join(SCRIPTS_DIR, "index.sh")
QUERY_SH = os.path.join(SCRIPTS_DIR, "query.sh")

# A real, small index produced this session's own scip-java pilot — copied into fixture
# HOME dirs below so status.sh exercises a genuine `scip stats --from` run, not a stub.
REAL_INDEX = os.path.expanduser("~/.cache/scip/sls-locking-service/index.scip")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None or shutil.which("jq") is None,
    reason="requires bash, git, and jq",
)


def run(cmd, **kw):
    kw.setdefault("timeout", 30)
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def init_repo(path, name):
    repo = path / name
    repo.mkdir()
    run(["git", "init", "-q"], cwd=repo)
    run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    run(["git", "config", "user.name", "Test"], cwd=repo)
    (repo / "README.md").write_text("fixture repo\n")
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-q", "-m", "init"], cwd=repo)
    return repo


# ---------------------------------------------- common.sh


def test_repo_root_fails_outside_a_git_repository(tmp_path):
    r = run(
        ["bash", "-c", f'source "{COMMON_SH}" && scip_repo_root'],
        cwd=tmp_path,
    )
    assert r.returncode != 0
    assert "Not inside a git repository" in r.stderr


def test_repo_root_succeeds_inside_a_git_repository(tmp_path):
    repo = init_repo(tmp_path, "demo-repo")
    r = run(["bash", "-c", f'source "{COMMON_SH}" && scip_repo_root'], cwd=repo)
    assert r.returncode == 0
    assert r.stdout.strip() == str(repo)


def test_cache_dir_and_index_path_are_keyed_by_repo_basename(tmp_path):
    repo = init_repo(tmp_path, "my-service")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = {**os.environ, "HOME": str(fake_home)}
    r = run(
        ["bash", "-c", f'source "{COMMON_SH}" && scip_cache_dir "{repo}" && scip_index_path "{repo}"'],
        env=env,
    )
    assert r.returncode == 0
    cache_dir, index_path = r.stdout.strip().splitlines()
    assert cache_dir == str(fake_home / ".cache" / "scip" / "my-service")
    assert index_path == str(fake_home / ".cache" / "scip" / "my-service" / "index.scip")


# ---------------------------------------------- status.sh


def test_status_reports_missing_index_without_crashing(tmp_path):
    repo = init_repo(tmp_path, "no-index-yet")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = {**os.environ, "HOME": str(fake_home)}
    r = run(["bash", STATUS_SH], cwd=repo, env=env)
    assert r.returncode == 0
    assert "No SCIP index found" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


@pytest.mark.skipif(not os.path.exists(REAL_INDEX), reason="fixture index not present on this machine")
def test_status_reports_path_size_age_and_real_scip_stats(tmp_path):
    repo = init_repo(tmp_path, "sls-locking-service")
    fake_home = tmp_path / "fake-home"
    cache_dir = fake_home / ".cache" / "scip" / "sls-locking-service"
    cache_dir.mkdir(parents=True)
    shutil.copyfile(REAL_INDEX, cache_dir / "index.scip")
    env = {**os.environ, "HOME": str(fake_home)}

    r = run(["bash", STATUS_SH], cwd=repo, env=env)

    assert r.returncode == 0
    assert str(cache_dir / "index.scip") in r.stdout
    assert "Size:" in r.stdout
    assert "Built:" in r.stdout
    stats_json = r.stdout[r.stdout.index("{"):]
    stats = json.loads(stats_json)
    assert stats["documents"] > 0
    assert stats["definitions"] > 0
    assert stats["occurrences"] > 0


# ---------------------------------------------- cleanup.sh


def test_cleanup_reports_nothing_to_clean_up_when_no_cache_exists(tmp_path):
    repo = init_repo(tmp_path, "never-indexed")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = {**os.environ, "HOME": str(fake_home)}
    r = run(["bash", CLEANUP_SH], cwd=repo, env=env)
    assert r.returncode == 0
    assert "nothing to clean up" in r.stdout


def test_cleanup_removes_the_cache_dir_and_only_the_cache_dir(tmp_path):
    repo = init_repo(tmp_path, "indexed-repo")
    fake_home = tmp_path / "fake-home"
    cache_dir = fake_home / ".cache" / "scip" / "indexed-repo"
    cache_dir.mkdir(parents=True)
    (cache_dir / "index.scip").write_bytes(b"fake index bytes")
    env = {**os.environ, "HOME": str(fake_home)}

    r = run(["bash", CLEANUP_SH], cwd=repo, env=env)

    assert r.returncode == 0
    assert not cache_dir.exists()
    assert (repo / "README.md").exists()  # repo's own working tree untouched


# ---------------------------------------------- setup.sh fast path


def _stub_bin_dir(tmp_path):
    """A directory with stub `scip`/`scip-java`/`java` executables, so the 'already
    installed' fast path can be exercised without touching the network or a real JVM."""
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    for name, output in (
        ("scip", "scip version v0.10.0"),
        ("scip-java", "scip-java help text"),
        ("java", "openjdk version stub"),
    ):
        script = stub_dir / name
        script.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "{output}"
            """))
        script.chmod(0o755)
    return stub_dir


def test_setup_is_a_fast_no_op_when_both_tools_are_already_installed(tmp_path):
    stub_dir = _stub_bin_dir(tmp_path)
    env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"}
    r = run(["bash", SETUP_SH], env=env)
    assert r.returncode == 0
    assert "Nothing to do" in r.stdout
    assert "curl" not in r.stdout.lower()


# ---------------------------------------------- index.sh


def _stub_scip_java_dir(tmp_path, write_index):
    """A stub `scip-java` on PATH — never a real build. When `write_index` is False, it
    reproduces the exact sls-bi-worker symptom this fix targets: exit 0, output file
    never written. When True, it writes a placeholder file at the `--output` path, like
    a real successful run would."""
    stub_dir = tmp_path / "stub-scip-java-bin"
    stub_dir.mkdir()
    script = stub_dir / "scip-java"
    if write_index:
        body = textwrap.dedent("""\
            #!/usr/bin/env bash
            shift  # drop the "index" subcommand
            while [[ $# -gt 0 ]]; do
              case "$1" in
                --output) echo "fake index bytes" > "$2"; shift 2 ;;
                *) shift ;;
              esac
            done
            """)
    else:
        body = textwrap.dedent("""\
            #!/usr/bin/env bash
            # Simulates the real sls-bi-worker failure mode: exits 0, writes nothing.
            exit 0
            """)
    script.write_text(body)
    script.chmod(0o755)
    return stub_dir


def test_index_fails_clearly_when_scip_java_exits_zero_but_writes_no_index(tmp_path):
    repo = init_repo(tmp_path, "silently-failing-repo")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    stub_dir = _stub_scip_java_dir(tmp_path, write_index=False)
    env = {**os.environ, "HOME": str(fake_home), "PATH": f"{stub_dir}:{os.environ['PATH']}"}

    r = run(["bash", INDEX_SH], cwd=repo, env=env)

    assert r.returncode != 0
    assert "Index written to" not in r.stdout
    expected_path = fake_home / ".cache" / "scip" / "silently-failing-repo" / "index.scip"
    assert str(expected_path) in r.stderr
    assert not expected_path.exists()


def test_index_fails_clearly_on_refresh_even_with_a_stale_index_already_on_disk(tmp_path):
    """A repo that indexed successfully before, then silently fails on a later `refresh`,
    must not be masked by the previous run's leftover index.scip still sitting in the
    cache dir — the check has to reflect *this* run, not a stale one. The stale file is
    left in place (not deleted) rather than destroyed on the mere possibility of a
    failure — see the crash-preservation test below for why that matters."""
    repo = init_repo(tmp_path, "previously-indexed-repo")
    fake_home = tmp_path / "fake-home"
    cache_dir = fake_home / ".cache" / "scip" / "previously-indexed-repo"
    cache_dir.mkdir(parents=True)
    stale_bytes = b"stale index from a prior successful run"
    (cache_dir / "index.scip").write_bytes(stale_bytes)
    stub_dir = _stub_scip_java_dir(tmp_path, write_index=False)
    env = {**os.environ, "HOME": str(fake_home), "PATH": f"{stub_dir}:{os.environ['PATH']}"}

    r = run(["bash", INDEX_SH], cwd=repo, env=env)

    assert r.returncode != 0
    assert "Index written to" not in r.stdout
    expected_path = cache_dir / "index.scip"
    assert str(expected_path) in r.stderr
    assert expected_path.read_bytes() == stale_bytes  # untouched, not deleted


def test_index_preserves_a_valid_index_when_scip_java_crashes_outright(tmp_path):
    """A genuine scip-java/build crash (nonzero exit) is a different failure mode from
    the silent-success bug this script otherwise guards against — it must not destroy a
    previously valid index still sitting in the cache dir. `set -e` aborts the script at
    the scip-java call itself, before either post-build check runs."""
    repo = init_repo(tmp_path, "crash-during-refresh-repo")
    fake_home = tmp_path / "fake-home"
    cache_dir = fake_home / ".cache" / "scip" / "crash-during-refresh-repo"
    cache_dir.mkdir(parents=True)
    valid_bytes = b"previously valid index"
    (cache_dir / "index.scip").write_bytes(valid_bytes)
    stub_dir = tmp_path / "stub-crash-bin"
    stub_dir.mkdir()
    script = stub_dir / "scip-java"
    script.write_text("#!/usr/bin/env bash\necho 'build crashed' >&2\nexit 1\n")
    script.chmod(0o755)
    env = {**os.environ, "HOME": str(fake_home), "PATH": f"{stub_dir}:{os.environ['PATH']}"}

    r = run(["bash", INDEX_SH], cwd=repo, env=env)

    assert r.returncode != 0
    expected_path = cache_dir / "index.scip"
    assert expected_path.read_bytes() == valid_bytes


def test_index_replaces_a_stale_index_on_a_genuinely_successful_refresh(tmp_path):
    """The flip side of the two tests above: when scip-java *does* freshly rewrite the
    index this run, that has to be recognized as success even though a stale file already
    existed beforehand — the mtime-comparison check must not itself become a false
    failure on the normal, working refresh path."""
    repo = init_repo(tmp_path, "refreshed-repo")
    fake_home = tmp_path / "fake-home"
    cache_dir = fake_home / ".cache" / "scip" / "refreshed-repo"
    cache_dir.mkdir(parents=True)
    stale_path = cache_dir / "index.scip"
    stale_path.write_bytes(b"stale index from a prior run")
    old_time = time.time() - 3600  # backdate well clear of the new write's mtime
    os.utime(stale_path, (old_time, old_time))
    stub_dir = _stub_scip_java_dir(tmp_path, write_index=True)
    env = {**os.environ, "HOME": str(fake_home), "PATH": f"{stub_dir}:{os.environ['PATH']}"}

    r = run(["bash", INDEX_SH], cwd=repo, env=env)

    assert r.returncode == 0
    assert f"Index written to {stale_path}" in r.stdout
    assert stale_path.read_bytes() == b"fake index bytes\n"


def test_index_succeeds_and_reports_the_path_when_scip_java_actually_writes_it(tmp_path):
    repo = init_repo(tmp_path, "successfully-indexed-repo")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    stub_dir = _stub_scip_java_dir(tmp_path, write_index=True)
    env = {**os.environ, "HOME": str(fake_home), "PATH": f"{stub_dir}:{os.environ['PATH']}"}

    r = run(["bash", INDEX_SH], cwd=repo, env=env)

    assert r.returncode == 0
    expected_path = fake_home / ".cache" / "scip" / "successfully-indexed-repo" / "index.scip"
    assert f"Index written to {expected_path}" in r.stdout
    assert expected_path.exists()


# ---------------------------------------------- query.sh


def test_query_fails_clearly_when_no_index_exists(tmp_path):
    repo = init_repo(tmp_path, "no-index-for-query")
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = {**os.environ, "HOME": str(fake_home)}
    r = run(["bash", QUERY_SH, "symbol", "anything"], cwd=repo, env=env)
    assert r.returncode != 0
    assert "No SCIP index found" in r.stderr
