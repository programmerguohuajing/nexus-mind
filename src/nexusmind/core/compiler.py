import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from nexusmind.config import VAULT_ROOT
from nexusmind.core.notification import send_notification
from nexusmind.core.occ import get_file_hash, verify_occ
from nexusmind.core.permissions import check_write_permission
from nexusmind.core.storage import extract_frontmatter, extract_links, resolve_vault_path


def patch_note(
    rel_path: str,
    content: str,
    if_match: Optional[str] = None,
    *,
    actor: str = "agent",
    privileged: bool = False,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    """统一写入入口：权限矩阵 + OCC + 原子替换。"""
    check_write_permission(rel_path, actor=actor, privileged=privileged)
    file_path = resolve_vault_path(rel_path, vault_root=vault_root)
    exists = file_path.exists()
    current_version = None
    if exists:
        current_version = get_file_hash(file_path.read_text(encoding="utf-8"))
    verify_occ(current_version, if_match, exists=exists)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(file_path)
    return {
        "status": "success",
        "path": rel_path,
        "version": get_file_hash(content),
        "created": not exists,
    }


def build_source_provenance_tag(rel_path: str, start_line: int = 1, end_line: int = 20) -> str:
    norm = rel_path.replace("\\", "/")
    return f"[[{norm}#L{start_line}-L{end_line}]]"


def _validate_raw_sources(raw_sources: List[str], vault_root: Path) -> List[str]:
    if not raw_sources:
        raise ValueError("raw_sources must not be empty")
    normalized: List[str] = []
    for source in raw_sources:
        rel = source.replace("\\", "/").strip("/")
        if not rel.startswith("60-References/"):
            raise ValueError(f"Raw source must be under 60-References: {source}")
        path = resolve_vault_path(rel, vault_root=vault_root)
        if not path.is_file():
            raise FileNotFoundError(f"Raw source not found: {rel}")
        normalized.append(rel)
    return sorted(set(normalized))


def _with_sources_frontmatter(content: str, raw_sources: List[str]) -> str:
    """确保编译产物带 sources 与 last_compiled_at，不破坏已有 frontmatter。"""
    fm = extract_frontmatter(content)
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            body = parts[2].lstrip("\n")
    existing = fm.get("sources", [])
    if isinstance(existing, str):
        existing = [existing]
    provenance = [build_source_provenance_tag(s, 1, 30) for s in raw_sources]
    fm["sources"] = list(dict.fromkeys([*existing, *provenance]))
    fm["last_compiled_at"] = datetime.now().strftime("%Y-%m-%d")
    fm.setdefault("compiled_by", "NexusMind Compiler")
    header = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n\n{body.rstrip()}\n"


def _append_audit_log(
    *,
    raw_sources: List[str],
    target_card_path: str,
    version: str,
    created: bool,
    conflict_detected: bool,
    conflict_summary: Optional[str],
    link_count: int,
    vault_root: Path,
) -> None:
    log_file = vault_root / "00-Meta" / "COMPILATION-LOG.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sources = ", ".join(f"`{s}`" for s in raw_sources)
    conflict = conflict_summary or ("检测到事实冲突" if conflict_detected else "无显式事实冲突")
    entry = (
        f"\n## [{timestamp}] LLM Wiki 增量编译记录\n"
        f"- **编译目标**: `[[{target_card_path}]]`\n"
        f"- **原始素材 (Raw)**: {sources}\n"
        f"- **操作类型**: {'新建卡片' if created else '增量更新'}\n"
        f"- **事实演进/冲突判定**: {conflict}\n"
        f"- **关联双向链接数**: {link_count}\n"
        f"- **版本哈希**: `{version}`\n"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.write_text("# 📜 知识库编译与审计流水账\n", encoding="utf-8")
    with log_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(entry)


def compile_wiki_card(
    raw_sources: List[str],
    target_card_path: str,
    content: str,
    conflict_detected: bool = False,
    conflict_summary: Optional[str] = None,
    if_match: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
    push_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """编译正式 Wiki 卡片，并强制来源声明、OCC 与审计日志。"""
    raw_sources = _validate_raw_sources(raw_sources, vault_root)
    target = target_card_path.replace("\\", "/").strip("/")
    if not target.startswith("40-Domain/") or not target.endswith(".md"):
        raise ValueError("Compiled cards must be markdown files under 40-Domain/")
    if conflict_detected and "### ⚠️ 结论与事实演进对比" not in content:
        summary = conflict_summary or "检测到新旧事实冲突，需人工补齐差异细节"
        content = (
            content.rstrip()
            + "\n\n### ⚠️ 结论与事实演进对比\n"
            + f"- **冲突说明**: {summary}\n"
            + "- **处理原则**: 保留既有结论，不做静默覆盖。\n"
            + "- **状态**: [推测待验证] 等待人工或上层 Agent 补齐新旧事实与适用范围。\n"
        )
    compiled_content = _with_sources_frontmatter(content, raw_sources)
    patch_res = patch_note(
        target,
        compiled_content,
        if_match=if_match,
        actor="compiler",
        privileged=True,
        vault_root=vault_root,
    )
    _append_audit_log(
        raw_sources=raw_sources,
        target_card_path=target,
        version=patch_res["version"],
        created=patch_res["created"],
        conflict_detected=conflict_detected,
        conflict_summary=conflict_summary,
        link_count=len(extract_links(compiled_content)),
        vault_root=vault_root,
    )

    notification_result = None
    if push_channels:
        card_name = Path(target).stem
        op_type = "新建知识卡片" if patch_res["created"] else "增量更新知识卡片"
        notification_result = send_notification(
            title=f"提炼知识: {card_name}",
            content=f"【NexusMind LLM Wiki 知识编译】\n- 操作类型: {op_type}\n- 目标卡片: {target}\n- 原始素材: {', '.join(raw_sources)}\n- 版本: {patch_res['version']}",
            channel_ids=push_channels,
            event_type="knowledge_compiled",
            metadata={"card_path": target, "sources": raw_sources},
        )

    return {
        "status": "compiled_successfully",
        "card_path": target,
        "version": patch_res["version"],
        "created": patch_res["created"],
        "audit_logged": True,
        "sources": raw_sources,
        "notification_result": notification_result,
    }


def scan_uncompiled_sources(vault_root: Path = VAULT_ROOT) -> List[Path]:
    """扫描 Raw 层中尚未出现在编译审计日志里的 Markdown。"""
    ref_dir = vault_root / "60-References"
    if not ref_dir.exists():
        return []
    log_file = vault_root / "00-Meta" / "COMPILATION-LOG.md"
    logged = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    pending: List[Path] = []
    for md_file in ref_dir.rglob("*.md"):
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        if f"`{rel}`" not in logged:
            pending.append(md_file)
    return sorted(pending, key=lambda p: str(p).lower())


def ensure_conflict_section(original_content: str, old_facts: str, new_facts: str, reason: str) -> str:
    """显式保留新旧事实，不静默覆盖历史结论。"""
    heading = "### ⚠️ 结论与事实演进对比"
    item = (
        f"- **历史结论**: {old_facts}\n"
        f"- **现行演进**: {new_facts}\n"
        f"- **演进根因**: {reason}\n"
    )
    if heading not in original_content:
        return original_content.rstrip() + f"\n\n{heading}\n{item}"
    stamp = datetime.now().strftime("%Y-%m-%d")
    return original_content.rstrip() + f"\n- **{stamp} 新演进**: {new_facts}（根因: {reason}）\n"


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return content.strip()


def _source_excerpt(content: str, limit: int = 1800) -> str:
    """仅抽取原文，不做模型脑补；作为无 LLM 配置时的安全编译降级。"""
    body = _strip_frontmatter(content)
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    excerpt = "\n".join(lines[:40])
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rstrip() + "…"
    return excerpt or "[原材料正文为空，待人工核验]"


def _infer_domain(title: str, content: str) -> str:
    text = f"{title} {content[:800]}".lower()
    if any(k in text for k in ("agent", "智能体", "mcp")):
        return "Agent"
    if any(k in text for k in ("architecture", "架构", "occ", "并发", "llm wiki")):
        return "Architecture"
    return "Knowledge"


def _new_card_content(title: str, rel_path: str, raw_content: str) -> str:
    provenance = build_source_provenance_tag(rel_path, 1, 30)
    excerpt = _source_excerpt(raw_content)
    return f"""---
title: "{title}"
aliases:
  - "{title}"
tags:
  - "#domain"
  - "#atomic-card"
sources:
  - "{provenance}"
---

# 🧠 {title}

## 核心材料摘录

> 以下内容直接摘录/整理自原始素材，不补充素材外事实。来源：{provenance}

{excerpt}

## 待编译结论

- [推测待验证] 当前为安全降级编译结果；如接入 LLM/人工审核，应在不丢失溯源的前提下提炼原子结论。

## 🔗 链接与导航
- 主索引：[[40-Domain/00-Index/Master-Index|Master Index]]
- 原始素材：[[{rel_path}]]
"""
def _merge_existing_card(existing: str, rel_path: str, raw_content: str) -> str:
    provenance = build_source_provenance_tag(rel_path, 1, 30)
    excerpt = _source_excerpt(raw_content, limit=1200)
    block = (
        f"\n## 增量编译 · {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"- 新来源：{provenance}\n\n"
        f"{excerpt}\n"
    )
    return existing.rstrip() + block


def auto_compile_pending_sources(
    vault_root: Path = VAULT_ROOT,
    push_channels: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """批量增量编译待处理 Raw，并在完成后重建分层索引。"""
    pending = scan_uncompiled_sources(vault_root=vault_root)
    results: List[Dict[str, Any]] = []
    for md_file in pending:
        rel = str(md_file.relative_to(vault_root)).replace("\\", "/")
        raw = md_file.read_text(encoding="utf-8")
        fm = extract_frontmatter(raw)
        title = str(fm.get("title") or md_file.stem)
        domain = _infer_domain(title, raw)
        target = f"40-Domain/{domain}/{md_file.stem}.md"
        target_path = resolve_vault_path(target, vault_root=vault_root)
        if target_path.exists():
            existing = target_path.read_text(encoding="utf-8")
            content = _merge_existing_card(existing, rel, raw)
            if_match = get_file_hash(existing)
        else:
            content = _new_card_content(title, rel, raw)
            if_match = "NEW"
        result = compile_wiki_card(
            [rel],
            target,
            content,
            if_match=if_match,
            vault_root=vault_root,
            push_channels=push_channels,
        )
        results.append(result)

    if results:
        from nexusmind.core.indexer import rebuild_all_indices
        rebuild_all_indices(vault_root=vault_root)
    return results
