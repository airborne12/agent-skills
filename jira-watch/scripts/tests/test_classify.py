"""issue 分类纯函数测试。"""
from jw import classify


def _issue(project="CIR", itype="故障", summary="x", labels=(), versions=(), status="待办"):
    return {
        "key": f"{project}-1",
        "fields": {
            "project": {"key": project},
            "issuetype": {"name": itype},
            "summary": summary,
            "labels": list(labels),
            "versions": [{"name": v} for v in versions],
            "status": {"name": status},
        },
    }


def test_ci_flaky_by_label_or_summary():
    c = classify.classify(_issue("DORIS", "故障", "[社区流水线] 不稳定用例 mute: x", labels=("社区流水线",)))
    assert c.category == "CI_FLAKY"
    c2 = classify.classify(_issue("DORIS", "故障", "不稳定用例 mute: y"))
    assert c2.category == "CI_FLAKY"


def test_customer_bug_for_cir_project():
    c = classify.classify(_issue("CIR", "故障", "[渠道A][5.0.4][cluster] BE集群挂掉重启", labels=("cloud", "渠道A"), versions=("cloud-5.0.4",)))
    assert c.category == "CUSTOMER_BUG"
    assert c.versions == ("cloud-5.0.4",)


def test_customer_bug_falls_back_to_summary_version_when_field_empty():
    c = classify.classify(_issue("CIR", "故障", "【客户A】【2.1.7】stream load 报错"))
    assert c.category == "CUSTOMER_BUG"
    assert c.versions == ("2.1.7",)


def test_epic_and_feature_not_auto_processed():
    assert classify.classify(_issue("DORIS", "Epic", "滚动分区升级")).category == "EPIC"
    assert classify.classify(_issue("DORIS", "Story", "倒排索引V4 阶段一")).category == "FEATURE"
    assert classify.classify(_issue("CORE", "任务", "云上版本禁止新建倒排索引V1的表")).category == "FEATURE"


def test_plain_bug_in_doris_or_core():
    assert classify.classify(_issue("DORIS", "故障", "inverted_index_p2 用例失败")).category == "BUG"
    assert classify.classify(_issue("CORE", "Bug", "查询 core")).category == "BUG"


def test_auto_process_eligibility():
    assert classify.auto_processable("CUSTOMER_BUG") is True
    assert classify.auto_processable("CI_FLAKY") is True
    assert classify.auto_processable("BUG") is True
    assert classify.auto_processable("EPIC") is False
    assert classify.auto_processable("FEATURE") is False


def test_repo_hints_by_product():
    assert classify.repo_hints("CUSTOMER_BUG", ("cloud-5.0.4",)) == ("example-org/internal-core", "apache/doris")
    assert classify.repo_hints("CUSTOMER_BUG", ("2.1.7",)) == ("example-org/internal-core", "apache/doris")
    assert classify.repo_hints("CI_FLAKY", ()) == ("apache/doris",)
    assert classify.repo_hints("BUG", ()) == ("apache/doris", "example-org/internal-core")
