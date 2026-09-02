"""版本 → tag 候选 / 最近基线分支 的纯函数与注入式 git 测试。"""
from jw import versions


def test_tag_candidates_internal_core_cloud():
    assert versions.tag_candidates("example-org/internal-core", "cloud", "26.0.4") == (
        "tag-internal-cloud-26.0.4",
        "26.0.4",
    )


def test_tag_candidates_internal_core_enterprise():
    assert versions.tag_candidates("example-org/internal-core", "enterprise", "2.1.7") == (
        "tag-internal-doris-2.1.7",
        "2.1.7",
    )


def test_tag_candidates_apache_doris():
    assert versions.tag_candidates("apache/doris", "enterprise", "2.1.7") == ("2.1.7", "branch-2.1.7")
    assert versions.tag_candidates("apache/doris", "cloud", "4.1.7") == ()  # 云版本号对 doris 无意义，走 BE commit 反查


def test_nearest_branch_prefers_zero_tag_ahead_then_smallest_branch_ahead():
    d = {
        "branch-internal-doris-4.0": versions.Distance(branch_ahead=1545, tag_ahead=0),
        "branch-internal-doris-4.1": versions.Distance(branch_ahead=1743, tag_ahead=0),
        "branch-internal-doris-3.1": versions.Distance(branch_ahead=7392, tag_ahead=9326),
    }
    m = versions.nearest_branch(d)
    assert m.branch == "branch-internal-doris-4.0" and m.tag_ahead == 0


def test_nearest_branch_tolerates_small_tag_ahead():
    d = {
        "branch-internal-doris-3.1": versions.Distance(branch_ahead=249, tag_ahead=3),
        "branch-internal-doris-3.0": versions.Distance(branch_ahead=733, tag_ahead=1904),
    }
    m = versions.nearest_branch(d)
    assert m.branch == "branch-internal-doris-3.1" and m.tag_ahead == 3


def test_nearest_branch_empty_returns_none():
    assert versions.nearest_branch({}) is None


def test_resolve_version_with_fake_git():
    calls = []

    def git(args, cwd):
        calls.append(args)
        if args[:2] == ["rev-parse", "-q"]:
            return (0, "abc\n") if "tag-internal-cloud-26.0.4^{commit}" in args else (1, "")
        if args[0] == "rev-list":
            # rev-list --count A ^B
            a, b = args[2], args[3]
            if b.startswith("^origin/branch-internal-doris-4.0") or a == "origin/branch-internal-doris-4.0":
                return (0, "0\n" if a.startswith("tag-") else "212\n")
            return (0, "686\n" if a.startswith("tag-") else "1096\n")
        raise AssertionError(args)

    r = versions.resolve_version(
        repo="example-org/internal-core",
        product="cloud",
        version="26.0.4",
        release_branches=("branch-internal-doris-4.0", "branch-internal-doris-4.1"),
        git_run=git,
        cwd="/repo",
    )
    assert r["ref"] == "tag-internal-cloud-26.0.4"
    assert r["base_branch"] == "branch-internal-doris-4.0"
    assert r["distances"]["branch-internal-doris-4.0"] == {"branch_ahead": 212, "tag_ahead": 0}


def test_resolve_version_no_ref_found_reports_low_confidence():
    r = versions.resolve_version(
        repo="apache/doris", product="cloud", version="4.0.11",
        release_branches=("branch-4.0",), git_run=lambda a, cwd: (1, ""), cwd="/repo",
    )
    assert r["ref"] is None and r["base_branch"] is None and r["confidence"] == "none"
    assert "4.0" in r["series_hint"]
