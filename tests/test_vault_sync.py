from __future__ import annotations

import hashlib
from pathlib import Path

import nexusmind.core.vault_sync as vault_sync


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeCloudClient:
    def __init__(self, notes: dict[str, str], tombstones=None):
        self.notes = notes
        self.tombstones = tombstones or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
    def get(self, url, headers=None):
        assert url.endswith("/api/cloud/vault/manifest")
        return FakeResponse({
            "notes": [
                {"path": path, "version": _hash(content), "updated_at": "now"}
                for path, content in sorted(self.notes.items())
            ],
            "tombstones": [
                {"path": path, "version": version, "deleted_at": "now"}
                for path, version in sorted(self.tombstones.items())
            ],
        })

    def post(self, url, headers=None, json=None):
        if url.endswith("/api/cloud/vault/pull"):
            return FakeResponse({
                "notes": [
                    {
                        "path": path,
                        "content": self.notes[path],
                        "version": _hash(self.notes[path]),
                    }
                    for path in json["paths"]
                    if path in self.notes
                ]
            })
        assert url.endswith("/api/cloud/vault/push")
        results = []
        for item in json["notes"]:
            path = item["path"]
            current = self.notes.get(path)
            current_version = _hash(current) if current is not None else None
            base = item.get("base_version")
            if current is not None and base != current_version:
                results.append({
                    "path": path, "status": "conflict", "operation": "upsert",
                    "remote_version": current_version,
                })
                continue
            self.notes[path] = item["content"]
            self.tombstones.pop(path, None)
            results.append({
                "path": path, "status": "success", "operation": "upsert",
                "version": _hash(item["content"]),
            })
        for item in json["deletions"]:
            path = item["path"]
            current = self.notes.get(path)
            current_version = _hash(current) if current is not None else None
            if current is not None and item.get("base_version") != current_version:
                results.append({
                    "path": path, "status": "conflict", "operation": "delete",
                    "remote_version": current_version,
                })
                continue
            self.notes.pop(path, None)
            version = "deleted-" + path
            self.tombstones[path] = version
            results.append({
                "path": path, "status": "success", "operation": "delete",
                "version": version,
            })
        return FakeResponse({"results": results})


def _run(monkeypatch, tmp_path: Path, client: FakeCloudClient):
    monkeypatch.setattr(vault_sync.httpx, "Client", lambda timeout: client)
    return vault_sync.sync_vault_bidirectional(
        vault_root=tmp_path / "vault",
        data_root=tmp_path,
        cloud_url="https://cloud.example",
        cloud_token="token",
    )


def test_first_sync_uploads_local_and_downloads_cloud(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "local.md").write_text("local", encoding="utf-8")
    client = FakeCloudClient({"cloud.md": "cloud"})

    result = _run(monkeypatch, tmp_path, client)

    assert result["success"] is True
    assert result["uploaded"] == 1
    assert result["downloaded"] == 1
    assert client.notes["local.md"] == "local"
    assert (vault / "cloud.md").read_text(encoding="utf-8") == "cloud"
def test_second_sync_propagates_local_and_cloud_edits(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "same.md").write_text("v1", encoding="utf-8")
    client = FakeCloudClient({"same.md": "v1"})
    _run(monkeypatch, tmp_path, client)

    (vault / "same.md").write_text("local-v2", encoding="utf-8")
    result = _run(monkeypatch, tmp_path, client)
    assert result["uploaded"] == 1
    assert client.notes["same.md"] == "local-v2"

    client.notes["same.md"] = "cloud-v3"
    result = _run(monkeypatch, tmp_path, client)
    assert result["downloaded"] == 1
    assert (vault / "same.md").read_text(encoding="utf-8") == "cloud-v3"


def test_conflict_preserves_local_and_writes_cloud_copy(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("base", encoding="utf-8")
    client = FakeCloudClient({"note.md": "base"})
    _run(monkeypatch, tmp_path, client)

    (vault / "note.md").write_text("local-change", encoding="utf-8")
    client.notes["note.md"] = "cloud-change"
    result = _run(monkeypatch, tmp_path, client)

    assert result["conflicts"] == 1
    assert (vault / "note.md").read_text(encoding="utf-8") == "local-change"
    conflict_paths = result["conflict_files"]
    assert len(conflict_paths) == 1
    assert Path(conflict_paths[0]).read_text(encoding="utf-8") == "cloud-change"


def test_remote_delete_propagates_when_local_is_unchanged(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("base", encoding="utf-8")
    client = FakeCloudClient({"note.md": "base"})
    _run(monkeypatch, tmp_path, client)

    client.notes.pop("note.md")
    client.tombstones["note.md"] = "deleted-note"
    result = _run(monkeypatch, tmp_path, client)

    assert result["deleted"] == 1
    assert not (vault / "note.md").exists()


def test_local_delete_propagates_to_cloud(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("base", encoding="utf-8")
    client = FakeCloudClient({"note.md": "base"})
    _run(monkeypatch, tmp_path, client)

    (vault / "note.md").unlink()
    result = _run(monkeypatch, tmp_path, client)

    assert result["deleted"] == 1
    assert "note.md" not in client.notes
    assert "note.md" in client.tombstones


def test_first_sync_different_versions_creates_conflict_without_overwrite(
    monkeypatch, tmp_path
):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("local", encoding="utf-8")
    client = FakeCloudClient({"note.md": "cloud"})

    result = _run(monkeypatch, tmp_path, client)

    assert result["conflicts"] == 1
    assert (vault / "note.md").read_text(encoding="utf-8") == "local"
    assert client.notes["note.md"] == "cloud"
    assert Path(result["conflict_files"][0]).read_text(encoding="utf-8") == "cloud"
