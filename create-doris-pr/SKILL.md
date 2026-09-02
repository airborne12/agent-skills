---
name: create-doris-pr
description: 为 Apache Doris 创建 pull request，遵循仓库当前的 PR 模板与标题规范。当用户说"提PR""提交PR""创建PR""create PR""push and create PR"，或想把分支推上去开 PR 时使用。所有仓库标识、远端名、默认分支、模板内容都从当前仓库现场解析，不写死。
---

# 创建 Doris PR

向 Doris 上游仓库发起 PR，标题和正文都遵循仓库当前的规范。

## 第一步：解析事实，不要写死

```bash
git remote -v                                  # 找出上游远端与个人 fork 远端
git branch --show-current
git ls-files | grep -i pull_request_template   # 定位仓库当前的 PR 模板
```

- **上游仓库 slug**：从上游远端 URL 解析 `owner/repo`。
- **fork owner**：从个人 fork 远端 URL 解析，不要写死用户名。
- **目标分支**：从上游远端解析默认分支（`git symbolic-ref refs/remotes/<上游远端>/HEAD`，或 `gh repo view <上游 slug> --json defaultBranchRef`），不要假设。
- **PR 正文模板**：读上面定位到的模板文件的当前内容，不要用记忆里的旧版本。
- **标题规范**：从仓库根部 agent 指令文件（`AGENTS.md` / `CLAUDE.md`）里的提交信息格式解析。

## 第二步：前置检查

```bash
git log --oneline <分支> --not <上游远端>/<默认分支>
git status --porcelain
```

- 改动必须已全部提交；没提交就先让用户确认再提交。
- 分支上只能有本任务相关的 commit。混进了别的特性就停下来告诉用户，不要硬提。
- 确认分支已推送到个人 fork 远端；没推就先推：`git push -u <fork 远端> <分支>`。

## 第三步：创建 PR

用解析出来的值填占位符，正文用 heredoc 传入：

```bash
gh pr create --repo <上游 slug> --base <默认分支> \
  --head <fork owner>:<分支> \
  --title "<按仓库规范的标题>" \
  --body "$(cat <<'EOF'
<按仓库当前 PR 模板逐节填写>
EOF
)"
```

## 填写要点

- **Issue Number**：用户提到 issue 就写 `close #xxx`；没有就删掉该行或写 `N/A`。
- **Related PR**：有就列出，没有就删掉或写 `N/A`。
- **Problem Summary**：写清问题是什么、代码里的根因、修复前后的端到端现象、以及怎么修的。只读这一段就能完整理解背景。重构说明理由，性能优化给出具体 case 和提升幅度。
- **Release note**：面向用户的行为或特性变更必须写；纯内部重构或只改测试写 `None`。
- **测试清单**：只勾真正跑过的。勾了手动测试就补上具体步骤。
- **Behavior changed / 文档**：默认 `No`，有变更才改。

模板里的其它章节按模板当前结构填，不要增删章节。

## 第四步：创建后核对

- 回给用户 PR URL。
- 核对 PR 的 base 分支、head SHA、commit 列表、改动文件，与预期一致。

## 注意

- 目标仓库、fork owner、默认分支一律用第一步解析出来的值，不要用上一次的记忆。
- 不要把不同特性的 commit 混进一个 PR；发现了先警告用户。
- 建 PR 前确认分支确实推到了 fork 远端。
