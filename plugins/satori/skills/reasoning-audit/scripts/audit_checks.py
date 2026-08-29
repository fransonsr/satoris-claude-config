#!/usr/bin/env python3
"""audit_checks.py — the mechanically decidable lenses of /satori:reasoning-audit.

Decides lenses 3 (citations), 5 (self-dated claims), 6-static (bypassed scripts)
and 7 (structure conventions). Lenses 1, 2 and 4 need judgment and are left to
the skill's own reasoning; this script only supplies evidence for them.

Exit codes are the interface, so the same script serves a hook, a CI job and an
interactive run without modification:

    0  clean      — every lens that ran found nothing
    1  findings   — at least one lens fired
    2  cannot check — target missing, unreadable, or unclassifiable

"Cannot check" is deliberately never "clean": a checker that cannot tell must
refuse to bless, because false assurance costs more than a missed run.

Usage:
    audit_checks.py <target> [--max-age-days N]

    <target> may be a SKILL.md, a CLAUDE.md, a skill directory, or a plugin root.
"""

import argparse
import datetime
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

import yaml

CLEAN = 0
FINDINGS = 1
CANNOT_CHECK = 2

# Frontmatter fields current Claude Code accepts.
#
# Provenance: skill-creator's quick_validate.py ALLOWED_PROPERTIES, verified
# 2026-08-29, PLUS `argument-hint` — which that list omits even though the
# harness accepts it and 3 of satori's own skills use it. Treat this list as
# subject to lens 1: it is a copied constant, and the source was already stale.
ALLOWED_FRONTMATTER = {
    "name", "description", "license", "allowed-tools",
    "metadata", "compatibility", "argument-hint",
}
REQUIRED_FRONTMATTER = {"name", "description"}

DESCRIPTION_MAX = 1024      # skill-creator quick_validate.py, verified 2026-08-29
NAME_MAX = 64               # ditto
COMPATIBILITY_MAX = 500     # ditto
SKILL_MD_MAX_LINES = 500    # skill-creator SKILL.md "progressive disclosure", 2026-08-29
REFERENCE_TOC_LINES = 300   # ditto — reference files past this need a TOC
DEFAULT_MAX_AGE_DAYS = 90   # local default; no external source, subject to lens 1
ANCESTOR_SEARCH_DEPTH = 2   # how far up to look for a sibling-relative citation

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BACKTICKED = re.compile(r"`([^`\n]+)`")
CITEABLE_SUFFIXES = (".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml")
DATED_CLAIM = re.compile(
    r"(verified|last updated|last checked|last tested|validated|re-verified)"
    r"\W{0,6}(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
# A results-table row: `| case-name | 2026-07-02 | PASS |`. The cc-plugins
# evals/README.md convention puts the date in a cell, so the "Last Tested" header
# sits rows away from it and the inline pattern above cannot reach it.
DATED_TABLE_ROW = re.compile(
    r"^\s*\|[^|]+\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(PASS|FAIL|PENDING)\b",
    re.IGNORECASE,
)
# The same row shape with an empty or dashed date cell — "never run". Worse than
# stale, and invisible until this was added: the em-dash is the cc-plugins
# convention, so every un-run eval README read as clean (found 2026-08-29).
UNRUN_TABLE_ROW = re.compile(
    r"^\s*\|[^|]+\|\s*[—–-]?\s*\|\s*(PASS|FAIL|PENDING)\b",
    re.IGNORECASE,
)
# A dated section header: `## Key Improvement (2026-04-17)`. Carries no
# verification keyword, so the inline pattern above cannot see it.
DATED_HEADER = re.compile(r"^\s*#{1,6}\s+.*\((\d{4}-\d{2}-\d{2})\)")
# An undated novelty marker: `(NEW)`, `(NEW - 2026-04-27)`. It cannot expire, so
# past a couple of them it stops carrying information.
NOVELTY_MARKER = re.compile(r"\(NEW\b[^)]*\)")
NOVELTY_MARKER_THRESHOLD = 2
CITATION_CUES = (
    "see ", "per ", "documented in", "described in", "defined in",
    "refer to", "for the", "listed in", "specified in",
)
NEGATION_CUES = (
    " no ", " not ", "n't", " lacks", " lack ", " without ", " never ",
    " missing", " absent", " omits", " excludes",
)
EXAMPLES_HEADING = re.compile(r"^\s*(\*\*|#+\s*)?examples?\b", re.IGNORECASE)
ILLUSTRATIVE_CUES = (
    "e.g.", "for example", "for instance", "such as", "name like", "like `",
)
CLAUDE_MD_NAMES = {"claude.md", ".claude.md", ".claude.local.md"}
SCRIPT_SUFFIXES = (".py", ".sh")

PROJECT_SIGNALS = (
    "## commands", "## architecture", "## key files", "## setup",
    "build:", "test:", "npm run", "mvn ", "gradle ", "make ",
    "entry point", "directory structure", "src/",
)
STANDARDS_SIGNALS = (
    "core principles", "coding standards", "solid", "test-first", "test-after",
    "refactor", "anti-pattern", "code review checklist", "decision override",
    "testing pyramid", "principles",
)
MIN_CLASSIFICATION_SIGNALS = 2


@dataclass(frozen=True)
class Finding:
    path: str
    line: Optional[int]
    lens: str
    message: str

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: [{self.lens}] {self.message}"


# ------------------------------------------------------------------ lens 7


def check_frontmatter(path: pathlib.Path) -> List[Finding]:
    """Validate SKILL.md frontmatter against the conventions above."""
    text = path.read_text()
    if not text.startswith("---"):
        return [Finding(str(path), 1, "frontmatter",
                        "file does not open with '---'; no frontmatter to validate")]

    parts = text.split("---", 2)
    if len(parts) < 3:
        return [Finding(str(path), 1, "frontmatter",
                        "frontmatter block is not closed by a second '---'")]

    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0]
        return [Finding(str(path), 1, "frontmatter",
                        f"frontmatter is not valid YAML ({detail}); "
                        "YAML-based tooling will reject this file even if the harness tolerates it")]

    if not isinstance(data, dict):
        return [Finding(str(path), 1, "frontmatter",
                        f"frontmatter parses as {type(data).__name__}, not a mapping")]

    return _validate_frontmatter_fields(path, data)


