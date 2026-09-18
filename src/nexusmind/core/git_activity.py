from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from nexusmind.config import PROJECT_ROOT, VAULT_ROOT
from nexusmind.core.compiler import patch_note
from nexusmind.core.occ import get_file_hash

START_MARKER = "<!-- nexusmind:git-activity:start -->"
END_MARKER = "<!-- nexusmind:git-activity:end -->"
WORKFLOW_CONFIG_PATH = PROJECT_ROOT / "workflow-config.json"


def load_workflow_config() -> Dict[str, Any]:
    if not WORKFLOW_CONFIG_PATH.exists():
        return {"targets": []}
    try:
        data = json.loads(WORKFLOW_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"targets": []}
    targets = data.get("targets", [])
    return {"targets": targets if isinstance(targets, list) else []}


def save_workflow_config(targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in targets:
        kind = str(item.get("type") or "").strip().lower()
        raw_path = str(item.get("path") or "").strip()
        if kind not in {"directory", "repository"}:
            raise ValueError("type must be directory or repository")
        if not raw_path:
            raise ValueError("path must not be empty")
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"path not found: {path}")
        if kind == "repository" and not (path / ".git").exists():
            raise ValueError(f"not a Git repository: {path}")
        key = (kind, str(path).lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "type": kind,
            "path": str(path),
            "enabled": bool(item.get("enabled", True)),
        })
    payload = {"targets": normalized}
    WORKFLOW_CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def workflow_targets() -> List[Dict[str, Any]]:
    return [
        item for item in load_workflow_config()["targets"]
        if item.get("enabled", True)
    ]


