"""CLI 编排层的纯函数：issue 增强、事件派生、fetch 陈旧判断、round 汇总。"""
import json
from jw import cli, events


def _issue(key="CIR-10001", comments=(), summary="[渠道A][5.0.4][c] BE 挂掉", project="CIR", itype="故障", desc=""):
    return {
        "key": key,
        "fields": {
            "project": {"key": project}, "issuetype": {"name": itype}, "summary": summary,
            "status": {"name": "待办"}, "updated": "2026-09-02T14:51:45.000+0800", "labels": ["cloud"],
            "versions": [{"name": "cloud-5.0.4"}], "description": desc,
            "comment": {"comments": [
                {"id": str(i), "author": {"name": a, "displayName": a}, "created": "c", "updated": "u", "body": b}
                for i, (a, b) in enumerate(comments, start=1)
            ]},
        },
    }


BW = "AI-Analysis-Slot: slot_1\nh2. 首次 on-call triage 结论\n*判断：{{fail}}；根因置信度：{{high}}。*\n* CIR-10003 同栈\n* https://github.com/apache/doris/pull/63138"


def test_enrich_issue_collects_ai_ci_prs_refs_and_mentions():
    issue = _issue(comments=[("aibot", "正在分析该问题"), ("aibot", BW), ("bob", "和 CIR-10003 一致 [~alice] 看看")])
    e = cli.enrich_issue(issue, me="alice", bot_users=("aibot",), ci_bot_users=("cibot",))
    assert e["classification"]["category"] == "CUSTOMER_BUG"
    assert e["ai_analyses"][0]["comment_id"] == "2" and e["ai_analyses"][0]["judgment"] == "fail"
    assert [a["comment_id"] for a in e["ai_analyses"]] == ["2"]  # 占位评论不算
    assert e["pr_refs"] == [{"repo": "apache/doris", "number": 63138, "url": "https://github.com/apache/doris/pull/63138", "by": "aibot", "comment_id": "2"}]
    assert e["issue_refs"] == ["CIR-10003"]
    assert e["mentions_me"] == ["3"]
    assert e["versions"] == ["cloud-5.0.4"]
    assert e["ci_inspections"] == []


def test_derive_events_adds_semantic_kinds():
    issue = _issue(comments=[("aibot", BW), ("bob", "[~alice] 看看"), ("cibot", "[社区流水线每日巡检 2026-09-02 | test=-1 | latest=build:(id:5),id:6 | decision=confirmed-flaky]")])
    raw = (
        events.Event("NEW_ISSUE", "CIR-10001", {}),
        events.Event("NEW_COMMENT", "CIR-10001", {"comment_id": "1", "author": "aibot", "edited": False, "updated": "u"}),
        events.Event("NEW_COMMENT", "CIR-10001", {"comment_id": "2", "author": "bob", "edited": False, "updated": "u"}),
        events.Event("NEW_COMMENT", "CIR-10001", {"comment_id": "3", "author": "cibot", "edited": False, "updated": "u"}),
    )
    enriched = {"CIR-10001": cli.enrich_issue(issue, "alice", ("aibot",), ("cibot",))}
    derived = cli.derive_events(raw, enriched)
    kinds = [(d["kind"], d.get("detail", {}).get("comment_id")) for d in derived]
    assert ("AI_ANALYSIS_READY", "1") in kinds
    assert ("MENTIONED_ME", "2") in kinds
    assert ("CI_INSPECTION", "3") in kinds
    assert ("NEW_ISSUE", None) in kinds
    assert all("event_id" in d for d in derived)


def test_fetch_needed_by_age():
    assert cli.fetch_needed(fetch_head_mtime=0, now=10 * 3600, stale_hours=6) is True
    assert cli.fetch_needed(fetch_head_mtime=8 * 3600, now=10 * 3600, stale_hours=6) is False
    assert cli.fetch_needed(fetch_head_mtime=None, now=1, stale_hours=6) is True


def test_round_id_and_idempotency_key():
    rid = cli.round_id(now_iso="2026-09-02T08:00:00Z")
    assert rid == "2026-09-02T08:00:00Z"
    assert cli.idem_key(rid) == "jira-watch-2026-09-02T08:00:00Z"


def test_summarize_pick_advice_text_mentions_missing_targets():
    adv = {
        "issue": "CIR-10001", "version": "cloud-5.0.4",
        "base": {"example-org/internal-core": {"base_branch": "branch-internal-doris-4.0", "confidence": "high", "ref": "tag-internal-cloud-5.0.0"}},
        "families": [{"core": "[fix] x", "members": [{"repo": "apache/doris", "number": 63138, "state": "MERGED", "base": "master"}],
                 "matrix": {"apache/doris": {"master": {"kind": "direct"}, "branch-4.1": {"kind": "picked", "sha": "9f98"}, "branch-4.0": {"kind": "missing"}},
                            "example-org/internal-core": {"branch-internal-doris-4.0": {"kind": "missing"}, "branch-internal-doris-4.1": {"kind": "missing"}}},
                 "advice": {"example-org/internal-core": {"base_has_fix": False, "suggested_targets": ["branch-internal-doris-4.0"]}}}],
    }
    text = cli.render_pick_advice(adv)
    assert "branch-internal-doris-4.0" in text and "缺" in text
    assert "master" in text and "branch-4.1" in text


def test_enterprise_version_from_commit_versions():
    assert cli.enterprise_version(["cloud-26.0.4", "enterprise-4.0.6"]) == "4.0.6"
    assert cli.enterprise_version(["cloud-26.0.4"]) is None
    assert cli.enterprise_version([]) is None
