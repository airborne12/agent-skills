# Bug-fix reply template (Jira wiki markup)

Used by `bash jira.sh fix-comment` to standardize bug-fix replies on a Jira
issue. Rendered as Jira wiki markup so headings/code blocks display correctly.

Sections (in order):

1. **问题触发条件** — when / how the bug fires, with a minimal repro if possible.
2. **定位根因** — where in the code the defect lives and why it produces the wrong
   behavior. Reference functions / files with `{{...}}` inline code.
3. **解决方案** — what was changed and why, plus the PR link.

## Rendered shape

```
h3. 1. 问题触发条件

<trigger>

h3. 2. 定位根因

<root_cause>

h3. 3. 解决方案

<solution>

PR: <pr_url>
```

Inside each section, use Jira wiki markup:
- Inline code: `{{ident}}`
- Code block: `{code:cpp} ... {code}` (or `{code:sql}`, `{code:java}`, etc.)
- Bold: `*text*`
- Bullet list: lines starting with `* `
