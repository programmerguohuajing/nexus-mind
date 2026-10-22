"""Phase 1 前端资产与剪藏扩展测试：PWA 资源可达、扩展清单合法。"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from nexusmind.api.server import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_pwa_assets_are_served():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "application/manifest+json" in manifest.headers.get("content-type", "")
    data = manifest.json()
    assert data["start_url"] == "/m"
    assert data["display"] == "standalone"

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "nexusmind-v1" in sw.text

    mobile = client.get("/m")
    assert mobile.status_code == 200
    assert "移动速记" in mobile.text or "快速记录" in mobile.text
    assert "vault_ingest" in mobile.text

    extras = client.get("/extras.js")
    assert extras.status_code == 200
    assert "问知识" in extras.text
    assert "/api/ask" in extras.text

    index = client.get("/")
    assert "/manifest.webmanifest" in index.text
    assert "/extras.js" in index.text


def test_web_clipper_extension_files():
    ext_dir = ROOT / "extensions" / "web-clipper"
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["background"]["service_worker"] == "background.js"
    for name in ("background.js", "clipper.js", "popup.html", "popup.js", "options.html", "README.md"):
        assert (ext_dir / name).is_file(), name
    clipper = (ext_dir / "clipper.js").read_text(encoding="utf-8")
    assert "/api/web-ingest" in clipper
    assert "/mcp/vault_ingest" in clipper
    background = (ext_dir / "background.js").read_text(encoding="utf-8")
    assert "contextMenus" in background
