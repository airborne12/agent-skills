"""快照 diff → 事件；状态文件（snapshot.json / state.jsonl / lock）读写。"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CommentDigest:
    id: str
    author: str
    updated: str


@dataclass(frozen=True)
class IssueDigest:
    key: str
    status: str
    updated: str
    comments: tuple[CommentDigest, ...] = ()


@dataclass(frozen=True)
class Event:
    kind: str
    key: str
    detail: dict = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        raw = json.dumps([self.kind, self.key, self.detail], sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "kind": self.kind, "key": self.key, "detail": dict(self.detail)}


def digest_from_issue(issue: dict) -> IssueDigest:
    f = issue.get("fields", {})
    comments = tuple(
        CommentDigest(str(c["id"]), (c.get("author") or {}).get("name", "?"), c.get("updated", ""))
        for c in (f.get("comment") or {}).get("comments", [])
    )
    return IssueDigest(issue["key"], (f.get("status") or {}).get("name", ""), f.get("updated", ""), comments)


def _comment_events(key: str, prev: IssueDigest, curr: IssueDigest) -> list[Event]:
    before = {c.id: c for c in prev.comments}
    out = []
    for c in curr.comments:
        old = before.get(c.id)
        if old is None:
            out.append(Event("NEW_COMMENT", key, {"comment_id": c.id, "author": c.author, "edited": False, "updated": c.updated}))
        elif old.updated != c.updated:
            out.append(Event("NEW_COMMENT", key, {"comment_id": c.id, "author": c.author, "edited": True, "updated": c.updated}))
    return out


def diff_snapshots(prev: dict, curr: dict) -> tuple[Event, ...]:
    out: list[Event] = []
    for key in sorted(curr):
        if key not in prev:
            out.append(Event("NEW_ISSUE", key, {"status": curr[key].status, "updated": curr[key].updated}))
            continue
        p, c = prev[key], curr[key]
        if p.status != c.status:
            out.append(Event("STATUS_CHANGED", key, {"from": p.status, "to": c.status}))
        out.extend(_comment_events(key, p, c))
    for key in sorted(prev):
        if key not in curr:
            out.append(Event("DROPPED", key, {"last_status": prev[key].status}))
    return tuple(out)


# ---------- 状态文件 ----------

def load_snapshot(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # 损坏快照 = 无基线；调用方会提示重跑 baseline
    return {
        k: IssueDigest(v["key"], v["status"], v["updated"], tuple(CommentDigest(**c) for c in v.get("comments", [])))
        for k, v in raw.items()
    }


def save_snapshot(path: Path, snap: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: asdict(v) for k, v in snap.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def append_record(path: Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_records(path: Path) -> tuple[tuple[dict, ...], int]:
    """返回 (记录, 损坏行数)。损坏行跳过，不按空状态重放。"""
    path = Path(path)
    if not path.exists():
        return (), 0
    recs, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return tuple(recs), bad


def handled_event_ids(records: tuple[dict, ...]) -> frozenset:
    """只有 phase=RESULT 才算处理完；覆盖记录里的全部 event_ids（REFUSED/INTENT 不算）。"""
    out: set = set()
    for r in records:
        if r.get("phase") != "RESULT":
            continue
        out.update(r.get("event_ids") or ([r["event_id"]] if r.get("event_id") else []))
    return frozenset(out)


def dangling_intents(records: tuple[dict, ...]) -> tuple[dict, ...]:
    done = handled_event_ids(records)
    return tuple(r for r in records if r.get("phase") == "INTENT" and r.get("event_id") not in done)


# ---------- 锁 ----------

def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def lock_is_stale(content: str, now_iso: str, stale_seconds: int) -> bool:
    try:
        ts = _parse_iso(json.loads(content)["ts"])
    except (ValueError, KeyError, TypeError):
        return True
    return (_parse_iso(now_iso) - ts).total_seconds() > stale_seconds


LOCK_STALE_SECONDS = 7200  # 一轮最长 2 小时，超过视为遗留锁


def ensure_private_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def acquire_lock(state_dir: Path, pid: int, now_iso: Optional[str] = None,
                 stale_seconds: int = LOCK_STALE_SECONDS, name: str = "lock") -> bool:
    """O_EXCL 原子创建；陈旧锁先删再重试一次。"""
    state_dir = ensure_private_dir(state_dir)
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    lock = state_dir / name
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            content = lock.read_text(encoding="utf-8")
        except OSError:
            return False
        if not lock_is_stale(content, now_iso, stale_seconds):
            return False
        lock.unlink(missing_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"pid": pid, "ts": now_iso}))
    return True


def release_lock(state_dir: Path, pid: Optional[int] = None, name: str = "lock") -> bool:
    """给了 pid 就只释放自己的锁；不给 pid 视为管理员强制释放。"""
    lock = Path(state_dir) / name
    if not lock.exists():
        return True
    if pid is not None:
        try:
            owner = json.loads(lock.read_text(encoding="utf-8")).get("pid")
        except (ValueError, OSError):
            owner = None
        if owner != pid:
            return False
    lock.unlink(missing_ok=True)
    return True
