import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from nexusmind.api.server import app
from nexusmind.core.compiler import compile_wiki_card
from nexusmind.core.notification import (
    _gen_dingtalk_url,
    _gen_feishu_signature,
    load_notification_config,
    sanitize_channel_config,
    save_notification_config,
    send_notification,
    test_notification_channel,
)
from nexusmind.core.review import generate_weekly_review

client = TestClient(app)


def test_notification_config_save_load_and_sanitize(tmp_path: Path):
    config_file = tmp_path / "notification-config.json"
    assert load_notification_config(config_file) == {"default_channel_id": None, "channels": []}

    channels = [
        {
            "id": "feishu_main",
            "name": "飞书通知群",
            "type": "feishu",
            "enabled": True,
            "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "secret": "my_secret_key",
        },
        {
            "id": "dingtalk_dev",
            "name": "钉钉开发群",
            "type": "dingtalk",
            "enabled": True,
            "url": "https://oapi.dingtalk.com/robot/send?access_token=test",
            "secret": "ding_secret",
        },
    ]

    save_notification_config(channels, default_channel_id="feishu_main", config_path=config_file)

    loaded = load_notification_config(config_file)
    assert loaded["default_channel_id"] == "feishu_main"
    assert len(loaded["channels"]) == 2
    assert loaded["channels"][0]["secret"] == "my_secret_key"

    sanitized = [sanitize_channel_config(c) for c in loaded["channels"]]
    assert sanitized[0]["secret"] == "******"
    assert sanitized[1]["secret"] == "******"


def test_signature_helpers():
    feishu_sig = _gen_feishu_signature("test_secret", 1600000000)
    assert isinstance(feishu_sig, str) and len(feishu_sig) > 0

    ding_url = _gen_dingtalk_url("https://oapi.dingtalk.com/robot/send?access_token=xyz", "sec_123")
    assert "timestamp=" in ding_url and "sign=" in ding_url


@patch("httpx.post")
def test_send_notification_feishu_mock(mock_post, tmp_path: Path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"code": 0, "msg": "success"}
    mock_post.return_value = mock_resp

    config_file = tmp_path / "notification-config.json"
    save_notification_config(
        [
            {
                "id": "feishu_test",
                "name": "飞书测试",
                "type": "feishu",
                "enabled": True,
                "url": "https://open.feishu.cn/open-apis/bot/v2/hook/mock",
                "secret": "sec",
            }
        ],
        config_path=config_file,
    )

    res = send_notification("测试标题", "测试正文", channel_ids=["feishu_test"], config_path=config_file)
    assert res["status"] == "success"
    assert res["sent_count"] == 1
    assert mock_post.called


@patch("httpx.post")
def test_test_notification_channel(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
    mock_post.return_value = mock_resp

    ch = {
        "id": "dingtalk_test",
        "name": "钉钉",
        "type": "dingtalk",
        "url": "https://oapi.dingtalk.com/robot/send?access_token=test",
    }

    res = test_notification_channel(ch)
    assert res["status"] == "success"


@patch("nexusmind.core.review.send_notification")
def test_review_generate_with_push_channels(mock_send, tmp_path: Path):
    for folder in (
        "00-Meta",
        "20-Projects/Sample",
        "40-Domain/00-Index",
        "60-References/Articles",
        "90-AI-Workspace/reviews",
    ):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    (tmp_path / "00-Meta/COMPILATION-LOG.md").write_text("# Log\n", encoding="utf-8")

    mock_send.return_value = {"status": "success", "sent_count": 1, "failed_count": 0}

    res = generate_weekly_review("2026-W38", vault_root=tmp_path, push_channels=["feishu_main"])
    assert res["status"] == "review_generated"
    assert res["notification_result"] == {"status": "success", "sent_count": 1, "failed_count": 0}
    assert mock_send.called


@patch("nexusmind.core.compiler.send_notification")
def test_compile_wiki_card_with_push_channels(mock_send, tmp_path: Path):
    ref_dir = tmp_path / "60-References" / "Articles"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "src.md").write_text("# Raw Source\nContent", encoding="utf-8")

    domain_dir = tmp_path / "40-Domain" / "Architecture"
    domain_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "00-Meta").mkdir(parents=True, exist_ok=True)

    mock_send.return_value = {"status": "success", "sent_count": 1}

    res = compile_wiki_card(
        ["60-References/Articles/src.md"],
        "40-Domain/Architecture/card.md",
        "# Card Content",
        vault_root=tmp_path,
        push_channels=["dingtalk_dev"],
    )

    assert res["status"] == "compiled_successfully"
    assert res["notification_result"]["status"] == "success"
    assert mock_send.called


