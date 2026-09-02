"""配置：~/.jira.conf（凭据）+ ~/.jira-watch.conf（技能参数），环境变量可覆盖。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_LINE = re.compile(r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^#\s]*))\s*(?:#.*)?$""")
MODES = ("OBSERVE", "INTERACT")
INTERNAL_REPO = "example-org/internal-core"  # 与 apache/doris 互相 pick 的内部仓库标识
DEFAULT_JQL = "assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC"


@dataclass(frozen=True)
class Config:
    jira_url: str
    jira_user: str
    jira_token: str
    mode: str
    jql: str
    state_dir: str
    bot_users: tuple
    ci_bot_users: tuple
    allowed_transitions: tuple
    lark_open_id: str
    repo_paths: dict          # {"apache/doris": path, "example-org/internal-core": path}
    release_branches: dict    # {"apache/doris": (...), ...}
    fetch_stale_hours: int
    projects: tuple = ("CIR", "DORIS", "CORE", "OPENSOURCE")
    pr_owners: tuple = ("apache", "internal")
    mode_source: str = "conf"


def parse_shell_conf(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m or line.strip().startswith("#"):
            continue
        k, dq, sq, bare = m.groups()
        out[k] = dq if dq is not None else (sq if sq is not None else bare)
    return out


def _tuple(v: str, default: tuple) -> tuple:
    return tuple(x.strip() for x in v.split(",") if x.strip()) if v else default


def build_config(creds: dict, opts: dict) -> Config:
    missing = [k for k in ("JIRA_URL", "JIRA_USER", "JIRA_TOKEN") if not creds.get(k)]
    if missing:
        raise ValueError(f"~/.jira.conf 缺少 {', '.join(missing)}")
    mode = (opts.get("JIRA_WATCH_MODE") or "OBSERVE").upper()
    if mode not in MODES:
        raise ValueError(f"非法 mode {mode!r}，只允许 {MODES}")
    doris_branches = _tuple(opts.get("JIRA_WATCH_DORIS_BRANCHES", ""), ("master", "branch-4.1", "branch-4.0", "branch-3.1", "branch-3.0", "branch-2.1"))
    core_branches = _tuple(opts.get("JIRA_WATCH_INTERNAL_BRANCHES", ""), ("internal-cloud-4.0", "branch-internal-doris-4.1", "branch-internal-doris-4.0", "branch-internal-doris-3.1", "branch-internal-doris-3.0", "branch-internal-doris-2.1"))
    return Config(
        jira_url=creds["JIRA_URL"].rstrip("/"),
        jira_user=creds["JIRA_USER"],
        jira_token=creds["JIRA_TOKEN"],
        mode=mode,
        jql=opts.get("JIRA_WATCH_JQL") or DEFAULT_JQL,
        state_dir=opts.get("JIRA_WATCH_STATE_DIR") or os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "jira-watch"),
        bot_users=_tuple(opts.get("JIRA_WATCH_BOT_USERS", ""), ("aibot",)),
        ci_bot_users=_tuple(opts.get("JIRA_WATCH_CI_BOT_USERS", ""), ("cibot",)),
        allowed_transitions=_tuple(opts.get("JIRA_WATCH_ALLOWED_TRANSITIONS", ""), ("处理中",)),
        lark_open_id=opts.get("JIRA_WATCH_LARK_OPEN_ID", ""),
        repo_paths={k: v for k, v in (("apache/doris", opts.get("JIRA_WATCH_REPO_DORIS", "")), (INTERNAL_REPO, opts.get("JIRA_WATCH_REPO_INTERNAL", ""))) if v},
        release_branches={"apache/doris": doris_branches, INTERNAL_REPO: core_branches},
        fetch_stale_hours=int(opts.get("JIRA_WATCH_FETCH_STALE_HOURS") or 6),
        projects=_tuple(opts.get("JIRA_WATCH_PROJECTS", ""), ("CIR", "DORIS", "CORE", "OPENSOURCE")),
        pr_owners=_tuple(opts.get("JIRA_WATCH_PR_OWNERS", ""), ("apache", "internal")),
        mode_source="env" if opts.get("_MODE_FROM_ENV") else "conf",
    )


def load_config(jira_conf: str = "~/.jira.conf", watch_conf: str = "~/.jira-watch.conf") -> Config:
    creds = parse_shell_conf(Path(os.path.expanduser(jira_conf)).read_text(encoding="utf-8"))
    wpath = Path(os.path.expanduser(watch_conf))
    opts = parse_shell_conf(wpath.read_text(encoding="utf-8")) if wpath.exists() else {}
    env = {k: v for k, v in os.environ.items() if k.startswith("JIRA_WATCH_")}
    marker = {"_MODE_FROM_ENV": "1"} if "JIRA_WATCH_MODE" in env else {}
    return build_config(creds, {**opts, **env, **marker})
