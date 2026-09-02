"""副作用层命令：用假 Jira 客户端 + 假 git/sh 驱动 Ctx。"""
import json
from pathlib import Path
from jw import cli, config, events


class FakeClient:
    def __init__(self, issues=None, comments=None, transitions=None):
        self.issues = issues or []
        self._comments = comments or []
        self._transitions = transitions or [{"id": "21", "name": "处理中", "to": {"name": "处理中"}}]
        self.calls = []

    def search(self, jql, fields=None, max_total=500):
        self.calls.append(("search", jql)); return self.issues

    def issue(self, key, fields=None):
        self.calls.append(("issue", key))
        for i in self.issues:
            if i["key"] == key:
                return i
        return {"key": key, "fields": {"summary": "s", "status": {"name": "待办"}, "updated": "u", "project": {"key": key.split("-")[0]},
                                       "issuetype": {"name": "故障"}, "versions": [{"name": "cloud-5.0"}], "comment": {"comments": []}}}

    def comments(self, key):
        self.calls.append(("comments", key)); return self._comments

    def add_comment(self, key, body):
        self.calls.append(("add_comment", key, body)); return {"id": "999", "created": "now"}

    def transitions(self, key):
        self.calls.append(("transitions", key)); return self._transitions

    def do_transition(self, key, tid, comment=None):
        self.calls.append(("do_transition", key, tid, comment))


def _issue(key, status="待办", comments=()):
    return {"key": key, "fields": {"summary": f"[渠道A][5.0.4][c] {key}", "status": {"name": status}, "updated": "u1",
                                   "project": {"key": key.split("-")[0]}, "issuetype": {"name": "故障"}, "labels": [],
                                   "versions": [{"name": "cloud-5.0.4"}], "description": "",
                                   "comment": {"comments": [{"id": str(i), "author": {"name": a}, "updated": "u", "body": b} for i, (a, b) in enumerate(comments, 1)]}}}


def _ctx(tmp_path, client, mode=None, git=None, sh=None):
    cfg = config.build_config({"JIRA_URL": "http://j", "JIRA_USER": "me", "JIRA_TOKEN": "t"},
                              {"JIRA_WATCH_STATE_DIR": str(tmp_path / "state"), "JIRA_WATCH_REPO_DORIS": str(tmp_path / "doris")})
    return cli.Ctx(cfg, client=client, git=git or (lambda a, c: (1, "")), sh=sh or (lambda a: (1, "")), mode=mode)


def test_cmd_comment_refuses_in_observe_and_never_touches_client(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c)
    f = tmp_path / "b.txt"; f.write_text("正文", encoding="utf-8")
    out = cli.cmd_comment(ctx, "CIR-1", str(f), ("e1", "e2"), dry=False)
    assert out["refused"] is True
    assert not [x for x in c.calls if x[0] in ("add_comment", "comments")]
    recs, _ = events.read_records(ctx.records_path)
    assert recs[-1]["phase"] == "REFUSED" and events.handled_event_ids(recs) == frozenset()
    assert str(f) in recs[-1]["evidence"]


def test_cmd_comment_interact_writes_with_two_phase_and_all_event_ids(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c, mode="INTERACT")
    f = tmp_path / "b.txt"; f.write_text("正文", encoding="utf-8")
    out = cli.cmd_comment(ctx, "CIR-1", str(f), ("e1", "e2"), dry=False)
    assert out["ok"] and out["comment_id"] == "999"
    body = [x for x in c.calls if x[0] == "add_comment"][0][2]
    assert "Jira-Watch-Slot" in body and "me" in body
    recs, _ = events.read_records(ctx.records_path)
    assert [r["phase"] for r in recs] == ["INTENT", "RESULT"]
    assert events.handled_event_ids(recs) == frozenset({"e1", "e2"})


