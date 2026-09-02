---
name: pick-pr
description: 把一个 PR 或 commit cherry-pick / backport 到另一个分支或另一个仓库(如 apache/doris 各 release 分支、internal-core),覆盖直接 pick、冲突解决、文件挪位/函数重构后的语义移植,以及 pick 后的编译、单测、回归与提 PR。当用户要求 pick、backport、cherry-pick、合到 branch-X、pick 到 internal、摘到某分支时使用。
---

# PR Pick 工作流

## 入口

参数文法(各运行时通用),用户点名本技能即可,不需要复述任何流程要求:

```
pick-pr <源 PR 号或 commit> <目标仓库> <目标分支> [更多目标分支...]
```

- Claude Code 里用 `/pick-pr ...`;其它运行时直接说"用 pick-pr 技能:pick 66877 到 internal-core internal-cloud-4.0"。
- 无界面直跑(按所在运行时):`claude -p "/pick-pr ..."` / `codex exec "use the pick-pr skill: ..."` / `gemini -p "..."`。headless 需保证运行时沙箱允许网络与写操作,否则查询与 push 会卡审批。
- **headless 规则**:下文任何"停下问用户"节点在 headless 下 = 终点。把问题与选项写入 `.pick_progress`(标 `BLOCKED`),输出摘要后以失败状态结束;绝不在无人应答时自选任何选项。交互式重跑同一命令时从该问题继续。
- 省略目标仓库时按分支名推断:`branch-*` → doris;`internal-*` / `branch-internal-*` / `branch-hotfix-*` → internal-core。有歧义就问,不猜。

## 事实来源(先解析,再动手)

1. **跨仓库路由事实**(仓库路径、worktree 根、远端、push/PR 惯例、分支构建环境坑)读本技能 `references/repos.md`。它是快照:与现场不符时以现场为准。**回写规则**:仅当验证命令**成功执行**且输出与快照矛盾时才允许回写,回写必须附验证命令及输出摘录;命令失败(网络抖动、超时)一律先当环境故障排查,禁止据失败改写事实。运行时若无权写该文件(只读沙箱),以现场核实值继续执行,并把建议的路由表补丁写进最终报告,不阻塞流程。
2. **仓库内纪律**(构建/UT/回归脚本及参数、格式化、worktree 初始化、提交信息格式、PR/CI 的等价命令)从目标仓库根的 `AGENTS.md` / `CLAUDE.md` 现场解析。仓库指令与本技能冲突时,以仓库指令为准。
3. **仓库不在路由表里**:正文所有"按路由表"的项(worktree 根、远端、push/PR 惯例、构建环境)改为全部从该仓库指令文件与 `git remote -v` / `git branch -r` 现场解析;解析结果若值得复用,按回写规则新增条目(一次性/沙箱仓库不回写)。
4. 猜出来的命令产出的不是证据。解析不出来就去仓库里找。

## 前置自检(门 0 之前)

- 源/目标仓库走 GitHub 的:`gh auth status` 确认已登录且有读写权限;未登录即停(headless → BLOCKED)。
- 本技能命令假定 bash + GNU coreutils;worktree 与编译在本机文件系统执行。

## 必用能力(运行时有同名 skill 则用;没有就按内联程序执行,不许跳过)

- **完成前验证**(等价 superpowers:verification-before-completion):任何"编译过了 / UT 绿了 / 可以提 PR"的断言,必须在同一轮里实际跑过对应命令、读完输出、核对退出码;没有新鲜命令输出不许下断言。提交、push、建 PR 前各执行一次。
- **发 PR**(等价 create-doris-pr):不写死仓库事实,现场解析——`git remote -v` 解析上游 slug 与 fork owner;读 `.github/PULL_REQUEST_TEMPLATE.md` 逐节填写;标题规范按仓库惯例(现场 `git log <目标ref> --oneline` 核对);先 push fork 再 `gh pr create --repo <上游slug> --base <目标分支> --head <fork owner>:<分支>`;建完核对 base/head/文件列表并回 PR URL。
- **CI 诊断**:TeamCity 类仓库若 `~/.claude/skills/teamcity/teamcity.sh` 存在(纯 bash,凭 `~/.teamcity.conf`),直接调用;否则 `gh pr checks` + `gh pr view --json statusCheckRollup` 盯 CI。
- **格式化/UT/回归**:一律按目标仓库根指令文件解析出的脚本执行;运行时若有对应仓库 skill 可代替手工解析,但结论以仓库脚本输出为准。

## 七道门

