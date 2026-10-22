"""入库智能处理与智能补链（产品设计文档 P2-3 / P2-5）。

所有产出都是"建议"，由用户确认后才应用（人在回路）：
- 摘要：LLM 生成或抽取式降级；
- 标签：优先复用知识库已有标签体系（与笔记内容匹配的高频标签）；
- 链接：语义近邻中尚未建立链接的笔记。
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note, scan_uncompiled_sources
from nexusmind.core.embeddings import semantic_search
from nexusmind.core.llm import LlmUnavailable, generate, llm_status
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import (
    extract_frontmatter,
    extract_links,
    extract_tags,
    find_backlinks,
    normalize_link_target,
    resolve_vault_path,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s*")


def _body_of(content: str) -> str:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return content.strip()


def extractive_summary(content: str, *, max_chars: int = 200) -> str:
    """抽取式摘要：取正文首个有信息量的段落的前几句。"""
    body = _body_of(content)
    lines = [line.strip() for line in body.splitlines() if line.strip() and not line.startswith(("#", ">", "-", "|", "```"))]
    text = " ".join(lines)
    if not text:
        return ""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) > max_chars and summary:
            break
        summary += sentence
    return summary[:max_chars].strip()


def _llm_summary(title: str, content: str) -> Optional[str]:
    if not llm_status()["available"]:
        return None
    body = _body_of(content)[:3000]
    try:
        text = generate(
            f"用中文为下面这篇笔记写一段不超过 200 字的摘要，只写摘要正文，不要标题和前缀。\n\n标题：{title}\n\n正文：\n{body}",
            temperature=0.2,
        )
        return text.strip()[:400] or None
    except LlmUnavailable:
        return None


def _existing_tag_pool(vault_root: Path) -> Counter:
    pool: Counter = Counter()
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith((".history/", ".nexusmind/")):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for tag in extract_tags(text):
            pool[tag] += 1
    return pool


def suggest_tags(content: str, vault_root: Path, *, limit: int = 5) -> List[Dict[str, Any]]:
    """从全库已有标签中推荐与正文关键词匹配的标签（复用标签体系，避免标签爆炸）。"""
    pool = _existing_tag_pool(vault_root)
    current = set(extract_tags(content))
    body_lower = _body_of(content).lower()
    scored: List[Dict[str, Any]] = []
    for tag, freq in pool.items():
        if tag in current:
            continue
        keyword = tag.lstrip("#").lower()
        if len(keyword) < 2:
            continue
        hits = body_lower.count(keyword)
        if hits:
            scored.append({"tag": tag, "score": round(hits * (1 + min(freq, 10) * 0.05), 3), "vault_frequency": freq})
    scored.sort(key=lambda item: -item["score"])
    return scored[:limit]


def suggest_links(
    rel_path: str,
    *,
    vault_root: Path = VAULT_ROOT,
    limit: int = 5,
    min_score: float = 0.15,
) -> Dict[str, Any]:
    """为笔记推荐尚未建立链接的语义近邻（排除已链接/已反链/自身）。"""
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    content = file_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(content)
    title = str(fm.get("title") or file_path.stem)
    query = f"{title}\n{_body_of(content)[:600]}"
    result = semantic_search(query, vault_root=vault_root, limit=limit + 8)

    linked = {normalize_link_target(x) for x in extract_links(content)}
    backlinked = {normalize_link_target(x) for x in find_backlinks(rel_path, vault_root=vault_root)}
    self_norm = normalize_link_target(rel_path)
    suggestions: List[Dict[str, Any]] = []
    for item in result["matches"]:
        target_norm = normalize_link_target(item["path"])
        if target_norm == self_norm or target_norm in linked or target_norm in backlinked:
            continue
        if float(item["score"]) < min_score:
            continue
        suggestions.append({
            "path": item["path"],
            "title": item["title"],
            "score": item["score"],
            "reason": "语义相近且尚未建立链接",
        })
        if len(suggestions) >= limit:
            break
    return {"path": rel_path.replace("\\", "/"), "total": len(suggestions), "suggestions": suggestions}


def suggest_for_note(rel_path: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """单篇笔记的完整处理建议：摘要 + 标签 + 链接（不落盘）。"""
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    content = file_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(content)
    title = str(fm.get("title") or file_path.stem)
    summary = _llm_summary(title, content)
    summary_mode = "llm" if summary else "extractive"
    if not summary:
        summary = extractive_summary(content)
    links = suggest_links(rel_path, vault_root=vault_root)["suggestions"]
    return {
        "path": rel_path.replace("\\", "/"),
        "title": title,
        "summary": summary,
        "summary_mode": summary_mode,
        "tags": suggest_tags(content, vault_root),
        "links": links,
    }


def apply_suggestions(
    rel_path: str,
    *,
    vault_root: Path = VAULT_ROOT,
    summary: Optional[str] = None,
    tags: Optional[List[str]] = None,
    links: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """应用用户确认后的建议：摘要/标签写 frontmatter，链接追加到文末相关链接区。"""
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    content = file_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(content)
    body = _body_of(content)

    if summary:
        fm["summary"] = summary
    if tags:
        existing = fm.get("tags", [])
        if isinstance(existing, str):
            existing = [existing]
        merged = list(existing)
        for tag in tags:
            normalized = tag if tag.startswith("#") else f"#{tag}"
            if normalized not in merged:
                merged.append(normalized)
        fm["tags"] = merged
    if links:
        section_lines = [f"- [[{link}]]" for link in links]
        if "## 相关链接" in body:
            body = body.rstrip() + "\n" + "\n".join(section_lines) + "\n"
        else:
            body = body.rstrip() + "\n\n## 相关链接\n\n" + "\n".join(section_lines) + "\n"

    header = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    new_content = f"---\n{header}\n---\n\n{body.rstrip()}\n"
    result = patch_note(
        rel_path,
        new_content,
        if_match=get_file_hash(content),
        actor="smart-suggestions",
        privileged=True,
        vault_root=vault_root,
    )
    return {"status": "applied", "path": rel_path.replace("\\", "/"), "version": result["version"]}


def batch_pending_suggestions(*, vault_root: Path = VAULT_ROOT, days: int = 30, limit: int = 50) -> Dict[str, Any]:
    """对编译队列中积压（默认 30 天内未编译）的 Raw 生成处理建议清单。"""
    cutoff = datetime.now() - timedelta(days=days)
    items: List[Dict[str, Any]] = []
    for path in scan_uncompiled_sources(vault_root=vault_root):
        rel = str(path.relative_to(vault_root)).replace("\\", "/")
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            continue
        suggestion = suggest_for_note(rel, vault_root=vault_root)
        items.append(suggestion)
        if len(items) >= limit:
            break
    return {"total": len(items), "items": items}
