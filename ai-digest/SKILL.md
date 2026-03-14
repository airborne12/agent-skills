---
name: ai-digest
description: Collect and analyze daily AI coding assistant usage (Claude Code, Codex, Antigravity, OpenCode, Gemini CLI). Use when the user asks about their daily AI usage summary, work digest, or wants to review what they did with AI tools today.
---

# AI Digest — Daily AI Usage Summary

## Overview

Collects local logs from AI coding assistants and generates structured daily work summaries. Supports Claude Code, Codex, Antigravity, OpenCode, and Gemini CLI.

## Installation Path

- Repository: `~/.local/share/ai-digest/`
- Virtual env: `~/.local/share/ai-digest/.venv/`
- CLI binary: `~/.local/share/ai-digest/.venv/bin/digest`

## Configuration

Config file: `~/.local/share/ai-digest/config.yaml`

```yaml
ai:
  api_key: "YOUR_API_KEY"
  model: "claude-3-7-sonnet-latest"
  base_url: null  # optional
  provider: "anthropic"  # openai | anthropic
```

If no `config.yaml`, set `ANTHROPIC_API_KEY` env var and it defaults to anthropic provider.

## Commands

### Collect sessions (display table)

```bash
# Today
~/.local/share/ai-digest/.venv/bin/digest collect

# Specific date
~/.local/share/ai-digest/.venv/bin/digest collect --date 2026-03-14
```

### Analyze with LLM (generate report)

```bash
# Requires config.yaml or ANTHROPIC_API_KEY
~/.local/share/ai-digest/.venv/bin/digest analyze --date 2026-03-14
```

## Usage Instructions

When the user asks to see their AI usage or daily digest:

1. Run `collect` first to show the activity table
2. If the user wants an LLM-generated summary, run `analyze`
3. Check if `~/.local/share/ai-digest/config.yaml` exists; if not, prompt user to configure it before running `analyze`

## Data Sources

| Tool | Log Path | Format |
|------|----------|--------|
| Claude Code | `~/.claude/projects/` | JSONL |
| Codex | `~/.codex/sessions/` | JSONL |
| Antigravity | `~/.gemini/antigravity/brain/` | Artifacts + JSON |
| OpenCode | `~/.local/share/opencode/opencode.db` | SQLite / JSON |
| Gemini CLI | `~/.gemini/history/` | Directory mtime |

## Updating

```bash
cd ~/.local/share/ai-digest && git pull && uv sync
```
