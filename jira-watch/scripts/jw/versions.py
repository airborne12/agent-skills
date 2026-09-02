"""版本 → tag 候选 → 最近基线分支。git 调用通过 git_run 注入，便于测试。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

_BUMP = re.compile(r"\b(cloud|enterprise)-(\d+(?:\.\d+)+)\b")

GitRun = Callable[[list, str], tuple[int, str]]


@dataclass(frozen=True)
class Distance:
    branch_ahead: int  # 分支领先 tag 的提交数
    tag_ahead: int     # tag 领先分支的提交数（0 = tag 完全包含于分支）


@dataclass(frozen=True)
class BranchMatch:
    branch: str
    branch_ahead: int
    tag_ahead: int


def tag_candidates(repo: str, product: str, version: str) -> tuple[str, ...]:
    if repo == "apache/doris":
        return () if product == "cloud" else (version, f"branch-{version}")
    prefix = "tag-internal-cloud-" if product == "cloud" else "tag-internal-doris-"
    return (f"{prefix}{version}", version)


def nearest_branch(distances: dict) -> Optional[BranchMatch]:
    if not distances:
        return None
    branch, d = min(distances.items(), key=lambda kv: (kv[1].tag_ahead, kv[1].branch_ahead))
    return BranchMatch(branch, d.branch_ahead, d.tag_ahead)


def series_of(version: str) -> str:
    parts = version.split(".")
    return ".".join(parts[:2])


def _vtuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def nearest_series_tag(tags: list, prefix: str, version: str) -> Optional[str]:
    """同 major.minor 系列里 ≤ 请求版本的最高 tag（排除 -rc/-hotfix 等后缀）。"""
    want = _vtuple(version)
    series = want[:2]
    best = None
    for t in tags:
        if not t.startswith(prefix):
            continue
        v = t[len(prefix):]
        if not v.replace(".", "").isdigit():
            continue
        vt = _vtuple(v)
        if vt[:2] != series or vt > want:
            continue
        if best is None or vt > _vtuple(best[len(prefix):]):
            best = t
    return best


def _fallback_ref(git_run: GitRun, cwd: str, candidates: tuple, version: str) -> Optional[str]:
    for cand in candidates:
        prefix = cand[: len(cand) - len(version)] if cand.endswith(version) else None
        if prefix is None:
            continue
        rc, out = git_run(["tag", "--list", f"{prefix}{series_of(version)}.*"], cwd)
        if rc != 0:
            continue
        hit = nearest_series_tag(out.split(), prefix, version)
        if hit:
            return hit
    return None


def _ref_exists(git_run: GitRun, cwd: str, ref: str) -> bool:
    rc, _ = git_run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd)
    return rc == 0


def _count(git_run: GitRun, cwd: str, a: str, b: str) -> Optional[int]:
    rc, out = git_run(["rev-list", "--count", a, f"^{b}"], cwd)
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else None


def _distances(git_run: GitRun, cwd: str, ref: str, branches: tuple[str, ...]) -> dict:
    out = {}
    for br in branches:
        remote = f"origin/{br}"
        branch_ahead = _count(git_run, cwd, remote, ref)
        tag_ahead = _count(git_run, cwd, ref, remote)
        if branch_ahead is None or tag_ahead is None:
            continue
        out[br] = Distance(branch_ahead, tag_ahead)
    return out


def resolve_version(repo: str, product: str, version: str, release_branches: tuple[str, ...],
                    git_run: GitRun, cwd: str) -> dict:
    """返回 {ref, base_branch, confidence, distances, series_hint}。找不到 ref 时 confidence=none。"""
    candidates = tag_candidates(repo, product, version)
    ref = next((c for c in candidates if _ref_exists(git_run, cwd, c)), None)
    fallback = False
    if ref is None:
        ref = _fallback_ref(git_run, cwd, candidates, version)
        fallback = ref is not None
    hint = f"{series_of(version)} 系列（按版本号推断，未经 git 核实）"
    if ref is None:
        return {"repo": repo, "ref": None, "ref_is_fallback": False, "base_branch": None, "confidence": "none",
                "distances": {}, "series_hint": hint, "candidates": list(candidates)}
    dist = _distances(git_run, cwd, ref, release_branches)
    match = nearest_branch(dist)
    confidence = "high" if match and match.tag_ahead == 0 else ("medium" if match and match.tag_ahead <= 50 else "low")
    if fallback and confidence == "high":
        confidence = "medium"
    return {
        "repo": repo,
        "ref": ref,
        "ref_is_fallback": fallback,
        "base_branch": match.branch if match else None,
        "confidence": confidence if match else "none",
        "distances": {k: {"branch_ahead": v.branch_ahead, "tag_ahead": v.tag_ahead} for k, v in dist.items()},
        "series_hint": hint,
        "candidates": list(candidates),
    }


def versions_from_bump_subject(subject: str) -> tuple:
    return tuple(f"{a}-{b}" for a, b in _BUMP.findall(subject))


def _confidence(match: Optional[BranchMatch]) -> str:
    if not match:
        return "none"
    return "high" if match.tag_ahead == 0 else ("medium" if match.tag_ahead <= 50 else "low")


def resolve_ref(repo: str, ref: str, release_branches: tuple, git_run: GitRun, cwd: str) -> dict:
    """任意 ref（通常是崩溃栈里的 BE commit）→ 所在版本 tag、Bump 提交主题、最近基线分支。"""
    rc, out = git_run(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd)
    if rc != 0:
        return {"repo": repo, "ref": None, "base_branch": None, "confidence": "none", "subject": None, "tags_at": [], "distances": {}}
    full = out.strip()
    _, subject = git_run(["log", "-1", "--format=%s", full], cwd)
    _, tags = git_run(["tag", "--points-at", full], cwd)
    dist = _distances(git_run, cwd, full, release_branches)
    match = nearest_branch(dist)
    return {
        "repo": repo, "ref": ref, "subject": subject.strip(), "tags_at": sorted(tags.split()),
        "base_branch": match.branch if match else None, "confidence": _confidence(match),
        "distances": {k: {"branch_ahead": v.branch_ahead, "tag_ahead": v.tag_ahead} for k, v in dist.items()},
        "versions": list(versions_from_bump_subject(subject)),
    }
