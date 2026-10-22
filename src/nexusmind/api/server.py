import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nexusmind import __version__
from nexusmind.config import RUNTIME_MODE, VAULT_ROOT
from nexusmind.core.canvas import CanvasEdge, CanvasNode, generate_canvas
from nexusmind.core.compiler import (
    auto_compile_pending_sources,
    compile_wiki_card,
    patch_note,
    scan_uncompiled_sources,
)
from nexusmind.core.indexer import find_broken_links, find_orphans, rebuild_all_indices
from nexusmind.core.git_activity import (
    collect_repository,
    discover_repositories,
    load_workflow_config,
    save_workflow_config,
    sync_git_activity,
)
from nexusmind.core.ingest import ingest_article
from nexusmind.core.notification import (
    load_notification_config,
    save_notification_config,
    sanitize_channel_config,
    send_notification,
    test_notification_channel,
)
from nexusmind.core.web_ingest import fetch_web_page
from nexusmind.core.ask import ask_vault
from nexusmind.core.embeddings import (
    backend_id,
    hybrid_search,
    index_status,
    rebuild_vector_index,
    semantic_search,
)
from nexusmind.core.llm import llm_status
from nexusmind.core.narrative import generate_daily_narrative, push_daily_narrative
from nexusmind.core.project_binding import project_context
from nexusmind.core.analytics import dashboard_analytics, log_search_miss
from nexusmind.core.collab import (
    add_comment,
    create_share,
    list_comments,
    list_spaces,
    mark_helpful,
    read_share,
    resolve_comment,
    revoke_share,
    space_visible_notes,
    upsert_space,
)
from nexusmind.core.connectors import (
    load_connectors_config,
    sanitize_connectors_config,
    save_connectors_config,
    sync_all_connectors,
)
from nexusmind.core.feeds import load_feeds_config, poll_email_inbox, poll_feeds, save_feeds_config
from nexusmind.core.goals import (
    add_key_result,
    compute_progress,
    create_objective,
    goals_review_section,
    list_objectives,
    update_key_result_current,
)
from nexusmind.core.smart import (
    apply_suggestions,
    batch_pending_suggestions,
    suggest_for_note,
    suggest_links,
)
from nexusmind.core.duplicates import find_duplicate_pairs, ignore_pair, merge_notes
from nexusmind.core.freshness import freshness_digest, list_stale_notes, mark_reviewed
from nexusmind.core.history import diff_snapshot, list_history, rollback_note
from nexusmind.core.ocr import ocr_status
from nexusmind.core.templates import create_from_template, list_action_items, list_templates
from nexusmind.core.occ import get_file_hash
from nexusmind.core.review import generate_review, generate_weekly_review, sync_knowledge_cards
from nexusmind.core.search import search_notes
from nexusmind.core.uploads import SUPPORTED_EXTENSIONS, ingest_uploaded_file
from nexusmind.core.storage import (
    extract_frontmatter,
    extract_links,
    extract_tags,
    find_backlinks,
    normalize_link_target,
    resolve_vault_path,
)

app = FastAPI(title="NexusMind Vault MCP Service", version=__version__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.middleware("http")
async def api_token_middleware(request, call_next):
    """NEXUSMIND_API_TOKEN 启用时，非回环来源的 /api 与 /mcp 请求必须带 Token。"""
    path = request.url.path
    if path.startswith(("/api/", "/mcp/")) and not path.startswith("/api/share/"):
        from starlette.responses import JSONResponse

        from nexusmind.core.api_auth import check_token

        client_host = request.client.host if request.client else None
        allowed = check_token(
            client_host,
            request.headers.get("authorization"),
            request.headers.get("x-nexusmind-token"),
        )
        if not allowed:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    return await call_next(request)


class ReadRequest(BaseModel):
    path: str


class PatchRequest(BaseModel):
    path: str
    content: str
    ifMatch: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = ""
    folder: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)
    regex: bool = False
    limit: int = 50
    mode: Optional[str] = None  # keyword（默认）| semantic | hybrid


class CanvasRequest(BaseModel):
    canvas_path: str
    nodes: List[CanvasNode]
    edges: List[CanvasEdge]
    ifMatch: Optional[str] = None


class CompileRequest(BaseModel):
    raw_sources: List[str]
    target_card_path: str
    content: str
    conflict_detected: bool = False
    conflict_summary: Optional[str] = None
    ifMatch: Optional[str] = None
    push_channels: Optional[List[str]] = None


class IngestRequest(BaseModel):
    title: str
    content: str
    author: str = "Unknown"
    url: Optional[str] = None
    folder: str = "60-References/Articles"


