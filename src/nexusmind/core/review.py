import re
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from nexusmind.config import VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.indexer import find_broken_links, find_orphans
from nexusmind.core.notification import send_notification
from nexusmind.core.storage import extract_frontmatter


def _parse_week(week_str: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-W(\d{2})", week_str)
    if not match:
        raise ValueError("week must use ISO format YYYY-Www")
    year, week = int(match.group(1)), int(match.group(2))
    date.fromisocalendar(year, week, 1)
    return year, week


def _previous_week(week_str: str) -> str:
    year, week = _parse_week(week_str)
    monday = date.fromisocalendar(year, week, 1) - timedelta(days=7)
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _belongs_to_week(stem: str, year: int, week: int) -> bool:
    try:
        day = date.fromisoformat(stem)
    except ValueError:
        return False
    iso = day.isocalendar()
    return iso.year == year and iso.week == week


def _split_markdown_row(line: str) -> List[str]:
    """按 Markdown 表格列切分，但不把 [[target|alias]] 内的 | 当分隔符。"""
    text = line.strip()
    if not text.startswith("|"):
        return []
    cells: List[str] = []
    current: List[str] = []
    wiki_depth = 0
    i = 1
    while i < len(text):
        pair = text[i:i + 2]
        if pair == "[[":
            wiki_depth += 1
            current.append(pair)
            i += 2
            continue
        if pair == "]]" and wiki_depth:
            wiki_depth -= 1
            current.append(pair)
            i += 2
            continue
        ch = text[i]
        if ch == "|" and wiki_depth == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        cells.append("".join(current).strip())
    if cells and cells[-1] == "":
        cells.pop()
    return cells
def _table_rows(text: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in text.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 2:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _extract_task_rows(text: str, day: str) -> List[Dict[str, str]]:
    rows = _table_rows(text)
    if not rows:
        return []
    header_index = -1
    header: List[str] = []
    for idx, row in enumerate(rows):
        normalized = [c.strip().lower() for c in row]
        if any(x in normalized for x in ("关联任务", "时间段", "项目", "所属项目")):
            header_index = idx
            header = row
            break
    if header_index < 0:
        return []

    tasks: List[Dict[str, str]] = []
    for row in rows[header_index + 1:]:
        if len(row) != len(header):
            continue
        item = {header[i].strip(): row[i].strip() for i in range(len(header))}
        task = item.get("关联任务") or item.get("任务") or item.get("时间段") or ""
        project = item.get("所属项目") or item.get("项目") or ""
        hours = item.get("阶段投入 (h)") or item.get("投入工时") or ""
        output = item.get("交付产出与进展") or item.get("产出") or item.get("执行产出与记录") or ""
        link = item.get("关联笔记/卡片") or ""
        if not any((task, project, hours, output, link)):
            continue
        tasks.append({
            "date": day,
            "task": task,
            "project": project,
            "hours": hours,
            "output": output,
            "link": link,
        })
    return tasks


def _extract_checklist(text: str) -> tuple[List[str], List[str]]:
    completed: List[str] = []
    pending: List[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*[-*]?\s*\[([ xX])\]\s*(.+)", line)
        if not match:
            continue
        value = re.sub(r"\*\*", "", match.group(2)).strip()
        if match.group(1).lower() == "x":
            completed.append(value)
        else:
            pending.append(value)
    return completed, pending


def _numeric(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


COMMIT_TYPE_LABELS = {
    "feat": "功能交付",
    "fix": "问题修复",
    "perf": "性能优化",
    "refactor": "架构重构",
    "security": "安全加固",
    "ci": "CI / 发布工程",
    "build": "构建工程",
    "test": "测试质量",
    "docs": "文档沉淀",
    "chore": "工程维护",
    "release": "版本发布",
}


def _classify_commit(subject: str) -> Dict[str, str]:
    match = re.match(
        r"^(?P<type>[A-Za-z0-9_-]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<title>.+)$",
        subject.strip(),
    )
    if match:
        commit_type = match.group("type").lower()
        scope = (match.group("scope") or "").strip()
        title = match.group("title").strip()
    else:
        commit_type, scope, title = "other", "", subject.strip()
    if commit_type == "fix" and scope.lower() in {"security", "auth"}:
        category = "安全加固"
    elif commit_type == "chore" and scope.lower() == "release":
        category = "版本发布"
    else:
        category = COMMIT_TYPE_LABELS.get(commit_type, "其他变更")
    return {
        "type": commit_type,
        "scope": scope,
        "title": title,
        "category": category,
    }


def _extract_git_activity(text: str, author_scope: str = "current_user") -> Dict[str, Any]:
    if author_scope not in {"current_user", "all_users"}:
        raise ValueError("author_scope must be current_user or all_users")
    start = text.find("<!-- nexusmind:git-activity:start -->")
    end = text.find("<!-- nexusmind:git-activity:end -->")
    if start < 0 or end < 0 or end <= start:
        return {
            "commits": 0,
            "tags": 0,
            "repositories": set(),
            "dirty_repositories": 0,
            "commit_items": [],
            "release_tags": [],
            "repo_status": [],
        }

    block = text[start:end]
    repositories = set(re.findall(r"^###\s+(.+)$", block, flags=re.MULTILINE))
    dirty = len(re.findall(r"工作区：有未提交变更", block))
    commits = 0
    tags = 0
    commit_items: List[Dict[str, str]] = []
    release_tags: List[Dict[str, str]] = []
    repo_status: List[Dict[str, Any]] = []
    current_repo = ""
    current_user_email = ""

    for line in block.splitlines():
        heading = re.match(r"^###\s+(.+)$", line)
        if heading:
            current_repo = heading.group(1).strip()
            current_user_email = ""
            repo_status.append({
                "repository": current_repo,
                "dirty": False,
                "changed_count": 0,
                "current_user_email": "",
            })
            continue

        user = re.match(r"^- (?:采集用户|当前仓库用户)：.* <([^>]+)>$", line)
        if user and repo_status:
            email = user.group(1).strip().lower()
            current_user_email = "" if email == "未配置 user.email" else email
            repo_status[-1]["current_user_email"] = current_user_email
            continue

        status = re.match(r"^- 工作区：(有未提交变更|干净)（(\d+) 个文件）", line)
        if status and repo_status:
            repo_status[-1]["dirty"] = status.group(1) == "有未提交变更"
            repo_status[-1]["changed_count"] = int(status.group(2))
            continue

        release = re.match(
            r"^\s+- Release/Tag：(.+?)\s+—\s+target-author\s+<([^>]+)>$",
            line,
        )
        if release and current_repo:
            target_email = release.group(2).strip().lower()
            if author_scope == "all_users" or (current_user_email and target_email == current_user_email):
                tags += 1
                release_tags.append({
                    "repository": current_repo,
                    "tag": release.group(1).strip(),
                    "author_email": target_email,
                })
            continue

        commit = re.match(
            r"^\s+- ([0-9a-fA-F]{7,40})\s+(.+?)\s+—\s+(.+?)\s+<([^>]+)>$",
            line,
        )
        if commit and current_repo:
            author_email = commit.group(4).strip().lower()
            if author_scope == "current_user" and (
                not current_user_email or author_email != current_user_email
            ):
                continue
            subject = commit.group(2).strip()
            classified = _classify_commit(subject)
            commits += 1
            commit_items.append({
                "repository": current_repo,
                "hash": commit.group(1),
                "subject": subject,
                "author": commit.group(3).strip(),
                "author_email": author_email,
                **classified,
            })

    return {
        "commits": commits,
        "tags": tags,
        "repositories": repositories,
        "dirty_repositories": dirty,
        "commit_items": commit_items,
        "release_tags": release_tags,
        "repo_status": repo_status,
    }


def resolve_review_period(
    period_type: str = "week",
    period_value: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    today = date.today()
    pt = (period_type or "week").lower()
    if pt == "day":
        val = period_value or today.isoformat()
        start_d = date.fromisoformat(val)
        end_d = start_d
        prev_start_d = start_d - timedelta(days=1)
        prev_end_d = prev_start_d
        period_label = f"{val} 日复盘报告"
        file_name = f"{val}-Daily-Review.md"
    elif pt == "month":
        val = period_value or today.strftime("%Y-%m")
        match = re.fullmatch(r"(\d{4})-(\d{2})", val)
        if not match:
            raise ValueError("month must use format YYYY-MM")
        year, month = int(match.group(1)), int(match.group(2))
        start_d = date(year, month, 1)
        if month == 12:
            end_d = date(year, 12, 31)
            prev_start_d = date(year, 11, 1)
            prev_end_d = date(year, 11, 30)
        else:
            end_d = date(year, month + 1, 1) - timedelta(days=1)
            if month == 1:
                prev_start_d = date(year - 1, 12, 1)
                prev_end_d = date(year - 1, 12, 31)
            else:
                prev_start_d = date(year, month - 1, 1)
                prev_end_d = start_d - timedelta(days=1)
        period_label = f"{val} 月度复盘报告"
        file_name = f"{val}-Monthly-Review.md"
    elif pt == "quarter":
        if not period_value:
            q = (today.month - 1) // 3 + 1
            val = f"{today.year}-Q{q}"
        else:
            val = period_value.upper()
        match = re.fullmatch(r"(\d{4})-Q([1-4])", val)
        if not match:
            raise ValueError("quarter must use format YYYY-Qn (e.g. 2026-Q3)")
        year, q = int(match.group(1)), int(match.group(2))
        start_m = (q - 1) * 3 + 1
        end_m = q * 3
        start_d = date(year, start_m, 1)
        end_d = date(year, end_m + 1, 1) - timedelta(days=1) if end_m < 12 else date(year, 12, 31)
        if q == 1:
            prev_start_d = date(year - 1, 10, 1)
            prev_end_d = date(year - 1, 12, 31)
        else:
            prev_q = q - 1
            prev_sm = (prev_q - 1) * 3 + 1
            prev_em = prev_q * 3
            prev_start_d = date(year, prev_sm, 1)
            prev_end_d = date(year, prev_em + 1, 1) - timedelta(days=1)
        period_label = f"{val} 季度复盘报告"
        file_name = f"{val}-Quarterly-Review.md"
    elif pt == "year":
        val = period_value or str(today.year)
        match = re.fullmatch(r"\d{4}", val)
        if not match:
            raise ValueError("year must use format YYYY")
        year = int(val)
        start_d = date(year, 1, 1)
        end_d = date(year, 12, 31)
        prev_start_d = date(year - 1, 1, 1)
        prev_end_d = date(year - 1, 12, 31)
        period_label = f"{val} 年度复盘报告"
        file_name = f"{val}-Yearly-Review.md"
    elif pt == "custom":
        if period_value and ".." in period_value:
            s, e = period_value.split("..", 1)
            start_d = date.fromisoformat(s.strip())
            end_d = date.fromisoformat(e.strip())
        elif start_date and end_date:
            start_d = date.fromisoformat(start_date)
            end_d = date.fromisoformat(end_date)
        else:
            start_d = today - timedelta(days=7)
            end_d = today
        if start_d > end_d:
            start_d, end_d = end_d, start_d
        duration = (end_d - start_d).days + 1
        prev_end_d = start_d - timedelta(days=1)
        prev_start_d = prev_end_d - timedelta(days=duration - 1)
        val = f"{start_d}_{end_d}"
        period_label = f"{start_d} 至 {end_d} 自定义复盘报告"
        file_name = f"{start_d}_{end_d}-Custom-Review.md"
    else:  # week
        if not period_value:
            iso = today.isocalendar()
            val = f"{iso.year}-W{iso.week:02d}"
        else:
            val = period_value
        year, week = _parse_week(val)
        start_d = date.fromisocalendar(year, week, 1)
        end_d = date.fromisocalendar(year, week, 7)
        prev_str = _previous_week(val)
        py, pw = _parse_week(prev_str)
        prev_start_d = date.fromisocalendar(py, pw, 1)
        prev_end_d = date.fromisocalendar(py, pw, 7)
        period_label = f"{val} 工作周报"
        file_name = f"{val}-Weekly-Review.md"

    return {
        "period_type": pt,
        "period_value": val,
        "start_date": start_d,
        "end_date": end_d,
        "prev_start_date": prev_start_d,
        "prev_end_date": prev_end_d,
        "period_label": period_label,
        "file_name": file_name,
        "path": f"90-AI-Workspace/reviews/{file_name}",
    }


def _belongs_to_date_range(stem: str, start_d: date, end_d: date) -> bool:
    try:
        day = date.fromisoformat(stem)
    except ValueError:
        return False
    return start_d <= day <= end_d


def _period_data(
    start_d: date,
    end_d: date,
    vault_root: Path,
    author_scope: str = "current_user",
) -> Dict[str, Any]:
    daily_dir = vault_root / "30-Logs" / "Daily"
    daily_files = [
        p for p in daily_dir.glob("*.md")
        if _belongs_to_date_range(p.stem, start_d, end_d)
    ] if daily_dir.exists() else []

    total_hours = 0.0
    focus_scores: List[float] = []
    completed: List[str] = []
    pending: List[str] = []
    tasks: List[Dict[str, str]] = []
    outputs: List[str] = []
    projects: set[str] = set()
    git_commits = 0
    git_tags = 0
    git_repositories: set[str] = set()
    git_dirty_repositories = 0
    git_commit_items: List[Dict[str, str]] = []
    git_release_tags: List[Dict[str, str]] = []
    git_repo_status: Dict[str, Dict[str, Any]] = {}

    for daily in sorted(daily_files):
        text = daily.read_text(encoding="utf-8")
        fm = extract_frontmatter(text)
        hours = _numeric(fm.get("total_hours"))
        focus = _numeric(fm.get("focus_score"))
        if hours is not None:
            total_hours += hours
        if focus is not None:
            focus_scores.append(focus)
        done, todo = _extract_checklist(text)
        completed.extend(done)
        pending.extend(todo)
        daily_tasks = _extract_task_rows(text, daily.stem)
        tasks.extend(daily_tasks)
        git = _extract_git_activity(text, author_scope=author_scope)
        git_commits += git["commits"]
        git_tags += git["tags"]
        git_repositories.update(git["repositories"])
        git_dirty_repositories = max(git_dirty_repositories, git["dirty_repositories"])
        git_commit_items.extend(git.get("commit_items", []))
        git_release_tags.extend(git.get("release_tags", []))
        for repo in git.get("repo_status", []):
            git_repo_status[repo["repository"]] = repo
        for item in daily_tasks:
            if item["project"]:
                projects.add(item["project"])
            if item["output"]:
                outputs.append(item["output"])

    return {
        "daily_files": daily_files,
        "total_hours": total_hours,
        "focus_scores": focus_scores,
        "avg_focus": mean(focus_scores) if focus_scores else None,
        "completed": completed,
        "pending": pending,
        "tasks": tasks,
        "outputs": outputs,
        "projects": sorted(projects),
        "git_commits": git_commits,
        "git_tags": git_tags,
        "git_repositories": sorted(git_repositories),
        "git_dirty_repositories": git_dirty_repositories,
        "git_commit_items": git_commit_items,
        "git_release_tags": git_release_tags,
        "git_repo_status": list(git_repo_status.values()),
    }


def _week_data(
    week_str: str,
    vault_root: Path,
    author_scope: str = "current_user",
) -> Dict[str, Any]:
    year, week = _parse_week(week_str)
    start_d = date.fromisocalendar(year, week, 1)
    end_d = date.fromisocalendar(year, week, 7)
    return _period_data(start_d, end_d, vault_root, author_scope=author_scope)


def _compilation_stats_range(start_d: date, end_d: date, vault_root: Path) -> Dict[str, Any]:
    log_file = vault_root / "00-Meta" / "COMPILATION-LOG.md"
    stats: Dict[str, Any] = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "targets": [],
        "domains": {},
    }
    if not log_file.exists():
        return stats
    current_in_range = False
    targets: List[str] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        match = re.match(r"## \[(\d{4}-\d{2}-\d{2}) ", line)
        if match:
            d = date.fromisoformat(match.group(1))
            current_in_range = start_d <= d <= end_d
            if current_in_range:
                stats["total"] += 1
            continue
        if not current_in_range:
            continue
        if "操作类型" in line and "新建卡片" in line:
            stats["created"] += 1
        elif "操作类型" in line and "增量更新" in line:
            stats["updated"] += 1
        target = re.search(r"\*\*编译目标\*\*:\s*`\[\[([^\]]+)\]\]`", line)
        if target:
            path = target.group(1).strip()
            if path not in targets:
                targets.append(path)

    stats["targets"] = targets
    domains: Dict[str, int] = {}
    for path in targets:
        parts = path.split("/")
        domain = parts[1] if len(parts) > 2 and parts[0] == "40-Domain" else "Other"
        domains[domain] = domains.get(domain, 0) + 1
    stats["domains"] = domains
    return stats


def _compilation_stats(week_str: str, vault_root: Path) -> Dict[str, Any]:
    year, week = _parse_week(week_str)
    start_d = date.fromisocalendar(year, week, 1)
    end_d = date.fromisocalendar(year, week, 7)
    return _compilation_stats_range(start_d, end_d, vault_root)

def _group_commit_highlights(data: Dict[str, Any]) -> Dict[str, Any]:
    by_repo: Dict[str, List[Dict[str, str]]] = {}
    by_category: Dict[str, List[Dict[str, str]]] = {}
    for item in data.get("git_commit_items", []):
        by_repo.setdefault(item["repository"], []).append(item)
        by_category.setdefault(item["category"], []).append(item)

    category_order = [
        "版本发布",
        "功能交付",
        "安全加固",
        "问题修复",
        "架构重构",
        "性能优化",
        "CI / 发布工程",
        "构建工程",
        "测试质量",
        "文档沉淀",
        "工程维护",
        "其他变更",
    ]
    category_lines: List[str] = []
    for category in category_order:
        items = by_category.get(category, [])
        if not items:
            continue
        titles = []
        for item in items:
            title = item["title"]
            if title not in titles:
                titles.append(title)
        preview = "；".join(titles[:4])
        if len(titles) > 4:
            preview += f"；另有 {len(titles) - 4} 项"
        repos = sorted({item["repository"] for item in items})
        category_lines.append(
            f"- **{category}** · {len(items)} 个提交 · {', '.join(repos)}：{preview}"
        )

    repo_lines: List[str] = []
    for repo, items in sorted(by_repo.items(), key=lambda pair: (-len(pair[1]), pair[0].lower())):
        categories: Dict[str, int] = {}
        for item in items:
            categories[item["category"]] = categories.get(item["category"], 0) + 1
        category_text = "、".join(
            f"{name} {count}"
            for name, count in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        repo_lines.append(f"- **{repo}**：{len(items)} 个提交（{category_text}）")

    releases = data.get("git_release_tags", [])
    release_lines = [
        f"- **{item['repository']}** 发布 / 标记 `{item['tag']}`"
        for item in releases
    ]
    return {
        "by_repo": by_repo,
        "by_category": by_category,
        "category_lines": category_lines,
        "repo_lines": repo_lines,
        "release_lines": release_lines,
    }


def _synthesize_git_workstreams(data: Dict[str, Any]) -> Dict[str, Any]:
    """把 Git 提交聚合为仓库级工作主线，避免逐条展示日志。"""
    commits = data.get("git_commit_items", [])
    releases = data.get("git_release_tags", [])
    by_repo: Dict[str, List[Dict[str, str]]] = {}
    for item in commits:
        by_repo.setdefault(item["repository"], []).append(item)

    release_by_repo: Dict[str, List[str]] = {}
    for item in releases:
        release_by_repo.setdefault(item["repository"], []).append(item["tag"])

    workstreams: List[Dict[str, Any]] = []
    for repo, items in sorted(by_repo.items(), key=lambda pair: (-len(pair[1]), pair[0].lower())):
        categories: Dict[str, int] = {}
        scopes: Dict[str, int] = {}
        titles: List[str] = []
        for item in items:
            categories[item["category"]] = categories.get(item["category"], 0) + 1
            scope = item.get("scope", "").strip()
            if scope:
                scopes[scope] = scopes.get(scope, 0) + 1
            title = item["title"].strip().rstrip("。")
            if title and title not in titles:
                titles.append(title)

        dominant_categories = [
            name for name, _ in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))
        ][:3]
        dominant_scopes = [
            name for name, _ in sorted(scopes.items(), key=lambda pair: (-pair[1], pair[0]))
        ][:4]
        focus = "、".join(dominant_scopes) if dominant_scopes else "、".join(dominant_categories)
        workstreams.append({
            "repository": repo,
            "commit_count": len(items),
            "categories": dominant_categories,
            "scopes": dominant_scopes,
            "focus": focus,
            "highlights": titles[:3],
            "releases": release_by_repo.get(repo, []),
        })

    lines: List[str] = []
    for stream in workstreams:
        focus = f"围绕 **{stream['focus']}** " if stream["focus"] else ""
        if stream["highlights"]:
            delivery = "；".join(stream["highlights"])
            sentence = (
                f"- **{stream['repository']}**：{focus}形成 {delivery}"
                f"；共归并 {stream['commit_count']} 个 Git 变更"
            )
        else:
            sentence = f"- **{stream['repository']}**：{focus}共归并 {stream['commit_count']} 个 Git 变更"
        if stream["releases"]:
            sentence += "；完成 " + "、".join(f"`{tag}`" for tag in stream["releases"]) + " 发布/标记"
        lines.append(sentence + "。")

    return {"workstreams": workstreams, "lines": lines}


def _synthesize_outcomes(data: Dict[str, Any], compile_stats: Dict[str, Any]) -> List[str]:
    """把 Git、人工日志和知识编译结果合并成成果层摘要。"""
    outcomes: List[str] = []
    streams = _synthesize_git_workstreams(data)["workstreams"]

    category_totals: Dict[str, int] = {}
    for item in data.get("git_commit_items", []):
        category = item.get("category", "其他变更")
        category_totals[category] = category_totals.get(category, 0) + 1
    priority = ["版本发布", "功能交付", "安全加固", "问题修复", "架构重构", "性能优化", "CI / 发布工程", "构建工程", "测试质量", "文档沉淀"]
    active = [name for name in priority if category_totals.get(name)]
    if active:
        outcomes.append("工程成果主要集中在" + "、".join(f"**{name}**" for name in active[:5]) + "，而不是零散提交堆叠。")

    completed = list(dict.fromkeys(item.strip() for item in data.get("completed", []) if item.strip()))
    if completed:
        outcomes.append("人工日志确认完成：" + "；".join(completed[:4]) + ("。" if len(completed) <= 4 else f"；另有 {len(completed) - 4} 项。"))

    targets = compile_stats.get("targets", [])
    if targets:
        domains = compile_stats.get("domains", {})
        domain_text = "、".join(
            f"{domain} {count} 个"
            for domain, count in sorted(domains.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        outcomes.append(
            f"知识库将本周工作进一步沉淀为 {len(targets)} 个正式知识主题"
            + (f"（{domain_text}）" if domain_text else "")
            + "。"
        )

    releases = data.get("git_release_tags", [])
    if releases:
        release_text = "、".join(f"{item['repository']} `{item['tag']}`" for item in releases)
        outcomes.append(f"交付节点：{release_text}。")

    if not outcomes:
        outcomes.append("本周缺少足够的结构化成果数据，暂不做超出证据范围的推断。")
    return outcomes


def _synthesize_daily_context(data: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    projects = sorted({item.get("project", "").strip() for item in data.get("tasks", []) if item.get("project", "").strip()})
    outputs = list(dict.fromkeys(item.get("output", "").strip() for item in data.get("tasks", []) if item.get("output", "").strip()))
    task_names = list(dict.fromkeys(item.get("task", "").strip() for item in data.get("tasks", []) if item.get("task", "").strip()))
    links = list(dict.fromkeys(item.get("link", "").strip() for item in data.get("tasks", []) if item.get("link", "").strip()))

    if projects:
        lines.append("主要关联项目：" + "、".join(projects) + "。")
    if outputs:
        lines.append("人工日志记录的交付产出：" + "；".join(outputs[:5]) + ("。" if len(outputs) <= 5 else f"；另有 {len(outputs) - 5} 项。"))
    elif task_names:
        lines.append("人工日志记录的主要事项：" + "；".join(task_names[:5]) + ("。" if len(task_names) <= 5 else f"；另有 {len(task_names) - 5} 项。"))
    task_links = [item for item in task_names if "[[" in item and "]]" in item]
    if task_links:
        lines.append("关联任务：" + "、".join(task_links[:5]) + ("。" if len(task_links) <= 5 else f"；另有 {len(task_links) - 5} 项。"))
    if links:
        lines.append("关联任务 / 知识：" + "、".join(links[:5]) + ("。" if len(links) <= 5 else f"；另有 {len(links) - 5} 项。"))
    if data.get("total_hours"):
        lines.append(f"结构化日志记录投入 {data['total_hours']:.1f}h，覆盖 {len(data.get('daily_files', []))} 天。")
    if not lines:
        lines.append("本周没有足够的结构化人工日志用于补充工作上下文。")
    return lines


def _next_week_focus(data: Dict[str, Any], governance: Dict[str, int]) -> List[str]:
    focus: List[str] = []
    pending = list(dict.fromkeys(item.strip() for item in data.get("pending", []) if item.strip()))
    if pending:
        focus.append("优先收口未完成事项：" + "；".join(pending[:3]) + "。")
    if data.get("git_dirty_repositories"):
        focus.append(f"处理 {data['git_dirty_repositories']} 个仍有未提交变更的仓库，避免工作跨周失去可追溯性。")
    if governance.get("broken"):
        focus.append(f"治理 {governance['broken']} 个未解析链接，提升知识引用完整性。")
    if governance.get("orphans"):
        focus.append(f"处理 {governance['orphans']} 个知识孤岛，补充入口、反链或归档判断。")
    if not focus:
        focus.append("延续本周主线，并优先把已完成工程成果沉淀为可复用知识与明确交付节点。")
    return focus


def _executive_summary(
    data: Dict[str, Any],
    compile_stats: Dict[str, Any],
) -> str:
    commits = data.get("git_commit_items", [])
    releases = data.get("git_release_tags", [])
    active_repos = sorted({item["repository"] for item in commits})
    if not active_repos:
        active_repos = data.get("git_repositories", [])

    phrases: List[str] = []
    if active_repos:
        focus = "、".join(active_repos[:3])
        if len(active_repos) > 3:
            focus += f" 等 {len(active_repos)} 个仓库"
        phrases.append(f"本周工作主要覆盖 {focus}")
    if releases:
        release_text = "、".join(
            f"{item['repository']} {item['tag']}" for item in releases[:3]
        )
        phrases.append(f"完成 {release_text} 的版本发布/标记")
    grouped = _group_commit_highlights(data)
    major_categories = [
        name
        for name in ("功能交付", "安全加固", "问题修复", "CI / 发布工程", "架构重构")
        if grouped["by_category"].get(name)
    ]
    if major_categories:
        phrases.append("主要变更集中在" + "、".join(major_categories[:4]))
    targets = compile_stats.get("targets", [])
    if targets:
        phrases.append(f"同步沉淀 {len(targets)} 个正式知识主题")
    if not phrases:
        return "本周暂无足够的结构化工作数据用于提炼。"
    return "；".join(phrases) + "。"


def _knowledge_highlights(compile_stats: Dict[str, Any]) -> str:
    targets = compile_stats.get("targets", [])
    if not targets:
        return "- 本周没有可识别的正式知识编译目标。"
    domains = compile_stats.get("domains", {})
    lines = []
    if domains:
        domain_text = "、".join(
            f"{domain} {count} 个"
            for domain, count in sorted(domains.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        lines.append(f"- 知识主题分布：{domain_text}。")
    display_targets = targets[:10]
    lines.extend(f"- [[{path}|{Path(path).stem}]]" for path in display_targets)
    if len(targets) > len(display_targets):
        lines.append(f"- 另有 {len(targets) - len(display_targets)} 个知识主题已完成编译。")
    return "\n".join(lines)


def _git_commit_details(data: Dict[str, Any]) -> str:
    items = data.get("git_commit_items", [])
    if not items:
        return "- 本周没有采集到 Git Commit 明细。"
    by_repo: Dict[str, List[Dict[str, str]]] = {}
    for item in items:
        by_repo.setdefault(item["repository"], []).append(item)
    lines: List[str] = []
    for repo, commits in sorted(by_repo.items()):
        lines.append(f"### {repo}")
        for item in commits:
            scope = f"({item['scope']})" if item.get("scope") else ""
            lines.append(
                f"- `{item['hash']}` **{item['type']}{scope}** · {item['title']}"
            )
    return "\n".join(lines)

def _comparison(current: Dict[str, Any], previous: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    cur_days = len(current["daily_files"])
    prev_days = len(previous["daily_files"])
    if prev_days == 0 and cur_days == 0:
        return ["- 当前周与上周均无 Daily Log，无法形成趋势对比。"]

    lines.append(f"- 日志覆盖：本周 {cur_days} 天；上周 {prev_days} 天。")
    lines.append(f"- 总投入：本周 {current['total_hours']:.1f}h；上周 {previous['total_hours']:.1f}h。")
    if current["avg_focus"] is not None or previous["avg_focus"] is not None:
        cur = f"{current['avg_focus']:.1f}" if current["avg_focus"] is not None else "无数据"
        prev = f"{previous['avg_focus']:.1f}" if previous["avg_focus"] is not None else "无数据"
        lines.append(f"- 平均专注度：本周 {cur}；上周 {prev}。")
    lines.append(f"- 已完成清单项：本周 {len(current['completed'])} 项；上周 {len(previous['completed'])} 项。")
    lines.append(f"- Git Commit：本周 {current['git_commits']} 个；上周 {previous['git_commits']} 个。")
    return lines


def _attention_items(data: Dict[str, Any], broken_count: int, orphan_count: int) -> List[str]:
    items: List[str] = []
    if len(data["daily_files"]) < 3:
        items.append("本周 Daily Log 少于 3 天，趋势判断样本不足；优先补齐日常记录。")
    if data["pending"]:
        items.append(f"仍有 {len(data['pending'])} 个未完成清单项，建议确认是否顺延到下一周。")
    if data["git_dirty_repositories"]:
        items.append(f"当前有 {data['git_dirty_repositories']} 个仓库存在未提交变更，建议确认是否需要提交、拆分或清理。")
    if broken_count:
        items.append(f"知识库当前有 {broken_count} 个未解析链接，建议先处理真实死链并降低误报。")
    if orphan_count:
        items.append(f"知识库当前有 {orphan_count} 个孤岛条目，建议确认入口或治理规则。")
    if not items:
        items.append("本周未检测到明显治理风险；下周继续保持日志记录和知识编译节奏。")
    return items


def _bullet_lines(values: List[str], empty_text: str) -> str:
    return "\n".join(f"- {v}" for v in values) if values else f"- {empty_text}"
def generate_review(
    period_type: str = "week",
    period_value: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
    author_scope: str = "current_user",
    push_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """从真实日志与 Git 跨数据源生成多维度结构化复盘报告。"""
    if author_scope not in {"current_user", "all_users"}:
        raise ValueError("author_scope must be current_user or all_users")

    resolved = resolve_review_period(
        period_type=period_type,
        period_value=period_value,
        start_date=start_date,
        end_date=end_date,
    )

    data = _period_data(resolved["start_date"], resolved["end_date"], vault_root, author_scope=author_scope)
    previous = _period_data(resolved["prev_start_date"], resolved["prev_end_date"], vault_root, author_scope=author_scope)
    compile_stats = _compilation_stats_range(resolved["start_date"], resolved["end_date"], vault_root)
    governance = {
        "broken": find_broken_links(vault_root=vault_root)["total_broken"],
        "orphans": find_orphans(vault_root=vault_root)["total_orphans"],
    }

    comparison = "\n".join(_comparison(data, previous))
    attention = _bullet_lines(
        _attention_items(data, governance["broken"], governance["orphans"]),
        "暂无需特别关注事项",
    )
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    avg_focus = f"{data['avg_focus']:.1f}/10" if data["avg_focus"] is not None else "无数据"
    daily_context = _bullet_lines(
        _synthesize_daily_context(data),
        "该时间范围内暂无结构化人工日志。",
    )

    git_summary = _group_commit_highlights(data)
    active_git_repositories = sorted(git_summary["by_repo"].keys())
    executive_summary = _executive_summary(data, compile_stats)
    workstreams = _synthesize_git_workstreams(data)
    workstream_text = "\n".join(workstreams["lines"]) or "- 该时间范围内没有足够 Git 数据形成明确工作主线。"
    outcome_text = _bullet_lines(
        _synthesize_outcomes(data, compile_stats),
        "该时间范围内没有足够数据提炼关键成果。",
    )
    release_highlights = "\n".join(git_summary["release_lines"]) or "- 该时间范围内没有采集到版本发布 / Tag。"
    knowledge_highlights = _knowledge_highlights(compile_stats)
    next_focus = _bullet_lines(
        _next_week_focus(data, governance),
        "暂无明确的后续重点。",
    )
    status_icon = "✅" if not data["pending"] and not data["git_dirty_repositories"] else "🟡"
    scope_label = "当前仓库用户" if author_scope == "current_user" else "所有用户"

    content = f"""---
title: "{resolved['period_label']}"
generated_at: "{timestamp}"
period_type: "{resolved['period_type']}"
period_value: "{resolved['period_value']}"
start_date: "{resolved['start_date'].isoformat()}"
end_date: "{resolved['end_date'].isoformat()}"
author_scope: "{author_scope}"
total_hours: {data['total_hours']:.1f}
avg_focus: "{avg_focus}"
completed_items: {len(data['completed'])}
pending_items: {len(data['pending'])}
compiled_items: {compile_stats['total']}
knowledge_topics: {len(compile_stats.get('targets', []))}
git_commits: {data['git_commits']}
git_tags: {data['git_tags']}
broken_links: {governance['broken']}
orphans: {governance['orphans']}
tags:
  - "#review"
  - "#{resolved['period_type']}-review"
  - "#work-report"
---

# {resolved['period_label']}

> **Git 统计口径：{scope_label}**
>
> **本阶段摘要**
> {executive_summary}

## 📊 阶段速览

| 指标 | 当前周期 |
| --- | ---: |
| 日志覆盖 | {len(data['daily_files'])} 天 |
| Git Commit | {data['git_commits']} 个 |
| 活跃仓库 | {len(active_git_repositories)} 个 |
| 已监控仓库 | {len(data['git_repositories'])} 个 |
| Release / Tag | {data['git_tags']} 个 |
| 正式知识主题 | {len(compile_stats.get('targets', []))} 个 |
| 总投入 | {data['total_hours']:.1f}h |
| 平均专注度 | {avg_focus} |
| 完成 / 待办 | {len(data['completed'])} / {len(data['pending'])} |
| 阶段状态 | {status_icon} |

## 🎯 工作主线

{workstream_text}

> 工作主线不是按提交时间排序，而是将同一仓库、同一 scope 和相近工程类型的变更归并后形成。

## ✅ 关键成果与交付

{outcome_text}

### 发布节点

{release_highlights}

> Git Commit、Release/Tag、Daily Log 与知识编译审计共同作为成果证据；报告只保留提炼后的结论，不在正文逐条复述 Git Log。

## 🧠 知识沉淀

- 编译审计记录：**{compile_stats['total']}** 条
- 新建知识卡片：**{compile_stats['created']}** 条
- 增量更新卡片：**{compile_stats['updated']}** 条
- 独立知识主题：**{len(compile_stats.get('targets', []))}** 个

{knowledge_highlights}

## 📝 人工日志补充

{daily_context}

### 未完成 / 顺延

{_bullet_lines(data['pending'], "日志中没有结构化未完成项。")}

## 📈 与上一周期对比

{comparison}

## ⚠️ 风险与遗留

{attention}

## 🧭 后续重点

{next_focus}

### 知识库健康度

- 未解析链接：**{governance['broken']}**
- 知识孤岛：**{governance['orphans']}**
- 有未提交变更的仓库：**{data['git_dirty_repositories']}**

## 数据口径

- Git 自动采集保存所有用户的提交记录；本复盘报告 Git 统计口径为：**{scope_label}**。
- 原始 Git Commit 仅作为内部证据源参与聚合，不在报告正文逐条展示。
- 工作主线会按仓库、scope、工程类别、Release/Tag 与人工日志进行去重和聚合，再形成成果级摘要。
- Daily Log、知识编译审计和知识库治理状态会与 Git 数据交叉整合，避免把提交数量等同于工作价值。
- 报告只陈述可验证事实；不会根据提交信息推断收入、业务效果或未记录的主观结论。
"""

    review_path = resolved["path"]
    review_file = vault_root / review_path
    old_version = None
    if review_file.exists():
        from nexusmind.core.occ import get_file_hash
        old_version = get_file_hash(review_file.read_text(encoding="utf-8"))

    res = patch_note(
        review_path,
        content,
        if_match=old_version or "NEW",
        actor="reviewer",
        vault_root=vault_root,
    )
    notification_result = None
    if push_channels:
        title = f"{resolved['period_label']}"
        notification_result = send_notification(
            title=title,
            content=f"【NexusMind {resolved['period_label']}】\n- 总投入工时: {data['total_hours']:.1f}h\n- Git Commit: {data['git_commits']} 个\n- 完成/待办: {len(data['completed'])} / {len(data['pending'])}\n- 编译知识: {compile_stats['total']} 条\n\n查看完整复盘报告:\n{review_path}",
            channel_ids=push_channels,
            event_type="review",
            metadata={"period_type": resolved["period_type"], "period_value": resolved["period_value"], "path": review_path},
        )

    return {
        "status": "review_generated",
        "period_type": resolved["period_type"],
        "period_value": resolved["period_value"],
        "week": resolved["period_value"] if resolved["period_type"] == "week" else None,
        "author_scope": author_scope,
        "author_scope_label": scope_label,
        "path": review_path,
        "daily_logs_count": len(data["daily_files"]),
        "logged_tasks_count": len(data["tasks"]),
        "total_hours": data["total_hours"],
        "avg_focus": data["avg_focus"],
        "completed_items": len(data["completed"]),
        "pending_items": len(data["pending"]),
        "compiled_items": compile_stats["total"],
        "git_commits": data["git_commits"],
        "git_tags": data["git_tags"],
        "git_repositories": data["git_repositories"],
        "git_active_repositories": active_git_repositories,
        "knowledge_topics": len(compile_stats.get("targets", [])),
        "broken_links": governance["broken"],
        "orphans": governance["orphans"],
        "version": res["version"],
        "notification_result": notification_result,
    }


def generate_weekly_review(
    week_str: Optional[str] = None,
    vault_root: Path = VAULT_ROOT,
    author_scope: str = "current_user",
    push_channels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """从真实周数据生成结构化复盘（兼容旧接口）。"""
    return generate_review(
        period_type="week",
        period_value=week_str,
        vault_root=vault_root,
        author_scope=author_scope,
        push_channels=push_channels,
    )
