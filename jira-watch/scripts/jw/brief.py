"""单轮简报渲染（Markdown）。"""
from __future__ import annotations


def _lines(items, fmt):
    return [fmt(x) for x in items] or ["（无）"]


def render_brief(r: dict) -> str:
    parts = [f"# jira-watch 单轮简报 {r.get('round_id', '')}（模式 {r.get('mode', 'OBSERVE')}）", ""]
    parts += [f"① 本轮增量：{r.get('events_total', 0)} 个事件", ""]
    parts += ["② 判定与证据："] + _lines(r.get("verdicts", []), lambda v: f"- {v['key']} [{v.get('category', '?')}] {v.get('verdict', '?')} — {v.get('evidence', '')}") + [""]
    parts += ["③ 已做动作："] + _lines(r.get("actions", []), lambda a: f"- {a['key']} {a['action']} ← {a.get('confirmation', '')}") + [""]
    parts += ["④ PENDING_USER："] + _lines(r.get("pending_user", []), lambda p: f"- {p['key']}：{p.get('why', '')}") + [""]
    parts += ["⑤ 能力缺口："] + _lines(r.get("gaps", []), lambda g: f"- {g}") + [""]
    parts += [f"⑥ 建议下轮间隔：{r.get('next_interval', '30m')}"]
    return "\n".join(parts)
