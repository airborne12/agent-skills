"""快照 diff → 事件 的纯函数测试，以及状态文件读写。"""
import json
from jw import events


def _digest(key, status="待办", updated="2026-09-02T10:00:00+0800", comments=()):
    return events.IssueDigest(key=key, status=status, updated=updated, comments=tuple(comments))


def test_new_issue_event():
    prev = {}
    curr = {"CIR-1": _digest("CIR-1")}
    evs = events.diff_snapshots(prev, curr)
    assert [(e.kind, e.key) for e in evs] == [("NEW_ISSUE", "CIR-1")]


def test_status_change_event():
    prev = {"CIR-1": _digest("CIR-1", status="待办")}
    curr = {"CIR-1": _digest("CIR-1", status="处理中")}
    evs = events.diff_snapshots(prev, curr)
    assert evs[0].kind == "STATUS_CHANGED"
    assert evs[0].detail == {"from": "待办", "to": "处理中"}


def test_new_and_edited_comment_events():
    c1 = events.CommentDigest(id="100", author="aibot", updated="t1")
    c1_edited = events.CommentDigest(id="100", author="aibot", updated="t2")
    c2 = events.CommentDigest(id="101", author="bob", updated="t1")
    prev = {"CIR-1": _digest("CIR-1", comments=[c1])}
    curr = {"CIR-1": _digest("CIR-1", comments=[c1_edited, c2])}
    evs = events.diff_snapshots(prev, curr)
    kinds = [(e.kind, e.detail.get("comment_id"), e.detail.get("edited")) for e in evs]
    assert ("NEW_COMMENT", "100", True) in kinds
    assert ("NEW_COMMENT", "101", False) in kinds


def test_dropped_issue_event_when_no_longer_matching():
    prev = {"CIR-1": _digest("CIR-1")}
    evs = events.diff_snapshots(prev, {})
    assert [(e.kind, e.key) for e in evs] == [("DROPPED", "CIR-1")]


def test_no_events_when_unchanged():
    d = _digest("CIR-1", comments=[events.CommentDigest("1", "a", "t")])
    assert events.diff_snapshots({"CIR-1": d}, {"CIR-1": d}) == ()


def test_event_id_is_stable_and_unique():
    e1 = events.Event(kind="NEW_COMMENT", key="CIR-1", detail={"comment_id": "100", "edited": False, "updated": "t1"})
    e2 = events.Event(kind="NEW_COMMENT", key="CIR-1", detail={"comment_id": "100", "edited": True, "updated": "t2"})
    assert e1.event_id != e2.event_id
    assert e1.event_id == events.Event(kind="NEW_COMMENT", key="CIR-1", detail={"comment_id": "100", "edited": False, "updated": "t1"}).event_id


def test_digest_from_issue_json():
    issue = {
        "key": "CIR-1",
        "fields": {
            "status": {"name": "待办"},
            "updated": "2026-09-02T10:00:00.000+0800",
            "comment": {"comments": [{"id": "5", "author": {"name": "aibot"}, "updated": "u1", "body": "x"}]},
        },
    }
    d = events.digest_from_issue(issue)
    assert d.key == "CIR-1" and d.status == "待办"
    assert d.comments == (events.CommentDigest("5", "aibot", "u1"),)


def test_snapshot_roundtrip(tmp_path):
    p = tmp_path / "snapshot.json"
    snap = {"CIR-1": _digest("CIR-1", comments=[events.CommentDigest("1", "a", "t")])}
    events.save_snapshot(p, snap)
    assert events.load_snapshot(p) == snap


def test_load_snapshot_missing_file_is_empty(tmp_path):
    assert events.load_snapshot(tmp_path / "nope.json") == {}


def test_append_and_read_records_skips_corrupt_lines(tmp_path):
    p = tmp_path / "state.jsonl"
    events.append_record(p, {"a": 1})
    p.open("a", encoding="utf-8").write("{not json\n")
    events.append_record(p, {"b": 2})
    recs, bad = events.read_records(p)
    assert recs == ({"a": 1}, {"b": 2})
    assert bad == 1


def test_handled_event_ids_from_records():
    recs = ({"phase": "RESULT", "event_id": "e1"}, {"phase": "INTENT", "event_id": "e2"}, {"phase": "RESULT"})
    assert events.handled_event_ids(recs) == frozenset({"e1"})
    assert events.dangling_intents(recs) == ({"phase": "INTENT", "event_id": "e2"},)


def test_lock_stale_detection():
    assert events.lock_is_stale('{"pid": 1, "ts": "2026-09-02T00:00:00Z"}', now_iso="2026-09-02T03:00:00Z", stale_seconds=7200) is True
    assert events.lock_is_stale('{"pid": 1, "ts": "2026-09-02T02:30:00Z"}', now_iso="2026-09-02T03:00:00Z", stale_seconds=7200) is False
    assert events.lock_is_stale("garbage", now_iso="2026-09-02T03:00:00Z", stale_seconds=7200) is True


def test_acquire_and_release_lock(tmp_path):
    assert events.acquire_lock(tmp_path, pid=1, now_iso="2026-09-02T03:00:00Z") is True
    assert events.acquire_lock(tmp_path, pid=2, now_iso="2026-09-02T03:00:01Z") is False
    events.release_lock(tmp_path)
    assert events.acquire_lock(tmp_path, pid=2, now_iso="2026-09-02T03:00:02Z") is True
