"""基线对照发现的缺口：连字符分支前缀、BE commit 反查版本、发布 tag 包含、hotfix 分支纳入矩阵。"""
from jw import parse, prchain, versions


def test_title_core_strips_hyphenated_internal_branch_prefix():
    t = "branch-internal-doris-4.0: [fix](clucene) Fix clucene multi-segment readBlock (#66736) (#10973)"
    assert prchain.title_core(t) == "[fix](clucene) fix clucene multi-segment readblock"
    t2 = "branch-hotfix-internal-cloud-26.1.1-customer-a: [fix](x) y (#1) (#2)"
    assert prchain.title_core(t2) == "[fix](x) y"


def test_be_commit_from_crash_text():
    desc = "堆栈信息\n*** Current BE git commitID: a9719436f68 ***\n*** SIGABRT"
    assert parse.be_commits(desc) == ("a9719436f68",)
    assert parse.be_commits("版本：{{internal-4.1.7-2cb76e238bf}}") == ("2cb76e238bf",)
    assert parse.be_commits("nothing") == ()


def test_release_tags_sorted_filters_and_orders_desc():
    tags = ["tag-internal-cloud-26.0.5.3", "tag-internal-cloud-26.0.6", "tag-internal-cloud-26.0.4-fix-CIR-10002",
            "tag-internal-doris-4.0.7", "4.1.4-rc04", "4.1.3", "tmp-foo"]
    out = prchain.release_tags_sorted(tags)
    assert out[:3] == ["tag-internal-cloud-26.0.6", "tag-internal-cloud-26.0.5.3", "tag-internal-doris-4.0.7"]
    assert "tmp-foo" not in out and "tag-internal-cloud-26.0.4-fix-CIR-10002" not in out
    assert out[-2:] == ["4.1.4-rc04", "4.1.3"] or out[-2:] == ["4.1.3", "4.1.4-rc04"]


def test_tags_containing_uses_git_and_limits():
    def git(args, cwd):
        assert args[:2] == ["tag", "--contains"]
        return (0, "tag-internal-cloud-26.0.6\ntag-internal-cloud-26.1.2\ntmp-x\n")
    assert prchain.tags_containing("sha", git, "/repo", limit=1) == ["tag-internal-cloud-26.1.2"]


def test_resolve_ref_for_commit_reports_containing_tags_and_subject():
    def git(args, cwd):
        if args[:3] == ["rev-parse", "-q", "--verify"]:
            return (0, "a9719436f68\n")
        if args[:2] == ["log", "-1"]:
            return (0, "Bump version to cloud-26.0.4 enterprise-4.0.6\n")
        if args[:2] == ["tag", "--points-at"]:
            return (0, "tag-internal-cloud-26.0.4\ntag-internal-doris-4.0.6\n")
        if args[0] == "rev-list":
            return (0, "0\n" if args[2] == "a9719436f68" else "212\n")
        raise AssertionError(args)
    r = versions.resolve_ref("example-org/internal-core", "a9719436f68", ("branch-internal-doris-4.0",), git, "/repo")
    assert r["ref"] == "a9719436f68" and r["base_branch"] == "branch-internal-doris-4.0" and r["confidence"] == "high"
    assert r["subject"].startswith("Bump version to cloud-26.0.4")
    assert r["tags_at"] == ["tag-internal-cloud-26.0.4", "tag-internal-doris-4.0.6"]


def test_resolve_ref_missing_commit():
    r = versions.resolve_ref("example-org/internal-core", "deadbeef", ("b",), lambda a, c: (1, ""), "/repo")
    assert r["ref"] is None and r["confidence"] == "none"


def test_version_from_bump_subject():
    assert versions.versions_from_bump_subject("Bump version to cloud-26.0.4 enterprise-4.0.6") == ("cloud-26.0.4", "enterprise-4.0.6")
    assert versions.versions_from_bump_subject("[fix] x") == ()
