"""Embedding 层 + 本地向量索引（产品设计文档 Phase 2 架构层）。

红线（文档 §7）：向量索引与 Vault 同命——单文件 SQLite 放在
Vault/.nexusmind/vectors.db，随 Vault 拷贝即完整迁移；且 .nexusmind
已被云同步忽略名单排除，不会把向量传上云。

后端：
- local（默认）：内置离线向量器（哈希 TF 向量，中英混排分词），零依赖、
  完全离线，适合个人千级文档规模。
- ollama / openai：调用真实语义模型 API（NEXUSMIND_EMBED_MODEL），
  索引 meta 记录后端标识，后端变化时自动全量重建，避免向量空间混杂。
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx

from nexusmind.config import VAULT_ROOT
from nexusmind.core.duplicates import tokenize
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import extract_frontmatter

LOCAL_DIM = 512
_CHUNK_CHARS = 800
_CHUNK_OVERLAP = 120
_SKIP_PREFIXES = (".history/", ".nexusmind/")


def embed_provider() -> str:
    return (os.environ.get("NEXUSMIND_EMBED_PROVIDER", "local").strip().lower() or "local")


def embed_model() -> str:
    return os.environ.get("NEXUSMIND_EMBED_MODEL", "bge-m3").strip()


def backend_id() -> str:
    provider = embed_provider()
    return "local-hash-v1" if provider == "local" else f"{provider}:{embed_model()}"


# ---------------- 向量器 ----------------

def local_embed(text: str) -> List[float]:
    """离线哈希 TF 向量：token 哈希分桶 + 符号位，L2 归一化。"""
    tokens = tokenize(text)
    vec = [0.0] * LOCAL_DIM
    if not tokens:
        return vec
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    for token, count in counts.items():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "little") % LOCAL_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[bucket] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _remote_embed(texts: Sequence[str]) -> List[List[float]]:
    provider = embed_provider()
    model = embed_model()
    if provider == "ollama":
        base = os.environ.get("NEXUSMIND_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        out: List[List[float]] = []
        with httpx.Client(timeout=60) as client:
            for text in texts:
                resp = client.post(f"{base}/api/embeddings", json={"model": model, "prompt": text})
                resp.raise_for_status()
                out.append([float(x) for x in resp.json().get("embedding", [])])
        return out
    if provider == "openai":
        base = os.environ.get("NEXUSMIND_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        key = os.environ.get("NEXUSMIND_LLM_API_KEY", "")
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{base}/embeddings",
                json={"model": model, "input": list(texts)},
                headers={"Authorization": f"Bearer {key}"},
            )
            resp.raise_for_status()
            data = sorted(resp.json().get("data", []), key=lambda item: item.get("index", 0))
            return [[float(x) for x in item.get("embedding", [])] for item in data]
    raise RuntimeError(f"Unknown embed provider: {provider}")


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    if embed_provider() == "local":
        return [local_embed(text) for text in texts]
    return _remote_embed(texts)


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------- 索引存储 ----------------

def _db_path(vault_root: Path) -> Path:
    return vault_root / ".nexusmind" / "vectors.db"


def _connect(vault_root: Path) -> sqlite3.Connection:
    path = _db_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "path TEXT NOT NULL, chunk_idx INTEGER NOT NULL, title TEXT, "
        "doc_hash TEXT, snippet TEXT, vector BLOB, PRIMARY KEY (path, chunk_idx))"
    )
    return conn


def _pack(vec: Sequence[float]) -> bytes:
    return array.array("f", [float(x) for x in vec]).tobytes()


def _unpack(blob: bytes) -> List[float]:
    arr = array.array("f")
    arr.frombytes(blob)
    return list(arr)


def chunk_text(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + _CHUNK_CHARS)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


def _iter_notes(vault_root: Path):
    for md_file in sorted(vault_root.rglob("*.md"), key=lambda p: str(p).lower()):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith(_SKIP_PREFIXES):
            continue
        yield md_file, rel


def rebuild_vector_index(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """全量重建向量索引。"""
    conn = _connect(vault_root)
    try:
        conn.execute("DELETE FROM chunks")
        docs = 0
        chunk_count = 0
        for md_file, rel in _iter_notes(vault_root):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            chunks = chunk_text(text)
            if not chunks:
                continue
            fm = extract_frontmatter(text)
            title = str(fm.get("title") or md_file.stem)
            vectors = embed_texts([f"{title}\n{chunk}" for chunk in chunks])
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
                conn.execute(
                    "INSERT OR REPLACE INTO chunks (path, chunk_idx, title, doc_hash, snippet, vector)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (rel, idx, title, get_file_hash(text), chunk[:200], _pack(vec)),
                )
                chunk_count += 1
            docs += 1
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('backend', ?)",
            (backend_id(),),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('built_at', ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "rebuilt", "backend": backend_id(), "documents": docs, "chunks": chunk_count}


def ensure_index_fresh(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """增量维护：后端变化→全量重建；文档增删改→仅更新受影响文档。"""
    db = _db_path(vault_root)
    if not db.exists():
        return rebuild_vector_index(vault_root=vault_root)
    conn = _connect(vault_root)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='backend'").fetchone()
        if not row or row[0] != backend_id():
            conn.close()
            return rebuild_vector_index(vault_root=vault_root)
        existing = {
            path: doc_hash
            for path, doc_hash in conn.execute(
                "SELECT path, MAX(doc_hash) FROM chunks GROUP BY path"
            ).fetchall()
        }
    finally:
        conn.close()

    current: Dict[str, tuple[Path, str]] = {}
    for md_file, rel in _iter_notes(vault_root):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        current[rel] = (md_file, get_file_hash(text))

    changed = [rel for rel, (_, h) in current.items() if existing.get(rel) != h]
    removed = [rel for rel in existing if rel not in current]
    if not changed and not removed:
        return {"status": "fresh", "backend": backend_id(), "documents": len(current), "updated": 0}

    conn = _connect(vault_root)
    try:
        for rel in removed:
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        for rel in changed:
            md_file, _ = current[rel]
            text = md_file.read_text(encoding="utf-8")
            chunks = chunk_text(text)
            fm = extract_frontmatter(text)
            title = str(fm.get("title") or md_file.stem)
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
            vectors = embed_texts([f"{title}\n{chunk}" for chunk in chunks])
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
                conn.execute(
                    "INSERT OR REPLACE INTO chunks (path, chunk_idx, title, doc_hash, snippet, vector)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (rel, idx, title, get_file_hash(text), chunk[:200], _pack(vec)),
                )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('built_at', ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "updated",
        "backend": backend_id(),
        "documents": len(current),
        "updated": len(changed),
        "removed": len(removed),
    }


def index_status(*, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    db = _db_path(vault_root)
    if not db.exists():
        return {"exists": False, "backend": backend_id(), "documents": 0, "chunks": 0}
    conn = _connect(vault_root)
    try:
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        docs = conn.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    finally:
        conn.close()
    return {
        "exists": True,
        "backend": meta.get("backend"),
        "current_backend": backend_id(),
        "built_at": meta.get("built_at"),
        "documents": docs,
        "chunks": chunks,
    }


# ---------------- 检索 ----------------

def semantic_search(
    query: str,
    *,
    vault_root: Path = VAULT_ROOT,
    limit: int = 10,
    folder: Optional[str] = None,
) -> Dict[str, Any]:
    """语义检索：按 chunk 打分，聚合到文档取最高分 chunk 作为摘要。"""
    ensure_index_fresh(vault_root=vault_root)
    query_vec = embed_text(query)
    conn = _connect(vault_root)
    try:
        rows = conn.execute(
            "SELECT path, title, snippet, vector FROM chunks"
        ).fetchall()
    finally:
        conn.close()
    best: Dict[str, Dict[str, Any]] = {}
    for path, title, snippet, blob in rows:
        if folder and not path.startswith(folder.replace("\\", "/").strip("/") + "/"):
            continue
        score = cosine(query_vec, _unpack(blob))
        current = best.get(path)
        if current is None or score > current["score"]:
            best[path] = {
                "path": path,
                "title": title,
                "score": round(score, 4),
                "snippet": snippet,
            }
    results = sorted(best.values(), key=lambda item: -item["score"])[:limit]
    return {
        "query": query,
        "mode": "semantic",
        "backend": backend_id(),
        "total": len(results),
        "matches": results,
        "results": results,
    }


def hybrid_search(
    query: str,
    *,
    vault_root: Path = VAULT_ROOT,
    limit: int = 10,
    folder: Optional[str] = None,
    keyword_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> Dict[str, Any]:
    """混合检索：关键词分与语义分加权融合（各自先归一化到 0-1）。"""
    from nexusmind.core.search import search_notes

    semantic = semantic_search(query, vault_root=vault_root, limit=limit * 2, folder=folder)
    keyword = search_notes(query, folder=folder, limit=limit * 2, vault_root=vault_root)

    merged: Dict[str, Dict[str, Any]] = {}
    sem_scores = [m["score"] for m in semantic["matches"]] or [1.0]
    sem_max = max(sem_scores) or 1.0
    for item in semantic["matches"]:
        merged[item["path"]] = {
            "path": item["path"],
            "title": item["title"],
            "snippet": item["snippet"],
            "semantic_score": item["score"],
            "keyword_score": 0.0,
            "score": semantic_weight * (item["score"] / sem_max),
        }
    kw_scores = [m["score"] for m in keyword["matches"]] or [1.0]
    kw_max = max(kw_scores) or 1.0
    for item in keyword["matches"]:
        entry = merged.setdefault(item["path"], {
            "path": item["path"],
            "title": item["title"],
            "snippet": item["snippet"],
            "semantic_score": 0.0,
            "keyword_score": 0.0,
            "score": 0.0,
        })
        entry["keyword_score"] = item["score"]
        entry["score"] += keyword_weight * (item["score"] / kw_max)
        if item.get("snippet"):
            entry["snippet"] = item["snippet"]
    results = sorted(merged.values(), key=lambda item: -item["score"])
    for item in results:
        item["score"] = round(item["score"], 4)
        item["semantic_score"] = round(float(item["semantic_score"]), 4)
        item["keyword_score"] = round(float(item["keyword_score"]), 4)
    results = results[:limit]
    return {
        "query": query,
        "mode": "hybrid",
        "backend": backend_id(),
        "total": len(results),
        "matches": results,
        "results": results,
    }
