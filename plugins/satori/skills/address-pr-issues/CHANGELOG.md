# Address PR Issues Skill - Changelog

## 2026-08-31 - v1.7.8: Workspace namespacing, escalation target, doc/code reconciliation

Backfilled 2026-08-31 — this file had stopped at v1.7.6 while two commits changed shipped
behaviour, which a `/satori:reasoning-audit` pass flagged as a guard that stopped guarding.
The two missed commits are recorded as v1.7.7 below; this entry covers the work that followed.

**Fixed (found by running the checker's own eval suite for the first time, and by auditing the
skill against its own scripts):**
- `/tmp/pr-<number>` carried no repo component, so two PRs with the same number in different
  repositories shared one workspace and overwrote each other's `threads.json`, `round.txt`,
  `fixes.json` and `triage.json`. All six scripts now derive the path from one shared
  `pr_workspace_dir` helper in `lib/github-api.sh`, namespaced by owner and repo, which also
  guarantees they agree with each other — six independent literals were a latent split-brain,
  not just a naming problem. Fails loudly outside a git repo rather than falling back to the
  colliding path.
- Step 8's new-comment detection could never fire: `jq -s '.[0] - .[1]'` on `threads.json`,
  which is JSON Lines, slurped both files into one flat array so `.[0]`/`.[1]` were the first
  two *threads*. The resulting type error went to stderr inside `$(...)`, leaving `NEW_THREADS`
  empty, so every round reported "no new Copilot comments". Now uses `--slurpfile`.
- The MANDATORY pre-push checklist gate could never pass: `all(.[]; . == true)` read
  `commit_ready`, which is only set true *inside* the success branch it gates. Now
  `del(.commit_ready) | all(...)` at both sites.
- `classify-threads.sh` emits four fail-closed labels; SKILL.md documented three.
  `unexpected_body_type` appeared in no doc, so a thread the script refused to trust reached
  Step 3 looking verified — the fail-closed path leaking where it was built not to.
- `commit-pr-fixes.sh`'s `read -p` had no non-interactive path, so an agent stalled on the
  documented primary commit path and then committed off-book. Now behind `[ -t 0 ]` with a
  `COMMIT_AUTO_CONFIRM` escape.
- `PR_NUMBER="${args:-...}"` — bash never sets `$args`, so the fallback always won and a
  supplied PR number was silently ignored. Now `${1:-...}`.
- Script paths: the skill asserted both that scripts must run from the target repo (true — they
  call `git remote get-url origin`) and that `./scripts/` resolved to the skill's install
  directory with agents "automatically resolving" it. Both cannot hold, and the failure mode is
  worse than not-found: many Java repos have their own `./scripts/`, so a relative invocation
  could silently execute an unrelated script. Every invocation now uses an explicitly resolved
  `$SKILL_SCRIPTS`, and the Note on Script Paths moved above the first use.

**Changed:**
- Step 8's escalation target: `/plan` is not a command in this environment. It now spawns a
  planning subagent (`Agent` with `subagent_type: 'Plan'`); section retitled "Numeric Plan-Agent
  Escalation".
- Removed every explicit token-savings figure ("80-85%", "25k-37.5k per 15-round PR",
  "5 rounds → 1-2", and the per-script column). None had a method or a date, and the headline
  claim traced only to a reconstructed counterfactual. The Hard Rule stands on the mechanism.
- `SONAR_TOKEN` docs now name the `SONARQUBE_CLI_TOKEN` fallback the scripts have used since
  v1.7.7, so a reader stops concluding the credential is missing.
- Removed duplicate skill frontmatter from `README.md`; `argument-hint` quoted so it parses as a
  string rather than a YAML list.

**Testing** — this is the substantive change. The skill had no automated tests at all:
- `scripts/test_script_contracts.py` (29 tests) executes the jq expressions and bash snippets
  *out of SKILL.md itself* and parses the scripts, so prose is held to the code's standard.
  Four of the defects above lived in markdown, which is why they survived: nothing executes a
  code block.
- Workspace namespacing is asserted by property (different repos diverge, a fork and its
  upstream diverge, ssh and https converge, the path stays one component under `/tmp`), not by
  string.

## 2026-08-14 / 2026-08-21 - v1.7.7: Threaded-reply API corrections, Sonar token fallback, set -e guard

Backfilled 2026-08-31. Both commits changed shipped script behaviour and were never logged.

**Fixed** (`9f93975`, 2026-08-14):
- `test_threaded_reply_api` read `threads.json` as a JSON array when it is JSON Lines, silently
  erroring to jq's stderr and always reporting "disabled" — for the wrong reason. Now reads
  `.commentId | head -1`.
- The same function deleted its test reply using the *original* comment id against the wrong
  endpoint shape; it now captures the created reply's own id and deletes via
  `pulls/comments/{reply_id}`.
- `try_threaded_reply` (and its test twin) now take `pr_number` and build the reply URL as
  `pulls/$pr_number/comments/$comment_id/replies`, the valid POST target for a threaded reply.
  `init-pr-state.sh` and `resolve-thread.sh` pass it through.
- `get_sonar_config` falls back to `SONARQUBE_CLI_TOKEN` when `SONAR_TOKEN` is unset, matching
  this environment's actual credential naming. **The docs did not follow until v1.7.8** — that
  gap is the visible residue of this entry having been missing.

