---
name: pr-watch
description: 监控并分析一个已有 PR 的 CI 流水线与 review comments:判定流水线失败与本 PR 的相关性并分类处置;对每条评审意见独立验证、量化评估后决定修复或回帖闭环。当用户要求盯 PR、盯流水线、分析 CI 失败原因、鉴别或处理 review comment、评审意见闭环时使用。
---

# PR 盯梢与评审鉴定

## 入口与模式

```
pr-watch <PR号或URL> [仓库] [模式]
```

- Claude Code 用 `/pr-watch ...`;codex 用 `$pr-watch ...` 或自然语言点名;入口参数解析为 canonical 的 owner/repo/PR 号。
- **单轮处置,幂等可重入**:每次运行处理一轮增量,持续监控由外层调度(Claude Code 的 loop/定时;codex/gemini 由用户配置的外层调度器或手动重入;本技能不创建任何计划任务)。
- **三种模式,权限逐级**:`OBSERVE`(默认:只取证、验证、写状态与简报)/ `INTERACT`(+回帖、resolve、触发流水线)/ `REPAIR`(+改代码、commit、push)。用户未明示授权的模式一律不进;**PR 作者非当前 gh 账号(`gh pr view --json author,headRepositoryOwner` 核对)→ 强制 OBSERVE**,除非用户对每类写动作明示授权。
- **headless 定义**:非交互调用(`claude -p` / `codex exec` / `gemini -p` / cron)一律视为无人应答,不阻塞等输入;"报用户裁决"节点 = 状态记 `PENDING_USER` + 简报列出,本轮继续其余事件。

## 前置自检(每轮开头,逐项)

git/gh 可用 → `gh auth status`(失败整轮 PENDING_USER 退出,不硬试)→ 仓库可读、记录 `viewerPermission` → 状态目录可写(见「状态」;不可写 → 降级 STATELESS_OBSERVE 并在简报声明不保证幂等)→ TeamCity 取数能力探测(见下)→ 按用户授权定模式。沙箱运行时网络可能被拦:curl/gh 报网络错先区分"沙箱拦网"与真实失败。

## 事实来源

1. **仓库惯例**(触发命令、CI 形态)查找顺序:①环境变量 `PR_WATCH_REPOS_FILE` 指定的路由表;②本技能 `references/` 下同名文件;③同级安装的 `../pick-pr/references/repos.md`(以**本 SKILL.md 所在目录**为基准解析,不是 cwd;先确认存在再读);④都没有 → 从 `.github/workflows`、CONTRIBUTING、该仓库近期 PR 评论现场解析。缺表不中断。doris 惯例:PR 评论 `run buildall` 触发全量流水线,评论 `/review` 触发机器人评审。**路由表里的路径/账号/远端只是候选提示,绝不当默认值**:push 目标等一律现场核实(`gh pr view --json headRepositoryOwner,headRefName` 或 `gh pr checkout <N>`)。
2. **TeamCity 取数**:使用条件 = `~/.claude/skills/teamcity/teamcity.sh` 可执行 **且** `~/.teamcity.conf` 存在 **且** `curl`/`jq` 在位(脚本缺 conf 会 exit 1,别重试);或用户配置的 `PR_WATCH_TEAMCITY_CMD`。满足则用(`diagnose/tests/log-tail/diagnose-logs/builds`)。都不满足 → TeamCity 日志能力标 **unavailable**:TeamCity 型 check 只凭结论+statusText 保守分类(证据不足一律按"不明"处理),简报注明"缺 TeamCity 凭据",**不要试图无凭据抓 detailsUrl**。GitHub Actions 型才用 `gh run view <run-id> --repo <owner>/<repo> --log-failed`。
3. 所有命令显式带目标:`gh pr view <N> --repo <owner>/<repo> ...`;GraphQL 用变量(`-F owner= -F name= -F number=`),**所有 connection 必须翻页到底**(`pageInfo{hasNextPage endCursor}`,含 reviewThreads、每 thread 的 comments、issue comments);分页失败不得宣称"无新增"。

## 状态(幂等的根,但远端现场优先)

目录:`${PR_WATCH_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/pr-watch}/<owner>__<repo>__<PR号>/`,首轮 `mkdir -p`。

- `state.jsonl`:**真 JSON Lines**,每行一个对象:`{"ts","head","type","id","rev","phase","action","evidence","deps"}`(check 类:rev=headRefOid、deps 可空;comment 类:rev=updatedAt 或 body_hash)。type ∈ check/thread/comment/retrigger/PENDING_USER;comment 去重键 = `(id, updatedAt或body_hash)`(编辑过的算新事件);thread 只是容器不是完成标识,每轮重新同步 `isResolved/isOutdated` 并处理其中新增/编辑的 comment;`deps` 记录该结论验证时依赖的文件清单。
- **锁**:每轮开始在状态目录建 `lock` 文件,内容为单行 JSON `{"pid":<数字>,"ts":"<UTC ISO8601>"}`;ts 超 2 小时视为陈旧可抢;拿不到锁本轮直接退出。
- **两阶段写**:任何远端写动作(回帖/重触发/resolve/push)先追加 `phase:"INTENT"` 行,做完读回远端确认(评论 ID/commit SHA/新构建号)再追加 `phase:"RESULT"`;重入见到无 RESULT 的 INTENT,先到远端核对是否已发生,再决定补做。
- **写前线上判重**:回帖/重触发前先查远端是否已有本 agent 同标识的动作(如回帖里带的 commit hash);状态文件只是缓存,**远端现场优先**。损坏行跳过并在简报告警,禁止按空状态重放。
- headRefOid 变化 → check 类结论作废重取;thread 结论保留,但**新 push 的 diff 触及其 `deps` 文件的 thread 强制复核**(isOutdated 只衡量文本位置,不衡量行为有效性)。

