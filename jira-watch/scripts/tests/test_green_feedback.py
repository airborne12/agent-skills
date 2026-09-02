"""GREEN 验证 agent 的反馈：先红后绿。"""
from jw import parse, prchain, versions, render


def test_ai_analysis_judgment_without_braces_and_english_confidence():
    a = parse.parse_ai_analysis("h2. 首次 on-call triage 结论\n*判断：fail（已确认代码缺陷）；confidence：high。*")
    assert a.judgment == "fail" and a.confidence == "high"


def test_extract_shas_10_to_40_hex_only():
    text = "commit 03b7afda992 与 `d8cd719ab65`，短的 abc123 不算，deadbeef 不算，6549362b4960204ae380c27b89677ba9c13a01b9 算"
    assert parse.extract_shas(text) == ("03b7afda992", "d8cd719ab65", "6549362b4960204ae380c27b89677ba9c13a01b9")


def test_containment_unions_tags_from_direct_and_pick_commits():
    def git(args, cwd):
        if args[0] == "merge-base":
            return (0, "")  # 直接祖先（经 merge 带入的 doris SHA）
        if args[0] == "log":
            return (0, "c160\x00branch-internal-doris-4.1: [fix](clucene) Fix clucene multi-segment readBlock (#66736) (#10974)\n")
        if args[:2] == ["tag", "--contains"]:
            return (0, "tag-internal-cloud-26.1.2\n" if args[2] == "c160" else "")
        raise AssertionError(args)
    pr = prchain.PrMeta("apache/doris", 66736, "[fix](clucene) Fix clucene multi-segment readBlock", "MERGED", "master", "b514", "t")
    m = prchain.containment(pr, ("branch-internal-doris-4.1",), git_run=git, cwd="/r")
    h = m["branch-internal-doris-4.1"]
    assert h.kind == "direct" and h.tags == ("tag-internal-cloud-26.1.2",) and h.shas == ("b514", "c160")


def test_enumerate_family_prs_via_gh_search_filters_by_core_and_keeps_closed():
    def sh(args):
        assert args[:3] == ["gh", "pr", "list"] and "--state" in args and args[args.index("--state") + 1] == "all"
        repo = args[args.index("--repo") + 1]
        rows = {"apache/doris": [
            {"number": 66737, "title": "branch-4.0: [fix](clucene) Fix clucene multi-segment readBlock #66736", "state": "CLOSED", "baseRefName": "branch-4.0", "mergeCommit": None, "mergedAt": None},
            {"number": 1, "title": "[fix](clucene) something else", "state": "MERGED", "baseRefName": "master", "mergeCommit": {"oid": "x"}, "mergedAt": "t"},
        ], "example-org/internal-core": [
            {"number": 10973, "title": "branch-internal-doris-4.0: [fix](clucene) Fix clucene multi-segment readBlock (#66736)", "state": "MERGED", "baseRefName": "branch-internal-doris-4.0", "mergeCommit": {"oid": "bfef"}, "mergedAt": "t"},
        ]}[repo]
        import json; return (0, json.dumps(rows))
    prs = prchain.enumerate_family_prs("[fix](clucene) fix clucene multi-segment readblock", ("apache/doris", "example-org/internal-core"), sh)
    assert [(p.repo, p.number, p.state) for p in prs] == [("apache/doris", 66737, "CLOSED"), ("example-org/internal-core", 10973, "MERGED")]


def test_cloud_version_has_no_doris_tag_candidates():
    assert versions.tag_candidates("apache/doris", "cloud", "4.1.7") == ()


def test_render_marks_hotfix_verified_and_closed_members():
    fam = {"core": "x", "members": [
        {"repo": "example-org/internal-core", "number": 10979, "state": "MERGED", "base": "branch-hotfix-internal-cloud-26.1.1-customer-a"},
        {"repo": "apache/doris", "number": 66737, "state": "CLOSED", "base": "branch-4.0"}], "matrix": {}, "advice": {}}
    text = render.render_pick_advice({"issue": "K", "families": [fam]})
    assert "客户 hotfix 已验证" in text and "已关闭未合入" in text


def test_extract_shas_requires_both_letters_and_digits():
    assert parse.extract_shas("时间戳 1788330282 不是 SHA；abcdefabcdef 也不是；03b7afda992 是") == ("03b7afda992",)
