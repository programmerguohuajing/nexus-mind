from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

STATE_VERSION = 1
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
IGNORED_TOP_LEVEL = {".obsidian", ".git", ".nexusmind", "__pycache__"}


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_rel_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid vault path: {value}")
    return str(path)


def _local_path(root: Path, rel: str) -> Path:
    safe = _safe_rel_path(rel)
    target = (root / Path(*PurePosixPath(safe).parts)).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ValueError(f"Vault path escapes root: {rel}")
    return target


def _is_syncable(rel: str) -> bool:
    path = PurePosixPath(_safe_rel_path(rel))
    return bool(path.parts) and path.parts[0] not in IGNORED_TOP_LEVEL


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _scan_vault(root: Path) -> tuple[dict[str, dict[str, str]], int]:
    files: dict[str, dict[str, str]] = {}
    skipped = 0
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel_path = path.relative_to(root)
        if rel_path.parts and rel_path.parts[0] in IGNORED_TOP_LEVEL:
            continue
        content = _read_text(path)
        if content is None:
            skipped += 1
            continue
        rel = PurePosixPath(*rel_path.parts).as_posix()
        files[rel] = {"content": content, "version": _sha256(content)}
    return files, skipped


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == STATE_VERSION and isinstance(data.get("files"), dict):
            return data
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {"version": STATE_VERSION, "files": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _headers(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}", "content-type": "application/json"}
def _pull_notes(
    client: httpx.Client,
    endpoint: str,
    headers: dict[str, str],
    paths: list[str],
) -> dict[str, dict[str, str]]:
    pulled: dict[str, dict[str, str]] = {}
    for index in range(0, len(paths), 100):
        batch = paths[index:index + 100]
        response = client.post(
            endpoint + "/api/cloud/vault/pull",
            headers=headers,
            json={"paths": batch},
        )
        response.raise_for_status()
        for item in response.json().get("notes", []):
            path = _safe_rel_path(str(item["path"]))
            pulled[path] = {
                "content": str(item["content"]),
                "version": str(item["version"]),
            }
    return pulled


def _write_local(root: Path, rel: str, content: str) -> None:
    path = _local_path(root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".nexusmind-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _write_conflict(
    conflict_root: Path,
    rel: str,
    remote_content: str,
    reason: str,
) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = _local_path(conflict_root / stamp, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(remote_content, encoding="utf-8")
    meta = target.with_name(target.name + ".conflict.json")
    meta.write_text(
        json.dumps({"path": rel, "reason": reason}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(target)
def _push_batch(
    client: httpx.Client,
    endpoint: str,
    headers: dict[str, str],
    notes: list[dict[str, Any]],
    deletions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    note_index = 0
    delete_index = 0
    while note_index < len(notes) or delete_index < len(deletions):
        note_batch = notes[note_index:note_index + 50]
        delete_batch = deletions[delete_index:delete_index + 50]
        response = client.post(
            endpoint + "/api/cloud/vault/push",
            headers=headers,
            json={"notes": note_batch, "deletions": delete_batch},
        )
        response.raise_for_status()
        results.extend(response.json().get("results", []))
        note_index += len(note_batch)
        delete_index += len(delete_batch)
    return results


def sync_vault_bidirectional(
    *,
    vault_root: Path,
    data_root: Path,
    cloud_url: str,
    cloud_token: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    cloud_url = cloud_url.strip().rstrip("/")
    cloud_token = cloud_token.strip()
    if not cloud_url or not cloud_token:
        return {
            "enabled": False, "success": False, "uploaded": 0,
            "downloaded": 0, "deleted": 0, "conflicts": 0,
            "skipped_binary": 0,
        }

    state_path = data_root / "cloud-vault-sync-state.json"
    conflict_root = data_root / "sync-conflicts"
    state = _load_state(state_path)
    if state.get("cloud_url") != cloud_url:
        state = {"version": STATE_VERSION, "cloud_url": cloud_url, "files": {}}
    else:
        state["cloud_url"] = cloud_url
    records: dict[str, dict[str, Any]] = state["files"]
    local, skipped = _scan_vault(vault_root)
    headers = _headers(cloud_token)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                cloud_url + "/api/cloud/vault/manifest",
                headers=headers,
            )
            response.raise_for_status()
            manifest = response.json()
            cloud = {
                _safe_rel_path(str(item["path"])): item
                for item in manifest.get("notes", [])
                if _is_syncable(str(item["path"]))
            }
            tombstones = {
                _safe_rel_path(str(item["path"])): item
                for item in manifest.get("tombstones", [])
                if _is_syncable(str(item["path"]))
            }

            uploads: list[dict[str, Any]] = []
            remote_deletes: list[dict[str, Any]] = []
            download_paths: list[str] = []
            local_deletes: list[str] = []
            conflict_paths: dict[str, str] = {}
            stable_conflicts: list[str] = []

            all_paths = sorted(set(local) | set(cloud) | set(tombstones) | set(records))
            for rel in all_paths:
                loc = local.get(rel)
                rem = cloud.get(rel)
                tomb = tombstones.get(rel)
                prev = records.get(rel)

                if loc and rem:
                    if loc["version"] == rem["version"]:
                        records[rel] = {
                            "local_version": loc["version"],
                            "cloud_version": rem["version"],
                            "deleted": False,
                            "conflicted": False,
                        }
                        continue
                    if not prev:
                        conflict_paths[rel] = "首次同步时本地与云端内容不同"
                        continue
                    local_changed = loc["version"] != prev.get("local_version")
                    cloud_changed = rem["version"] != prev.get("cloud_version")
                    if local_changed and not cloud_changed and not prev.get("deleted"):
                        uploads.append({
                            "path": rel,
                            "content": loc["content"],
                            "base_version": rem["version"],
                        })
                    elif cloud_changed and not local_changed and not prev.get("deleted"):
                        download_paths.append(rel)
                    elif prev.get("conflicted") and not local_changed and not cloud_changed:
                        stable_conflicts.append(rel)
                    else:
                        conflict_paths[rel] = "本地与云端同时发生修改"
                    continue
                if loc and not rem:
                    if tomb and prev and not prev.get("deleted"):
                        local_changed = loc["version"] != prev.get("local_version")
                        if not local_changed:
                            local_deletes.append(rel)
                            records[rel] = {
                                "local_version": None,
                                "cloud_version": tomb["version"],
                                "deleted": True,
                                "conflicted": False,
                            }
                        else:
                            records[rel] = {
                                "local_version": loc["version"],
                                "cloud_version": tomb["version"],
                                "deleted": False,
                                "conflicted": True,
                            }
                            stable_conflicts.append(rel)
                    else:
                        uploads.append({
                            "path": rel,
                            "content": loc["content"],
                            "base_version": None,
                        })
                    continue

                if rem and not loc:
                    if not prev or prev.get("deleted"):
                        download_paths.append(rel)
                        continue
                    if prev.get("conflicted") and prev.get("local_version") is None:
                        if rem["version"] == prev.get("cloud_version"):
                            stable_conflicts.append(rel)
                        else:
                            conflict_paths[rel] = "本地删除后云端内容再次发生修改"
                        continue
                    cloud_changed = rem["version"] != prev.get("cloud_version")
                    if not cloud_changed:
                        remote_deletes.append({
                            "path": rel,
                            "base_version": rem["version"],
                        })
                    else:
                        conflict_paths[rel] = "本地删除与云端修改发生冲突"
                    continue

                if tomb:
                    records[rel] = {
                        "local_version": None,
                        "cloud_version": tomb["version"],
                        "deleted": True,
                        "conflicted": False,
                    }
                else:
                    records.pop(rel, None)
            need_pull = sorted(set(download_paths) | set(conflict_paths))
            pulled = _pull_notes(client, cloud_url, headers, need_pull) if need_pull else {}

            downloaded = 0
            for rel in download_paths:
                item = pulled.get(rel)
                if not item:
                    continue
                _write_local(vault_root, rel, item["content"])
                records[rel] = {
                    "local_version": item["version"],
                    "cloud_version": item["version"],
                    "deleted": False,
                    "conflicted": False,
                }
                downloaded += 1

            deleted_local = 0
            for rel in local_deletes:
                path = _local_path(vault_root, rel)
                try:
                    path.unlink()
                    deleted_local += 1
                except FileNotFoundError:
                    pass

            conflict_files: list[str] = []
            for rel, reason in conflict_paths.items():
                item = pulled.get(rel)
                loc = local.get(rel)
                if item:
                    conflict_files.append(
                        _write_conflict(conflict_root, rel, item["content"], reason)
                    )
                records[rel] = {
                    "local_version": loc["version"] if loc else None,
                    "cloud_version": (
                        item["version"] if item else cloud.get(rel, {}).get("version")
                    ),
                    "deleted": False,
                    "conflicted": True,
                }

            push_results = _push_batch(
                client, cloud_url, headers, uploads, remote_deletes
            ) if uploads or remote_deletes else []
            uploaded = 0
            deleted_remote = 0
            late_conflicts = 0
            late_conflict_paths: list[str] = []
            local_by_path = {item["path"]: item for item in uploads}
            for result in push_results:
                rel = _safe_rel_path(str(result["path"]))
                status = result.get("status")
                operation = result.get("operation")
                if status == "success" and operation == "upsert":
                    source = local_by_path.get(rel)
                    version = str(result["version"])
                    records[rel] = {
                        "local_version": (
                            _sha256(str(source["content"])) if source else version
                        ),
                        "cloud_version": version,
                        "deleted": False,
                        "conflicted": False,
                    }
                    uploaded += 1
                elif status == "success" and operation == "delete":
                    records[rel] = {
                        "local_version": None,
                        "cloud_version": str(result["version"]),
                        "deleted": True,
                        "conflicted": False,
                    }
                    deleted_remote += 1
                elif status == "conflict":
                    late_conflicts += 1
                    late_conflict_paths.append(rel)
                    records[rel] = {
                        "local_version": local.get(rel, {}).get("version"),
                        "cloud_version": result.get("remote_version"),
                        "deleted": False,
                        "conflicted": True,
                    }

            if late_conflict_paths:
                late_remote = _pull_notes(
                    client, cloud_url, headers, sorted(set(late_conflict_paths))
                )
                for rel in sorted(set(late_conflict_paths)):
                    item = late_remote.get(rel)
                    if item:
                        conflict_files.append(
                            _write_conflict(
                                conflict_root,
                                rel,
                                item["content"],
                                "同步期间云端版本发生变化",
                            )
                        )
                        records[rel]["cloud_version"] = item["version"]

            _save_state(state_path, state)
            return {
                "enabled": True,
                "success": True,
                "uploaded": uploaded,
                "downloaded": downloaded,
                "deleted": deleted_local + deleted_remote,
                "conflicts": len(conflict_paths) + len(stable_conflicts) + late_conflicts,
                "conflict_files": conflict_files,
                "skipped_binary": skipped,
            }
    except Exception as exc:
        return {
            "enabled": True,
            "success": False,
            "uploaded": 0,
            "downloaded": 0,
            "deleted": 0,
            "conflicts": 0,
            "skipped_binary": skipped,
            "error": str(exc),
        }
