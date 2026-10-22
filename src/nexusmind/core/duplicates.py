"""重复内容检测与合并（SimHash + Jaccard），状态存于 Vault/.nexusmind/governance.json。

向量语义升级路径见产品设计文档 P1-6：Phase 2 可用 embedding 相似度替换/增强本模块。
治理状态文件不是 .md，不会污染搜索/图谱/索引。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.occ import get_file_hash
from nexusmind.core.storage import extract_frontmatter, resolve_vault_path

_STATE_REL = ".nexusmind/governance.json"
_SKIP_PREFIXES = ("00-Meta/", ".history/", ".nexusmind/")
_MIN_BODY_CHARS = 100
_WORD_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    """中英混排分词：英文单词 + 中文单字/双字 bigram。"""
    lowered = text.lower()
    tokens: List[str] = _WORD_RE.findall(lowered)
    cjk_chars = _CJK_RE.findall(lowered)
    tokens.extend(cjk_chars)
    tokens.extend("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:]))
    return tokens


def simhash64(tokens: List[str]) -> int:
    if not tokens:
        return 0
    weights = [0] * 64
    for token in tokens:
        digest = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:16], 16)
        for bit in range(64):
            weights[bit] += 1 if (digest >> bit) & 1 else -1
    fingerprint = 0
    for bit in range(64):
        if weights[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_state(vault_root: Path) -> Dict[str, Any]:
    path = vault_root / _STATE_REL
    if not path.exists():
        return {"ignored_pairs": [], "merges": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("ignored_pairs", [])
            data.setdefault("merges", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"ignored_pairs": [], "merges": []}


def _save_state(vault_root: Path, state: Dict[str, Any]) -> None:
    path = vault_root / _STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _pair_key(a: str, b: str) -> List[str]:
    return sorted([a, b])


def find_duplicate_pairs(
    *,
    vault_root: Path = VAULT_ROOT,
    threshold: float = 0.88,
    limit: int = 100,
) -> Dict[str, Any]:
    """扫描全库，返回超过相似度阈值的疑似重复对（已排除用户忽略的配对）。"""
    state = _load_state(vault_root)
    ignored = {tuple(pair) for pair in state.get("ignored_pairs", []) if len(pair) == 2}

    docs: List[Tuple[str, str, int, Set[str]]] = []
    for md_file in sorted(vault_root.rglob("*.md"), key=lambda p: str(p).lower()):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if rel.startswith(_SKIP_PREFIXES):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = extract_frontmatter(text)
        if fm.get("merged_into"):
            continue
        body = text.strip()
        if len(body) < _MIN_BODY_CHARS:
            continue
        tokens = tokenize(body)
        if not tokens:
            continue
        docs.append((rel, str(fm.get("title") or md_file.stem), simhash64(tokens), set(tokens)))

    pairs: List[Dict[str, Any]] = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            rel_a, title_a, hash_a, set_a = docs[i]
            rel_b, title_b, hash_b, set_b = docs[j]
            if tuple(_pair_key(rel_a, rel_b)) in ignored:
                continue
            simhash_sim = 1.0 - _hamming(hash_a, hash_b) / 64.0
            if simhash_sim < threshold - 0.1:
                continue
            score = round(0.7 * simhash_sim + 0.3 * _jaccard(set_a, set_b), 4)
            if score >= threshold:
                pairs.append({
                    "path_a": rel_a,
                    "title_a": title_a,
                    "path_b": rel_b,
                    "title_b": title_b,
                    "score": score,
                    "simhash_similarity": round(simhash_sim, 4),
                })
    pairs.sort(key=lambda item: -item["score"])
    return {"total": len(pairs), "pairs": pairs[:limit], "threshold": threshold}


def ignore_pair(path_a: str, path_b: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """把一对疑似重复标记为已忽略，之后不再提示。"""
    state = _load_state(vault_root)
    key = _pair_key(path_a.replace("\\", "/"), path_b.replace("\\", "/"))
    existing = {tuple(pair) for pair in state.get("ignored_pairs", []) if len(pair) == 2}
    if tuple(key) not in existing:
        state["ignored_pairs"].append(key)
        _save_state(vault_root, state)
    return {"status": "ignored", "pair": key}


def merge_notes(primary: str, secondary: str, *, vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """合并：次文档改写为重定向 stub（保留路径与反链），合并记录写入治理状态。"""
    primary_rel = primary.replace("\\", "/").strip("/")
    secondary_rel = secondary.replace("\\", "/").strip("/")
    if primary_rel == secondary_rel:
        raise ValueError("primary and secondary must be different notes")
    primary_path = resolve_vault_path(primary_rel, vault_root=vault_root)
    secondary_path = resolve_vault_path(secondary_rel, vault_root=vault_root)
    if not primary_path.is_file():
        raise FileNotFoundError(f"Primary note not found: {primary_rel}")
    if not secondary_path.is_file():
        raise FileNotFoundError(f"Secondary note not found: {secondary_rel}")

    secondary_text = secondary_path.read_text(encoding="utf-8")
    fm = extract_frontmatter(secondary_text)
    title = str(fm.get("title") or secondary_path.stem)
    merged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stub = (
        "---\n"
        f'title: "{title.replace(chr(34), chr(39))}"\n'
        f"merged_into: \"[[{primary_rel}]]\"\n"
        f'merged_at: "{merged_at}"\n'
        "tags:\n"
        '  - "#merged"\n'
        "---\n\n"
        f"# {title}\n\n"
        f"> 本笔记已于 {merged_at} 合并至 [[{primary_rel}]]，正文以主文档为准。\n"
    )
    result = patch_note(
        secondary_rel,
        stub,
        if_match=get_file_hash(secondary_text),
        actor="governance-merge",
        privileged=True,
        vault_root=vault_root,
    )
    state = _load_state(vault_root)
    record = {
        "primary": primary_rel,
        "secondary": secondary_rel,
        "merged_at": merged_at,
        "secondary_version_before": get_file_hash(secondary_text),
    }
    state.setdefault("merges", []).append(record)
    _save_state(vault_root, state)
    return {"status": "merged", **record, "stub_version": result["version"]}
