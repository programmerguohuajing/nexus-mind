"""Ask My Vault（产品设计文档 P2-2）：基于自己知识库的问答。

铁律（文档 §9 风险项）：引用必须真实存在于检索结果中；检索不到就明确
说"知识库里没有"，绝不编造。无 LLM 时降级为抽取式回答（原文片段+出处）。
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.embeddings import hybrid_search, semantic_search
from nexusmind.core.llm import LlmUnavailable, generate, llm_status
from nexusmind.core.search import search_notes

_MIN_SEMANTIC_SCORE = 0.18
_PATH_IN_TEXT_RE = re.compile(r"[\w\-./\u4e00-\u9fff]+\.md")


def _retrieve(question: str, vault_root: Path, limit: int) -> List[Dict[str, Any]]:
    """相关性门槛用原始语义余弦/关键词命中判断（混合分已归一化，不能判有无）。"""
    semantic = semantic_search(question, vault_root=vault_root, limit=limit * 2)
    relevant = {
        item["path"]
        for item in semantic["matches"]
        if float(item.get("score", 0)) >= _MIN_SEMANTIC_SCORE
    }
    keyword = search_notes(question, limit=limit * 2, vault_root=vault_root)
    relevant.update(item["path"] for item in keyword["matches"])
    if not relevant:
        return []
    hybrid = hybrid_search(question, vault_root=vault_root, limit=limit * 2)
    matches = [item for item in hybrid["matches"] if item["path"] in relevant]
    if not matches:  # 混合结果被截断时退回语义结果本身
        matches = [
            {"path": item["path"], "title": item["title"], "score": item["score"], "snippet": item["snippet"]}
            for item in semantic["matches"]
            if item["path"] in relevant
        ]
    return matches[:limit]


def _extractive_answer(question: str, matches: List[Dict[str, Any]]) -> str:
    lines = [f"根据知识库中与「{question}」相关的内容，整理如下（抽取式摘要，未经模型改写）：", ""]
    for item in matches:
        snippet = " ".join(str(item.get("snippet") or "").split())[:280]
        lines.append(f"- **{item['title']}**（[[{item['path']}]]）：{snippet}")
    lines.append("")
    lines.append("如需更完整的结论，可打开来源笔记查看全文，或为系统配置 LLM 后获得综合回答。")
    return "\n".join(lines)


def _llm_answer(question: str, matches: List[Dict[str, Any]]) -> str:
    context_blocks = []
    for idx, item in enumerate(matches, start=1):
        snippet = " ".join(str(item.get("snippet") or "").split())[:600]
        context_blocks.append(f"[来源{idx}] 路径：{item['path']} 标题：{item['title']}\n{snippet}")
    prompt = (
        "你是 NexusMind 知识库问答助手。只能依据下面提供的知识库片段回答问题，"
        "不允许引入片段之外的事实；片段不足以回答时明确说明信息不足。\n"
        "回答用中文，结构清晰，并在每条结论后标注来源路径（格式：[[路径]]）。\n\n"
        f"问题：{question}\n\n知识库片段：\n" + "\n\n".join(context_blocks)
    )
    return generate(prompt, temperature=0.2)


def ask_vault(
    question: str,
    *,
    vault_root: Path = VAULT_ROOT,
    limit: int = 6,
    save: bool = False,
) -> Dict[str, Any]:
    """问答主入口：混合检索 → （LLM 综合 | 抽取式降级）→ 引用校验。"""
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")
    matches = _retrieve(question, vault_root, limit)
    if not matches:
        return {
            "question": question,
            "answer": "知识库里没有找到与这个问题相关的内容。",
            "citations": [],
            "mode": "no_match",
            "saved_path": None,
        }

    mode = "extractive"
    status = llm_status()
    if status["available"]:
        try:
            answer = _llm_answer(question, matches)
            mode = "llm"
        except LlmUnavailable:
            answer = _extractive_answer(question, matches)
    else:
        answer = _extractive_answer(question, matches)

    # 引用校验：LLM 模式下只保留答案中真实出现、且属于检索集合的路径；
    # 抽取式模式引用即检索集合本身。
    retrieved_paths = [item["path"] for item in matches]
    if mode == "llm":
        cited = []
        for raw in _PATH_IN_TEXT_RE.findall(answer):
            normalized = raw.replace("\\", "/").strip("/")
            for path in retrieved_paths:
                if normalized == path or path.endswith(normalized):
                    if path not in cited:
                        cited.append(path)
        citation_paths = cited or retrieved_paths[:3]
    else:
        citation_paths = retrieved_paths
    score_by_path = {item["path"]: item["score"] for item in matches}
    snippet_by_path = {item["path"]: item.get("snippet", "") for item in matches}
    citations = [
        {"path": path, "score": score_by_path.get(path), "snippet": snippet_by_path.get(path, "")}
        for path in citation_paths
    ]

    saved_path = None
    if save:
        now = datetime.now()
        rel = f"20-QA/{now.strftime('%Y-%m-%d-%H%M%S')}.md"
        body = (
            "---\n"
            f'title: "问答：{question[:40].replace(chr(34), chr(39))}"\n'
            "tags:\n  - \"#qa\"\n"
            f"created: {now.strftime('%Y-%m-%d')}\n"
            "---\n\n"
            f"# 问：{question}\n\n{answer}\n\n## 来源\n\n"
            + "\n".join(f"- [[{c['path']}]]" for c in citations)
            + "\n"
        )
        patch_note(rel, body, if_match="NEW", actor="ask", privileged=True, vault_root=vault_root)
        saved_path = rel

    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "mode": mode,
        "saved_path": saved_path,
    }
