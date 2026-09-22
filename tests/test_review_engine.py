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
- 采集用户：Tester <tester@example.com>
- 今日提交：4 个；Merge/PR 线索：1 个；Tag：1 个
- 工作区：有未提交变更（2 个文件）
  - aaaaaaa feat: one — Tester <tester@example.com>
  - bbbbbbb fix: two — Tester <tester@example.com>
  - ccccccc ci: three — Tester <tester@example.com>
  - ddddddd docs: four — Tester <tester@example.com>
  - Release/Tag：v0.1.0 — target-author <tester@example.com>
### nexus-mind
- 采集用户：Tester <tester@example.com>
- 今日提交：2 个；Merge/PR 线索：0 个；Tag：0 个
- 工作区：干净（0 个文件）
  - eeeeeee feat: five — Tester <tester@example.com>
  - fffffff fix: six — Tester <tester@example.com>
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
- 采集用户：Tester <tester@example.com>
- 今日提交：5 个；Merge/PR 线索：0 个；Tag：2 个
- 工作区：干净（0 个文件）
  - aaaaaaa feat(sdk-rn): 新增 React Native 会话回放 — Tester <tester@example.com>
  - bbbbbbb fix(security): 加固多租户隔离 — Tester <tester@example.com>
  - ccccccc ci(workflow): 新增 SDK 发布自动化 — Tester <tester@example.com>
  - ddddddd chore(release): 发布 0.8.1 — Tester <tester@example.com>
  - eeeeeee feat: 其他成员功能 — Other User <other@example.com>
  - Release/Tag：v0.8.1 — target-author <tester@example.com>
  - Release/Tag：v-other — target-author <other@example.com>
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
    assert "## 🔎 Git Commit 明细" not in review
    assert "`aaaaaaa`" not in review
    assert "`bbbbbbb`" not in review
    assert "围绕 **" in review
    assert "sdk-rn" in review
    assert "security" in review
    assert "workflow" in review


