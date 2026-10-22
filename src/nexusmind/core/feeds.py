"""输入管道（产品设计文档 P3-6）：RSS 订阅自动入库 + 邮件转发入库。

- RSS：配置存 DATA_ROOT/feeds-config.json，去重状态存同目录 feeds-state.json。
- 邮件：IMAP 轮询（配置含 password_env 环境变量名，密码不落盘配置）；
  未读邮件解析为 Raw 笔记后标记已读。
"""
from __future__ import annotations

import email
import imaplib
import json
import os
import re
from email.header import decode_header
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import httpx

from nexusmind.config import FEEDS_CONFIG_PATH, VAULT_ROOT
from nexusmind.core.ingest import ingest_article

_ATOM = {"atom": "http://www.w3.org/2005/Atom"}


def _fetch(url: str) -> bytes:
    """统一抓取（测试可 monkeypatch）。"""
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": "NexusMind/0.4 feeds"})
        resp.raise_for_status()
        return resp.content


def load_feeds_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or FEEDS_CONFIG_PATH
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("feeds", [])
                data.setdefault("email", None)
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"feeds": [], "email": None}


def save_feeds_config(data: Dict[str, Any], config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or FEEDS_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_feeds_config(path)


def _state_path(config_path: Optional[Path]) -> Path:
    base = config_path or FEEDS_CONFIG_PATH
    return base.with_name("feeds-state.json")


def _load_state(config_path: Optional[Path]) -> Dict[str, Any]:
    path = _state_path(config_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"seen": {}}


def _save_state(config_path: Optional[Path], state: Dict[str, Any]) -> None:
    path = _state_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(xml_bytes: bytes) -> List[Dict[str, str]]:
    """解析 RSS 2.0 / Atom，返回 [{id, title, link, summary}]。"""
    root = ElementTree.fromstring(xml_bytes)
    items: List[Dict[str, str]] = []
    if root.tag.endswith("feed"):  # Atom
        for entry in root.findall("atom:entry", _ATOM):
            title = (entry.findtext("atom:title", default="", namespaces=_ATOM) or "").strip()
            link = ""
            for link_el in entry.findall("atom:link", _ATOM):
                if link_el.get("rel") in (None, "alternate"):
                    link = link_el.get("href", "")
                    break
            summary = entry.findtext("atom:summary", default="", namespaces=_ATOM) or ""
            entry_id = entry.findtext("atom:id", default="", namespaces=_ATOM) or link
            items.append({"id": entry_id, "title": title or link, "link": link, "summary": _strip_html(summary)})
        return items
    channel = root.find("channel") if root.tag.endswith("rss") else root
    if channel is None:
        return items
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        description = item.findtext("description") or ""
        items.append({
            "id": guid or link,
            "title": title or link,
            "link": link,
            "summary": _strip_html(description),
        })
    return items


def poll_feeds(*, vault_root: Path = VAULT_ROOT, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """轮询全部启用的 RSS 源，新文章自动入库（按 guid/link 去重）。"""
    config = load_feeds_config(config_path)
    state = _load_state(config_path)
    outcomes: List[Dict[str, Any]] = []
    for feed in config.get("feeds", []):
        if not feed.get("enabled", True):
            continue
        feed_id = str(feed.get("id") or feed.get("url"))
        seen = set(state["seen"].get(feed_id, []))
        try:
            entries = parse_feed(_fetch(str(feed["url"])))
        except Exception as exc:
            outcomes.append({"feed": feed_id, "status": "error", "error": str(exc)[:200]})
            continue
        added = 0
        for entry in entries:
            if entry["id"] in seen:
                continue
            ingest_article(
                title=entry["title"],
                content=entry["summary"] or entry["title"],
                author=str(feed.get("name") or "RSS"),
                url=entry["link"] or None,
                folder=str(feed.get("folder") or "60-References/Articles"),
                vault_root=vault_root,
            )
            seen.add(entry["id"])
            added += 1
        state["seen"][feed_id] = sorted(seen)[-2000:]
        outcomes.append({"feed": feed_id, "status": "ok", "added": added, "total_entries": len(entries)})
    _save_state(config_path, state)
    return {"outcomes": outcomes, "total_added": sum(o.get("added", 0) for o in outcomes)}


def _decode_header(value: Optional[str]) -> str:
    if not value:
        return ""
    parts: List[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts)


def _message_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                return _strip_html(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        return ""
    payload = msg.get_payload(decode=True) or b""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return _strip_html(text) if msg.get_content_type() == "text/html" else text


def poll_email_inbox(*, vault_root: Path = VAULT_ROOT, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """轮询 IMAP 收件箱未读邮件并入库（入库后标记已读，避免重复）。"""
    config = load_feeds_config(config_path)
    mail_cfg = config.get("email")
    if not mail_cfg:
        return {"status": "not_configured", "added": 0}
    password = os.environ.get(str(mail_cfg.get("password_env") or ""), "")
    if not password:
        raise RuntimeError(f"邮箱密码环境变量未设置：{mail_cfg.get('password_env')}")
    mailbox = str(mail_cfg.get("mailbox") or "INBOX")
    folder = str(mail_cfg.get("folder") or "60-References/Email")
    added = 0
    conn = imaplib.IMAP4_SSL(str(mail_cfg["imap_host"]), int(mail_cfg.get("imap_port") or 993))
    try:
        conn.login(str(mail_cfg["imap_user"]), password)
        conn.select(mailbox)
        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            return {"status": "search_failed", "added": 0}
        for num in data[0].split():
            status, fetched = conn.fetch(num, "(RFC822)")
            if status != "OK" or not fetched or not fetched[0]:
                continue
            raw = fetched[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(bytes(raw))
            subject = _decode_header(msg.get("Subject")) or "(无主题邮件)"
            sender = _decode_header(msg.get("From"))
            body = _message_body(msg).strip() or "(无正文)"
            ingest_article(
                title=subject,
                content=f"发件人：{sender}\n\n{body}",
                author=sender or "Email",
                folder=folder,
                vault_root=vault_root,
            )
            conn.store(num, "+FLAGS", "\\Seen")
            added += 1
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return {"status": "ok", "added": added}
