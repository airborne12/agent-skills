---
name: jira-watch
description: 监听分配给自己的 Jira（内部 Jira Server）并对新事件做单轮自动处置：校验 aibot 等 AI 值班机器人的分析、追出修复 PR 在 apache/doris 与 internal-core 各分支的落地/pick 情况、判断当前 issue 版本对应的基线分支与是否需要 pick，受控回写评论与状态并推送飞书简报。当用户要求盯 Jira、监听 Jira、值班处理新分配的 Jira、校验 AI 分析结论、查某个修复在哪些分支/要不要 pick、或按事件驱动跟进 CIR/DORIS/CORE issue 时使用。
---

# Jira 监听与自动处置

## 入口与模式

```
jira-watch [模式] [--jql '<JQL>'] [KEY ...]
```

- **单轮处置，幂等可重入**：每次运行处理一轮增量；持续监听由外层调度（Claude Code：`/loop 30m /jira-watch`；无人值守：cron 跑 `claude -p "/jira-watch"`）。本技能**不创建任何计划任务**。
- **两档权限**：`OBSERVE`（默认：只取证、分析、写本地状态与简报、推飞书）/ `INTERACT`（+回写 Jira 评论、把 `待办` 流转到 `处理中`）。用户未在本次对话明示授权就不进 INTERACT；INTERACT 只通过 `--mode INTERACT` 传给脚本，不改配置文件默认值。
- **只处理分配给自己的 issue**；`@我` 但 assignee 是别人的，只在简报里提，不回写。
- **headless 定义**：非交互调用一律视为无人应答，不阻塞等输入；"报用户裁决"= 状态记 `PENDING_USER` + 简报列出，本轮继续。
- 工具：`~/.claude/skills/jira-watch/scripts/jira_watch.py`（子命令见下表；一切输出 JSON）。凭据 `~/.jira.conf`，参数 `~/.jira-watch.conf`（本机路径、飞书 open_id、白名单）。

| 子命令 | 用途 |
|---|---|
| `baseline` | 首轮只建快照，不把存量当事件 |
| `events [--dry] [--force KEY,..]` | 轮询 + diff 快照 + 并入上轮未 ack 事件 + 过滤已处理 → 本轮事件与增强后的 issue；`--force` 把存量 issue 当事件重处理 |
| `issue KEY` | 单个 issue 增强视图：分类、AI 分析解析、CI 巡检解析、PR/Jira 引用、@我、附件 |
| `pick-advice KEY [--no-fetch]` | 修复族 × 分支包含矩阵 + 版本基线 + pick 建议（自动追 1 跳引用 issue 的 PR） |
| `pr-chain REF...` / `resolve-version V` | 上一条的两个零件 |
| `comment KEY --body-file F --event-ids ...` | 受控评论：免责前缀 + slot 判重 + 两阶段记录；OBSERVE 下拒绝 |
| `transition KEY --to 处理中` | 白名单流转；OBSERVE 或非白名单目标一律拒绝 |
| `record --json` / `lock` / `unlock` / `brief --file` / `notify --file --round-id` / `attachments KEY` | 状态、简报、飞书私聊、拉附件 |

## 前置自检（每轮开头）

`lock`（拿不到锁本轮退出）→ `config`（凭据、仓库路径、open_id 都在，`fetch_head_age_hours` 看克隆新鲜度；超过 6 小时脚本会自动 `git fetch`，失败进"能力缺口"）→ `gh auth status`→ 状态目录可写（不可写 → 降级 STATELESS_OBSERVE 并在简报声明不保证幂等）→ 是否有 `dangling_intents`（有则先到 Jira 远端核对该动作是否已发生，再决定补做）。

## 事实来源与红线级原则