class WebIngestRequest(BaseModel):
    url: str
    author: str = "Unknown"
    folder: str = "60-References/Articles"


class ReviewRequest(BaseModel):
    period_type: Optional[str] = "week"
    period_value: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    week: Optional[str] = None
    author_scope: str = "current_user"
    push_channels: Optional[List[str]] = None


class KnowledgeItemModel(BaseModel):
    title: Optional[str] = None
    path: Optional[str] = None
    target_path: Optional[str] = None
    content: str
    domain: Optional[str] = None


class SyncKnowledgeRequest(BaseModel):
    items: List[KnowledgeItemModel] = Field(default_factory=list)


class NotificationChannelModel(BaseModel):
    id: str
    name: Optional[str] = None
    type: str
    enabled: bool = True
    feishu_mode: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    receive_id: Optional[str] = None
    receive_id_type: Optional[str] = "open_id"
    url: Optional[str] = None
    secret: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 465
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    use_tls: Optional[bool] = True
    sender: Optional[str] = None
    recipients: Optional[List[str]] = Field(default_factory=list)
    headers: Optional[Dict[str, str]] = Field(default_factory=dict)


class NotificationConfigRequest(BaseModel):
    default_channel_id: Optional[str] = None
    channels: List[NotificationChannelModel] = Field(default_factory=list)


class NotificationPushRequest(BaseModel):
    title: str
    content: str
    channels: Optional[List[str]] = None
    event_type: str = "general"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WorkflowTarget(BaseModel):
    type: str
    path: str
    enabled: bool = True


class WorkflowConfigRequest(BaseModel):
    targets: List[WorkflowTarget] = Field(default_factory=list)


