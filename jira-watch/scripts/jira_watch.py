#!/usr/bin/env python3
"""jira-watch CLI 入口。所有子命令输出 JSON（pick-advice 另带 text）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jw import brief, cli, config, events  # noqa: E402

LOCKED_COMMANDS = ("events", "comment", "transition", "attachments")  # 互斥执行，防止并发写状态


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jira_watch.py")
    p.add_argument("--mode", choices=config.MODES, help="覆盖配置中的模式（INTERACT 必须由用户明示授权）")
    p.add_argument("--conf", default="~/.jira-watch.conf")
    p.add_argument("--debug", action="store_true", help="异常时打印堆栈")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("config")
    for name in ("poll", "baseline"):
        sub.add_parser(name).add_argument("--jql")
    sp = sub.add_parser("events"); sp.add_argument("--jql"); sp.add_argument("--dry", action="store_true", help="不更新快照/待处理事件"); sp.add_argument("--force", default="", help="逗号分隔的 KEY，强制作为事件重新处理")
    sub.add_parser("issue").add_argument("key")
    sp = sub.add_parser("resolve-version"); sp.add_argument("version"); sp.add_argument("--no-fetch", action="store_true")
    sp = sub.add_parser("pr-chain"); sp.add_argument("refs", nargs="+"); sp.add_argument("--no-fetch", action="store_true")
    sp = sub.add_parser("pick-advice"); sp.add_argument("key"); sp.add_argument("--no-fetch", action="store_true"); sp.add_argument("--hops", type=int, default=1)
    sp = sub.add_parser("comment"); sp.add_argument("key"); sp.add_argument("--body-file", required=True); sp.add_argument("--event-ids", default=""); sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("transition"); sp.add_argument("key"); sp.add_argument("--to", required=True); sp.add_argument("--event-ids", default=""); sp.add_argument("--comment"); sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("notify"); sp.add_argument("--file", required=True); sp.add_argument("--round-id", required=True); sp.add_argument("--dry-run", action="store_true")
    sub.add_parser("record").add_argument("--json", required=True)
    sub.add_parser("lock"); sub.add_parser("unlock").add_argument("--force", action="store_true")
    sub.add_parser("brief").add_argument("--file", required=True)
    sp = sub.add_parser("attachments"); sp.add_argument("key"); sp.add_argument("--dir")
    return p


def _ids(s: str) -> tuple:
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _config_view(cfg: config.Config) -> dict:
    ages = {}
    for repo, path in cfg.repo_paths.items():
        fh = Path(path) / ".git" / "FETCH_HEAD"
        ages[repo] = round((datetime.now().timestamp() - fh.stat().st_mtime) / 3600, 1) if fh.exists() else None
    return {**cfg.__dict__, "jira_token": "***", "fetch_head_age_hours": ages}


def _dispatch(a, ctx: cli.Ctx) -> dict:
    handlers = {
        "poll": lambda: cli.cmd_poll(ctx, a.jql),
        "baseline": lambda: cli.cmd_baseline(ctx, a.jql),
        "events": lambda: cli.cmd_events(ctx, a.jql, a.dry, _ids(a.force)),
        "issue": lambda: cli.cmd_issue(ctx, a.key),
        "resolve-version": lambda: cli.cmd_resolve_version(ctx, a.version, a.no_fetch),
        "pr-chain": lambda: cli.cmd_pr_chain(ctx, a.refs, a.no_fetch),
        "pick-advice": lambda: cli.cmd_pick_advice(ctx, a.key, a.no_fetch, a.hops),
        "comment": lambda: cli.cmd_comment(ctx, a.key, a.body_file, _ids(a.event_ids), a.dry_run),
        "transition": lambda: cli.cmd_transition(ctx, a.key, a.to, _ids(a.event_ids), a.dry_run, a.comment),
        "notify": lambda: cli.cmd_notify(ctx, a.file, a.round_id, a.dry_run),
        "attachments": lambda: cli.cmd_attachments(ctx, a.key, a.dir),
        "record": lambda: _record(ctx, a.json),
        "lock": lambda: {"locked": events.acquire_lock(ctx.state, os.getpid())},
        "unlock": lambda: {"unlocked": events.release_lock(ctx.state, None if a.force else os.getpid())},
    }
    return handlers[a.cmd]()


def _record(ctx: cli.Ctx, raw: str) -> dict:
    rec = json.loads(raw)
    if rec.get("type") == "write":
        return {"error": "record 不允许伪造 type=write 的审计记录（写动作只能由 comment/transition 产生）"}
    full = {**rec, "ts": rec.get("ts") or cli.now_iso()}
    ctx.record(full)
    return {"recorded": full}


def _run_locked(a, ctx: cli.Ctx) -> dict:
    if a.cmd not in LOCKED_COMMANDS:
        return _dispatch(a, ctx)
    if not events.acquire_lock(ctx.state, os.getpid(), stale_seconds=cli.OP_LOCK_STALE_S, name="op.lock"):
        return {"error": "另一个 jira-watch 命令正在运行（op.lock 被占用）；稍后重试"}
    try:
        return _dispatch(a, ctx)
    finally:
        events.release_lock(ctx.state, os.getpid(), name="op.lock")


def main(argv=None) -> int:
    a = _parser().parse_args(argv)
    cfg = config.load_config(watch_conf=a.conf)
    if a.cmd == "config":
        print(json.dumps(_config_view(cfg), ensure_ascii=False, indent=1)); return 0
    if a.cmd == "brief":
        print(brief.render_brief(json.loads(Path(a.file).read_text(encoding="utf-8")))); return 0
    out = _run_locked(a, cli.Ctx(cfg, mode=a.mode))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not (isinstance(out, dict) and out.get("error")) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 顶层兜底：结构化错误；--debug 或 errors.log 里看堆栈
        if "--debug" in sys.argv:
            traceback.print_exc()
        try:
            log = Path(os.path.expanduser("~/.local/state/jira-watch")); log.mkdir(parents=True, exist_ok=True)
            with (log / "errors.log").open("a", encoding="utf-8") as fh:
                fh.write(f"{cli.now_iso()} {' '.join(sys.argv[1:])}\n{traceback.format_exc()}\n")
        except OSError:
            pass
        print(json.dumps({"error": cli.redact(f"{type(e).__name__}: {e}")}, ensure_ascii=False))
        sys.exit(1)
