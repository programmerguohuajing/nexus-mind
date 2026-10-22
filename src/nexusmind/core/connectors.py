"""代码平台连接器（产品设计文档 P3-1）：GitHub / GitLab 的 PR/MR 与 Issue 同步。

同步产物：
- PR/MR、Issue 写入 Raw 层 60-References/CodePlatform（不可覆盖，增量跳过未变化项）；
- 评论中带知识标记（"知识:"/"坑:"/"注意:" 或被标为知识性）的内容返回为
  knowledge_candidates，供上层一键转 Domain 卡片；
- 同步状态（每仓库已同步条目的 updated_at）存 Vault/.nexusmind/connectors-state.json。
配置存 DATA_ROOT/connectors-config.json（Token 不进 Vault、不进 Git）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from nexusmind.config import CONNECTORS_CONFIG_PATH, VAULT_ROOT
from nexusmind.core.ingest import ingest_article

_KNOWLEDGE_MARKERS = ("知识:", "知识：", "坑:", "坑：", "注意:", "注意：", "知识点", "踩坑")


def _get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    """统一 GET JSON（测试可 monkeypatch）。"""
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


def load_connectors_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or CONNECTORS_CONFIG_PATH
    if not path.exists():
        return {"github": {"token": "", "repos": []}, "gitlab": {"base_url": "https://gitlab.com", "token": "", "projects": []}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("github", {"token": "", "repos": []})
            data.setdefault("gitlab", {"base_url": "https://gitlab.com", "token": "", "projects": []})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"github": {"token": "", "repos": []}, "gitlab": {"base_url": "https://gitlab.com", "token": "", "projects": []}}


def save_connectors_config(data: Dict[str, Any], config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or CONNECTORS_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_connectors_config(path)


def sanitize_connectors_config(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = json.loads(json.dumps(data))
    for platform in ("github", "gitlab"):
        if cleaned.get(platform, {}).get("token"):
            cleaned[platform]["token"] = "******"
    return cleaned


def _state_path(vault_root: Path) -> Path:
    return vault_root / ".nexusmind" / "connectors-state.json"


def _load_state(vault_root: Path) -> Dict[str, Any]:
    path = _state_path(vault_root)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"items": {}}


def _save_state(vault_root: Path, state: Dict[str, Any]) -> None:
    path = _state_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _knowledge_candidates(comments: List[Dict[str, Any]], *, repo: str, number: int, kind: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        if any(marker in body for marker in _KNOWLEDGE_MARKERS) and len(body) >= 10:
            candidates.append({
                "repo": repo,
                "kind": kind,
                "number": number,
                "author": str((comment.get("user") or {}).get("login") or comment.get("author") or "unknown"),
                "excerpt": body[:500],
            })
    return candidates


def _render_item_markdown(item: Dict[str, Any], comments: List[Dict[str, Any]], kind: str) -> str:
    lines = [
        f"# {kind} #{item['number']}：{item['title']}",
        "",
        f"- 状态：{item.get('state', '')}",
        f"- 作者：{item.get('author', '')}",
        f"- 链接：{item.get('html_url', '')}",
        f"- 创建：{item.get('created_at', '')} · 更新：{item.get('updated_at', '')}",
    ]
    if item.get("merged_at"):
        lines.append(f"- 合并时间：{item['merged_at']}")
    if item.get("labels"):
        lines.append(f"- 标签：{', '.join(item['labels'])}")
    lines += ["", "## 描述", "", str(item.get("body") or "（无描述）"), ""]
    if comments:
        lines.append("## 评论")
        for comment in comments[:30]:
            author = str((comment.get("user") or {}).get("login") or comment.get("author") or "unknown")
            lines.append(f"\n### @{author}\n\n{comment.get('body') or ''}")
    return "\n".join(lines) + "\n"


def _sync_items(
    *,
    platform: str,
    repo_key: str,
    items: List[Dict[str, Any]],
    comments_by_number: Dict[int, List[Dict[str, Any]]],
    vault_root: Path,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    folder = "60-References/CodePlatform"
    synced, skipped = 0, 0
    candidates: List[Dict[str, Any]] = []
    for item in items:
        state_key = f"{platform}:{repo_key}:{item['kind']}:{item['number']}"
        if state["items"].get(state_key) == item.get("updated_at"):
            skipped += 1
            continue
        comments = comments_by_number.get(item["number"], [])
        content = _render_item_markdown(item, comments, item["kind"])
        ingest_article(
            title=f"[{repo_key}] {item['kind']} #{item['number']} {item['title']}",
            content=content,
            author=item.get("author") or platform,
            url=item.get("html_url"),
            folder=folder,
            vault_root=vault_root,
        )
        candidates.extend(_knowledge_candidates(comments, repo=repo_key, number=item["number"], kind=item["kind"]))
        state["items"][state_key] = item.get("updated_at")
        synced += 1
    return {"repo": repo_key, "platform": platform, "synced": synced, "skipped": skipped, "knowledge_candidates": candidates}


def sync_github_repo(owner: str, repo: str, *, token: str = "", vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """同步单个 GitHub 仓库的 PR 与 Issue（含评论）。"""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    state = _load_state(vault_root)
    results: List[Dict[str, Any]] = []

    pulls = _get_json(f"{base}/pulls?state=all&per_page=50&sort=updated&direction=desc", headers)
    items: List[Dict[str, Any]] = []
    comments_by_number: Dict[int, List[Dict[str, Any]]] = {}
    for pr in pulls if isinstance(pulls, list) else []:
        items.append({
            "kind": "PR",
            "number": pr["number"],
            "title": pr.get("title", ""),
            "state": "merged" if pr.get("merged_at") else pr.get("state", ""),
            "author": (pr.get("user") or {}).get("login", ""),
            "html_url": pr.get("html_url", ""),
            "created_at": pr.get("created_at", ""),
            "updated_at": pr.get("updated_at", ""),
            "merged_at": pr.get("merged_at"),
            "labels": [label.get("name", "") for label in pr.get("labels", [])],
            "body": pr.get("body") or "",
        })
        comments = _get_json(f"{base}/issues/{pr['number']}/comments?per_page=30", headers)
        comments_by_number[pr["number"]] = comments if isinstance(comments, list) else []
    results.append(_sync_items(platform="github", repo_key=f"{owner}/{repo}", items=items,
                               comments_by_number=comments_by_number, vault_root=vault_root, state=state))

    issues_raw = _get_json(f"{base}/issues?state=all&per_page=50&sort=updated&direction=desc", headers)
    items = []
    comments_by_number = {}
    for issue in issues_raw if isinstance(issues_raw, list) else []:
        if "pull_request" in issue:
            continue
        items.append({
            "kind": "Issue",
            "number": issue["number"],
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "author": (issue.get("user") or {}).get("login", ""),
            "html_url": issue.get("html_url", ""),
            "created_at": issue.get("created_at", ""),
            "updated_at": issue.get("updated_at", ""),
            "merged_at": None,
            "labels": [label.get("name", "") for label in issue.get("labels", [])],
            "body": issue.get("body") or "",
        })
        comments = _get_json(f"{base}/issues/{issue['number']}/comments?per_page=30", headers)
        comments_by_number[issue["number"]] = comments if isinstance(comments, list) else []
    results.append(_sync_items(platform="github", repo_key=f"{owner}/{repo}", items=items,
                               comments_by_number=comments_by_number, vault_root=vault_root, state=state))

    _save_state(vault_root, state)
    return {"platform": "github", "results": results}


def sync_gitlab_project(project: str, *, base_url: str = "https://gitlab.com", token: str = "",
                        vault_root: Path = VAULT_ROOT) -> Dict[str, Any]:
    """同步单个 GitLab 项目的 MR 与 Issue。project 为 URL 编码前路径或数字 ID。"""
    from urllib.parse import quote

    headers = {"PRIVATE-TOKEN": token} if token else {}
    base = f"{base_url.rstrip('/')}/api/v4/projects/{quote(str(project), safe='')}"
    state = _load_state(vault_root)
    results: List[Dict[str, Any]] = []

    for kind, endpoint in (("MR", "merge_requests"), ("Issue", "issues")):
        raw = _get_json(f"{base}/{endpoint}?per_page=50&order_by=updated_at&sort=desc", headers)
        items: List[Dict[str, Any]] = []
        comments_by_number: Dict[int, List[Dict[str, Any]]] = {}
        for entry in raw if isinstance(raw, list) else []:
            number = entry.get("iid")
            items.append({
                "kind": kind,
                "number": number,
                "title": entry.get("title", ""),
                "state": entry.get("state", ""),
                "author": (entry.get("author") or {}).get("username", ""),
                "html_url": entry.get("web_url", ""),
                "created_at": entry.get("created_at", ""),
                "updated_at": entry.get("updated_at", ""),
                "merged_at": entry.get("merged_at"),
                "labels": entry.get("labels", []),
                "body": entry.get("description") or "",
            })
            notes = _get_json(f"{base}/{endpoint}/{number}/notes?per_page=30", headers)
            comments_by_number[number] = [
                {"body": note.get("body") or "", "author": (note.get("author") or {}).get("username", "")}
                for note in (notes if isinstance(notes, list) else [])
                if not note.get("system")
            ]
        results.append(_sync_items(platform="gitlab", repo_key=str(project), items=items,
                                   comments_by_number=comments_by_number, vault_root=vault_root, state=state))
    _save_state(vault_root, state)
    return {"platform": "gitlab", "results": results}


def sync_all_connectors(*, vault_root: Path = VAULT_ROOT, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """按配置同步全部启用的仓库/项目。"""
    config = load_connectors_config(config_path)
    outcomes: List[Dict[str, Any]] = []
    github_cfg = config.get("github", {})
    for repo_cfg in github_cfg.get("repos", []):
        if not repo_cfg.get("enabled", True):
            continue
        outcomes.append(sync_github_repo(
            repo_cfg["owner"], repo_cfg["repo"],
            token=github_cfg.get("token", ""), vault_root=vault_root,
        ))
    gitlab_cfg = config.get("gitlab", {})
    for project_cfg in gitlab_cfg.get("projects", []):
        if not project_cfg.get("enabled", True):
            continue
        outcomes.append(sync_gitlab_project(
            project_cfg["project"],
            base_url=gitlab_cfg.get("base_url", "https://gitlab.com"),
            token=gitlab_cfg.get("token", ""), vault_root=vault_root,
        ))
    total_synced = sum(
        r["synced"] for outcome in outcomes for r in outcome["results"]
    )
    candidates = [
        c for outcome in outcomes for r in outcome["results"] for c in r["knowledge_candidates"]
    ]
    return {"outcomes": outcomes, "total_synced": total_synced, "knowledge_candidates": candidates}