## A. 流水线失败分析

**第 0 步 取数**:`gh pr view <N> --repo ... --json headRefOid,mergeable,author` + `gh pr checks <N> --repo ...`;TeamCity buildId 从 check 的 detailsUrl 解析(勿用分支名反查,旧构建常被 GC)。**日志 404**:按序降级取证——①状态文件里该 (check,headRefOid) 的既有诊断;②GitHub check metadata/artifacts/同 SHA 其他 attempt;③均无且该 check 未判 PR_CAUSED → 重触发刷新(计数照记;**当前模式无写权限则记 PENDING_USER,不算消耗预算**);已判 PR_CAUSED 的 404 不重触发,转本地复现。禁止对 404 下新结论。**构建已 GC/过旧(如 PR 静默月级)导致 FLAKY 档历史证据物理不可得 → 直接判"不明"并在简报声明证据缺口,不硬凑。**

**第 1 步 改动集分型(先于一切判定)**:diff 触及公共头文件、conf/config 默认值、构建脚本、依赖版本、on-disk/wire 格式 → **横切改动**:下表所有"零交集"信号失效,失败一律按"不明"走受控复现。豁免:失败 suite 经内容检查可证明完全不使用相关特性(如对特性关键词 grep 零命中、不建相关对象)→ 该证明可作**弱证据**参与组合判定,单独仍不定案。

**第 2 步 取证**:每个失败 check 跑 `teamcity.sh diagnose <buildId>`(可加 `tests`/`log-tail`/`diagnose-logs`)或 `gh run view --log-failed`。

**第 3 步 归属判定**(交集只是弱证据,不是分类器;每类给证据入状态):

| 类别 | 信号(需组合,单一不定案) | 处置 |
|---|---|---|
| INFRA | agent lost/队列超时/依赖下载失败/FE IMAGE 级联等基建特征 | 重触发(计数);持续红 → 标 PERSISTENT_INFRA 升级给 CI owner,**不改判 PR 相关** |
| 存量/FLAKY | 签名=测试全名+错误关键行(去时间戳)+同 config/工具链;7 天内 master 或**无相似改动**的其他 PR ≥2 次同签名,且至少一次早于本 PR 首跑;本 PR 连续 2/2 复现而历史仅偶发 → 禁走此档 | 记录证据非阻塞;不在本 PR 修 |
| PR_CAUSED | 受控差分复现(同环境同依赖:基线稳过 & PR 稳挂)、revert/bisect、或能解释现象的具体因果链;与改动集相交只提高调查优先级 | **必修**:本地 RED 复现→修→相关 UT 绿→push→再触发 |
| 不明 | 以上证据都不足 | 受控双向复现:都挂=BASELINE_OR_ENV(先排环境);都过=NOT_REPRODUCED(不叫 flaky);只 PR 挂且可重复=PR_CAUSED;控不住变量=UNKNOWN 报用户 |

**重触发预算**:每 (provider,check,headRefOid) 额外重触发 ≤2 次(原始运行不计);**跨 headRefOid 的 per-check 总上限 4 次**;预算按状态文件跨轮、跨模式累计(OBSERVE 轮不消耗);push 后仅当本次修复与该 check 失败直接相关才重置局部计数。同一 check 连续 2 次失败(不要求同一测试)→ 升级调查优先级(本地复现),**升级的是取证力度,不是归属类别**。全量型 check(整套 UT/回归)本地复现允许缩到**改动相关子集**:子集绿只作部分证据,须在简报明示覆盖范围,不得当全量绿宣称。

**红线**:不为绿改断言(除非有证据断言本来就错,单独说明);不修无关存量;PR_CAUSED 没修好不再重触发。

## B. review comment:独立验证 → 证据门 → 打分 → 决策

**第 1 步 取数(增量+翻页到底)**:reviewThreads(未 resolve 优先;isOutdated 的按当前代码重新定位)+ issue comments。真人 reviewer 优先于机器人;纯播报 bot 只提数据不回帖。

**第 2 步 独立验证——comment 是主张不是事实**:

