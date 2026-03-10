---
name: jira
description: Use when the user asks to view, search, comment on, create, or transition Jira issues. Also use when user mentions a Jira issue key like CIR-12345 or asks about task status.
---

# Jira Interaction

## Overview

Interact with SelectDB's Jira Server (8.20.4) via REST API v2. All requests go through VPN interface `tun0`. Auth uses **Bearer token** (Personal Access Token).

## Configuration

Credentials in `~/.jira.conf`:

```bash
JIRA_URL="http://39.106.86.136:8090"
JIRA_USER="jiangkai"
JIRA_TOKEN='your_pat_token'   # MUST use single quotes (token has +, #, etc.)
JIRA_INTERFACE="tun0"
```

## Helper Script

Use `~/.claude/skills/jira/jira.sh` for all operations:

```bash
bash ~/.claude/skills/jira/jira.sh view CIR-19418
bash ~/.claude/skills/jira/jira.sh search 'project = CIR AND assignee = jiangkai ORDER BY updated DESC'
bash ~/.claude/skills/jira/jira.sh comment CIR-19418 'Comment text here'
bash ~/.claude/skills/jira/jira.sh create CIR Task 'Fix login bug'
bash ~/.claude/skills/jira/jira.sh create CIR Bug 'Login fails' 'Steps to reproduce...'
bash ~/.claude/skills/jira/jira.sh create CIR Task 'Review PR' '' zhangsan
bash ~/.claude/skills/jira/jira.sh transitions CIR-19418
bash ~/.claude/skills/jira/jira.sh transition CIR-19418 21          # Move to 处理中
bash ~/.claude/skills/jira/jira.sh transition CIR-19418 41 'Done!'  # Complete with comment
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `view <KEY>` | Show issue details (summary, status, assignee, description, comments) |
| `search '<JQL>'` | Search issues with JQL query (max 20 results) |
| `comment <KEY> '<body>'` | Add a comment to an issue |
| `create <PROJ> <TYPE> <SUMMARY> [DESC] [ASSIGNEE]` | Create a new issue (assignee defaults to `$JIRA_USER`) |
| `transitions <KEY>` | List available status transitions and their IDs |
| `transition <KEY> <ID> [comment]` | Change issue status (optionally with comment) |

## Manual curl (if script unavailable)

**IMPORTANT:** Must use Bearer auth, NOT Basic Auth. Must use `--interface tun0`.

```bash
source ~/.jira.conf
unset HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
curl -s --interface "$JIRA_INTERFACE" \
  -H "Authorization: Bearer $JIRA_TOKEN" \
  "$JIRA_URL/rest/api/2/issue/CIR-19418?fields=summary,status"
```

## REST API Endpoints

| Operation | Method | Endpoint |
|-----------|--------|----------|
| View issue | GET | `/rest/api/2/issue/{key}` |
| Search (JQL) | GET | `/rest/api/2/search?jql=...` |
| Add comment | POST | `/rest/api/2/issue/{key}/comment` |
| Create issue | POST | `/rest/api/2/issue` |
| Get transitions | GET | `/rest/api/2/issue/{key}/transitions` |
| Do transition | POST | `/rest/api/2/issue/{key}/transitions` |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `-u user:token` (Basic Auth) | Use `-H "Authorization: Bearer $JIRA_TOKEN"` |
| Token in double quotes in config | Use single quotes: `JIRA_TOKEN='...'` |
| Forgot `--interface tun0` | Required — server only reachable via VPN |
| Proxy env vars set | `unset HTTP_PROXY http_proxy HTTPS_PROXY https_proxy` |
| `source ~/.jira.conf` fails in zsh | Use `bash jira.sh` (script runs in bash) |

## Browse URL

`http://39.106.86.136:8090/browse/{ISSUE_KEY}`
