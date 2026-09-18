import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from nexusmind.config import VAULT_ROOT
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import extract_frontmatter, extract_tags, resolve_vault_path


def _make_snippet(text: str, start: int, end: int, radius: int = 100) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right].replace("\n", " ").strip()
    return ("…" if left else "") + snippet + ("…" if right < len(text) else "")


def search_notes(
    query: str,
    *,
    folder: Optional[str] = None,
    tags: Optional[List[str]] = None,
    properties: Optional[Dict[str, Any]] = None,
    regex: bool = False,
    limit: int = 50,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """全文 + 标签 + Frontmatter 属性过滤，并返回摘要和简单相关度评分。"""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    target_dir = resolve_vault_path(folder or ".", vault_root=vault_root)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Invalid target folder")

    try:
        pattern = re.compile(query, re.IGNORECASE) if regex and query else None
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {exc}") from exc

    wanted_tags = {
        tag if tag.startswith("#") else f"#{tag}"
        for tag in (tags or [])
    }
    properties = properties or {}
    results: List[Dict[str, Any]] = []

    for md_file in target_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = extract_frontmatter(text)
        note_tags = set(extract_tags(text))
        if wanted_tags and not wanted_tags.issubset(note_tags):
            continue
        if any(fm.get(key) != value for key, value in properties.items()):
            continue
        match = None
        if query:
            if pattern:
                match = pattern.search(text)
            else:
                idx = text.lower().find(query.lower())
                if idx >= 0:
                    match = re.match(re.escape(text[idx:idx + len(query)]), text[idx:])
                    if match:
                        match_start, match_end = idx, idx + len(query)
            if not pattern and match is None:
                continue
            if pattern and match is None:
                continue
        if pattern and match:
            match_start, match_end = match.span()
        elif not query:
            match_start = match_end = 0

        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        title = str(fm.get("title") or md_file.stem)
        score = 1.0
        if query:
            q = query.lower()
            score += 3.0 if q in title.lower() else 0.0
            score += min(text.lower().count(q), 10) * 0.2 if not regex else 0.5
        score += len(wanted_tags.intersection(note_tags)) * 0.5
        results.append({
            "path": rel,
            "title": title,
            "version": get_file_hash(text),
            "score": round(score, 2),
            "snippet": _make_snippet(text, match_start, match_end) if query else "",
            "tags": sorted(note_tags),
            "frontmatter": fm,
        })

    results.sort(key=lambda item: (-item["score"], item["path"].lower()))
    return {
        "query": query,
        "folder": folder,
        "total": len(results),
        "matches": results[:limit],
    }