def _validate_frontmatter_fields(path: pathlib.Path, data: dict) -> List[Finding]:
    findings = []

    for missing in sorted(REQUIRED_FRONTMATTER - set(data)):
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"required field '{missing}' is absent"))

    for unknown in sorted(set(data) - ALLOWED_FRONTMATTER):
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"unknown frontmatter key '{unknown}'"))

    findings.extend(_check_name_field(path, data.get("name")))
    findings.extend(_check_description_field(path, data.get("description")))

    compatibility = data.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > COMPATIBILITY_MAX:
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"compatibility is {len(compatibility)} chars "
                                f"(limit {COMPATIBILITY_MAX})"))
    return findings


def _check_name_field(path: pathlib.Path, name) -> List[Finding]:
    if name is None:
        return []
    if not isinstance(name, str):
        return [Finding(str(path), 1, "frontmatter",
                        f"name must be a string, got {type(name).__name__}")]
    findings = []
    if not NAME_PATTERN.match(name):
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"name '{name}' is not kebab-case "
                                "(lowercase letters, digits, single hyphens)"))
    if len(name) > NAME_MAX:
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"name is {len(name)} chars (limit {NAME_MAX})"))
    return findings


def _check_description_field(path: pathlib.Path, description) -> List[Finding]:
    if description is None:
        return []
    if not isinstance(description, str):
        return [Finding(str(path), 1, "frontmatter",
                        f"description must be a string, got {type(description).__name__}")]
    findings = []
    if "<" in description or ">" in description:
        findings.append(Finding(str(path), 1, "frontmatter",
                                "description contains an angle bracket, which is not permitted"))
    if len(description) > DESCRIPTION_MAX:
        findings.append(Finding(str(path), 1, "frontmatter",
                                f"description is {len(description)} chars "
                                f"(limit {DESCRIPTION_MAX})"))
    return findings


