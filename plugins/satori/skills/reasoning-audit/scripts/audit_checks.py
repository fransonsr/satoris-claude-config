#!/usr/bin/env python3
"""audit_checks.py — the mechanically decidable lenses of /satori:reasoning-audit.

Decides lenses 3 (citations), 5 (self-dated claims), 6-static (bypassed scripts),
7 (structure conventions) and 7's auto-memory analogue, `memory-contract` (the
Claude Code memory frontmatter and index contract). Lenses 1, 2 and 4 need
judgment and are left to the skill's own reasoning; this script only supplies
evidence for them.

Exit codes are the interface, so the same script serves a hook, a CI job and an
interactive run without modification:

    0  clean      — every lens that ran found nothing
    1  findings   — at least one lens fired
    2  cannot check — target missing, unreadable, or unclassifiable

"Cannot check" is deliberately never "clean": a checker that cannot tell must
refuse to bless, because false assurance costs more than a missed run.

Usage:
    audit_checks.py <target> [--max-age-days N]

    <target> may be a SKILL.md, a CLAUDE.md, a skill directory, a plugin root,
    or a Claude Code auto-memory file or directory.
"""

import argparse
import datetime
import io
import os
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence

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
# A self-dated claim: a verification keyword next to an ISO date.
#
# The second row of keywords was added 2026-09-16 for the auto-memory kind, which
# dates its claims overwhelmingly in those words ("confirmed 2026-07-31", "measured
# 2026-09-15") and on which lens 5 — its headline lens — was otherwise near-blind.
# This deliberately changes behaviour for EVERY kind; the knock-on effects are pinned
# by tests (eval-suite classification widens through _has_results_evidence, and an
# un-run results row whose name carries a keyword stops being reported).
#
# The leading \b is not decoration and not only for the new words: without it
# `verified` matches inside "unverified" and `validated` inside "invalidated", so the
# finding asserts the opposite of the text. Both were live defects before this change
# (checked 2026-09-16: zero occurrences in the corpus, so prevention — of a bug that
# had already shipped). The cost is that "reconfirmed", with no boundary after its
# prefix, no longer matches; that trade is deliberate and pinned by test.
DATED_CLAIM = re.compile(
    r"\b(verified|last updated|last checked|last tested|validated|re-verified"
    r"|measured|confirmed|observed|re-checked|rechecked|re-validated|as of)"
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

# Claude Code auto-memory. `metadata.type` is the documented, closed set, which
# makes it the only positive evidence a memory file carries — the `memory/` path
# component is not evidence, per Step 0's rule.
MEMORY_TYPES = {"user", "feedback", "project", "reference"}
# The index the harness itself loads. Identifying this file's ROLE is name-based
# on purpose: the filename is the harness's contract, not an inference. Deciding
# the KIND stays evidence-based — two different questions, two different rules.
MEMORY_INDEX_NAME = "MEMORY.md"
MEMORY_REQUIRED_FIELDS = ("name", "description")
# feedback and project memories are documented to lead with the rule, then carry
# their reasoning and their trigger. Matched loosely on purpose: real bodies write
# `**Why this matters**`, `**Why it moved**`, `**How to apply going forward**`.
# Demanding the literal `**Why:**` would report 21 real files that plainly DO carry
# their reasoning — the noise this lens exists to avoid.
MEMORY_WHY_MARKER = re.compile(r"^\s*\*\*Why\b", re.IGNORECASE | re.MULTILINE)
MEMORY_HOW_MARKER = re.compile(r"^\s*\*\*How to apply\b", re.IGNORECASE | re.MULTILINE)
MEMORY_RATIONALE_TYPES = {"feedback", "project"}
MEMORY_RATIONALE_SAMPLE = 3     # how many filenames to name before "and N more"
# The harness loads memories by their frontmatter, so ANY unusable block — absent,
# unclosed, invalid YAML, or not a mapping — leaves the file inert. One clause rather
# than a table keyed by shape, because it is equally true of all four, and the caller
# owns the separator here exactly as it does for SKILL_FRONTMATTER_CONSEQUENCE.
MEMORY_FRONTMATTER_CONSEQUENCE = ("the harness loads memories by their frontmatter, so "
                                  "this file is inert whatever it contains")
# One wording for the one `_read_text_or_none` failure mode, because two call sites said
# it in slightly different words and a test pins the distinction that wording carries.
MEMORY_UNREADABLE_PROBLEM = "could not be read (unreadable, or not decodable text)"
# An unreadable file's frontmatter is UNKNOWN, not unusable, so it gets its own
# consequence rather than borrowing the frontmatter one — otherwise the operator is sent
# to inspect a YAML block in a file that cannot be opened.
MEMORY_UNREADABLE_CONSEQUENCE = ("nothing about its contents — frontmatter included — "
                                 "could be checked")
MEMORY_INDEX_MAX_LINES = 200    # documented budget; no truncation mechanism cited
MEMORY_ENTRY_MAX_CHARS = 150    # documented as "under ~150" — the tilde is load-bearing
# Anchored on `](target)` rather than on the whole `[title](target)` shape: a title
# containing `]` (two real index entries contain brackets) defeats a `\[([^\]]*)\]\(`
# parse and would report a correctly-indexed file as an orphan.
INDEX_LINK = re.compile(r"\]\(([^)\s]+)\)")
WIKILINK = re.compile(r"\[\[([^\]]*)\]\]")
# `[[ "$STATUS" -eq 0 ]]`, `[[ ]]` and `[[ ... ]]` are bash test syntax, and appear in
# real memory bodies in prose as well as in fenced blocks. A shape test excludes them
# where a fence test alone would not, while still admitting `cc-plugins-java-stack#152`.
WIKILINK_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9#._-]*$")

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


# What an unusable frontmatter block means depends on who loads the file, so the
# mechanics are shared and only the consequence is written per kind.
SKILL_FRONTMATTER_CONSEQUENCE = {
    "absent": "no frontmatter to validate",
    "invalid-yaml": ("YAML-based tooling will reject this file even if the harness "
                     "tolerates it"),
}


def check_frontmatter(path: pathlib.Path) -> List[Finding]:
    """Validate SKILL.md frontmatter against the conventions above."""
    data, problem, kind = _classify_frontmatter(path.read_text(encoding="utf-8"))
    if problem:
        consequence = SKILL_FRONTMATTER_CONSEQUENCE.get(kind, "")
        message = f"{problem}; {consequence}" if consequence else problem
        return [Finding(str(path), 1, "frontmatter", message)]
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
        lines = len(skill_md.read_text(encoding="utf-8").splitlines())
        if lines > SKILL_MD_MAX_LINES:
            findings.append(Finding(str(skill_md), None, "structure",
                                    f"SKILL.md is {lines} lines (past {SKILL_MD_MAX_LINES}); "
                                    "add a layer of hierarchy with pointers to bundled resources"))

    for reference in sorted((skill_dir / "references").glob("*.md")):
        findings.extend(_check_reference_toc(reference))
    return findings


def _check_reference_toc(reference: pathlib.Path) -> List[Finding]:
    lines = reference.read_text(encoding="utf-8").splitlines()
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
        # `previous` advances on every line, including the ones that `continue` below.
        # Assigning it only on the fall-through path left the lookback comparing against
        # a line from before a fence or an Examples block, which suppressed real findings
        # an arbitrary distance past the illustrative content.
        was_previous, previous = previous, line

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
        context = (was_previous + " " + line).lower()
        yield lineno, line, any(cue in context for cue in ILLUSTRATIVE_CUES)


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
        content = target.read_text(encoding="utf-8")
    except OSError:
        return []
    return [Finding(str(path), lineno, "citations",
                    f"`{cited}` resolves but does not contain the cited term `{term}` — "
                    "the link works, so nothing looks broken")
            for term in terms if term not in content]


def _exists(path: pathlib.Path) -> bool:
    """Whether a path resolves — for a path built from text this module did not write.

    `Path.exists()` swallows only ENOENT/ENOTDIR/EBADF/ELOOP and ValueError and re-raises
    every other OSError, ENAMETOOLONG among them, so on a hostile path it raises instead
    of answering. Every caller here is asking a yes/no question about an unvalidated
    token — a backticked citation, an index link target — so a path that cannot be
    answered for is a "no", not a crash.
    """
    try:
        return path.exists()
    except OSError:
        return False


def _resolve_citation(path: pathlib.Path, cited: str,
                      root: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Resolve a cited path, or None if it genuinely does not exist.

    A bare basename is satisfied by a match anywhere under the search roots: a
    SKILL.md citing `pattern_checker.py` means scripts/pattern_checker.py, and
    demanding a literal relative path there produces noise, not findings.
    """
    if cited.startswith("~"):
        expanded = pathlib.Path(cited).expanduser()
        return expanded if _exists(expanded) else None

    for base in _search_bases(path, root):
        if "/" in cited:
            for ancestor in (base, *list(base.parents)[:ANCESTOR_SEARCH_DEPTH]):
                if _exists(ancestor / cited):
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
    """Flag text carrying its own validation date whose re-check window has passed.

    Illustrative lines are skipped, exactly as check_citations has skipped them since
    2026-08-29 — a sample date in a documented example is not a claim anyone should
    re-verify. Lens 3 got that treatment then and lens 5 did not, for no reason beyond
    no date keyword having yet landed in an example; Change 4's added keywords made it
    reachable and `(measured 2026-04-15)`, inside the example handoff document that
    handoff/SKILL.md tells the reader to write, became two false findings.

    The filter is applied once here and handed to all three sub-checks, including
    _check_novelty_markers, which reads whole text and so cannot inherit it from the
    per-line loop.
    """
    allow_headers = not _is_history_document(path)
    prose = [(lineno, line) for lineno, line, illustrative in _walk_prose_lines(text)
             if not illustrative]

    findings = []
    unrun_lines = []
    for lineno, line in prose:
        findings.extend(_check_one_dated_line(path, lineno, line, max_age_days, today,
                                              allow_headers))
        if _is_unrun_row(line):
            unrun_lines.append(lineno)

    findings.extend(_check_unrun_rows(path, unrun_lines))
    findings.extend(_check_novelty_markers(path, prose))
    return findings


def _check_one_dated_line(path, lineno, line, max_age_days, today,
                          allow_headers: bool = True) -> List[Finding]:
    """Judge a line by its NEWEST dated claim.

    Only the newest date governs: "Verified X, re-verified Y" is a maintained claim,
    not a stale one, and reading the older date produced a false positive at tight
    windows (observed 2026-08-29).
    """
    dated = [(k, ds, _parse_date(ds)) for k, ds in _dated_claims_on(line, allow_headers)]
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


def _check_novelty_markers(path: pathlib.Path, prose) -> List[Finding]:
    """Flag a thicket of undated '(NEW)' markers, once per file.

    One marker on genuinely new content is normal. Nineteen, the oldest 4.5 months
    old and labelling the central mechanism, is the signal — reported once with a
    count rather than once per line, so the finding stays readable.

    Takes prose lines rather than whole text so that markers inside a documented
    example of the convention are not counted as uses of it.
    """
    hits = [lineno for lineno, line in prose if NOVELTY_MARKER.search(line)]
    if len(hits) < NOVELTY_MARKER_THRESHOLD:
        return []
    return [Finding(str(path), hits[0], "self-dated",
                    f"{len(hits)} undated '(NEW)' markers in this file "
                    f"(first at line {hits[0]}, last at line {hits[-1]}). A marker with no "
                    "date cannot expire, so past a couple of them it stops distinguishing "
                    "new content from settled content")]


def _dated_claims_on(line: str, allow_headers: bool = True):
    """Yield (keyword, date) pairs for inline claims, dated headers, and table rows.

    `allow_headers=False` suppresses the dated-section-header form, which a CHANGELOG
    uses to record *when something landed* rather than to claim current truth. An
    explicit "Verified <date>" inside a changelog still counts — the exemption is
    narrow, matching the same reasoning that exempts changelogs from the
    SONARQUBE_CLI_TOKEN doc invariant.
    """
    inline = DATED_CLAIM.findall(line)
    if inline:
        return inline
    if allow_headers:
        header = DATED_HEADER.match(line)
        if header:
            return [("section header", header.group(1))]
    row = DATED_TABLE_ROW.match(line)
    return [(row.group(2).upper(), row.group(1))] if row else []


def _is_history_document(path: pathlib.Path) -> bool:
    """A changelog records what was true then; its dated headings are not stale claims."""
    return "changelog" in path.name.lower()


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
            wrapper_texts.append(wrapper.read_text(encoding="utf-8"))
        except OSError:
            continue
    indirect = {s for s in scripts
                if s not in direct and any(s.name in t for t in wrapper_texts)}
    return direct | indirect


def _collect_skill_texts(root: pathlib.Path) -> List[str]:
    return [p.read_text(encoding="utf-8") for p in root.rglob("SKILL.md") if p.is_file()]


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


# ------------------------------------------------ lens 7 analogue: memory-contract


@dataclass(frozen=True)
class _MemoryDocument:
    """One memory file, read and parsed once.

    Every check below needs some slice of this, and re-reading per check would walk
    a ~90-file corpus several times over.
    """
    path: pathlib.Path
    data: dict
    body: str
    problem: str
    kind: str

    @property
    def declared_type(self):
        """The type this file declares, in either shape, un-coerced.

        Returned raw rather than normalized so a caller reporting a bad value can
        show what was actually written.
        """
        metadata = self.data.get("metadata")
        if isinstance(metadata, dict) and "type" in metadata:
            return metadata["type"]
        return self.data.get("type")


def _memory_target_role(target: pathlib.Path) -> str:
    """What this target IS: "corpus", "index" or "memory". Decided once, here.

    Four branches used to re-derive this from the same two primitives, `is_dir()` and the
    filename, and the findings half and the notes half derived it separately — two
    definitions of one identity, which is structurally what round 1's headline bug was
    made of. One function, one answer, and the role is what every branch dispatches on.
    """
    if target.is_dir():
        return "corpus"
    return "index" if _is_index_role(target) else "memory"


def _is_index_role(target: pathlib.Path) -> bool:
    """MEMORY.md beside at least one real memory — the harness's own entry list.

    Frontmatter-agnostic on purpose. Making its ABSENCE an admission condition made the
    "carries frontmatter" finding unreachable on the single-file route, since that is the
    very input the finding exists to report: one file got two verdicts depending on
    whether you pointed at it or at its directory. The frontmatter question belongs
    entirely to `_check_index_integrity`, which is the function that answers it.

    The sibling requirement is what keeps the role evidence-based — the name alone would
    claim any MEMORY.md anywhere — and the index itself is excluded from supplying that
    evidence, or a MEMORY.md carrying memory frontmatter would vouch for its own role.
    """
    return (target.name == MEMORY_INDEX_NAME
            and any(_is_memory_file(p) for p in _memory_documents(target.parent)))


def memory_notes(target: pathlib.Path) -> List[str]:
    """Observations that are explicitly NOT defects.

    Kept off the findings list so they cannot change the verdict: an informational
    item that moves the exit code is a finding wearing a softer word.
    """
    role = _memory_target_role(target)
    notes = [] if role == "corpus" else _single_file_scope_note(role)
    if role == "memory":
        return notes

    index = target if role == "index" else target / MEMORY_INDEX_NAME
    text = _read_text_or_none(index) if index.is_file() else None
    if text is not None:
        notes.extend(_index_budget_notes(index, text))
    if role == "corpus":
        notes.extend(_dangling_wikilink_notes(target))
    return notes


def _single_file_scope_note(role: str) -> List[str]:
    """Name every check that did not run, so `clean` cannot overstate its coverage.

    The list differs by role, and the note built to stop `clean` overstating coverage
    understated it twice: first by omitting the rationale convention, then — for the new
    index route — by omitting that an index target never opens the memories beside it,
    so the per-file contract runs on nothing at all.
    """
    skipped = ["orphan detection", "duplicate `name` values",
               "the Why/How-to-apply convention", "wikilink resolution"]
    if role == "index":
        skipped.append("the per-file contract on the memories beside it")
    else:
        skipped.insert(0, "index integrity")
    return [f"single-file target: {', '.join(skipped)} did not run — each needs the "
            "whole directory. Point at the memory directory for those"]


def _dangling_wikilink_notes(directory: pathlib.Path) -> List[str]:
    """Count unresolved [[links]] once, as information.

    The documented contract is explicit that a dangling link "marks something worth
    writing later, not an error", so this must never become a finding — not even
    though it is trivially detectable.
    """
    documents = [_load_memory_document(p) for p in _memory_documents(directory)]
    known = _known_link_targets(documents)
    dangling = sorted({target
                       for document in documents
                       for target in _wikilink_targets(document.body)
                       if target not in known})
    if not dangling:
        return []
    return [f"{len(dangling)} unresolved [[link]] target(s): {', '.join(dangling)} — "
            "each marks something worth writing later, not an error"]


def _known_link_targets(documents: List[_MemoryDocument]) -> set:
    """What a [[link]] may legitimately resolve to: a `name:` value OR a filename stem.

    The spec said `name:` values only. Measured 2026-09-16, that is wrong for this
    corpus and reports correct work: `feedback-wsl-parallel-agent-crash.md` carries
    `name: wsl-parallel-agent-crash`, and authors link by the stem they can see in the
    directory. Resolving against `name:` alone called 12 RP targets dangling when 4
    genuinely are.
    """
    known = set()
    for document in documents:
        known.add(document.path.stem)
        name = document.data.get("name")
        if isinstance(name, str):
            known.add(name)
    return known


def _wikilink_targets(body: str) -> List[str]:
    return [target.strip() for target in WIKILINK.findall(body)
            if WIKILINK_TARGET.match(target.strip())]


def check_memory_contract(target: pathlib.Path) -> List[Finding]:
    """Check Claude Code auto-memory against its documented contract.

    A directory is a corpus and gets the corpus-level checks too; a single file
    gets only what can be decided from that file alone.
    """
    role = _memory_target_role(target)
    if role == "corpus":
        return _check_memory_corpus(target)
    if role == "index":
        return _check_index_document(target)
    return _check_memory_document(_load_memory_document(target))


def _check_index_document(index: pathlib.Path) -> List[Finding]:
    """The index, audited as an index rather than as a memory.

    The two rules are genuine opposites: a memory must carry frontmatter, an index must
    not. Handing MEMORY.md to the per-file contract therefore reported it for the one
    property that made it an index, on the one file the harness certainly loads.

    Role is decided by `_is_index_role`, on the filename plus a real memory sibling, and
    deliberately not on whether frontmatter is present: that question is this branch's to
    answer, so making its answer an admission condition is what made the finding
    unreachable here in the first place.

    No unreadable guard: every route here decoded this file during classification, so the
    only way to a read failure is a race between the two, and `main`'s own handler turns
    that into CANNOT_CHECK. An unfalsifiable guard was rejected for the same reason
    `_lacks_rationale`'s dead branch was deleted rather than tested.
    """
    return _check_index_integrity(index, index.read_text(encoding="utf-8"))


def _check_index_integrity(index: pathlib.Path, text: str,
                           memory_count: Optional[int] = None) -> List[Finding]:
    """Everything decidable from the index's own claims, shared by both entry points.

    Its claims are: whether it carries frontmatter, whether it lists any entries at all,
    and whether each entry it lists resolves beside it. Not "from the index file alone" —
    resolution reads the filesystem around it — so `text` must be the contents of
    `index`, because entries resolve against `index.parent`.

    Sharing is the point rather than a convenience: the entry-less test lived in the
    corpus path only, so the single-file branch could not tell an index from a
    hand-written status document and returned `clean` on one that loads nothing.

    Orphan detection is deliberately NOT here: a dead entry is a claim the index itself
    makes, while an orphan is a file the index omits, which needs the corpus to see.
    `memory_count` is the corpus's one enrichment — whether the index is entry-less is
    decidable from `text`, but how many memories that strands is not.
    """
    findings = []
    if text.startswith("---"):
        findings.append(Finding(str(index), 1, "memory-contract",
                                f"{MEMORY_INDEX_NAME} carries frontmatter, but it is an "
                                "index, not a memory; the harness loads it as the entry "
                                "list"))
    targets = _index_link_targets(text)
    if not targets:
        findings.append(_entry_less_index_finding(index, memory_count))
    findings.extend(_check_dead_index_entries(index, targets))
    return findings


def _entry_less_index_finding(index: pathlib.Path,
                              memory_count: Optional[int]) -> Finding:
    """One root cause, not N symptoms: a file named MEMORY.md need not be an index at
    all. The bulk-export corpus's is a hand-written project-status document.

    The corpus entry point knows how many memories that strands, and says why it is not
    also listing each of them as an orphan. A single-file target knows neither.
    """
    if memory_count:
        stranded = (f"none of the {memory_count} memories beside it can be loaded into a "
                    "session. Reporting the cause rather than each file, because it is "
                    "one problem")
    else:
        stranded = "nothing beside it can be loaded into a session"
    return Finding(str(index), None, "memory-contract",
                   f"{MEMORY_INDEX_NAME} contains no entries, so {stranded}")


def _index_link_targets(text: str) -> set:
    return {t for line in text.splitlines() for t in INDEX_LINK.findall(line)}


def _check_memory_corpus(directory: pathlib.Path) -> List[Finding]:
    documents = [_load_memory_document(p) for p in _memory_documents(directory)]
    findings: List[Finding] = []
    for document in documents:
        findings.extend(_check_memory_document(document))
    findings.extend(_check_rationale_convention(directory, documents))
    findings.extend(_check_memory_index(directory, documents))
    findings.extend(_check_duplicate_names(directory, documents))
    return findings


def _check_memory_index(directory: pathlib.Path,
                        documents: List[_MemoryDocument]) -> List[Finding]:
    """MEMORY.md is what the harness actually loads, so its integrity gates everything.

    A memory nothing links to can never surface, whatever it says — which makes this
    the highest-signal check in the lens. Measured 2026-09-16: 28 of 92 files in the RP
    scope are orphaned, and their names identify the pattern (completed-status entries,
    chat logs) — exactly the ephemeral content the memory rules say should not persist.
    """
    index = directory / MEMORY_INDEX_NAME
    text = _read_text_or_none(index) if index.is_file() else None
    if text is None:
        return _unreachable_corpus_finding(
            directory, documents, f"there is no readable {MEMORY_INDEX_NAME}")

    findings = _check_index_integrity(index, text, memory_count=len(documents))

    targets = _index_link_targets(text)
    if not targets:
        # `_check_index_integrity` has already named the one root cause; listing every
        # file as an orphan on top of it would report N symptoms of it.
        return findings

    findings.extend(_check_orphans(directory, documents, targets))
    return findings


def _unreachable_corpus_finding(directory, documents, cause: str) -> List[Finding]:
    if not documents:
        return []
    return [Finding(str(directory), None, "memory-contract",
                    f"{cause}, so none of the {len(documents)} memories beside it can "
                    "be loaded into a session. Reporting the cause rather than each "
                    "file, because it is one problem")]


def _check_orphans(directory, documents, targets: set) -> List[Finding]:
    """One finding carrying every orphan's name.

    Not one finding per orphan (28 of them reads as 28 unrelated defects), and not a
    bare count either — each orphan is an individually actionable keep-or-delete
    decision, so the list is the payload, not decoration.
    """
    orphans = sorted(d.path.name for d in documents if d.path.name not in targets)
    if not orphans:
        return []
    subject = ("1 memory has" if len(orphans) == 1
               else f"{len(orphans)} memories have")
    pronoun = "it" if len(orphans) == 1 else "them"
    return [Finding(str(directory), None, "memory-contract",
                    f"{subject} no entry in {MEMORY_INDEX_NAME}, so nothing loads "
                    f"{pronoun}: "
                    f"{', '.join(orphans)}")]


def _check_dead_index_entries(index: pathlib.Path, targets: set) -> List[Finding]:
    """Entries the index claims, that do not resolve beside it.

    `directory` was dropped as a parameter once one caller remained: it always equalled
    `index.parent`, and an argument that must equal a derivable value invites a future
    caller to pass something else — entries would then resolve against the wrong
    directory and produce a plausible wrong list rather than an error.

    An entry that cannot even be stat'd counts as dead, via `_exists`. A malformed entry
    is precisely what this check exists to report, so it must not abort the run: one
    over-long link target used to degrade the whole audit to "CANNOT CHECK: <directory>
    could not be read", losing every other finding and blaming the directory.
    """
    directory = index.parent
    dead = sorted(t for t in targets
                  if _is_local_document(t) and not _exists(directory / t))
    if not dead:
        return []
    subject = ("1 index entry points" if len(dead) == 1
               else f"{len(dead)} index entries point")
    return [Finding(str(index), None, "memory-contract",
                    f"{subject} at files that do not exist: {', '.join(dead)}")]


def _is_local_document(target: str) -> bool:
    return target.endswith(".md") and "://" not in target and not target.startswith("#")


def _index_budget_notes(index: pathlib.Path, text: str) -> List[str]:
    """Length and entry width, as ONE soft-budget observation — a note, not a finding.

    Measured 2026-09-16: the real index was 66 lines (inside the line budget) but 63 of
    those 66 exceeded 150 characters. The documented rule reads "under ~150 characters"
    and the tilde is load-bearing — this is a budget, not something the harness enforces.
    Reported as a finding it moved the exit code, so every real index in the fleet failed
    on a soft convention and the exit code stopped distinguishing anything.

    Takes `(index, text)` to match `_check_index_integrity`: one convention for the index
    helpers, and the caller owns the read and the unreadable case exactly once.
    """
    lines = text.splitlines()
    overlong = [len(line) for line in lines if len(line) > MEMORY_ENTRY_MAX_CHARS]

    problems = []
    if len(lines) > MEMORY_INDEX_MAX_LINES:
        problems.append(f"it is {len(lines)} lines, past the documented "
                        f"{MEMORY_INDEX_MAX_LINES}-line budget (a documented budget, not a "
                        "measured harness limit)")
    if overlong:
        problems.append(f"{len(overlong)} of {len(lines)} lines exceed the ~"
                        f"{MEMORY_ENTRY_MAX_CHARS}-character entry budget "
                        f"(longest {max(overlong)})")
    if not problems:
        return []
    return [f"{index.name} is over budget: " + "; ".join(problems)
            + " — a documented convention, not a harness limit, so it is reported "
              "here rather than as a finding"]


def _check_duplicate_names(directory, documents) -> List[Finding]:
    """Two files claiming one `name`.

    A [[link]] resolves to one of them; the other is unreachable by link.
    """
    by_name = {}
    for document in documents:
        name = document.data.get("name")
        if isinstance(name, str):
            by_name.setdefault(name, []).append(document.path.name)
    return [Finding(str(directory), None, "memory-contract",
                    f"'{name}' is claimed as the `name` of {len(files)} files "
                    f"({', '.join(sorted(files))}); duplicate memories are forbidden, "
                    "and a [[link]] to this name can only reach one of them")
            for name, files in sorted(by_name.items()) if len(files) > 1]



def _memory_documents(directory: pathlib.Path) -> List[pathlib.Path]:
    """The memories in a corpus — every markdown file except the index itself.

    Deliberately every file, not only those that would classify on their own: a
    frontmatter-less note sitting in a memory directory is inert, and saying so is
    the whole point. Classification asks what a file IS when pointed at directly;
    this asks what belongs to a corpus already identified.
    """
    return sorted(p for p in directory.glob("*.md") if p.name != MEMORY_INDEX_NAME)


def _load_memory_document(path: pathlib.Path) -> _MemoryDocument:
    text = _read_text_or_none(path)
    if text is None:
        return _MemoryDocument(path, {}, "", f"file {MEMORY_UNREADABLE_PROBLEM}",
                               "unreadable")
    data, problem, kind = _classify_frontmatter(text)
    body = text.split("---", 2)[2] if not problem else ""
    return _MemoryDocument(path, data, body, problem, kind)


def _check_memory_document(document: _MemoryDocument) -> List[Finding]:
    """Frontmatter contract for one memory.

    An unusable frontmatter block stops the file there: every later check would be
    restating a consequence of the same defect.
    """
    if document.problem:
        # No line number for an unreadable file: `:1` implies a location that was never
        # parsed, and the reader is being told a line to go and look at.
        line = None if document.kind == "unreadable" else 1
        return [Finding(str(document.path), line, "memory-contract",
                        f"{document.problem}; {_memory_consequence(document.kind)}")]

    findings = []
    for field in MEMORY_REQUIRED_FIELDS:
        if document.data.get(field) is None:
            findings.append(Finding(str(document.path), 1, "memory-contract",
                                    f"required field '{field}' is absent"))
    findings.extend(_check_memory_name(document))
    findings.extend(_check_memory_description(document))
    findings.extend(_check_memory_type(document))
    return findings


def _memory_consequence(kind: str) -> str:
    """Why the file is inert — which is not one answer for every way it can be.

    `kind` is the provenance marker saying WHY a document is unusable, and this is its
    consumer. Collapsing the per-kind table to a single string widened the frontmatter
    clause onto a fifth shape it does not fit: a file whose bytes could not be read has
    an UNKNOWN frontmatter, not an unusable one, and telling the operator otherwise sends
    them to inspect a YAML block in a file that cannot be opened.
    """
    return (MEMORY_UNREADABLE_CONSEQUENCE if kind == "unreadable"
            else MEMORY_FRONTMATTER_CONSEQUENCE)


def _check_memory_name(document: _MemoryDocument) -> List[Finding]:
    """`name` is the identity other memories link to as [[name]], so its shape matters.

    Note what is NOT checked: `name` need not match the filename stem. The documented
    examples differ (aesthetic_philosophy.md carries `name: aesthetic-philosophy`), so
    a stem-equality rule would manufacture findings against correct work.
    """
    name = document.data.get("name")
    if name is None:
        return []      # already reported as absent
    if not isinstance(name, str):
        return [Finding(str(document.path), 1, "memory-contract",
                        f"name must be a string, got {type(name).__name__}")]
    if not NAME_PATTERN.match(name):
        return [Finding(str(document.path), 1, "memory-contract",
                        f"name '{name}' is not kebab-case "
                        "(lowercase letters, digits, single hyphens)")]
    return []


def _check_memory_description(document: _MemoryDocument) -> List[Finding]:
    """`description` is loaded as text, so a non-string value is a defect to report.

    `name` has been type-checked since the first version; `description` was the one
    untyped required field on the memory path, while the skill lens type-checks its own
    two functions away. The classification gate must not be what catches this — refusing
    to classify a file is a refusal to report it.

    An empty string is deliberately left alone: it is present and it is a string, and
    there is no evidence in the corpus that it is a problem worth a finding.
    """
    description = document.data.get("description")
    if description is None or isinstance(description, str):
        return []      # absent is already reported by the required-field loop
    return [Finding(str(document.path), 1, "memory-contract",
                    f"description must be a string, "
                    f"got {type(description).__name__}")]


def _check_memory_type(document: _MemoryDocument) -> List[Finding]:
    declared = document.declared_type
    nested = _nests_type_under_metadata(document.data)
    if _is_memory_type(declared) and nested:
        return []

    if _is_memory_type(declared):
        # Valid value, wrong place. Appending the allowed set here read as "'feedback'
        # ... must be one of: feedback, project, reference, user" on the live corpus —
        # true, and it misdirects the operator to the value instead of the nesting.
        return [Finding(str(document.path), 1, "memory-contract",
                        f"type is declared at the top level as {declared!r}; the "
                        "contract nests it under `metadata`, and the harness routes "
                        "memories by `metadata.type`, so a top-level `type:` is not "
                        "read at all")]

    if declared is None:
        detail = "metadata.type is absent"
    elif not nested:
        detail = (f"type is declared at the top level as {declared!r}; "
                  "the contract nests it under `metadata`")
    else:
        detail = f"metadata.type is {declared!r}"
    allowed = ", ".join(sorted(MEMORY_TYPES))
    return [Finding(str(document.path), 1, "memory-contract",
                    f"{detail}. The harness routes memories by this field, so it must "
                    f"be one of: {allowed}")]


def _nests_type_under_metadata(data: dict) -> bool:
    metadata = data.get("metadata")
    return isinstance(metadata, dict) and "type" in metadata


def _check_rationale_convention(directory: pathlib.Path,
                                documents: List[_MemoryDocument]) -> List[Finding]:
    """Report the missing Why / How-to-apply convention ONCE, with a count.

    Measured 2026-09-16: 33 of 86 real feedback/project files lack these, because the
    convention postdates most of the corpus. One finding per file would bury every
    check that actually matters under dozens of style complaints — the same failure
    this skill's own tuning notes record, where 40 findings against correct work were
    cut to 2.

    That 33 is the count under the tolerant match below. A strict `**Why:**` literal
    measures 54, and the 21-file difference is entirely files that carry their reasoning
    under variant wording — so 54 is the number a reader re-measuring with the obvious
    regex would get, and it is the wrong one.
    """
    missing = sorted(d.path.name for d in documents if _lacks_rationale(d))
    if not missing:
        return []

    named = ", ".join(missing[:MEMORY_RATIONALE_SAMPLE])
    if len(missing) > MEMORY_RATIONALE_SAMPLE:
        named += f", and {len(missing) - MEMORY_RATIONALE_SAMPLE} more"
    return [Finding(str(directory), None, "memory-contract",
                    f"{len(missing)} feedback/project memories lack a '**Why:**' or "
                    f"'**How to apply:**' line ({named}) — a rule with no reason cannot "
                    "be re-judged when circumstances change, and one with no trigger "
                    "cannot be applied. A soft convention, reported once as a budget")]


def _lacks_rationale(document: _MemoryDocument) -> bool:
    """Whether a feedback/project memory is missing its reasoning or its trigger.

    A file whose frontmatter is unusable returns False here through declared_type being
    None: one defect, one finding, rather than reporting the same file twice. The
    type-check is also what keeps an unhashable `type:` value out of the set-membership
    test below, which would raise TypeError rather than answering.
    """
    if not _is_memory_type(document.declared_type):
        return False
    if document.declared_type not in MEMORY_RATIONALE_TYPES:
        return False
    return not (MEMORY_WHY_MARKER.search(document.body)
                and MEMORY_HOW_MARKER.search(document.body))


# ------------------------------------------------------- classification


def _read_text_or_none(path: pathlib.Path) -> Optional[str]:
    """A file's text, or None if it cannot be read.

    UnicodeDecodeError is caught alongside OSError because it is NOT an OSError:
    one undecodable byte anywhere in a ~200-file corpus walk would otherwise end
    the run in a traceback rather than a clean refusal.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_frontmatter(path: pathlib.Path) -> dict:
    """A file's frontmatter mapping, empty when there is not one to use.

    Collapses "unreadable", "absent", "unclosed", "invalid YAML" and "not a mapping"
    into one empty mapping, because classification only ever asks whether usable
    evidence is present. The memory-contract lens distinguishes those cases itself,
    since for it the difference is the finding.
    """
    text = _read_text_or_none(path)
    return {} if text is None else _frontmatter_of(text)


def _frontmatter_of(text: str) -> dict:
    """The frontmatter mapping, empty if there is not a usable one."""
    return _classify_frontmatter(text)[0]


def _classify_frontmatter(text: str) -> tuple[dict, str, str]:
    """Return (mapping, problem, kind); on success problem and kind are empty strings.

    Both lenses that report on frontmatter need to say which way it is broken, because
    that difference is the finding, so one parse keeps the reason rather than discarding
    it. `kind` lets each caller append the consequence for ITS kind of file, since the
    same malformed block means different things to a skill and to a memory.

    Empty values rather than None on every path: an absent mapping and an empty one lead
    to the same answer everywhere downstream, and keeping the types unconditional is what
    lets a type checker verify the callers instead of trusting a docstring precondition.
    """
    if not text.startswith("---"):
        return {}, "file does not open with '---'", "absent"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, "frontmatter block is not closed by a second '---'", "unclosed"
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0]
        return {}, f"frontmatter is not valid YAML ({detail})", "invalid-yaml"
    if not isinstance(data, dict):
        return ({}, f"frontmatter parses as {type(data).__name__}, not a mapping",
                "not-a-mapping")
    return data, "", ""


def _is_memory_file(path: pathlib.Path) -> bool:
    """Positive evidence that a file is a memory, in either documented shape.

    Modern files declare `metadata.type`, which is evidence enough on its own. Two
    real files predate that wrapper and carry `type:` at the top level; a bare
    `type:` is too weak to stand alone — it is an ordinary key in static-site
    generators — so the legacy shape must also carry `name` and `description`.
    Requiring all three there costs nothing real: both legacy files have all three.

    `name` must be a usable string, not merely present: it is the identity a [[link]]
    resolves against, and a presence test is satisfied by `name:` with a null value while
    a null test is satisfied by `name: 42` — either would carry a non-memory file through
    the gate whose whole purpose is keeping them out.

    `description` is deliberately only required to be PRESENT. Typing it here rejected
    two different provenances when only one should be rejected: a docs page, which must
    be refused, and a real but incomplete legacy memory whose `description:` is blank,
    which the contract check has a purpose-built finding for. A gate that declassifies a
    broken memory turns a reportable defect into a silent exit-2 refusal of its whole
    corpus, so the typing lives in `_check_memory_description` where it is reported.
    """
    data = _read_frontmatter(path)
    if not data:
        return False
    metadata = data.get("metadata")
    if isinstance(metadata, dict) and _is_memory_type(metadata.get("type")):
        return True
    return (_is_memory_type(data.get("type"))
            and isinstance(data.get("name"), str)
            and "description" in data)


def _is_memory_type(declared) -> bool:
    """Type-checked before membership, so a non-string cannot decide it either way."""
    return isinstance(declared, str) and declared in MEMORY_TYPES


def _holds_memory_files(directory: pathlib.Path) -> bool:
    return any(_is_memory_file(p) for p in sorted(directory.glob("*.md")))


def classify_target(path: pathlib.Path) -> str:
    """Classify from file evidence, never from path.

    Returns one of: skill, standards-claude-md, project-claude-md, script,
    auto-memory, unclassified. Unclassified is a deliberate refusal, not a fallback bucket:
    a lens applied where it may not belong produces confident complaints about
    correct work.
    """
    if path.is_dir():
        if (path / "SKILL.md").is_file():
            return "skill"
        if _holds_memory_files(path):
            return "auto-memory"
        return "unclassified"
    if path.name == "SKILL.md":
        return "skill"
    if path.suffix in SCRIPT_SUFFIXES:
        return "script"
    if path.name.lower() in CLAUDE_MD_NAMES:
        return _classify_claude_md(path)
    if _looks_like_eval_suite(path):
        return "eval-suite"
    if _is_memory_file(path) or _is_index_role(path):
        return "auto-memory"
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
        return _has_results_evidence(path.read_text(encoding="utf-8"))
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
    lowered = path.read_text(encoding="utf-8").lower()
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
    # Deliberately without `citations`: memory cites paths in other repos by
    # nature, so that lens would report mostly-unverifiable cross-repo references
    # and bury everything else. Lens 3's wikilink form lives in memory-contract.
    "auto-memory": ("self-dated", "memory-contract"),
    "script": ("self-dated",),
}