1. **AI 机器人的评论是主张不是事实。** aibot 给出的根因、"同 CIR-xxxx"、PR 链接，每一条都要独立核对：引用 issue 真的同栈/同版本吗？引用 PR 真的合了、合到哪、标题核心是什么？实际落到客户的 hotfix 可能是**另一条**PR 链（`references/jira-conventions.md` 有实例）。
2. **PR 号会跨仓库撞号。** 判断某分支是否含修复只认两种证据：`merge-base --is-ancestor <mergeSHA>`，或 pick 提交的**标题核心**（去 `branch-x:` 前缀与尾部 `(#N)`）一致。`git log --grep '#N'` 单独不算。
3. **本地克隆先看新鲜度。** 结论依赖的分支/tag 必须来自 fetch 之后；`ref_is_fallback=true`（精确 tag 不在本地）时结论标"待 fetch 复核"。
4. **崩溃栈里的 BE commit 才是版本的事实源。** Jira 版本字段可能是旧命名或填错（实例：标 `cloud-5.0.4`，BE commit `a9719436f68` 反查是 `Bump version to cloud-26.0.4 enterprise-4.0.6`）。`pick-advice` 会自动用描述里的 `Current BE git commitID` 反查并标出 `version_mismatch`；版本对不上时评论里要请报告人改版本字段。
5. **版本 → 基线分支用 git 距离，不用记忆。** `resolve-version` 输出 `confidence`；`none/low` 时不得写"对应 X 分支"，只写"按版本号推断"。
6. **"分支已含修复" ≠ "客户能拿到"。** 矩阵里每个命中都带 `tags`（含该提交的发布 tag）；`尚无发布 tag 包含` 意味着还没有正式版带上它，`Bump version` 提交排在修复之后也不等于发布包含，要以 tag 或包内 submodule 指针为准。
7. 仓库路径、远端名、分支族只是候选提示（`../pick-pr/references/repos.md`），执行时现场核实。`gh pr view` 的合并信息也要用本地 `merge-base`/`branch -r --contains` 交叉核一次。

## 单轮流程

**第 0 步 取事件**：`events`。没有事件也要出简报（①增量为 0）。每个事件按 `kind` 分流：

| kind | 处置 |
|---|---|
| `NEW_ISSUE` | 先 `issue KEY` 看分类；`EPIC/FEATURE/OTHER` 只跟踪记 `TRACK_ONLY`；`CUSTOMER_BUG/BUG/CI_FLAKY` 进第 1 步 |
| `AI_ANALYSIS_READY` | 进第 1 步（校验）+ 第 2 步（补充） |
| `CI_INSPECTION` | 进第 3 步 |
| `MENTIONED_ME` / `NEW_COMMENT` | 读评论：是提问 → 草拟答复进 PENDING_USER；是新证据（core/日志/SQL） → 更新台账；是分派提醒（"看看这个"） → 视同 `NEW_ISSUE` 走第 1 步 |
| `FORCED` | 用户用 `events --force KEY` 指定重处理的存量 issue，按其分类走第 1 步 |
| `STATUS_CHANGED` / `DROPPED` | 只记录 |

**第 1 步 校验 AI 分析**（`CUSTOMER_BUG` / `BUG`）：

1. 复述 AI 的主张：根因、判断 `fail/partial/pass`、置信度、引用的 issue 与 PR。
2. 逐条核对：`issue REF` 看引用 issue 的版本/栈/结论；`pr-chain` 看引用 PR 的状态与标题核心；栈/SQL/版本与本 issue 描述是否一致（BE commit、版本字段、慢查询时间戳等）。
3. 判定：`AI_VERIFIED`（主张成立且证据齐）/ `AI_PARTIAL`（成立但缺环，列出缺什么）/ `AI_REJECTED`（给出反证）/ `INCONCLUSIVE`（证据不足，列出要向报告人要什么）。**纯读评论没有任何独立核对 → 只能 INCONCLUSIVE。**

**第 2 步 补充结论（用户要的"更进一步"）**：`pick-advice KEY`（约 1–2 分钟；同一轮复跑加 `--no-fetch`），然后用人话回答五个问题：

1. 客户到底跑的什么版本（`be_commits` → `commit_versions`；与 Jira 标注不符要点明）。
2. 修复在哪个 PR（修复族源头 + 各 pick 成员，附状态与目标分支）。
3. 已 pick 到 doris / internal-core 的哪些分支、含于哪些发布 tag（矩阵里 `direct/picked` 与 `tags`）。
4. 当前版本对应哪个基线分支（`base_branch` + 依据 + 置信度）；**当前版本**已有的 `branch-hotfix-internal-cloud-<版本>*` 是否已含修复（它们已并入矩阵；其他版本的 hotfix 分支只会通过引用链出现）。修复族成员里 base 为 `branch-hotfix-*` 的会标"客户 hotfix 已验证"，`CLOSED` 的 pick 会标"已关闭未合入"（要问关闭原因，不要再建议 pick 同一分支）。
5. 要不要 pick、pick 到哪（`suggested_targets`）；客户升级到哪个正式版能拿到修复；不能升级时从哪个 tag 拉 hotfix、pick 哪个 SHA（可直接给 `/pick-pr` 命令）。
   矩阵里 `missing` 的分支只代表**本地克隆**没找到；fetch 失败或 `ref_is_fallback` 时必须写明。修复族之间要分清"必需"与"加固"（看哪一族真正被客户 hotfix 验证过）。

