from pathlib import Path

from fastapi.testclient import TestClient

from nexusmind.api.server import app as local_app
from nexusmind.cloud.app import _week_bounds, app as cloud_app
from nexusmind.core.cloud_sync import _payload


def test_local_runtime_capabilities():
    response = TestClient(local_app).get("/api/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] in {"local", "docker"}
    assert body["capabilities"]["folder_picker"] is True
    assert body["capabilities"]["git_collection"] is True


def test_cloud_runtime_capabilities():
    response = TestClient(cloud_app).get("/api/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "cloudflare"
    assert body["capabilities"]["folder_picker"] is False
    assert body["capabilities"]["cloud_git_ingest"] is True
    assert body["capabilities"]["cloud_vault_sync"] is True


def test_cloud_sync_payload_omits_local_repository_path():
    result = {
        "day": "2026-09-18",
        "synced_at": "2026-09-18 12:00:00",
        "repositories": [{
            "name": "demo",
            "path": r"D:\private\demo",
            "branch": "main",
            "remote": "https://example.com/demo.git",
            "current_user": {"name": "Me", "email": "me@example.com"},
            "commits": [],
            "tags": [],
        }],
    }
    payload = _payload(result)
    assert "path" not in payload["repositories"][0]
    assert payload["repositories"][0]["name"] == "demo"


def test_cloud_week_bounds():
    week, start, end = _week_bounds("2026-W38")
    assert week == "2026-W38"
    assert start.isoformat() == "2026-09-14"
    assert end.isoformat() == "2026-09-20"


def test_cloudflare_files_are_present():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src/worker.py").exists()
    assert (root / "wrangler.example.jsonc").exists()
    migration = (root / "migrations/0001_init.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS notes" in migration
    assert "CREATE TABLE IF NOT EXISTS git_commits" in migration
    assert "CREATE TABLE IF NOT EXISTS cloud_files" in migration
    sync_migration = (root / "migrations/0002_bidirectional_vault_sync.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS sync_tombstones" in sync_migration
    routes = {route.path for route in cloud_app.routes}
    assert "/api/cloud/vault/manifest" in routes
    assert "/api/cloud/vault/pull" in routes
    assert "/api/cloud/vault/push" in routes


def test_brand_assets_and_web_favicon_are_present():
    root = Path(__file__).resolve().parents[1]
    agent_assets = root / "src/nexusmind/agent/assets"
    web_assets = root / "src/nexusmind/web/assets"
    assert (agent_assets / "nexusmind-agent.png").exists()
    assert (agent_assets / "nexusmind-agent.ico").exists()
    assert (agent_assets / "nexusmind-agent.svg").exists()
    assert (web_assets / "nexusmind-agent.svg").exists()
    assert (root / "src/nexusmind/web/favicon.ico").exists()

    index = (root / "src/nexusmind/web/index.html").read_text(encoding="utf-8")
    assert '/favicon.ico' in index
    assert '/assets/nexusmind-agent.svg' in index
