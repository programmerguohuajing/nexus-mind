import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.storage import resolve_vault_path


class CanvasNode(BaseModel):
    id: str
    text: Optional[str] = None
    file: Optional[str] = None
    x: int
    y: int
    width: int
    height: int


class CanvasEdge(BaseModel):
    id: str
    fromNode: str
    toNode: str


def generate_canvas(
    canvas_path: str,
    nodes: List[CanvasNode],
    edges: List[CanvasEdge],
    if_match: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """生成 Obsidian Canvas；正式知识 Canvas 由专用工具受控写入并遵循 OCC。"""
    normalized = canvas_path.replace("\\", "/").strip("/")
    if not normalized.endswith(".canvas"):
        raise ValueError("canvas_path must end with .canvas")
    if not (
        normalized.startswith("40-Domain/")
        or normalized.startswith("90-AI-Workspace/")
    ):
        raise ValueError("Canvas can only be written under 40-Domain or 90-AI-Workspace")

    node_ids = [node.id for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Canvas node ids must be unique")
    edge_ids = [edge.id for edge in edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Canvas edge ids must be unique")

    node_set = set(node_ids)
    for edge in edges:
        if edge.fromNode not in node_set or edge.toNode not in node_set:
            raise ValueError(f"Edge {edge.id} references an unknown node")

    for node in nodes:
        if node.file:
            target = resolve_vault_path(node.file, vault_root=vault_root)
            if not target.exists():
                raise ValueError(f"Canvas file node does not exist: {node.file}")

    data = {
        "nodes": [n.model_dump(exclude_none=True) for n in nodes],
        "edges": [e.model_dump() for e in edges],
    }
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    result = patch_note(
        normalized,
        serialized,
        if_match=if_match,
        actor="canvas",
        privileged=True,
        vault_root=vault_root,
    )
    return {
        "status": "success",
        "canvas_path": normalized,
        "nodes": len(nodes),
        "edges": len(edges),
        "version": result["version"],
        "created": result["created"],
    }
