---
name: jira
description: Use when the user asks to view, search, comment on, create, or transition Jira issues. Also use when user mentions a Jira issue key like CIR-10006 or asks about task status.
---

# Jira Interaction

## Overview

Interact with the internal Jira Server (8.20.4) via REST API v2. All requests go through VPN interface `tun0`. Auth uses **Bearer token** (Personal Access Token).

## Configuration

Credentials in `~/.jira.conf`:

```bash
JIRA_URL="http://jira.example.com:8090"
JIRA_USER="your_username"
JIRA_TOKEN='your_pat_token'   # MUST use single quotes (token has +, #, etc.)
JIRA_INTERFACE="tun0"
```

## Helper Script

Use `~/.claude/skills/jira/jira.sh` for all operations:

```bash
bash ~/.claude/skills/jira/jira.sh view CIR-10005
bash ~/.claude/skills/jira/jira.sh search 'project = CIR AND assignee = alice ORDER BY updated DESC'
bash ~/.claude/skills/jira/jira.sh comment CIR-10005 'Comment text here'
bash ~/.claude/skills/jira/jira.sh fix-comment DORIS-20002 \
    'https://github.com/apache/doris/pull/62699' \
    @/tmp/trigger.md @/tmp/cause.md @/tmp/solution.md
bash ~/.claude/skills/jira/jira.sh create CIR Task 'Fix login bug'
bash ~/.claude/skills/jira/jira.sh create CIR Bug 'Login fails' 'Steps to reproduce...'
bash ~/.claude/skills/jira/jira.sh create CIR Task 'Review PR' '' zhangsan
bash ~/.claude/skills/jira/jira.sh transitions CIR-10005
bash ~/.claude/skills/jira/jira.sh transition CIR-10005 21          # Move to 处理中
bash ~/.claude/skills/jira/jira.sh transition CIR-10005 41 'Done!'  # Complete with comment
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `view <KEY>` | Show issue details (summary, status, assignee, description, comments) |
| `search '<JQL>'` | Search issues with JQL query (max 20 results) |
| `comment <KEY> '<body>'` | Add a comment to an issue |
| `fix-comment <KEY> <PR_URL> <TRIGGER> <ROOT_CAUSE> <SOLUTION>` | Post a bug-fix reply rendered with the 3-section template (see below). Any of TRIGGER/ROOT_CAUSE/SOLUTION may be `@path/to/file`. |
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
  "$JIRA_URL/rest/api/2/issue/CIR-10005?fields=summary,status"
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

`http://jira.example.com:8090/browse/{ISSUE_KEY}`

## Bug-fix reply template

After fixing a defect tracked by a Jira issue, post a structured reply with
`fix-comment`. The template (see `templates/fix-reply.md`) has three sections,
plus a PR link at the bottom:

1. **问题触发条件** — minimal repro / when the bug fires
2. **定位根因** — where in the code the defect lives and why
3. **解决方案** — what changed and why (and the PR link is appended automatically)

Each input is rendered into Jira wiki markup. Inside any section you can use
`{{ident}}` for inline code and `{code:cpp} ... {code}` for code blocks.

```bash
# Inline literals (newlines inside the quoted string are preserved).
bash ~/.claude/skills/jira/jira.sh fix-comment DORIS-20002 \
    'https://github.com/apache/doris/pull/62699' \
    'When ... ' \
    'Function {{foo}} ignores ...' \
    'Wrap result in {{ColumnConst}} ...'

# Or read each section from a file (recommended for multi-line content):
bash ~/.claude/skills/jira/jira.sh fix-comment DORIS-20002 \
    'https://github.com/apache/doris/pull/62699' \
    @/tmp/trigger.md @/tmp/cause.md @/tmp/solution.md
```

Trigger this command automatically once a fix PR is opened/merged and the
related Jira key is known (e.g. mentioned in the PR description as
`Related Jira: DORIS-XXXXX`).

## VPN routing

The Jira server (`jira.example.com`) is only reachable through `tun0`. If your
default route doesn't already cover it, add a host route once per session:

```bash
sudo ip route add jira.example.com dev tun0
```

The script also sets `--noproxy '*'` and unsets every proxy env var
(`HTTP(S)_PROXY`, `ALL_PROXY`) so SOCKS/HTTP proxies don't intercept the
connection.