def test_review_filters_other_authors_from_collected_git_log(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-18", 1.0, 8, True)
    daily = tmp_path / "30-Logs/Daily/2026-09-18.md"
    text = daily.read_text(encoding="utf-8")
    text += """
<!-- nexusmind:git-activity:start -->
## Git 工作活动（自动采集）
### team-repo
- 采集用户：Tester <tester@example.com>
- 今日提交：3 个；Merge/PR 线索：0 个；Tag：2 个
- 工作区：干净（0 个文件）
  - aaaaaaa feat: my feature — Tester <tester@example.com>
  - bbbbbbb fix: my fix — Tester <tester@example.com>
  - ccccccc feat: teammate feature — Teammate <teammate@example.com>
  - Release/Tag：v-mine — target-author <tester@example.com>
  - Release/Tag：v-team — target-author <teammate@example.com>
<!-- nexusmind:git-activity:end -->
"""
    daily.write_text(text, encoding="utf-8")

    result = generate_weekly_review("2026-W38", vault_root=tmp_path)
    assert result["git_commits"] == 2
    assert result["git_tags"] == 1
    assert result["git_active_repositories"] == ["team-repo"]
    review = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "my feature" in review
    assert "my fix" in review
    assert "teammate feature" not in review
    assert "`aaaaaaa`" not in review
    assert "`bbbbbbb`" not in review
    assert "v-mine" in review
    assert "v-team" not in review


def test_review_can_include_all_users_from_collected_git_log(tmp_path):
    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-18", 1.0, 8, True)
    daily = tmp_path / "30-Logs/Daily/2026-09-18.md"
    text = daily.read_text(encoding="utf-8")
    text += """
<!-- nexusmind:git-activity:start -->
## Git 工作活动（自动采集）
### team-repo
- 当前仓库用户：Tester <tester@example.com>
- 今日全部用户提交：3 个；Merge/PR 线索：0 个；Tag：2 个
- 工作区：干净（0 个文件）
  - aaaaaaa feat: my feature — Tester <tester@example.com>
  - bbbbbbb fix: my fix — Tester <tester@example.com>
  - ccccccc feat: teammate feature — Teammate <teammate@example.com>
  - Release/Tag：v-mine — target-author <tester@example.com>
  - Release/Tag：v-team — target-author <teammate@example.com>
<!-- nexusmind:git-activity:end -->
"""
    daily.write_text(text, encoding="utf-8")

    result = generate_weekly_review(
        "2026-W38",
        vault_root=tmp_path,
        author_scope="all_users",
    )
    assert result["author_scope"] == "all_users"
    assert result["git_commits"] == 3
    assert result["git_tags"] == 2
    review = (tmp_path / result["path"]).read_text(encoding="utf-8")
    assert "Git 统计口径：所有用户" in review
    assert "teammate feature" in review
    assert "v-team" in review
    assert "`aaaaaaa`" not in review
    assert "`ccccccc`" not in review
    assert "原始 Git Commit 仅作为内部证据源参与聚合" in review


def test_resolve_review_period_granularity():
    from datetime import date
    from nexusmind.core.review import resolve_review_period

    # Day
    day_res = resolve_review_period(period_type="day", period_value="2026-09-17")
    assert day_res["period_type"] == "day"
    assert day_res["period_value"] == "2026-09-17"
    assert day_res["start_date"] == date(2026, 9, 17)
    assert day_res["end_date"] == date(2026, 9, 17)
    assert day_res["path"] == "90-AI-Workspace/reviews/2026-09-17-Daily-Review.md"

    # Month
    month_res = resolve_review_period(period_type="month", period_value="2026-09")
    assert month_res["period_type"] == "month"
    assert month_res["start_date"] == date(2026, 9, 1)
    assert month_res["end_date"] == date(2026, 9, 30)
    assert month_res["path"] == "90-AI-Workspace/reviews/2026-09-Monthly-Review.md"

    # Quarter
    q_res = resolve_review_period(period_type="quarter", period_value="2026-Q3")
    assert q_res["period_type"] == "quarter"
    assert q_res["start_date"] == date(2026, 7, 1)
    assert q_res["end_date"] == date(2026, 9, 30)
    assert q_res["path"] == "90-AI-Workspace/reviews/2026-Q3-Quarterly-Review.md"

    # Year
    yr_res = resolve_review_period(period_type="year", period_value="2026")
    assert yr_res["period_type"] == "year"
    assert yr_res["start_date"] == date(2026, 1, 1)
    assert yr_res["end_date"] == date(2026, 12, 31)
    assert yr_res["path"] == "90-AI-Workspace/reviews/2026-Yearly-Review.md"

    # Custom range with start_date / end_date
    c_res = resolve_review_period(period_type="custom", start_date="2026-09-01", end_date="2026-09-15")
    assert c_res["period_type"] == "custom"
    assert c_res["start_date"] == date(2026, 9, 1)
    assert c_res["end_date"] == date(2026, 9, 15)
    assert c_res["path"] == "90-AI-Workspace/reviews/2026-09-01_2026-09-15-Custom-Review.md"


def test_generate_review_multi_granularity(tmp_path):
    from nexusmind.core.review import generate_review

    _seed(tmp_path)
    _write_daily(tmp_path, "2026-09-17", 2.0, 8, True)
    _write_daily(tmp_path, "2026-09-18", 3.0, 9, True)

    # Monthly review
    m_result = generate_review(period_type="month", period_value="2026-09", vault_root=tmp_path)
    assert m_result["status"] == "review_generated"
    assert m_result["period_type"] == "month"
    assert m_result["period_value"] == "2026-09"
    assert m_result["daily_logs_count"] == 2
    assert m_result["total_hours"] == 5.0
    assert (tmp_path / m_result["path"]).exists()
    text = (tmp_path / m_result["path"]).read_text(encoding="utf-8")
    assert "2026-09 月度复盘报告" in text

    # Daily review
    d_result = generate_review(period_type="day", period_value="2026-09-17", vault_root=tmp_path)
    assert d_result["status"] == "review_generated"
    assert d_result["period_type"] == "day"
    assert d_result["daily_logs_count"] == 1
    assert d_result["total_hours"] == 2.0
    assert (tmp_path / d_result["path"]).exists()

