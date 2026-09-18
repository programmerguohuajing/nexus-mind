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


@dataclass
class AgentStatus:
    state: str = "stopped"
    message: str = ""
    last_sync: str = ""
    repository_count: int = 0
    commit_count: int = 0
    cloud_delivered: bool = False
    api_running: bool = False


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
            self._emit(state="running", message="Agent running")


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
        self._emit(state="stopped", message="Agent stopped", api_running=False)

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
        self._emit(state="running", message="Configuration reloaded")

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
                message=(
                    "Local API failed to start. "
                    "Check whether the configured port is already in use."
                ),
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
        folders = [
            {"type": "directory", "path": path, "enabled": True}
            for path in self.config.folders
            if Path(path).is_dir()
        ]
        if not folders:
            self._emit(
                state="running",
                message="No Git collection folders configured",
                repository_count=0,
                commit_count=0,
            )
            return
        try:
            env = runtime_environment(self.config)
            os.environ.update({
                key: env[key]
                for key in (
                    "NEXUSMIND_CLOUD_SYNC_URL",
                    "NEXUSMIND_CLOUD_SYNC_TOKEN",
                )
            })
            result = sync_git_activity(
                targets=folders,
                vault_root=Path(self.config.data_root) / "vault",
            )
            cloud = result.get("cloud_sync") or {}
            self._emit(
                state="running",
                message="Sync completed",
                last_sync=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                repository_count=result.get("repository_count", 0),
                commit_count=result.get("commit_count", 0),
                cloud_delivered=bool(cloud.get("delivered")),
            )
        except Exception as exc:
            self._emit(state="error", message=str(exc))

    def _watch_config(self) -> None:
        while not self._shutdown.is_set():
            time.sleep(2)
            mtime = self._mtime()
            if mtime and mtime != self._config_mtime:
                self._config_mtime = mtime
                try:
                    self.reload()
                except Exception as exc:
                    self._emit(state="error", message=f"Config reload failed: {exc}")
