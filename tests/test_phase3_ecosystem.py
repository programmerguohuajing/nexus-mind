"""Phase 3 测试：代码平台连接器 / 团队协作 / OKR / 输入管道 / 数据看板 / 远程 MCP。"""
import email as email_lib
from email.mime.text import MIMEText
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexusmind.api import server as server_module
from nexusmind.api.server import app
from nexusmind.core import connectors as connectors_module
from nexusmind.core import feeds as feeds_module
from nexusmind.core import goals as goals_module
from nexusmind.core.analytics import dashboard_analytics, log_search_miss
from nexusmind.core.collab import (
    add_comment,
    create_share,
    list_comments,
    read_share,
    resolve_comment,
    revoke_share,
    space_visible_notes,
    upsert_space,
)
from nexusmind.core.connectors import sync_github_repo, sync_gitlab_project
from nexusmind.core.feeds import poll_email_inbox, poll_feeds
from nexusmind.core.goals import (
    add_key_result,
    compute_progress,
    create_objective,
    goals_review_section,
    update_key_result_current,
)

client = TestClient(app)


def _write(vault: Path, rel: str, content: str):
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------- GitHub / GitLab 连接器 ----------------

def _github_router(url, headers=None):
    if "/pulls?" in url:
        return [{
            "number": 7, "title": "支付回调重试", "state": "closed", "merged_at": "2026-10-20T10:00:00Z",
            "user": {"login": "jing"}, "html_url": "https://github.com/o/r/pull/7",
            "created_at": "2026-10-19T09:00:00Z", "updated_at": "2026-10-20T10:00:00Z",
            "labels": [{"name": "payment"}], "body": "增加重试队列",
        }]
    if "/issues/7/comments" in url:
        return [{"body": "知识点：回调接口必须做幂等校验，否则重试会重复入账。", "user": {"login": "reviewer"}}]
    if "/issues?" in url:
        return [{
            "number": 3, "title": "超时无提示", "state": "open",
            "user": {"login": "qa"}, "html_url": "https://github.com/o/r/issues/3",
            "created_at": "2026-10-18T09:00:00Z", "updated_at": "2026-10-18T10:00:00Z",
            "labels": [], "body": "支付超时页面白屏",
        }]
    if "/issues/3/comments" in url:
        return []
    raise AssertionError(f"unexpected url: {url}")


def test_github_sync_incremental_and_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(connectors_module, "_get_json", _github_router)
    first = sync_github_repo("o", "r", token="t", vault_root=tmp_path)
    total_synced = sum(r["synced"] for r in first["results"])
    assert total_synced == 2
    candidates = [c for r in first["results"] for c in r["knowledge_candidates"]]
    assert len(candidates) == 1 and candidates[0]["number"] == 7
    raw_notes = list((tmp_path / "60-References/CodePlatform").rglob("*.md"))
    assert len(raw_notes) == 2

    second = sync_github_repo("o", "r", token="t", vault_root=tmp_path)
    assert sum(r["synced"] for r in second["results"]) == 0
    assert sum(r["skipped"] for r in second["results"]) == 2


def test_gitlab_sync(tmp_path, monkeypatch):
    def router(url, headers=None):
        if "merge_requests?" in url:
            return [{
                "iid": 5, "title": "修复缓存击穿", "state": "merged",
                "author": {"username": "jing"}, "web_url": "https://gitlab.example.com/g/p/-/merge_requests/5",
                "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-02T00:00:00Z",
                "merged_at": "2026-10-02T00:00:00Z", "labels": ["cache"], "description": "互斥锁方案",
            }]
        if "merge_requests/5/notes" in url:
            return [{"body": "系统通知", "author": {"username": "bot"}, "system": True}]
        if "issues?" in url:
            return []
        raise AssertionError(url)

    monkeypatch.setattr(connectors_module, "_get_json", router)
    result = sync_gitlab_project("g/p", base_url="https://gitlab.example.com", vault_root=tmp_path)
    assert sum(r["synced"] for r in result["results"]) == 1


