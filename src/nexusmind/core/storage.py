import re
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml
from fastapi import HTTPException

from nexusmind.config import VAULT_ROOT
from nexusmind.core.occ import get_file_hash  # backward-compatible export

WIKILINK_RE = re.compile(r"\[\[(.*?)(?:\|(.*?))?\]\]")
TAG_RE = re.compile(r"(?<![\w/])#([\w\-\u4e00-\u9fff]+)")


def normalize_link_target(target: str) -> str:
    """去掉 Obsidian 链接中的标题锚点、块锚点和 .md 后缀。"""
    target = target.strip().split("#", 1)[0].split("^", 1)[0].strip()
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target.replace("\\", "/")


def extract_links(content: str) -> List[str]:
    """提取 Markdown 中的 Wikilink 目标，保留原路径但忽略显示别名。"""
    links = {m.group(1).strip() for m in WIKILINK_RE.finditer(content)}
    return sorted(links)


def extract_frontmatter(content: str) -> Dict[str, Any]:
    """解析 Markdown 头部 YAML Frontmatter。"""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1]
    try:
        data = yaml.safe_load(raw)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        # 兼容 Obsidian 常见的 tags: [#tag1, #tag2] 非标准 YAML 写法。
        def quote_hash_tags(match: re.Match) -> str:
            values = [v.strip() for v in match.group(1).split(",")]
            quoted = [f'"{v}"' if v.startswith("#") else v for v in values]
            return "tags: [" + ", ".join(quoted) + "]"

        repaired = re.sub(r"tags:\s*\[([^\]]+)\]", quote_hash_tags, raw)
        try:
            data = yaml.safe_load(repaired)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}


def extract_tags(content: str) -> List[str]:
    """合并 frontmatter tags 与正文 #tag，统一返回带 # 的标签。"""
    tags: Set[str] = set()
    fm_tags = extract_frontmatter(content).get("tags", [])
    if isinstance(fm_tags, str):
        fm_tags = [fm_tags]
    if isinstance(fm_tags, list):
        for tag in fm_tags:
            if tag:
                value = str(tag).strip()
                tags.add(value if value.startswith("#") else f"#{value}")
    for match in TAG_RE.finditer(content):
        tags.add(f"#{match.group(1)}")
    return sorted(tags)


def resolve_vault_path(rel_path: str, vault_root: Path = VAULT_ROOT) -> Path:
    """安全解析 Vault 相对路径，阻断 .. 与绝对路径越界。"""
    root = vault_root.resolve()
    file_path = (root / rel_path).resolve()
    if not file_path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid path outside vault")
    return file_path


def get_all_note_identifiers(vault_root: Path = VAULT_ROOT) -> Set[str]:
    """建立可用于 Wikilink 解析的路径、文件名、stem 标识集合。"""
    identifiers: Set[str] = set()
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        rel_no_ext = rel[:-3] if rel.lower().endswith(".md") else rel
        identifiers.update({rel, rel_no_ext, md_file.name, md_file.stem})
    return identifiers


def find_backlinks(target_name: str, vault_root: Path = VAULT_ROOT) -> List[str]:
    """计算真正指向目标笔记的反向链接，避免简单字符串包含造成误报。"""
    target = normalize_link_target(target_name)
    target_stem = Path(target).stem
    backlinks: List[str] = []
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if normalize_link_target(rel) == target:
            continue
        try:
            links = extract_links(md_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        normalized = {normalize_link_target(link) for link in links}
        if target in normalized or target_stem in {Path(x).stem for x in normalized}:
            backlinks.append(f"[[{rel}]]")
    return sorted(set(backlinks))