def check_skill_structure(skill_dir: pathlib.Path) -> List[Finding]:
    """Check SKILL.md length and reference-file table-of-contents conventions."""
    findings = []

    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        lines = len(skill_md.read_text().splitlines())
        if lines > SKILL_MD_MAX_LINES:
            findings.append(Finding(str(skill_md), None, "structure",
                                    f"SKILL.md is {lines} lines (past {SKILL_MD_MAX_LINES}); "
                                    "add a layer of hierarchy with pointers to bundled resources"))

    for reference in sorted((skill_dir / "references").glob("*.md")):
        findings.extend(_check_reference_toc(reference))
    return findings


def _check_reference_toc(reference: pathlib.Path) -> List[Finding]:
    lines = reference.read_text().splitlines()
    if len(lines) <= REFERENCE_TOC_LINES:
        return []
    head = "\n".join(lines[:50]).lower()
    if "contents" in head:
        return []
    return [Finding(str(reference), None, "structure",
                    f"reference file is {len(lines)} lines (past {REFERENCE_TOC_LINES}) "
                    "with no table of contents in its first 50 lines")]


# ------------------------------------------------------------------ lens 3


def check_citations(path: pathlib.Path, text: str,
                    root: Optional[pathlib.Path] = None) -> List[Finding]:
    """Flag cited paths that do not resolve, and resolved paths lacking a cited term.

    `root` is the skill (or document set) root a relative citation may be written
    against; it defaults to the citing file's own directory. A references/ file
    citing `audit_checks.py` means scripts/audit_checks.py under the skill root,
    not under references/.

    Lines in illustrative context are skipped — see _walk_prose_lines.
    """
    findings = []
    for lineno, line, illustrative in _walk_prose_lines(text):
        if illustrative:
            continue
        tokens = BACKTICKED.findall(line)
        paths = [t for t in tokens if _looks_like_path(t)]
        terms = _cited_terms(line, tokens)
        for cited in paths:
            findings.extend(_check_one_citation(path, lineno, cited, terms, root))
    return findings


def _walk_prose_lines(text: str):
    """Yield (lineno, line, illustrative) for each line.

    A line is illustrative when it sits inside a fenced code block, under an
    "Examples" heading, or carries phrasing that introduces a sample rather than
    a citation. Each of those held real example paths that the first dogfood run
    (2026-08-29) reported as broken citations — noise that would have trained a
    reader to ignore this lens entirely.
    """
    in_fence = False
    in_examples = False
    previous = ""

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            yield lineno, line, True
            continue

        if EXAMPLES_HEADING.match(stripped):
            in_examples = True
            yield lineno, line, True
            continue
        if in_examples:
            if stripped == "" or _is_list_item(stripped):
                yield lineno, line, True
                continue
            in_examples = False

        # Check the previous line too: prose wraps, so an "e.g." can introduce a
        # sample that lands on the next line.
        context = (previous + " " + line).lower()
        yield lineno, line, any(cue in context for cue in ILLUSTRATIVE_CUES)
        previous = line


def _is_list_item(stripped: str) -> bool:
    return stripped.startswith(("-", "*", "+")) or bool(re.match(r"^\d+\.", stripped))


def _cited_terms(line: str, tokens: List[str]) -> List[str]:
    """Backticked identifiers this line positively claims live in the cited file.

    Requires an explicit citation cue and no negation on the line. Without both,
    a co-occurring identifier is not a claim about the file's contents — prose
    noting what a script does NOT handle is the common counter-example, and
    reading it as a broken citation was a real false positive (2026-08-29).
    """
    lowered = line.lower()
    if not any(cue in lowered for cue in CITATION_CUES):
        return []
    if any(neg in lowered for neg in NEGATION_CUES):
        return []
    return [t for t in tokens if not _looks_like_path(t) and _looks_like_identifier(t)]


