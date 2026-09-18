import os
from pathlib import Path

# Vault 根目录解析（优先使用环境变量，默认使用项目内 vault/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_VAULT_ROOT = PROJECT_ROOT / "vault"
VAULT_ROOT = Path(os.environ.get("NEXUSMIND_VAULT_ROOT", DEFAULT_VAULT_ROOT)).resolve()

# 默认服务端口配置
DEFAULT_HOST = os.environ.get("NEXUSMIND_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("NEXUSMIND_PORT", "8301"))
GIT_SYNC_INTERVAL = max(60, int(os.environ.get("NEXUSMIND_GIT_SYNC_INTERVAL", "300")))

# 只读限制目录前缀矩阵
READ_ONLY_FOLDERS = ["60-References"]
