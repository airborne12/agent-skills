"""副作用封装：subprocess（带超时与兜底）、脱敏、附件名守卫、运行上下文 Ctx。"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from jw import config, events, jira_api

GIT_TIMEOUT_S = 180
SH_TIMEOUT_S = 120
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}  # 禁止交互式凭据提示导致挂起
_SECRET = re.compile(r"(https?://)[^/@\s]+@")


def redact(text: str) -> str:
    """去掉 URL 里的 user:token@ 片段，避免凭据进入输出与状态文件。"""
    return _SECRET.sub(r"\1<redacted>@", text or "")


def _run(argv: list, cwd: Optional[str], timeout: int, env: Optional[dict] = None) -> tuple:
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env={**os.environ, **(env or {})})
    except FileNotFoundError as e:
        return 127, f"命令不存在或工作目录无效：{e}"
    except subprocess.TimeoutExpired:
        return 124, f"超时 {timeout}s：{' '.join(argv[:3])}"
    return p.returncode, p.stdout if p.returncode == 0 else (p.stdout + p.stderr)


def git_run(args: list, cwd: str) -> tuple:
    return _run(["git", *args], cwd, GIT_TIMEOUT_S, _GIT_ENV)


def sh_run(args: list) -> tuple:
    return _run(args, None, SH_TIMEOUT_S)


def safe_attachment_name(raw: str) -> str:
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    if not name or name in (".", ".."):
        raise ValueError(f"非法附件名 {raw!r}")
    return name


def attachment_url_allowed(url: str, jira_url: str) -> bool:
    return url.startswith(jira_url.rstrip("/") + "/")


def fetch_needed(fetch_head_mtime: Optional[float], now: float, stale_hours: int) -> bool:
    return fetch_head_mtime is None or (now - fetch_head_mtime) > stale_hours * 3600


class Ctx:
    """一轮运行的共享上下文：配置、Jira 客户端、git/sh 执行器、状态目录、能力缺口。"""

    _CACHEABLE = ("log", "rev-list", "merge-base", "tag", "rev-parse", "branch")

    def __init__(self, cfg: config.Config, client=None, git: Callable = git_run, sh: Callable = sh_run,
                 mode: Optional[str] = None):
        self.cfg = cfg
        self.mode = (mode or cfg.mode).upper()
        self.mode_source = "cli" if mode else cfg.mode_source
        self.client = client or jira_api.JiraClient(cfg.jira_url, cfg.jira_token)
        self._git, self.sh = git, sh
        self.state = events.ensure_private_dir(Path(cfg.state_dir))
        self.gaps: list = []
        self._fetched: set = set()
        self._git_cache: dict = {}

    # ---- 路径 ----
    @property
    def snapshot_path(self): return self.state / "snapshot.json"
    @property
    def records_path(self): return self.state / "state.jsonl"
    @property
    def pending_path(self): return self.state / "pending_events.json"
    def issue_cache(self, key): return self.state / "issues" / f"{key}.json"

    # ---- 副作用 ----
    def git(self, args: list, cwd: str) -> tuple:
        """只读 git 命令在本进程内做 memo（同族成员会重复查同样的 branch × core）。"""
        key = (tuple(args), cwd)
        if args and args[0] in self._CACHEABLE:
            if key not in self._git_cache:
                self._git_cache[key] = self._git(args, cwd)
            return self._git_cache[key]
        return self._git(args, cwd)

    def add_gap(self, text: str) -> None:
        t = redact(text)
        if t not in self.gaps:
            self.gaps.append(t)

    def record(self, rec: dict) -> None:
        clean = {**rec, "evidence": redact(rec["evidence"])} if isinstance(rec.get("evidence"), str) else dict(rec)
        events.append_record(self.records_path, clean)

    def cache_issue(self, enriched: dict) -> dict:
        p = self.issue_cache(enriched["key"])
        events.ensure_private_dir(p.parent)
        p.write_text(json.dumps(enriched, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(p, 0o600)
        return enriched

    def ensure_fresh(self, repo: str, no_fetch: bool) -> None:
        path = self.cfg.repo_paths.get(repo)
        if not path:
            self.add_gap(f"{repo} 未配置本地克隆路径（JIRA_WATCH_REPO_*）")
            return
        if no_fetch or repo in self._fetched:
            return
        self._fetched.add(repo)
        fh = Path(path) / ".git" / "FETCH_HEAD"
        mtime = fh.stat().st_mtime if fh.exists() else None
        if not fetch_needed(mtime, datetime.now().timestamp(), self.cfg.fetch_stale_hours):
            return
        rc, out = self._git(["fetch", "origin", "--prune", "--quiet"], path)
        if rc != 0:
            self.add_gap(f"{repo} git fetch 失败：{out.strip()[:200]}")
