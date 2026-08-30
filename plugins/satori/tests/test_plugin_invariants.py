"""Plugin-wide invariants for the satori skills.

These encode rules that were each broken at least once and fixed by hand, so the fix
does not depend on anyone remembering it. Every assertion here corresponds to a real
defect found in this repo, not a hypothetical.

Run from anywhere: `python3 -m pytest plugins/satori/tests/`
"""

import pathlib
import re

import pytest
import yaml

SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "skills"
PLUGIN_NAME = "satori"

SKILL_MDS = sorted(SKILLS_DIR.glob("*/SKILL.md"))
SKILL_NAMES = {p.parent.name for p in SKILL_MDS}


def frontmatter(path):
    text = path.read_text()
    assert text.startswith("---"), f"{path} has no frontmatter"
    return yaml.safe_load(text.split("---", 2)[1])


def test_there_are_skills_to_check():
    """Guard against the glob silently matching nothing and every test vacuously passing."""
    assert len(SKILL_MDS) >= 6, f"expected at least 6 skills, found {len(SKILL_MDS)}"


@pytest.mark.parametrize("skill_md", SKILL_MDS, ids=lambda p: p.parent.name)
def test_frontmatter_parses_as_strict_yaml(skill_md):
    """xp-pair shipped an unquoted flow sequence containing a colon; it loaded at runtime
    but crashed PyYAML, so any YAML-based tooling would have rejected the file."""
    frontmatter(skill_md)


@pytest.mark.parametrize("skill_md", SKILL_MDS, ids=lambda p: p.parent.name)
def test_argument_hint_is_a_string_not_a_list(skill_md):
    """`argument-hint: [pr-number]` is valid YAML but parses as a LIST.

    Every other skill quotes it, so the type silently varied across the plugin. A
    consumer expecting a string gets `['pr-number']`.
    """
    hint = frontmatter(skill_md).get("argument-hint")
    if hint is None:
        pytest.skip("skill declares no argument-hint")
    assert isinstance(hint, str), (
        f"argument-hint parsed as {type(hint).__name__} ({hint!r}) — quote the value")


@pytest.mark.parametrize("skill_md", SKILL_MDS, ids=lambda p: p.parent.name)
def test_frontmatter_name_matches_the_directory(skill_md):
    assert frontmatter(skill_md)["name"] == skill_md.parent.name


def _skill_call_sites():
    """Every `Skill(<name>` occurrence across the plugin's markdown."""
    sites = []
    for md in sorted(SKILLS_DIR.rglob("*.md")):
        for lineno, line in enumerate(md.read_text().splitlines(), 1):
            for m in re.finditer(r"Skill\(([A-Za-z0-9_:-]+)", line):
                sites.append((md, lineno, m.group(1)))
    return sites


def test_every_skill_invocation_is_plugin_prefixed():
    """`Skill(adversarial-review, ...)` does not resolve — the registered name is
    `satori:adversarial-review`. The Skill tool takes the exact name from the listing,
    and plugin skills are addressed `plugin:skill`.

    Consolidation under the satori: prefix landed in b5d1be4 (2026-06-26); the
    invocation strings never followed, in 8 places across 4 skills.
    """
    offenders = [
        f"{md.relative_to(SKILLS_DIR)}:{lineno}: Skill({name}"
        for md, lineno, name in _skill_call_sites()
        if name in SKILL_NAMES and not name.startswith(f"{PLUGIN_NAME}:")
    ]
    assert not offenders, (
        "unprefixed Skill() invocation(s) — these will not resolve:\n  "
        + "\n  ".join(offenders))


def test_skill_invocations_name_a_skill_that_exists():
    """A prefixed call must still point at a real skill directory."""
    unknown = [
        f"{md.relative_to(SKILLS_DIR)}:{lineno}: Skill({name}"
        for md, lineno, name in _skill_call_sites()
        if name.startswith(f"{PLUGIN_NAME}:")
        and name.split(":", 1)[1] not in SKILL_NAMES
    ]
    assert not unknown, "Skill() call(s) naming a nonexistent skill:\n  " + "\n  ".join(unknown)


def test_no_readme_duplicates_a_skill_frontmatter_block():
    """A second file in the skill dir declaring `name:` is a duplicate-definition hazard,
    and address-pr-issues' README reproduced SKILL.md's block verbatim."""
    offenders = []
    for readme in sorted(SKILLS_DIR.glob("*/README.md")):
        text = readme.read_text()
        if not text.startswith("---"):
            continue
        try:
            block = yaml.safe_load(text.split("---", 2)[1])
        except yaml.YAMLError:
            continue
        if isinstance(block, dict) and "name" in block:
            offenders.append(str(readme.relative_to(SKILLS_DIR)))
    assert not offenders, (
        "README(s) carrying skill frontmatter — delete the block:\n  " + "\n  ".join(offenders))


def test_no_reference_to_an_undefined_project_key_variable():
    """`$PROJECT_KEY` appears in prose but exists nowhere in the codebase; the real
    variable is SONAR_PROJECT_KEY, so the documented URL expands with an empty id."""
    offenders = []
    for md in sorted(SKILLS_DIR.rglob("*.md")):
        for lineno, line in enumerate(md.read_text().splitlines(), 1):
            if re.search(r"\$PROJECT_KEY\b|\$\{PROJECT_KEY\b", line):
                offenders.append(f"{md.relative_to(SKILLS_DIR)}:{lineno}")
    assert not offenders, (
        "reference(s) to $PROJECT_KEY, which is never set (use SONAR_PROJECT_KEY):\n  "
        + "\n  ".join(offenders))


def test_sonar_credential_docs_mention_the_variable_this_environment_provisions():
    """lib/sonar-api.sh falls back to SONARQUBE_CLI_TOKEN, which is what the keyring
    actually provides here. Docs naming only SONAR_TOKEN lead a reader to conclude the
    credential is missing — the exact misdiagnosis CLAUDE.md warns about.
    """
    # Live guidance only. A CHANGELOG records what was true at the time and should not be
    # rewritten to match the present — that is what makes it a changelog.
    live_guidance = {"SKILL.md", "README.md", "QUICK_START.md"}
    for doc in sorted(SKILLS_DIR.rglob("*.md")):
        if doc.name not in live_guidance:
            continue
        text = doc.read_text()
        if "SONAR_TOKEN" not in text:
            continue
        assert "SONARQUBE_CLI_TOKEN" in text, (
            f"{doc.relative_to(SKILLS_DIR)} documents SONAR_TOKEN without mentioning the "
            "SONARQUBE_CLI_TOKEN fallback the scripts actually use")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