def _check_one_citation(path, lineno, cited, terms, root=None) -> List[Finding]:
    target = _resolve_citation(path, cited, root)
    if target is None:
        return [Finding(str(path), lineno, "citations",
                        f"cited path `{cited}` cannot be resolved from {path.parent}")]
    if not target.is_file():
        return []
    try:
        content = target.read_text()
    except OSError:
        return []
    return [Finding(str(path), lineno, "citations",
                    f"`{cited}` resolves but does not contain the cited term `{term}` — "
                    "the link works, so nothing looks broken")
            for term in terms if term not in content]


def _resolve_citation(path: pathlib.Path, cited: str,
                      root: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Resolve a cited path, or None if it genuinely does not exist.

    A bare basename is satisfied by a match anywhere under the search roots: a
    SKILL.md citing `pattern_checker.py` means scripts/pattern_checker.py, and
    demanding a literal relative path there produces noise, not findings.
    """
    if cited.startswith("~"):
        expanded = pathlib.Path(cited).expanduser()
        return expanded if expanded.exists() else None

    for base in _search_bases(path, root):
        if "/" in cited:
            for ancestor in (base, *list(base.parents)[:ANCESTOR_SEARCH_DEPTH]):
                if (ancestor / cited).exists():
                    return ancestor / cited
            found = _find_by_path_suffix(base, cited)
        else:
            found = next(base.rglob(cited), None)
        if found is not None:
            return found
    return None


def _search_bases(path: pathlib.Path, root: Optional[pathlib.Path]):
    """Directories a relative citation may be written against, nearest first.

    Absolute-resolved, because a relative invocation (`audit_checks.py my-skill`)
    would otherwise have an empty .parents chain and silently lose the ancestor
    search that sibling-skill references depend on.
    """
    bases = [path.parent.resolve()]
    if root is not None:
        resolved_root = root.resolve()
        if resolved_root not in bases:
            bases.append(resolved_root)
    return bases


def _find_by_path_suffix(base: pathlib.Path, cited: str) -> Optional[pathlib.Path]:
    """Find a file under base whose path ends with the cited fragment."""
    name = cited.rsplit("/", 1)[-1]
    for candidate in base.rglob(name):
        if candidate.as_posix().endswith("/" + cited):
            return candidate
    return None


def _looks_like_path(token: str) -> bool:
    """A citeable path: no whitespace, a recognized suffix, and not a template or URI.

    The exclusions below were each a real false positive on the first dogfood run
    (2026-08-29): template placeholders, shell variables, elided paths and URIs all
    look path-shaped but name nothing a static check can resolve.
    """
    if not token or any(c.isspace() for c in token):
        return False
    if not token.endswith(CITEABLE_SUFFIXES):
        return False
    # A bare suffix like `.py` is a file type being discussed, not a file cited.
    if token.startswith("."):
        return False
    if any(marker in token for marker in ("<", ">", "$", "...", "*", "://", "{", "}")):
        return False
    # An absolute path names a runtime or system location (/tmp/..., /etc/...),
    # not a file shipped alongside the citing document.
    if token.startswith("/"):
        return False
    # A bare basename is only worth checking for shipped executables. A bare
    # `threads.json` or `notes.md` is far more often a runtime artifact or an
    # external document than a missing shipped file.
    if "/" not in token and not token.endswith(SCRIPT_SUFFIXES):
        return False
    return True


def _looks_like_identifier(token: str) -> bool:
    """A plausible cited field/symbol name, not a shell command or prose."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", token))


# ------------------------------------------------------------------ lens 5


def check_self_dated_claims(path: pathlib.Path, text: str, max_age_days: int,
                            today: datetime.date) -> List[Finding]:
    """Flag text carrying its own validation date whose re-check window has passed."""
    findings = []
    unrun_lines = []
    for lineno, line in enumerate(text.splitlines(), 1):
        findings.extend(_check_one_dated_line(path, lineno, line, max_age_days, today))
        if _is_unrun_row(line):
            unrun_lines.append(lineno)

    findings.extend(_check_unrun_rows(path, unrun_lines))
    findings.extend(_check_novelty_markers(path, text))
    return findings