def test_cmd_comment_skips_when_remote_slot_exists(tmp_path):
    from jw import writes
    slot = writes.slot_id("CIR-1", ("e1",))
    c = FakeClient(comments=[{"id": "5", "body": f"x\nJira-Watch-Slot: {slot}"}]); ctx = _ctx(tmp_path, c, mode="INTERACT")
    f = tmp_path / "b.txt"; f.write_text("正文", encoding="utf-8")
    out = cli.cmd_comment(ctx, "CIR-1", str(f), ("e1",), dry=False)
    assert out["skipped"] and not [x for x in c.calls if x[0] == "add_comment"]


def test_cmd_transition_refuses_observe_and_whitelist(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c)
    assert cli.cmd_transition(ctx, "CIR-1", "处理中", ("e1",), dry=False, comment=None)["refused"]
    ctx2 = _ctx(tmp_path, c, mode="INTERACT")
    assert cli.cmd_transition(ctx2, "CIR-1", "完成", ("e1",), dry=False, comment=None)["refused"]
    assert not [x for x in c.calls if x[0] in ("transitions", "do_transition")]


def test_cmd_events_requires_baseline_and_persists_pending(tmp_path):
    c = FakeClient(issues=[_issue("CIR-1")]); ctx = _ctx(tmp_path, c)
    assert "error" in cli.cmd_events(ctx, None, dry=False)
    cli.cmd_baseline(ctx, None)
    c.issues = [_issue("CIR-1", comments=[("aibot", "AI-Analysis-Slot: s\nh2. 首次 on-call triage 结论")]), _issue("CIR-2")]
    first = cli.cmd_events(ctx, None, dry=False)
    kinds = sorted(e["kind"] for e in first["events"])
    assert kinds == ["AI_ANALYSIS_READY", "NEW_ISSUE"]
    # 第二轮：没有落 RESULT，事件必须仍在（H10）
    second = cli.cmd_events(ctx, None, dry=False)
    assert sorted(e["event_id"] for e in second["events"]) == sorted(e["event_id"] for e in first["events"])
    # 记 RESULT 后消失
    for e in first["events"]:
        ctx.record({"phase": "RESULT", "event_id": e["event_id"], "event_ids": [e["event_id"]], "type": "verdict"})
    assert cli.cmd_events(ctx, None, dry=False)["events"] == []


def test_cmd_events_dry_does_not_update_snapshot(tmp_path):
    c = FakeClient(issues=[_issue("CIR-1")]); ctx = _ctx(tmp_path, c)
    cli.cmd_baseline(ctx, None)
    c.issues = [_issue("CIR-1"), _issue("CIR-2")]
    cli.cmd_events(ctx, None, dry=True)
    assert "CIR-2" not in events.load_snapshot(ctx.snapshot_path)


def test_cmd_events_refuses_snapshot_collapse(tmp_path):
    c = FakeClient(issues=[_issue(f"CIR-{i}") for i in range(10)]); ctx = _ctx(tmp_path, c)
    cli.cmd_baseline(ctx, None)
    c.issues = [_issue("CIR-0")]
    out = cli.cmd_events(ctx, None, dry=False)
    assert out.get("error") and len(events.load_snapshot(ctx.snapshot_path)) == 10


def test_cmd_pick_advice_unparsable_version_reports_gap_not_crash(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c)
    out = cli.cmd_pick_advice(ctx, "CIR-9", no_fetch=True, hops=0)
    assert any("无法解析版本" in g for g in out["gaps"]) and out["families"] == []


def test_ensure_fresh_deduplicates_gaps_and_fetches_once(tmp_path):
    calls = []
    def git(a, cwd):
        calls.append(a); return (1, "fatal: https://u:p@x/y")
    c = FakeClient(); ctx = _ctx(tmp_path, c, git=git)
    (tmp_path / "doris").mkdir()
    ctx.ensure_fresh("apache/doris", no_fetch=False); ctx.ensure_fresh("apache/doris", no_fetch=False)
    assert len([a for a in calls if a[0] == "fetch"]) == 1
    assert len(ctx.gaps) == 1 and "<redacted>" in ctx.gaps[0]


def test_intent_record_carries_mode_source(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c, mode="INTERACT")
    f = tmp_path / "b.txt"; f.write_text("正文", encoding="utf-8")
    cli.cmd_comment(ctx, "CIR-1", str(f), ("e1",), dry=False)
    recs, _ = events.read_records(ctx.records_path)
    assert recs[0]["mode_source"] == "cli"


