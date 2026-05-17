---
name: doris-wiki-knowledge-loop
description: Use when working on Apache Doris source (apache/doris PRs, DORIS-XXXX issues, files under be/ fe/ cloud/, branches like master/branch-4.x) — including re-reviews, verifications of prior analyses, and tasks where the user has cited a specific file path or line. Triggers especially when you feel ready to grep source directly.
---

# Doris Wiki Knowledge Loop

Curated wiki lives at `$OBSIDIAN_VAULT_PATH/projects/apache-doris/`. Ground first, write back after.

## Step 0 — Resolve the wiki path

Walk up CWD for `.env` with `OBSIDIAN_VAULT_PATH`. Fallback: `~/.obsidian-wiki/config`. Set `WIKI=$OBSIDIAN_VAULT_PATH/projects/apache-doris`. If no config, tell the operator to run `wiki-setup` — don't guess. If `$WIKI` missing, record `phase1=gap-noted` and proceed.

## Phase 1 — Ground before reading source

Before any `Read` / `Grep` / `Bash ls` on Doris source:

1. `cat $WIKI/apache-doris.md` (the index).
2. **REQUIRED SUB-SKILL:** invoke `wiki-query` with the subsystem name (e.g. "inverted index NULL bitmap", "exchange sink pipelineX").
3. Read returned pages end-to-end. Their cited `file:line` are your real entry points.

If wiki returns nothing, record `phase1=none-relevant`.

## Phase 2 — Write back after the task

Ask: *did I learn something the wiki doesn't yet encode?*

Triggers (any one):

- Traced a flow or invariant the wiki doesn't map.
- Caught a refactor-driven stale path (e.g. `be/src/olap/...` → `be/src/storage/...` after #61107).
- Disproved a confidently-stated hypothesis with source evidence.
- Confirmed a subtle contract worth preserving.

If a trigger fires:

1. Stage `$WIKI/_raw/folio-<task-id>-<slug>.md` with frontmatter `source: folio-task`, `created: <ISO>`. Body: declarative knowledge with `file:line` citations and `[[wikilinks]]`.
2. **REQUIRED SUB-SKILL:** invoke `wiki-ingest` on the staged file.
3. Sandbox refusal? Stage at `$CODEX_HOME/memories/wiki-stage/` or `.claude/memory/wiki-stage/`; declare the path in your reply.

Never write to `concepts/` / `references/` / `synthesis/` — those are operator-reviewed.

## Mandatory protocol declaration

Every reply on a Doris task MUST end with:

```
wiki-loop: phase1=<consulted-pages|none-relevant|gap-noted>; phase2=<staged-path|no-trigger|sandbox-fallback:<path>>
```

## Rationalization Table

Each row is your cue to **stop and run Phase 1**.

| Tempting behavior | Reality |
|---|---|
| `ls` the user's cited path and start there | Stale or hallucinated in 3/3 baselines. Wiki cites current locations. |
| "I can verify faster by reading source directly" | Baselines took 8 / 22 / 7 tool calls. `wiki-query` would be 2. |
| "Re-review, prior agent already worked the context" | Prior agents read source cold too. Their context = one cold read away from yours. |
| Finish with new findings, forget Phase 2 | 3/3 baselines produced sink-worthy findings; 0/3 recorded them. |
| Skip `wiki-loop:` because "this one didn't need it" | Omitting = skipped. The line is mandatory. |
| After staging, write a "clean version" directly to `concepts/` | `wiki-ingest` + operator review owns promotion. You only stage in `_raw/`. |

## Red Flags — STOP

- About to `Read` / `Grep` / `Bash ls` Doris source without first reading a wiki page.
- Building a conclusion from one cited `file:line` without zooming out to the subsystem.
- Finished verification, about to reply, no Phase 2 trigger check done.
- About to omit the `wiki-loop:` declaration.
- About to `Write` a file under `concepts/` / `references/` / `synthesis/` directly.

## When NOT to apply

- Task is not Doris source.
- One-line typo / formatting fix.
- User explicitly says "skip wiki this time" (explicit override only).

Omit the declaration in these cases.

## Don't

- Don't ingest task-progress logs ("I tried X then Y") — distill to declarative truths.
- Don't dump the whole wiki into context — use `wiki-query`.
