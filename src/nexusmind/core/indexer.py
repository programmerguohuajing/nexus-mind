from pathlib import Path
from typing import Any, Dict, List

from nexusmind.config import VAULT_ROOT
from nexusmind.core.storage import (
    extract_frontmatter,
    extract_links,
    find_backlinks,
    get_all_note_identifiers,
    normalize_link_target,
)


def find_broken_links(vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """巡检全库未解析 Wikilink，正确忽略标题/块锚点与 .md 后缀。"""
    all_notes = get_all_note_identifiers(vault_root=vault_root)
    normalized_notes = {normalize_link_target(x) for x in all_notes}
    broken: List[Dict[str, str]] = []

    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        try:
            links = extract_links(md_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        for raw_link in links:
            target = normalize_link_target(raw_link)
            if not target:
                continue
            stem = Path(target).stem
            if target not in normalized_notes and stem not in normalized_notes:
                broken.append({"source": rel, "broken_link": f"[[{raw_link}]]"})
    unique = {(x["source"], x["broken_link"]): x for x in broken}
    values = sorted(unique.values(), key=lambda x: (x["source"], x["broken_link"]))
    return {"total_broken": len(values), "broken_links": values}


def find_orphans(vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """巡检正式知识/项目中的孤岛笔记。"""
    excluded = ("00-Meta/", "30-Logs/", "60-References/", "90-AI-Workspace/")
    orphans: List[str] = []
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith(excluded):
            continue
        if not find_backlinks(rel, vault_root=vault_root):
            orphans.append(rel)
    return {"total_orphans": len(orphans), "orphans": sorted(orphans)}


def rebuild_sub_indices(vault_root: Path = VAULT_ROOT) -> Dict[str, int]:
    """扫描 40-Domain 子域，生成二级渐进式索引。"""
    domain_dir = vault_root / "40-Domain"
    index_dir = domain_dir / "00-Index"
    index_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, int] = {}

    sub_folders = [
        d for d in domain_dir.iterdir()
        if d.is_dir() and d.name != "00-Index"
    ] if domain_dir.exists() else []

    for folder in sorted(sub_folders, key=lambda p: p.name.lower()):
        cards = sorted(folder.glob("*.md"), key=lambda p: p.name.lower())
        lines: List[str] = []
        for card in cards:
            rel = str(card.relative_to(vault_root)).replace("\\", "/")
            text = card.read_text(encoding="utf-8")
            fm = extract_frontmatter(text)
            title = fm.get("title", card.stem)
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            tag_text = " ".join(f"`{tag}`" for tag in tags)
            lines.append(f"- [[{rel}|{title}]] {tag_text}".rstrip())

        sub_index = index_dir / f"{folder.name}-Index.md"
        body = "\n".join(lines) if lines else "*暂无卡片*"
        content = (
            f"# 📁 {folder.name} 领域二级子索引\n\n"
            f"> 自动生成；包含 {len(cards)} 张原子知识卡片。\n\n"
            f"## 🗂️ 卡片清单\n\n{body}\n\n"
            "- 返回：[[40-Domain/00-Index/Master-Index|Master Index]]\n"
        )
        sub_index.write_text(content, encoding="utf-8")
        summary[folder.name] = len(cards)
    return summary


def rebuild_master_index(vault_root: Path = VAULT_ROOT) -> str:
    """汇总二级索引，Master 只保留高维导航，避免递归收录自身。"""
    domain_dir = vault_root / "40-Domain"
    index_dir = domain_dir / "00-Index"
    index_dir.mkdir(parents=True, exist_ok=True)
    nav: List[str] = []
    sub_indices = [
        p for p in index_dir.glob("*-Index.md")
        if p.name != "Master-Index.md"
    ]
    for idx in sorted(sub_indices, key=lambda p: p.name.lower()):
        category = idx.stem.removesuffix("-Index")
        rel = str(idx.relative_to(vault_root)).replace("\\", "/")
        card_dir = domain_dir / category
        count = len(list(card_dir.glob("*.md"))) if card_dir.exists() else 0
        nav.append(f"- [[{rel}|{category}]] · {count} 张卡片")

    nav_text = "\n".join(nav) if nav else "*暂无子领域索引*"
    content = (
        "# 🌐 领域知识主索引树 (Master Index)\n\n"
        "> 仅保留高维导航。检索时先读本页，再按需下钻二级索引。\n\n"
        "## 子领域导航\n\n"
        f"{nav_text}\n\n"
        "## 全局入口\n"
        "- [[00-Meta/COMPILATION-LOG|增量编译日志]]\n"
        "- [[40-Domain/Architecture/architecture-map.canvas|架构 Canvas]]\n"
    )
    master = index_dir / "Master-Index.md"
    master.write_text(content, encoding="utf-8")
    return str(master.relative_to(vault_root)).replace("\\", "/")


def rebuild_all_indices(vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    sub = rebuild_sub_indices(vault_root=vault_root)
    master = rebuild_master_index(vault_root=vault_root)
    return {"status": "success", "sub_indices": sub, "master_index": master}