def run_lenses(target: pathlib.Path, kind: str, max_age_days: int,
               today: datetime.date) -> List[Finding]:
    """Run every lens applicable to kind and return the combined findings."""
    if kind == "auto-memory":
        return _run_memory_lenses(target, max_age_days, today)

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


def _run_memory_lenses(target: pathlib.Path, max_age_days: int,
                       today: datetime.date) -> List[Finding]:
    """Memory takes its own branch rather than threading through the skill path.

    A memory corpus has no SKILL.md, no references/ and no scripts/, so every
    skill-shaped helper would either no-op or answer a question nobody asked.
    """
    documents = (sorted(target.glob("*.md")) if target.is_dir() else [target])
    findings = _scan(documents, lambda d, t: check_self_dated_claims(
        d, t, max_age_days, today))
    findings.extend(check_memory_contract(target))
    return findings


def _scan(documents, check) -> List[Finding]:
    findings: List[Finding] = []
    for document in documents:
        text = _read_text_or_none(document)
        if text is None:
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
    _force_utf8_output()
    args = _parse_args(argv)
    # Expand once, here: a `~` or `$VAR` the shell did not expand (from a hook, a config
    # file, or a quoted argument) otherwise reports as a missing file rather than as an
    # unexpanded one, which is a different problem with a different fix.
    target = pathlib.Path(os.path.expandvars(os.path.expanduser(args.target)))
    typed = "" if str(target) == args.target else f" (from '{args.target}')"

    try:
        present = target.exists()
    except OSError as exc:
        # An unusable argument is REFUSED, not folded into "does not exist": an
        # expansion long enough to raise ENAMETOOLONG otherwise escaped as a traceback,
        # whose exit status is 1 — the value the module docstring reserves for FINDINGS.
        print(f"CANNOT CHECK: {args.target} cannot be examined ({exc})", file=sys.stderr)
        return CANNOT_CHECK
    if not present:
        print(f"CANNOT CHECK: {target}{typed} does not exist", file=sys.stderr)
        return CANNOT_CHECK

    try:
        kind = classify_target(target)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"CANNOT CHECK: {target} could not be classified ({exc})", file=sys.stderr)
        return CANNOT_CHECK

    if kind == "unclassified":
        print(f"CANNOT CHECK: {target} is unclassified — {_unclassified_reason(target)} "
              "Skipping rather than guessing a kind.", file=sys.stderr)
        return CANNOT_CHECK

    try:
        findings = run_lenses(target, kind, args.max_age_days, datetime.date.today())
    except (OSError, UnicodeDecodeError) as exc:
        print(f"CANNOT CHECK: {target} could not be read ({exc})", file=sys.stderr)
        return CANNOT_CHECK

    notes = memory_notes(target) if kind == "auto-memory" else []
    return _report(target, kind, findings, notes)