def _check_one_dated_line(path, lineno, line, max_age_days, today) -> List[Finding]:
    """Judge a line by its NEWEST dated claim.

    Only the newest date governs: "Verified X, re-verified Y" is a maintained claim,
    not a stale one, and reading the older date produced a false positive at tight
    windows (observed 2026-08-29).
    """
    dated = [(k, ds, _parse_date(ds)) for k, ds in _dated_claims_on(line)]
    dated = [(k, ds, d) for k, ds, d in dated if d is not None]
    if not dated:
        return []

    keyword, datestr, claimed = max(dated, key=lambda item: item[2])
    age = (today - claimed).days
    if age <= max_age_days:
        return []
    return [Finding(str(path), lineno, "self-dated",
                    f"'{keyword}' claim dated {datestr} is {age} days old "
                    f"(window {max_age_days}); unverified rather than wrong — "
                    "due for re-check")]


def _is_unrun_row(line: str) -> bool:
    """A results row with no date, and no dated claim to explain it."""
    return bool(UNRUN_TABLE_ROW.match(line)) and not _dated_claims_on(line)


def _check_unrun_rows(path: pathlib.Path, linenos: List[int]) -> List[Finding]:
    """Report never-run results rows once per file, with a count.

    One sentence repeated per row is noise; a reader needs to know the suite has
    never run, not to read the same finding ten times.
    """
    if not linenos:
        return []
    where = (f"line {linenos[0]}" if len(linenos) == 1
             else f"lines {linenos[0]}-{linenos[-1]}")
    return [Finding(str(path), linenos[0], "self-dated",
                    f"{len(linenos)} results row(s) have no date ({where}) — those cases "
                    "have never been run. A suite that has never reported bad news has not "
                    "demonstrated it can; 'never run' is a weaker position than 'run once, "
                    "long ago'")]


def _check_novelty_markers(path: pathlib.Path, text: str) -> List[Finding]:
    """Flag a thicket of undated '(NEW)' markers, once per file.

    One marker on genuinely new content is normal. Nineteen, the oldest 4.5 months
    old and labelling the central mechanism, is the signal — reported once with a
    count rather than once per line, so the finding stays readable.
    """
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines, 1) if NOVELTY_MARKER.search(line)]
    if len(hits) < NOVELTY_MARKER_THRESHOLD:
        return []
    return [Finding(str(path), hits[0], "self-dated",
                    f"{len(hits)} undated '(NEW)' markers in this file "
                    f"(first at line {hits[0]}, last at line {hits[-1]}). A marker with no "
                    "date cannot expire, so past a couple of them it stops distinguishing "
                    "new content from settled content")]


def _dated_claims_on(line: str):
    """Yield (keyword, date) pairs for inline claims, dated headers, and table rows."""
    inline = DATED_CLAIM.findall(line)
    if inline:
        return inline
    header = DATED_HEADER.match(line)
    if header:
        return [("section header", header.group(1))]
    row = DATED_TABLE_ROW.match(line)
    return [(row.group(2).upper(), row.group(1))] if row else []


