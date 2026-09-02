"""PR 链：gh 元信息、标题归一化、分支包含矩阵（防跨仓库 PR 撞号）、pick 建议。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Optional

GitRun = Callable[[list, str], tuple[int, str]]

_PREFIX = re.compile(r"^\s*(?:\[(?:pick|cherry-pick)\]\s*)?(?:(?:branch-[\w.-]+|internal-cloud-[\w.-]+|master|\d+(?:\.\d+)+)\s*:\s*)?", re.I)
_TAG_SEGMENTS = 4  # 发布 tag 最多四段，比较前补零避免变长元组
_RELEASE_TAG = re.compile(r"^(tag-internal-cloud-|tag-internal-doris-)?(\d+(?:\.\d+){1,3})(?:-rc\d+)?$")
_FAMILY_RANK = {"tag-internal-cloud-": 0, "tag-internal-doris-": 1, None: 2}
_TRAILING_NUM = re.compile(r"\s*(?:\(#\d+\)|#\d+)\s*$")
_ANY_NUM = re.compile(r"#(\d+)")
_URL = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")
_SHORT = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_BARE = re.compile(r"^#(\d+)$")


@dataclass(frozen=True)
class PrMeta:
    repo: str
    number: int
    title: str
    state: str
    base: Optional[str]
    merge_sha: Optional[str]
    merged_at: Optional[str]

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}/pull/{self.number}"


@dataclass(frozen=True)
class Hit:
    kind: str  # direct | picked | missing
    sha: Optional[str]
    subject: Optional[str]
    tags: tuple = ()  # 含该分支上任一同族提交的发布 tag 并集（按版本降序）
    shas: tuple = ()  # 该分支上找到的全部同族提交（直接祖先 + pick）


@dataclass(frozen=True)
class Family:
    core: str
    members: tuple  # PrMeta...

    @property
    def origin(self) -> "PrMeta":
        """族源头：非 pick 前缀且 base 为 master 的成员优先，其次编号最小。"""
        def rank(m):
            pick_like = bool(_PREFIX.match(m.title))
            return (pick_like, (m.base or "") != "master", m.number)
        return min(self.members, key=rank)


_SIBLINGS = ("apache/doris", "example-org/internal-core")


def group_families(prs: list) -> tuple:
    """按标题核心归组，保持首次出现顺序。"""
    order, buckets = [], {}
    for pr in prs:
        core = title_core(pr.title)
        if core not in buckets:
            order.append(core); buckets[core] = []
        buckets[core].append(pr)
    return tuple(Family(c, tuple(buckets[c])) for c in order)


def candidate_repos_for_number(repo: str) -> tuple:
    """标题里的 #N 可能属于哪些仓库：internal-core 的 pick 标题会带 doris 的 PR 号。"""
    return (repo, "apache/doris") if repo == "example-org/internal-core" else (repo,)


def matrix_repos(pr_repo: str, configured: tuple) -> tuple:
    """只在 doris/internal-core 这对互相 pick 的仓库里查包含关系，且必须有本地克隆。"""
    if pr_repo not in _SIBLINGS:
        return ()
    return tuple(r for r in _SIBLINGS if r in configured)


@dataclass(frozen=True)
class Advice:
    fixed_on: tuple[str, ...]
    base_has_fix: Optional[bool]
    suggested_targets: tuple[str, ...]


def title_core(title: str) -> str:
    t = _PREFIX.sub("", title, count=1)
    while True:
        t2 = _TRAILING_NUM.sub("", t)
        if t2 == t:
            break
        t = t2
    return re.sub(r"\s+", " ", t).strip().lower()


def referenced_numbers(title: str) -> tuple[int, ...]:
    return tuple(int(n) for n in _ANY_NUM.findall(title))


def parse_pr_ref(s: str, default_repo: Optional[str] = None) -> Optional[tuple[str, int]]:
    s = s.strip()
    for rx in (_URL, _SHORT):
        m = rx.match(s)
        if m:
            return (m.group(1), int(m.group(2)))
    m = _BARE.match(s)
    if m and default_repo:
        return (default_repo, int(m.group(1)))
    return None


def pr_meta_from_gh(repo: str, j: dict) -> PrMeta:
    mc = j.get("mergeCommit") or {}
    return PrMeta(repo, int(j["number"]), j.get("title", ""), j.get("state", "UNKNOWN"),
                  j.get("baseRefName"), mc.get("oid"), j.get("mergedAt"))


FAMILY_SEARCH_LIMIT = 30


