"""issue 分类：决定哪些自动深度处理、哪些只跟踪。纯函数。"""
from __future__ import annotations

from dataclasses import dataclass

from jw import parse

_FEATURE_TYPES = {"story", "task", "任务", "新功能", "改进", "improvement", "new feature", "sub-task", "子任务"}
_BUG_TYPES = {"bug", "故障", "缺陷"}
_AUTO = ("CUSTOMER_BUG", "CI_FLAKY", "BUG")


@dataclass(frozen=True)
class Classification:
    category: str
    reasons: tuple[str, ...]
    versions: tuple[str, ...]


def _field_versions(fields: dict) -> tuple[str, ...]:
    return tuple(v.get("name", "") for v in fields.get("versions") or [] if v.get("name"))


def classify(issue: dict) -> Classification:
    f = issue.get("fields", {})
    project = (f.get("project") or {}).get("key", "")
    itype = ((f.get("issuetype") or {}).get("name") or "").strip()
    summary = f.get("summary") or ""
    labels = tuple(f.get("labels") or [])
    versions = _field_versions(f) or parse.versions_from_summary(summary)

    if "社区流水线" in labels or "不稳定用例" in summary or summary.startswith("[社区流水线]"):
        return Classification("CI_FLAKY", ("label/summary: 社区流水线 不稳定用例",), versions)
    if itype.lower() == "epic":
        return Classification("EPIC", (f"issuetype={itype}",), versions)
    if itype.lower() in _FEATURE_TYPES:
        return Classification("FEATURE", (f"issuetype={itype}",), versions)
    if project == "CIR":
        return Classification("CUSTOMER_BUG", ("project=CIR",), versions)
    if itype.lower() in _BUG_TYPES:
        return Classification("BUG", (f"project={project} issuetype={itype}",), versions)
    return Classification("OTHER", (f"project={project} issuetype={itype}",), versions)


def auto_processable(category: str) -> bool:
    return category in _AUTO


def repo_hints(category: str, versions: tuple[str, ...]) -> tuple[str, ...]:
    """候选仓库顺序（只是提示，现场核实）。"""
    if category == "CI_FLAKY":
        return ("apache/doris",)
    if category == "CUSTOMER_BUG":
        return ("example-org/internal-core", "apache/doris")
    return ("apache/doris", "example-org/internal-core")
