"""团队空间轻协作（产品设计文档 P3-3）：评论 / @提及 / 公开分享 / 空间可见性。

不做实时协同编辑（非目标）。协作数据存 Vault/.nexusmind/：
- comments.json：{笔记路径: [评论]}（评论不写进笔记正文，避免污染知识内容）
- shares.json：{token: {path, created_at, expires_at, password_hash}}
- spaces.json：[{name, folders, visibility, members}]
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from nexusmind.config import VAULT_ROOT
from nexusmind.core.storage import extract_frontmatter, resolve_vault_path

_MENTION_RE = re.compile(r"@([\w\-.\u4e00-\u9fff]+)")


def _load_json(vault_root: Path, name: str, default: Any) -> Any:
    path = vault_root / ".nexusmind" / name
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (OSError, json.JSONDecodeError):
            pass
    return default


def _save_json(vault_root: Path, name: str, data: Any) -> None:
    path = vault_root / ".nexusmind" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- 评论 ----------------

def list_comments(rel_path: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    data = _load_json(vault_root, "comments.json", {})
    comments = data.get(rel_path.replace("\\", "/"), [])
    return {"path": rel_path.replace("\\", "/"), "total": len(comments), "comments": comments}


def add_comment(
    rel_path: str,
    author: str,
    content: str,
    *,
    vault_root: Path = VAULT_ROOT,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    rel = rel_path.replace("\\", "/")
    file_path = resolve_vault_path(rel, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel}")
    data = _load_json(vault_root, "comments.json", {})
    comment = {
        "id": secrets.token_hex(6),
        "author": author,
        "content": content,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "parent_id": parent_id,
        "resolved": False,
        "mentions": sorted(set(_MENTION_RE.findall(content))),
        "helpful": 0,
    }
    data.setdefault(rel, []).append(comment)
    _save_json(vault_root, "comments.json", data)
    return {"status": "added", "comment": comment}


def resolve_comment(rel_path: str, comment_id: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    rel = rel_path.replace("\\", "/")
    data = _load_json(vault_root, "comments.json", {})
    for comment in data.get(rel, []):
        if comment.get("id") == comment_id:
            comment["resolved"] = True
            _save_json(vault_root, "comments.json", data)
            return {"status": "resolved", "comment": comment}
    raise FileNotFoundError(f"Comment not found: {comment_id}")


def mark_helpful(rel_path: str, comment_id: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    rel = rel_path.replace("\\", "/")
    data = _load_json(vault_root, "comments.json", {})
    for comment in data.get(rel, []):
        if comment.get("id") == comment_id:
            comment["helpful"] = int(comment.get("helpful", 0)) + 1
            _save_json(vault_root, "comments.json", data)
            return {"status": "ok", "comment": comment}
    raise FileNotFoundError(f"Comment not found: {comment_id}")


# ---------------- 公开分享 ----------------

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_share(
    rel_path: str,
    *,
    vault_root: Path = VAULT_ROOT,
    ttl_days: int = 7,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    rel = rel_path.replace("\\", "/")
    file_path = resolve_vault_path(rel, vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError(f"Note not found: {rel}")
    token = secrets.token_urlsafe(24)
    now = datetime.now()
    record = {
        "path": rel,
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(days=max(1, ttl_days))).isoformat(timespec="seconds"),
        "password_hash": _hash_password(password) if password else None,
    }
    data = _load_json(vault_root, "shares.json", {})
    data[token] = record
    _save_json(vault_root, "shares.json", data)
    return {"token": token, "url_path": f"/api/share/{token}", **record, "password_hash": bool(record["password_hash"])}


def read_share(token: str, *, vault_root: Path = VAULT_ROOT, password: Optional[str] = None) -> Dict[str, Any]:
    data = _load_json(vault_root, "shares.json", {})
    record = data.get(token)
    if not record:
        raise FileNotFoundError("Share link not found")
    if datetime.now() > datetime.fromisoformat(record["expires_at"]):
        raise ValueError("Share link expired")
    if record.get("password_hash"):
        if not password or _hash_password(password) != record["password_hash"]:
            raise PermissionError("Share password required or incorrect")
    file_path = resolve_vault_path(record["path"], vault_root=vault_root)
    if not file_path.is_file():
        raise FileNotFoundError("Shared note no longer exists")
    content = file_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(content)
    return {
        "path": record["path"],
        "title": str(fm.get("title") or Path(record["path"]).stem),
        "content": content,
        "expires_at": record["expires_at"],
    }


def revoke_share(token: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    data = _load_json(vault_root, "shares.json", {})
    if token not in data:
        raise FileNotFoundError("Share link not found")
    del data[token]
    _save_json(vault_root, "shares.json", data)
    return {"status": "revoked", "token": token}


# ---------------- 团队空间 ----------------

def list_spaces(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    spaces = _load_json(vault_root, "spaces.json", [])
    return {"total": len(spaces), "spaces": spaces}


def upsert_space(
    name: str,
    *,
    folders: List[str],
    visibility: str = "members",
    members: Optional[List[str]] = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    if visibility not in {"public", "members", "private"}:
        raise ValueError("visibility must be public|members|private")
    spaces = _load_json(vault_root, "spaces.json", [])
    record = {
        "name": name,
        "folders": [f.replace("\\", "/").strip("/") for f in folders],
        "visibility": visibility,
        "members": members or [],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    spaces = [s for s in spaces if s.get("name") != name] + [record]
    _save_json(vault_root, "spaces.json", spaces)
    return {"status": "saved", "space": record}


def space_visible_notes(space_name: str, *, member: Optional[str] = None, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """按空间可见性列出成员可见的笔记（private 仅成员，members 需成员身份，public 任何人）。"""
    spaces = _load_json(vault_root, "spaces.json", [])
    space = next((s for s in spaces if s.get("name") == space_name), None)
    if not space:
        raise FileNotFoundError(f"Space not found: {space_name}")
    visibility = space.get("visibility", "members")
    members = space.get("members", [])
    if visibility == "private" and member not in members:
        return {"space": space_name, "visibility": visibility, "total": 0, "notes": [], "reason": "private space: member required"}
    if visibility == "members" and member is not None and member not in members:
        return {"space": space_name, "visibility": visibility, "total": 0, "notes": [], "reason": "not a space member"}
    notes: List[str] = []
    for folder in space.get("folders", []):
        base = vault_root / folder
        if base.exists():
            for md_file in sorted(base.rglob("*.md"), key=lambda p: str(p).lower()):
                notes.append(str(md_file.relative_to(vault_root)).replace("\\", "/"))
    return {"space": space_name, "visibility": visibility, "total": len(notes), "notes": notes}