@app.get("/")
def web_console():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/styles.css", include_in_schema=False)
def web_styles():
    return FileResponse(
        WEB_DIR / "styles.css",
        media_type="text/css",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/app.js", include_in_schema=False)
def web_app_js():
    return FileResponse(
        WEB_DIR / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/ui.js", include_in_schema=False)
def web_ui_js():
    return FileResponse(
        WEB_DIR / "ui.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/extras.js", include_in_schema=False)
def web_extras_js():
    return FileResponse(
        WEB_DIR / "extras.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/sw.js", include_in_schema=False)
def web_service_worker():
    return FileResponse(
        WEB_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Service-Worker-Allowed": "/"},
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    return FileResponse(
        WEB_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/m", include_in_schema=False)
def web_mobile():
    return FileResponse(WEB_DIR / "mobile.html")


@app.get("/favicon.ico", include_in_schema=False)
def web_favicon():
    return FileResponse(
        WEB_DIR / "favicon.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/assets/{asset_path:path}", include_in_schema=False)
def web_asset(asset_path: str):
    asset_root = (WEB_DIR / "assets").resolve()
    target = (asset_root / asset_path).resolve()
    try:
        target.relative_to(asset_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(target)


@app.get("/api/dashboard")
def dashboard_summary():
    markdown_files = list(VAULT_ROOT.rglob("*.md"))
    domain_files = list((VAULT_ROOT / "40-Domain").rglob("*.md")) if (VAULT_ROOT / "40-Domain").exists() else []
    raw_files = list((VAULT_ROOT / "60-References").rglob("*.md")) if (VAULT_ROOT / "60-References").exists() else []
    pending = scan_uncompiled_sources()
    broken = find_broken_links()
    orphans = find_orphans()
    log_path = VAULT_ROOT / "00-Meta" / "COMPILATION-LOG.md"
    recent = []
    if log_path.exists():
        for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if line.startswith("## ["):
                recent.append(line.removeprefix("## ").strip())
                if len(recent) == 5:
                    break
    return {
        "status": "ok",
        "version": __version__,
        "vault": str(VAULT_ROOT),
        "notes": len(markdown_files),
        "domain_notes": len(domain_files),
        "raw_sources": len(raw_files),
        "pending_compile": len(pending),
        "broken_links": broken["total_broken"],
        "orphans": orphans["total_orphans"],
        "recent_compilations": recent,
    }


@app.get("/api/runtime")
def runtime_info():
    return {
        "mode": RUNTIME_MODE,
        "capabilities": {
            "local_filesystem": True,
            "git_collection": True,
            "folder_picker": True,
            "uploads": True,
            "knowledge_compile": True,
            "governance": True,
            "weekly_review": True,
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "vault": str(VAULT_ROOT)}


@app.post("/mcp/vault_read")
def vault_read(req: ReadRequest):
    file_path = resolve_vault_path(req.path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    content = file_path.read_text(encoding="utf-8")
    return {
        "path": req.path,
        "version": get_file_hash(content),
        "content": content,
        "links": extract_links(content),
        "backlinks": find_backlinks(req.path),
        "frontmatter": extract_frontmatter(content),
        "tags": extract_tags(content),
    }


@app.post("/mcp/vault_patch")
def vault_patch_endpoint(req: PatchRequest):
    return patch_note(
        rel_path=req.path,
        content=req.content,
        if_match=req.ifMatch,
    )


@app.post("/mcp/vault_search")
def vault_search_endpoint(req: SearchRequest):
    if req.mode == "semantic":
        result = semantic_search(req.query, folder=req.folder, limit=min(req.limit, 50), vault_root=VAULT_ROOT)
    elif req.mode == "hybrid":
        result = hybrid_search(req.query, folder=req.folder, limit=min(req.limit, 50), vault_root=VAULT_ROOT)
    else:
        result = search_notes(
            req.query,
            folder=req.folder,
            tags=req.tags,
            properties=req.properties,
            regex=req.regex,
            limit=req.limit,
        )
    if req.query and result.get("total", 0) == 0:
        log_search_miss(req.query, vault_root=VAULT_ROOT, source=req.mode or "keyword")
    return result


@app.get("/mcp/vault_list_unresolved")
@app.get("/mcp/vault_find_broken_links")
def vault_find_broken_links_endpoint():
    return find_broken_links()


@app.get("/mcp/vault_find_orphans")
def vault_find_orphans_endpoint():
    return find_orphans()


@app.post("/mcp/vault_compile")
def vault_compile_endpoint(req: CompileRequest):
    try:
        return compile_wiki_card(
            raw_sources=req.raw_sources,
            target_card_path=req.target_card_path,
            content=req.content,
            conflict_detected=req.conflict_detected,
            conflict_summary=req.conflict_summary,
            if_match=req.ifMatch,
            push_channels=req.push_channels,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/mcp/vault_compile_pending")
def vault_compile_pending_preview():
    pending = scan_uncompiled_sources()
    return {
        "total": len(pending),
        "sources": [
            str(path.relative_to(VAULT_ROOT)).replace("\\", "/")
            for path in pending
        ],
    }


@app.post("/mcp/vault_incremental_compile")
def vault_incremental_compile_endpoint(push_channels: Optional[List[str]] = None):
    return {"status": "success", "results": auto_compile_pending_sources(push_channels=push_channels)}


@app.post("/mcp/vault_rebuild_indices")
def vault_rebuild_indices_endpoint():
    return rebuild_all_indices()


@app.post("/mcp/vault_generate_canvas")
def vault_generate_canvas_endpoint(req: CanvasRequest):
    try:
        return generate_canvas(
            canvas_path=req.canvas_path,
            nodes=req.nodes,
            edges=req.edges,
            if_match=req.ifMatch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/resolve-link")
def resolve_link(target: str):
    normalized = normalize_link_target(target)
    exact_matches: List[str] = []
    stem_matches: List[str] = []
    for md_file in VAULT_ROOT.rglob("*.md"):
        rel = str(md_file.relative_to(VAULT_ROOT)).replace("\\", "/")
        rel_normalized = normalize_link_target(rel)
        if normalized in {
            rel_normalized,
            normalize_link_target(md_file.name),
        }:
            exact_matches.append(rel)
        if md_file.stem.lower() == Path(normalized).stem.lower():
            stem_matches.append(rel)
    matches = list(dict.fromkeys(exact_matches or stem_matches))
    if not matches:
        raise HTTPException(status_code=404, detail="Wikilink target not found")
    if len(matches) > 1:
        return {"status": "ambiguous", "target": target, "matches": matches}
    return {"status": "resolved", "target": target, "path": matches[0]}


@app.get("/api/graph")
def knowledge_graph(folder: Optional[str] = None):
    root = resolve_vault_path(folder, vault_root=VAULT_ROOT) if folder else VAULT_ROOT
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    files = sorted(root.rglob("*.md"), key=lambda path: str(path).lower())
    nodes: List[Dict[str, Any]] = []
    by_normalized: Dict[str, str] = {}
    by_stem: Dict[str, List[str]] = {}

    for md_file in files:
        rel = str(md_file.relative_to(VAULT_ROOT)).replace("\\", "/")
        content = md_file.read_text(encoding="utf-8")
        fm = extract_frontmatter(content)
        title = str(fm.get("title") or md_file.stem)
        nodes.append({
            "id": rel,
            "path": rel,
            "title": title,
            "tags": extract_tags(content)[:8],
        })
        normalized = normalize_link_target(rel)
        by_normalized[normalized] = rel
        by_normalized[normalize_link_target(md_file.name)] = rel
        by_stem.setdefault(md_file.stem.lower(), []).append(rel)

    edges: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for md_file in files:
        source = str(md_file.relative_to(VAULT_ROOT)).replace("\\", "/")
        try:
            links = extract_links(md_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        for raw in links:
            normalized = normalize_link_target(raw)
            target = by_normalized.get(normalized)
            if not target:
                matches = by_stem.get(Path(normalized).stem.lower(), [])
                if len(matches) == 1:
                    target = matches[0]
            if not target or target == source:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": source, "target": target})

    degree: Dict[str, int] = {node["id"]: 0 for node in nodes}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    for node in nodes:
        node["degree"] = degree.get(node["id"], 0)
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


@app.get("/api/canvases")
def list_canvases():
    items = []
    for path in sorted(VAULT_ROOT.rglob("*.canvas"), key=lambda p: str(p).lower()):
        rel = str(path.relative_to(VAULT_ROOT)).replace("\\", "/")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        items.append({
            "path": rel,
            "name": path.stem,
            "nodes": len(data.get("nodes", [])) if isinstance(data, dict) else 0,
            "edges": len(data.get("edges", [])) if isinstance(data, dict) else 0,
        })
    return {"total": len(items), "items": items}


@app.get("/api/canvas")
def read_canvas(path: str):
    if not path.lower().endswith(".canvas"):
        raise HTTPException(status_code=400, detail="Canvas path must end with .canvas")
    file_path = resolve_vault_path(path, vault_root=VAULT_ROOT)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Canvas not found")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid Canvas JSON") from exc
    return {
        "path": path,
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
    }


@app.get("/api/fs/directories")
def list_local_directories(path: Optional[str] = None):
    if not path:
        if os.name == "nt":
            roots = [
                f"{letter}:\\"
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if Path(f"{letter}:\\").exists()
            ]
        else:
            roots = ["/"]
        return {
            "path": None,
            "parent": None,
            "roots": roots,
            "directories": [],
        }

    current = Path(path).expanduser().resolve()
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    directories = []
    try:
        children = sorted(
            (child for child in current.iterdir() if child.is_dir()),
            key=lambda child: child.name.lower(),
        )
    except OSError as exc:
        raise HTTPException(status_code=403, detail=f"Cannot access directory: {current}") from exc

    for child in children:
        try:
            is_git = (child / ".git").exists()
        except OSError:
            is_git = False
        directories.append({
            "name": child.name,
            "path": str(child),
            "is_git": is_git,
        })

    parent = current.parent
    return {
        "path": str(current),
        "parent": str(parent) if parent != current else None,
        "roots": [],
        "directories": directories,
        "is_git": (current / ".git").exists(),
    }


@app.get("/api/workflow/config")
def workflow_config_get():
    return load_workflow_config()


@app.put("/api/workflow/config")
def workflow_config_put(req: WorkflowConfigRequest):
    try:
        return save_workflow_config([item.model_dump() for item in req.targets])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/workflow")
def workflow_status():
    config = load_workflow_config()
    repos = [collect_repository(repo) for repo in discover_repositories(targets=config["targets"])]
    return {
        "configured": bool(config["targets"]),
        "targets": config["targets"],
        "repository_count": len(repos),
        "commit_count": sum(item["commit_count"] for item in repos),
        "tag_count": sum(item["tag_count"] for item in repos),
        "repositories": repos,
        "daily_log": f"30-Logs/Daily/{datetime.now().date().isoformat()}.md" if repos else None,
    }


@app.post("/api/workflow/sync")
def workflow_sync():
    return sync_git_activity()


@app.get("/api/references")
def list_references():
    files_dir = VAULT_ROOT / "60-References" / "Files"
    articles_dir = VAULT_ROOT / "60-References" / "Articles"
    compilation_log = VAULT_ROOT / "00-Meta" / "COMPILATION-LOG.md"
    compiled_text = compilation_log.read_text(encoding="utf-8") if compilation_log.exists() else ""

    article_by_source: Dict[str, Dict[str, Any]] = {}
    if articles_dir.exists():
        for article in articles_dir.rglob("*.md"):
            try:
                content = article.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = extract_frontmatter(content)
            source_file = str(fm.get("source_file") or "").replace("\\", "/").strip()
            if not source_file:
                continue
            article_rel = str(article.relative_to(VAULT_ROOT)).replace("\\", "/")
            article_by_source[source_file] = {
                "markdown_path": article_rel,
                "title": str(fm.get("title") or article.stem),
                "source_type": str(fm.get("source_type") or article.suffix.lstrip(".")),
                "ingested_at": str(fm.get("ingested_at") or ""),
                "compiled": f"`{article_rel}`" in compiled_text,
            }

    items: List[Dict[str, Any]] = []
    if files_dir.exists():
        for file_path in files_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(VAULT_ROOT)).replace("\\", "/")
            stat = file_path.stat()
            article_info = article_by_source.get(rel, {})
            items.append({
                "filename": file_path.name,
                "original_path": rel,
                "bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "markdown_path": article_info.get("markdown_path"),
                "title": article_info.get("title") or file_path.stem,
                "source_type": article_info.get("source_type") or file_path.suffix.lstrip(".").lower(),
                "ingested_at": article_info.get("ingested_at") or "",
                "extracted": bool(article_info),
                "compiled": bool(article_info.get("compiled")),
            })

    items.sort(key=lambda item: item["modified_at"], reverse=True)
    return {
        "total": len(items),
        "items": items,
    }


@app.post("/api/uploads")
async def upload_files(
    files: List[UploadFile] = File(...),
    author: str = Form("Unknown"),
    source_url: Optional[str] = Form(None),
):
    results = []
    for upload in files:
        filename = upload.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({
                "filename": filename,
                "status": "error",
                "error": "仅支持 MD / TXT / PDF / DOCX / PNG / JPG / WEBP",
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
        try:
            item = ingest_uploaded_file(
                filename,
                data,
                author=author,
                source_url=source_url,
            )
            results.append(item)
        except Exception as exc:
            results.append({
                "filename": filename,
                "status": "error",
                "error": str(exc),
            })
    succeeded = sum(1 for item in results if item.get("status") == "ingested_successfully")
    return {
        "status": "success",
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@app.post("/api/web-ingest")
def web_ingest_endpoint(req: WebIngestRequest):
    try:
        page = fetch_web_page(req.url, allow_private=True)
        result = ingest_article(
            title=page["title"],
            content=page["content"],
            author=req.author,
            url=page["url"],
            folder=req.folder,
        )
        return {**result, "source_url": page["url"], "characters": page["characters"]}
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/mcp/vault_ingest")
def vault_ingest_endpoint(req: IngestRequest):
    try:
        return ingest_article(
            title=req.title,
            content=req.content,
            author=req.author,
            url=req.url,
            folder=req.folder,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/mcp/vault_review")
@app.post("/mcp/vault_weekly_review")
def vault_review_endpoint(req: ReviewRequest):
    try:
        p_type = req.period_type or "week"
        p_val = req.period_value or req.week
        return generate_review(
            period_type=p_type,
            period_value=p_val,
            start_date=req.start_date,
            end_date=req.end_date,
            author_scope=req.author_scope,
            push_channels=req.push_channels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/review/sync-knowledge")
@app.post("/mcp/vault_sync_knowledge")
def sync_review_knowledge_endpoint(req: SyncKnowledgeRequest):
    try:
        items_data = [item.model_dump(exclude_unset=True) for item in req.items]
        return sync_knowledge_cards(items_data, vault_root=VAULT_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/notifications/channels")
def get_notification_channels():
    config = load_notification_config()
    sanitized_channels = [sanitize_channel_config(c) for c in config.get("channels", [])]
    return {
        "default_channel_id": config.get("default_channel_id"),
        "channels": sanitized_channels,
    }


@app.post("/api/notifications/channels")
def update_notification_channels(req: NotificationConfigRequest):
    try:
        channels_data = [ch.model_dump(exclude_unset=True) for ch in req.channels]
        saved = save_notification_config(channels_data, default_channel_id=req.default_channel_id)
        sanitized = [sanitize_channel_config(c) for c in saved.get("channels", [])]
        return {
            "status": "success",
            "default_channel_id": saved.get("default_channel_id"),
            "channels": sanitized,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/notifications/test")
def test_notification_channel_endpoint(channel: NotificationChannelModel):
    try:
        channel_data = channel.model_dump(exclude_unset=True)
        if channel_data.get("id"):
            cfg = load_notification_config()
            existing = next((c for c in cfg.get("channels", []) if c.get("id") == channel_data["id"]), None)
            if existing:
                for k in ("secret", "app_secret", "smtp_pass"):
                    if channel_data.get(k) == "******" or not channel_data.get(k):
                        if existing.get(k):
                            channel_data[k] = existing.get(k)
        res = test_notification_channel(channel_data)
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/notifications/push")
def push_notification_endpoint(req: NotificationPushRequest):
    return send_notification(
        title=req.title,
        content=req.content,
        channel_ids=req.channels,
        event_type=req.event_type,
        metadata=req.metadata,
    )


class RollbackRequest(BaseModel):
    path: str
    version: str


class DuplicatePairRequest(BaseModel):
    path_a: str
    path_b: str


class MergeNotesRequest(BaseModel):
    primary: str
    secondary: str


class ReviewedRequest(BaseModel):
    path: str
    extend_days: Optional[int] = None


class TemplateCreateRequest(BaseModel):
    template_id: str
    title: str
    folder: Optional[str] = None
    variables: Dict[str, str] = Field(default_factory=dict)


@app.get("/api/ocr/status")
def ocr_status_endpoint():
    return ocr_status()


@app.get("/api/history")
def history_list_endpoint(path: str):
    return list_history(path, vault_root=VAULT_ROOT)


@app.get("/api/history/diff")
def history_diff_endpoint(path: str, version: str):
    return diff_snapshot(path, version, vault_root=VAULT_ROOT)


@app.post("/api/history/rollback")
def history_rollback_endpoint(req: RollbackRequest):
    return rollback_note(req.path, req.version, vault_root=VAULT_ROOT)


@app.get("/api/governance/duplicates")
def governance_duplicates_endpoint(threshold: float = 0.88):
    return find_duplicate_pairs(threshold=threshold, vault_root=VAULT_ROOT)


@app.post("/api/governance/duplicates/ignore")
def governance_duplicates_ignore_endpoint(req: DuplicatePairRequest):
    return ignore_pair(req.path_a, req.path_b, vault_root=VAULT_ROOT)


@app.post("/api/governance/duplicates/merge")
def governance_duplicates_merge_endpoint(req: MergeNotesRequest):
    try:
        return merge_notes(req.primary, req.secondary, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/governance/stale")
def governance_stale_endpoint():
    return list_stale_notes(vault_root=VAULT_ROOT)


@app.post("/api/governance/reviewed")
def governance_reviewed_endpoint(req: ReviewedRequest):
    try:
        return mark_reviewed(req.path, extend_days=req.extend_days, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/governance/freshness-digest")
def governance_freshness_digest_endpoint(push: bool = False):
    digest = freshness_digest(vault_root=VAULT_ROOT)
    notification_result = None
    if push and digest["total"]:
        notification_result = send_notification(
            title="知识保鲜复审提醒",
            content=digest["digest"],
            event_type="freshness_digest",
            metadata={"stale_total": digest["total"]},
        )
    return {**digest, "notification_result": notification_result}


@app.get("/api/templates")
def templates_list_endpoint():
    return list_templates(vault_root=VAULT_ROOT)


@app.post("/api/templates/create")
def templates_create_endpoint(req: TemplateCreateRequest):
    try:
        return create_from_template(
            req.template_id,
            req.title,
            folder=req.folder,
            variables=req.variables,
            vault_root=VAULT_ROOT,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/templates/action-items")
def templates_action_items_endpoint(path: str):
    try:
        return list_action_items(path, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class AskRequest(BaseModel):
    question: str
    limit: int = 6
    save: bool = False


@app.get("/api/project/context")
def project_context_endpoint(project_path: Optional[str] = None, project: Optional[str] = None, limit: int = 50):
    try:
        return project_context(
            project_path=project_path,
            project=project,
            limit=limit,
            vault_root=VAULT_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SuggestionsApplyRequest(BaseModel):
    path: str
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    links: Optional[List[str]] = None


class NarrativeRequest(BaseModel):
    date: Optional[str] = None
    push_channels: Optional[List[str]] = None
    author_scope: str = "all_users"


@app.get("/api/ai/status")
def ai_status_endpoint():
    return {
        "llm": llm_status(),
        "embedding": index_status(vault_root=VAULT_ROOT),
        "embed_backend": backend_id(),
    }


@app.post("/api/embeddings/rebuild")
def embeddings_rebuild_endpoint():
    return rebuild_vector_index(vault_root=VAULT_ROOT)


@app.post("/api/ask")
@app.post("/mcp/vault_ask")
def vault_ask_endpoint(req: AskRequest):
    try:
        result = ask_vault(req.question, limit=req.limit, save=req.save, vault_root=VAULT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("mode") == "no_match":
        log_search_miss(req.question, vault_root=VAULT_ROOT, source="ask")
    return result


@app.get("/api/notes/suggestions")
def note_suggestions_endpoint(path: str):
    try:
        return suggest_for_note(path, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/notes/suggestions/apply")
def note_suggestions_apply_endpoint(req: SuggestionsApplyRequest):
    try:
        return apply_suggestions(
            req.path,
            summary=req.summary,
            tags=req.tags,
            links=req.links,
            vault_root=VAULT_ROOT,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/notes/link-suggestions")
def note_link_suggestions_endpoint(path: str, limit: int = 5):
    try:
        return suggest_links(path, limit=limit, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/compile/suggestions")
def compile_suggestions_endpoint(days: int = 30):
    return batch_pending_suggestions(days=days, vault_root=VAULT_ROOT)


@app.post("/api/narrative/daily")
def narrative_daily_endpoint(req: NarrativeRequest):
    if req.push_channels is not None:
        return push_daily_narrative(
            req.date,
            channels=req.push_channels,
            author_scope=req.author_scope,
            vault_root=VAULT_ROOT,
        )
    return generate_daily_narrative(req.date, author_scope=req.author_scope, vault_root=VAULT_ROOT)


# ---------------- Phase 3：连接器 / 协作 / OKR / 管道 / 看板 / 远程 MCP ----------------

class CommentRequest(BaseModel):
    path: str
    author: str
    content: str
    parent_id: Optional[str] = None
    notify: bool = False


class CommentActionRequest(BaseModel):
    path: str
    comment_id: str


class ShareRequest(BaseModel):
    path: str
    ttl_days: int = 7
    password: Optional[str] = None


class SpaceRequest(BaseModel):
    name: str
    folders: List[str] = Field(default_factory=list)
    visibility: str = "members"
    members: List[str] = Field(default_factory=list)


class ObjectiveRequest(BaseModel):
    title: str
    period: str = ""


class KeyResultRequest(BaseModel):
    title: str
    target: float = 1.0
    unit: str = ""
    source: Optional[Dict[str, Any]] = None


class KeyResultUpdateRequest(BaseModel):
    current: float


@app.get("/api/connectors")
def connectors_get_endpoint():
    return sanitize_connectors_config(load_connectors_config())


@app.post("/api/connectors")
def connectors_save_endpoint(payload: Dict[str, Any]):
    existing = load_connectors_config()
    for platform in ("github", "gitlab"):
        token = (payload.get(platform) or {}).get("token")
        if token == "******" and existing.get(platform, {}).get("token"):
            payload[platform]["token"] = existing[platform]["token"]
    saved = save_connectors_config(payload)
    return sanitize_connectors_config(saved)


@app.post("/api/connectors/sync")
def connectors_sync_endpoint():
    try:
        return sync_all_connectors(vault_root=VAULT_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/notes/comments")
def comments_list_endpoint(path: str):
    return list_comments(path, vault_root=VAULT_ROOT)


@app.post("/api/notes/comments")
def comments_add_endpoint(req: CommentRequest):
    try:
        result = add_comment(req.path, req.author, req.content, parent_id=req.parent_id, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    notification_result = None
    mentions = result["comment"].get("mentions") or []
    if req.notify and mentions:
        notification_result = send_notification(
            title="笔记评论提及",
            content=f"{req.author} 在 [[{req.path}]] 评论并提及 {' '.join('@' + m for m in mentions)}：\n\n{req.content}",
            event_type="comment_mention",
            metadata={"path": req.path, "mentions": mentions},
        )
    return {**result, "notification_result": notification_result}


@app.post("/api/notes/comments/resolve")
def comments_resolve_endpoint(req: CommentActionRequest):
    try:
        return resolve_comment(req.path, req.comment_id, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/notes/comments/helpful")
def comments_helpful_endpoint(req: CommentActionRequest):
    try:
        return mark_helpful(req.path, req.comment_id, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/shares")
def shares_create_endpoint(req: ShareRequest):
    try:
        return create_share(req.path, ttl_days=req.ttl_days, password=req.password, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/share/{token}")
def shares_read_endpoint(token: str, password: Optional[str] = None):
    try:
        return read_share(token, password=password, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc


@app.delete("/api/shares/{token}")
def shares_revoke_endpoint(token: str):
    try:
        return revoke_share(token, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/spaces")
def spaces_list_endpoint():
    return list_spaces(vault_root=VAULT_ROOT)


@app.post("/api/spaces")
def spaces_upsert_endpoint(req: SpaceRequest):
    try:
        return upsert_space(
            req.name,
            folders=req.folders,
            visibility=req.visibility,
            members=req.members,
            vault_root=VAULT_ROOT,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/spaces/{name}/notes")
def spaces_notes_endpoint(name: str, member: Optional[str] = None):
    try:
        return space_visible_notes(name, member=member, vault_root=VAULT_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/goals")
def goals_list_endpoint():
    return list_objectives()


@app.post("/api/goals")
def goals_create_endpoint(req: ObjectiveRequest):
    return create_objective(req.title, period=req.period)


@app.post("/api/goals/{objective_id}/key-results")
def goals_add_kr_endpoint(objective_id: str, req: KeyResultRequest):
    try:
        return add_key_result(
            objective_id,
            req.title,
            target=req.target,
            unit=req.unit,
            source=req.source,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/goals/{objective_id}/key-results/{kr_id}")
def goals_update_kr_endpoint(objective_id: str, kr_id: str, req: KeyResultUpdateRequest):
    try:
        return update_key_result_current(objective_id, kr_id, req.current)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/goals/progress")
def goals_progress_endpoint(since: Optional[str] = None):
    return compute_progress(vault_root=VAULT_ROOT, since=since)


@app.get("/api/goals/review-section")
def goals_review_section_endpoint(since: Optional[str] = None):
    return goals_review_section(vault_root=VAULT_ROOT, since=since)


@app.get("/api/feeds")
def feeds_get_endpoint():
    return load_feeds_config()


@app.post("/api/feeds")
def feeds_save_endpoint(payload: Dict[str, Any]):
    return save_feeds_config(payload)


@app.post("/api/feeds/poll")
def feeds_poll_endpoint():
    try:
        return poll_feeds(vault_root=VAULT_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/feeds/poll-email")
def feeds_poll_email_endpoint():
    try:
        return poll_email_inbox(vault_root=VAULT_ROOT)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/analytics")
def analytics_endpoint(weeks: int = 8):
    return dashboard_analytics(vault_root=VAULT_ROOT, weeks=weeks)


# 远程 MCP（Streamable HTTP 风格 JSON-RPC）：与本地 stdio 共用工具实现。
_MCP_READ_ONLY_TOOLS = {
    "vault_read", "vault_search", "vault_ask", "vault_project_context",
    "vault_list_unresolved", "vault_find_orphans", "vault_compile_pending",
    "vault_suggestions", "vault_list_notification_channels",
}


def _mcp_scope(request) -> Optional[str]:
    """返回 full | readonly | None（未授权）。回环来源或未配置 Token 时为 full。"""
    import os as _os

    from nexusmind.core.api_auth import is_loopback

    api_token = _os.environ.get("NEXUSMIND_API_TOKEN", "").strip()
    readonly_token = _os.environ.get("NEXUSMIND_MCP_READONLY_TOKEN", "").strip()
    client_host = request.client.host if request.client else None
    if is_loopback(client_host) or (not api_token and not readonly_token):
        return "full"
    provided = (request.headers.get("x-nexusmind-token") or "").strip()
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if api_token and provided == api_token:
        return "full"
    if readonly_token and provided == readonly_token:
        return "readonly"
    return None


@app.post("/mcp-rpc")
async def remote_mcp_endpoint(request: Request):
    from starlette.responses import JSONResponse

    from nexusmind.api.mcp_stdio import TOOLS_MANIFEST, dispatch_tool

    scope = _mcp_scope(request)
    if scope is None:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing MCP token"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})
    req_id = body.get("id")
    method = body.get("method", "")

    def rpc_result(result: Any) -> JSONResponse:
        return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": result})

    def rpc_error(code: int, message: str) -> JSONResponse:
        return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

    if method.startswith("notifications/"):
        return JSONResponse(status_code=202, content={})
    if method == "initialize":
        return rpc_result({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "nexusmind-mcp-remote", "version": __version__},
            "scope": scope,
        })
    if method == "ping":
        return rpc_result({})
    if method == "tools/list":
        tools = TOOLS_MANIFEST
        if scope == "readonly":
            tools = [tool for tool in TOOLS_MANIFEST if tool["name"] in _MCP_READ_ONLY_TOOLS]
        return rpc_result({"tools": tools})
    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name", "")
        if scope == "readonly" and name not in _MCP_READ_ONLY_TOOLS:
            return rpc_error(-32001, f"Tool {name} requires write scope")
        try:
            output = dispatch_tool(name, params.get("arguments") or {})
        except Exception as exc:
            return rpc_error(-32603, str(exc))
        return rpc_result({
            "content": [{
                "type": "text",
                "text": json.dumps(output, ensure_ascii=False, indent=2, default=str),
            }],
            "isError": False,
        })
    return rpc_error(-32601, f"Method not found: {method}")


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
