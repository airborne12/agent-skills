# TeamCity Skill

A Claude Code skill for querying TeamCity CI/CD pipelines via REST API.

## Features

- **List projects & configs** - Browse TeamCity projects and build configurations
- **Check build status** - Get latest build status for any config/branch combination
- **Diagnose failures** - One-command full diagnosis: build details + problems + failed tests + log tail
- **View test results** - List test results with optional status filtering
- **Download logs** - Full build log or last N lines
- **Monitor pipeline** - Check queued and running builds
- **Branch builds** - Find builds across all configs for a specific branch

## Setup

1. Create `~/.teamcity.conf` with your credentials:

```bash
TEAMCITY_URL="http://your-teamcity-server:8111"
TEAMCITY_TOKEN='your_token_here'
# TEAMCITY_INTERFACE="tun0"    # Optional: VPN interface
```

2. For multiple TeamCity instances, use `TEAMCITY_CONF` env var:

```bash
TEAMCITY_CONF=~/.teamcity-staging.conf bash teamcity.sh status MyProject_Build main
```

## Usage

```bash
# List all projects
bash teamcity.sh projects

# List build configurations
bash teamcity.sh configs

# Check latest build status for a branch
bash teamcity.sh status MyProject_Build feature/my-branch

# Full failure diagnosis
bash teamcity.sh diagnose <build_id>

# View failed tests
bash teamcity.sh tests <build_id> FAILURE

# Get last 300 lines of build log
bash teamcity.sh log-tail <build_id> 300

# Find all builds for a branch
bash teamcity.sh branch-builds feature/my-branch
```

## Files

| File | Description |
|------|-------------|
| `teamcity.sh` | Bash helper script wrapping TeamCity REST API calls |
| `SKILL.md` | Claude Code skill definition with trigger rules and full reference |

## Authentication

Uses **Bearer token** authentication via TeamCity access tokens.

## Dependencies

- `bash`, `curl`, `jq`
