# Jira Skill

A Claude Code skill for interacting with Jira Server via REST API v2.

## Features

- **View issues** - Display issue details including summary, status, assignee, description, and comments
- **Search issues** - Query issues using JQL (Jira Query Language)
- **Add comments** - Post comments to existing issues
- **Create issues** - Create new issues with project, type, summary, description, and assignee
- **Manage transitions** - List available status transitions and change issue status

## Setup

1. Create `~/.jira.conf` with your credentials:

```bash
JIRA_URL="http://your-jira-server:8090"
JIRA_USER="your_username"
JIRA_TOKEN='your_personal_access_token'   # Use single quotes
```

2. Ensure the Jira server is reachable (VPN may be required).

## Usage

```bash
# View an issue
bash jira.sh view CIR-19418

# Search issues
bash jira.sh search 'project = CIR AND assignee = jiangkai ORDER BY updated DESC'

# Add a comment
bash jira.sh comment CIR-19418 'Comment text here'

# Create an issue
bash jira.sh create CIR Task 'Fix login bug'
bash jira.sh create CIR Bug 'Login fails' 'Steps to reproduce...'

# List available transitions
bash jira.sh transitions CIR-19418

# Transition an issue
bash jira.sh transition CIR-19418 21
```

## Files

| File | Description |
|------|-------------|
| `jira.sh` | Bash helper script wrapping Jira REST API calls |
| `SKILL.md` | Claude Code skill definition with trigger rules and full reference |

## Authentication

Uses **Bearer token** (Personal Access Token) authentication. Basic Auth is not supported.

## Dependencies

- `bash`, `curl`, `python3`