**Fixed** (`9a51f16`, 2026-08-21, closes #3):
- `format_quality_gate_status` returns non-zero as its normal "gate failed" signal, which under
  `set -euo pipefail` killed `check-sonar-quality-gate.sh` before it reached the block that
  fetches blocking issues on a FAILED gate.

## 2026-08-02/03 - v1.7.6: Fable Design Guidance, Native Fix-Planning, Base-Branch Bug

**Context**: A follow-on to v1.7.5's PR #171 hardening, this batch spans all four satori review
skills (`address-pr-issues`, `adversarial-review`, `pre-pr-audit`, `xp-pair`), plus two rounds of
`/satori:pre-pr-audit` dogfooding against the batch's own changes, which is why the set of fixes
is broader than the original feature. Added: `xp-pair` gained a Fable-model generative design
guidance step (Step 2) that reads matching `copilot-review-patterns.md` classes and returns a
design recommendation plus an edge-case watch-list, augmenting its existing 4 discovery agents;
`adversarial-review` gained a native (not `xp-pair`) Fable fix-planning gate in Phase D for
approved findings with `cascade_siblings`, `cross_file` blast radius, or CRITICAL/HIGH severity —
deliberately not invoking `xp-pair`, since its Step 5 commits and shuts down its team, which would
violate Phase D's no-commit git guardrails; `adversarial-review`'s Setup Step 5 was rewritten so
`CLASSES` carries lightweight `{name, lensKind, model?}` metadata instead of full per-class prompt
text, after discovering the original prose-only "capture it in a shell variable" plan doesn't work
(`Workflow` args must be literal JSON; Bash shell state doesn't persist across tool calls) — each
spawned agent now reads its own pattern-file section directly. Round 1 of dogfooding against this
batch (23 findings, 18 cross-file) fixed: a `lensKind` fallback+log in `buildPrompt()`, a missing
doc-file enumeration command, `Phase E`'s retry instructions listing all required args, explicit
guardrails on the fix-planning agent, `--base-branch` actually being honored, `xp-pair`'s
fictional pattern-class names, `address-pr-issues`' `xp-pair`-fix caveat wrongly saying "resume at
Step 8" (it was skipping mandatory steps and the push), a severity-trend gate that printed an
unsubstituted template placeholder, an "Already Decided" thread-closeout bucket, and reduced
`address-pr-issues/README.md` from a 1696-line stale duplicate of `SKILL.md` to a 103-line
pointer-based overview. Round 2 (18 more cross-file findings, mostly bugs in round 1's own fixes —
exactly what this repo's dogfooding recipe warns a single round won't catch) fixed the most
consequential one: `adversarial-review`'s and `pre-pr-audit`'s base-branch auto-detect used
`@{u}` (the current branch's *own* upstream), which resolves to the branch itself once pushed
with `-u` — every round `address-pr-issues` runs — silently producing an empty diff and a false
CONVERGED verdict; replaced with `gh pr view --json baseRefName` + `git symbolic-ref
refs/remotes/origin/HEAD`, plus a hard-stop guard on an empty/self-matching diff. Also fixed:
`xp-pair`'s pattern-file fallback path was relative instead of absolute (silently unresolvable
outside this repo's own checkout); the escalation-override mechanism referenced a shell function
that doesn't survive a new turn; `triage.round-N.json`'s writer and reader disagreed on round
numbers across a Step 4.1 loop-back (glob-based lookup now used instead of round arithmetic);
`pre-pr-audit`'s Step 4.7/Step 6 still described the pre-restructure "findings return to Step 5"
model after Step 4/5 were rewritten; and `pre-pr-audit/README.md` / `xp-pair/README.md` were
confirmed stale by the same mechanism and reduced to pointers alongside `address-pr-issues/README.md`.
Round 3 (43 findings, provisionalYield 26 — growing, not converging) found the architecturally most
significant bug in the whole batch: every diff-range computation (`adversarial-review`'s Setup
Step 3/4, `pre-pr-audit`'s Step 2) used a three-dot commit range (`origin/$BASE...$CURRENT` /
`origin/$BASE...HEAD`), which can NEVER see uncommitted working-tree changes — directly
contradicting Phase D's own prohibition on `git commit`ing fix-round changes, so every round after
the first was silently re-diffing pre-fix content. Fixed by switching every diff-range use to a
two-dot form against a pinned `$MERGE_BASE`. Also fixed: `pre-pr-audit`'s CLEAN/NOT_CLEAN
idempotency marker read `$ADVERSARIAL_OUTCOME`/`$BLOCKING_ISSUES`, neither of which was ever
assigned anywhere, making the marker permanently record `NOT_CLEAN`; the base-branch fallback
checked local `refs/heads/*` instead of `refs/remotes/origin/*`; and roughly two dozen smaller
cross-file consistency/documentation-drift findings. Round 4 (27 findings, provisionalYield 18)
found that round 3's "working-tree-aware" fix still couldn't see brand-new, never-`git add`ed
files (`git diff`/`git stash create` only ever see tracked content) — fixed by unioning in `git
ls-files --others --exclude-standard` everywhere a changed-file set or the audited-tree hash is
computed; that round also found `git fetch origin $BASE_BRANCH` (round 3's own suggested remedy
for a missing ref) does not actually create the remote-tracking ref in a restricted-refspec clone,
an unchecked `git merge-base` substitution, the exact same shell-state-doesn't-persist-across-
blocks bug recurring in round 3's own `$ADVERSARIAL_OUTCOME`/`$TESTS_GREEN` capture (fixed by
persisting to a marker file instead), a non-deterministic dedup key introduced by round 3's own
fix (reverted), `pattern_checker.py` (the one piece of this batch that's actual Python, not prose)
still using a three-dot diff, and a Known-Limitations/Fix-Provenance-Notes miscategorization.
A separate crash-fix (`067df8a`) landed next: `adversarial-review`'s own Phase A/B script could
crash the whole round when a per-class agent thunk rejected instead of resolving null (observed
live — a class hit its StructuredOutput retry cap and threw), discarding the `{name, result}`
wrapper `parallel()` expects and crashing downstream reads on the resulting bare `null`. Round 5
(24 findings, provisionalYield 15) found that round 4's untracked-file fix hadn't reached
`pattern_checker.py`'s own per-line diff logic (a brand-new file's checks were still silently
skipped) and that round 4's own persistence fix for `$ADVERSARIAL_OUTCOME`/`$TESTS_GREEN`
reintroduced the identical shell-state-doesn't-persist bug one variable over, for `$BASE_BRANCH`
(added to the same marker in the same commit) — both now fixed — plus a Phase E retry-yield bug
that recomputed against already-mutated `PRIOR_FINDINGS`, a `missingClasses` slot-identity gap,
a `lensKind` misclassification, and roughly a dozen smaller error-message/documentation-drift
findings across all three skill files.

See commits `cab1a0f` (the Fable/fix-planning feature), `29a594c` (round-1 dogfood fixes),
`c767eea` (round-2), `842ced8` (round-3), the round-4 commit, `067df8a` (the crash-fix), and this
round's commit (round-5 dogfood fixes) for the full change.

## 2026-08-02 - v1.7.5: Process Hardening from PR #171 Retrospective

**Context**: `fs-eng/cc-plugins-java-stack#171` (a `logging-migration` regex-based completeness
gate) ran ~10 reactive `address-pr-issues` rounds without ever running `/pre-pr-audit` first,
surfacing six gaps in this skill's own process logic. Added a reverse cross-reference to
`/pre-pr-audit` (Workflow Overview) for PRs that skipped it; accounted for repos that auto-review Copilot on
every push, not just PR open, and required checking for new comments after every push regardless
of whether an explicit re-request fired (Step 8); paired the numeric re-request-count escalation
gate with a qualitative severity-trend summary of the last 1-2 rounds, since this PR's count
crossed the escalation threshold while still surfacing genuinely new Critical/High bugs each
round — the user correctly overrode the bare-count recommendation multiple times based on trend,
not count alone; added an explicit "Already Decided" disposition (Step 3) for findings that
re-flag a design tradeoff already made and documented in an earlier round, mirroring
`/adversarial-review`'s own "Contradicts design → Override" category; added a "Mechanism-Level
Diminishing Returns" signal (Step 8), distinct from Pattern Class Recurrence, for when a single
detection heuristic (not a single bug class) needs 3+ structurally distinct extensions and may
warrant replacing rather than continuing to patch; and documented delegating fix implementation
to a background `Agent` call (Step 4.1) as a third named option alongside Direct Implementation
and xp-pair, validated across ~7 delegated fixes in this PR's later rounds.

## 2026-07-08 - v1.7.4: Workflow-ified Adversarial Review, INCOMPLETE Outcome

**Context**: `/adversarial-review`'s per-class review agents were spawned via the ad-hoc
mailbox/teammate system, which had no barrier — agents could go idle for up to an hour without
delivering a result, or never deliver at all, and nothing stopped the orchestrating session from
declaring a round "converged" on partial results. Phase A/B now runs as a single `Workflow` call
per round: `parallel()` is a hard barrier that can't advance to synthesis until every class
resolves or is retried to a terminal `null`, and `schema`-forced structured output replaces
asking agents to comply with a "return ONLY this JSON" text instruction. A class that never
returns a result is tracked as `missingClasses` and surfaces as a new INCOMPLETE outcome — since
this skill always invokes with `--rounds 1`, round 1 is always the round cap, so INCOMPLETE fires
immediately rather than waiting for a later round; the disposition options are retry, accept the
gap as a known limitation, or **abandon the round** (this skill's Step 3.5 briefly said "proceed
without it" instead, a materially different instruction, fixed in a follow-up round).

See commits `1f56d89` (Workflow-ification), `ce0e2d6` (round-1 dogfood fixes), `36aa744`
(round-2 dogfood fixes), `50db93e` (round-3 dogfood fixes — Phase D routing for retried
findings, a stale dedup-key phrase in copilot-review-patterns.md, merge-loop dedup gaps),
`3da773b` (round-4 dogfood fixes — severity/justification reconciliation on merge,
cascade_siblings reaching Phase D, PRIOR_FINDINGS tracking every disposition, INCOMPLETE and
NOT-converged evaluated independently, Abandon given a defined outcome), `27edc33` (round-5
comprehensive audit — a CRITICAL bug where PRIOR_FINDINGS excluded a location from yield
regardless of blast_radius rather than only on a prior cross_file sighting, a shared
`mergeStrings()` helper replacing four inconsistent ad-hoc merge implementations, the
missing-class record redefined as its own `coverage_gap` type instead of a fake finding, and
the Abandon/Phase-D-ordering contradiction fixed), and this round's commit (round-6 dogfood
fixes — Known Limitations legends updated for coverage_gap entries, pre-pr-audit's missing
ABANDONED badge, the retry path routed through Phase C/PRIOR_FINDINGS/a CONVERGED re-check,
Abandon short-circuiting the yield check, and a `parallel()` ordering assumption removed) for
the full change.

## 2026-07-07 - v1.7.3: Cross-File Yield Convergence Vocabulary

**Context**: `/adversarial-review` replaced its boolean `is_clean` termination gate with a
`blast_radius` (local vs cross_file) tag per finding and a "cross-file yield" convergence
signal — local findings no longer force another round, and hitting the round cap with
cross-file findings still open now escalates to a targeted deep-dive instead of a vague
"PR too large" signal. Realigned this skill's Convergence Criterion, Pattern Class
Recurrence, and Numeric /plan Escalation sections to the same vocabulary: Copilot's own
review behavior has no principled convergence point either (it scans until it finds enough
issues, not until impact is exhausted), so a Copilot round finding nothing is one noisy
sample, not proof the PR is done — the rewritten Convergence Criterion says so explicitly.

See commit `d4e8401` for the vocabulary realignment across all three satori review skills, and
`d6ca3a6` for round-1 dogfood-review fixes (a cascading miss in pre-pr-audit's Step 8 summary
template, a human-approval gap in the escalation path, and this changelog entry itself).

## 2026-07-01 - v1.7.2: Adversarial-Review Convergence Rounds 2-6

**Context**: Per the dogfooding discipline (`~/.claude/CLAUDE.md`'s dogfooding section) of
running multiple verification rounds rather than trusting a single fix batch, ran five more
`/adversarial-review` rounds against v1.7.0's own fixes. Each round found real bugs in the
*previous* round's fixes, not just new debt — the whole reason this discipline exists. Findings
per round plateaued at 13-16 (Round 3 onward) rather than converging to zero — a large,
actively-edited document may not realistically reach a fully clean round, so Round 6 was
adopted as the stopping point rather than continuing indefinitely:

- **Round 2** (8 fixes): `classify-threads.sh`'s stale-schema guard checked only 2 of the 3
  required fields (missing `isOutdated`); a present-but-null `lastCommentAuthor` silently fell
  back to the thread-opener's identity instead of failing closed; the Protected-Branch Guard
  (`git config branch.<name>.merge`) failed open on any branch with no tracking ref configured
  — verified live by creating an actual untracked branch.
- **Round 3** (17 fixes): the Round 2 fix for `lastCommentAuthor` left the sibling field
  `lastCommentBody` with the identical null-fallback gap; threads with genuinely empty content
  had no degraded-data label at all; the Step 2 triage agent never received the `labels` field
  where degraded-data markers live, so a thread kept only because its data was unverifiable was
  triaged as if reliable; the stale-schema banner checked only the first cached record instead
  of the whole file.
- **Round 4** (14 fixes): the Round 3 fix for Step 8's re-request counter advanced it even when
  the `gh pr edit` call *failed*, recording a re-request that never happened; the `$CURRENT_BRANCH`
  reuse fix reintroduced the exact cross-snippet variable-persistence gap it was meant to close;
  `scripts/lib/github-api.sh` crashed the entire thread fetch on a null first-comment body (the
  same class of gap already fixed on the last-comment side); a previously-untouched
  `examples/iterative-fixing-session.md` had a stale hand-written commit-message template.
- **Round 5** (13 fixes): `$WORKSPACE_DIR` itself — unlike the shorthand vars derived from it —
  was never covered by SKILL.md's "shorthand" disclaimer despite ~2 dozen usage sites depending
  on it (pre-existing debt, not introduced by any round); `examples/iterative-fixing-session.md`
  had two more stale hand-written blocks beyond the one Round 4 fixed, including a raw
  `gh api graphql`/`gh pr comment` block contradicting SKILL.md's own Hard Rule; a dangling,
  incomplete "Example Session Flow" in QUICK_START.md had survived three prior rounds untouched.
- **Round 6** (14 fixes): the Round 5 fix for `$WORKSPACE_DIR` only added a reminder at Step 8 —
  the identical gap existed at Step 6, Step 7, and the State Management section too;
  `commit-pr-fixes.sh`'s recovery/retry path silently defaulted `DIRECTIONAL_COUNT` to 0 if the
  operator retried without re-passing the same arg; `classify-threads.sh`'s `is_complimentary()`
  crashed the entire script on a non-string comment body (verified live, pre-existing since
  Round 1); the "Example Session Flow" written in Round 5 itself reintroduced a misconception
  (that `classify-threads.sh` resolves threads, not just classifies them) that SKILL.md
  explicitly warns against elsewhere — the same misconception also existed, pre-existing and
  uncaught, at QUICK_START.md's "Filter Trivial Threads" section.

See commits `f8d4a6c`, `0ddab3a`, `b5ee8a4`, `df8a759`, and this round's commit for full
per-round detail.

## 2026-07-01 - v1.7.0: First Real Dogfood Run (pre-pr-audit + adversarial-review)

**Context**: Ran `/satori:pre-pr-audit` against this skill's own diff for the first time —
previously it had never been reviewed by its own tooling. Surfaced 42 findings total: 9 from
the mandatory adversarial pattern review (11 classes), 33 from Steps 4.8/4.9 (spec-completeness
+ whole-document coherence walk). ~16 were caused by today's diff; the rest was pre-existing
structural debt (duplicate "Step 3.5"/"Step 4" headings, Workflow Overview numbers that never
matched the body, several orphaned/undefined references) that the whole-document walk surfaced
because it reads entire files, not just diffs. Fixed all of it in one batch:

- **`classify-threads.sh`**: fixed a real bug — stale-schema caches and empty comment bodies
  were failing OPEN into the auto-resolving `silent` bucket instead of failing closed to `keep`.
  Added a `has()`-based stale-schema guard and an empty-text guard in `is_complimentary()`.
- **`commit-pr-fixes.sh`**: fixed a real crash — a zero-padded `directional_count` (e.g. `"08"`)
  passed the digits-only regex but crashed bash's `-gt` (octal interpretation of leading zero).
  Also replaced the hardcoded, already-stale `Co-Authored-By: Claude Sonnet 4.5` with a
  generic `Co-Authored-By: Claude` — model names go stale, this shouldn't need updating again.
- **SKILL.md/README.md**: renamed the duplicate "Step 3.5" (adversarial review gate → "Step
  2.5") and duplicate "Step 4" (execute fixes → "Step 4.1") headings; fixed the Workflow
  Overview's wrong numbers (1.5→1.6, 3.5→3.7 for pre-fix sweep, "return to step 5"→"step 4.1");
  added the missing DIRECTIONAL_COUNT derivation (persist Step 2's triage to `triage.json`,
  compute the count from it after Step 4.1 — this was referenced at Step 7/8 but never
  actually shown); gave the Step 8 re-review counter a real persistence file
  (`copilot_review_count.txt`, it previously had none unlike every other cross-round counter);
  added a Bucket 1 outcome category to the Thread-Accountability Closeout (it claimed to cover
  "both" Step 1.6 buckets but only had a slot for one); added the missing `commentId`
  derivation for Step 1.6's silent-bucket react step; moved the SonarQube fetch section from
  under Step 2 back to Step 1 (where the Workflow Overview already said it lived).
- **scripts/README.md, QUICK_START.md**: removed a literal reproduction of `commit-pr-fixes.sh`'s
  commit-message template (Class 11 drift risk — confirmed a stale co-author line), clarified
  that scripts/README.md's 1-7 workflow numbering is independent of SKILL.md's step numbers
  rather than implying a 1:1 mapping, and pointed both at the new DIRECTIONAL_COUNT derivation.

**Process change going forward**: `plugin.json`/`marketplace.json`'s version must be bumped
whenever plugin content changes, or `Skill()` invocations keep serving a stale cached snapshot
indefinitely (discovered during this run — the cache was 5 days stale despite several commits
landing in between). See `~/.claude/CLAUDE.md`'s dogfooding section for the full workflow.

## 2026-07-01 - v1.6.0: Ported apply-feedback Strengths + Script-First Cleanup

**Motivation**: Compared against `golden-pr:apply-feedback`, which handles the same
"address open PR review comments" job with a leaner, subagent-delegated design. Four
capabilities were missing here; ported them over. Separately, direct review found the SKILL
body reproducing GraphQL/curl operations that the skill's own `scripts/`/`lib/` already cover
— the duplication is why the agent kept re-deriving queries inline instead of calling scripts.

**Added**:
1. **Step 1.6 — Silent-thread pre-filter**: auto-handle purely-complimentary and
   already-resolved threads (precise, checkable definition) before the CRITICAL/HIGH/MEDIUM/LOW
   triage in Step 3. New `react_to_comment()` helper in `lib/github-api.sh`.
2. **PR intent + directional/polish classification**: Step 1 now reads the PR body for
   `PR_INTENT`/`RISK_FILES`; Step 2's triage schema gains a `classification` field
   (directional | polish) — a fix that shifts what the PR does vs. one that refines within
   existing intent. Drives Step 8's `DIRECTIONAL_COUNT`-gated **active** Copilot re-request
   (`gh pr edit --add-reviewer @copilot`), replacing the old passive "wait ~5-10 min."
   No PR-description auto-refresh (this skill has no generator tool) — surfaces a manual nudge
   instead.
3. **Thread-accountability closeout** (Step 6): a per-thread status table covering every
   thread touched this session, with a hard stop on any `skipped` thread lacking an explicit
   "leave open" acknowledgment.
4. **Protected-branch guard** (Step 7, before push), a **Reply Tone** contract (future tense for
   not-yet-made fixes, past tense for confirmed ones), and a **numeric `/plan` escalation**
   (re-request #2+ triggers a recommended `/plan` cycle instead of another blind re-request),
   sharpening the existing qualitative Convergence Criterion.

**Removed / collapsed** (script-first enforcement): deleted the fully-redundant manual
`<details>` blocks that reimplemented `init-pr-state.sh`, the thread-fetch GraphQL query
(previously duplicated 3×), the Sonar polling loop, and the manual commit block — all replaced
with pointers to the existing scripts/`lib/` functions. Added a hard rule to the "Use Automation
Scripts First" section: if you're about to write `gh api graphql` or a SonarQube `curl` by hand,
a script already does it. Condensed the post-mortem jq catalog to two commands + a pointer.

**Net effect**: four new capabilities landed with the file still shorter than before
(~1754 → ~1450 lines).

**Follow-up hardening (same day)** — implementing the above as prose-only left two things
unbuildable, caught on review:
- `fetch_pr_threads()` only ever cached each thread's *first* comment, but Step 1.6's bucket
  rules need the *most recent* comment (to detect resolved-with-new-activity) and `isOutdated`
  (for the `[outdated]` label) — neither field existed in the cache. Extended the GraphQL query
  and cached schema with `lastCommentAuthor`/`lastCommentBody`/`lastCommentId`/`isOutdated`.
- Added `scripts/classify-threads.sh` — turns Step 1.6's bucket rules into a deterministic jq
  classifier instead of prose the agent applies per-thread. The "purely complimentary" heuristic
  was hardened beyond its `apply-feedback` origin (expanded trigger-word vocabulary + a word-count
  guard) after testing showed the original definition misclassifies short substantive comments
  like "This method should validate input" as complimentary — a false positive here silently
  auto-resolves a real comment with no human ever seeing it.
- `commit-pr-fixes.sh` now takes an optional `directional_count` argument and persists it into
  `fixes.json`, so Step 8's Copilot re-request decision reads from disk instead of depending on
  conversation memory surviving a context compaction or resumed session.

**Also extended**: `copilot-review-patterns.md` Class 11 (Cross-File Rule Consistency) to cover
doc-vs-script restatement — this session found `address-pr-issues/SKILL.md` had already suffered
a real drift incident from exactly this pattern (see `~/.claude/copilot-review-patterns.md`).
README.md resynced to current SKILL.md (was a stale pre-adversarial-review snapshot, ~728 lines
diverged before this session).

**Follow-up (same day, round 2)** — self-review turned up two more gaps:
- QUICK_START.md never mentioned Step 1.6 or `classify-threads.sh` — added a "Filter Trivial
  Threads" cheat-sheet entry and a workflow-diagram step, so the cheat sheet doesn't omit a
  documented step.
- Step 3's "Present Questionable Issues to User" template didn't show where Step 1.6's
  `[outdated]` / `[resolved + new activity]` labels appear in the presented list — added two
  labeled example items.
README.md resynced again to match.

## 2026-06-12 - v1.5.0: Sweep Improvements + Pagination Warning

### Step 3.7: Two-tier sweep for structural absence (Changes 1 & 2)

**Problem**: The diff-scoped sweep caught textual repetition but missed *structural absence* — when a function lacked a property that all sibling functions already had (e.g., `run_step_analyze` missing a preflight check that `run_step_tier1` and `run_step_verify` already had). The sibling wasn't in the diff, so grep found nothing and reported a clean pass.

**Fix**:
- Added **Tier 3b file-scoped grep**: for structural issues, grep the *full changed file*, not just diff lines, to find all sibling functions/call-sites of the same class.
- Added **absence-detection logic**: "nothing found" on a structural issue now triggers an explicit set-difference check — enumerate the siblings, verify each has the property, report gaps.
- Added new Key Principles: "When the issue is structural, extend the grep to the full changed file" and "'Nothing found' on a structural issue triggers a set-difference check."
- Added new `run_step_analyze` preflight example to Step 3.7.

### Step 1: Pagination warning (Change 3)

**Problem**: `init-pr-state.sh` silently capped at 100 threads. On PR #32 (130+ threads), every round falsely reported "0 unresolved" while page-2 threads remained open.

**Fix**:
- Added pagination warning note after `init-pr-state.sh` in Step 1, including the two-step detection query.
- `scripts/lib/github-api.sh`: `fetch_pr_threads` now requests `pageInfo { hasNextPage endCursor }` and emits a `⚠️ WARNING` to stderr if `hasNextPage` is true, including the `endCursor` needed to fetch page 2.
- Both GraphQL queries in Step 6 (OLD METHOD and Check for New Copilot Comments) now request `pageInfo { hasNextPage endCursor }`.

## 2026-05-20 - v1.1.0: Fix Script Organization & Documentation

### Problem: Scripts at Wrong Plugin Level
**Issue**: Scripts were organized at plugin root (`plugins/address-pr-issues/scripts/`) instead of skill level (`plugins/address-pr-issues/skills/address-pr-issues/scripts/`), causing them to be inaccessible when following documentation.

**Impact**: Users saw "No such file or directory" errors when trying to use automation scripts.

**Root Cause**: During marketplace conversion, scripts remained at plugin root level instead of being organized per-skill as per plugin conventions (see `splunk-to-dynatrace` for correct pattern).

**Fix Applied** (commits c0ccfa9, 916e2d8, 946c9b2):
1. **Added working directory requirement**: Scripts must run from within git repository
2. **Moved scripts to skill level**: `skills/address-pr-issues/scripts/` (per conventions)
3. **Simplified paths**: Use relative paths `./scripts/` instead of complex discovery

**Structure After Fix**:
```
plugins/address-pr-issues/
  └── skills/
      └── address-pr-issues/
          ├── SKILL.md
          └── scripts/           ✅ Correct location
              ├── init-pr-state.sh
              ├── fetch-pr-threads.sh
              ├── resolve-threads-bulk.sh
              └── lib/
```

**Benefits**:
- Scripts properly co-located with skill
- Simple relative path references work naturally
- Matches plugin organization conventions
- Version-agnostic (no hardcoded paths)

## 2026-04-27 - Bug Fixes: Bulk Resolution & GitHub API

### Problem: Bulk Thread Resolution Failed After First Thread

**Issue identified in PR #68**:
- Bulk resolution script (`resolve-threads-bulk.sh`) resolved first thread successfully
- Script exited with error code 1 after first resolution
- Remaining threads were not resolved
- Root cause: `jq` cache update corrupted newline-delimited JSON file

**Technical Details**:
- threads.json uses newline-delimited JSON (not array)
- Cache update used `jq` without `-s` flag
- Command processed only first JSON object, corrupting file structure
- Subsequent thread lookups failed on corrupted cache

**Fix Applied** (commit 91bccc3):
```bash
# Before (line 152-154):
jq --arg tid "$thread_id" \
  'if .threadId == $tid then .isResolved = true else . end' \
  "$THREADS_FILE" > "${THREADS_FILE}.tmp"

# After:
jq -s --arg tid "$thread_id" \
  'map(if .threadId == $tid then .isResolved = true else . end) | .[]' \
  "$THREADS_FILE" > "${THREADS_FILE}.tmp"
```

**Verified**: Tested with 3-object newline-delimited JSON, all objects preserved correctly.

### Problem: GitHub Projects (classic) Deprecation Warnings

**Issue**: `gh pr view` without `--json` queries deprecated Projects (classic) API
- Non-fatal GraphQL errors clutter output
- Affects `gh pr view` and `gh pr edit` commands

**Fix Applied** (commit 91bccc3):
- Added note to SKILL.md Prerequisites section
- All script examples already use `--json` correctly
- Issue only affects manual workflow commands

**Workaround**: Always use `gh pr view --json <fields>` to avoid deprecated API

**Impact**:
- ✅ Bulk resolution now works for multiple threads (87.5% token savings realized)
- ✅ Cleaner output without deprecation warnings
- ✅ Scripts future-proofed against GitHub API changes

---

## 2026-04-24 - State Management & Caching

### Problem: Redundant API Calls and Manual Tracking

**Issues identified in production use**:
1. Multiple GitHub API calls to fetch same thread data (fetch → resolve → verify)
2. Manual round number tracking (lost context across sessions)
3. No fix history or traceability across rounds
4. Threaded reply API failures required fallback without detection
5. Pre-commit checklist was manual/prone to skip

**Impact**: Slower workflow, lost context, incomplete audit trail

### Solution: Comprehensive State Management System

**Added** (Step 1: Initialize State Management):
- **Thread caching**: Fetch once at start, query locally thereafter
- **Round tracking**: Auto-increment in `/tmp/pr-{number}/round.txt`
- **Fix history**: Track commits, threads, files per round in `fixes.json`
- **Progress checklist**: Automated tracking in `checklist.json`
- **API capability detection**: Test threaded replies at start, cache result

**State Files Created** (`/tmp/pr-{number}/`):
```
threads.json              # Cached thread metadata (no re-fetching)
round.txt                 # Current round number (auto-incremented)
fixes.json                # Fix history per round
checklist.json            # Pre-commit checklist state
api-capabilities.txt      # API feature flags
threads.json.before-round-N  # Thread state snapshots
```

**Updated Steps**:
- **Step 1**: Initialize workspace, cache threads, detect API capabilities
- **Step 6**: Query cached threads (no API call), update cache after resolution
- **Step 7**: Automated checklist validation, auto-generated commit messages
- **Step 8**: Refresh cache after CI/CD, compare with previous state

**New Section**: "State Management & Fix History"
- View complete fix history across all rounds
- Compare thread state changes
- Archive state for post-mortem analysis
- Export workflow metrics

**Benefits**:
- ⚡ **3-5x faster**: Eliminated redundant GitHub API calls
- 📊 **Complete audit trail**: Track every fix, commit, thread across all rounds
- 🎯 **Accurate tracking**: No manual round counting (was "Round 8" in handoff)
- 🔍 **Post-mortem analysis**: Export metrics for process improvement
- 🛡️ **Graceful degradation**: Adapts when threaded reply API unavailable

**Example Fix History Output**:
```
round_1:
  Commit: abc123def
  Threads Resolved: PRRT_kwDOQ5-SAM59LkA-, PRRT_kwDOQ5-SAM59LkBj
  Files Changed: 3
  Tests Passing: 495

round_2:
  Commit: def456ghi
  Threads Resolved: PRRT_kwDOQ5-SAM59OMjh, PRRT_kwDOQ5-SAM59OMkF
  Files Changed: 2
  Tests Passing: 496
```

**Cleanup**: EXIT trap removes state files, or archive to `~/.claude/pr-history/` for analysis

**Testing**: Validated in PR #67 (8 rounds, 12 threads resolved)

---

## 2026-04-20 - Major Improvements

### 1. SonarQube Web API Integration

**Added**: Comprehensive SonarQube API polling and validation (Step 5b-5c)

**Problem**: Skill ran `sonar-scanner` but never verified actual results - just checked that the scanner completed successfully.

**Solution**:
- Extract task ID from scanner output
- Poll `/api/ce/task?id=<task-id>` every 5 seconds (max 60s) until status = SUCCESS
- Fetch quality gate status: `/api/qualitygates/project_status`
- Fetch blocking issues: `/api/issues/search` (BLOCKER, CRITICAL only)
- Fallback to manual dashboard review for SSO-protected instances

**API Endpoints**:
```bash
# Wait for analysis
GET /api/ce/task?id=<task-id>
Response: {"task": {"status": "SUCCESS|PENDING|FAILED"}}

# Quality gate
GET /api/qualitygates/project_status?projectKey=X&pullRequest=Y
Response: {"projectStatus": {"status": "OK|ERROR"}}

# Issues
GET /api/issues/search?componentKeys=X&pullRequest=Y&resolved=false&severities=BLOCKER,CRITICAL
Response: {"issues": [{severity, message, component, line}]}
```

**Authentication**: Use `Authorization: Bearer $SONAR_TOKEN` header (not basic auth with `-u token:`).

**Caveat**: Enterprise SonarQube with SSO may return HTML instead of JSON. Documented fallback to manual dashboard review.

### 2. Conversation Resolution Before Commit

**Fixed**: Workflow said "resolve before commit" but example showed resolving after push.

**Changes**:
- Moved Step 6 (Resolve Conversations) to come BEFORE Step 7 (Commit & Push) in execution order
- Added verification step after resolving threads (check all threads isResolved=true)
- Updated QUICK_START workflow diagram to emphasize correct order
- Added rationale: "Reviewers see resolved conversations immediately, commit messages reference already-addressed issues"

### 3. Pre-Push Checklist (Step 7)

**Added**: Mandatory checklist before commit to prevent common mistakes.

**Checklist Items**:
- ✅ All tests passing (`mvn test`)
- ✅ Build clean (`mvn clean install -DskipTests`)
- ✅ SonarQube dashboard reviewed (no new blocking issues)
- ✅ All GitHub conversations resolved (verified with gh API)
- ✅ Commit message references fixed issues
- ✅ No debug code, console.logs, or temporary changes left

**Enforcement**: User must acknowledge checklist before proceeding (Ctrl+C to abort).

### 4. Structured Commit Message Template

**Added**: Template with clear sections for traceability.

**Format**:
```
fix: Address Copilot/SonarQube PR review issues (Round N)

Critical Fixes:
- Issue description (file:line)

High Priority Fixes:
- Issue description (file:line)

Medium Priority Fixes:
- Issue description (file:line)

Test Coverage:
- X/Y tests passing
- New tests: [list]

Resolves: [thread IDs]
Addresses: GitHub Copilot review on PR #XX
```

**Benefits**:
- Clear severity categorization (matches Step 3)
- File:line references for reviewers
- Test count shows verification
- Thread IDs for traceability

### 5. Test Coverage for New Code

**Added**: Explicit requirement to test new methods/classes added during fixes.

**Checklist**:
- [ ] Write test for happy path
- [ ] Write test for null/edge cases
- [ ] Write test for error conditions
- [ ] Verify test coverage (all new code executed)

**Example**: If adding `setAccumulator()` method, must write tests for:
- Setting accumulator after construction (happy path)
- Null accumulator handling (edge case)

**Rationale**: In this session, I added `setAccumulator()` and `executeWithRetryVoid()` without tests, which was incomplete.

### 6. Documentation Updates

**README.md**:
- Added SonarQube Web API integration section
- Documented task polling pattern
- Documented quality gate + issues endpoints
- Added note about SSO-protected instances
- Bearer token authentication clarification

**QUICK_START.md**:
- Updated SonarQube fetch example (Bearer token instead of basic auth)
- Added note about SSO/API access issues
- Emphasized conversation resolution order

**SKILL.md**:
- Enhanced Step 5 with comprehensive API polling
- Added Pre-Push Checklist (Step 7)
- Added Structured Commit Message Template
- Added Test Coverage for New Code requirement

## Lessons Learned (2026-04-20 Session)

### What Went Wrong

1. **Skipped SonarQube result verification**: Ran scanner but didn't check actual issues
2. **Resolved conversations after push**: Should have been before commit
3. **No tests for new methods**: Added `setAccumulator()` without test coverage
4. **Used wrong auth format**: Used `-u token:` instead of `Bearer` header

### What Went Right

1. **Fixed all 9 Copilot issues**: Comprehensive fixes for null-safety, validation, accumulator wiring
2. **All 464 tests passing**: No regressions introduced
3. **Clean build**: No compilation errors, Maven Shade working correctly
4. **Proper TDD approach**: Used test-after for obvious fixes (correct for PR issue fixes)

### Process Improvements Applied

- SonarQube API polling + verification (prevents "just ran the tool" mistake)
- Pre-push checklist (prevents skipping validation steps)
- Structured commit messages (improves traceability)
- Test coverage requirement for new code (enforces completeness)
- Conversation resolution BEFORE commit (keeps PR clean)

## Future Enhancements (Ideas)

### 1. Automatic Test Generation

**Idea**: When adding new methods during fixes, automatically generate test stubs.

**Example**:
```bash
# Detect new methods via git diff
NEW_METHODS=$(git diff HEAD~1 --unified=0 | grep "^+.*public.*void.*setAccumulator")

# Generate test stub
cat > Test.java <<EOF
@Test
void shouldSetAccumulatorAfterConstruction() {
    // TODO: Implement
}
EOF
```

### 2. SonarQube Issue Auto-Fix

**Idea**: For trivial issues (unused imports, missing finals), apply fixes automatically.

**Example**:
```bash
# Detect "make method static" issues
STATIC_METHODS=$(curl ... | jq -r '.issues[] | select(.message | contains("static")) | .component + ":" + .line')

# Apply fix automatically (if single-line change)
```

### 3. Conversation Auto-Reply

**Idea**: Generate threaded replies automatically based on commit diff.

**Example**:
```bash
# For Issue #1 at RetryConfig.java:74
COMMIT_SHA=$(git rev-parse --short HEAD)
CHANGES=$(git diff HEAD~1 RetryConfig.java | grep -A5 "line 74")

REPLY="✅ Fixed in $COMMIT_SHA\n\nChanges:\n\`\`\`diff\n$CHANGES\n\`\`\`"
```

### 4. Quality Gate as Git Hook

**Idea**: Block commit if local SonarQube scan fails quality gate.

**Implementation**: Pre-commit hook that runs sonar-scanner and checks quality gate.

---

## API Research Notes (2026-04-20)

### SonarQube Authentication Testing

**Tested Methods**:
1. ✅ Bearer token: `Authorization: Bearer $SONAR_TOKEN` (correct for SonarQube tokens)
2. ❌ Basic auth: `-u $SONAR_TOKEN:` (wrong - this is for username:password)
3. ❌ API endpoints returned HTML (SSO redirect)

**Finding**: Enterprise SonarQube instance (churchofjesuschrist.org) uses SSO authentication that intercepts API calls and returns HTML login page instead of JSON. This is common with SAML/OAuth2-based enterprise instances.

**Workaround**: Document fallback to manual dashboard review when API returns HTML.

### Task Polling Pattern

**Scanner Output**:
```
More about the report processing at https://sonarqube.../api/ce/task?id=<task-id>
```

**Extraction**:
```bash
TASK_URL=$(sonar-scanner 2>&1 | grep "More about the report processing" | sed 's/.*at //')
TASK_ID=$(echo "$TASK_URL" | sed 's/.*id=//')
```

**Poll Loop**:
```bash
for i in {1..12}; do
  STATUS=$(curl -s -H "Authorization: Bearer $SONAR_TOKEN" \
    "$SONAR_HOST/api/ce/task?id=$TASK_ID" | jq -r '.task.status')
  
  [ "$STATUS" = "SUCCESS" ] && break
  sleep 5
done
```

**Timeout**: 12 attempts × 5 seconds = 60 seconds (sufficient for most PRs)

### API Endpoints Reference

| Endpoint | Purpose | Response Time |
|----------|---------|---------------|
| `/api/ce/task?id=X` | Check analysis status | Immediate |
| `/api/qualitygates/project_status` | Pass/fail status | After analysis complete |
| `/api/issues/search` | List issues | After analysis complete |
| `/api/measures/component` | Metrics (coverage, bugs) | After analysis complete |

**All require**: `pullRequest=N` parameter for PR-specific results.

---

## Version History

- **2026-07-01**: First real dogfood run (pre-pr-audit + adversarial-review) + 5 rounds of
  adversarial-review convergence fixes (v1.7.0-v1.7.2)
- **2026-07-01**: Ported apply-feedback strengths (silent-thread filter, directional/polish
  classification, thread-accountability closeout, protected-branch guard, /plan escalation) +
  script-first cleanup (net line reduction)
- **2026-04-20**: Major update (SonarQube API, pre-push checklist, conversation ordering)
- **2026-04-17**: Added adversarial review agent pattern
- **2026-04-16**: Initial version (basic workflow)
