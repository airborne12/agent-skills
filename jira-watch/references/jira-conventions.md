# 内部 Jira 现场惯例（快照，以现场为准；最后核实 2026-09-02）

本文件是 jira-watch 的参考资料，记录**当前**Jira 实例上可观测到的机器人、字段、状态与标题惯例。任何一项与现场不符时，以现场为准并回写本文件。

## 连接

- Jira Server 8.20.4，REST v2；凭据 `~/.jira.conf`（Bearer PAT）；只能经 VPN（`tun0`）直连，脚本已剥离代理环境变量。
- 交互脚本：`~/.claude/skills/jira/jira.sh`（view/search/comment/create/transitions/transition）；jira-watch 自带 `scripts/jira_watch.py` 覆盖轮询、diff、链路分析与受控写。

## 项目与分类信号

| 项目 | 典型内容 | 标题惯例 | 分类 |
|---|---|---|---|
| CIR | 客户故障 | `[渠道A][5.0.4][cluster-xxx] 现象` / `【客户】【2.1.7】现象` / `[Cloud][4.1.7][仓库ID] 现象` | CUSTOMER_BUG |
| DORIS | 社区流水线巡检、内部缺陷、Epic/功能 | `[社区流水线] 不稳定用例 mute: <case>`（label `社区流水线`） | CI_FLAKY / BUG / EPIC / FEATURE |
| CORE | 内部核心缺陷与任务 | 自由 | BUG / FEATURE |

- 版本字段 `versions`：`cloud-5.0.4` / `cloud-26.0.4` / `cloud-4.1.7`（云）；`2.1.7`（企业版）。字段为空时从标题方括号取。
- **版本字段可能是旧命名或填错**：`cloud-5.0.x` 是 `cloud-26.0.x` 的旧命名（`tag-internal-cloud-5.0.0` 是 `26.0.1` 的祖先，仓库没有 5.0.4 tag）。以崩溃栈 `*** Current BE git commitID: <sha> ***` 反查为准：internal-core 里该 commit 通常就是 `Bump version to cloud-X enterprise-Y` 提交，`git tag --points-at` 直接给出版本 tag。
- 描述里的版本串：`internal-4.1.7-2cb76e238bf`（含 commit）。
- 常见 label：`cloud`、`渠道A`、`值班`、`倒排索引`、`半结构化`、`社区流水线`。
- issue 类型：`故障`（Bug）、`Epic`、`Story/任务/新功能/改进`（FEATURE）。

## 状态流转（CIR/DORIS/CORE 三个项目 ID 相同）

| ID | 目标状态 |
|---|---|
| 11 | 待办 |
| 21 | 处理中 |
| 31 | In Review（正评审） |
| 41 | 完成 |
| 51 | 待排期（Backlog） |
| 61 | AddUserCase（CIR）/ In Development（DORIS/CORE） |
| 71 | In Testing（DORIS/CORE） |

jira-watch 白名单默认只含 `处理中`。`完成`/`In Review` 永远由人决定。

## 机器人与评论格式

### aibot（AI 值班 triage）

- 先发占位：`正在分析该问题，将结合…给出 triage 结论。`（不算分析）
- 再发正文，特征：首行 `AI-Analysis-Slot: slot_xxx`；`h2. 首次 on-call triage 结论`；`*判断：{{fail|partial|pass}}…；根因置信度：{{high|medium|low}}。*`；分节 `h2. 当前证据与调用链`、`h2. 历史 Jira 与代码修复证据`（引用其他 Jira key 与 GitHub PR URL）。
- 后续可能再评论（如确认 hotfix PR）。
- **它是主张不是事实**：引用的 PR 可能不是最终落地的修复链（例：CIR-10001 分析引用 doris#63138/#65687，实际客户 hotfix 走的是 doris#66736 → internal-core#10979；同族在客户基线 `branch-internal-doris-4.0` 上是 #10973，在 4.1 上是 #10974，doris `branch-4.0` 的 #66737 被关闭未合入）。
- 正文常用**裸 SHA**（`03b7afda992`）而非 PR 链接引用提交，`pick-advice` 会把本地仓库能找到的 SHA 通过提交主题尾部 `(#N)` 反查成 PR。
- 判断/置信度写法不固定：`{{fail}}` 或 `fail（已确认代码缺陷）`，`置信度：{{high}}` 或 `confidence：high`。

### cibot（社区流水线每日巡检脚本）

- 头行：`[社区流水线每日巡检 2026-09-02 | test=<TeamCity testId> | latest=build:(id:N),id:M | decision=confirmed-flaky]`
- 分节：`h2. 失败现场`（`*失败行:*`、`*Build:*` URL 带 `buildTypeId`）、`h2. 样本与结论`（最近 300/50 次统计、owner 证据）、`h2. 处置`（含恢复条件）。
- 描述里有：流水线链接、首次失败 PR、TeamCity 历史记录链接。

### PR 链接在哪里

- 没有 GitHub dev-panel 集成（`/rest/dev-status` 为空），PR 只出现在**评论/描述正文**里，格式 `https://github.com/<owner>/<repo>/pull/N` 或 wiki 链接 `[文字|url]`。
- 附件通过 `fields.attachment[].content` 下载（core/日志常以外链形式贴在评论里，如 COS/OSS URL）。

## 仓库分支与 pick 惯例（详见 `../pick-pr/references/repos.md`）

- apache/doris：`master`、`branch-4.1/4.0/3.1/3.0/2.1` 及点版本分支；pick 标题 `branch-4.1: <原标题> #<原PR> (#<pickPR>)`。
- example-org/internal-core：默认 `internal-cloud-4.0`；基线 `branch-internal-doris-2.1/3.0/3.1/4.0/4.1`；客户 hotfix `branch-hotfix-internal-cloud-<版本>[-客户]`；tag `tag-internal-cloud-<版本>` / `tag-internal-doris-<版本>`；pick 标题 `<目标分支>: <原标题> (#<doris PR>) (#<core PR>)`。
- **PR 号跨仓库撞号**：internal-core 提交信息里的 `(#10979)` 可能是 2022 年的 doris PR 号。判定"某分支是否含修复"必须按**标题核心**（去 `branch-x:` 前缀与尾部 `(#N)`）比对，或用 `gh pr view --json mergeCommit` 取 SHA 做 `merge-base --is-ancestor`。
- 发布 tag 是否含修复：`git tag --contains <pick SHA>`；`Bump version` 提交排在修复之后不代表已发布。
- 版本 → 基线分支：用 tag 与各基线分支的 `git rev-list --count` 双向距离，`tag_ahead=0` 且 `branch_ahead` 最小者为基线（实测：`tag-internal-cloud-26.0.4` → `branch-internal-doris-4.0`；`tag-internal-cloud-4.1.7` → `branch-internal-doris-3.1`，tag 多 3 个 hotfix 提交）。
