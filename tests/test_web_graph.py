from fastapi.testclient import TestClient

from nexusmind.api.server import app

client = TestClient(app)


def test_graph_resolve_and_canvas_read(tmp_path, monkeypatch):
    domain = tmp_path / "40-Domain"
    domain.mkdir(parents=True)
    (domain / "A.md").write_text(
        "---\ntitle: A\ntags: [graph]\n---\n# A\n[[40-Domain/B|B]]\n",
        encoding="utf-8",
    )
    (domain / "B.md").write_text("# B\n", encoding="utf-8")
    canvas = domain / "map.canvas"
    canvas.write_text(
        '{"nodes":[{"id":"a","file":"40-Domain/A.md","x":0,"y":0,"width":200,"height":100},'
        '{"id":"b","text":"Idea","x":300,"y":0,"width":200,"height":100}],'
        '"edges":[{"id":"e","fromNode":"a","toNode":"b"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr("nexusmind.api.server.VAULT_ROOT", tmp_path)

    graph = client.get("/api/graph", params={"folder": "40-Domain"})
    assert graph.status_code == 200
    body = graph.json()
    assert body["node_count"] == 2
    assert body["edge_count"] == 1
    assert body["edges"][0] == {
        "source": "40-Domain/A.md",
        "target": "40-Domain/B.md",
    }

    resolved = client.get("/api/resolve-link", params={"target": "B"})
    assert resolved.status_code == 200
    assert resolved.json()["path"] == "40-Domain/B.md"

    canvases = client.get("/api/canvases")
    assert canvases.status_code == 200
    assert canvases.json()["total"] == 1
    assert canvases.json()["items"][0]["nodes"] == 2

    canvas_res = client.get("/api/canvas", params={"path": "40-Domain/map.canvas"})
    assert canvas_res.status_code == 200
    assert len(canvas_res.json()["edges"]) == 1


def test_graph_rejects_path_outside_vault(tmp_path, monkeypatch):
    monkeypatch.setattr("nexusmind.api.server.VAULT_ROOT", tmp_path)
    response = client.get("/api/graph", params={"folder": "../"})
    assert response.status_code == 400
