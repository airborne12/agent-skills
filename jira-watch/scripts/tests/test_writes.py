"""写操作守卫：评论构造/判重、流转白名单、两阶段记录。"""
from jw import writes


def test_build_comment_has_disclaimer_and_slot_marker():
    body = writes.build_comment("h2. 结论\n内容", slot="jw_abc123")
    assert body.startswith("{panel")
    assert "jira-watch" in body.splitlines()[0] or "jira-watch" in body
    assert "Jira-Watch-Slot: jw_abc123" in body
    assert body.rstrip().endswith("内容") or "内容" in body


def test_slot_id_is_deterministic():
    assert writes.slot_id("CIR-1", ("e1", "e2")) == writes.slot_id("CIR-1", ("e2", "e1"))
    assert writes.slot_id("CIR-1", ("e1",)) != writes.slot_id("CIR-2", ("e1",))
    assert writes.slot_id("CIR-1", ("e1",)).startswith("jw_")


def test_find_existing_slot_in_remote_comments():
    comments = [{"id": "1", "body": "hello"}, {"id": "2", "body": "x\nJira-Watch-Slot: jw_abc\ny"}]
    assert writes.find_existing_slot(comments, "jw_abc")["id"] == "2"
    assert writes.find_existing_slot(comments, "jw_zzz") is None


def test_transition_allowed_whitelist():
    assert writes.transition_allowed("处理中", allowed=("处理中",)) is True
    assert writes.transition_allowed("完成", allowed=("处理中",)) is False


def test_pick_transition_id_by_target_name():
    trans = [{"id": "21", "name": "处理中", "to": {"name": "处理中"}}, {"id": "41", "name": "完成", "to": {"name": "完成"}}]
    assert writes.pick_transition_id(trans, "处理中") == "21"
    assert writes.pick_transition_id(trans, "In Review") is None


def test_intent_and_result_records_shape():
    i = writes.intent_record(key="CIR-1", action="COMMENT", event_ids=("e1",), slot="jw_a", ts="t0", extra={"mode": "INTERACT"})
    assert i == {"ts": "t0", "key": "CIR-1", "type": "write", "action": "COMMENT", "phase": "INTENT",
                 "event_id": "e1", "event_ids": ["e1"], "slot": "jw_a", "mode": "INTERACT"}
    r = writes.result_record(i, ts="t1", evidence="comment id 123")
    assert r["phase"] == "RESULT" and r["evidence"] == "comment id 123" and r["ts"] == "t1"
    assert i["phase"] == "INTENT"  # 原记录不被修改


def test_strip_scores_from_public_text():
    text = "结论：需要 pick。C=0.8 S=0.9 P=1.0 总分=0.85\n证据：x"
    cleaned = writes.strip_scores(text)
    assert "C=" not in cleaned and "总分" not in cleaned and "证据：x" in cleaned
