"""数据看板与搜索分析（产品设计文档 P3-7）。

- 搜索无结果日志：.nexusmind/search-log.jsonl（指导补什么知识）；
- 看板：知识增长（按周）、最常被引用 Top、标签云、健康度四象限汇总。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.duplicates import find_duplicate_pairs
from nexusmind.core.freshness import list_stale_notes
from nexusmind.core.indexer import find_broken_links, find_orphans
from nexusmind.core.storage import (
    extract_links,
    extract_tags,
    get_all_note_identifiers,
    normalize_link_target,
)

_LOG_NAME = "search-log.jsonl"


def log_search_miss(query: str, *, vault_root: Path = VAULT_ROOT, source: str = "search") -> None:
    """记录一次无结果搜索（失败不影响主流程）。"""
    try:
        path = vault_root / ".nexusmind" / _LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "source": source,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def top_search_misses(*, vault_root: Path = VAULT_ROOT, limit: int = 10) -> List[Dict[str, Any]]:
    path = vault_root / ".nexusmind" / _LOG_NAME
    counter: Counter = Counter()
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                query = str(record.get("query") or "").strip()
                if query:
                    counter[query] += 1
        except OSError:
            pass
    return [{"query": q, "count": c} for q, c in counter.most_common(limit)]


def _weekly_growth(vault_root: Path, weeks: int = 8) -> List[Dict[str, Any]]:
    """按文件 mtime 统计最近 N 周每周新增笔记数与累计数（近似增长曲线）。"""
    now = datetime.now()
    current_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets: List[Dict[str, Any]] = []
    starts = [current_monday - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]
    counts = [0] * weeks
    total_files = 0
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith((".history/", ".nexusmind/")):
            continue
        total_files += 1
        try:
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        except OSError:
            continue
        for idx, start in enumerate(starts):
            end = start + timedelta(weeks=1)
            if start <= mtime < end:
                counts[idx] += 1
                break
    cumulative = total_files - sum(counts)
    for idx, start in enumerate(starts):
        cumulative += counts[idx]
        buckets.append({
            "week_start": start.date().isoformat(),
            "added": counts[idx],
            "cumulative": cumulative,
        })
    return buckets


def _top_referenced(vault_root: Path, limit: int = 10) -> List[Dict[str, Any]]:
    """单遍扫描统计被引用次数最多的笔记（按 wikilink 目标解析）。"""
    identifiers = get_all_note_identifiers(vault_root=vault_root)
    by_normalized: Dict[str, str] = {}
    by_stem: Dict[str, str] = {}
    rel_of: Dict[Path, str] = {}
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith((".history/", ".nexusmind/")):
            continue
        rel_of[md_file] = rel
        by_normalized[normalize_link_target(rel)] = rel
        by_stem.setdefault(Path(rel).stem, rel)
    _ = identifiers
    counter: Counter = Counter()
    for md_file, rel in rel_of.items():
        try:
            links = extract_links(md_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        for raw in links:
            target = normalize_link_target(raw)
            resolved = by_normalized.get(target) or by_stem.get(Path(target).stem)
            if resolved and resolved != rel:
                counter[resolved] += 1
    return [{"path": path, "references": count} for path, count in counter.most_common(limit)]


def _tag_cloud(vault_root: Path, limit: int = 20) -> List[Dict[str, Any]]:
    counter: Counter = Counter()
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith((".history/", ".nexusmind/")):
            continue
        try:
            counter.update(extract_tags(md_file.read_text(encoding="utf-8")))
        except OSError:
            continue
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(limit)]


def dashboard_analytics(*, vault_root: Path = VAULT_ROOT, weeks: int = 8) -> Dict[str, Any]:
    """团队/个人知识看板汇总。"""
    total_notes = 0
    for md_file in vault_root.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if not rel.startswith((".history/", ".nexusmind/")):
            total_notes += 1
    broken = find_broken_links(vault_root=vault_root)
    orphans = find_orphans(vault_root=vault_root)
    stale = list_stale_notes(vault_root=vault_root)
    duplicates = find_duplicate_pairs(vault_root=vault_root)
    return {
        "total_notes": total_notes,
        "growth": _weekly_growth(vault_root, weeks=weeks),
        "top_referenced": _top_referenced(vault_root),
        "tag_cloud": _tag_cloud(vault_root),
        "health": {
            "broken_links": broken["total_broken"],
            "orphans": orphans["total_orphans"],
            "stale_notes": stale["total"],
            "duplicate_pairs": duplicates["total"],
        },
        "search_misses": top_search_misses(vault_root=vault_root),
    }
