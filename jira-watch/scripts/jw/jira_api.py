"""Jira Server REST v2 极简客户端。http 可注入；默认实现走 requests，剥离代理。"""
from __future__ import annotations

import json
from typing import Callable, Optional

Http = Callable[..., tuple[int, dict]]
ISSUE_FIELDS = ("summary", "status", "assignee", "reporter", "description", "comment", "issuetype",
                "priority", "created", "updated", "labels", "versions", "fixVersions", "components",
                "project", "issuelinks", "attachment")


class JiraError(RuntimeError):
    pass


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def requests_http(token: str, timeout: int = 60) -> Http:
    import requests  # 延迟导入，测试不依赖

    session = requests.Session()
    session.trust_env = False  # 忽略 HTTP(S)_PROXY，Jira 走 VPN 直连
    headers = {**auth_headers(token), "Content-Type": "application/json"}

    def http(method, url, params=None, json=None):
        resp = session.request(method, url, params=params, json=json, headers=headers, timeout=timeout)
        try:
            body = resp.json() if resp.text else {}
        except ValueError:
            body = {"raw": resp.text[:500]}
        return resp.status_code, body

    return http


class JiraClient:
    def __init__(self, url: str, token: str, http: Optional[Http] = None, page_size: int = 50):
        self.url = url.rstrip("/")
        self.http = http or requests_http(token)
        self.page_size = page_size

    def _call(self, method: str, path: str, params=None, json=None) -> dict:
        status, body = self.http(method, f"{self.url}/rest/api/2/{path}", params=params, json=json)
        if status >= 400 or (isinstance(body, dict) and body.get("errorMessages")):
            msg = "; ".join(body.get("errorMessages", [])) if isinstance(body, dict) else str(body)
            raise JiraError(f"HTTP {status} {path}: {msg or body}")
        return body

    def search(self, jql: str, fields: tuple = ISSUE_FIELDS, max_total: int = 500) -> list:
        out, start = [], 0
        while True:
            page = self._call("GET", "search", params={"jql": jql, "fields": ",".join(fields),
                                                        "startAt": start, "maxResults": self.page_size})
            got = page.get("issues", [])
            out.extend(got)
            if not got:
                return out
            start += len(got)  # 服务端可能按自己的上限截断每页，按实际条数推进
            if start >= page.get("total", 0):
                return out
            if len(out) >= max_total:
                raise JiraError(f"JQL 命中超过 max_total={max_total}，拒绝返回截断结果（会造成假 DROPPED）；请收窄 JQL")

    def issue(self, key: str, fields: tuple = ISSUE_FIELDS) -> dict:
        return self._call("GET", f"issue/{key}", params={"fields": ",".join(fields)})

    def comments(self, key: str) -> list:
        return self._call("GET", f"issue/{key}/comment").get("comments", [])

    def add_comment(self, key: str, body: str) -> dict:
        return self._call("POST", f"issue/{key}/comment", json={"body": body})

    def transitions(self, key: str) -> list:
        return self._call("GET", f"issue/{key}/transitions").get("transitions", [])

    def do_transition(self, key: str, transition_id: str, comment: Optional[str] = None) -> None:
        payload = {"transition": {"id": str(transition_id)}}
        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}
        self._call("POST", f"issue/{key}/transitions", json=payload)
