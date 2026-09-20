from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from nexusmind.agent.configuration import (
    AgentConfig,
    AgentConfigStore,
    api_service_command,
)
from nexusmind.core.git_activity import sync_git_activity
from nexusmind.core.vault_sync import sync_vault_bidirectional


@dataclass
class AgentStatus:
    state: str = "stopped"
    message: str = ""
    last_sync: str = ""
    repository_count: int = 0
    commit_count: int = 0
    cloud_delivered: bool = False
    cloud_state: str = "unconfigured"
    cloud_message: str = ""
    cloud_last_sync: str = ""
    api_running: bool = False
    sync_in_progress: bool = False
    sync_uploaded: int = 0
    sync_downloaded: int = 0
    sync_deleted: int = 0
    sync_conflicts: int = 0


StatusCallback = Callable[[AgentStatus], None]


def runtime_environment(config: AgentConfig) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "NEXUSMIND_RUNTIME": "local",
        "NEXUSMIND_DATA_ROOT": config.data_root,
        "NEXUSMIND_HOST": config.local_api_host,
        "NEXUSMIND_PORT": str(config.local_api_port),
        "NEXUSMIND_GIT_SYNC_INTERVAL": str(config.sync_interval),
        "NEXUSMIND_CLOUD_SYNC_URL": config.cloud_url,
        "NEXUSMIND_CLOUD_SYNC_TOKEN": config.cloud_token,
    })
    return env


