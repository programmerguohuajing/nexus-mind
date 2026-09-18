import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from nexusmind.api.server import app
from nexusmind.config import VAULT_ROOT

client = TestClient(app)


def run_tests():
    print("=== 1. Health ===")
    health = client.get("/health")
    assert health.status_code == 200
    print("✅", health.json())

    print("\n=== 2. 正式知识读取 ===")
    target = "40-Domain/Architecture/LLM-Wiki-编译型知识架构.md"
    read = client.post("/mcp/vault_read", json={"path": target})
    assert read.status_code == 200
    print("✅ version:", read.json()["version"])

    print("\n=== 3. 权限矩阵 ===")
    denied = client.post("/mcp/vault_patch", json={
        "path": target,
        "content": "# forbidden",
        "ifMatch": read.json()["version"],
    })
    assert denied.status_code == 403
    raw_denied = client.post("/mcp/vault_patch", json={
        "path": "60-References/Articles/__forbidden__.md",
        "content": "# forbidden",
        "ifMatch": "NEW",
    })
    assert raw_denied.status_code == 403
    print("✅ 40-Domain / 60-References 直接写入均已拦截")

    print("\n=== 4. OCC 并发控制 ===")
    scratch = "90-AI-Workspace/drafts/__system_check__.md"
    scratch_file = VAULT_ROOT / scratch
    if scratch_file.exists():
        scratch_file.unlink()
    created = client.post("/mcp/vault_patch", json={
        "path": scratch,
        "content": "# OCC\n",
        "ifMatch": "NEW",
    })
    assert created.status_code == 200
    v1 = created.json()["version"]
    updated = client.post("/mcp/vault_patch", json={
        "path": scratch,
        "content": "# OCC\nA\n",
        "ifMatch": v1,
    })
    assert updated.status_code == 200
    stale = client.post("/mcp/vault_patch", json={
        "path": scratch,
        "content": "# OCC\nB\n",
        "ifMatch": v1,
    })
    assert stale.status_code == 412
    scratch_file.unlink(missing_ok=True)
    print("✅ 过期版本已被 412 拦截")

    print("\n=== 5. 检索 / 巡检 / 索引 ===")
    search = client.post("/mcp/vault_search", json={
        "query": "OCC",
        "folder": "40-Domain",
        "limit": 5,
    })
    assert search.status_code == 200
    unresolved = client.get("/mcp/vault_list_unresolved")
    assert unresolved.status_code == 200
    orphans = client.get("/mcp/vault_find_orphans")
    assert orphans.status_code == 200
    pending = client.get("/mcp/vault_compile_pending")
    assert pending.status_code == 200
    print(
        f"✅ search={search.json()['total']}, "
        f"broken={unresolved.json()['total_broken']}, "
        f"orphans={orphans.json()['total_orphans']}, "
        f"pending={pending.json()['total']}"
    )

    print("\n🎉 NexusMind 核心知识库能力自检通过")


if __name__ == "__main__":
    run_tests()
