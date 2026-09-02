"""解析类纯函数测试：PR 引用、Jira 引用、@提及、aibot 分析、CI 巡检、版本。"""
from jw import parse

AIBOT_FULL = """AI-Analysis-Slot: slot_56662d497257

h2. 首次 on-call triage 结论

*判断：{{fail}}（已确认 Doris/InternalCo 代码缺陷）；根因置信度：{{high}}。*

h2. 历史 Jira 与代码修复证据

* CIR-10003 使用完全相同的 BE commit
* 修复 PR：https://github.com/apache/doris/pull/63138 与 [branch-4.1 pick|https://github.com/apache/doris/pull/65687]
"""

AIBOT_PLACEHOLDER = "正在分析该问题，将结合崩溃堆栈、相关查询、历史问题及对应代码链路给出 triage 结论。"

CI_INSPECTION = """[社区流水线每日巡检 2026-09-02 | test=-8388185459402651183 | latest=build:(id:1035951),id:2000003144 | decision=confirmed-flaky]

h2. 失败现场
*失败行:* fe/fe-core/src/test/java/org/apache/doris/common/PropertyAnalyzerTest.java:412
*Build:* http://teamcity.example.com:8111/viewLog.html?buildId=1035951&buildTypeId=Doris_Doris_FeUt
"""


def test_extract_pr_refs_from_urls_and_wiki_links_dedup():
    refs = parse.extract_pr_refs(AIBOT_FULL)
    assert [(r.repo, r.number) for r in refs] == [
        ("apache/doris", 63138),
        ("apache/doris", 65687),
    ]
    assert refs[1].url == "https://github.com/apache/doris/pull/65687"


def test_extract_pr_refs_short_form_and_internal_repo():
    text = "见 example-org/internal-core#10979 以及 https://github.com/example-org/internal-core/pull/10979)"
    refs = parse.extract_pr_refs(text)
    assert [(r.repo, r.number) for r in refs] == [("example-org/internal-core", 10979)]


def test_extract_issue_refs_excludes_self_and_dedups():
    text = "和 CIR-10003 一致，参考 DORIS-20001、CIR-10003，本单 CIR-10001"
    assert parse.extract_issue_refs(text, exclude="CIR-10001") == ("CIR-10003", "DORIS-20001")


def test_mentions_user_wiki_syntax():
    assert parse.mentions_user("[~alice]  看看这个啊", "alice") is True
    assert parse.mentions_user("[~alice2] 看看", "alice") is False
    assert parse.mentions_user("alice 看看", "alice") is False


def test_parse_aibot_full_analysis():
    a = parse.parse_ai_analysis(AIBOT_FULL)
    assert a is not None
    assert a.is_placeholder is False
    assert a.slot == "slot_56662d497257"
    assert a.judgment == "fail"
    assert a.confidence == "high"
    assert a.issue_refs == ("CIR-10003",)
    assert [r.number for r in a.pr_refs] == [63138, 65687]


def test_parse_aibot_placeholder():
    a = parse.parse_ai_analysis(AIBOT_PLACEHOLDER)
    assert a is not None and a.is_placeholder is True


def test_parse_ai_analysis_returns_none_for_human_text():
    assert parse.parse_ai_analysis("和 CIR-10003 这个一致，关闭 enable_inverted_index_query") is None


def test_parse_ci_inspection_header():
    c = parse.parse_ci_inspection(CI_INSPECTION)
    assert c is not None
    assert c.date == "2026-09-02"
    assert c.test_id == "-8388185459402651183"
    assert c.latest_build_id == 1035951
    assert c.decision == "confirmed-flaky"
    assert c.build_type_id == "Doris_Doris_FeUt"
    assert c.failure_location == "fe/fe-core/src/test/java/org/apache/doris/common/PropertyAnalyzerTest.java:412"


def test_parse_ci_inspection_none_for_other_text():
    assert parse.parse_ci_inspection("普通评论") is None


def test_parse_version_cloud_enterprise_and_commit_suffix():
    assert parse.parse_version("cloud-5.0.4") == parse.ProductVersion("cloud", "5.0.4", None)
    assert parse.parse_version("2.1.7") == parse.ProductVersion("enterprise", "2.1.7", None)
    assert parse.parse_version("internal-4.1.7-2cb76e238bf") == parse.ProductVersion("cloud", "4.1.7", "2cb76e238bf")
    assert parse.parse_version("cloud-4.1.8.2") == parse.ProductVersion("cloud", "4.1.8.2", None)


def test_parse_version_rejects_garbage():
    assert parse.parse_version("N/A") is None


def test_versions_from_summary_brackets():
    assert parse.versions_from_summary("[渠道A][5.0.4][cluster-0001] BE集群挂掉重启") == ("5.0.4",)
    assert parse.versions_from_summary("【客户A】【2.1.7】stream load导入报错") == ("2.1.7",)
    assert parse.versions_from_summary("[渠道A][cloud-4.0.11][x] 倒排索引等值查询失效") == ("cloud-4.0.11",)
    assert parse.versions_from_summary("倒排索引V4 阶段一") == ()
