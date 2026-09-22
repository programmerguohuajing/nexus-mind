from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nexusmind import __version__
from nexusmind.core.web_ingest import extract_web_page

app = FastAPI(title="NexusMind Cloud", version=__version__)
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


class ReadRequest(BaseModel):
    path: str


class PatchRequest(BaseModel):
    path: str
    content: str
    ifMatch: str | None = None


class SearchRequest(BaseModel):
    query: str = ""
    folder: str | None = None
    limit: int = 50
class IngestRequest(BaseModel):
    title: str
    content: str
    author: str = "Unknown"
    url: str | None = None
    folder: str = "60-References/Articles"


class WebIngestRequest(BaseModel):
    url: str
    author: str = "Unknown"
    folder: str = "60-References/Articles"


class ReviewRequest(BaseModel):
    week: str | None = None
    author_scope: str = "current_user"


class GitUser(BaseModel):
    name: str = ""
    email: str = ""


class GitCommit(BaseModel):
    hash: str
    short: str = ""
    authored_at: str = ""
    author: str = ""
    author_email: str = ""
    subject: str = ""
    is_merge: bool = False


class GitTag(BaseModel):
    name: str
    created_at: str = ""
    target_author_email: str = ""


class GitRepositoryEvent(BaseModel):
    name: str
    branch: str = ""
    remote: str = ""
    current_user: GitUser = Field(default_factory=GitUser)
    commits: list[GitCommit] = Field(default_factory=list)
    tags: list[GitTag] = Field(default_factory=list)


class GitSyncRequest(BaseModel):
    day: str
    synced_at: str
    repositories: list[GitRepositoryEvent] = Field(default_factory=list)


class CloudVaultPullRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)


class CloudVaultNote(BaseModel):
    path: str
    content: str
    base_version: str | None = None


class CloudVaultDelete(BaseModel):
    path: str
    base_version: str | None = None


class CloudVaultPushRequest(BaseModel):
    notes: list[CloudVaultNote] = Field(default_factory=list)
    deletions: list[CloudVaultDelete] = Field(default_factory=list)


def _env(request: Request):
    return request.scope["env"]