def discover_repositories(
    roots: Optional[Iterable[Path]] = None,
    targets: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Path]:
    found: Dict[str, Path] = {}
    if roots is not None:
        effective_targets = [
            {"type": "directory", "path": str(Path(root).resolve()), "enabled": True}
            for root in roots
        ]
    else:
        effective_targets = list(targets) if targets is not None else workflow_targets()

    for item in effective_targets:
        if not item.get("enabled", True):
            continue
        kind = str(item.get("type") or "").lower()
        path = Path(str(item.get("path") or "")).expanduser().resolve()
        if kind == "repository":
            if (path / ".git").exists():
                found[str(path).lower()] = path
            continue
        if kind != "directory" or not path.exists():
            continue
        if (path / ".git").exists():
            found[str(path).lower()] = path
        try:
            candidates = [child for child in path.iterdir() if child.is_dir()]
        except OSError:
            continue
        for candidate in candidates:
            if (candidate / ".git").exists():
                found[str(candidate).lower()] = candidate
    return sorted(found.values(), key=lambda p: p.name.lower())


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _commit_rows(repo: Path, day: date) -> List[Dict[str, Any]]:
    start = datetime.combine(day, time.min).isoformat()
    end = datetime.combine(day + timedelta(days=1), time.min).isoformat()
    output = _git(
        repo, "log", f"--since={start}", f"--until={end}", "--date=iso-strict",
        "--pretty=format:%H%x1f%h%x1f%ad%x1f%an%x1f%s",
    )
    commits: List[Dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split("\x1f", 4)
        if len(parts) != 5:
            continue
        full, short, authored_at, author, subject = parts
        commits.append({
            "hash": full,
            "short": short,
            "authored_at": authored_at,
            "author": author,
            "subject": subject,
            "is_merge": subject.lower().startswith("merge ") or "pull request #" in subject.lower(),
        })
    return commits


def _tag_rows(repo: Path, day: date) -> List[Dict[str, str]]:
    output = _git(repo, "for-each-ref", "--format=%(refname:short)%09%(creatordate:iso-strict)", "refs/tags")
    items: List[Dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        name, created = parts
        try:
            created_day = datetime.fromisoformat(created.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if created_day == day:
            items.append({"name": name, "created_at": created})
    return items


def _working_tree(repo: Path) -> Dict[str, Any]:
    output = _git(repo, "status", "--porcelain=v1")
    rows = [line for line in output.splitlines() if line.strip()]
    return {
        "dirty": bool(rows),
        "changed_count": len(rows),
        "changed_files": [(line[3:].strip() if len(line) > 3 else line) for line in rows][:30],
    }


def collect_repository(repo: Path, day: Optional[date] = None) -> Dict[str, Any]:
    day = day or date.today()
    commits = _commit_rows(repo, day)
    tags = _tag_rows(repo, day)
    tree = _working_tree(repo)
    branch = _git(repo, "branch", "--show-current") or _git(repo, "rev-parse", "--short", "HEAD")
    remote = _git(repo, "config", "--get", "remote.origin.url")
    head = _git(repo, "log", "-1", "--pretty=format:%H%x1f%h%x1f%ad%x1f%s", "--date=iso-strict")
    hp = head.split("\x1f", 3) if head else []
    return {
        "name": repo.name,
        "path": str(repo),
        "branch": branch,
        "remote": remote,
        "commits": commits,
        "commit_count": len(commits),
        "merge_count": sum(1 for item in commits if item["is_merge"]),
        "tags": tags,
        "tag_count": len(tags),
        "working_tree": tree,
        "head": {"hash": hp[0], "short": hp[1], "authored_at": hp[2], "subject": hp[3]} if len(hp) == 4 else None,
    }


def _safe_slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", name).strip("-") or "repository"


def _managed_block(snapshots: List[Dict[str, Any]], synced_at: str) -> str:
    lines = [
        START_MARKER,
        "## Git 工作活动（自动采集）",
        "",
        f"> NexusMind 自动同步于 {synced_at}。此区块由系统维护，可重复刷新。",
        "",
    ]
    for repo in snapshots:
        tree = repo["working_tree"]
        slug = _safe_slug(repo["name"])
        lines.extend([
            f"### {repo['name']}",
            f"- 项目活动：[[20-Projects/Repositories/{slug}/Repository-Activity|{repo['name']}]]",
            f"- 仓库：{repo['path']}",
            f"- 分支：{repo['branch']}",
            f"- 今日提交：{repo['commit_count']} 个；Merge/PR 线索：{repo['merge_count']} 个；Tag：{repo['tag_count']} 个",
            f"- 工作区：{'有未提交变更' if tree['dirty'] else '干净'}（{tree['changed_count']} 个文件）",
        ])
        for commit in repo["commits"]:
            lines.append(f"  - {commit['short']} {commit['subject']}")
        for tag in repo["tags"]:
            lines.append(f"  - Release/Tag：{tag['name']}")
        if tree["changed_files"]:
            lines.append("  - 未提交文件：" + "、".join(tree["changed_files"][:8]))
        lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _upsert_managed_block(content: str, block: str) -> str:
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    if pattern.search(content):
        return pattern.sub(lambda _: block, content).rstrip() + "\n"
    return content.rstrip() + "\n\n---\n\n" + block + "\n"


def _daily_log_base(day: date) -> str:
    return (
        "---\n"
        f"date: {day.isoformat()}\n"
        "tags:\n"
        '  - "#daily-log"\n'
        '  - "#auto-workflow"\n'
        "---\n\n"
        f"# {day.isoformat()} 工作日志\n"
    )


def _write_project_snapshot(repo: Dict[str, Any], synced_at: str, vault_root: Path) -> str:
    rel = f"20-Projects/Repositories/{_safe_slug(repo['name'])}/Repository-Activity.md"
    path = vault_root / rel
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    commits = "\n".join(
        f"- {item['short']} {item['subject']} ({item['authored_at']})"
        for item in repo["commits"]
    ) or "- 今日暂无提交"
    tags = "、".join(item["name"] for item in repo["tags"]) or "无"
    tree = repo["working_tree"]
    head_text = f"{repo['head']['short']} {repo['head']['subject']}" if repo["head"] else "暂无提交"
    safe_path = repo["path"].replace('"', "'")
    safe_remote = repo["remote"].replace('"', "'")
    content = f'''---
title: "{repo['name']} Repository Activity"
repository: "{safe_path}"
remote: "{safe_remote}"
last_synced_at: "{synced_at}"
tags:
  - "#project"
  - "#repository"
  - "#auto-workflow"
---

# {repo['name']} · Repository Activity

## 当前状态
- 路径：{repo['path']}
- 分支：{repo['branch']}
- Remote：{repo['remote'] or '未配置'}
- 工作区：{'有未提交变更' if tree['dirty'] else '干净'}（{tree['changed_count']} 个文件）
- 今日 Tag：{tags}

## 今日提交
{commits}

## 最近 HEAD
- {head_text}

> 此文件由 NexusMind Git 工作流采集器维护。
'''
    version = get_file_hash(existing) if existing else "NEW"
    patch_note(rel, content, if_match=version, actor="workflow", privileged=True, vault_root=vault_root)
    return rel


def sync_git_activity(
    *,
    day: Optional[date] = None,
    roots: Optional[Iterable[Path]] = None,
    targets: Optional[Iterable[Dict[str, Any]]] = None,
    vault_root: Path = VAULT_ROOT,
) -> Dict[str, Any]:
    day = day or date.today()
    configured_targets = list(targets) if targets is not None else (None if roots is not None else workflow_targets())
    repos = discover_repositories(roots=roots, targets=configured_targets)
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshots = [collect_repository(repo, day) for repo in repos]

    result = {
        "status": "success",
        "configured": bool(roots is not None or configured_targets),
        "synced_at": synced_at,
        "day": day.isoformat(),
        "targets": configured_targets or [],
        "repositories": snapshots,
        "repository_count": len(snapshots),
        "commit_count": sum(x["commit_count"] for x in snapshots),
        "tag_count": sum(x["tag_count"] for x in snapshots),
        "daily_log": None,
        "project_notes": [],
    }
    if not repos:
        return result

    daily_rel = f"30-Logs/Daily/{day.isoformat()}.md"
    daily_path = vault_root / daily_rel
    existing = daily_path.read_text(encoding="utf-8") if daily_path.exists() else _daily_log_base(day)
    updated = _upsert_managed_block(existing, _managed_block(snapshots, synced_at))
    version = get_file_hash(daily_path.read_text(encoding="utf-8")) if daily_path.exists() else "NEW"
    patch_note(daily_rel, updated, if_match=version, actor="workflow", privileged=True, vault_root=vault_root)

    project_notes = [_write_project_snapshot(repo, synced_at, vault_root) for repo in snapshots]
    result["daily_log"] = daily_rel
    result["project_notes"] = project_notes
    return result
