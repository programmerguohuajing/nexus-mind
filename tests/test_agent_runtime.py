from __future__ import annotations

import threading
from pathlib import Path

from nexusmind.agent.configuration import AgentConfig, AgentConfigStore
from nexusmind.agent.runtime import AgentSupervisor, runtime_environment


def test_agent_config_store_round_trip(tmp_path):
    store = AgentConfigStore(tmp_path / "agent.json")
    config = AgentConfig(
        folders=[str(tmp_path), str(tmp_path)],
        local_api_enabled=False,
        cloud_url="https://example.workers.dev/",
        cloud_token="secret",
        sync_interval=30,
        data_root=str(tmp_path / "data"),
    )
    saved = store.save(config)
    loaded = store.load()

    assert saved.sync_interval == 60
    assert loaded.folders == [str(tmp_path.resolve())]
    assert loaded.cloud_url == "https://example.workers.dev"
    assert loaded.cloud_token == "secret"


def test_runtime_environment_uses_agent_configuration(tmp_path):
    config = AgentConfig(
        local_api_host="0.0.0.0",
        local_api_port=9123,
        data_root=str(tmp_path / "data"),
        cloud_url="https://cloud.example",
        cloud_token="token-1",
        sync_interval=120,
    ).normalized()
    env = runtime_environment(config)

    assert env["NEXUSMIND_DATA_ROOT"] == str((tmp_path / "data").resolve())
    assert env["NEXUSMIND_HOST"] == "0.0.0.0"
    assert env["NEXUSMIND_PORT"] == "9123"
    assert env["NEXUSMIND_CLOUD_SYNC_URL"] == "https://cloud.example"
    assert env["NEXUSMIND_CLOUD_SYNC_TOKEN"] == "token-1"


def test_supervisor_supports_repeated_hot_apply(tmp_path, monkeypatch):
    store = AgentConfigStore(tmp_path / "agent.json")
    store.save(AgentConfig(local_api_enabled=False, data_root=str(tmp_path / "data")))
    supervisor = AgentSupervisor(store)

    monkeypatch.setattr(supervisor, "_start_api", lambda: None)
    monkeypatch.setattr(supervisor, "_stop_api", lambda: None)
    monkeypatch.setattr(
        supervisor,
        "_run_loop",
        lambda: supervisor._worker_stop.wait(),
    )

    supervisor.start()
    try:
        first = AgentConfig(
            local_api_enabled=False,
            cloud_url="https://one.example",
            data_root=str(tmp_path / "data"),
            sync_interval=60,
        )
        second = AgentConfig(
            local_api_enabled=False,
            cloud_url="https://two.example",
            data_root=str(tmp_path / "data"),
            sync_interval=180,
        )
        supervisor.apply(first)
        supervisor.apply(second)

        assert supervisor.config.cloud_url == "https://two.example"
        assert supervisor.config.sync_interval == 180
        assert store.load().cloud_url == "https://two.example"
        assert supervisor._watcher is not None
        assert supervisor._watcher.is_alive()
    finally:
        supervisor.stop()
