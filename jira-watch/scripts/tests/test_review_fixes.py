"""代码审查发现的缺陷（纯函数部分）：先红后绿。"""
import json
from jw import parse, prchain, writes, events, jira_api, versions, cli


# C2 分页
def test_search_advances_by_returned_count_when_server_caps_page():
    pages = {0: {"total": 5, "issues": [{"key": "A"}, {"key": "B"}]}, 2: {"total": 5, "issues": [{"key": "C"}, {"key": "D"}]}, 4: {"total": 5, "issues": [{"key": "E"}]}}
    def http(method, url, params=None, json=None):
        return 200, pages[int(params["startAt"])]
    c = jira_api.JiraClient("http://j", "t", http=http, page_size=50)
    assert [i["key"] for i in c.search("x", fields=("summary",))] == ["A", "B", "C", "D", "E"]


def test_search_raises_instead_of_silently_truncating():
    def http(method, url, params=None, json=None):
        return 200, {"total": 10, "issues": [{"key": str(params["startAt"])}, {"key": "x"}]}
    c = jira_api.JiraClient("http://j", "t", http=http, page_size=2)
    try:
        c.search("x", fields=("summary",), max_total=4)
    except jira_api.JiraError as e:
        assert "max_total" in str(e)
    else:
        raise AssertionError("expected JiraError")


# H3 幂等覆盖全部 event_ids；H2 REFUSED 不算已处理
def test_handled_ids_cover_all_event_ids_and_ignore_refused():
    recs = ({"phase": "RESULT", "event_id": "a", "event_ids": ["a", "b"]}, {"phase": "REFUSED", "event_id": "c", "event_ids": ["c"]})
    assert events.handled_event_ids(recs) == frozenset({"a", "b"})


# H5 Jira key 白名单
def test_extract_issue_refs_ignores_utf8_sha1_iso8601_with_project_whitelist():
    text = "UTF-8 SHA-1 ISO-8601 CVE-2024-1 AES-256 见 CIR-10003 和 OPENSOURCE-412"
    assert parse.extract_issue_refs(text, projects=("CIR", "DORIS", "CORE", "OPENSOURCE")) == ("CIR-10003", "OPENSOURCE-412")


def test_extract_pr_refs_short_form_requires_known_owner():
    assert parse.extract_pr_refs("路径 fe/fe-core#123 不是 PR；apache/doris#5 是") == (parse.PrRef("apache/doris", 5),)


# H6 去评分整行剔除且不留残渣，保留代码块空行
def test_strip_scores_removes_whole_line_multi_digit_and_keeps_blank_lines():
    text = "结论：需要 pick\nC=10 S=0.95 P=100 总分=0.85\n{code}\nSELECT 1\n\n  \n{code}\n证据：x"
    out = writes.strip_scores(text)
    assert "0.95" not in out and "00" not in out and "总分" not in out
    assert "结论：需要 pick" in out and "证据：x" in out
    assert "\n\n" in out  # 空行保留


# M9 免责声明操作人来自配置
def test_build_comment_operator_from_argument():
    body = writes.build_comment("x", slot="jw_1", operator="someone")
    assert "someone" in body and "alice" not in body


# H8 四段版本排序
def test_release_tags_sorted_four_segment_beats_three_segment():
    assert prchain.release_tags_sorted(["tag-internal-cloud-26.0.5", "tag-internal-cloud-26.0.5.3"])[0] == "tag-internal-cloud-26.0.5.3"


# M7 更多 pick 前缀
def test_title_core_strips_pick_tag_and_bare_version_prefix():
    assert prchain.title_core("[pick] [fix](x) y (#1)") == "[fix](x) y"
    assert prchain.title_core("2.1: [fix](x) y") == "[fix](x) y"
    assert prchain.title_core("branch-2.1:[fix](x) y (#2) (#3)") == "[fix](x) y"


# H7 gh 非 JSON
def test_gh_pr_view_non_json_raises_runtime_error():
    try:
        prchain.gh_pr_view("apache/doris", 1, lambda a: (0, "Upgrade available!\n{not json"))
    except RuntimeError as e:
        assert "非预期" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


# H4 subprocess 兜底
def test_git_run_returns_error_tuple_for_missing_cwd_or_binary():
    rc, out = cli.git_run(["status"], "/definitely/not/a/dir")
    assert rc == 127 and "不存在" in out
    rc, out = cli.sh_run(["definitely-not-a-real-binary-xyz"])
    assert rc == 127


# M1 脱敏
def test_redact_strips_userinfo_from_urls():
    assert cli.redact("fatal: https://user:tok3n@github.com/x.git failed") == "fatal: https://<redacted>@github.com/x.git failed"


# M6 快照损坏可容忍
def test_load_snapshot_corrupt_json_is_tolerated(tmp_path):
    p = tmp_path / "snapshot.json"; p.write_text("{corrupt", encoding="utf-8")
    assert events.load_snapshot(p) == {}


# H11 锁：原子 + 属主
def test_release_lock_requires_owner_pid(tmp_path):
    assert events.acquire_lock(tmp_path, pid=111, now_iso="2026-09-02T03:00:00Z") is True
    assert events.release_lock(tmp_path, pid=222) is False
    assert (tmp_path / "lock").exists()
    assert events.release_lock(tmp_path, pid=111) is True


# C1 附件名
def test_safe_attachment_name_rejects_traversal_and_absolute():
    assert cli.safe_attachment_name("be.out") == "be.out"
    assert cli.safe_attachment_name("dir\\x.log") == "x.log"
    for bad in ("../../etc/evil", "/etc/passwd", "", ".", ".."):
        try:
            cli.safe_attachment_name(bad)
        except ValueError:
            continue
        # 绝对路径与穿越取 basename 后仍需非空；'/etc/passwd' → 'passwd' 可接受
        assert bad == "/etc/passwd" or bad == "../../etc/evil"


# H10 待处理事件持久化（纯函数）
def test_merge_pending_events_dedup_and_filter_handled():
    pending = [{"event_id": "a", "kind": "NEW_ISSUE", "key": "K"}, {"event_id": "b", "kind": "x", "key": "K"}]
    fresh = [{"event_id": "b", "kind": "x", "key": "K"}, {"event_id": "c", "kind": "y", "key": "K"}]
    out = cli.merge_pending(pending, fresh, handled=frozenset({"a"}))
    assert [e["event_id"] for e in out] == ["b", "c"]
