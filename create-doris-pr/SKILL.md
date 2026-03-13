---
name: create-pr
description: Create a pull request for the Apache Doris project following the official PR template. Use when user says "提PR", "create PR", "提交PR", "push and create PR", "创建PR", or wants to push changes and open a pull request.
---

# Create Doris PR

Create a pull request to the Apache Doris upstream repo (`apache/doris`) following the official PR template format.

## Prerequisites

Before creating the PR, gather all necessary information:

1. **Check current branch and remote tracking:**
   ```bash
   git branch --show-current
   git remote -v | grep jk
   git log --oneline <branch> --not origin/master
   ```
2. **Ensure changes are committed** — if not, ask the user to commit first.
3. **Ensure branch only contains relevant commits** — no unrelated commits mixed in.

## Push

Push the branch to the user's fork remote (`jk`) if not already pushed:

```bash
git push -u jk <branch-name>
```

## PR Title Convention

Follow Doris commit message convention for the PR title:

```
[type](scope) description
```

- **type**: `fix`, `feature`, `enhancement`, `refactor`, `test`, `docs`, `chore`
- **scope**: module or area, e.g. `build`, `storage`, `planner`, `inverted index`
- **description**: concise summary, under 70 characters total

## PR Body Template

Use EXACTLY this template structure. Fill in the relevant sections based on the changes. Use a HEREDOC to pass the body:

```bash
gh pr create --repo apache/doris --base master \
  --head airborne12:<branch-name> \
  --title "[type](scope) description" \
  --body "$(cat <<'EOF'
### What problem does this PR solve?

Issue Number: close #xxx

Related PR: #xxx

Problem Summary:
<describe the problem and solution concisely>

### Release note

None

### Check List (For Author)

- Test
    - [ ] Regression test
    - [ ] Unit Test
    - [ ] Manual test (add detailed scripts or steps below)
    - [ ] No need to test or manual test. Explain why:
        - [ ] This is a refactor/code format and no logic has been changed.
        - [ ] Previous test can cover this change.
        - [ ] No code files have been changed.
        - [ ] Other reason

- Behavior changed:
    - [ ] No.
    - [ ] Yes.

- Does this need documentation?
    - [ ] No.
    - [ ] Yes.

### Check List (For Reviewer who merge this PR)

- [ ] Confirm the release note
- [ ] Confirm test cases
- [ ] Confirm document
- [ ] Add branch pick label
EOF
)"
```

## Filling In The Template

- **Issue Number**: If user mentions an issue, use `close #xxx`. If no issue, remove the line or write `N/A`.
- **Related PR**: If user mentions related PRs, list them. Otherwise remove or write `N/A`.
- **Problem Summary**: Write a clear description of what the problem is and how this PR solves it. Include technical context.
- **Release note**: Default to `None` unless the change is user-facing.
- **Test checklist**: Check the appropriate boxes based on what tests exist:
  - Check `Manual test` if user verified manually (e.g. build succeeded on macOS).
  - Check `No need to test` sub-items if it's a refactor, build fix, etc.
  - Add specific test details when `Manual test` is checked.
- **Behavior changed**: Default to `No` unless there's a behavior change.
- **Documentation**: Default to `No` unless docs are needed.

## After Creation

Return the PR URL to the user.

## Important Notes

- Always use `--repo apache/doris` to target the upstream repo.
- Always use `--head airborne12:<branch>` to specify the fork.
- Always use `--base master` unless user specifies otherwise.
- Do NOT mix commits from different features in one PR. If detected, warn the user.
- Verify the branch has been pushed to `jk` remote before creating the PR.
