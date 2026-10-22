"""OKR / 目标跟踪（产品设计文档 P3-5）：目标进展由工作活动自动折算。

数据存 DATA_ROOT/goals.json（不进 Vault 正文）。KR 进展来源：
- manual：手动维护 current；
- notes_count：统计关联 folder/tag 下的笔记数；
- releases：扫描周期内 Daily Log 的 Release/Tag 记录（可按仓库名过滤）。
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusmind.config import GOALS_DATA_PATH, VAULT_ROOT
from nexusmind.core.search import search_notes


def _load(path: Optional[Path]) -> Dict[str, Any]:
    target = path or GOALS_DATA_PATH
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("objectives", [])
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"objectives": []}


def _save(path: Optional[Path], data: Dict[str, Any]) -> None:
    target = path or GOALS_DATA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_objectives(*, data_path: Optional[Path] = None) -> Dict[str, Any]:
    data = _load(data_path)
    return {"total": len(data["objectives"]), "objectives": data["objectives"]}


def create_objective(title: str, *, period: str = "", data_path: Optional[Path] = None) -> Dict[str, Any]:
    data = _load(data_path)
    objective = {
        "id": secrets.token_hex(4),
        "title": title,
        "period": period,
        "key_results": [],
    }
    data["objectives"].append(objective)
    _save(data_path, data)
    return objective


def add_key_result(
    objective_id: str,
    title: str,
    *,
    target: float = 1.0,
    unit: str = "",
    source: Optional[Dict[str, Any]] = None,
    data_path: Optional[Path] = None,
) -> Dict[str, Any]:
    data = _load(data_path)
    for objective in data["objectives"]:
        if objective["id"] == objective_id:
            kr = {
                "id": secrets.token_hex(4),
                "title": title,
                "target": target,
                "current": 0,
                "unit": unit,
                "source": source or {"type": "manual"},
            }
            objective["key_results"].append(kr)
            _save(data_path, data)
            return kr
    raise FileNotFoundError(f"Objective not found: {objective_id}")


def update_key_result_current(
    objective_id: str,
    kr_id: str,
    current: float,
    *,
    data_path: Optional[Path] = None,
) -> Dict[str, Any]:
    data = _load(data_path)
    for objective in data["objectives"]:
        if objective["id"] != objective_id:
            continue
        for kr in objective["key_results"]:
            if kr["id"] == kr_id:
                kr["current"] = current
                _save(data_path, data)
                return kr
    raise FileNotFoundError("Objective or key result not found")


_TAG_LINE_RE = re.compile(r"Release/Tag：(.+?)\s+—")


def _count_releases(vault_root: Path, repo: Optional[str], since: Optional[date]) -> int:
    daily_dir = vault_root / "30-Logs" / "Daily"
    if not daily_dir.exists():
        return 0
    count = 0
    current_repo = ""
    for log_file in sorted(daily_dir.glob("*.md")):
        if since:
            try:
                if date.fromisoformat(log_file.stem) < since:
                    continue
            except ValueError:
                pass
        text = log_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            heading = re.match(r"^###\s+(.+)$", line)
            if heading:
                current_repo = heading.group(1).strip()
            if "Release/Tag：" in line:
                if repo and repo != current_repo:
                    continue
                count += 1
    return count


def _kr_measured_value(kr: Dict[str, Any], vault_root: Path, since: Optional[date]) -> float:
    source = kr.get("source") or {"type": "manual"}
    kind = source.get("type", "manual")
    if kind == "notes_count":
        folder = source.get("folder")
        tag = source.get("tag")
        if tag:
            result = search_notes("", tags=[tag], limit=200, vault_root=vault_root)
            return float(result["total"])
        if folder:
            base = vault_root / str(folder)
            return float(len(list(base.rglob("*.md")))) if base.exists() else 0.0
        return float(kr.get("current", 0))
    if kind == "releases":
        return float(_count_releases(vault_root, source.get("repo"), since))
    return float(kr.get("current", 0))


def compute_progress(
    *,
    vault_root: Path = VAULT_ROOT,
    data_path: Optional[Path] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """计算全部目标的 KR 进展（自动来源实时折算，手动来源用存储值）。"""
    data = _load(data_path)
    since_date = date.fromisoformat(since) if since else None
    objectives_out: List[Dict[str, Any]] = []
    for objective in data["objectives"]:
        krs_out: List[Dict[str, Any]] = []
        for kr in objective.get("key_results", []):
            measured = _kr_measured_value(kr, vault_root, since_date)
            target = float(kr.get("target") or 1)
            progress = round(min(measured / target, 1.0), 4) if target > 0 else 0.0
            krs_out.append({**kr, "measured": measured, "progress": progress})
        overall = round(sum(k["progress"] for k in krs_out) / len(krs_out), 4) if krs_out else 0.0
        objectives_out.append({**objective, "key_results": krs_out, "progress": overall})
    return {"objectives": objectives_out}


def goals_review_section(
    *,
    vault_root: Path = VAULT_ROOT,
    data_path: Optional[Path] = None,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """生成可嵌入周复盘的「目标进展」章节（Markdown）。"""
    result = compute_progress(vault_root=vault_root, data_path=data_path, since=since)
    if not result["objectives"]:
        return {"section": "", "objectives": []}
    lines = ["## 🎯 目标进展", ""]
    for objective in result["objectives"]:
        lines.append(f"### {objective['title']}（整体 {round(objective['progress'] * 100, 1)}%）")
        for kr in objective["key_results"]:
            lines.append(
                f"- {kr['title']}：{kr['measured']}/{kr['target']}{kr.get('unit', '')}"
                f"（{round(kr['progress'] * 100, 1)}%）"
            )
        lines.append("")
    return {"section": "\n".join(lines).rstrip() + "\n", "objectives": result["objectives"]}
