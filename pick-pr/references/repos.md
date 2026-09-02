# Pick 路由表(快照,以现场为准;回写须附验证命令与输出,写不了就出补丁建议)

本文件是**本机 host profile**(本机（示例）):换机器/换账号时逐项现场核实重建,绝不套用这里的绝对路径与 fork 账号。
最后核实:2026-08-31。所有远端名/分支都要在执行时用 `git remote -v` / `git branch -r` 复核。

## apache/doris

| 项 | 值 |
|---|---|
| 本地主仓库 | `/path/to/doris`(常年脏,勿动) |
| worktree 根 | `/path/to/doris-worktrees/`;disk1 空间紧张时用 `/path/to/alt-disk/doris-wt/` |
| 远端 | `origin` = apache/doris;`jk` = <your-fork-owner>/apache-doris(fork,push 走这里) |
| 仓库指令 | 根目录 `AGENTS.md`(构建/测试/格式化/worktree 初始化全在里面,现场解析) |
| worktree 初始化 | `AGENTS.md` 规定:`ROOT_WORKSPACE_PATH=<主仓库> hooks/setup_worktree.sh`,核对 `.worktree_initialized` + `thirdparty/installed` + submodule;起集群需端口偏移 |
| 目标分支族 | `branch-2.1` / `branch-3.0` / `branch-3.1` / `branch-4.0` / `branch-4.1` 及点版本分支 |
| pick 标题惯例 | `branch-3.0: <原标题> #<PR号>`(以 `git log <目标ref> --oneline` 现场核对为准) |
| PR | 从 fork 发起:`gh pr create --repo apache/doris --base <目标分支> --head <your-fork-owner>:<分支>`,模板 `.github/PULL_REQUEST_TEMPLATE.md`;CI 靠 PR 评论 `run buildall`,机器人评审靠 PR 评论 `/review`;TeamCity 用 `~/.claude/skills/teamcity/teamcity.sh`(纯 bash,凭 `~/.teamcity.conf`,任何 agent 可直接调用)或 `gh pr checks` |

### 分支构建环境坑(不查就编 = 烧几小时)

- **branch-4.0**:必须用 **Arrow 17 的 thirdparty** + `/path/to/jdk-17.0.16`,否则编译/链接必挂。
- **branch-4.1**:`thirdparty/installed → /path/to/thirdparty/installed-master` 软链(Arrow 24)+ jdk-17.0.16 即可(验证:worktree pick-66877-branch-4.1 以此配置产出完整 output/ 与 be/build_ASAN;其 installed 软链与 arrow config.h ARROW_VERSION_MAJOR=24 实测于 2026-08-31)。worktree 初始化:branch-4.1 无 `hooks/setup_worktree.sh` 也无 AGENTS.md,手工等价三步 = 拷 custom_env.sh + 软链 thirdparty/installed + touch `.worktree_initialized`;build.sh 用分支自带的;子模块在 `contrib/`(clucene/apache-orc/faiss)。
- BE UT 若报 ORC protobuf `port_def.inc not found`:补 `be/thirdparty/installed/include` 软链。
- 起服务前 `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy`;判存活用 `pgrep -x doris_be` / `comm=java`,别用 `pgrep -f`。

## internal-core

| 项 | 值 |
|---|---|
| 本地主仓库 | `/path/to/internal-core`(常年脏,勿动) |
| worktree 根 | `/path/to/internal-core-worktrees/` |
| 远端 | `origin` = example-org/internal-core;`jk` = <your-fork-owner>/internal-core(fork,push 走这里);`apache` = apache/doris(**跨仓库 pick 的关键**:先 `git fetch apache <ref>` 把 doris commit 对象拿进来再 cherry-pick);`jkdoris` = <your-fork-owner>/apache-doris |
| 仓库指令 | 根目录**无** AGENTS.md/CLAUDE.md;有 `.claude/skills/code-review`、`.claude/commands/doris-init.md`(纯 markdown,任何 agent 可直接读);构建同样走 `./build.sh`,惯例大体沿用 doris,拿不准时对照 doris-clean 的 AGENTS.md |
| 目标分支族 | 默认分支 `internal-cloud-4.0`;`branch-internal-doris-3.1 / -4.0 / -4.1`;hotfix:`branch-hotfix-internal-cloud-26.x.y[-客户名]` |
| pick 分支/标题惯例 | 分支 `pick-<PR>-<目标分支>`;标题 `<目标分支>: <原标题> (#<原PR号>)`;PR 全部从 fork 发起(实测近期 PR 均 cross-repository),`gh pr create --repo example-org/internal-core --head <your-fork-owner>:<分支>`;body 按 `.github/PULL_REQUEST_TEMPLATE.md` |

## 通用

- gh 登录账号为 airborne12(repo scope)——这是快照,执行前仍以 `gh auth status` 现场核实为准(尤其换运行时/换沙箱时凭据可能不在)。
- 机器 多核,编译一律 `-j $(nproc)`。
- 用户 fork 是 airborne12/**apache-doris**(注意不是 airborne12/doris,那是别人项目的 fork)。
