"""面向人的文本渲染（pick 建议）。"""
from __future__ import annotations


def _hit_text(br: str, h: dict) -> str:
    tags = h.get("tags") or ()
    tag_txt = f"，含于 {', '.join(tags)}" if tags else "，尚无发布 tag 包含"
    return f"{br}({h['kind']}{tag_txt})"


def _base_lines(adv: dict) -> list:
    lines = []
    if adv.get("be_commits"):
        cv = "、".join(adv.get("commit_versions") or []) or "未在本地仓库找到"
        mismatch = "（与 Jira 标注不符！）" if adv.get("version_mismatch") else ""
        lines.append(f"- 描述中的 BE commit {', '.join(adv['be_commits'])} → 版本 {cv}{mismatch}")
    for repo, b in adv.get("base", {}).items():
        via = "BE commit" if b.get("source") == "be_commit" else "版本字段"
        evidence = b.get("subject") or b.get("ref") or b.get("series_hint", "?")
        lines.append(f"- {repo} 基线：{b.get('base_branch') or '无法解析'}（依据 {via}：{evidence}，置信度 {b.get('confidence')}）")
    return lines


def _member_text(m: dict) -> str:
    base = m.get("base") or "?"
    note = ""
    if m.get("state") == "CLOSED":
        note = "（已关闭未合入）"
    elif base.startswith("branch-hotfix-"):
        note = "（客户 hotfix 已验证）"
    return f"{m['repo']}#{m['number']}[{m['state']}→{base}]{note}"


def _family_lines(fam: dict) -> list:
    members = "、".join(_member_text(m) for m in fam["members"])
    lines = [f"- 修复族「{fam['core']}」成员：{members}"]
    if not fam.get("matrix"):
        lines.append("    （无本地克隆的仓库，未检查分支包含关系）")
    for repo, m in fam.get("matrix", {}).items():
        have = [_hit_text(br, h) for br, h in m.items() if h["kind"] != "missing"]
        miss = [br for br, h in m.items() if h["kind"] == "missing"]
        lines.append(f"    {repo} 已含：{', '.join(have) or '无'}；缺：{', '.join(miss) or '无'}")
    for repo, a in fam.get("advice", {}).items():
        if a.get("suggested_targets"):
            lines.append(f"    ⇒ {repo} 基线缺此修复，建议 pick 到 {', '.join(a['suggested_targets'])}")
        elif a.get("base_has_fix"):
            lines.append(f"    ⇒ {repo} 基线已含此修复")
    return lines


def render_pick_advice(adv: dict) -> str:
    lines = [f"issue {adv['issue']} 标注版本 {adv.get('version') or '未知'}"] + _base_lines(adv)
    for fam in adv.get("families", []):
        lines += _family_lines(fam)
    if any(v.get("ref_is_fallback") for v in adv.get("base", {}).values()):
        lines.append("- 注意：精确 tag 不在本地，基线按同系列最近 tag 推断；fetch 后复核")
    for h in adv.get("hotfix_branches", []):
        lines.append(f"- 该版本已有 hotfix 分支：{h}")
    return "\n".join(lines)
