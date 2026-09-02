"""修复族归组、跨仓库 PR 号展开、无克隆仓库不出矩阵、同系列 tag 回退。"""
from jw import prchain, versions


def _pr(repo, n, title, base="master"):
    return prchain.PrMeta(repo, n, title, "MERGED", base, "sha%d" % n, "t")


def test_group_families_by_title_core():
    prs = [
        _pr("apache/doris", 63138, "[fix](inverted index) Split bound multi-segment readers"),
        _pr("apache/doris", 65687, "branch-4.1: [fix](inverted index) Split bound multi-segment readers #63138", base="branch-4.1"),
        _pr("example-org/internal-core", 10979, "[fix](clucene) Fix clucene multi-segment readBlock (#66736)", base="branch-hotfix-x"),
        _pr("apache/doris", 66736, "[fix](clucene) Fix clucene multi-segment readBlock"),
    ]
    fams = prchain.group_families(prs)
    assert [f.core for f in fams] == [
        "[fix](inverted index) split bound multi-segment readers",
        "[fix](clucene) fix clucene multi-segment readblock",
    ]
    assert [(p.repo, p.number) for p in fams[0].members] == [("apache/doris", 63138), ("apache/doris", 65687)]
    assert fams[1].origin.number == 66736  # 族的"源头"= 非 pick 前缀且 base 为 master 的成员，其次最早编号


def test_candidate_repos_for_number_cross_repo():
    assert prchain.candidate_repos_for_number("example-org/internal-core") == ("example-org/internal-core", "apache/doris")
    assert prchain.candidate_repos_for_number("apache/doris") == ("apache/doris",)
    assert prchain.candidate_repos_for_number("apache/doris-thirdparty") == ("apache/doris-thirdparty",)


def test_matrix_repos_only_sibling_repos_with_clone():
    configured = ("apache/doris", "example-org/internal-core")
    assert prchain.matrix_repos("apache/doris", configured) == ("apache/doris", "example-org/internal-core")
    assert prchain.matrix_repos("example-org/internal-core", configured) == ("apache/doris", "example-org/internal-core")
    assert prchain.matrix_repos("apache/doris-thirdparty", configured) == ()
    assert prchain.matrix_repos("apache/doris", ("apache/doris",)) == ("apache/doris",)


def test_nearest_series_tag_prefers_exact_then_highest_not_above():
    tags = ["tag-internal-cloud-5.0.0", "tag-internal-cloud-4.1.9", "tag-internal-cloud-5.0.2", "tag-internal-cloud-5.1.0"]
    assert versions.nearest_series_tag(tags, "tag-internal-cloud-", "5.0.4") == "tag-internal-cloud-5.0.2"
    assert versions.nearest_series_tag(tags, "tag-internal-cloud-", "5.0.2") == "tag-internal-cloud-5.0.2"
    assert versions.nearest_series_tag(tags, "tag-internal-cloud-", "5.0.1") == "tag-internal-cloud-5.0.0"
    assert versions.nearest_series_tag(tags, "tag-internal-cloud-", "6.0.1") is None
    assert versions.nearest_series_tag(["4.1.3", "4.1.3-rc01", "4.1.2"], "", "4.1.7") == "4.1.3"


def test_resolve_version_falls_back_to_series_tag():
    def git(args, cwd):
        if args[:2] == ["rev-parse", "-q"]:
            return (1, "")
        if args[0] == "tag":
            return (0, "tag-internal-cloud-5.0.0\ntag-internal-cloud-4.1.9\n")
        if args[0] == "rev-list":
            return (0, "0\n" if args[2].startswith("tag-") else "1545\n")
        raise AssertionError(args)
    r = versions.resolve_version("example-org/internal-core", "cloud", "5.0.4", ("branch-internal-doris-4.0",), git, "/repo")
    assert r["ref"] == "tag-internal-cloud-5.0.0" and r["ref_is_fallback"] is True
    assert r["base_branch"] == "branch-internal-doris-4.0" and r["confidence"] == "medium"