每道门拿到新鲜证据才前进;没过的门不许跳。**总则(证据失效语义,按 tree 而不是 HEAD)**:门 5 各子步的证据绑定当时的 `git rev-parse HEAD^{tree}`;树 OID 变了(代码真变了)→ 门 5 已过子步全部作废,从 5.1 重跑;只改 commit message(amend 后树 OID 不变)→ 门 5 证据仍有效,只需重做门 6 的核对。`.pick_progress` 每条记录必须带当时的树 OID,与现场不符即无效。

### 门 0 — 解析源

```bash
gh pr view <N> --repo <源仓库> --json state,title,baseRefName,mergeCommit,mergedAt,commits,files,body
```

(仓库无 GitHub 时用其指令文件规定的等价查询。)

- **state != MERGED → 停下问用户**(headless → BLOCKED)。绝不自行 pick 未合并的 head。
- **revert / follow-up 检查**:`git log <源base ref> --oneline --grep='#<N>'`(mergedAt 之后)+ `gh pr list --repo <源仓库> --search "revert #<N>" --state all`。命中 revert → 必须问用户;命中 follow-up fix → 记入 PR body 并问是否连带 pick。
- **pick 对象判别算法**(不许凭感觉选):
  1. `git cat-file -p <mergeCommit>` 看 parent 数。**多 parent = 真 merge**:pick 对象是 `pull/<N>/head` 的各 commit(`git fetch <源远端> pull/<N>/head:pr-<N>-head`),按 commits 顺序逐个 pick,跳过其中的 merge commit,**绝不 `-m 1` pick mergeCommit**。
  2. 单 parent 且 commits 数 = 1:squash 或单 commit,pick mergeCommit。
  3. 单 parent 且 commits 数 > 1:可能是 rebase-merge(mergeCommit 只指向序列最后一个)。对比 `gh pr diff <N>` 与 `git show <mergeCommit>` 的 diff:一致 → squash,pick mergeCommit;不一致 → rebase-merge,逐个 pick head commits。
  4. base 非 master 的 PR,mergeCommit 可能不在一等历史/本地无对象:同样走 `pull/<N>/head`,以 `gh pr diff` 为权威 diff。
- **已落地检测**:pick 前查目标分支是否已有该变更——`git log <目标ref> --oneline --grep='#<N>'` + 对代表性 hunk 做 `git grep`;已存在 → 报告"无需 pick"成功结束,不建 worktree。
- 读 PR 描述与关联 issue(从 PR 元数据/正文链接解析,记录查过的 URL;没有关联 issue 就写明,不编造意图),记下**意图**——语义移植落地的是意图,不是文本。head commits 是 commit 事实,`gh pr diff` 是期望变更集;两者对不上 → 停下查原因,不硬选一边。

### 门 1 — 适用性预检(硬闸门)

**跨仓库时本门在目标仓库里执行**(先把源对象 fetch 进目标仓库,`<目标ref>` 才存在)。按**文件状态**分流检查(A=新增 / M=修改 / D=删除):

```bash
git diff-tree -r --first-parent --name-status <sha>   # 或逐 commit 累加
```

- **M/D 文件**:`git cat-file -e <目标ref>:"$f"` 必须存在;MISSING 的用门 4 三板斧找新家。
- **A(新增)文件**:目标分支上本来就不该存在,只检查其父目录/同级文件存在,不算 MISSING,不触发语义定位。
- **文件清单为空 = 取 diff 方式错了**(多半对 merge commit 跑了 show),回门 0 重取。禁止以空清单通过本门。
- **整个特性在目标分支不存在**(相关符号 `git grep` 全无,且不是"全是新增文件"造成的错觉):停下问用户,给三个选项,不擅自选:(a) 先整体 port 特性;(b) 基于既有 port/pick 分支 stack;(c) 语义移植到等价旧路径(manual backport)。

### 门 2 — worktree

- worktree **必须**建在路由表规定的 worktree 根下,分支与目录统一命名 `pick-<PR号>-<目标分支>`(多 PR 按号**数值升序** `pick-<PR1>-<PR2>-<目标分支>`)。
- **撞名处理**:目录已存在但没有 `.pick_progress`、或其记录的 PR/分支与本命令不符 → 视为他人工作区,**不删不用**,换名 `pick-...-r2` 并告知用户;记录相符 → 走断点续跑。
- 基点一律 `origin/<目标分支>`(先 fetch),本地同名分支可能陈旧。
- 执行仓库的 worktree 初始化纪律(doris:`hooks/setup_worktree.sh` + `ROOT_WORKSPACE_PATH` + 核对 `.worktree_initialized` 与 `thirdparty/installed` + submodule;起集群按仓库指令做端口偏移隔离)。
- 绝不在主工作区或别的 worktree 里切分支——它们通常是脏的。

