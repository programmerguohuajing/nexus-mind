from pathlib import Path

from fastapi.testclient import TestClient

from nexusmind.api.server import app

client = TestClient(app)


def test_directory_browser_lists_subfolders_and_git_marker(tmp_path):
    normal = tmp_path / "normal"
    repo = tmp_path / "repo"
    normal.mkdir()
    repo.mkdir()
    (repo / ".git").mkdir()

    response = client.get("/api/fs/directories", params={"path": str(tmp_path)})
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(tmp_path.resolve())

    items = {item["name"]: item for item in body["directories"]}
    assert items["normal"]["is_git"] is False
    assert items["repo"]["is_git"] is True
    assert items["repo"]["path"] == str(repo.resolve())


def test_workflow_config_accepts_multiple_selected_folders(tmp_path, monkeypatch):
    config_path = tmp_path / "workflow-config.json"
    monkeypatch.setattr("nexusmind.core.git_activity.WORKFLOW_CONFIG_PATH", config_path)

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    response = client.put("/api/workflow/config", json={
        "targets": [
            {"type": "directory", "path": str(first), "enabled": True},
            {"type": "directory", "path": str(second), "enabled": True},
        ]
    })
    assert response.status_code == 200
    targets = response.json()["targets"]
    assert len(targets) == 2
    assert {item["path"] for item in targets} == {
        str(first.resolve()),
        str(second.resolve()),
    }