class AgentSupervisor:
    def __init__(
        self,
        store: AgentConfigStore,
        on_status: StatusCallback | None = None,
    ):
        self.store = store
        self.on_status = on_status or (lambda _: None)
        self.config = store.load()
        self.status = AgentStatus()
        self._shutdown = threading.Event()
        self._worker_stop = threading.Event()
        self._sync_now = threading.Event()
        self._worker: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._api_process: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._config_mtime = self._mtime()

    def _mtime(self) -> float:
        try:
            return self.store.path.stat().st_mtime
        except OSError:
            return 0.0

    def _emit(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self.status, key, value)
        self.on_status(self.status)

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._shutdown.clear()
            self._worker_stop.clear()
            self._write_workflow_config(self.config)
            self._start_api()
            self._worker = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="nexusmind-agent-sync",
            )
            self._worker.start()
            if not self._watcher or not self._watcher.is_alive():
                self._watcher = threading.Thread(
                    target=self._watch_config,
                    daemon=True,
                    name="nexusmind-agent-config-watch",
                )
                self._watcher.start()
            self._emit(state="running", message="Agent 正在运行")


    def stop(self) -> None:
        self._shutdown.set()
        self._worker_stop.set()
        self._sync_now.set()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=5)
        self._worker = None
        watcher = self._watcher
        if watcher and watcher.is_alive() and watcher is not threading.current_thread():
            watcher.join(timeout=3)
        self._watcher = None
        self._stop_api()
        self._emit(state="stopped", message="Agent 已停止", api_running=False)

    def apply(self, config: AgentConfig, save: bool = True) -> AgentConfig:
        with self._lock:
            config = self.store.save(config) if save else config.normalized()
            self._write_workflow_config(config)
            self.config = config
            self._config_mtime = self._mtime()
            self._restart_runtime()
            return config

    def _write_workflow_config(self, config: AgentConfig) -> None:
        path = Path(config.data_root) / "workflow-config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        targets = [
            {"type": "directory", "path": folder, "enabled": True}
            for folder in config.folders
        ]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"targets": targets}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def reload(self) -> AgentConfig:
        return self.apply(self.store.load(), save=False)

    def sync_now(self) -> None:
        if self.status.sync_in_progress:
            return
        cloud_ready = bool(self.config.cloud_url and self.config.cloud_token)
        self._emit(
            sync_in_progress=True,
            cloud_state="syncing" if cloud_ready else (
                "incomplete" if self.config.cloud_url else "unconfigured"
            ),
            cloud_message="正在同步云端数据…" if cloud_ready else "",
            message="已请求立即同步",
        )
        self._sync_now.set()

    def _restart_runtime(self) -> None:
        self._worker_stop.set()
        self._sync_now.set()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=5)
        self._worker_stop.clear()
        self._stop_api()
        self._start_api()
        self._worker = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="nexusmind-agent-sync",
        )
        self._worker.start()
        self._emit(state="running", message="配置已重新加载")

    def _start_api(self) -> None:
        if not self.config.local_api_enabled:
            self._emit(api_running=False)
            return
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._api_process = subprocess.Popen(
            api_service_command(),
            env=runtime_environment(self.config),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        time.sleep(0.25)
        if self._api_process.poll() is not None:
            self._emit(
                api_running=False,
                message="本地 API 启动失败，请检查配置的端口是否已被占用。",
            )
            self._api_process = None
            return
        self._emit(api_running=True)

    def _stop_api(self) -> None:
        process = self._api_process
        self._api_process = None
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


    def _run_loop(self) -> None:
        while not self._worker_stop.is_set() and not self._shutdown.is_set():
            self._run_once()
            wait_for = max(60, self.config.sync_interval)
            self._sync_now.wait(wait_for)
            self._sync_now.clear()

    def _run_once(self) -> None:
        self._emit(
            sync_in_progress=True,
            message="正在采集 Git 活动并同步知识库…",
            sync_uploaded=0,
            sync_downloaded=0,
            sync_deleted=0,
            sync_conflicts=0,
        )
        folders = [
            {"type": "directory", "path": path, "enabled": True}
            for path in self.config.folders
            if Path(path).is_dir()
        ]
        try:
            env = runtime_environment(self.config)
            os.environ.update({
                key: env[key]
                for key in (
                    "NEXUSMIND_CLOUD_SYNC_URL",
                    "NEXUSMIND_CLOUD_SYNC_TOKEN",
                )
            })
            vault_root = Path(self.config.data_root) / "vault"
            if folders:
                result = sync_git_activity(targets=folders, vault_root=vault_root)
            else:
                result = {"repository_count": 0, "commit_count": 0, "cloud_sync": {}}

            vault_sync = sync_vault_bidirectional(
                vault_root=vault_root,
                data_root=Path(self.config.data_root),
                cloud_url=self.config.cloud_url,
                cloud_token=self.config.cloud_token,
            )
            git_cloud = result.get("cloud_sync") or {}
            cloud_url_set = bool(self.config.cloud_url.strip())
            cloud_ready = bool(
                self.config.cloud_url.strip() and self.config.cloud_token.strip()
            )
            vault_ok = bool(vault_sync.get("success"))
            git_attempted = bool(git_cloud.get("enabled"))
            git_ok = bool(git_cloud.get("delivered"))
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not cloud_url_set:
                cloud_state = "unconfigured"
                cloud_message = "未配置 Cloud API"
                cloud_ok = False
            elif not cloud_ready:
                cloud_state = "incomplete"
                cloud_message = "Cloud API 已填写，但缺少 Sync Token"
                cloud_ok = False
            elif vault_ok and (not git_attempted or git_ok):
                cloud_state = "synced"
                cloud_message = "云端数据同步成功"
                cloud_ok = True
            elif vault_ok or git_ok:
                cloud_state = "partial"
                cloud_message = (
                    "部分云端数据同步成功；"
                    + (
                        f"Git 事件同步失败：{git_cloud.get('error', '未知错误')}"
                        if vault_ok and git_attempted and not git_ok
                        else f"知识库同步失败：{vault_sync.get('error', '未知错误')}"
                    )
                )
                cloud_ok = True
            else:
                cloud_state = "error"
                cloud_message = (
                    vault_sync.get("error")
                    or git_cloud.get("error")
                    or "云端同步失败"
                )
                cloud_ok = False

            if vault_sync.get("enabled") and not vault_sync.get("success"):
                message = f"知识库同步失败：{vault_sync.get('error', '未知错误')}"
                state = "error" if cloud_state == "error" else "running"
            elif vault_sync.get("enabled"):
                message = (
                    f"同步完成：上传 {vault_sync.get('uploaded', 0)}，"
                    f"下载 {vault_sync.get('downloaded', 0)}，"
                    f"删除 {vault_sync.get('deleted', 0)}，"
                    f"冲突 {vault_sync.get('conflicts', 0)}"
                )
                if vault_sync.get("conflicts"):
                    message += f"（冲突副本：{Path(self.config.data_root) / 'sync-conflicts'}）"
                state = "running"
            elif folders:
                message = (
                    "Git 活动采集完成；"
                    + (
                        cloud_message
                        if cloud_state in {"incomplete", "error", "partial"}
                        else "云端知识库同步未配置"
                    )
                )
                state = "running"
            else:
                message = "尚未配置 Git 采集目录或云端同步"
                state = "running"

            self._emit(
                state=state,
                message=message,
                last_sync=now_text,
                repository_count=result.get("repository_count", 0),
                commit_count=result.get("commit_count", 0),
                cloud_delivered=cloud_ok,
                cloud_state=cloud_state,
                cloud_message=cloud_message,
                cloud_last_sync=now_text if cloud_state in {"synced", "partial"} else self.status.cloud_last_sync,
                sync_in_progress=False,
                sync_uploaded=int(vault_sync.get("uploaded", 0)),
                sync_downloaded=int(vault_sync.get("downloaded", 0)),
                sync_deleted=int(vault_sync.get("deleted", 0)),
                sync_conflicts=int(vault_sync.get("conflicts", 0)),
            )
        except Exception as exc:
            if self.config.cloud_url.strip() and self.config.cloud_token.strip():
                cloud_state = "error"
            elif self.config.cloud_url.strip():
                cloud_state = "incomplete"
            else:
                cloud_state = "unconfigured"
            self._emit(
                state="error",
                message=str(exc),
                cloud_state=cloud_state,
                cloud_message=str(exc) if cloud_state == "error" else "",
                sync_in_progress=False,
            )

    def _watch_config(self) -> None:
        while not self._shutdown.is_set():
            time.sleep(2)
            mtime = self._mtime()
            if mtime and mtime != self._config_mtime:
                self._config_mtime = mtime
                try:
                    self.reload()
                except Exception as exc:
                    self._emit(state="error", message=f"配置重新加载失败：{exc}")
