from __future__ import annotations

import os
from typing import Any, Dict

import httpx


def _payload(result: Dict[str, Any]) -> Dict[str, Any]:
    repositories = []
    for repo in result.get("repositories", []):
        repositories.append({
            "name": repo.get("name", ""),
            "branch": repo.get("branch", ""),
            "remote": repo.get("remote", ""),
            "current_user": repo.get("current_user", {}),
            "commits": repo.get("commits", []),
            "tags": repo.get("tags", []),
        })
    return {
        "day": result.get("day"),
        "synced_at": result.get("synced_at"),
        "repositories": repositories,
    }


def deliver_git_sync(
    result: Dict[str, Any],
    *,
    cloud_url: str | None = None,
    cloud_token: str | None = None,
) -> Dict[str, Any]:
    cloud_url = (cloud_url if cloud_url is not None else os.environ.get(
        "NEXUSMIND_CLOUD_SYNC_URL", ""
    )).strip()
    cloud_token = (cloud_token if cloud_token is not None else os.environ.get(
        "NEXUSMIND_CLOUD_SYNC_TOKEN", ""
    )).strip()
    if not cloud_url:
        return {"enabled": False, "delivered": False}

    endpoint = cloud_url.rstrip("/") + "/api/cloud/git-events"
    headers = {"content-type": "application/json"}
    if cloud_token:
        headers["authorization"] = f"Bearer {cloud_token}"

    try:
        response = httpx.post(
            endpoint,
            headers=headers,
            json=_payload(result),
            timeout=10.0,
        )
        response.raise_for_status()
        return {
            "enabled": True,
            "delivered": True,
            "status_code": response.status_code,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "delivered": False,
            "error": str(exc),
        }
