"""纯解析函数：PR/Jira 引用、@提及、AI 分析评论、CI 巡检评论、版本字符串。

所有函数无副作用，输入文本，输出不可变数据（frozen dataclass / tuple）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_PR_URL = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")
_PR_SHORT = re.compile(r"(?<![\w/])([\w.-]+/[\w.-]+)#(\d+)")
_ISSUE_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_SLOT = re.compile(r"AI-Analysis-Slot:\s*(\S+)")
_JUDGMENT = re.compile(r"判断[:：]\s*\{{0,2}(fail|partial|pass)\}{0,2}", re.I)
_CONFIDENCE = re.compile(r"(?:置信度|confidence)[:：]\s*\{{0,2}(high|medium|low)\}{0,2}", re.I)
_SHA = re.compile(r"(?<![0-9a-zA-Z])([0-9a-f]{10,40})(?![0-9a-zA-Z])")
_CI_HEADER = re.compile(
    r"\[社区流水线每日巡检\s+(\d{4}-\d{2}-\d{2})\s*\|\s*test=(-?\d+)\s*\|\s*latest=build:\(id:(\d+)\)[^|]*\|\s*decision=([\w-]+)\]"
)
_CI_BUILD_TYPE = re.compile(r"buildTypeId=([\w.-]+)")
_CI_FAIL_LINE = re.compile(r"\*失败行:\*\s*(\S+)")
_VERSION = re.compile(r"^(?:(cloud|internal)-)?(\d+(?:\.\d+){2,3})(?:-([0-9a-f]{7,40}))?$")
_BRACKET = re.compile(r"[\[【]([^\]】]+)[\]】]")
_VERSION_TOKEN = re.compile(r"^(?:cloud-)?\d+(?:\.\d+){2,3}$")
_BE_COMMIT = re.compile(r"Current BE git commitID:\s*([0-9a-f]{7,40})|internal-\d+(?:\.\d+)+-([0-9a-f]{7,40})")


@dataclass(frozen=True)
class PrRef:
    repo: str
    number: int

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}/pull/{self.number}"


@dataclass(frozen=True)
class AiAnalysis:
    is_placeholder: bool
    slot: Optional[str]
    judgment: Optional[str]
    confidence: Optional[str]
    issue_refs: tuple[str, ...]
    pr_refs: tuple[PrRef, ...]


@dataclass(frozen=True)
class CiInspection:
    date: str
    test_id: str
    latest_build_id: int
    decision: str
    build_type_id: Optional[str]
    failure_location: Optional[str]


@dataclass(frozen=True)
class ProductVersion:
    product: str  # cloud | enterprise
    version: str
    commit: Optional[str]


def _dedup(items):
    seen: set = set()
    out = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return tuple(out)


DEFAULT_PR_OWNERS = ("apache", "internal")


def extract_pr_refs(text: str, owners: tuple = DEFAULT_PR_OWNERS) -> tuple[PrRef, ...]:
    """从文本中提取 GitHub PR 引用：URL 一律接受；短格式 owner/repo#N 只认白名单 owner（防 fe/fe-core#123 误报）。"""
    found = [PrRef(m.group(1), int(m.group(2))) for m in _PR_URL.finditer(text)]
    found += [PrRef(m.group(1), int(m.group(2))) for m in _PR_SHORT.finditer(text)
              if m.group(1).split("/")[0] in owners]
    return _dedup(found)


def extract_issue_refs(text: str, exclude: Optional[str] = None, projects: tuple = ()) -> tuple[str, ...]:
    """Jira key；给了 projects 白名单就过滤掉 UTF-8 / SHA-1 / CVE-2024 这类误报。"""
    keys = [m.group(1) for m in _ISSUE_KEY.finditer(text)
            if m.group(1) != exclude and (not projects or m.group(1).split("-", 1)[0] in projects)]
    return _dedup(keys)


def mentions_user(text: str, username: str) -> bool:
    return f"[~{username}]" in text


def parse_ai_analysis(body: str) -> Optional[AiAnalysis]:
    """识别 aibot 类 AI 值班机器人的评论；非 AI 评论返回 None。"""
    slot = _SLOT.search(body)
    is_full = bool(slot) or "on-call triage 结论" in body
    is_placeholder = (not is_full) and body.strip().startswith("正在分析")
    if not is_full and not is_placeholder:
        return None
    judgment = _JUDGMENT.search(body)
    confidence = _CONFIDENCE.search(body)
    return AiAnalysis(
        is_placeholder=is_placeholder,
        slot=slot.group(1) if slot else None,
        judgment=judgment.group(1).lower() if judgment else None,
        confidence=confidence.group(1).lower() if confidence else None,
        issue_refs=extract_issue_refs(body),
        pr_refs=extract_pr_refs(body),
    )


def parse_ci_inspection(body: str) -> Optional[CiInspection]:
    """识别社区流水线每日巡检机器人评论头。"""
    m = _CI_HEADER.search(body)
    if not m:
        return None
    bt = _CI_BUILD_TYPE.search(body)
    fl = _CI_FAIL_LINE.search(body)
    return CiInspection(
        date=m.group(1),
        test_id=m.group(2),
        latest_build_id=int(m.group(3)),
        decision=m.group(4),
        build_type_id=bt.group(1) if bt else None,
        failure_location=fl.group(1) if fl else None,
    )


def parse_version(raw: str) -> Optional[ProductVersion]:
    """`cloud-5.0.4` / `2.1.7` / `internal-4.1.7-2cb76e238bf` → 产品线 + 版本 + 可选 commit。"""
    m = _VERSION.match(raw.strip())
    if not m:
        return None
    prefix, version, commit = m.groups()
    product = "cloud" if prefix in ("cloud", "internal") else "enterprise"
    return ProductVersion(product, version, commit)


def versions_from_summary(summary: str) -> tuple[str, ...]:
    """从标题的 [渠道A][5.0.4][...] / 【客户A】【2.1.7】 标签里抓版本号。"""
    tokens = [t.strip() for t in _BRACKET.findall(summary)]
    return _dedup([t for t in tokens if _VERSION_TOKEN.match(t)])


def be_commits(text: str) -> tuple[str, ...]:
    """崩溃栈里的 `Current BE git commitID: xxx` 或版本串 `internal-4.1.7-<sha>` 里的 commit。"""
    return _dedup([m.group(1) or m.group(2) for m in _BE_COMMIT.finditer(text)])


def extract_shas(text: str) -> tuple[str, ...]:
    """裸 git SHA（10–40 位 hex，前后不粘字母数字，且同时含字母与数字——排除时间戳与纯字母串）。"""
    return _dedup([m.group(1) for m in _SHA.finditer(text)
                   if any(c.isdigit() for c in m.group(1)) and any(c.isalpha() for c in m.group(1))])
