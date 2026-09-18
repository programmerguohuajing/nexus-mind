from pathlib import Path

from nexusmind.core.review import generate_weekly_review


def _write_daily(root: Path, day: str, hours: float, focus: int, checked: bool, alias_link: bool = False):
    daily = root / "30-Logs" / "Daily"
    daily.mkdir(parents=True, exist_ok=True)
    link = (
        "[[20-Projects/Sample/v1/Core/Task-001|Task-001]]"
        if alias_link else "Task-001"
    )
    content = f"""---
date: {day}
total_hours: {hours}
focus_score: {focus}
---

# {day}

- [{'x' if checked else ' '}] 完成核心功能
- [ ] 修复遗留问题

| 关联任务 | 所属项目 | 阶段投入 (h) | 交付产出与进展 |
| :--- | :--- | :--- | :--- |
| {link} | NexusMind | {hours} | 完成复盘引擎 |
"""
    (daily / f"{day}.md").write_text(content, encoding="utf-8")


def _seed(root: Path):
    for folder in (
        "00-Meta",
        "20-Projects/Sample",
        "40-Domain/00-Index",
        "60-References/Articles",
        "90-AI-Workspace/reviews",
    ):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "00-Meta/COMPILATION-LOG.md").write_text(
        "# Log\n\n"
        "## [2026-09-17 10:00:00] LLM Wiki 增量编译记录\n"
        "- **操作类型**: 新建卡片\n",
        encoding="utf-8",
    )
def test_review_engine_parses_alias_link_and_dynamic_metrics(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-17", 2.5, 9, True, alias_link=True)
    _write_daily(tmp_path, "2026-09-18", 1.5, 7, True)

    result = generate_weekly_review("2026-W38", vault_root=tmp_path)
    assert result["daily_logs_count"] == 2
    assert result["logged_tasks_count"] == 2
    assert result["total_hours"] == 4.0
    assert result["avg_focus"] == 8
    assert result["completed_items"] == 2
    assert result["pending_items"] == 2
    assert result["compiled_items"] == 1

    text = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "[[20-Projects/Sample/v1/Core/Task-001|Task-001]]" in text
    assert "| 总投入 | 4.0h |" in text
    assert "| 平均专注度 | 8.0/10 |" in text
    assert "完成复盘引擎" in text
    assert "新建知识卡片：**1** 条" in text


def test_review_engine_compares_previous_week(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-10", 1.0, 6, True)
    _write_daily(tmp_path, "2026-09-17", 3.0, 8, True)

    result = generate_weekly_review("2026-W38", vault_root=tmp_path)
    text = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "上周 1 天" in text
    assert "上周 1.0h" in text
    assert "上周 6.0" in text


def test_review_includes_auto_git_activity(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-17", 2.0, 8, True)
    daily = tmp_path / "30-Logs/Daily/2026-09-17.md"
    text = daily.read_text(encoding="utf-8")
    text += """
<!-- nexusmind:git-activity:start -->
## Git 工作活动（自动采集）
### web-eys-sdk
- 今日提交：4 个；Merge/PR 线索：1 个；Tag：1 个
- 工作区：有未提交变更（2 个文件）
### nexus-mind
- 今日提交：2 个；Merge/PR 线索：0 个；Tag：0 个
- 工作区：干净（0 个文件）
<!-- nexusmind:git-activity:end -->
"""
    daily.write_text(text, encoding="utf-8")

    result = generate_weekly_review("2026-W38", vault_root=tmp_path)
    assert result["git_commits"] == 6
    assert result["git_tags"] == 1
    assert result["git_repositories"] == ["nexus-mind", "web-eys-sdk"]
    review = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "| Git Commit | 6 个 |" in review
    assert "| Release / Tag | 1 个 |" in review


def test_review_extracts_commit_themes_and_release(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-18", 1.0, 8, True)
    daily = tmp_path / "30-Logs/Daily/2026-09-18.md"
    text = daily.read_text(encoding="utf-8")
    text += """
<!-- nexusmind:git-activity:start -->
## Git 工作活动（自动采集）
### web-eys-sdk
- 今日提交：4 个；Merge/PR 线索：0 个；Tag：1 个
- 工作区：干净（0 个文件）
  - aaaaaaa feat(sdk-rn): 新增 React Native 会话回放
  - bbbbbbb fix(security): 加固多租户隔离
  - ccccccc ci(workflow): 新增 SDK 发布自动化
  - ddddddd chore(release): 发布 0.8.1
  - Release/Tag：v0.8.1
<!-- nexusmind:git-activity:end -->
"""
    daily.write_text(text, encoding="utf-8")

    result = generate_weekly_review("2026-W38", vault_root=tmp_path)
    assert result["git_active_repositories"] == ["web-eys-sdk"]
    review = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "**功能交付**" in review
    assert "**安全加固**" in review
    assert "**CI / 发布工程**" in review
    assert "**版本发布**" in review
    assert "v0.8.1" in review
    assert "新增 React Native 会话回放" in review
