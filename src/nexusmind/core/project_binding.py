"""项目绑定（Agent 连接知识库 · B 块）：让 Agent 知道"当前项目对应哪些知识"。

两种绑定来源（repo 根优先）：
1. 项目仓库根目录的 `.nexusmind.yaml`：
   ```yaml
   project: account-shop
   scope:
     folders: ["40-Domain/Pay", "20-Projects/account-shop"]
     tags: ["#支付", "#订单"]
   ```
2. Vault 侧映射 `00-Meta/projects.yaml`（项目不方便放文件时用）：
   ```yaml
   projects:
     account-shop:
       folders: ["40-Domain/Pay"]
       tags: ["#支付"]
   ```

Agent 开工时调用 vault_project_context（传自己所在仓库路径），即可拿到
该项目作用域内的知识清单，再用 vault_search/vault_ask 在作用域内深挖。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nexusmind.config import VAULT_ROOT
from nexusmind.core.search import search_notes
from nexusmind.core.storage import extract_frontmatter, extract_tags

BINDING_FILENAME = ".nexusmind.yaml"
VAULT_BINDINGS_REL = "00-Meta/projects.yaml"


def find_binding_file(start_dir: Path) -> Optional[Path]:
    """从 start_dir 向上逐级查找 .nexusmind.yaml。"""
    current = start_dir.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate_dir in [current, *current.parents]:
        candidate = candidate_dir / BINDING_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _normalize_scope(raw: Any) -> Dict[str, List[str]]:
    scope = raw if isinstance(raw, dict) else {}
    folders = scope.get("folders") or []
    tags = scope.get("tags") or []
    return {
        "folders": [str(x).replace("\\", "/").strip("/") for x in folders if str(x).strip()],
        "tags": [str(x) if str(x).startswith("#") else f"#{x}" for x in tags if str(x).strip()],
    }


def load_binding_file(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid binding file: {path}")
    return {
        "project": str(data.get("project") or path.parent.name),
        "description": str(data.get("description") or ""),
        "scope": _normalize_scope(data.get("scope")),
        "source": "repo",
        "binding_file": str(path),
    }


def load_vault_bindings(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Dict[str, Any]]:
    path = vault_root / VAULT_BINDINGS_REL
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for name, spec in projects.items():
        spec = spec if isinstance(spec, dict) else {}
        result[str(name)] = {
            "project": str(name),
            "description": str(spec.get("description") or ""),
            "scope": _normalize_scope(spec),
            "source": "vault",
            "binding_file": str(path),
        }
    return result


def resolve_binding(
    *,
    project_path: Optional[str] = None,
    project: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """按 repo 文件 → vault 映射的顺序解析项目绑定。"""
    if project_path:
        binding_file = find_binding_file(Path(project_path))
        if binding_file:
            return load_binding_file(binding_file)
    if project:
        bindings = load_vault_bindings(vault_root=vault_root)
        if project in bindings:
            return bindings[project]
        if project_path:
            # 有路径但无绑定文件：以目录名作为项目名，作用域为空并给出指引
            return {
                "project": project,
                "description": "",
                "scope": {"folders": [], "tags": []},
                "source": "none",
                "binding_file": None,
            }
        raise ValueError(
            f"Project binding not found: {project}。"
            f"请在仓库根放 {BINDING_FILENAME}，或在 Vault 的 {VAULT_BINDINGS_REL} 中登记。"
        )
    if project_path:
        return {
            "project": Path(project_path).expanduser().resolve().name,
            "description": "",
            "scope": {"folders": [], "tags": []},
            "source": "none",
            "binding_file": None,
        }
    raise ValueError("project_path or project is required")


def _notes_in_folders(folders: List[str], vault_root: Path, limit: int) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for folder in folders:
        base = vault_root / folder
        if not base.exists():
            continue
        for md_file in sorted(base.rglob("*.md"), key=lambda p: str(p).lower()):
            rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = extract_frontmatter(text)
            notes.append({
                "path": rel,
                "title": str(fm.get("title") or md_file.stem),
                "tags": extract_tags(text),
                "matched_by": f"folder:{folder}",
            })
            if len(notes) >= limit:
                return notes
    return notes


def project_context(
    *,
    project_path: Optional[str] = None,
    project: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
    limit: int = 50,
) -> Dict[str, Any]:
    """返回项目作用域内的知识清单，供 Agent 开工前建立上下文。"""
    binding = resolve_binding(project_path=project_path, project=project, vault_root=vault_root)
    scope = binding["scope"]
    notes = _notes_in_folders(scope["folders"], vault_root, limit)
    seen = {note["path"] for note in notes}
    for tag in scope["tags"]:
        if len(notes) >= limit:
            break
        result = search_notes("", tags=[tag], limit=limit, vault_root=vault_root)
        for match in result["matches"]:
            if match["path"] in seen:
                continue
            seen.add(match["path"])
            notes.append({
                "path": match["path"],
                "title": match["title"],
                "tags": match["tags"],
                "matched_by": f"tag:{tag}",
            })
            if len(notes) >= limit:
                break
    return {
        "project": binding["project"],
        "description": binding["description"],
        "source": binding["source"],
        "binding_file": binding["binding_file"],
        "scope": scope,
        "total": len(notes),
        "notes": notes,
        "guidance": (
            "先用本清单了解项目已有知识；开发中遇到问题先 vault_search（可带 folder 限定作用域）"
            "或 vault_ask 查询，不要凭空假设。查不到就明确说知识库没有，不要编造。"
        ) if binding["source"] != "none" else (
            f"未找到项目绑定：请在仓库根创建 {BINDING_FILENAME}（project/scope.folders/scope.tags），"
            f"或在 Vault 的 {VAULT_BINDINGS_REL} 登记该项目。"
        ),
    }