def test_state_dir_is_private(tmp_path):
    c = FakeClient(issues=[_issue("CIR-1")]); ctx = _ctx(tmp_path, c)
    cli.cmd_baseline(ctx, None)
    import stat
    assert stat.S_IMODE(ctx.state.stat().st_mode) == 0o700


def test_cmd_events_force_reprocesses_baselined_issue(tmp_path):
    c = FakeClient(issues=[_issue("CIR-1")]); ctx = _ctx(tmp_path, c)
    cli.cmd_baseline(ctx, None)
    out = cli.cmd_events(ctx, None, dry=True, force=("CIR-1",))
    assert [e["kind"] for e in out["events"]] == ["FORCED"] and "CIR-1" in out["issues"]


def test_cmd_comment_dry_run_previews_in_observe_without_recording(tmp_path):
    c = FakeClient(); ctx = _ctx(tmp_path, c)
    f = tmp_path / "b.txt"; f.write_text("正文", encoding="utf-8")
    out = cli.cmd_comment(ctx, "CIR-1", str(f), ("e1",), dry=True)
    assert out["dry_run"] and "Jira-Watch-Slot" in out["body"]
    assert events.read_records(ctx.records_path)[0] == ()


def test_cmd_pick_advice_uses_bare_sha_refs_as_seeds(tmp_path):
    issue = _issue("CIR-1", comments=[("aibot", "h2. 首次 on-call triage 结论\n修复提交 bfef01a41bf 已合入")])
    def git(a, cwd):
        if a[:3] == ["rev-parse", "-q", "--verify"] and a[3].startswith("bfef01a41bf"):
            return (0, "bfef01a41bfffffffffffffffffffffffffffffff\n")
        if a[:2] == ["log", "-1"]:
            return (0, "branch-internal-doris-4.0: [fix](clucene) Fix clucene multi-segment readBlock (#66736) (#10973)\n")
        return (1, "")
    def sh(a):
        if a[:3] == ["gh", "pr", "view"]:
            import json; return (0, json.dumps({"number": int(a[3]), "title": "[fix](clucene) Fix clucene multi-segment readBlock", "state": "MERGED", "baseRefName": "master", "mergeCommit": {"oid": "d8cd"}, "mergedAt": "t"}))
        return (0, "[]")
    c = FakeClient(issues=[issue]); ctx = _ctx(tmp_path, c, git=git, sh=sh)
    out = cli.cmd_pick_advice(ctx, "CIR-1", no_fetch=True, hops=0)
    assert out["sha_refs"] == ["bfef01a41bf"]
    assert any(m["number"] == 10973 for f in out["families"] for m in f["members"])


def test_seeds_from_shas_attribute_to_first_repo_only_and_are_speculative(tmp_path):
    """internal-core 克隆里也有 apache 远端的提交：同一 SHA 只归到优先仓库（doris），且 gh 404 不报 gap。"""
    cfg = config.build_config({"JIRA_URL": "http://j", "JIRA_USER": "me", "JIRA_TOKEN": "t"},
                              {"JIRA_WATCH_STATE_DIR": str(tmp_path / "s"), "JIRA_WATCH_REPO_DORIS": str(tmp_path / "d"), "JIRA_WATCH_REPO_INTERNAL": str(tmp_path / "c")})
    def git(a, cwd):
        if a[:3] == ["rev-parse", "-q", "--verify"]:
            return (0, "03b7afda9927f552eebb99d478f2f76f49942099\n")
        if a[:2] == ["log", "-1"]:
            return (0, "[fix](inverted index) Split bound multi-segment readers (#63138)\n")
        return (1, "")
    ctx = cli.Ctx(cfg, client=FakeClient(), git=git, sh=lambda a: (1, "GraphQL: Could not resolve to a PullRequest"))
    seeds = cli._seeds_from_shas(ctx, ["03b7afda992"])
    assert seeds == [("apache/doris", 63138)]
    assert cli._expand_chain(ctx, [], speculative=seeds) == [] and ctx.gaps == []
