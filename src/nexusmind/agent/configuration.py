from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_NAME = "NexusMind"
CONFIG_NAME = "agent-config.json"


def user_config_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        return base / APP_NAME
    if system == "darwin":
        return Path.home() / "Library/Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "nexusmind"


def default_data_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        return base / APP_NAME / "data"
    if system == "darwin":
        return Path.home() / "Library/Application Support" / APP_NAME / "data"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "nexusmind"


@dataclass
class AgentConfig:
    folders: list[str] = field(default_factory=list)
    local_api_enabled: bool = True
    local_api_host: str = "127.0.0.1"
    local_api_port: int = 8301
    data_root: str = field(default_factory=lambda: str(default_data_dir()))
    cloud_url: str = ""
    cloud_token: str = ""
    sync_interval: int = 300
    start_minimized: bool = False
    auto_start: bool = False

    def normalized(self) -> "AgentConfig":
        folders: list[str] = []
        seen: set[str] = set()
        for raw in self.folders:
            path = Path(raw).expanduser().resolve()
            key = os.path.normcase(str(path))
            if key in seen:
                continue
            seen.add(key)
            folders.append(str(path))
        self.folders = folders
        self.sync_interval = max(60, int(self.sync_interval))
        self.local_api_port = int(self.local_api_port)
        self.cloud_url = self.cloud_url.strip().rstrip("/")
        self.cloud_token = self.cloud_token.strip()
        self.local_api_host = self.local_api_host.strip() or "127.0.0.1"
        self.data_root = str(Path(self.data_root).expanduser().resolve())
        return self


class AgentConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (user_config_dir() / CONFIG_NAME)

    def load(self) -> AgentConfig:
        if not self.path.exists():
            return AgentConfig().normalized()
        try:
            data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AgentConfig().normalized()
        allowed = {item.name for item in AgentConfig.__dataclass_fields__.values()}
        payload = {key: value for key, value in data.items() if key in allowed}
        try:
            return AgentConfig(**payload).normalized()
        except (TypeError, ValueError):
            return AgentConfig().normalized()

    def save(self, config: AgentConfig) -> AgentConfig:
        config = config.normalized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return config


def executable_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "nexusmind.agent.main"]


def api_service_command() -> list[str]:
    return executable_command() + ["--api-service"]


def startup_command() -> str:
    parts = executable_command() + ["--minimized"]
    if platform.system().lower() == "windows":
        return " ".join(f'"{part}"' if " " in part else part for part in parts)
    return " ".join(parts)
