"""对 Jira 的写操作守卫：评论构造/判重、流转白名单、两阶段记录、公开文本去评分。"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

DISCLAIMER = "{panel:bgColor=#f4f5f7}本评论由 jira-watch（AI 值班助手，操作人 {operator}）自动生成，作为对既有 AI 分析的校验与补充；请以人工复核结论为准。{panel}"
SLOT_PREFIX = "Jira-Watch-Slot: "
_SCORE_LINE = re.compile(r"^.*(?:归一化总分|总分\s*=|(?<![A-Za-z0-9_])[CSP]\s*=\s*\d+(?:\.\d+)?).*$")


def slot_id(key: str, event_ids: tuple) -> str:
    raw = key + "|" + "|".join(sorted(event_ids))
    return "jw_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_comment(body: str, slot: str, operator: str = "值班") -> str:
    return f"{DISCLAIMER.replace('{operator}', operator)}\n\n{body.rstrip()}\n\n{SLOT_PREFIX}{slot}"


def find_existing_slot(comments: list, slot: str) -> Optional[dict]:
    marker = f"{SLOT_PREFIX}{slot}"
    return next((c for c in comments if marker in (c.get("body") or "")), None)


def transition_allowed(target: str, allowed: tuple) -> bool:
    return target in allowed


def pick_transition_id(transitions: list, target: str) -> Optional[str]:
    for t in transitions:
        if (t.get("to") or {}).get("name") == target or t.get("name") == target:
            return str(t["id"])
    return None


def intent_record(key: str, action: str, event_ids: tuple, slot: Optional[str], ts: str, extra: Optional[dict] = None) -> dict:
    base = {"ts": ts, "key": key, "type": "write", "action": action, "phase": "INTENT",
            "event_id": event_ids[0] if event_ids else None, "event_ids": list(event_ids), "slot": slot}
    return {**base, **(extra or {})}


def result_record(intent: dict, ts: str, evidence: str) -> dict:
    return {**intent, "ts": ts, "phase": "RESULT", "evidence": evidence}


def strip_scores(text: str) -> str:
    """整行剔除含内部评分的行（不留 '0'/'00' 残渣），其余行（含空行）原样保留。"""
    return "\n".join(l for l in text.splitlines() if not _SCORE_LINE.fullmatch(l))
