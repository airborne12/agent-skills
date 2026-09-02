# jira-watch

监听分配给自己的 Jira issue，对每轮增量做受控自动处置：校验 AI 值班机器人的分析、追出修复 PR 在 apache/doris 与内部仓库各分支/发布 tag 的落地情况、给出基线分支与 pick 建议，按授权回写评论与状态，并把单轮简报推到飞书私聊。

## 安装

```bash
cp -r jira-watch ~/.claude/skills/        # 或 ~/.agents/skills/ 再软链
cp jira-watch/jira-watch.conf.example ~/.jira-watch.conf   # 按注释填写
python3 -m pip install --user requests pytest
```

依赖：`~/.jira.conf`（见 `jira` 技能）、`gh` 已登录、apache/doris 与内部仓库的本地克隆、可选的 `lark-cli`（飞书通知）与 `teamcity` 技能。

## 使用

```bash
S=~/.claude/skills/jira-watch/scripts/jira_watch.py
python3 $S config                      # 检查配置、克隆新鲜度
python3 $S baseline                    # 首轮只建快照，不把存量当事件
python3 $S events                      # 之后每轮：增量事件 + 增强后的 issue
python3 $S pick-advice CIR-10001       # 修复族 × 分支矩阵 + 基线 + pick 建议
python3 $S comment CIR-10001 --body-file draft.txt --event-ids e1 --dry-run
python3 --mode INTERACT $S transition CIR-10001 --to 处理中   # 仅在用户明示授权时
```

持续监听由外层调度：Claude Code 里 `/loop 30m /jira-watch`，或 cron 跑 `claude -p "/jira-watch"`。技能本身不建计划任务。

## 安全模型

- `OBSERVE`（默认）只读取证与本地落账；`INTERACT` 才允许评论与白名单流转，且只能通过 `--mode INTERACT` 或环境变量显式开启，账本会记录来源。
- 评论自动带免责前缀和 `Jira-Watch-Slot` 判重标记；远端写动作两阶段记录（INTENT → RESULT）。
- 没落 RESULT 的事件下一轮会原样再来；`record` 不允许伪造写动作审计。
- 输出与状态文件会剥离 URL 里的凭据；状态目录 0700。

## 测试

```bash
cd scripts && python3 -m pytest -q
```

代码中的内部仓库名、分支与 tag 前缀（`internal-*`）是占位示例，按你的仓库惯例修改 `jw/config.py`、`jw/prchain.py`、`jw/versions.py` 里的常量或配置项。