def enumerate_family_prs(core: str, repos: tuple, run: Callable[[list], tuple[int, str]]) -> tuple:
    """按标题核心到各仓库搜 PR（含 CLOSED），只保留标题核心完全一致的。"""
    out = []
    query = core.split("(", 1)[-1].split(")", 1)[-1].strip() or core  # 去掉 [fix](area) 标签，搜正文
    for repo in repos:
        rc, raw = run(["gh", "pr", "list", "--repo", repo, "--state", "all", "--limit", str(FAMILY_SEARCH_LIMIT),
                       "--search", f"{query} in:title", "--json", "number,title,state,baseRefName,mergeCommit,mergedAt"])
        if rc != 0:
            continue
        try:
            rows = json.loads(raw)
        except ValueError:
            continue
        out += [pr_meta_from_gh(repo, r) for r in rows if title_core(r.get("title", "")) == core]
    return tuple(out)


def gh_pr_view(repo: str, number: int, run: Callable[[list], tuple[int, str]]) -> PrMeta:
    rc, out = run(["gh", "pr", "view", str(number), "--repo", repo, "--json",
                   "number,title,state,mergedAt,baseRefName,mergeCommit"])
    if rc != 0:
        raise RuntimeError(f"gh pr view {repo}#{number} failed: {out.strip()[:300]}")
    try:
        return pr_meta_from_gh(repo, json.loads(out))
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"gh pr view {repo}#{number} 返回非预期内容: {e}") from e


def release_tags_sorted(tags: list) -> list:
    """只保留发布 tag（含 rc），按 家族(cloud>doris>裸) + 版本降序。"""
    rows = []
    for t in tags:
        m = _RELEASE_TAG.match(t.strip())
        if not m:
            continue
        vt = tuple(int(x) for x in m.group(2).split("."))
        vt = vt + (0,) * (_TAG_SEGMENTS - len(vt))
        rows.append((_FAMILY_RANK[m.group(1)], tuple(-x for x in vt), t.strip()))
    return [r[2] for r in sorted(rows)]


def tags_containing(sha: str, git_run: GitRun, cwd: str, limit: int = 4) -> list:
    rc, out = git_run(["tag", "--contains", sha], cwd)
    return release_tags_sorted(out.split())[:limit] if rc == 0 else []


def match_hits(core: str, log_lines: list) -> tuple[Hit, ...]:
    """log 行格式 `<sha>\\x00<subject>`；只有标题核心一致才算命中（PR 号会跨仓库撞号）。"""
    hits = []
    for line in log_lines:
        if "\x00" not in line:
            continue
        sha, subject = line.split("\x00", 1)
        if title_core(subject) == core:
            hits.append(Hit("picked", sha.strip(), subject.strip()))
    return tuple(hits)


def _is_ancestor(git_run: GitRun, cwd: str, sha: str, branch: str) -> bool:
    rc, _ = git_run(["merge-base", "--is-ancestor", sha, f"origin/{branch}"], cwd)
    return rc == 0


def _grep_branch(git_run: GitRun, cwd: str, branch: str, core: str) -> list:
    rc, out = git_run(["log", f"origin/{branch}", "-i", "--fixed-strings", f"--grep={core}",
                       "--format=%H%x00%s", "-n", "20"], cwd)
    return out.splitlines() if rc == 0 else []


def containment(pr: PrMeta, branches: tuple[str, ...], git_run: GitRun, cwd: str) -> dict:
    core = title_core(pr.title)
    result = {}
    for br in branches:
        direct = bool(pr.merge_sha) and _is_ancestor(git_run, cwd, pr.merge_sha, br)
        picks = match_hits(core, _grep_branch(git_run, cwd, br, core)) if core else ()
        shas = tuple(dict.fromkeys(([pr.merge_sha] if direct else []) + [h.sha for h in picks]))
        if not shas:
            result[br] = Hit("missing", None, None)
            continue
        tags = release_tags_sorted([t for sha in shas for t in tags_containing(sha, git_run, cwd, limit=99)])
        first = Hit("direct", pr.merge_sha, None) if direct else picks[0]
        result[br] = Hit(first.kind, first.sha, first.subject, tuple(dict.fromkeys(tags))[:4], shas)
    return result


def pick_advice(base_branch: Optional[str], matrix: dict) -> Advice:
    fixed = tuple(b for b, h in matrix.items() if h.kind in ("direct", "picked"))
    if base_branch is None:
        return Advice(fixed, None, ())
    has = base_branch in fixed
    return Advice(fixed, has, () if has else (base_branch,))