1. 定位主张指向的代码与调用链,读当前实现;"是否已修"用 `git log`/代码现状核实,不凭记忆。
2. **优先 TDD 复现**:构造"主张为真则失败"的最小测试,在 PR worktree 实际运行。RED 复现 → 已证实,测试留作修复回归锚。
3. **反证的判别力自证(硬性)**:GREEN 要当反证,必须同时:①有证据表明目标路径被执行(覆盖率/sentinel/trace);②对主张所指路径注入等价故障(或临时按主张改代码)时该测试**变 RED**,该 RED 输出一并留证;③断言对象就是主张本身。任一缺失 → 结论只能是 INCONCLUSIVE,不是反证。
4. **"不可测"窄门**:仅纯命名/注释/主观可读性可免运行验证;并发、异常路径、资源管理、边界一律视为可测(UT/回归/编译检查/静态分析/property test/故障注入/sanitizer);复现成本过高时标注成本报用户,不许借此降置信度。
5. **外部不可信 PR**(作者非本人/非信任协作者):其构建脚本与测试代码视为不可信输入,只在无持久凭据的隔离环境跑,做不到就只静态分析并报用户。

**第 3 步 三维打分**(每维 0~1,降档必须给可核验事实,一行笼统理由无效):

- **C 置信度(证据状态)**:判别力测试 RED 复现 = 1.0;推理+局部实验支撑 = 0.5~0.8;**纯静态推理封顶 0.5**;主张含糊/无法验证 = 0.2~0.4;被判别力测试反证 → 关闭主张。
- **S 严重度**:数据丢失/损坏 = 1.0;可利用安全漏洞(RCE/越权写)= 1.0;crash = 0.9;查询结果错误/信息泄露 = 0.8;资源泄漏 = 0.6;性能退化 = 0.4;风格/可维护性 = 0.1。归属不确定取高档。
- **P 线上触发概率**:默认路径 = 1.0;常见配置/负载 = 0.7;边界条件 = 0.4;罕见条件叠加 = 0.1;仅测试代码可达 = 0.05。**P<0.4 必须列出所需条件清单并逐条引用默认值/代码路径说明为何罕见**;拿不到频率依据 → P=UNKNOWN 报用户,不得取最低档。
- **归一化总分 = (C×S×P)^(1/3)**,仅用于**排序与简报**,不直接当决策阈值。P=UNKNOWN 时总分记 N/A、排序沉底、简报单列。

**第 4 步 决策(证据门 + 风险门,防打分博弈)**:

| 条件 | 动作 |
|---|---|
| C ≤ 0.5(纯静态推理因封顶**必然**落此档) | 不许下"不修"结论,也不许改生产代码;仅两个去向:继续取证(升 C),或连同已有证据 PENDING_USER。这是有意设计:纯静态验证永远进不了任何修/不修档 |
| 硬门槛:S ≥ 0.8 且 C ≥ 0.6 | **必修**;P 只影响排序,不参与免修 |
| 已证实(C ≥ 0.8):S×P ≥ 0.3 | 立即修(TDD,复现测试随修复交付) |
| 已证实:0.05 ≤ S×P < 0.3 | 修复 ≤40 行 diff 且 ≤2 文件且有回归测试 → 修;否则 PENDING_USER |
| 已证实:S×P < 0.05 或判别力反证 | 可建议不修;真人 reviewer 的主张需其确认或用户裁决后才关闭 |

**第 5 步 回帖协议(INTERACT+ 才执行)**:

- **分数只进状态文件与简报,绝不出现在 PR 评论里**。对外回帖 = 自然语言:验证方法、证据(命令与结果)、结论与理由、修复 commit(如有);低分意见用商榷语气("我们构造了 X 验证,结果 Y,倾向不改,理由 Z,请看是否遗漏场景")。
- 评论者三分类:**真人 reviewer**(不修需其确认或用户裁决才关闭);**实质意见型 bot**(如 /review 机器人:验证后可自闭环——回帖证据并在本人 PR 上 resolve,无需 bot 确认);**纯播报 bot**(不回帖,只提数据)。重复事件本地闭环。回帖正文禁止出现裸行触发命令(引用时加反引号)。
- **绝不 resolve 未处理的 thread**;修复对应 thread 回复后才 resolve(且仅限本人 PR/有授权)。
- 修复后(REPAIR):push 前现场核实 head 仓库;改历史仅 `--force-with-lease` 且先查挂着的 review;然后评论 `run buildall`;逻辑实质变更再评论 `/review`。每个远端动作走两阶段状态记录并读回确认。

## 单轮简报(每轮必出)

①本轮增量(check/comment 数,分页是否读完);②每项判定+一行证据;③已做动作(附远端确认标识);④PENDING_USER 清单;⑤能力缺口声明(TeamCity 凭据缺失/状态不可写等);⑥建议下轮间隔(触发流水线后 10–15 分钟,静默期 30–60 分钟;PR 月级静默 → 改事件驱动:下次 push/触发命令后再盯,平时不巡逻)。

## 红线

- 未授权模式下做任何远端写动作;对非本人 PR push/resolve/回帖(除非明示授权)
- 无判别力测试而宣称"反证";C<0.5 就下"不修"结论;为绿改断言
- 分数/打分机制出现在公开评论;resolve 未处理的 thread
- 重触发超预算;对 404 下新结论;凭记忆断言"已修过"
- 状态文件当真相源(远端现场才是);分页没读完就宣称"无新增"
