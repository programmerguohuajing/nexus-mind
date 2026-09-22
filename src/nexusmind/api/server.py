import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
from nexusmind.core.occ import get_file_hash
from nexusmind.core.review import generate_weekly_review
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
    week: Optional[str] = None
    author_scope: str = "current_user"
    push_channels: Optional[List[str]] = None


class NotificationChannelModel(BaseModel):
    id: str
    name: Optional[str] = None
    type: str
    enabled: bool = True
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
    return search_notes(
        req.query,
        folder=req.folder,
        tags=req.tags,
        properties=req.properties,
        regex=req.regex,
        limit=req.limit,
    )


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


@app.post("/mcp/vault_weekly_review")
def vault_weekly_review_endpoint(req: ReviewRequest):
    try:
        return generate_weekly_review(
            week_str=req.week,
            author_scope=req.author_scope,
            push_channels=req.push_channels,
        )
    except ValueError as exc:
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
        res = test_notification_channel(channel.model_dump(exclude_unset=True))
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


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
