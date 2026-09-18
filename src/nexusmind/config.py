import os
from pathlib import Path

# Runtime / persistent data roots.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME_MODE = os.environ.get("NEXUSMIND_RUNTIME", "local").strip().lower() or "local"
DATA_ROOT = Path(os.environ.get("NEXUSMIND_DATA_ROOT", PROJECT_ROOT)).expanduser().resolve()
DEFAULT_VAULT_ROOT = DATA_ROOT / "vault"
VAULT_ROOT = Path(os.environ.get("NEXUSMIND_VAULT_ROOT", DEFAULT_VAULT_ROOT)).expanduser().resolve()
WORKFLOW_CONFIG_PATH = Path(
    os.environ.get("NEXUSMIND_WORKFLOW_CONFIG", DATA_ROOT / "workflow-config.json")
).expanduser().resolve()
CLOUD_SYNC_URL = os.environ.get("NEXUSMIND_CLOUD_SYNC_URL", "").strip()
CLOUD_SYNC_TOKEN = os.environ.get("NEXUSMIND_CLOUD_SYNC_TOKEN", "").strip()

# 默认服务端口配置
DEFAULT_HOST = os.environ.get("NEXUSMIND_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("NEXUSMIND_PORT", "8301"))
GIT_SYNC_INTERVAL = max(60, int(os.environ.get("NEXUSMIND_GIT_SYNC_INTERVAL", "300")))

# 只读限制目录前缀矩阵
READ_ONLY_FOLDERS = ["60-References"]
