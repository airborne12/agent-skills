"""PR 链：标题归一化、跨仓库撞号防护、分支包含矩阵、pick 建议。"""
from jw import prchain


def test_title_core_strips_branch_prefix_and_pr_numbers():
    t = "branch-4.1: [fix](inverted index) Split bound multi-segment readers #63138 (#65687)"
    assert prchain.title_core(t) == "[fix](inverted index) split bound multi-segment readers"
    t2 = "internal-cloud-4.0:[fix](lineage) Propagate connectAttributes (#62082) (#8615)"
    assert prchain.title_core(t2) == "[fix](lineage) propagate connectattributes"
    t3 = "[fix](clucene) Fix clucene multi-segment readBlock (#66736)"
    assert prchain.title_core(t3) == "[fix](clucene) fix clucene multi-segment readblock"


def test_referenced_numbers_in_title():
    assert prchain.referenced_numbers("branch-4.1: x #63138 (#65687)") == (63138, 65687)
    assert prchain.referenced_numbers("[fix] y") == ()


def test_parse_pr_ref_forms():
    assert prchain.parse_pr_ref("https://github.com/apache/doris/pull/63138") == ("apache/doris", 63138)
    assert prchain.parse_pr_ref("example-org/internal-core#10979") == ("example-org/internal-core", 10979)
    assert prchain.parse_pr_ref("#42", default_repo="apache/doris") == ("apache/doris", 42)
    assert prchain.parse_pr_ref("#42") is None


def test_match_hits_requires_title_core_match_not_just_number():
    core = "[fix](clucene) fix clucene multi-segment readblock"
    log_lines = [
        "aaaa\x00[hotfix](dev-1.1.1) fallback to no-vec outer join in some case (#10979)",
        "bbbb\x00internal-cloud-4.0: [fix](clucene) Fix clucene multi-segment readBlock (#66736) (#10979)",
    ]
    hits = prchain.match_hits(core, log_lines)
    assert [h.sha for h in hits] == ["bbbb"]


def test_containment_direct_then_pick_then_missing():
    def git(args, cwd):
        if args[0] == "merge-base":
            return (0, "") if args[-1] == "origin/master" else (1, "")
        if args[0] == "log":
            branch = args[1]
            if branch == "origin/branch-4.1":
                return (0, "9f98\x00branch-4.1: [fix](inverted index) Split bound multi-segment readers #63138 (#65687)\n")
            return (0, "")
        if args[:2] == ["tag", "--contains"]:
            return (0, "4.1.4-rc04\ntmp-x\n" if args[2] == "9f98" else "")
        raise AssertionError(args)

    pr = prchain.PrMeta(repo="apache/doris", number=63138, title="[fix](inverted index) Split bound multi-segment readers",
                        state="MERGED", base="master", merge_sha="03b7", merged_at="2026-05-25T09:01:22Z")
    m = prchain.containment(pr, ("master", "branch-4.1", "branch-4.0"), git_run=git, cwd="/repo")
    assert m["master"].kind == "direct"
    assert m["branch-4.1"].kind == "picked" and m["branch-4.1"].sha == "9f98"
    assert m["branch-4.1"].tags == ("4.1.4-rc04",)
    assert m["master"].tags == ()
    assert m["branch-4.0"].kind == "missing"


def test_containment_without_merge_sha_uses_title_only():
    def git(args, cwd):
        assert args[0] != "merge-base"
        return (0, "")
    pr = prchain.PrMeta(repo="apache/doris", number=1, title="[fix] x", state="OPEN", base="master", merge_sha=None, merged_at=None)
    m = prchain.containment(pr, ("master",), git_run=git, cwd="/repo")
    assert m["master"].kind == "missing"


def test_pr_meta_from_gh_json():
    j = {"number": 10979, "title": "[fix](clucene) Fix clucene multi-segment readBlock (#66736)", "state": "MERGED",
         "mergedAt": "2026-08-13T12:18:30Z", "baseRefName": "branch-hotfix-internal-cloud-26.1.1-customer-a",
         "mergeCommit": {"oid": "6549362b"}}
    pr = prchain.pr_meta_from_gh("example-org/internal-core", j)
    assert pr.merge_sha == "6549362b" and pr.base.startswith("branch-hotfix") and pr.number == 10979


def test_pick_advice_marks_missing_base_and_suggests_target():
    matrix = {
        "master": prchain.Hit("direct", "03b7", None),
        "branch-4.1": prchain.Hit("picked", "9f98", "branch-4.1: ..."),
        "branch-4.0": prchain.Hit("missing", None, None),
    }
    adv = prchain.pick_advice(base_branch="branch-4.0", matrix=matrix)
    assert adv.fixed_on == ("master", "branch-4.1")
    assert adv.base_has_fix is False
    assert adv.suggested_targets == ("branch-4.0",)


def test_pick_advice_when_base_already_fixed():
    matrix = {"branch-4.1": prchain.Hit("picked", "9f98", "x")}
    adv = prchain.pick_advice(base_branch="branch-4.1", matrix=matrix)
    assert adv.base_has_fix is True and adv.suggested_targets == ()


def test_pick_advice_unknown_base():
    adv = prchain.pick_advice(base_branch=None, matrix={"master": prchain.Hit("direct", "a", None)})
    assert adv.base_has_fix is None and adv.suggested_targets == ()
