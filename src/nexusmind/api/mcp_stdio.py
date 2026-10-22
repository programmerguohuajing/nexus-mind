import json
import logging
import sys
from typing import Any, Dict

from nexusmind import __version__
from nexusmind.config import VAULT_ROOT
from nexusmind.core.canvas import CanvasEdge, CanvasNode, generate_canvas
from nexusmind.core.compiler import (
    auto_compile_pending_sources,
    compile_wiki_card,
    patch_note,
    scan_uncompiled_sources,
)
from nexusmind.core.indexer import find_broken_links, find_orphans, rebuild_all_indices
from nexusmind.core.ingest import ingest_article
from nexusmind.core.notification import (
    load_notification_config,
    sanitize_channel_config,
    send_notification,
)
from nexusmind.core.ask import ask_vault
from nexusmind.core.embeddings import hybrid_search, semantic_search
from nexusmind.core.narrative import generate_daily_narrative, push_daily_narrative
from nexusmind.core.occ import get_file_hash
from nexusmind.core.project_binding import project_context
from nexusmind.core.smart import suggest_for_note
from nexusmind.core.review import generate_review, generate_weekly_review
from nexusmind.core.search import search_notes
from nexusmind.core.storage import (
    extract_frontmatter,
    extract_links,
    extract_tags,
    find_backlinks,
    resolve_vault_path,
)

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

TOOLS_MANIFEST = [
    {
        "name": "vault_read",
        "description": "读取笔记正文、版本、Frontmatter、标签、正反向链接。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "vault_patch",
        "description": "基于 ifMatch OCC 修改/新建允许写入的笔记。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "ifMatch": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "vault_search",
        "description": "全文/正则检索，支持目录、标签、Frontmatter 属性过滤；mode=semantic/hybrid 时走语义/混合检索。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "folder": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "properties": {"type": "object"},
                "regex": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 50},
                "mode": {"type": "string", "enum": ["keyword", "semantic", "hybrid"]},
            },
        },
    },
    {
        "name": "vault_project_context",
        "description": "按项目绑定（仓库根 .nexusmind.yaml 或 Vault 00-Meta/projects.yaml）返回当前项目作用域内的知识清单。Agent 在新项目开工时应先调用它建立上下文。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "当前开发仓库的本地路径（自动向上查找 .nexusmind.yaml）"},
                "project": {"type": "string", "description": "项目名（走 Vault 侧映射时使用）"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "vault_ask",
        "description": "基于知识库回答问题：混合检索后综合作答并给出真实来源引用；知识库没有的内容会明确说明。开发新功能前可用它查既有经验与规范。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "limit": {"type": "integer", "default": 6},
                "save": {"type": "boolean", "default": False},
            },
            "required": ["question"],
        },
    },
    {
        "name": "vault_suggestions",
        "description": "为一篇笔记生成智能处理建议：摘要、标签推荐与待补链接（仅建议，不落盘）。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "vault_daily_narrative",
        "description": "把某天 Daily Log 的 Git 活动生成中文日报叙事，可选推送到通知渠道。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "push_channels": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "vault_list_unresolved",
        "description": "列出未解析 Wikilink/死链。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_find_orphans",
        "description": "列出没有传入反链的知识孤岛。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_compile",
        "description": "将 Raw 素材编译为正式 Domain 卡片并记录审计日志。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "raw_sources": {"type": "array", "items": {"type": "string"}},
                "target_card_path": {"type": "string"},
                "content": {"type": "string"},
                "conflict_detected": {"type": "boolean"},
                "conflict_summary": {"type": "string"},
                "ifMatch": {"type": "string"},
            },
            "required": ["raw_sources", "target_card_path", "content"],
        },
    },
    {
        "name": "vault_compile_pending",
        "description": "预览尚未编译的 Raw 素材。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_incremental_compile",
        "description": "自动编译全部待处理 Raw，并重建分层索引。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_rebuild_indices",
        "description": "重建 Master Index 与所有二级子索引。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_generate_canvas",
        "description": "生成经过节点/边校验的 Obsidian Canvas。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "canvas_path": {"type": "string"},
                "nodes": {"type": "array", "items": {"type": "object"}},
                "edges": {"type": "array", "items": {"type": "object"}},
                "ifMatch": {"type": "string"},
            },
            "required": ["canvas_path", "nodes", "edges"],
        },
    },
    {
        "name": "vault_ingest",
        "description": "以不可覆盖方式向 60-References Raw 层采集 Markdown。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "author": {"type": "string"},
                "url": {"type": "string"},
                "folder": {"type": "string"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "vault_weekly_review",
        "description": "按 ISO 周生成结构化周复盘，可选推送到通知渠道。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "week": {"type": "string"},
                "author_scope": {
                    "type": "string",
                    "enum": ["current_user", "all_users"],
                    "default": "current_user",
                },
                "push_channels": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "vault_list_notification_channels",
        "description": "获取已配置的推送通知渠道列表（飞书、钉钉、邮件、Webhook）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "vault_send_notification",
        "description": "手动推送到指定的通知渠道。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
                "event_type": {"type": "string", "default": "general"},
            },
            "required": ["title", "content"],
        },
    },
]