def _version(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_path(path: str) -> str:
    clean = str(PurePosixPath(path.replace("\\", "/"))).lstrip("/")
    if clean.startswith("../") or clean == "..":
        raise HTTPException(status_code=400, detail="Invalid path")
    return clean


async def _rows(stmt) -> list[dict[str, Any]]:
    raw = await stmt.raw(columnNames=True)
    if not raw:
        return []
    columns = [str(value) for value in raw[0]]
    return [dict(zip(columns, row)) for row in raw[1:]]


async def _note(env, path: str) -> dict[str, Any] | None:
    rows = await _rows(
        env.DB.prepare(
            "SELECT path, content, version, updated_at FROM notes WHERE path = ? LIMIT 1"
        ).bind(path)
    )
    return rows[0] if rows else None


async def _tombstone(env, path: str) -> dict[str, Any] | None:
    rows = await _rows(
        env.DB.prepare(
            "SELECT path, version, deleted_at FROM sync_tombstones WHERE path = ? LIMIT 1"
        ).bind(path)
    )
    return rows[0] if rows else None


async def _upsert_note(env, path: str, content: str, if_match: str | None = None):
    existing = await _note(env, path)
    if if_match == "NEW" and existing:
        raise HTTPException(status_code=412, detail="Note already exists")
    if if_match not in (None, "NEW") and (
        not existing or existing["version"] != if_match
    ):
        raise HTTPException(status_code=412, detail="Version mismatch")
    version = _version(content)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    await env.DB.prepare(
        """
        INSERT INTO notes(path, content, version, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          content = excluded.content,
          version = excluded.version,
          updated_at = excluded.updated_at
        """
    ).bind(path, content, version, now).run()
    await env.DB.prepare("DELETE FROM sync_tombstones WHERE path = ?").bind(path).run()
    return {"status": "success", "path": path, "version": version}


def _frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in content[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"')
    return result


@app.get("/api/runtime")
async def runtime_info():
    return {
        "mode": "cloudflare",
        "capabilities": {
            "local_filesystem": False,
            "git_collection": False,
            "folder_picker": False,
            "uploads": True,
            "knowledge_compile": False,
            "governance": False,
            "weekly_review": True,
            "cloud_git_ingest": True,
            "cloud_vault_sync": True,
        },
    }
@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__, "runtime": "cloudflare"}


@app.get("/api/dashboard")
async def dashboard(request: Request):
    env = _env(request)
    rows = await _rows(env.DB.prepare(
        """
        SELECT COUNT(*) AS notes,
          SUM(CASE WHEN path LIKE '40-Domain/%' THEN 1 ELSE 0 END) AS domain_notes,
          SUM(CASE WHEN path LIKE '60-References/%' THEN 1 ELSE 0 END) AS raw_sources
        FROM notes
        """
    ))
    row = rows[0] if rows else {}
    return {
        "status": "ok", "version": __version__, "vault": "cloudflare:d1",
        "notes": int(row.get("notes") or 0),
        "domain_notes": int(row.get("domain_notes") or 0),
        "raw_sources": int(row.get("raw_sources") or 0),
        "pending_compile": 0, "broken_links": 0, "orphans": 0,
        "recent_compilations": [],
    }


@app.post("/mcp/vault_read")
async def vault_read(req: ReadRequest, request: Request):
    env = _env(request)
    path = _normalize_path(req.path)
    note = await _note(env, path)
    if not note:
        raise HTTPException(status_code=404, detail="File not found")
    content = str(note["content"])
    return {
        "path": path, "version": note["version"], "content": content,
        "links": LINK_RE.findall(content), "backlinks": [],
        "frontmatter": _frontmatter(content),
        "tags": re.findall(r"(?<!\w)#[\w-]+", content),
    }
@app.post("/mcp/vault_patch")
async def vault_patch(req: PatchRequest, request: Request):
    path = _normalize_path(req.path)
    if path.startswith("60-References/"):
        raise HTTPException(status_code=403, detail="Raw layer is immutable")
    return await _upsert_note(_env(request), path, req.content, req.ifMatch)


@app.post("/mcp/vault_search")
async def vault_search(req: SearchRequest, request: Request):
    env = _env(request)
    pattern = f"%{req.query}%"
    folder_pattern = f"{req.folder.rstrip('/')}%" if req.folder else "%"
    rows = await _rows(env.DB.prepare(
        """
        SELECT path, content, version, updated_at FROM notes
        WHERE path LIKE ? AND (path LIKE ? OR content LIKE ?)
        ORDER BY updated_at DESC LIMIT ?
        """
    ).bind(folder_pattern, pattern, pattern, min(max(req.limit, 1), 100)))
    matches = [{
        "path": row["path"],
        "title": _frontmatter(str(row["content"])).get(
            "title", PurePosixPath(str(row["path"])).stem
        ),
        "snippet": str(row["content"])[:320],
        "version": row["version"],
    } for row in rows]
    return {
        "query": req.query,
        "folder": req.folder,
        "total": len(rows),
        "matches": matches,
        "results": matches,
    }


@app.get("/api/resolve-link")
async def resolve_link(target: str, request: Request):
    env = _env(request)
    target = target.split("#", 1)[0].strip()
    candidates = [target, target + ".md"] if not target.endswith(".md") else [target]
    for candidate in candidates:
        note = await _note(env, _normalize_path(candidate))
        if note:
            return {"status": "resolved", "target": target, "path": note["path"]}
    stem = PurePosixPath(target).stem
    rows = await _rows(env.DB.prepare(
        "SELECT path FROM notes WHERE path LIKE ? LIMIT 10"
    ).bind(f"%/{stem}.md"))
    if len(rows) == 1:
        return {"status": "resolved", "target": target, "path": rows[0]["path"]}
    if len(rows) > 1:
        return {"status": "ambiguous", "target": target,
                "matches": [row["path"] for row in rows]}
    raise HTTPException(status_code=404, detail="Wikilink target not found")
@app.get("/api/graph")
async def knowledge_graph(request: Request, folder: str | None = None):
    env = _env(request)
    pattern = f"{folder.rstrip('/')}%" if folder else "%"
    rows = await _rows(env.DB.prepare(
        "SELECT path, content FROM notes WHERE path LIKE ?"
    ).bind(pattern))
    paths = {str(row["path"]) for row in rows}
    stems = {PurePosixPath(path).stem: path for path in paths}
    nodes, edges, seen = [], [], set()
    for row in rows:
        path, content = str(row["path"]), str(row["content"])
        nodes.append({
            "id": path, "path": path,
            "title": _frontmatter(content).get("title", PurePosixPath(path).stem),
            "tags": re.findall(r"(?<!\w)#[\w-]+", content)[:8], "degree": 0,
        })
        for link in LINK_RE.findall(content):
            target = link if link.endswith(".md") else link + ".md"
            if target not in paths:
                target = stems.get(PurePosixPath(link).stem, "")
            key = (path, target)
            if target and target != path and key not in seen:
                seen.add(key)
                edges.append({"source": path, "target": target})
    degree = {node["id"]: 0 for node in nodes}
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    for node in nodes:
        node["degree"] = degree[node["id"]]
    return {"nodes": nodes, "edges": edges,
            "node_count": len(nodes), "edge_count": len(edges)}


@app.get("/api/canvases")
async def list_canvases():
    return {"total": 0, "items": []}
def _authorize_sync(request: Request, env) -> None:
    expected = str(getattr(env, "SYNC_TOKEN", "") or "")
    supplied = request.headers.get("authorization", "")
    if not expected or supplied != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid sync token")


@app.get("/api/cloud/vault/manifest")
async def cloud_vault_manifest(request: Request):
    env = _env(request)
    _authorize_sync(request, env)
    notes = await _rows(env.DB.prepare(
        "SELECT path, version, updated_at FROM notes ORDER BY path"
    ))
    tombstones = await _rows(env.DB.prepare(
        "SELECT path, version, deleted_at FROM sync_tombstones ORDER BY path"
    ))
    return {"status": "success", "notes": notes, "tombstones": tombstones}


@app.post("/api/cloud/vault/pull")
async def cloud_vault_pull(payload: CloudVaultPullRequest, request: Request):
    env = _env(request)
    _authorize_sync(request, env)
    if len(payload.paths) > 100:
        raise HTTPException(status_code=400, detail="Too many paths")
    notes = []
    for raw_path in payload.paths:
        path = _normalize_path(raw_path)
        note = await _note(env, path)
        if note:
            notes.append(note)
    return {"status": "success", "notes": notes}


@app.post("/api/cloud/vault/push")
async def cloud_vault_push(payload: CloudVaultPushRequest, request: Request):
    env = _env(request)
    _authorize_sync(request, env)
    if len(payload.notes) > 50 or len(payload.deletions) > 50:
        raise HTTPException(status_code=400, detail="Too many changes")
    results: list[dict[str, Any]] = []

    for item in payload.notes:
        path = _normalize_path(item.path)
        existing = await _note(env, path)
        incoming_version = _version(item.content)
        if existing and incoming_version == existing["version"]:
            results.append({"path": path, "status": "success", "operation": "upsert", "version": existing["version"]})
            continue
        if existing and item.base_version != existing["version"]:
            results.append({"path": path, "status": "conflict", "operation": "upsert", "remote_version": existing["version"]})
            continue
        if not existing and item.base_version not in (None, "", "NEW"):
            tomb = await _tombstone(env, path)
            results.append({"path": path, "status": "conflict", "operation": "upsert", "remote_version": tomb["version"] if tomb else None})
            continue
        saved = await _upsert_note(env, path, item.content)
        results.append({"path": path, "status": "success", "operation": "upsert", "version": saved["version"]})

    for item in payload.deletions:
        path = _normalize_path(item.path)
        existing = await _note(env, path)
        if existing and item.base_version != existing["version"]:
            results.append({"path": path, "status": "conflict", "operation": "delete", "remote_version": existing["version"]})
            continue
        if existing:
            await env.DB.prepare("DELETE FROM notes WHERE path = ?").bind(path).run()
        tomb = await _tombstone(env, path)
        if tomb and not existing:
            version = tomb["version"]
        else:
            deleted_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            version = _version(f"deleted:{path}:{deleted_at}")
            await env.DB.prepare(
                """
                INSERT INTO sync_tombstones(path, version, deleted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  version=excluded.version, deleted_at=excluded.deleted_at
                """
            ).bind(path, version, deleted_at).run()
        results.append({"path": path, "status": "success", "operation": "delete", "version": version})

    return {"status": "success", "results": results}


@app.post("/api/cloud/git-events")
async def ingest_git_events(payload: GitSyncRequest, request: Request):
    env = _env(request)
    _authorize_sync(request, env)
    statements = []
    for repo in payload.repositories:
        statements.append(env.DB.prepare(
            """
            INSERT INTO repositories(name, branch, remote, current_user_name,
              current_user_email, last_sync)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              branch=excluded.branch, remote=excluded.remote,
              current_user_name=excluded.current_user_name,
              current_user_email=excluded.current_user_email,
              last_sync=excluded.last_sync
            """
        ).bind(repo.name, repo.branch, repo.remote, repo.current_user.name,
               repo.current_user.email.lower(), payload.synced_at))
        for commit in repo.commits:
            statements.append(env.DB.prepare(
                """
                INSERT OR REPLACE INTO git_commits(
                  repository, hash, short_hash, authored_at, author_name,
                  author_email, subject, branch, collected_day
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ).bind(repo.name, commit.hash, commit.short, commit.authored_at,
                   commit.author, commit.author_email.lower(), commit.subject,
                   repo.branch, payload.day))
        for tag in repo.tags:
            statements.append(env.DB.prepare(
                """
                INSERT OR REPLACE INTO git_tags(
                  repository, name, created_at, target_author_email, collected_day
                ) VALUES (?, ?, ?, ?, ?)
                """
            ).bind(repo.name, tag.name, tag.created_at,
                   tag.target_author_email.lower(), payload.day))
    if statements:
        await env.DB.batch(statements)
    return {"status": "success", "repositories": len(payload.repositories),
            "commits": sum(len(r.commits) for r in payload.repositories),
            "tags": sum(len(r.tags) for r in payload.repositories)}
@app.get("/api/workflow")
async def workflow_status(request: Request):
    env = _env(request)
    rows = await _rows(env.DB.prepare(
        """
        SELECT r.name, r.branch, r.remote, r.current_user_name,
          r.current_user_email, r.last_sync, COUNT(c.hash) AS commit_count
        FROM repositories r LEFT JOIN git_commits c
          ON c.repository=r.name AND c.collected_day=date('now')
        GROUP BY r.name ORDER BY r.name
        """
    ))
    return {
        "configured": bool(rows), "targets": [], "repository_count": len(rows),
        "commit_count": sum(int(r.get("commit_count") or 0) for r in rows),
        "tag_count": 0,
        "repositories": [{
            "name": r["name"], "path": "cloud-sync", "branch": r["branch"],
            "remote": r["remote"],
            "current_user": {"name": r["current_user_name"],
                             "email": r["current_user_email"]},
            "commit_count": int(r.get("commit_count") or 0),
            "merge_count": 0, "tag_count": 0, "commits": [],
            "working_tree": {"dirty": False, "changed_count": 0,
                             "changed_files": []},
        } for r in rows],
        "daily_log": None,
    }


@app.get("/api/workflow/config")
async def workflow_config():
    return {"targets": [], "managed_by": "local-agent"}


@app.put("/api/workflow/config")
@app.post("/api/workflow/sync")
@app.get("/api/fs/directories")
async def local_only():
    raise HTTPException(
        status_code=409,
        detail="This operation is provided by the NexusMind Local Agent.",
    )
def _week_bounds(week: str | None) -> tuple[str, date, date]:
    if week:
        match = re.fullmatch(r"(\d{4})-W(\d{2})", week)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid ISO week")
        year, week_no = int(match.group(1)), int(match.group(2))
        start = date.fromisocalendar(year, week_no, 1)
        return week, start, start + timedelta(days=6)
    today = date.today()
    iso = today.isocalendar()
    start = date.fromisocalendar(iso.year, iso.week, 1)
    return f"{iso.year}-W{iso.week:02d}", start, start + timedelta(days=6)


def _review_commit_meta(subject: str) -> dict[str, str]:
    match = re.match(r"(?P<type>[\w-]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<title>.+)", subject)
    if not match:
        return {"type": "other", "scope": "", "title": subject.strip(), "category": "其他变更"}
    commit_type = match.group("type").lower()
    scope = (match.group("scope") or "").strip()
    labels = {
        "feat": "功能交付", "fix": "问题修复", "refactor": "架构重构",
        "perf": "性能优化", "ci": "CI / 发布工程", "build": "构建工程",
        "test": "测试质量", "docs": "文档沉淀", "chore": "工程维护",
    }
    category = labels.get(commit_type, "其他变更")
    if commit_type == "fix" and scope.lower() in {"security", "auth"}:
        category = "安全加固"
    if commit_type == "chore" and scope.lower() == "release":
        category = "版本发布"
    return {
        "type": commit_type,
        "scope": scope,
        "title": match.group("title").strip().rstrip("。"),
        "category": category,
    }


def _cloud_review_synthesis(commits: list[dict[str, Any]], tags: list[dict[str, Any]]) -> dict[str, Any]:
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for raw in commits:
        item = dict(raw)
        item.update(_review_commit_meta(str(raw["subject"])))
        by_repo.setdefault(str(raw["repository"]), []).append(item)

    tags_by_repo: dict[str, list[str]] = {}
    for item in tags:
        tags_by_repo.setdefault(str(item["repository"]), []).append(str(item["name"]))

    lines: list[str] = []
    categories: dict[str, int] = {}
    for repo, items in sorted(by_repo.items(), key=lambda pair: (-len(pair[1]), pair[0].lower())):
        scopes: dict[str, int] = {}
        titles: list[str] = []
        repo_categories: dict[str, int] = {}
        for item in items:
            category = item["category"]
            categories[category] = categories.get(category, 0) + 1
            repo_categories[category] = repo_categories.get(category, 0) + 1
            if item["scope"]:
                scopes[item["scope"]] = scopes.get(item["scope"], 0) + 1
            if item["title"] and item["title"] not in titles:
                titles.append(item["title"])

        focus_parts = [
            name for name, _ in sorted(scopes.items(), key=lambda pair: (-pair[1], pair[0]))
        ][:4]
        if not focus_parts:
            focus_parts = [
                name for name, _ in sorted(repo_categories.items(), key=lambda pair: (-pair[1], pair[0]))
            ][:3]
        focus = "、".join(focus_parts)
        highlights = "；".join(titles[:3])
        sentence = f"- **{repo}**："
        if focus:
            sentence += f"围绕 **{focus}** "
        sentence += f"归并 {len(items)} 个 Git 变更"
        if highlights:
            sentence += f"，形成 {highlights}"
        repo_tags = tags_by_repo.get(repo, [])
        if repo_tags:
            sentence += "；交付节点 " + "、".join(repo_tags)
        lines.append(sentence + "。")

    priority = ["版本发布", "功能交付", "安全加固", "问题修复", "架构重构", "性能优化", "CI / 发布工程", "构建工程", "测试质量", "文档沉淀"]
    active = [name for name in priority if categories.get(name)]
    outcomes = []
    if active:
        outcomes.append("本周工程成果主要集中在" + "、".join(active[:5]) + "。")
    if tags:
        outcomes.append(
            "形成明确发布节点：" + "、".join(
                f"{item['repository']} {item['name']}" for item in tags
            ) + "。"
        )
    if not outcomes:
        outcomes.append("当前数据不足以形成进一步成果结论，报告不做超出证据范围的推断。")
    return {"lines": lines, "outcomes": outcomes, "categories": categories}


@app.post("/mcp/vault_weekly_review")
async def weekly_review(req: ReviewRequest, request: Request):
    env = _env(request)
    week, start, end = _week_bounds(req.week)
    if req.author_scope not in {"current_user", "all_users"}:
        raise HTTPException(status_code=400, detail="author_scope must be current_user or all_users")

    if req.author_scope == "all_users":
        commit_sql = """
        SELECT c.repository, c.hash, c.short_hash, c.subject, c.author_name,
          c.author_email, r.current_user_email
        FROM git_commits c JOIN repositories r ON r.name=c.repository
        WHERE c.collected_day BETWEEN ? AND ?
        ORDER BY c.authored_at
        """
        tag_sql = """
        SELECT t.repository, t.name
        FROM git_tags t JOIN repositories r ON r.name=t.repository
        WHERE t.collected_day BETWEEN ? AND ?
        ORDER BY t.created_at
        """
    else:
        commit_sql = """
        SELECT c.repository, c.hash, c.short_hash, c.subject, c.author_name,
          c.author_email, r.current_user_email
        FROM git_commits c JOIN repositories r ON r.name=c.repository
        WHERE c.collected_day BETWEEN ? AND ?
          AND lower(c.author_email)=lower(r.current_user_email)
        ORDER BY c.authored_at
        """
        tag_sql = """
        SELECT t.repository, t.name
        FROM git_tags t JOIN repositories r ON r.name=t.repository
        WHERE t.collected_day BETWEEN ? AND ?
          AND lower(t.target_author_email)=lower(r.current_user_email)
        ORDER BY t.created_at
        """

    commits = await _rows(env.DB.prepare(commit_sql).bind(start.isoformat(), end.isoformat()))
    tags = await _rows(env.DB.prepare(tag_sql).bind(start.isoformat(), end.isoformat()))
    repos = sorted({str(item["repository"]) for item in commits})
    synthesis = _cloud_review_synthesis(commits, tags)
    workstream_text = "\n".join(synthesis["lines"]) or "- 本周没有足够 Git 数据形成明确工作主线。"
    outcome_text = "\n".join(f"- {item}" for item in synthesis["outcomes"])
    release_text = "、".join(
        f"{item['repository']} {item['name']}" for item in tags
    ) or "本周没有明确 Release / Tag。"
    scope_label = "当前仓库用户" if req.author_scope == "current_user" else "所有用户"
    content = f"""---
title: "{week} 工作周报"
week: "{week}"
author_scope: "{req.author_scope}"
git_commits: {len(commits)}
git_tags: {len(tags)}
tags:
  - "#review"
  - "#weekly-review"
---

# {week} 工作周报

> **Git 统计口径：{scope_label}**
>
> 本周共采集 **{len(commits)}** 个 Git 变更，覆盖 **{len(repos)}** 个活跃仓库；以下内容已按工作主线聚合，不按 Commit 时间流水展示。

## 🎯 本周工作主线

{workstream_text}

## ✅ 关键成果与交付

{outcome_text}

### 发布节点

- {release_text}

## 📊 数据概览

| 指标 | 本周 |
| --- | ---: |
| Git Commit | {len(commits)} 个 |
| 活跃仓库 | {len(repos)} 个 |
| Release / Tag | {len(tags)} 个 |

## 数据口径

- Git 自动采集始终保存所有用户记录；本次复盘统计口径为 **{scope_label}**。
- 原始 Commit 只作为内部证据源参与聚合，不在周报正文逐条展示。
- 工作主线按照仓库、scope、工程类别和 Release/Tag 进行归并，再输出成果级摘要。
- 报告只陈述可从现有数据验证的事实，不把提交数量直接等同于工作价值。
"""
    path = f"90-AI-Workspace/reviews/{week}-Weekly-Review.md"
    await _upsert_note(env, path, content)
    return {
        "status": "success", "week": week, "path": path,
        "author_scope": req.author_scope, "author_scope_label": scope_label,
        "git_commits": len(commits), "git_tags": len(tags),
        "git_repositories": repos, "git_active_repositories": repos,
        "knowledge_topics": 0, "daily_logs_count": 0,
        "logged_tasks_count": 0, "total_hours": 0, "avg_focus": None,
        "completed_items": 0, "pending_items": 0, "compiled_items": 0,
    }


def _validate_cloud_web_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="仅支持有效的 http/https 在线链接")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="不允许抓取本机或内网地址")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise HTTPException(status_code=400, detail="不允许抓取本机或内网地址")
    return parsed.geturl()


@app.post("/mcp/vault_ingest")
async def vault_ingest(req: IngestRequest, request: Request):
    env = _env(request)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    stem = re.sub(
        r"[^0-9A-Za-z._\-\u4e00-\u9fff]+",
        "-",
        req.title,
    ).strip("-") or "note"
    folder = _normalize_path(req.folder)
    path = f"{folder.rstrip('/')}/{stamp}-{stem}.md"
    content = (
        f"---\ntitle: \"{req.title}\"\nauthor: \"{req.author}\"\n"
        f"url: \"{req.url or ''}\"\ningested_at: \"{datetime.utcnow().isoformat(timespec='seconds')}Z\"\n"
        f"tags:\n  - \"#raw-reference\"\n---\n\n# {req.title}\n\n{req.content.strip()}\n"
    )
    result = await _upsert_note(env, path, content, "NEW")
    return {
        "status": "ingested_successfully",
        "path": path,
        "version": result["version"],
    }


@app.post("/api/web-ingest")
async def web_ingest(req: WebIngestRequest, request: Request):
    url = _validate_cloud_web_url(req.url)
    try:
        from js import fetch as js_fetch
        response = await js_fetch(url)
        if not bool(response.ok):
            raise HTTPException(
                status_code=400,
                detail=f"网页请求失败：HTTP {int(response.status)}",
            )
        final_url = _validate_cloud_web_url(str(response.url or url))
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise HTTPException(status_code=400, detail="该链接不是可提取的 HTML 网页")
        html = str(await response.text())
        if len(html.encode("utf-8")) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="网页内容超过 5 MB，暂不支持直接抓取")
        page = extract_web_page(html, final_url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"抓取网页失败：{exc}") from exc

    result = await vault_ingest(
        IngestRequest(
            title=page["title"],
            content=page["content"],
            author=req.author,
            url=page["url"],
            folder=req.folder,
        ),
        request,
    )
    return {
        **result,
        "title": page["title"],
        "source_url": page["url"],
        "characters": page["characters"],
    }


@app.get("/api/references")
async def references(request: Request):
    rows = await _rows(_env(request).DB.prepare(
        """
        SELECT object_key, filename, bytes, source_type, markdown_path, uploaded_at
        FROM cloud_files ORDER BY uploaded_at DESC
        """
    ))
    return {
        "total": len(rows),
        "items": [{
            "filename": row["filename"],
            "original_path": f"r2:{row['object_key']}",
            "bytes": int(row["bytes"] or 0),
            "modified_at": row["uploaded_at"],
            "markdown_path": row["markdown_path"] or None,
            "title": PurePosixPath(str(row["filename"])).stem,
            "source_type": row["source_type"],
            "ingested_at": row["uploaded_at"],
            "extracted": bool(row["markdown_path"]),
            "compiled": False,
        } for row in rows],
    }
@app.post("/api/uploads")
async def uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    author: str = Form("Unknown"),
    source_url: str | None = Form(None),
):
    env = _env(request)
    results = []
    supported = {".md", ".txt", ".pdf", ".docx"}
    for upload in files:
        filename = PurePosixPath(upload.filename or "upload").name
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix not in supported:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "仅支持 MD / TXT / PDF / DOCX",
            })
            continue
        data = await upload.read()
        if len(data) > 50 * 1024 * 1024:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "单个文件不能超过 50 MB",
            })
            continue
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        key = f"uploads/{stamp}-{filename}"
        await env.FILES.put(key, data)
        uploaded_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        source_type = suffix.lstrip(".")
        stem = re.sub(
            r"[^0-9A-Za-z._\-\u4e00-\u9fff]+",
            "-",
            PurePosixPath(filename).stem,
        ).strip("-") or "upload"
        markdown_path = f"60-References/Articles/{stamp}-{stem}.md"
        if suffix in {".md", ".txt"}:
            extracted = data.decode("utf-8-sig", errors="replace")
        else:
            extracted = (
                f"原始文件已保存到 NexusMind Cloud 文件存储：{key}\n\n"
                "PDF / DOCX 正文提取由 NexusMind Local Agent 完成后再同步到远端服务。"
            )
        markdown = f"""---
title: "{PurePosixPath(filename).stem}"
author: "{author or 'Unknown'}"
url: "{source_url or ''}"
ingested_at: "{uploaded_at}"
source_file: "r2:{key}"
source_type: "{source_type}"
tags:
  - "#raw-reference"
  - "#uploaded"
---

# {PurePosixPath(filename).stem}

{extracted.strip()}
"""
        await _upsert_note(env, markdown_path, markdown, "NEW")
        await env.DB.prepare(
            """
            INSERT OR REPLACE INTO cloud_files(
              object_key, filename, bytes, source_type, markdown_path, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """
        ).bind(key, filename, len(data), source_type, markdown_path, uploaded_at).run()
        results.append({
            "status": "ingested_successfully", "filename": filename,
            "original_path": f"r2:{key}", "markdown_path": markdown_path,
            "source_type": source_type, "bytes": len(data),
        })
    succeeded = sum(
        1 for item in results if item.get("status") == "ingested_successfully"
    )
    return {
        "status": "success", "total": len(results),
        "succeeded": succeeded, "failed": len(results) - succeeded,
        "results": results,
    }


@app.get("/")
@app.get("/{path:path}")
async def frontend(request: Request, path: str = ""):
    env = _env(request)
    if not path:
        asset_path = "/index.html"
    elif path.startswith("web/"):
        asset_path = "/" + path.removeprefix("web/")
    else:
        asset_path = "/" + path
    response = await env.ASSETS.fetch(f"https://assets.local{asset_path}")
    body = await response.bytes()
    return Response(
        content=body,
        status_code=response.status,
        headers=dict(response.headers),
    )