**第 3 步 CI 不稳定用例**（`CI_FLAKY`）：读 `ci_inspections`（decision、test id、最新 build、失败行、恢复条件）；用 `teamcity` 技能对 `latest_build_id` 做 `diagnose`/`tests`，核对签名是否与巡检一致、失败是否只在该 case；结论三选一：`CONFIRM_FLAKY`（同意 mute，给出恢复条件）/ `REAL_BUG`（附本地复现或代码因果链，转第 2 步找修复）/ `INCONCLUSIVE`。

**第 4 步 回写协议（INTERACT 才执行）**：

- 评论正文 = 校验结论 + 五个问题的答案 + 证据（命令与关键输出）+ 下一步建议；**C/S/P 数值打分只进状态文件**（`strip_scores` 会整行剔除），判定词与置信度等级（`AI_VERIFIED`、`high`）可以出现在评论里。评论自动带免责前缀与 `Jira-Watch-Slot`；脚本先查远端同 slot 再发。OBSERVE 下用 `comment --dry-run` 可预览完整正文且不落账。
- 流转只允许 `待办 → 处理中`，且仅当本轮已回写了实质评论。`完成`、`In Review`、改 assignee、改字段一律 PENDING_USER。
- 每个远端动作两阶段：INTENT → 发 → 读回确认（评论 id / 状态名）→ RESULT。

**第 5 步 落账与简报**：每个事件 `record` 一条 `phase:RESULT` 的 verdict（含 `event_id`/`event_ids`、判定、一行证据）——**没落 RESULT 的事件下一轮会原样再来**（pending 持久化），这是有意设计；组装 round.json → `brief` → `notify`（`--round-id` 作幂等键）→ `unlock`。

## 单轮简报（每轮必出，推飞书）

①本轮增量（事件数、轮询数）；②每个事件的判定 + 一行证据；③已做动作（附远端确认标识）；④PENDING_USER 清单（含评论草稿路径）；⑤能力缺口（fetch 失败、gh 不可用、tag 缺失…）；⑥建议下轮间隔（有活跃客户故障 15–30 分钟，静默 60 分钟）。

## 红线

- OBSERVE 下做任何 Jira 写动作；对非本人 issue 回写；把 issue 流转到 `完成`/`In Review`
- 直接把 AI 机器人的 PR 号/结论当事实写进评论；用 `grep '#N'` 单证据断言"已 pick"
- 未 fetch 或 `ref_is_fallback` 时把"本地没找到"写成"未修复"
- 版本→分支凭记忆而非 `resolve-version`；分数出现在公开评论
- 跳过 `baseline` 直接 `events`（存量 98 个全成"新事件"）；一轮里对同一 issue 重复回写

## 合理化对照表

| 想法 | 现实 |
|---|---|
| "aibot 置信度 high，直接照抄" | 它抄错过 PR 链；校验是本技能存在的理由 |
| "grep 到 #10979 了，说明 pick 了" | 同号可能是 2022 年 doris 的 PR；看标题核心 |
| "本地克隆昨天才 fetch 过" | 看 FETCH_HEAD，脚本按 6 小时算陈旧 |
| "版本 4.1.7 肯定对应 branch-4.1" | 实测 cloud-4.1.7 基线是 internal-doris-3.1 |
| "先把状态改成处理中表示我接了" | 没有实质评论的流转是噪音；且只在 INTERACT |
| "这轮没事件就不出简报了" | 无事件也是信息，简报①写 0 |
| "Jira 标了 cloud-5.0.4 就按 5.0 找" | 栈里的 BE commit 反查是 26.0.4；5.0.x 是旧命名 |
| "Bump version 提交在修复之后，发布肯定带了" | 没有 tag 包含就是没发布；要核 tag 或包内 submodule |
| "gh 说 merged 到 master，那就在 master" | 本地 `merge-base --is-ancestor` 交叉核一次，顺便拿 tags |
| "两个修复族都是必须的" | 看哪一族被客户 hotfix 实际验证过；另一族可能只是加固 |
