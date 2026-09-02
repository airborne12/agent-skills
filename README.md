# Agent Skills

A collection of Claude Code skills for integrating with internal development tools.

## Skills

| Skill | Description |
|-------|-------------|
| [jira](./jira/) | Interact with Jira Server via REST API v2 - view, search, comment, create, transition issues, and post templated bug-fix replies |
| [jira-watch](./jira-watch/) | Watch your Jira queue, verify AI triage comments, trace fix PRs across doris/internal branches and release tags, controlled write-back, Feishu digest |
| [teamcity](./teamcity/) | Query TeamCity CI/CD pipelines - build status, failure diagnosis, test results, log retrieval, PR pipeline triage rules |
| [pr-watch](./pr-watch/) | Watch a PR: classify CI failures, independently verify review comments, controlled reply/resolve/repair modes |
| [pick-pr](./pick-pr/) | Cherry-pick / backport a PR or commit to another branch or repo, including semantic ports after refactors |
| [create-doris-pr](./create-doris-pr/) | Create an Apache Doris PR following the repo's current template and title rules |
| [doris-tdd-pr-workflow](./doris-tdd-pr-workflow/) | Take a Doris defect or review comment through TDD gates to a mergeable PR with fresh evidence at every gate |
| [fix-pr-pipeline](./fix-pr-pipeline/) | Systematic fixes for Doris PR pipeline failures (compiler differences, UT crashes, formatting, submodules) |
| [gh-address-comments](./gh-address-comments/) | Read GitHub PR review threads with resolution state via GraphQL and act on requested changes |
| [doris-profile-reader](./doris-profile-reader/) | Interpret Apache Doris query profiles: bottleneck triage, counter semantics, join order and runtime filters |
| [deploy-doris](./deploy-doris/) | Deploy a local Doris cluster |
| [doris-wiki-knowledge-loop](./doris-wiki-knowledge-loop/) | Knowledge loop for Doris wiki notes |
| [ai-digest](./ai-digest/) | Daily AI coding assistant usage digest |

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
| jira-watch | `~/.jira-watch.conf` | see `jira-watch/jira-watch.conf.example` (repo paths, bot users, Feishu open_id) |
| teamcity | `~/.teamcity.conf` | `TEAMCITY_URL`, `TEAMCITY_TOKEN` |

Refer to each skill's README for detailed setup instructions.

All hostnames, IPs, repository names, branch/tag prefixes, customer identifiers and issue keys in this repo are
placeholders (`*.example.com`, `example-org/internal-core`, `internal-*`, `CIR-1000x`). Replace them with your own
environment's values in the config files; nothing here should be taken as a real endpoint.

## Structure

Each skill contains:

```
<skill>/
├── <skill>.sh   # Bash helper script wrapping REST API calls
├── SKILL.md     # Claude Code skill definition (trigger rules, usage reference)
└── README.md    # Documentation
```