def test_notification_api_routes():
    res = client.get("/api/notifications/channels")
    assert res.status_code == 200
    assert "channels" in res.json()

    save_payload = {
        "default_channel_id": "generic_hook",
        "channels": [
            {
                "id": "generic_hook",
                "name": "通用 Hook",
                "type": "webhook",
                "enabled": True,
                "url": "https://example.com/hook",
            },
            {
                "id": "feishu_app_channel",
                "name": "飞书自建应用",
                "type": "feishu",
                "feishu_mode": "app",
                "app_id": "cli_mock123",
                "app_secret": "sec_mock456",
                "receive_id": "ou_user789",
                "receive_id_type": "open_id",
                "enabled": True,
            },
        ],
    }

    update_res = client.post("/api/notifications/channels", json=save_payload)
    assert update_res.status_code == 200
    assert update_res.json()["default_channel_id"] == "generic_hook"
    channels = update_res.json()["channels"]
    feishu_ch = next(c for c in channels if c["id"] == "feishu_app_channel")
    assert feishu_ch["app_secret"] == "******"
    assert feishu_ch["app_id"] == "cli_mock123"


@patch("httpx.post")
def test_send_notification_feishu_app_mode(mock_post, tmp_path: Path):
    auth_resp = MagicMock()
    auth_resp.status_code = 200
    auth_resp.headers = {"content-type": "application/json"}
    auth_resp.json.return_value = {"code": 0, "msg": "ok", "tenant_access_token": "t-app-token-123"}

    msg_resp = MagicMock()
    msg_resp.status_code = 200
    msg_resp.headers = {"content-type": "application/json"}
    msg_resp.json.return_value = {"code": 0, "msg": "success", "data": {"message_id": "om_test999"}}

    mock_post.side_effect = [auth_resp, msg_resp]

    config_file = tmp_path / "notification-config.json"
    save_notification_config(
        [
            {
                "id": "feishu_app_test",
                "name": "飞书自建应用通知",
                "type": "feishu",
                "feishu_mode": "app",
                "app_id": "cli_test_app",
                "app_secret": "test_app_secret",
                "receive_id": "oc_test_chat_id",
                "receive_id_type": "chat_id",
                "enabled": True,
            }
        ],
        config_path=config_file,
    )

    res = send_notification("自建应用通知", "这是测试内容", channel_ids=["feishu_app_test"], config_path=config_file)
    assert res["status"] == "success"
    assert res["sent_count"] == 1
    assert mock_post.call_count == 2

    # Check token call
    first_call_args, first_call_kwargs = mock_post.call_args_list[0]
    assert "tenant_access_token/internal" in first_call_args[0]
    assert first_call_kwargs["json"]["app_id"] == "cli_test_app"

    # Check message call
    second_call_args, second_call_kwargs = mock_post.call_args_list[1]
    assert "open-apis/im/v1/messages" in second_call_args[0]
    assert "Bearer t-app-token-123" in second_call_kwargs["headers"]["Authorization"]
    assert second_call_kwargs["json"]["receive_id"] == "oc_test_chat_id"
    assert "post" in second_call_kwargs["json"]["msg_type"]

