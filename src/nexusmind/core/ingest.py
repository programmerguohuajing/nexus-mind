from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note


def _safe_filename(title: str) -> str:
    safe = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    return safe or f"article-{int(datetime.now().timestamp())}"


def _unique_raw_path(folder: str, safe_title: str, vault_root: Path) -> str:
    """Raw 层不可变：同名再次导入时创建新文件而不是覆盖。"""
    base = f"{folder.rstrip('/')}/{safe_title}.md"
    if not (vault_root / base).exists():
        return base
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"{folder.rstrip('/')}/{safe_title}-{stamp}.md"
    seq = 2
    while (vault_root / candidate).exists():
        candidate = f"{folder.rstrip('/')}/{safe_title}-{stamp}-{seq}.md"
        seq += 1
    return candidate


def ingest_article(
    title: str,
    content: str,
    author: Optional[str] = "Unknown",
    url: Optional[str] = None,
    folder: str = "60-References/Articles",
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """受控采集网关：只允许向 Raw 层新增，不允许覆盖已有原始材料。"""
    normalized_folder = folder.replace("\\", "/").strip("/")
    if not normalized_folder.startswith("60-References/"):
        raise ValueError("Ingestion target must be under 60-References/")

    safe_title = _safe_filename(title)
    file_rel_path = _unique_raw_path(normalized_folder, safe_title, vault_root)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frontmatter = f"""---
title: "{title.replace('"', "'")}"
author: "{(author or 'Unknown').replace('"', "'")}"
url: "{(url or '').replace('"', "'")}"
ingested_at: "{timestamp}"
tags:
  - "#raw-reference"
  - "#ingested"
---

"""
    full_markdown = frontmatter + content.strip() + "\n"
    res = patch_note(
        file_rel_path,
        full_markdown,
        if_match="NEW",
        actor="gateway",
        privileged=True,
        vault_root=vault_root,
    )
    return {
        "status": "ingested_successfully",
        "title": title,
        "path": file_rel_path,
        "version": res["version"],
    }