def _parse_date(datestr: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(datestr)
    except ValueError:
        return None


# ------------------------------------------------------------------ lens 6


def check_unreferenced_scripts(root: pathlib.Path) -> List[Finding]:
    """Flag shipped scripts that no SKILL.md under root mentions.

    Evidence is drawn only from SKILL.md files, never from the scripts themselves,
    so a script naming itself in a docstring cannot vouch for its own use.
    """
    skill_texts = _collect_skill_texts(root)
    if not skill_texts:
        return []

    scripts = sorted(_iter_shipped_scripts(root))
    reachable = _reachable_scripts(scripts, skill_texts)

    return [Finding(
        str(script), None, "bypassed-scripts",
        f"no SKILL.md references `{script.name}`, directly or through a wrapper, so "
        "nothing will invoke it; a shipped script encodes reasoning already done — an "
        "unreferenced one means that reasoning is being re-derived inline or not at all")
        for script in scripts if script not in reachable]


def _reachable_scripts(scripts: List[pathlib.Path], skill_texts: List[str]) -> set:
    """Scripts a SKILL.md can reach, following one level of wrapper indirection.

    A `.sh` that `exec`s a `.py` is the common shape; greping SKILL.md only for the
    `.py`'s own name reported a live script as orphaned (confirmed false positive,
    2026-08-29). Indirection stops at one level and the wrapper must itself be
    directly referenced, so two mutually-referencing orphans cannot vouch for each
    other.
    """
    direct = {s for s in scripts if any(s.name in text for text in skill_texts)}
    wrapper_texts = []
    for wrapper in direct:
        try:
            wrapper_texts.append(wrapper.read_text())
        except OSError:
            continue
    indirect = {s for s in scripts
                if s not in direct and any(s.name in t for t in wrapper_texts)}
    return direct | indirect


def _collect_skill_texts(root: pathlib.Path) -> List[str]:
    return [p.read_text() for p in root.rglob("SKILL.md") if p.is_file()]


def _iter_shipped_scripts(root: pathlib.Path):
    for script in root.rglob("*"):
        if not script.is_file() or script.suffix not in SCRIPT_SUFFIXES:
            continue
        if script.parent.name != "scripts":
            continue
        if _is_test_file(script.name):
            continue
        yield script


def _is_test_file(name: str) -> bool:
    stem = name.rsplit(".", 1)[0]
    return name.startswith("test_") or stem.endswith("_test")


# ------------------------------------------------------- classification


def classify_target(path: pathlib.Path) -> str:
    """Classify from file evidence, never from path.

    Returns one of: skill, standards-claude-md, project-claude-md, script,
    unclassified. Unclassified is a deliberate refusal, not a fallback bucket:
    a lens applied where it may not belong produces confident complaints about
    correct work.
    """
    if path.is_dir():
        return "skill" if (path / "SKILL.md").is_file() else "unclassified"
    if path.name == "SKILL.md":
        return "skill"
    if path.suffix in SCRIPT_SUFFIXES:
        return "script"
    if path.name.lower() in CLAUDE_MD_NAMES:
        return _classify_claude_md(path)
    if _looks_like_eval_suite(path):
        return "eval-suite"
    return "unclassified"


def _looks_like_eval_suite(path: pathlib.Path) -> bool:
    """An eval/test-results document under an evals/ directory.

    Added after the eval surfaced that the artifact family which motivated this
    skill — a stale eval suite — was the one kind it could not classify, so lens 5
    named the convention while refusing to accept a file that used it.
    """
    if path.suffix.lower() != ".md":
        return False
    if "evals" not in {part.lower() for part in path.parts}:
        return False
    try:
        return _has_results_evidence(path.read_text())
    except OSError:
        return False


def _has_results_evidence(text: str) -> bool:
    for line in text.splitlines():
        if DATED_TABLE_ROW.match(line) or UNRUN_TABLE_ROW.match(line):
            return True
        if DATED_CLAIM.search(line):
            return True
    return False


def _classify_claude_md(path: pathlib.Path) -> str:
    lowered = path.read_text().lower()
    project = sum(1 for s in PROJECT_SIGNALS if s in lowered)
    standards = sum(1 for s in STANDARDS_SIGNALS if s in lowered)

    if project >= MIN_CLASSIFICATION_SIGNALS and project > standards:
        return "project-claude-md"
    if standards >= MIN_CLASSIFICATION_SIGNALS and standards > project:
        return "standards-claude-md"
    return "unclassified"


# ------------------------------------------------------------------- main

LENSES_BY_KIND = {
    "skill": ("frontmatter", "structure", "citations", "self-dated", "bypassed-scripts"),
    "standards-claude-md": ("citations", "self-dated"),
    "project-claude-md": ("citations", "self-dated"),
    "eval-suite": ("citations", "self-dated"),
    "script": ("self-dated",),
}


def run_lenses(target: pathlib.Path, kind: str, max_age_days: int,
               today: datetime.date) -> List[Finding]:
    """Run every lens applicable to kind and return the combined findings."""
    lenses = LENSES_BY_KIND[kind]
    findings: List[Finding] = []

    skill_md = target / "SKILL.md" if target.is_dir() else target
    skill_dir = target if target.is_dir() else target.parent

    if "frontmatter" in lenses:
        findings.extend(check_frontmatter(skill_md))
    if "structure" in lenses:
        findings.extend(check_skill_structure(skill_dir))
    # For a skill, citations and dates are checked across every bundled markdown
    # file, not just SKILL.md: a stale `Last Tested` row in evals/README.md is
    # exactly the drift this skill exists to catch, and auditing SKILL.md alone
    # would leave it invisible.
    if target.is_dir():
        cited_docs = _citation_documents(skill_dir)
        dated_docs = _bundled_markdown(skill_dir)
    else:
        cited_docs = dated_docs = [skill_md]

    if "citations" in lenses:
        findings.extend(_scan(cited_docs, lambda d, t: check_citations(d, t, root=skill_dir)))
    if "self-dated" in lenses:
        findings.extend(_scan(dated_docs, lambda d, t: check_self_dated_claims(
            d, t, max_age_days, today)))
    if "bypassed-scripts" in lenses:
        findings.extend(check_unreferenced_scripts(skill_dir))
    return findings


def _scan(documents, check) -> List[Finding]:
    findings: List[Finding] = []
    for document in documents:
        try:
            text = document.read_text()
        except OSError:
            continue
        findings.extend(check(document, text))
    return findings


def _bundled_markdown(skill_dir: pathlib.Path) -> List[pathlib.Path]:
    """SKILL.md first, then every other markdown file bundled with the skill.

    Dates mean the same thing wherever they appear, so the self-dated lens reads
    all of these — including evals/README.md, whose staleness is the whole point.
    """
    skill_md = skill_dir / "SKILL.md"
    others = sorted(p for p in skill_dir.rglob("*.md") if p != skill_md)
    return ([skill_md] if skill_md.is_file() else []) + others


def _citation_documents(skill_dir: pathlib.Path) -> List[pathlib.Path]:
    """Documents whose cited paths are meant to resolve.

    Excludes templates/, examples/ and CHANGELOG files: those hold placeholder and
    historical paths by design, and resolving them produced pure noise on the
    dogfood run (2026-08-29) — a template's unresolvable path is the template
    working as intended.
    """
    documents = [skill_dir / "SKILL.md"] if (skill_dir / "SKILL.md").is_file() else []
    documents += sorted((skill_dir / "references").rglob("*.md"))
    return documents


def main(argv=None) -> int:
    args = _parse_args(argv)
    target = pathlib.Path(args.target)

    if not target.exists():
        print(f"CANNOT CHECK: {target} does not exist", file=sys.stderr)
        return CANNOT_CHECK

    kind = classify_target(target)
    if kind == "unclassified":
        print(f"CANNOT CHECK: {target} is unclassified — no positive evidence of a known "
              "artifact kind (skill frontmatter, project-context markers, or standards "
              "markers). Skipping rather than guessing a kind.", file=sys.stderr)
        return CANNOT_CHECK

    try:
        findings = run_lenses(target, kind, args.max_age_days, datetime.date.today())
    except OSError as exc:
        print(f"CANNOT CHECK: {target} could not be read ({exc})", file=sys.stderr)
        return CANNOT_CHECK

    return _report(target, kind, findings)


def _report(target: pathlib.Path, kind: str, findings: List[Finding]) -> int:
    lenses = ", ".join(LENSES_BY_KIND[kind])
    if not findings:
        print(f"clean: {target} (kind: {kind}) — no findings from lenses: {lenses}")
        print("note: mechanical lenses only; lenses 1, 2 and 4 need judgment and did not run")
        return CLEAN

    print(f"{len(findings)} finding(s) in {target} (kind: {kind}); lenses run: {lenses}")
    for finding in findings:
        print(finding.render())
    return FINDINGS


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("target", help="SKILL.md, CLAUDE.md, skill dir, or plugin root")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help=f"re-check window for self-dated claims "
                             f"(default {DEFAULT_MAX_AGE_DAYS})")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
