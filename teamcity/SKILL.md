---
name: teamcity
description: Use when the user asks about CI/CD pipeline status, build failures, build logs, or mentions a TeamCity build. Also use when checking if a branch or PR passed CI, diagnosing build failures, or retrieving build problems and test results.
---

# TeamCity Pipeline Integration

## Overview

Query TeamCity builds via REST API. Check build status by branch/PR, diagnose failures with build problems + failed tests + log tail.

## Configuration

Credentials in `~/.teamcity.conf`:

```bash
TEAMCITY_URL="http://43.132.222.7:8111"
TEAMCITY_TOKEN='your_token_here'
# TEAMCITY_INTERFACE="tun0"    # Optional: VPN interface
```

For multiple TeamCity instances, set `TEAMCITY_CONF` env var to point to a different config:

```bash
TEAMCITY_CONF=~/.teamcity-staging.conf bash ~/.claude/skills/teamcity/teamcity.sh status MyProject_Build feature/login
```

## Helper Script

Use `~/.claude/skills/teamcity/teamcity.sh` for all operations:

```bash
bash ~/.claude/skills/teamcity/teamcity.sh <command> [args...]
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `projects` | List all projects |
| `configs [project_id]` | List build configurations |
| `builds <config_id> [branch]` | Recent builds for a config, optionally by branch |
| `build <build_id>` | Full build details (JSON) |
| `status <config_id> [branch]` | Latest finished build status |
| `problems <build_id>` | Build problems (failure reasons) |
| `tests <build_id> [FAILURE]` | Test results, filter by status |
| `log <build_id>` | Full build log |
| `log-tail <build_id> [lines]` | Last N lines of log (default 200) |
| `diagnose <build_id>` | Full diagnosis: details + problems + failed tests + log tail |
| `branch-builds <branch> [count]` | Builds across ALL configs for a branch |
| `queue [config_id]` | Queued builds |
| `running [config_id]` | Running builds |
| `web <build_id>` | Print web URL for build |

## Typical Workflows

### Check branch CI status

```bash
# Find the build config ID first
bash ~/.claude/skills/teamcity/teamcity.sh configs

# Check latest status for a branch
bash ~/.claude/skills/teamcity/teamcity.sh status MyProject_Build feature/my-branch

# Or find all builds for a branch across configs
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds feature/my-branch
```

### Diagnose a failed build

```bash
# One-command full diagnosis
bash ~/.claude/skills/teamcity/teamcity.sh diagnose <build_id>

# Or step by step:
bash ~/.claude/skills/teamcity/teamcity.sh problems <build_id>
bash ~/.claude/skills/teamcity/teamcity.sh tests <build_id> FAILURE
bash ~/.claude/skills/teamcity/teamcity.sh log-tail <build_id> 300
```

### Check PR pipeline (branch-based)

TeamCity tracks PRs via branch names. For GitHub PRs, the branch name is typically `refs/pull/<number>/merge` or the source branch name:

```bash
# Try source branch name first
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds feature/add-auth

# Or try PR ref
bash ~/.claude/skills/teamcity/teamcity.sh branch-builds "refs/pull/123/merge"
```

## REST API Reference (manual curl)

```bash
source ~/.teamcity.conf
curl -s -H "Authorization: Bearer $TEAMCITY_TOKEN" -H "Accept: application/json" \
  "${TEAMCITY_URL}/app/rest/builds?locator=buildType:(id:CONFIG_ID),branch:(name:BRANCH),count:5,defaultFilter:false&fields=build(id,number,status,branchName,statusText,webUrl)"
```

Key endpoints:

| Operation | Endpoint |
|-----------|----------|
| List builds | `/app/rest/builds?locator=...` |
| Build details | `/app/rest/builds/id:<id>` |
| Build problems | `/app/rest/problemOccurrences?locator=build:(id:<id>)` |
| Test results | `/app/rest/testOccurrences?locator=build:(id:<id>)` |
| Build log | `/downloadBuildLog.html?buildId=<id>` |
| Build configs | `/app/rest/buildTypes` |
| Projects | `/app/rest/projects` |

### Build Locator Dimensions

| Dimension | Example | Purpose |
|-----------|---------|---------|
| `buildType` | `buildType:(id:MyProject_Build)` | Filter by config |
| `branch` | `branch:(name:main)` | Filter by branch |
| `status` | `status:FAILURE` | SUCCESS, FAILURE, UNKNOWN |
| `state` | `state:finished` | queued, running, finished, any |
| `count` | `count:10` | Limit results |
| `defaultFilter` | `defaultFilter:false` | Include non-default branches |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Only seeing default branch builds | Add `defaultFilter:false` to locator |
| Branch not found | Try exact branch name from VCS, including `refs/...` prefix |
| 401 Unauthorized | Check token in `~/.teamcity.conf`, ensure single quotes around token |
| Empty log output | Use `/downloadBuildLog.html` not `/app/rest/` for logs |
| Can't find build config ID | Run `configs` command first to list all IDs |
