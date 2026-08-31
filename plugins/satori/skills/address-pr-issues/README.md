# Address PR Issues

Comprehensive workflow to address code quality issues from GitHub Copilot and SonarQube on pull requests with proper test coverage.

**This file is an overview, not the procedure.** `SKILL.md` in this directory is the source of
truth for the actual step-by-step workflow — it's what gets loaded and followed when this skill
runs. Keeping a second full copy here caused real drift in the past (a stale xp-pair invocation
placeholder and a stale escalation message survived multiple SKILL.md revisions because nothing
forced this file to update alongside it). This file now covers only what it genuinely owns:
the rationale, the script quick-reference, and pointers to the other docs.

- **Quick start / one-command usage**: see `QUICK_START.md`
- **Full step-by-step procedure**: see `SKILL.md`
- **Version history**: see `CHANGELOG.md`

## Key Improvement

**Problem**: Reactive fixing leads to cascading bugs across 5+ rounds
- Round 1: Fix reported bug X
- Round 2: Copilot finds related bug Y
- Round 3: Copilot finds related bug Z
- Result: Multiple commits, long cycle times, incomplete fixes

**Solution**: Adversarial review agent challenges completeness BEFORE implementing
- **Step 2**: Assess if issues involve cascading edge cases
- **Step 3.5**: Conditionally delegate to `/adversarial-review` (one round) — parallel
  per-class agents sweep all known Copilot issue pattern classes, cascade-sweep within each
  class, then pause for human disposition before applying git-guardrailed fixes
- Forces comprehensive analysis and testing upfront
- **Result**: markedly fewer review rounds

**When to Use**:
- Privacy/security critical code (data leaks, filtering)
- Defensive programming (null checks, conservative cleanup)
- Cascading bug patterns (fixing X reveals Y reveals Z)
- Complex edge case logic with multiple conditions

**When to Skip**:
- Simple style fixes (formatting, comments)
- Obvious bugs with clear solutions
- Low complexity, no edge case risk

## ⚠️ CRITICAL: Use Automation Scripts First

**Token Efficiency**: the scripts keep PR state out of context rather than re-reading it each
round. No savings figure is quoted because none has been measured.

**ALWAYS use scripts for repetitive operations** - they are in the skill's `scripts/` directory:

| Operation | Script / lib function |
|-----------|----------------------|
| Initialize state, cache threads | `"$SKILL_SCRIPTS/init-pr-state.sh" <pr_number>` |
| View threads | `"$SKILL_SCRIPTS/fetch-pr-threads.sh" <pr_number> --unresolved-only` |
| Classify silent/already-resolved/keep buckets | `"$SKILL_SCRIPTS/classify-threads.sh" <pr_number> <pr_author>` |
| Resolve one thread (+ optional reply) | `"$SKILL_SCRIPTS/resolve-thread.sh" <pr_number> <thread_id> [message]` |
| Resolve threads in bulk | `"$SKILL_SCRIPTS/resolve-threads-bulk.sh" <pr_number> --threads '...'` |
| React to a comment (👍) | `react_to_comment()` in `lib/github-api.sh` |
| Check quality gate + blocking issues | `"$SKILL_SCRIPTS/check-sonar-quality-gate.sh" <pr_number>` |
| Poll Sonar analysis completion | `wait_for_analysis()` in `lib/sonar-api.sh` |
| Commit changes | `"$SKILL_SCRIPTS/commit-pr-fixes.sh" <pr_number> [directional_count]` |

**🚨 Hard rule**: If you are about to write `gh api graphql`, a `curl` to SonarQube, or a
resolve/reply/fetch/react mutation by hand, **STOP**. A wrapper script or `lib/` function in the
table above already does it. Read the function in `lib/github-api.sh` or `lib/sonar-api.sh`
instead of re-deriving the query. The only inline API calls permitted anywhere in this skill are
the documented one-offs called out explicitly where they appear (page-2 pagination fallback,
SonarQube won't-fix transition, `sonar-scanner` itself) — everything else routes through a script.

**Only use manual commands for**:
- The specific one-off operations named above (not covered by any script)
- Debugging script failures
- Understanding what scripts do internally (read the code)

**Why this matters**: inline commands re-read and re-emit PR state every round; the scripts cache
it once and return only what changed. That compounds over a long PR.

## Workflow at a Glance

For full detail on any step, read the matching heading in `SKILL.md` — this list is for
orientation only, not a substitute for it:

1. Fetch Issues — Copilot PR comments, PR description, SonarQube analysis
1.6. Silent-thread pre-filter — auto-handle purely-complimentary and already-resolved threads
2. Assess Complexity — determine if adversarial review is needed
2.5. Adversarial Review Gate (mandatory check)
3. Prioritize — categorize issues by severity, present questionable ones to the user
3.5. Adversarial Review (delegated) — when the Step 2.5 gate says yes
3.7. Pre-fix sweep — grep for the same pattern across all touched files
3.8. Show Decision Summary — process decisions presented before work starts
4. Plan & Execute — Direct implementation, xp-pair, or a delegated background Agent
4.5. Post-fix sweep — catch cascading issues the fixes themselves introduced
5. Validate — local sonar-scanner before committing
6. Resolve Conversations — mark fixed threads resolved, reconcile every disposition
7. Commit & Push — protected-branch check, then push
8. Monitor & Repeat — classify fixes as directional/polish, re-request Copilot review, escalate to a `Plan` subagent if the PR has outgrown reactive rounds

**This is an iterative process** — expect multiple rounds. See `SKILL.md`'s own "Workflow
Overview" and "IMPORTANT" notes for why, and its `## Tips and Best Practices` section for
lessons from real-world usage.
