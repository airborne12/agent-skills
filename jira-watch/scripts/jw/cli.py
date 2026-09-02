"""CLI 编排层：把纯函数串成子命令。副作用都经 Ctx 注入，便于测试。"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jw import classify, events, jira_api, notify, parse, prchain, versions, writes
from jw.ctx import Ctx, attachment_url_allowed, fetch_needed, git_run, redact, safe_attachment_name, sh_run  # noqa: F401
from jw.render import render_pick_advice  # noqa: F401

ISSUE_REF_HOPS_MAX = 5        # 追引用 issue 的最大个数
CHAIN_LIMIT = 12              # 修复族展开的最大 PR 数
ATTACHMENT_MAX_BYTES = 200 * 1024 * 1024
SNAPSHOT_COLLAPSE_RATIO = 0.5  # 轮询结果少于快照一半视为异常（分页/JQL 出错），拒绝落快照
OP_LOCK_STALE_S = 600


# ---------- 纯函数 ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def round_id(now_iso: str) -> str:
    return now_iso


def idem_key(rid: str) -> str:
    return f"jira-watch-{rid}"


def enterprise_version(commit_versions: list) -> Optional[str]:
    return next((v.split("-", 1)[1] for v in commit_versions if v.startswith("enterprise-")), None)


def merge_pending(pending: list, fresh: list, handled: frozenset) -> list:
    """上轮未 ack 的事件 + 本轮新事件，去重并过滤已处理。"""
    seen, out = set(), []
    for e in list(pending) + list(fresh):
        if e["event_id"] in handled or e["event_id"] in seen:
            continue
        seen.add(e["event_id"]); out.append(e)
    return out


def _comment_rows(issue: dict) -> list:
    return (issue.get("fields", {}).get("comment") or {}).get("comments", [])


def _texts(issue: dict) -> list:
    f = issue.get("fields", {})
    rows = [("description", "description", f.get("description") or "", (f.get("reporter") or {}).get("name", ""))]
    rows += [("comment", c["id"], c.get("body") or "", (c.get("author") or {}).get("name", "")) for c in _comment_rows(issue)]
    return rows


def enrich_issue(issue: dict, me: str, bot_users: tuple, ci_bot_users: tuple,
                 projects: tuple = (), pr_owners: tuple = parse.DEFAULT_PR_OWNERS) -> dict:
    """在原始 issue JSON 之外派生：分类、AI 分析、CI 巡检、PR/SHA/Jira 引用、@我。"""
    f = issue.get("fields", {})
    cls = classify.classify(issue)
    ai, ci, prs, refs, shas, commits, mentions = [], [], [], [], [], [], []
    for kind, cid, body, author in _texts(issue):
        prs += [{"repo": r.repo, "number": r.number, "url": r.url, "by": author, "comment_id": cid} for r in parse.extract_pr_refs(body, pr_owners)]
        refs += parse.extract_issue_refs(body, exclude=issue["key"], projects=projects)
        commits += parse.be_commits(body)
        shas += [s for s in parse.extract_shas(body) if s not in commits]
        if parse.mentions_user(body, me):
            mentions.append(cid)
        if kind == "comment" and author in bot_users:
            a = parse.parse_ai_analysis(body)
            if a and not a.is_placeholder:
                ai.append({"comment_id": cid, **asdict(a), "pr_refs": [asdict(p) for p in a.pr_refs]})
        if kind == "comment" and author in ci_bot_users:
            c = parse.parse_ci_inspection(body)
            if c:
                ci.append({"comment_id": cid, **asdict(c)})
    return {
        "key": issue["key"], "summary": f.get("summary"), "status": (f.get("status") or {}).get("name"),
        "project": (f.get("project") or {}).get("key"), "issuetype": (f.get("issuetype") or {}).get("name"),
        "updated": f.get("updated"), "labels": list(f.get("labels") or []),
        "versions": list(cls.versions), "classification": asdict(cls),
        "be_commits": list(dict.fromkeys(commits)), "sha_refs": list(dict.fromkeys(shas)),
        "ai_analyses": ai, "ci_inspections": ci, "pr_refs": list({(p["repo"], p["number"]): p for p in prs}.values()),
        "issue_refs": list(dict.fromkeys(refs)), "mentions_me": mentions,
        "attachments": [{"filename": a.get("filename"), "size": a.get("size"), "url": a.get("content")} for a in f.get("attachment") or []],
        "description": f.get("description") or "",
        "comments": [{"id": c["id"], "author": (c.get("author") or {}).get("name"), "created": c.get("created"),
                      "updated": c.get("updated"), "body": c.get("body")} for c in _comment_rows(issue)],
    }


def _semantic_kind(ev: events.Event, enriched: dict) -> Optional[str]:
    if ev.kind != "NEW_COMMENT":
        return None
    cid = ev.detail.get("comment_id")
    if any(a["comment_id"] == cid for a in enriched.get("ai_analyses", [])):
        return "AI_ANALYSIS_READY"
    if any(c["comment_id"] == cid for c in enriched.get("ci_inspections", [])):
        return "CI_INSPECTION"
    if cid in enriched.get("mentions_me", []):
        return "MENTIONED_ME"
    return None


def derive_events(raw: tuple, enriched_by_key: dict) -> list:
    out = []
    for ev in raw:
        d = ev.to_dict()
        sem = _semantic_kind(ev, enriched_by_key.get(ev.key, {}))
        out.append({**d, "kind": sem or d["kind"], "raw_kind": d["kind"]})
    return out


# ---------- 读类命令 ----------

def _enrich(ctx: Ctx, issue: dict) -> dict:
    return ctx.cache_issue(enrich_issue(issue, ctx.cfg.jira_user, ctx.cfg.bot_users, ctx.cfg.ci_bot_users,
                                        ctx.cfg.projects, ctx.cfg.pr_owners))


def cmd_poll(ctx: Ctx, jql: Optional[str]) -> dict:
    issues = ctx.client.search(jql or ctx.cfg.jql)
    return {"total": len(issues), "issues": [_enrich(ctx, i) for i in issues]}


def cmd_baseline(ctx: Ctx, jql: Optional[str]) -> dict:
    issues = ctx.client.search(jql or ctx.cfg.jql)
    events.save_snapshot(ctx.snapshot_path, {i["key"]: events.digest_from_issue(i) for i in issues})
    for i in issues:
        _enrich(ctx, i)
    return {"baseline_issues": len(issues), "snapshot": str(ctx.snapshot_path)}


def _load_pending(ctx: Ctx) -> list:
    try:
        return json.loads(ctx.pending_path.read_text(encoding="utf-8")) if ctx.pending_path.exists() else []
    except (ValueError, OSError):
        ctx.add_gap("pending_events.json 损坏，已忽略")
        return []


def cmd_events(ctx: Ctx, jql: Optional[str], dry: bool, force: tuple = ()) -> dict:
    prev = events.load_snapshot(ctx.snapshot_path)
    if not prev:
        return {"error": "无基线快照（或快照损坏）；先运行 baseline（首轮只建基线不处理存量）"}
    issues = ctx.client.search(jql or ctx.cfg.jql)
    curr = {i["key"]: events.digest_from_issue(i) for i in issues}
    if len(curr) < len(prev) * SNAPSHOT_COLLAPSE_RATIO and len(prev) >= 4:
        return {"error": f"轮询结果 {len(curr)} 个远少于快照 {len(prev)} 个，疑似 JQL/分页异常，本轮不落快照不出事件"}
    raw = events.diff_snapshots(prev, curr) + tuple(events.Event("FORCED", k, {"by": "user"}) for k in force if k in curr)
    recs, bad = events.read_records(ctx.records_path)
    handled = events.handled_event_ids(recs)
    pending = _load_pending(ctx)
    touched = {e.key for e in raw} | {e["key"] for e in pending}
    enriched = {i["key"]: _enrich(ctx, i) for i in issues if i["key"] in touched}
    fresh = merge_pending(pending, derive_events(raw, enriched), handled)
    if not dry:
        events.save_snapshot(ctx.snapshot_path, curr)
        ctx.pending_path.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
    return {"round_id": round_id(now_iso()), "mode": ctx.mode, "polled": len(issues), "events": fresh,
            "carried_over": len([e for e in pending if e["event_id"] not in handled]),
            "dangling_intents": list(events.dangling_intents(recs)), "corrupt_records": bad,
            "issues": enriched, "gaps": ctx.gaps}


def cmd_issue(ctx: Ctx, key: str) -> dict:
    return _enrich(ctx, ctx.client.issue(key))


def _resolve_all(ctx: Ctx, version_raw: str, no_fetch: bool) -> dict:
    pv = parse.parse_version(version_raw)
    if not pv:
        return {"error": f"无法解析版本 {version_raw!r}（需形如 cloud-26.0.4 / 2.1.7）"}
    out = {}
    for repo, path in ctx.cfg.repo_paths.items():
        ctx.ensure_fresh(repo, no_fetch)
        out[repo] = versions.resolve_version(repo, pv.product, pv.version, ctx.cfg.release_branches[repo], ctx.git, path)
    return {"version": version_raw, "product": pv.product, "parsed": pv.version, "by_repo": out}


def cmd_resolve_version(ctx: Ctx, version_raw: str, no_fetch: bool) -> dict:
    return _resolve_all(ctx, version_raw, no_fetch)


def _expand_chain(ctx: Ctx, seeds: list, speculative: list = ()) -> list:
    """seed PR + 推测 seed（SHA 反查）+ 标题里引用的 PR（一跳，跨仓库候选），去重；只有显式 seed 失败才暴露。"""
    seed_set, seen, out, queue = set(seeds), set(), [], list(seeds) + [s for s in speculative if s not in seeds]
    while queue and len(out) < CHAIN_LIMIT:
        repo, number = queue.pop(0)
        if (repo, number) in seen:
            continue
        seen.add((repo, number))
        try:
            meta = prchain.gh_pr_view(repo, number, ctx.sh)
        except RuntimeError as e:
            if (repo, number) in seed_set or "Could not resolve" not in str(e):
                ctx.add_gap(str(e))
            continue
        out.append(meta)
        for n in prchain.referenced_numbers(meta.title):
            queue.extend((r, n) for r in prchain.candidate_repos_for_number(repo) if (r, n) not in seen)
    return out


def _matrix(ctx: Ctx, pr: prchain.PrMeta, no_fetch: bool, extra: Optional[dict] = None) -> dict:
    m = {}
    for repo in prchain.matrix_repos(pr.repo, tuple(ctx.cfg.repo_paths)):
        ctx.ensure_fresh(repo, no_fetch)
        branches = tuple(dict.fromkeys(ctx.cfg.release_branches[repo] + (extra or {}).get(repo, ())))
        m[repo] = {br: asdict(h) for br, h in prchain.containment(pr, branches, ctx.git, ctx.cfg.repo_paths[repo]).items()}
    return m


def cmd_pr_chain(ctx: Ctx, refs: list, no_fetch: bool) -> dict:
    seeds = [s for s in (prchain.parse_pr_ref(r, default_repo="apache/doris") for r in refs) if s]
    return {"prs": [{**asdict(p), "url": p.url, "matrix": _matrix(ctx, p, no_fetch)} for p in _expand_chain(ctx, seeds)],
            "gaps": ctx.gaps}


def _hotfix_branches(ctx: Ctx, version: str) -> list:
    path = ctx.cfg.repo_paths.get("example-org/internal-core")
    if not path:
        return []
    rc, out = ctx.git(["branch", "-r", "--list", f"origin/branch-hotfix-internal-cloud-{version}*"], path)
    return [l.strip().replace("origin/", "", 1) for l in out.splitlines() if l.strip()] if rc == 0 else []


def _resolve_commit(ctx: Ctx, commits: list, no_fetch: bool) -> dict:
    out = {}
    for repo, path in ctx.cfg.repo_paths.items():
        ctx.ensure_fresh(repo, no_fetch)
        for c in commits:
            r = versions.resolve_ref(repo, c, ctx.cfg.release_branches[repo], ctx.git, path)
            if r["ref"]:
                out[repo] = r
                break
    return out


def _effective_base(by_version: dict, by_commit: dict) -> dict:
    merged = {}
    for repo in set(by_version) | set(by_commit):
        c, v = by_commit.get(repo), by_version.get(repo)
        if c and c.get("base_branch"):
            merged[repo] = {**c, "source": "be_commit"}
        elif v:
            merged[repo] = {**v, "source": "version_field"}
    return merged


SHA_REPO_PRIORITY = ("apache/doris", "example-org/internal-core")  # internal-core 克隆含 apache 远端提交，先归 doris


def _seeds_from_shas(ctx: Ctx, shas: list) -> list:
    """评论里的裸 SHA → 本地仓库里的提交主题 → 尾部 (#N) → PR seed（推测性，每个 SHA 只归第一个命中的仓库）。"""
    seeds = []
    repos = [r for r in SHA_REPO_PRIORITY if r in ctx.cfg.repo_paths] + [r for r in ctx.cfg.repo_paths if r not in SHA_REPO_PRIORITY]
    for sha in shas:
        for repo in repos:
            rc, full = ctx.git(["rev-parse", "-q", "--verify", f"{sha}^{{commit}}"], ctx.cfg.repo_paths[repo])
            if rc != 0:
                continue
            _, subject = ctx.git(["log", "-1", "--format=%s", full.strip()], ctx.cfg.repo_paths[repo])
            nums = prchain.referenced_numbers(subject)
            if nums:
                seeds.append((repo, nums[-1]))
            break
    return list(dict.fromkeys(seeds))


def _collect_seeds(ctx: Ctx, e: dict, hops: int) -> tuple:
    """返回 (显式 seed, 推测 seed, 来源表)。"""
    prs = [(p["repo"], p["number"]) for p in e["pr_refs"]]
    sources = {(p["repo"], p["number"]): e["key"] for p in e["pr_refs"]}
    speculative = _seeds_from_shas(ctx, e.get("sha_refs", []))
    for s in speculative:
        sources.setdefault(s, f"{e['key']}(sha)")
    for ref in (e["issue_refs"][:ISSUE_REF_HOPS_MAX] if hops else []):
        try:
            other = cmd_issue(ctx, ref)
        except jira_api.JiraError as ex:
            ctx.add_gap(f"{ref}: {ex}")
            continue
        for p in other["pr_refs"]:
            prs.append((p["repo"], p["number"])); sources.setdefault((p["repo"], p["number"]), ref)
    return list(dict.fromkeys(prs)), speculative, sources


def _resolve_bases(ctx: Ctx, e: dict, no_fetch: bool) -> tuple:
    version = e["versions"][0] if e["versions"] else None
    resolved = _resolve_all(ctx, version, no_fetch) if version else {}
    if resolved.get("error"):
        ctx.add_gap(resolved["error"])
    by_commit = _resolve_commit(ctx, e.get("be_commits", []), no_fetch)
    commit_versions = [v for r in by_commit.values() for v in r.get("versions", [])]
    ev, doris = enterprise_version(commit_versions), ctx.cfg.repo_paths.get("apache/doris")
    if ev and doris and "apache/doris" not in by_commit:
        by_commit = {**by_commit, "apache/doris": {**versions.resolve_version("apache/doris", "enterprise", ev, ctx.cfg.release_branches["apache/doris"], ctx.git, doris),
                                                    "subject": f"enterprise-{ev}（来自 BE commit 的 Bump 提交）"}}
    effective = next((v for v in commit_versions if v.startswith("cloud-")), None) or version
    return version, _effective_base(resolved.get("by_repo", {}), by_commit), commit_versions, effective


def _family_rows(ctx: Ctx, metas: list, base: dict, no_fetch: bool, extra: dict, sources: dict) -> list:
    rows = []
    for fam in prchain.group_families(metas):
        members = list(fam.members) + [p for p in prchain.enumerate_family_prs(fam.core, tuple(ctx.cfg.repo_paths), ctx.sh)
                                       if (p.repo, p.number) not in {(m.repo, m.number) for m in fam.members}]
        matrix = _matrix(ctx, fam.origin, no_fetch, extra)
        advice = {repo: asdict(prchain.pick_advice(base.get(repo, {}).get("base_branch"), {br: prchain.Hit(**h) for br, h in matrix[repo].items()}))
                  for repo in matrix}
        rows.append({"core": fam.core, "origin": {**asdict(fam.origin), "url": fam.origin.url},
                     "members": [{**asdict(m), "url": m.url, "source_issue": sources.get((m.repo, m.number))} for m in members],
                     "matrix": matrix, "advice": advice})
    return rows


def cmd_pick_advice(ctx: Ctx, key: str, no_fetch: bool, hops: int = 1) -> dict:
    e = cmd_issue(ctx, key)
    seeds, speculative, sources = _collect_seeds(ctx, e, hops)
    version, base, commit_versions, effective = _resolve_bases(ctx, e, no_fetch)
    pv = parse.parse_version(effective) if effective else None
    hotfix = _hotfix_branches(ctx, pv.version) if pv and pv.product == "cloud" else []
    families = _family_rows(ctx, _expand_chain(ctx, seeds, speculative), base, no_fetch, {"example-org/internal-core": tuple(hotfix)}, sources)
    adv = {"issue": key, "version": version, "be_commits": e.get("be_commits", []), "sha_refs": e.get("sha_refs", []),
           "commit_versions": commit_versions, "effective_version": effective,
           "version_mismatch": bool(version and commit_versions and version not in commit_versions),
           "base": base, "families": families, "hotfix_branches": hotfix, "issue_refs": e["issue_refs"],
           "ai_analyses": [{k: a[k] for k in ("comment_id", "judgment", "confidence", "issue_refs")} for a in e["ai_analyses"]],
           "gaps": ctx.gaps}
    return {**adv, "text": render_pick_advice(adv)}


# ---------- 写类命令（模式守卫在最前） ----------

def _refuse(ctx: Ctx, key: str, action: str, why: str, event_ids: tuple) -> dict:
    ctx.record({"ts": now_iso(), "key": key, "type": "PENDING_USER", "action": action, "phase": "REFUSED",
                "event_id": event_ids[0] if event_ids else None, "event_ids": list(event_ids), "evidence": why})
    return {"refused": True, "why": why}


def cmd_comment(ctx: Ctx, key: str, body_file: str, event_ids: tuple, dry: bool) -> dict:
    body = writes.strip_scores(Path(body_file).read_text(encoding="utf-8"))
    slot = writes.slot_id(key, event_ids)
    full = writes.build_comment(body, slot, ctx.cfg.jira_user)
    if dry:
        return {"dry_run": True, "slot": slot, "mode": ctx.mode, "body": full}
    if ctx.mode != "INTERACT":
        return _refuse(ctx, key, "COMMENT", f"模式 {ctx.mode} 不允许回写 Jira；草稿在 {body_file}（slot {slot}）", event_ids)
    existing = writes.find_existing_slot(ctx.client.comments(key), slot)
    if existing:
        return {"skipped": True, "why": f"远端已存在同 slot 评论 id={existing['id']}", "slot": slot}
    intent = writes.intent_record(key, "COMMENT", event_ids, slot, now_iso(), {"mode": ctx.mode, "mode_source": ctx.mode_source})
    ctx.record(intent)
    resp = ctx.client.add_comment(key, full)
    ctx.record(writes.result_record(intent, now_iso(), f"comment id={resp.get('id')} created={resp.get('created')}"))
    return {"ok": True, "comment_id": resp.get("id"), "slot": slot}


def cmd_transition(ctx: Ctx, key: str, target: str, event_ids: tuple, dry: bool, comment: Optional[str]) -> dict:
    if ctx.mode != "INTERACT":
        return _refuse(ctx, key, "TRANSITION", f"模式 {ctx.mode} 不允许流转状态（目标 {target}）", event_ids)
    if not writes.transition_allowed(target, ctx.cfg.allowed_transitions):
        return _refuse(ctx, key, "TRANSITION", f"目标状态 {target} 不在白名单 {ctx.cfg.allowed_transitions}", event_ids)
    trans = ctx.client.transitions(key)
    tid = writes.pick_transition_id(trans, target)
    if not tid:
        return {"error": f"当前状态无法流转到 {target}", "available": [t.get("name") for t in trans]}
    if dry:
        return {"dry_run": True, "transition_id": tid, "target": target}
    intent = writes.intent_record(key, "TRANSITION", event_ids, None, now_iso(), {"mode": ctx.mode, "mode_source": ctx.mode_source, "target": target})
    ctx.record(intent)
    ctx.client.do_transition(key, tid, comment)
    after = (ctx.client.issue(key, ("status",)).get("fields", {}).get("status") or {}).get("name")
    ctx.record(writes.result_record(intent, now_iso(), f"status now {after}"))
    return {"ok": True, "status": after}


def cmd_notify(ctx: Ctx, file: str, rid: str, dry: bool) -> dict:
    text = Path(file).read_text(encoding="utf-8")
    args = notify.lark_send_args(ctx.cfg.lark_open_id, text, idem_key(rid))
    if dry:
        return {"dry_run": True, "args": args[:-1] + ["<idem>"]}
    rc, out = ctx.sh(args)
    ctx.record({"ts": now_iso(), "key": "-", "type": "notify", "action": "LARK_DM", "phase": "RESULT",
                "event_id": f"notify-{rid}", "evidence": out.strip()[:300], "ok": rc == 0})
    return {"ok": rc == 0, "output": out.strip()[:500]}


def cmd_attachments(ctx: Ctx, key: str, out_dir: Optional[str]) -> dict:
    import requests
    e = cmd_issue(ctx, key)
    dest = events.ensure_private_dir(Path(out_dir or (ctx.state / "attachments" / key)))
    s = requests.Session(); s.trust_env = False
    saved = []
    for a in e["attachments"]:
        if not a.get("url") or not attachment_url_allowed(a["url"], ctx.cfg.jira_url):
            ctx.add_gap(f"跳过非本站附件 URL：{str(a.get('url'))[:80]}")
            continue
        p = dest / safe_attachment_name(a["filename"])
        with s.get(a["url"], headers=jira_api.auth_headers(ctx.cfg.jira_token), timeout=300, stream=True) as r:
            r.raise_for_status()
            with p.open("wb") as fh:
                total = 0
                for chunk in r.iter_content(1 << 20):
                    total += len(chunk)
                    if total > ATTACHMENT_MAX_BYTES:
                        raise ValueError(f"附件超过 {ATTACHMENT_MAX_BYTES} 字节：{a['filename']}")
                    fh.write(chunk)
        saved.append(str(p))
    return {"saved": saved, "gaps": ctx.gaps}
