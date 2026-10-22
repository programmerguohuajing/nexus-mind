"""知识保鲜期：Domain 卡片到期复审队列（产品设计文档 P1-7）。

规则：
- 复审周期取 frontmatter `review_after`（如 "90d"、90、"180"），
  无则用默认：40-Domain 为 180 天，其他目录不纳入保鲜管理。
- 上次复审时间取 `last_reviewed` → `last_compiled_at` → 文件修改时间。
- 到期判定：上次复审 + 周期 < 今天。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import extract_frontmatter, resolve_vault_path

DEFAULT_REVIEW_DAYS = 180
_MANAGED_PREFIX = "40-Domain/"
_REVIEW_AFTER_RE = re.compile(r"^\s*(\d+)\s*d?\s*$")


def parse_review_after(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    match = _REVIEW_AFTER_RE.match(str(value))
    if match:
        return int(match.group(1))
    return None


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _last_activity(fm: Dict[str, Any], file_path: Path) -> date:
    for key in ("last_reviewed", "last_compiled_at", "updated", "created"):
        parsed = _parse_date(fm.get(key))
        if parsed:
            return parsed
    return datetime.fromtimestamp(file_path.stat().st_mtime).date()


def list_stale_notes(
    *,
    vault_root: Path = VAULT_ROOT,
    folder: str = "40-Domain",
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """列出已过复审期的笔记（默认只管 Domain 层）。"""
    today = today or date.today()
    root = resolve_vault_path(folder, vault_root=vault_root)
    stale: List[Dict[str, Any]] = []
    if root.exists():
        for md_file in sorted(root.rglob("*.md"), key=lambda p: str(p).lower()):
            rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
            if "/00-Index/" in rel:
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            fm = extract_frontmatter(text)
            if fm.get("merged_into"):
                continue
            cycle = parse_review_after(fm.get("review_after"))
            if cycle is None:
                if not rel.startswith(_MANAGED_PREFIX):
                    continue
                cycle = DEFAULT_REVIEW_DAYS
            last = _last_activity(fm, md_file)
            due = last + timedelta(days=cycle)
            if due < today:
                stale.append({
                    "path": rel,
                    "title": str(fm.get("title") or md_file.stem),
                    "last_reviewed": last.isoformat(),
                    "due_date": due.isoformat(),
                    "days_overdue": (today - due).days,
                    "review_after_days": cycle,
                })
    stale.sort(key=lambda item: -item["days_overdue"])
    return {"total": len(stale), "stale_notes": stale, "checked_at": today.isoformat()}


def _split_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    fm = extract_frontmatter(content)
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            body = parts[2].lstrip("\n")
    return fm, body


def mark_reviewed(
    rel_path: str,
    *,
    vault_root: Path = VAULT_ROOT,
    extend_days: Optional[int] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """确认复审：写回 last_reviewed=今天，并可调整 review_after 周期。"""
    today = today or date.today()
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel_path}")
    content = file_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(content)
    fm["last_reviewed"] = today.isoformat()
    if extend_days:
        fm["review_after"] = f"{int(extend_days)}d"
    header = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    new_content = f"---\n{header}\n---\n\n{body.rstrip()}\n"
    result = patch_note(
        rel_path,
        new_content,
        if_match=get_file_hash(content),
        actor="freshness-review",
        privileged=True,
        vault_root=vault_root,
    )
    return {
        "status": "reviewed",
        "path": rel_path.replace("\\", "/"),
        "last_reviewed": today.isoformat(),
        "review_after": fm.get("review_after"),
        "version": result["version"],
    }


def freshness_digest(*, vault_root: Path = VAULT_ROOT, today: Optional[date] = None) -> Dict[str, Any]:
    """生成保鲜复审周摘要（Markdown），供通知推送或治理页展示。"""
    data = list_stale_notes(vault_root=vault_root, today=today)
    stale = data["stale_notes"]
    if not stale:
        text = "✅ 本周没有过期的知识卡片，知识库保鲜状态良好。"
    else:
        lines = [f"⏰ 当前有 {len(stale)} 张知识卡片已过复审期，请安排复审：", ""]
        for item in stale[:20]:
            lines.append(
                f"- [[{item['path']}|{item['title']}]] · 逾期 {item['days_overdue']} 天"
                f"（应复审日 {item['due_date']}）"
            )
        if len(stale) > 20:
            lines.append(f"- ……另有 {len(stale) - 20} 张，详见治理页")
        text = "\n".join(lines)
    return {"total": len(stale), "digest": text, "stale_notes": stale}
