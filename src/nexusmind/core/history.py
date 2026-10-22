"""版本历史：每次写入前把旧版本快照到 Vault/.history/，支持查看、对比与回滚。

快照使用 .snap 后缀而非 .md，避免污染全文搜索、知识图谱与索引扫描。
快照目录结构：.history/<笔记相对路径>/<UTC时间戳>__<内容hash>.snap
"""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from nexusmind.config import HISTORY_KEEP, VAULT_ROOT
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import resolve_vault_path

HISTORY_DIRNAME = ".history"
_SNAP_RE = re.compile(r"^(?P<ts>\d{8}T\d{12})__(?P<hash>[0-9a-f]{12})\.snap$")


def _history_dir(rel_path: str, vault_root: Path) -> Path:
    rel = rel_path.replace("\\", "/").strip("/")
    return vault_root / HISTORY_DIRNAME / rel


def snapshot_note(
    rel_path: str,
    old_content: str,
    *,
    vault_root: Path = VAULT_ROOT,
    keep: int = HISTORY_KEEP,
) -> Optional[Dict[str, Any]]:
    """在覆盖写入前保存旧内容快照；失败不阻断写入（由调用方决定是否吞异常）。"""
    version = get_file_hash(old_content)
    target_dir = _history_dir(rel_path, vault_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    snap_path = target_dir / f"{stamp}__{version}.snap"
    snap_path.write_text(old_content, encoding="utf-8")
    _prune(rel_path, vault_root=vault_root, keep=keep)
    return {
        "version": version,
        "snapshot": str(snap_path.relative_to(vault_root)).replace("\\", "/"),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _prune(rel_path: str, *, vault_root: Path, keep: int) -> None:
    target_dir = _history_dir(rel_path, vault_root)
    if not target_dir.exists():
        return
    snaps = sorted(target_dir.glob("*.snap"))
    excess = len(snaps) - max(1, keep)
    for snap in snaps[: max(0, excess)]:
        try:
            snap.unlink()
        except OSError:
            pass


def _parse_snap_name(name: str) -> Optional[Dict[str, str]]:
    match = _SNAP_RE.match(name)
    if not match:
        return None
    ts_raw = match.group("ts")
    try:
        created = datetime.strptime(ts_raw, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)
        created_text = created.isoformat(timespec="seconds")
    except ValueError:
        created_text = ts_raw
    return {"version": match.group("hash"), "created_at": created_text}


def list_history(rel_path: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """列出某篇笔记的历史版本（最新在前）。"""
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    current_version = None
    if file_path.is_file():
        current_version = get_file_hash(file_path.read_text(encoding="utf-8"))
    target_dir = _history_dir(rel_path, vault_root)
    versions: List[Dict[str, Any]] = []
    if target_dir.exists():
        for snap in sorted(target_dir.glob("*.snap"), reverse=True):
            meta = _parse_snap_name(snap.name)
            if not meta:
                continue
            versions.append({
                **meta,
                "size": snap.stat().st_size,
                "is_current": meta["version"] == current_version,
            })
    return {
        "path": rel_path.replace("\\", "/"),
        "current_version": current_version,
        "total": len(versions),
        "versions": versions,
    }


def read_snapshot(rel_path: str, version: str, *, vault_root: Path = VAULT_ROOT) -> str:
    target_dir = _history_dir(rel_path, vault_root)
    candidates = sorted(target_dir.glob(f"*__{version}.snap")) if target_dir.exists() else []
    if not candidates:
        raise HTTPException(status_code=404, detail=f"History version not found: {version}")
    return candidates[-1].read_text(encoding="utf-8")


def diff_snapshot(rel_path: str, version: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """生成历史版本与当前版本的 unified diff。"""
    old = read_snapshot(rel_path, version, vault_root=vault_root)
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    current = file_path.read_text(encoding="utf-8")
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        current.splitlines(keepends=True),
        fromfile=f"{rel_path}@{version}",
        tofile=f"{rel_path}@current",
    )
    return {
        "path": rel_path.replace("\\", "/"),
        "version": version,
        "current_version": get_file_hash(current),
        "diff": "".join(diff),
    }


def rollback_note(rel_path: str, version: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """回滚到历史版本：走统一写入入口，回滚本身生成新版本（当前内容会被快照）。"""
    from nexusmind.core.compiler import patch_note

    old_content = read_snapshot(rel_path, version, vault_root=vault_root)
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Note not found")
    current_version = get_file_hash(file_path.read_text(encoding="utf-8"))
    result = patch_note(
        rel_path,
        old_content,
        if_match=current_version,
        actor="history-rollback",
        privileged=True,
        vault_root=vault_root,
    )
    return {
        "status": "rolled_back",
        "path": rel_path.replace("\\", "/"),
        "from_version": current_version,
        "restored_version": version,
        "new_version": result["version"],
    }
