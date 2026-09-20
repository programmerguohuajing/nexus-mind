import subprocess
from datetime import date
from pathlib import Path

from nexusmind.core.git_activity import (
    collect_repository,
    discover_repositories,
    load_workflow_config,
    save_workflow_config,
    sync_git_activity,
)


def _run(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _make_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.name", "Tester")
    _run(repo, "config", "user.email", "tester@example.com")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(
        repo,
        "-c", "user.name=Tester",
        "-c", "user.email=tester@example.com",
        "commit", "-m", "feat: initial commit",
    )
    _run(repo, "tag", "v0.1.0")
    return repo


def test_discover_and_sync_git_activity(tmp_path):
    workspace = tmp_path / "workspace"
    vault = tmp_path / "vault"
    workspace.mkdir()
    vault.mkdir()
    repo = _make_repo(workspace, "demo-repo")

    repos = discover_repositories([workspace])
    assert repos == [repo]

    first = sync_git_activity(day=date.today(), roots=[workspace], vault_root=vault)
    assert first["repository_count"] == 1
    assert first["commit_count"] == 1
    assert first["tag_count"] == 1

    daily = vault / first["daily_log"]
    assert daily.exists()
    text = daily.read_text(encoding="utf-8")
    assert "Git 工作活动（自动采集）" in text
    assert "demo-repo" in text
    assert "feat: initial commit" in text
    assert "v0.1.0" in text
    assert text.count("nexusmind:git-activity:start") == 1

    second = sync_git_activity(day=date.today(), roots=[workspace], vault_root=vault)
    text2 = daily.read_text(encoding="utf-8")
    assert second["commit_count"] == 1
    assert text2.count("nexusmind:git-activity:start") == 1

    project_note = vault / "20-Projects/Repositories/demo-repo/Repository-Activity.md"
    assert project_note.exists()
    assert "feat: initial commit" in project_note.read_text(encoding="utf-8")


def test_empty_config_scans_nothing(tmp_path, monkeypatch):
    config_path = tmp_path / "workflow-config.json"
    monkeypatch.setattr("nexusmind.core.git_activity.WORKFLOW_CONFIG_PATH", config_path)
    workspace = tmp_path / "workspace"
    vault = tmp_path / "vault"
    workspace.mkdir()
    vault.mkdir()
    _make_repo(workspace, "repo-a")

    assert load_workflow_config() == {"targets": []}
    result = sync_git_activity(vault_root=vault)
    assert result["configured"] is False
    assert result["repository_count"] == 0
    assert result["daily_log"] is None
    assert not (vault / "30-Logs").exists()


def test_exact_repository_config_only_collects_selected_repo(tmp_path, monkeypatch):
    config_path = tmp_path / "workflow-config.json"
    monkeypatch.setattr("nexusmind.core.git_activity.WORKFLOW_CONFIG_PATH", config_path)
    workspace = tmp_path / "workspace"
    vault = tmp_path / "vault"
    workspace.mkdir()
    vault.mkdir()
    repo_a = _make_repo(workspace, "repo-a")
    _make_repo(workspace, "repo-b")

    saved = save_workflow_config([
        {"type": "repository", "path": str(repo_a), "enabled": True}
    ])
    assert len(saved["targets"]) == 1

    result = sync_git_activity(vault_root=vault)
    assert result["configured"] is True
    assert result["repository_count"] == 1
    assert result["repositories"][0]["name"] == "repo-a"


def test_directory_target_can_be_git_repository_itself(tmp_path):
    workspace = tmp_path / "workspace"
    vault = tmp_path / "vault"
    workspace.mkdir()
    vault.mkdir()
    repo = _make_repo(workspace, "repo-self")

    result = sync_git_activity(
        day=date.today(),
        targets=[{"type": "directory", "path": str(repo), "enabled": True}],
        vault_root=vault,
    )
    assert result["repository_count"] == 1
    assert result["repositories"][0]["name"] == "repo-self"


def test_collect_repository_keeps_all_users_git_log(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = _make_repo(workspace, "team-repo")

    (repo / "other.txt").write_text("other\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(
        repo,
        "-c", "user.name=Other User",
        "-c", "user.email=other@example.com",
        "commit", "-m", "feat: other user work",
    )
    _run(repo, "tag", "v0.2.0")

    snapshot = collect_repository(repo, day=date.today())
    assert snapshot["current_user"]["name"] == "Tester"
    assert snapshot["current_user"]["email"] == "tester@example.com"
    assert snapshot["current_user_identified"] is True
    assert snapshot["commit_count"] == 2
    assert {item["author_email"] for item in snapshot["commits"]} == {
        "tester@example.com",
        "other@example.com",
    }
    assert snapshot["tag_count"] == 2
    assert {item["name"] for item in snapshot["tags"]} == {"v0.1.0", "v0.2.0"}


def test_collection_does_not_depend_on_repository_user_identity(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = workspace / "no-user"
    repo.mkdir()
    _run(repo, "init")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(
        repo,
        "-c", "user.name=Other User",
        "-c", "user.email=other@example.com",
        "commit", "-m", "feat: team work",
    )

    snapshot = collect_repository(repo, day=date.today())
    assert snapshot["commit_count"] == 1
    assert snapshot["commits"][0]["author_email"] == "other@example.com"


def test_collect_repository_pulls_latest_remote_commits_before_collecting(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    source = tmp_path / "source"
    source.mkdir()
    _run(source, "init")
    _run(source, "config", "user.name", "Tester")
    _run(source, "config", "user.email", "tester@example.com")
    (source / "README.md").write_text("one\n", encoding="utf-8")
    _run(source, "add", ".")
    _run(source, "commit", "-m", "feat: first")
    _run(source, "remote", "add", "origin", str(remote))
    _run(source, "push", "-u", "origin", "HEAD")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True, text=True)
    _run(clone, "config", "user.name", "Clone User")
    _run(clone, "config", "user.email", "clone@example.com")

    (source / "second.txt").write_text("two\n", encoding="utf-8")
    _run(source, "add", ".")
    _run(
        source,
        "-c", "user.name=Other User",
        "-c", "user.email=other@example.com",
        "commit", "-m", "feat: remote teammate commit",
    )
    _run(source, "push")

    snapshot = collect_repository(clone, day=date.today())

    assert snapshot["pull"]["attempted"] is True
    assert snapshot["pull"]["success"] is True
    assert any(
        item["subject"] == "feat: remote teammate commit"
        and item["author_email"] == "other@example.com"
        for item in snapshot["commits"]
    )
