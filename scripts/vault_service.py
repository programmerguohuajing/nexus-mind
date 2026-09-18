import sys
from pathlib import Path

# 将 src 加入 python path 方便直接运行脚本
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import threading
import time

import uvicorn
from nexusmind.config import DEFAULT_HOST, DEFAULT_PORT, GIT_SYNC_INTERVAL, VAULT_ROOT
from nexusmind.api.server import app
from nexusmind.core.git_activity import sync_git_activity


def _workflow_sync_loop():
    while True:
        try:
            result = sync_git_activity()
            print(
                f"Workflow sync: repos={result['repository_count']}, "
                f"commits={result['commit_count']}, log={result['daily_log']}"
            )
        except Exception as exc:
            print(f"Workflow sync failed: {exc}", file=sys.stderr)
        time.sleep(GIT_SYNC_INTERVAL)


if __name__ == "__main__":
    print(f"Starting NexusMind Vault MCP Service v4.0 at http://{DEFAULT_HOST}:{DEFAULT_PORT}, vault={VAULT_ROOT}")
    threading.Thread(target=_workflow_sync_loop, daemon=True, name="nexusmind-workflow-sync").start()
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