def _read(path: str) -> Dict[str, Any]:
    file_path = resolve_vault_path(path)
    if not file_path.is_file():
        raise FileNotFoundError(path)
    text = file_path.read_text(encoding="utf-8")
    return {
        "path": path,
        "version": get_file_hash(text),
        "content": text,
        "links": extract_links(text),
        "backlinks": find_backlinks(path),
        "frontmatter": extract_frontmatter(text),
        "tags": extract_tags(text),
    }


def dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "vault_read":
        return _read(args["path"])
    if name == "vault_patch":
        return patch_note(args["path"], args["content"], if_match=args.get("ifMatch"))
    if name == "vault_search":
        mode = args.get("mode", "keyword")
        if mode == "semantic":
            return semantic_search(
                args.get("query", ""),
                folder=args.get("folder"),
                limit=min(int(args.get("limit", 50)), 50),
            )
        if mode == "hybrid":
            return hybrid_search(
                args.get("query", ""),
                folder=args.get("folder"),
                limit=min(int(args.get("limit", 50)), 50),
            )
        return search_notes(
            args.get("query", ""),
            folder=args.get("folder"),
            tags=args.get("tags"),
            properties=args.get("properties"),
            regex=args.get("regex", False),
            limit=args.get("limit", 50),
        )
    if name == "vault_project_context":
        return project_context(
            project_path=args.get("project_path"),
            project=args.get("project"),
            limit=int(args.get("limit", 50)),
        )
    if name == "vault_ask":
        return ask_vault(
            args["question"],
            limit=int(args.get("limit", 6)),
            save=bool(args.get("save", False)),
        )
    if name == "vault_suggestions":
        return suggest_for_note(args["path"])
    if name == "vault_daily_narrative":
        if args.get("push_channels") is not None:
            return push_daily_narrative(args.get("date"), channels=args.get("push_channels"))
        return generate_daily_narrative(args.get("date"))
    if name == "vault_list_unresolved":
        return find_broken_links()
    if name == "vault_find_orphans":
        return find_orphans()
    if name == "vault_compile":
        return compile_wiki_card(
            raw_sources=args["raw_sources"],
            target_card_path=args["target_card_path"],
            content=args["content"],
            conflict_detected=args.get("conflict_detected", False),
            conflict_summary=args.get("conflict_summary"),
            if_match=args.get("ifMatch"),
            push_channels=args.get("push_channels"),
        )
    if name == "vault_compile_pending":
        pending = scan_uncompiled_sources()
        return {
            "total": len(pending),
            "sources": [str(p.relative_to(VAULT_ROOT)).replace("\\", "/") for p in pending],
        }
    if name == "vault_incremental_compile":
        return {"status": "success", "results": auto_compile_pending_sources(push_channels=args.get("push_channels"))}
    if name == "vault_rebuild_indices":
        return rebuild_all_indices()
    if name == "vault_generate_canvas":
        nodes = [CanvasNode(**item) for item in args["nodes"]]
        edges = [CanvasEdge(**item) for item in args["edges"]]
        return generate_canvas(
            args["canvas_path"],
            nodes,
            edges,
            if_match=args.get("ifMatch"),
        )
    if name == "vault_ingest":
        return ingest_article(
            title=args["title"],
            content=args["content"],
            author=args.get("author", "Unknown"),
            url=args.get("url"),
            folder=args.get("folder", "60-References/Articles"),
        )
    if name in ("vault_review", "vault_weekly_review"):
        return generate_review(
            period_type=args.get("period_type", "week"),
            period_value=args.get("period_value") or args.get("week"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            author_scope=args.get("author_scope", "current_user"),
            push_channels=args.get("push_channels"),
        )
    if name == "vault_list_notification_channels":
        config = load_notification_config()
        return {
            "default_channel_id": config.get("default_channel_id"),
            "channels": [sanitize_channel_config(c) for c in config.get("channels", [])],
        }
    if name == "vault_send_notification":
        return send_notification(
            title=args["title"],
            content=args["content"],
            channel_ids=args.get("channels"),
            event_type=args.get("event_type", "general"),
        )
    raise ValueError(f"Unknown tool name: {name}")


def _response(req_id: Any, *, result: Any = None, error: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def run_stdio_server():
    """最小 MCP stdio JSON-RPC 服务，工具能力与 HTTP API 保持一致。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            if method == "initialize":
                res = _response(req_id, result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "nexusmind-mcp", "version": __version__},
                })
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                res = _response(req_id, result={"tools": TOOLS_MANIFEST})
            elif method == "tools/call":
                params = req.get("params", {})
                output = dispatch_tool(params.get("name", ""), params.get("arguments", {}))
                res = _response(req_id, result={
                    "content": [{
                        "type": "text",
                        "text": json.dumps(output, ensure_ascii=False, indent=2, default=str),
                    }],
                    "isError": False,
                })
            else:
                res = _response(req_id, error={
                    "code": -32601,
                    "message": f"Method not found: {method}",
                })
        except Exception as exc:
            res = _response(req_id, error={"code": -32603, "message": str(exc)})
        sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