### 门 3 — 机械 pick

```bash
git cherry-pick -x <sha>   # 按门 0 判定的清单逐个执行,先列出完整有序清单
```

- 逐个 pick;某个失败就停在失败的 sha 上进门 4,绝不自动跳过它继续后面的。
- 跨仓库(doris → internal-core)同样走 cherry-pick:internal-core 配有指向 apache/doris 的远端,先 fetch 把对象拿进来。
- **干净通过也不免审计**:仍须生成门 4 的 hunk 审计表(逐文件与源 diff 对照,逐字节一致的记 `Ported(verbatim)`),然后进门 5。干净只免去解冲突,不免验证。

### 门 4 — 冲突与语义梯

**先分类再动手**:内容冲突 / 路径缺失(deleted by us)/ rename 漂移。每个冲突文件先用两侧 `git log --oneline -- <path>` 弄清分叉原因。

语义定位三板斧(文件挪位、函数重构对不上时):
1. **目录级**:在源分支找引入新布局的 refactor commit,`git show <sha> -M -C --summary | grep rename` 读映射;或 `git log --follow -- <旧路径>`。
2. **符号级**:`git grep -n "<特征片段>" <目标ref>` + `git log -S'<片段>'` pickaxe 找等价落点。
3. **类/接口级**:源类名 ↔ 目标类名对照;API 变了就**保断言/保语义、换 API 重写**。

纪律:
- **双方保留**:保住 pick 的既定语义 + 目标分支所有不冲突的既有行为;两者语义不相容时**不许机械地都塞进去**(会造出不可能状态),停下问用户(headless → BLOCKED),绝不静默取舍。
- 绝不 `git cherry-pick --skip`;放弃任何 hunk 必须显式记录理由。
- **hunk 审计表(强制,粒度有定义)**:最小粒度 = 源 diff 的每个 `@@` 头一行,引用 `@@` 头原文,标 `Ported / Adapted / N-A(理由)`;仅当某文件落地后与源逐字节一致时,才允许汇总为一行 `Ported(verbatim)`。禁止"全部文件: Ported"式一行表。**N-A 的门槛**:只允许用于在目标分支上确凿过时/不适用的 hunk,必须附目标代码证据;承载行为的 hunk 不得仅因"解冲突麻烦"标 N-A。表随 PR 描述交付。
- **range-diff 复核**:交付物是差异条目摘录 + 逐条解释,不是"已跑过"的声明;跨仓库/路径漂移导致 range-diff 不可用时写明,以 hunk 表为准。
- 冲突规模失控(核心逻辑已被重写、机械合并不可信)→ 降级 manual backport:对照源 diff 手写等语义最小补丁,原 PR 测试一并移植作行为锚点。**溯源规范**:作者唯一时保留 `--author`;commit 正文加 `Backport-of: <完整 sha>` 与源 PR 链接,写明 manually adapted;**禁止伪造 cherry-pick `-x` 行**。

### 门 5 — 质量门

按序,前一步不绿不进下一步;**中途改了代码回 5.1 重来**(见总则)。

1. **格式与静态检查**:行级优先——`git clang-format`(用仓库要求的版本,doris 为 v16)对比 `origin/<目标分支>`,只格式化本 pick 的改动行;出现全文件噪声就 `git checkout -- <file>` 恢复后重做行级;仓库的全文件脚本仅用于本 PR **新增**的文件;若该仓库 CI 的格式检查要求全文件(现场核实),以 CI 规则为准并在 PR 里说明。仓库要求的其余静态门一并跑(doris:编译后对改动 C++ 跑 `run-clang-tidy.sh`;FE 改动的 checkstyle 随 `build.sh --fe` 验证),记录命令与退出码。
2. **编译**:先按路由表 source 该分支的构建环境(JDK/thirdparty 坑)。**路由表对目标分支无构建环境条目 = 视同未查**:先从该分支指令文件/CI 配置解析出要求、回写路由表,再开编。用仓库脚本全量编,`-j $(nproc)` 用满核。
3. **单测**:跑受影响 filter 的 UT;原 PR 自带的测试必须实际执行到——先 `--gtest_list_tests` 列出期望用例名,再核对**执行输出里的已运行用例数与名单**都包含它们(list 只证明能发现,不证明跑过;filter 跑了 0 个用例不算过)。sanitizer 标准 = **零新增** crash/leak:与 `origin/<目标分支>` 基线(同 filter)对照,基线已有的存量报告记录进 PR body,不算阻塞,但也**不得在本 PR 里顺手修**。
4. **回归判定规则**:
   - **反向锚点(优先级最高)**:源 PR diff 含 `regression-test/`(或等价回归目录)用例的,该用例必须一并 pick 并在目标分支实际执行通过——此时无论改动分类如何,**不得免跑**。
   - 必跑触发面:查询执行路径、存储格式、索引读写、FE plan/优化器/元数据/事务。命中 → 起端口隔离集群跑对应 suite。
   - 免跑必须附证据:逐文件列出 diff 路径并归类,全部落进白名单(注释、报错文案、纯 UT 文件、文档)才可免;任何一个文件归不进去即不得免跑。理由与清单写入 PR 描述。

