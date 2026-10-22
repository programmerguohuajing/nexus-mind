"""笔记模板库（产品设计文档 P1-4）：会议纪要 / ADR / 故障复盘。

模板以 Markdown 形式存于 Vault 的 00-Templates/，用户可自行增改；
内置模板首次访问时自动播种。正文占位符：{{title}} {{date}} {{datetime}}。
行动项约定格式：- [ ] 事项 (@负责人 ddl:YYYY-MM-DD)
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.storage import extract_frontmatter, resolve_vault_path

TEMPLATES_DIR = "00-Templates"

BUILTIN_TEMPLATES: Dict[str, Dict[str, str]] = {
    "meeting": {
        "name": "会议纪要",
        "description": "议题、讨论、决议与带负责人/截止日期的行动项。",
        "folder": "30-Logs/Meetings",
        "body": """# {{title}}

- 时间：{{datetime}}
- 参会人：
- 记录人：

## 议题

1.

## 讨论要点

-

## 决议

-

## 行动项

- [ ] 示例行动项 (@负责人 ddl:{{date}})
""",
    },
    "adr": {
        "name": "ADR 架构决策记录",
        "description": "背景、候选方案、决策与后果，便于后期编译为架构知识卡片。",
        "folder": "20-Projects/Decisions",
        "body": """# ADR：{{title}}

- 日期：{{date}}
- 状态：提议中（提议中 / 已接受 / 已废弃 / 被替代）
- 决策人：

## 背景

（问题是什么？约束条件有哪些？）

## 候选方案

### 方案 A

- 优点：
- 缺点：

### 方案 B

- 优点：
- 缺点：

## 决策

（最终选择与理由）

## 后果

- 正面：
- 负面 / 风险：
- 后续跟进：
""",
    },
    "incident": {
        "name": "故障复盘",
        "description": "时间线、影响、根因、处置与改进项的标准复盘结构。",
        "folder": "30-Logs/Incidents",
        "body": """# 故障复盘：{{title}}

- 发生时间：{{datetime}}
- 持续时长：
- 影响范围：
- 等级：P0 / P1 / P2

## 时间线

| 时间 | 事件 |
|---|---|
| {{datetime}} | 故障发现 |

## 根因分析

（直接原因与深层原因）

## 处置过程

1.

## 改进项

- [ ] 示例改进项 (@负责人 ddl:{{date}})

## 经验沉淀

（可复用的排查经验，后续编译为 Domain 卡片）
""",
    },
}

_ACTION_ITEM_RE = re.compile(
    r"^\s*-\s*\[(?P<done>[ xX])\]\s*(?P<text>.+?)\s*$"
)
_ACTION_META_RE = re.compile(
    r"\(@(?P<owner>[^\s)]+)(?:\s+ddl:(?P<ddl>\d{4}-\d{2}-\d{2}))?\)\s*$"
)


def _template_rel(template_id: str) -> str:
    return f"{TEMPLATES_DIR}/{template_id}.md"


def ensure_templates(*, vault_root: Path = VAULT_ROOT) -> List[str]:
    """播种内置模板（已存在则不覆盖，尊重用户修改）。返回模板相对路径列表。"""
    created: List[str] = []
    for template_id, spec in BUILTIN_TEMPLATES.items():
        rel = _template_rel(template_id)
        path = resolve_vault_path(rel, vault_root=vault_root)
        if path.exists():
            continue
        content = (
            "---\n"
            f"template_id: {template_id}\n"
            f"name: {spec['name']}\n"
            f"description: {spec['description']}\n"
            f"default_folder: {spec['folder']}\n"
            "builtin: true\n"
            "---\n\n"
            + spec["body"]
        )
        patch_note(rel, content, if_match="NEW", actor="templates", privileged=True, vault_root=vault_root)
        created.append(rel)
    return created


def list_templates(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    ensure_templates(vault_root=vault_root)
    templates_dir = vault_root / TEMPLATES_DIR
    items: List[Dict[str, Any]] = []
    if templates_dir.exists():
        for md_file in sorted(templates_dir.glob("*.md"), key=lambda p: p.name.lower()):
            text = md_file.read_text(encoding="utf-8")
            fm = extract_frontmatter(text)
            rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
            items.append({
                "id": str(fm.get("template_id") or md_file.stem),
                "name": str(fm.get("name") or md_file.stem),
                "description": str(fm.get("description") or ""),
                "default_folder": str(fm.get("default_folder") or "30-Logs"),
                "path": rel,
                "builtin": bool(fm.get("builtin", False)),
            })
    return {"total": len(items), "templates": items}


def _safe_title(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", title).strip(" .")
    return safe or "untitled"


def create_from_template(
    template_id: str,
    title: str,
    *,
    vault_root: Path = VAULT_ROOT,
    folder: Optional[str] = None,
    variables: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """基于模板新建笔记，占位符自动替换，frontmatter 标注 template 与 status。"""
    ensure_templates(vault_root=vault_root)
    template_rel = _template_rel(template_id)
    template_path = resolve_vault_path(template_rel, vault_root=vault_root)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_id}")
    raw = template_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(raw)
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            body = parts[2].lstrip("\n")

    now = datetime.now()
    values = {
        "title": title,
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.strftime("%Y-%m-%d %H:%M"),
    }
    if variables:
        values.update({str(k): str(v) for k, v in variables.items()})
    rendered = body
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)

    target_folder = (folder or str(fm.get("default_folder") or "30-Logs")).replace("\\", "/").strip("/")
    filename = f"{now.strftime('%Y-%m-%d')}-{_safe_title(title)}.md"
    rel = f"{target_folder}/{filename}"
    target_path = resolve_vault_path(rel, vault_root=vault_root)
    seq = 2
    while target_path.exists():
        rel = f"{target_folder}/{now.strftime('%Y-%m-%d')}-{_safe_title(title)}-{seq}.md"
        target_path = resolve_vault_path(rel, vault_root=vault_root)
        seq += 1

    content = (
        "---\n"
        f'title: "{title.replace(chr(34), chr(39))}"\n'
        f"template: {template_id}\n"
        "status: draft\n"
        f"created: {now.strftime('%Y-%m-%d')}\n"
        "tags:\n"
        f'  - "#{template_id}"\n'
        "---\n\n"
        + rendered.rstrip() + "\n"
    )
    result = patch_note(rel, content, if_match="NEW", actor="templates", privileged=True, vault_root=vault_root)
    return {
        "status": "created",
        "path": rel,
        "template": template_id,
        "version": result["version"],
    }


def extract_action_items(content: str) -> List[Dict[str, Any]]:
    """解析笔记中的行动项 checklist（支持 (@负责人 ddl:日期) 后缀）。"""
    items: List[Dict[str, Any]] = []
    for line in content.splitlines():
        match = _ACTION_ITEM_RE.match(line)
        if not match:
            continue
        text = match.group("text").strip()
        owner = None
        ddl = None
        meta = _ACTION_META_RE.search(text)
        if meta:
            owner = meta.group("owner")
            ddl = meta.group("ddl")
            text = text[: meta.start()].strip()
        items.append({
            "text": text,
            "done": match.group("done").lower() == "x",
            "owner": owner,
            "ddl": ddl,
        })
    return items


def list_action_items(rel_path: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    items = extract_action_items(file_path.read_text(encoding="utf-8"))
    return {"path": rel_path.replace("\\", "/"), "total": len(items), "items": items}
