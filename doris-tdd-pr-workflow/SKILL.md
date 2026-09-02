---
name: doris-tdd-pr-workflow
description: Use when an Apache Doris bug or review comment must be implemented and taken through an independent pull request, especially requests mentioning TDD, 提PR, jk remote, run buildall, clang-format 16, TeamCity, or post-PR monitoring.
---

# Doris TDD PR Workflow

## Overview

Drive one Doris defect from evidence to one independently mergeable PR. Advance only when the current gate has fresh evidence; a plausible patch, reviewer authority, intermediate CI status, or an earlier SHA is not evidence for the next gate.

**One task → one latest-master worktree/branch → one TDD history → one PR.** Independent tasks never share or stack branches.

## Required sub-skills

- **REQUIRED:** Use `superpowers:using-git-worktrees` for isolation.
- **REQUIRED:** Use `superpowers:test-driven-development` for every production behavior change.
- **REQUIRED:** Use `superpowers:verification-before-completion` before commit, push, PR, or readiness claims.
- **REQUIRED:** Use `create-pr` when publishing the PR.
- **REQUIRED:** Use `teamcity` for post-PR CI diagnosis.
- **REQUIRED:** Use `github:gh-address-comments` when review-thread state matters.

Repository `AGENTS.md` overrides generic examples. Read it before acting.

## Evidence ledger

Create and maintain this record in the working plan or task notes; never add it to the Doris commit:

```text
Task / observable bug:
Comment description:
Independent validity decision: pending | confirmed | rejected
Real reproducer and expected result:
Base SHA / branch / worktree:
RED command and expected failure:
GREEN command and result:
Focused and broader tests:
clang-format 16 / check-format / clang-tidy:
Build:
Self-review findings:
Commit / pushed SHA / PR:
Current PR head SHA:
Initial checks / buildall trigger:
Latest finished CI per configuration:
Unresolved review threads:
```

Do not record “pass” without command, SHA, and terminal result.

## Gate 1: isolate from current upstream master

1. Resolve the Apache upstream remote; do not assume local `master` is current.
2. Fetch upstream `master` and pin its SHA.
3. Preserve every unrelated dirty change. Create one worktree and branch directly from the pinned SHA for this task.
4. In a Doris worktree, follow `AGENTS.md`: check `.worktree_initialized`, run `hooks/setup_worktree.sh` only when required, then verify dependencies and submodules.
5. For multiple independent tasks, repeat from upstream `master`; do not combine or base one task on another.

## Gate 2: establish the defect before code

For a review comment, process it in this order:

1. State exactly what the comment claims.
2. Understand the relevant architecture and behavior contract.
3. Construct the smallest real case and calculate the expected result independently. Consult the reference implementation when relevant.
4. Run the case. Decide `confirmed`, `rejected`, or `pending` from evidence—not reviewer status.
5. Record the resulting implementation task. If unconfirmed, make no speculative production change.

If production code already exists without an observed RED, remove only that task's production changes, preserve unrelated work, and restart test-first.

## Gate 3: vertical RED-GREEN-REFACTOR

For one observable behavior at a time:

1. Add the smallest BE unit, FE unit, or regression test using the real public path and an established nearby fixture.
2. Run it with the repository script (`run-be-ut.sh`, `run-fe-ut.sh`, or `run-regression-test.sh`). Verify it fails for the predicted bug reason—not compilation, fixture, or environment failure. Save the command and failure.
3. Make the minimal production change. Avoid speculative defensive branches; follow nearby Doris error, ownership, locking, and assertion patterns.
4. Re-run the exact test, then its owning suite. Refactor only while green and rerun after every refactor.
5. Generate regression `.out` only through the regression runner and keep it in the repository's established data location.

## Gate 4: verify and self-review

Use the current repository scripts, not guessed tool invocations:

```bash
build-support/clang-format.sh
build-support/check-format.sh
./build.sh --be        # select --fe/--cloud as the changed module requires
build-support/run-clang-tidy.sh   # modified C++ after build/compile_commands.json
git diff --check
```

Run the focused tests again after formatting and the appropriate broader suite/build. Keep ASAN unless performance testing was explicitly requested.

Review the full diff for root-cause correctness, error/lifetime behavior, concurrency and performance, storage/RPC/SQL compatibility, upgrade impact, deterministic coverage, and task-only scope. Any finding returns to RED-GREEN.

## Gate 5: commit, push, and create the PR

1. Re-fetch upstream. If the pinned base moved, rebase this branch independently and repeat affected verification.
2. Stage explicit task paths; exclude worktree markers, configuration, ports, logs, output, and unrelated edits.
3. Use the `AGENTS.md` Doris commit format and claim only tests actually run.
4. Push the branch normally to remote `jk`; do not force-push an unknown remote ref.
5. Read the current `.github/PULL_REQUEST_TEMPLATE.md`. Create an `apache/doris` PR against `master`, deriving the fork owner from `jk` rather than hardcoding it.
6. Include reproduction, root cause, before/after behavior, minimal fix, release/compatibility impact, and honest test evidence. Verify PR base, head SHA, commits, and changed files after creation.

## Gate 6: initial checks and `run buildall`

Record the PR head SHA. Treat queued/running checks—even `SUCCESS Step 1/2`—as pending.

Post the exact comment `run buildall` once only when the current SHA is stable, automatic title/license/format checks and any initial compilation checks are terminal-successful, no known code failure remains, and no buildall already covers that SHA. Verify that the trigger was accepted for that SHA.

Any new push invalidates previous readiness evidence and restarts this gate.

## Gate 7: monitor CI and review comments

For each TeamCity configuration, analyze only its newest `state:finished` build. Report queued/running builds separately. Compare the build revision with the current PR SHA before diagnosing.

- Current-SHA failure: inspect problems, failed tests, logs, and causal link. Reproduce locally when practical.
- Old SHA: stale, not evidence against the current head.
- Network, agent, missing artifact, cluster collapse, or cross-PR identical failure: infrastructure only when logs support that conclusion.
- Uncertain causality: keep it unresolved; do not label it unrelated for convenience.

A confirmed code failure or actionable review comment starts a new real-case RED-GREEN cycle on the same task branch. Fetch unresolved review threads repeatedly; for each, update the ledger with description, reproducer, validity decision, and task. Do not blindly follow comments. Reply or resolve threads only when the user authorized those GitHub writes; `run buildall` is the workflow's explicit exception.

## Ready gate

Call the PR ready only when one unchanged head SHA has fresh local verification, all required checks are terminal-successful, buildall ran for that SHA, every latest finished TeamCity configuration is acceptable, no actionable review thread remains, the PR contains only this task, and the evidence ledger is complete.

## Red flags

- “The fix is obvious; add tests afterward.”
- “Combine independent tasks to save CI time.”
- “Generic clang-format is close enough.”
- “Running SUCCESS means passed.”
- “A historical red build blocks the new SHA.”
- “The reviewer must be right.”
- “One green rerun proves the failure unrelated.”

Each red flag means stop at the current gate and restore evidence before continuing.
