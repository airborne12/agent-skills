# Agent Skills

A collection of skills for Claude Code and Codex, covering development tools and technical workflows.

## Skills

| Skill | Description |
|-------|-------------|
| [asd-ste100-explain](./asd-ste100-explain/) | Explain PRs, bugs, and code behavior with source evidence and ASD-STE100-inspired Chinese or English; includes a worked example and a local wording checker |
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
mkdir -p ~/.claude/skills
cp -r jira ~/.claude/skills/
cp -r teamcity ~/.claude/skills/
cp -r asd-ste100-explain ~/.claude/skills/
```

For Codex, copy the same directory into its user skills folder:

```bash
mkdir -p ~/.codex/skills
cp -r asd-ste100-explain ~/.codex/skills/
```

Invoke the explanation skill with `/asd-ste100-explain <PR URL or question>` in Claude Code,
or `$asd-ste100-explain <PR URL or question>` in Codex. It can also activate from a matching
natural-language request. The wording checker requires Python 3.8 or later; the skill requires
no service configuration. On one machine, Claude Code can use a directory symlink to the
Codex installation so both tools read the same files.

## Configuration

Some service integrations require a config file in your home directory:

| Skill | Config File | Required Fields |
|-------|-------------|-----------------|
| jira | `~/.jira.conf` | `JIRA_URL`, `JIRA_USER`, `JIRA_TOKEN` |
| jira-watch | `~/.jira-watch.conf` | see `jira-watch/jira-watch.conf.example` (repo paths, bot users, Feishu open_id) |
| teamcity | `~/.teamcity.conf` | `TEAMCITY_URL`, `TEAMCITY_TOKEN` |

Refer to each skill's README for detailed setup instructions.

Service configuration examples use placeholders such as `*.example.com`, `example-org/internal-core`,
`internal-*`, and `CIR-1000x`. Replace them with your environment's values in the config files.
Public repository URLs and source citations identify the actual referenced projects.

## Structure

Each skill contains a `SKILL.md` entrypoint. Supporting files depend on the skill:

```
<skill>/
├── SKILL.md     # Skill instructions and trigger description
├── scripts/    # Optional executable helpers
├── references/ # Optional supporting documentation and examples
├── agents/     # Optional host-specific metadata
├── <skill>.sh  # Optional Bash helper for service integrations
└── README.md   # Optional setup documentation
```
