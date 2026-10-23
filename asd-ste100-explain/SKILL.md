---
name: asd-ste100-explain
description: >-
  Explain pull requests, bugs, and code behavior with source evidence and
  ASD-STE100-inspired technical language in Chinese or English. Use when the
  user asks to explain a PR's problem, trigger, root cause, impact, or fix;
  says "按 ASD-STE100 解释", "解释这个 PR 修复了什么", or "把根因讲清楚";
  or requests a plain technical explanation grounded in code. For general
  prose editing, use the project's writing workflow instead.
---

# ASD-STE100 Technical Explanation

Explain how a technical problem occurs and how a change corrects it. Combine
source verification with selected ASD-STE100 writing principles: fixed terms,
short sentences, named actors, explicit conditions, and one topic per sentence.
Chinese output uses an adaptation of those principles. The bundled checker
does not certify compliance with the complete ASD-STE100 standard or dictionary.

Use the user's language unless the user requests another language. Keep the
explanation in chat unless the user asks for a file or another destination.
An explanation request does not authorize changing code or publishing a PR comment.

Read [writing-rules.md](references/writing-rules.md) before drafting. Read
[pr-420-example.md](references/pr-420-example.md) when a worked example would
help choose the level of detail. Its repository facts are historical evidence,
not a source for another PR's behavior or current status.

## Establish the facts

1. Identify the requested PR, commit, diff, or code path. Read project instructions
   and terminology that apply to the source. Answer repository questions from
   the repository before asking the user.
2. For a PR, read its description and complete diff. Record the actual base and
   head commits. Use the environment's connected repository tools when available;
   otherwise use its CLI or browser. Do not assume a specific MCP server exists.
3. Read the changed functions and enough callers, data readers, or formulas to
   connect the code change to the reported result. Inspect old code at the base
   and new code at the head. Avoid mixing the PR with the current default branch.
4. Read discussion, tests, and companion changes only where they explain intent,
   reproduction, dependencies, or validation. Attribute author-reported results
   to the author. Passing tests do not establish untested integration behavior.

Keep four kinds of evidence distinct while reasoning:

| Evidence | How to use it |
|---|---|
| Behavior verified in code | State the behavior and link to the inspected code |
| Results reported by an author | Name the author or report as the source |
| A calculation or inference | Give the inputs or state that it is an inference |
| An unknown or untested claim | State the limit without supplying a guessed value |

If the source cannot be read, explain the supported facts and the missing
evidence. Request the smallest missing diff or code excerpt when it prevents
an accurate explanation. Do not turn a PR title into a verified root cause.

## Build the explanation

Recover this causal chain before drafting:

> Trigger condition → component action → incorrect state or value →
> reader or consumer of that state → user-visible result.

Then identify the corresponding repair:

> Changed action → restored invariant → corrected result → conditions or dependencies.

Name the actor at each link. For example, a wrong counter matters because a
scorer reads it, not merely because the counter is wrong. Keep the scope of
each value clear: one field, document, segment, index, or whole collection.
Distinguish the primary defect from secondary defects repaired by the same diff.

Choose the smallest example that exposes the causal chain:

- Prefer the PR's verified reproduction. Preserve input values, query, version,
  configuration, and the event that activates the defect.
- Explain each quantity before using it. Distinguish repeated token occurrences
  from distinct terms, elapsed time from CPU time, or analogous domain quantities.
- Calculate intermediate values when they explain the failure. Use a comparison
  table when before/after results are easier to understand side by side.
- Label invented inputs as illustrative. Do not present computed or invented
  results as an executed test. Do not invent exact scores or performance numbers.

For a non-PR code explanation, use the same chain with the normal input and
result. Omit defect-specific material when the user is asking how working code behaves.

## Draft for the reader

Start with the concrete problem and consequence. Continue with the facts the
reader needs to understand that conclusion. A useful order for a substantial
PR explanation is:

- The failure and its user-visible effect.
- A small glossary, only for terms used in the explanation.
- The trigger and the old behavior.
- A minimal example with the wrong and correct results.
- The changed behavior and why it restores correctness.
- Material fallback behavior, dependencies, costs, and validation limits.

Treat this order as a set of building blocks, not mandatory headings. Use
connected paragraphs with a clear first sentence. Bold a topic sentence when
it helps scanning. Skip a glossary, example, or table when it adds no information.
Scale the detail to the user's question.

Keep code identifiers exact and in backticks. Link claims near their supporting
source. Prefer commit-pinned file links with line anchors for code, and the PR
or a specific comment for reported experiments. Verify current status if you
mention it; date a status that can become stale.

Describe the fix's actual scope and material limits. In particular, distinguish
a corrected output from immediately repairing existing stored data, and a
library guard from a companion application's rebuild path. Include a limit
only when it helps the reader assess or use the change.

## Check and deliver

Review the causal chain, arithmetic, terminology, source links, and attribution.
Confirm that a reader can answer: What triggers the problem? What goes wrong?
Why does that affect the result? How does the change correct it? What evidence
establishes the claim, and what remains untested?

Run the local language check on the explanation, using the skill's actual path:

```sh
python3 <skill-directory>/scripts/check.py --lang zh <draft-file>
python3 <skill-directory>/scripts/check.py --lang en <draft-file>
```

Choose the language of the output. Pass `-` instead of a file to check text on
standard input. Review each hit; code, quotations, and necessary technical
terms can justify an exception. If Python is unavailable, review the same
rules manually and do not claim that the script ran.

The checker finds wording and formatting candidates. It cannot verify facts,
causality, citations, or full ASD-STE100 compliance. Correct the explanation
after checking. Deliver the explanation, not the internal evidence ledger or
checker report, unless the user requests those artifacts.

## Use in Codex and Claude Code

This directory is self-contained. It requires no other installed skill.
Python 3 is used only for the optional mechanical check; repository access uses
whatever tools the host provides.

- In Codex, invoke `$asd-ste100-explain` followed by the PR or question.
- In Claude Code, invoke `/asd-ste100-explain` followed by the PR or question.
- Both hosts can also select the skill from a matching natural-language request.
- Install the directory in the host's skill search path. On one machine, a
  Claude Code entry at `~/.claude/skills/asd-ste100-explain` can be a directory
  symlink to the same skill used by Codex.
