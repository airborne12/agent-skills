"""Jira REST 客户端：分页、字段、错误处理（注入 fake http）。"""
from jw import jira_api


def _http_factory(pages):
    calls = []

    def http(method, url, params=None, json=None):
        calls.append((method, url, params, json))
        if url.endswith("/search"):
            start = int(params["startAt"])
            return 200, pages[start]
        if url.endswith("/comment") and method == "POST":
            return 201, {"id": "999", "author": {"displayName": "me"}, "created": "now"}
        if url.endswith("/transitions") and method == "GET":
            return 200, {"transitions": [{"id": "21", "name": "处理中", "to": {"name": "处理中"}}]}
        if url.endswith("/transitions") and method == "POST":
            return 204, {}
        if "/issue/" in url:
            return 200, {"key": "CIR-1", "fields": {"summary": "s"}}
        raise AssertionError(url)

    return http, calls


def test_search_paginates_until_total():
    pages = {
        0: {"total": 3, "startAt": 0, "maxResults": 2, "issues": [{"key": "A"}, {"key": "B"}]},
        2: {"total": 3, "startAt": 2, "maxResults": 2, "issues": [{"key": "C"}]},
    }
    http, calls = _http_factory(pages)
    c = jira_api.JiraClient("http://j", "tok", http=http, page_size=2)
    got = c.search("project = CIR", fields=("summary",))
    assert [i["key"] for i in got] == ["A", "B", "C"]
    assert calls[0][2]["fields"] == "summary" and calls[0][2]["jql"] == "project = CIR"


def test_error_messages_raise():
    def http(method, url, params=None, json=None):
        return 400, {"errorMessages": ["bad jql"]}
    c = jira_api.JiraClient("http://j", "tok", http=http)
    try:
        c.search("x", fields=("summary",))
    except jira_api.JiraError as e:
        assert "bad jql" in str(e)
    else:
        raise AssertionError("expected JiraError")


def test_add_comment_and_transition():
    http, calls = _http_factory({})
    c = jira_api.JiraClient("http://j", "tok", http=http)
    r = c.add_comment("CIR-1", "body")
    assert r["id"] == "999"
    assert calls[-1][3] == {"body": "body"}
    assert c.transitions("CIR-1")[0]["id"] == "21"
    c.do_transition("CIR-1", "21", comment="go")
    assert calls[-1][3]["transition"] == {"id": "21"}
    assert calls[-1][3]["update"]["comment"][0]["add"]["body"] == "go"


def test_auth_header_bearer():
    h = jira_api.auth_headers("tok")
    assert h == {"Authorization": "Bearer tok", "Accept": "application/json"}
