from fastapi.testclient import TestClient

from nexusmind.api.server import app
from nexusmind.config import VAULT_ROOT

client = TestClient(app)


def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["version"] == "4.0.0"


def test_api_occ_workflow():
    target = "90-AI-Workspace/drafts/__pytest_occ__.md"
    file_path = VAULT_ROOT / target
    if file_path.exists():
        file_path.unlink()

    created = client.post("/mcp/vault_patch", json={
        "path": target,
        "content": "# OCC Test\n",
        "ifMatch": "NEW",
    })
    assert created.status_code == 200
    version = created.json()["version"]

    first = client.post("/mcp/vault_patch", json={
        "path": target,
        "content": "# OCC Test\nAgent A\n",
        "ifMatch": version,
    })
    assert first.status_code == 200

    stale = client.post("/mcp/vault_patch", json={
        "path": target,
        "content": "# OCC Test\nAgent B stale\n",
        "ifMatch": version,
    })
    assert stale.status_code == 412

    missing_precondition = client.post("/mcp/vault_patch", json={
        "path": target,
        "content": "# no lock\n",
    })
    assert missing_precondition.status_code == 428

    domain_write = client.post("/mcp/vault_patch", json={
        "path": "40-Domain/Architecture/__forbidden__.md",
        "content": "# forbidden\n",
        "ifMatch": "NEW",
    })
    assert domain_write.status_code == 403

    if file_path.exists():
        file_path.unlink()


def test_web_console_and_dashboard():
    root = client.get("/")
    assert root.status_code == 200
    assert "NexusMind" in root.text

    css = client.get("/web/styles.css")
    js = client.get("/web/app.js")
    assert css.status_code == 200
    assert js.status_code == 200

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["status"] == "ok"
    assert data["notes"] >= data["domain_notes"]
    assert "broken_links" in data
    assert "orphans" in data