### 门 6 — 交付

1. commit:标题按目标仓库/分支既有 pick 惯例(现场 `git log <目标ref> --oneline` 核对,路由表有记录);保留原作者 `--author`;保留 `-x` 溯源行;有适配则加 `Conflicts:` 段。
2. push:**推 fork,不直推 origin**。被拒时先 `gh pr list --repo <上游> --head <fork owner>:<分支>` 查该分支是否挂着 open PR:有 → 问用户是更新还是换分支名,确认后仅 `--force-with-lease`;无 → 可 `--force-with-lease` 覆盖废弃分支。**禁止裸 `-f`**。
3. PR:创建前先查重——`gh pr list --repo <上游> --head <fork owner>:<分支> --state all`;有同 head 的 open PR → 走更新而不是新开;有无关撞名 → 停下问。然后按"必用能力·发 PR"程序创建。body 必含:源 PR 链接、pick 的 commit(s)、hunk 审计表、UT/回归结果、sanitizer 基线对照(如有存量)、免跑理由与文件归类(如免跑)。
4. CI:按仓库惯例触发(doris 评论 `run buildall`),盯到绿。**失败先判归属**:在 `origin/<目标分支>` 基线上能复现的同一失败 = 存量,记录基线证据后视为非阻塞,**不得在本 PR 内修无关问题**;基线复现不了的必须修。同一失败重触发 CI 最多 2 次,仍红按 flaky 记录并问用户。无权触发 CI 或拿不到日志 → 如实报告"PR 已建、CI 未确认",**不许宣称绿**。本地绿 + CI 绿(扣除已记录存量)双门槛。

## 批量多目标

- 多个目标分支 = 多个 worktree,**串行**执行(编译独占机器)。
- 顺序:从与源分叉最小的分支开始;后续分支优先从**已适配好的 pick commit** 再 pick,减少重复解冲突;若反而更冲突,退回直接 pick 源对象。
- 已适配 commit 只是机械起点:**每个目标分支的 hunk 审计表都必须对照原始源 PR 重做**——前一分支的适配对本分支可能是错的,不适用的适配要剔除。

## 断点续跑

在 worktree 根维护 `.pick_progress`(建好后立即把它写进该 worktree 的 `git rev-parse --git-path info/exclude`,防误提交),每行固定 schema:

```
门N|tree_oid|UTC时间|命令|结果摘录     # tree_oid = git rev-parse HEAD^{tree}
```

- 每过一道门追加一行;门 5 各子步各记一行。
- 重跑同一命令:先探测半途状态——`CHERRY_PICK_HEAD` 存在(pick 解到一半)、rebase/merge 进行中、残留的构建进程——有则先处置这个,不许视而不见,也不许 `--abort` 别人的操作。然后逐行校验:**只认树 OID 与现场一致、且结果可复核(命令能重放或产物还在)的记录**;不符的行连同其后所有行作废,从第一个作废的门重跑。自述文字本身不构成证据。
- BLOCKED 行(headless 停机点)= 交互式重跑时的第一个问题。

## 红线

- 在主工作区或他人 worktree 里切分支 / 动文件
- `cherry-pick --skip`、静默丢 hunk、静默丢任何一侧改动
- 编译或 UT 没绿就 push / 提 PR;`push -f`(只许 `--force-with-lease`,且按门 6.2 先查 PR)
- 路由表没查、或目标分支条目空白就开编(分支环境坑会烧掉几小时)
- 凭记忆猜脚本参数、猜远端名、猜分支惯例;命令失败就回写路由表
