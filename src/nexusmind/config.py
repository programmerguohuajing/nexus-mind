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
NOTIFICATION_CONFIG_PATH = Path(
    os.environ.get("NEXUSMIND_NOTIFICATION_CONFIG", DATA_ROOT / "notification-config.json")
).expanduser().resolve()
CLOUD_SYNC_URL = os.environ.get("NEXUSMIND_CLOUD_SYNC_URL", "").strip()
CLOUD_SYNC_TOKEN = os.environ.get("NEXUSMIND_CLOUD_SYNC_TOKEN", "").strip()

# Phase 1: 本地 API Token（剪藏扩展/局域网客户端调用 /api 时鉴权；为空表示不启用）
API_TOKEN = os.environ.get("NEXUSMIND_API_TOKEN", "").strip()
# Phase 1: 每篇笔记保留的历史版本份数
HISTORY_KEEP = max(1, int(os.environ.get("NEXUSMIND_HISTORY_KEEP", "30")))
# Phase 1: OCR 语言（tesseract 语言包名，+ 分隔）
OCR_LANG = os.environ.get("NEXUSMIND_OCR_LANG", "chi_sim+eng").strip() or "chi_sim+eng"

# Phase 2: LLM 网关（provider: auto|ollama|openai|off；auto 时优先本地 Ollama）
LLM_PROVIDER = os.environ.get("NEXUSMIND_LLM_PROVIDER", "auto").strip().lower() or "auto"
LLM_BASE_URL = os.environ.get("NEXUSMIND_LLM_BASE_URL", "http://127.0.0.1:11434").strip()
LLM_MODEL = os.environ.get("NEXUSMIND_LLM_MODEL", "qwen2.5:7b").strip()
LLM_API_KEY = os.environ.get("NEXUSMIND_LLM_API_KEY", "").strip()
LLM_TIMEOUT = float(os.environ.get("NEXUSMIND_LLM_TIMEOUT", "60"))
# Phase 2: Embedding 后端（local=内置离线向量器；ollama/openai 走对应 API）
EMBED_PROVIDER = os.environ.get("NEXUSMIND_EMBED_PROVIDER", "local").strip().lower() or "local"
EMBED_MODEL = os.environ.get("NEXUSMIND_EMBED_MODEL", "bge-m3").strip()

# Phase 3: 代码平台连接器与订阅管道配置路径
CONNECTORS_CONFIG_PATH = Path(
    os.environ.get("NEXUSMIND_CONNECTORS_CONFIG", DATA_ROOT / "connectors-config.json")
).expanduser().resolve()
FEEDS_CONFIG_PATH = Path(
    os.environ.get("NEXUSMIND_FEEDS_CONFIG", DATA_ROOT / "feeds-config.json")
).expanduser().resolve()
GOALS_DATA_PATH = Path(
    os.environ.get("NEXUSMIND_GOALS_DATA", DATA_ROOT / "goals.json")
).expanduser().resolve()

# 默认服务端口配置
DEFAULT_HOST = os.environ.get("NEXUSMIND_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("NEXUSMIND_PORT", "8301"))
GIT_SYNC_INTERVAL = max(60, int(os.environ.get("NEXUSMIND_GIT_SYNC_INTERVAL", "300")))

# 只读限制目录前缀矩阵
READ_ONLY_FOLDERS = ["60-References"]
