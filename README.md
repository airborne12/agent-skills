# Agent Skills

A collection of Claude Code skills for integrating with internal development tools.

## Skills

| Skill | Description |
|-------|-------------|
| [jira](./jira/) | Interact with Jira Server via REST API v2 - view, search, comment, create, and transition issues |
| [teamcity](./teamcity/) | Query TeamCity CI/CD pipelines - build status, failure diagnosis, test results, and log retrieval |

## Installation

Copy the desired skill directory into your Claude Code skills folder:

```bash
cp -r jira ~/.claude/skills/
cp -r teamcity ~/.claude/skills/
```

## Configuration

Each skill requires a config file in your home directory:

| Skill | Config File | Required Fields |
|-------|-------------|-----------------|
| jira | `~/.jira.conf` | `JIRA_URL`, `JIRA_USER`, `JIRA_TOKEN` |
| teamcity | `~/.teamcity.conf` | `TEAMCITY_URL`, `TEAMCITY_TOKEN` |

Refer to each skill's README for detailed setup instructions.

## Structure

Each skill contains:

```
<skill>/
├── <skill>.sh   # Bash helper script wrapping REST API calls
├── SKILL.md     # Claude Code skill definition (trigger rules, usage reference)
└── README.md    # Documentation
```