def _unclassified_reason(target: pathlib.Path) -> str:
    """Name only the evidence `classify_target` actually looked for on THIS shape.

    A directory is asked two questions; a file is asked six. Listing all of them either
    way reports reasons that were never evaluated — measured on the live corpus, 11 of 31
    refused directory scopes were told their project-context and standards markers were
    missing, neither of which is consulted for a directory. The `*.md` count is there so
    an empty directory and a directory of non-conforming notes read differently in one
    line; the old message described both as having no evidence at all.
    """
    if target.is_dir():
        candidates = len(list(target.glob("*.md")))
        return (f"it holds no SKILL.md, and none of its {candidates} *.md file(s) "
                "carries memory frontmatter (`metadata.type`, or a legacy top-level "
                "`type:` with a string `name` and a `description`).")
    return ("it is not named SKILL.md or CLAUDE.md, has no .py/.sh suffix, carries no "
            "memory frontmatter, is not MEMORY.md beside a real memory, and is not a "
            "dated results document under an evals/ directory.")


def _force_utf8_output() -> None:
    """Declare this tool's output encoding instead of inheriting the locale's.

    The input half of this bug was reading files without `encoding=`; this is the
    output half, and it is just as real: the checker's own finding messages contain em
    dashes, so under LC_ALL=C (locale encoding ANSI_X3.4-1968) printing a finding
    raised UnicodeEncodeError — a traceback whose exit status is 1, the value the module
    docstring reserves for FINDINGS. Found 2026-09-17 while fixing the read side.
    """
    for stream in (sys.stdout, sys.stderr):
        # isinstance rather than hasattr: reconfigure() belongs to TextIOWrapper, and
        # under a redirection either stream may be something else entirely.
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _report(target: pathlib.Path, kind: str, findings: List[Finding],
            notes: Sequence[str] = ()) -> int:
    lenses = ", ".join(LENSES_BY_KIND[kind])
    if not findings:
        print(f"clean: {target} (kind: {kind}) — no findings from lenses: {lenses}")
        _print_notes(notes)
        print("note: mechanical lenses only; lenses 1, 2 and 4 need judgment and did not run")
        return CLEAN

    print(f"{len(findings)} finding(s) in {target} (kind: {kind}); lenses run: {lenses}")
    for finding in findings:
        print(finding.render())
    _print_notes(notes)
    return FINDINGS


def _print_notes(notes: Sequence[str]) -> None:
    """Informational output, printed either way and counted neither way."""
    for note in notes:
        print(f"note: {note}")


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("target",
                        help="SKILL.md, CLAUDE.md, skill dir, plugin root, "
                             "or auto-memory file or directory")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help=f"re-check window for self-dated claims "
                             f"(default {DEFAULT_MAX_AGE_DAYS}; not kind-aware — pass 30 "
                             f"for auto-memory and for model/tool capability content)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