def test_connectors_config_api_sanitizes_token(tmp_path, monkeypatch):
    cfg_path = tmp_path / "connectors-config.json"
    monkeypatch.setattr(connectors_module, "CONNECTORS_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(server_module, "load_connectors_config", lambda: connectors_module.load_connectors_config(cfg_path))
    monkeypatch.setattr(server_module, "save_connectors_config", lambda data: connectors_module.save_connectors_config(data, cfg_path))
    payload = {"github": {"token": "ghp_secret", "repos": [{"owner": "o", "repo": "r"}]},
               "gitlab": {"base_url": "https://gitlab.com", "token": "", "projects": []}}
    saved = client.post("/api/connectors", json=payload)
    assert saved.status_code == 200
    assert saved.json()["github"]["token"] == "******"
    # 用 ****** 回存不应清掉真实 token
    client.post("/api/connectors", json=saved.json())
    assert connectors_module.load_connectors_config(cfg_path)["github"]["token"] == "ghp_secret"


# ---------------- 团队协作 ----------------

def test_comments_mentions_resolve(tmp_path):
    _write(tmp_path, "40-Domain/Pay/卡.md", "# 卡\n\n正文。")
    result = add_comment("40-Domain/Pay/卡.md", "jing", "@张三 这里有个坑，帮忙确认", vault_root=tmp_path)
    assert result["comment"]["mentions"] == ["张三"]
    listing = list_comments("40-Domain/Pay/卡.md", vault_root=tmp_path)
    assert listing["total"] == 1
    resolved = resolve_comment("40-Domain/Pay/卡.md", result["comment"]["id"], vault_root=tmp_path)
    assert resolved["comment"]["resolved"] is True


def test_share_with_password_and_revoke(tmp_path):
    _write(tmp_path, "40-Domain/Pay/分享.md", "---\ntitle: 分享卡\n---\n\n# 分享卡\n\n内容。")
    share = create_share("40-Domain/Pay/分享.md", password="s3cret", vault_root=tmp_path)
    with pytest.raises(PermissionError):
        read_share(share["token"], vault_root=tmp_path)
    opened = read_share(share["token"], password="s3cret", vault_root=tmp_path)
    assert opened["title"] == "分享卡"
    revoke_share(share["token"], vault_root=tmp_path)
    with pytest.raises(FileNotFoundError):
        read_share(share["token"], password="s3cret", vault_root=tmp_path)


def test_space_visibility(tmp_path):
    _write(tmp_path, "40-Domain/Pay/a.md", "# A")
    _write(tmp_path, "40-Domain/Pay/b.md", "# B")
    upsert_space("支付组", folders=["40-Domain/Pay"], visibility="private", members=["jing"], vault_root=tmp_path)
    member_view = space_visible_notes("支付组", member="jing", vault_root=tmp_path)
    assert member_view["total"] == 2
    outsider_view = space_visible_notes("支付组", member="other", vault_root=tmp_path)
    assert outsider_view["total"] == 0


# ---------------- OKR ----------------

def test_goals_progress_and_review_section(tmp_path):
    data_path = tmp_path / "goals.json"
    objective = create_objective("提升支付稳定性", period="2026-Q4", data_path=data_path)
    kr_manual = add_key_result(objective["id"], "线上事故清零", target=4, data_path=data_path)
    update_key_result_current(objective["id"], kr_manual["id"], 2, data_path=data_path)

    _write(tmp_path, "40-Domain/Pay/a.md", "# A")
    _write(tmp_path, "40-Domain/Pay/b.md", "# B")
    _write(tmp_path, "40-Domain/Pay/c.md", "# C")
    add_key_result(objective["id"], "支付域知识卡片", target=6, unit="张",
                   source={"type": "notes_count", "folder": "40-Domain/Pay"}, data_path=data_path)

    progress = compute_progress(vault_root=tmp_path, data_path=data_path)
    obj = progress["objectives"][0]
    by_title = {kr["title"]: kr for kr in obj["key_results"]}
    assert by_title["线上事故清零"]["progress"] == 0.5
    assert by_title["支付域知识卡片"]["measured"] == 3
    assert by_title["支付域知识卡片"]["progress"] == 0.5

    section = goals_review_section(vault_root=tmp_path, data_path=data_path)
    assert "目标进展" in section["section"]
    assert "支付域知识卡片" in section["section"]

    # API 层（goals 数据路径指向同一文件）
    monkeypatch_path = data_path
    original = goals_module.GOALS_DATA_PATH
    goals_module.GOALS_DATA_PATH = monkeypatch_path
    try:
        resp = client.get("/api/goals/progress")
        assert resp.status_code == 200
        assert resp.json()["objectives"][0]["title"] == "提升支付稳定性"
    finally:
        goals_module.GOALS_DATA_PATH = original


# ---------------- 输入管道 ----------------

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Tech Blog</title>
<item><title>第一篇</title><link>https://blog.example.com/1</link><guid>g1</guid><description>摘要一</description></item>
<item><title>第二篇</title><link>https://blog.example.com/2</link><guid>g2</guid><description>摘要二</description></item>
</channel></rss>""".encode("utf-8")


def test_rss_poll_dedupes(tmp_path):
    config_path = tmp_path / "feeds-config.json"
    config_path.write_text(
        '{"feeds": [{"id": "blog", "name": "Tech Blog", "url": "https://blog.example.com/feed", "enabled": true}], "email": null}',
        encoding="utf-8",
    )
    feeds_module._fetch = lambda url: _RSS_XML  # type: ignore[attr-defined]
    try:
        first = poll_feeds(vault_root=tmp_path, config_path=config_path)
        assert first["total_added"] == 2
        second = poll_feeds(vault_root=tmp_path, config_path=config_path)
        assert second["total_added"] == 0
    finally:
        del feeds_module._fetch


class _FakeIMAP:
    def __init__(self, host, port):
        self.host = host

    def login(self, user, password):
        return "OK", []

    def select(self, mailbox):
        return "OK", []

    def search(self, charset, criterion):
        return "OK", [b"1"]

    def fetch(self, num, spec):
        msg = MIMEText("这是一封转发的技术邮件正文。", "plain", "utf-8")
        msg["Subject"] = "转发：支付方案评审"
        msg["From"] = "lead@example.com"
        return "OK", [(b"1 (RFC822)", msg.as_bytes())]

    def store(self, num, flags, value):
        return "OK", []

    def logout(self):
        return "BYE", []


def test_email_poll_ingests_unseen(tmp_path, monkeypatch):
    config_path = tmp_path / "feeds-config.json"
    config_path.write_text(
        '{"feeds": [], "email": {"imap_host": "imap.example.com", "imap_user": "me@example.com", "password_env": "TEST_IMAP_PW"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_IMAP_PW", "pw")
    monkeypatch.setattr(feeds_module.imaplib, "IMAP4_SSL", _FakeIMAP)
    result = poll_email_inbox(vault_root=tmp_path, config_path=config_path)
    assert result["added"] == 1
    notes = list((tmp_path / "60-References/Email").rglob("*.md"))
    assert len(notes) == 1
    assert "支付方案评审" in notes[0].read_text(encoding="utf-8")


# ---------------- 数据看板 ----------------

def test_analytics_dashboard(tmp_path):
    _write(tmp_path, "40-Domain/Pay/被引用.md", "# 被引用卡片\n\n核心内容。")
    _write(tmp_path, "40-Domain/Pay/引用者一.md", "# 一\n\n参见 [[40-Domain/Pay/被引用]]。")
    _write(tmp_path, "40-Domain/Cache/引用者二.md", "# 二\n\n也参见 [[被引用]] 以及标签 #缓存 。")
    log_search_miss("如何配置单点登录", vault_root=tmp_path)
    log_search_miss("如何配置单点登录", vault_root=tmp_path)
    log_search_miss("蓝牙配对失败", vault_root=tmp_path)

    data = dashboard_analytics(vault_root=tmp_path)
    assert data["total_notes"] == 3
    assert data["top_referenced"][0]["path"] == "40-Domain/Pay/被引用.md"
    assert data["top_referenced"][0]["references"] == 2
    assert data["search_misses"][0] == {"query": "如何配置单点登录", "count": 2}
    assert len(data["growth"]) == 8
    assert "broken_links" in data["health"]


# ---------------- 远程 MCP ----------------

def _rpc(payload, headers=None):
    return client.post("/mcp-rpc", json=payload, headers=headers or {})


def test_remote_mcp_protocol_and_scopes(monkeypatch):
    monkeypatch.setenv("NEXUSMIND_API_TOKEN", "full-token")
    monkeypatch.setenv("NEXUSMIND_MCP_READONLY_TOKEN", "ro-token")

    no_token = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert no_token.status_code == 401

    init = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"Authorization": "Bearer full-token"})
    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "nexusmind-mcp-remote"
    assert init.json()["result"]["scope"] == "full"

    full_list = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, {"Authorization": "Bearer full-token"})
    full_names = {t["name"] for t in full_list.json()["result"]["tools"]}
    assert "vault_patch" in full_names and "vault_ask" in full_names

    ro_list = _rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, {"X-NexusMind-Token": "ro-token"})
    ro_names = {t["name"] for t in ro_list.json()["result"]["tools"]}
    assert "vault_ask" in ro_names and "vault_patch" not in ro_names

    ro_write = _rpc(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "vault_patch", "arguments": {"path": "x.md", "content": "y"}}},
        {"X-NexusMind-Token": "ro-token"},
    )
    assert ro_write.json()["error"]["code"] == -32001

    unknown = _rpc({"jsonrpc": "2.0", "id": 5, "method": "nope"}, {"Authorization": "Bearer full-token"})
    assert unknown.json()["error"]["code"] == -32601
