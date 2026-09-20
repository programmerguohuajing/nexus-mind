from fastapi.testclient import TestClient

from nexusmind.api.server import app


client = TestClient(app)


def test_local_web_static_assets_are_served_from_root_paths():
    expected = {
        "/": "text/html",
        "/styles.css": "text/css",
        "/app.js": "javascript",
        "/favicon.ico": "image/",
        "/assets/nexusmind-agent.svg": "image/svg+xml",
    }
    for path, content_type in expected.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert content_type in response.headers.get("content-type", ""), path
        assert response.content, path


def test_local_asset_route_rejects_path_escape():
    response = client.get("/assets/../index.html")
    assert response.status_code in {400, 404}
