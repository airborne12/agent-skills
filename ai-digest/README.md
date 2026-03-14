# AI Digest Skill

A Claude Code skill for collecting and analyzing daily AI coding assistant usage logs.

## Features

- **Multi-source collection** — Claude Code, Codex, Antigravity, OpenCode, Gemini CLI
- **Activity timeline** — Structured table of daily AI sessions with timestamps, projects, and message counts
- **LLM analysis** — Generate structured daily work summaries via OpenAI/Anthropic-compatible APIs

## Setup

1. Clone and install the CLI tool:

```bash
git clone https://github.com/jackwener/AI-digest.git ~/.local/share/ai-digest
cd ~/.local/share/ai-digest && uv sync
```

2. (Optional) Configure LLM analysis:

```bash
cp ~/.local/share/ai-digest/config.example.yaml ~/.local/share/ai-digest/config.yaml
# Edit config.yaml with your API key
```

## Usage

The skill is triggered when users ask about their daily AI usage, work digest, or session history.

- `digest collect` — Show today's AI session activity table
- `digest collect --date YYYY-MM-DD` — Show activity for a specific date
- `digest analyze --date YYYY-MM-DD` — Generate LLM-powered daily summary

## Upstream

- Repository: https://github.com/jackwener/AI-digest
- License: MIT
