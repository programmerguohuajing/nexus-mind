"""Daily Log 自动叙事（产品设计文档 P2-4）：把 Git 活动写成人话日报。

事实来自 Daily Log 的自动采集区块（与周复盘同一解析器，保证口径一致）；
叙事优先 LLM 生成，无 LLM 时用结构化模板降级。日报不列 commit hash。
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.llm import LlmUnavailable, generate, llm_status
from nexusmind.core.notification import send_notification
from nexusmind.core.review import _classify_commit, _extract_git_activity


def daily_log_path(day: date, vault_root: Path) -> Path:
    return vault_root / "30-Logs" / "Daily" / f"{day.isoformat()}.md"


def collect_day_facts(day: date, *, vault_root: Path = VAULT_ROOT, author_scope: str = "all_users") -> Dict[str, Any]:
    """读取某天 Daily Log 并提炼结构化事实（提交数/仓库/类型分布/主题）。"""
    path = daily_log_path(day, vault_root)
    if not path.is_file():
        return {"date": day.isoformat(), "exists": False, "commits": 0, "repositories": [], "types": {}, "subjects": [], "tags": []}
    text = path.read_text(encoding="utf-8")
    activity = _extract_git_activity(text, author_scope=author_scope)
    type_counter: Counter = Counter()
    subjects: List[str] = []
    for item in activity.get("commit_items", []):
        classified = _classify_commit(item.get("subject", ""))
        type_counter[classified.get("type", "other")] += 1
        subjects.append(item.get("subject", ""))
    return {
        "date": day.isoformat(),
        "exists": True,
        "commits": activity.get("commits", 0),
        "repositories": sorted(activity.get("repositories", [])),
        "types": dict(type_counter),
        "subjects": subjects[:20],
        "tags": [tag.get("tag") for tag in activity.get("release_tags", [])],
        "dirty_repositories": activity.get("dirty_repositories", 0),
    }


_TYPE_LABELS = {
    "feat": "新功能", "fix": "问题修复", "docs": "文档", "refactor": "重构",
    "perf": "性能优化", "test": "测试", "build": "构建", "ci": "CI/发布",
    "chore": "杂务", "style": "样式", "revert": "回滚", "other": "其他",
}


def _template_narrative(facts: Dict[str, Any]) -> str:
    if not facts["exists"]:
        return f"{facts['date']} 暂无 Daily Log 记录（当天可能未同步 Git 活动）。"
    if facts["commits"] == 0:
        return f"{facts['date']} 没有采集到提交记录。"
    repos = "、".join(facts["repositories"]) or "未知仓库"
    type_parts = [
        f"{_TYPE_LABELS.get(kind, kind)} {count} 次"
        for kind, count in sorted(facts["types"].items(), key=lambda kv: -kv[1])
    ]
    lines = [
        f"今日在 {len(facts['repositories'])} 个仓库（{repos}）共提交 {facts['commits']} 次，"
        f"构成：{'、'.join(type_parts)}。",
    ]
    if facts["subjects"]:
        highlights = "；".join(facts["subjects"][:5])
        lines.append(f"主要工作：{highlights}。")
    if facts["tags"]:
        lines.append(f"发布节点：{', '.join(facts['tags'])}。")
    if facts["dirty_repositories"]:
        lines.append(f"另有 {facts['dirty_repositories']} 个仓库存在未提交变更，注意收尾。")
    return "\n".join(lines)


def _llm_narrative(facts: Dict[str, Any]) -> Optional[str]:
    if not llm_status()["available"] or not facts["exists"] or facts["commits"] == 0:
        return None
    prompt = (
        "请根据下面的 Git 工作数据写一段 200 字以内的中文日报叙事："
        "按工作主线归纳，不要逐条罗列提交，不要出现 commit hash，不要编造数据之外的事实。\n\n"
        f"日期：{facts['date']}\n仓库：{', '.join(facts['repositories'])}\n"
        f"提交总数：{facts['commits']}\n类型分布：{facts['types']}\n"
        f"提交主题：{'；'.join(facts['subjects'])}\n发布标签：{', '.join(facts['tags'])}"
    )
    try:
        return generate(prompt, temperature=0.3).strip() or None
    except LlmUnavailable:
        return None


def generate_daily_narrative(
    day: Optional[str] = None,
    *,
    vault_root: Path = VAULT_ROOT,
    author_scope: str = "all_users",
) -> Dict[str, Any]:
    """生成某天（默认今天）的日报叙事。"""
    target = date.fromisoformat(day) if day else datetime.now().date()
    facts = collect_day_facts(target, vault_root=vault_root, author_scope=author_scope)
    narrative = _llm_narrative(facts)
    mode = "llm" if narrative else "template"
    if not narrative:
        narrative = _template_narrative(facts)
    return {"date": target.isoformat(), "narrative": narrative, "mode": mode, "facts": facts}


def push_daily_narrative(
    day: Optional[str] = None,
    *,
    vault_root: Path = VAULT_ROOT,
    channels: Optional[List[str]] = None,
    author_scope: str = "all_users",
) -> Dict[str, Any]:
    """生成日报并推送到通知渠道（复用现有 notification 模块）。"""
    result = generate_daily_narrative(day, vault_root=vault_root, author_scope=author_scope)
    notification = send_notification(
        title=f"每日工作叙事 · {result['date']}",
        content=result["narrative"],
        channel_ids=channels,
        event_type="daily_narrative",
        metadata={"date": result["date"], "mode": result["mode"]},
    )
    return {**result, "notification_result": notification}
