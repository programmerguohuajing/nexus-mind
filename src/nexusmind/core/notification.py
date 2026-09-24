from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from nexusmind.config import NOTIFICATION_CONFIG_PATH

from typing import Any, Dict, List, Optional

VALID_CHANNEL_TYPES = {"feishu", "dingtalk", "email", "webhook"}


def load_notification_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or NOTIFICATION_CONFIG_PATH
    if not path.exists():
        return {"default_channel_id": None, "channels": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"default_channel_id": None, "channels": []}
    channels = data.get("channels", [])
    default_id = data.get("default_channel_id")
    if not isinstance(channels, list):
        channels = []
    return {
        "default_channel_id": str(default_id) if default_id else None,
        "channels": channels,
    }


def sanitize_channel_config(channel: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(channel)
    if "secret" in sanitized and sanitized["secret"]:
        sanitized["secret"] = "******"
    if "app_secret" in sanitized and sanitized["app_secret"]:
        sanitized["app_secret"] = "******"
    if "smtp_pass" in sanitized and sanitized["smtp_pass"]:
        sanitized["smtp_pass"] = "******"
    return sanitized


def save_notification_config(
    channels: List[Dict[str, Any]],
    default_channel_id: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    path = config_path or NOTIFICATION_CONFIG_PATH
    existing_config = load_notification_config(path)
    existing_map = {c.get("id"): c for c in existing_config.get("channels", []) if c.get("id")}

    normalized: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in channels:
        channel_id = str(item.get("id") or "").strip()
        channel_type = str(item.get("type") or "").strip().lower()
        channel_name = str(item.get("name") or channel_id or channel_type).strip()

        if not channel_id:
            raise ValueError("Channel ID (id) cannot be empty")
        if channel_type not in VALID_CHANNEL_TYPES:
            raise ValueError(f"Unsupported channel type: {channel_type}. Allowed: {sorted(VALID_CHANNEL_TYPES)}")
        if channel_id in seen_ids:
            raise ValueError(f"Duplicate channel ID: {channel_id}")
        seen_ids.add(channel_id)

        old_item = existing_map.get(channel_id, {})
        secret = str(item.get("secret") or "").strip()
        if secret == "******":
            secret = str(old_item.get("secret") or "")

        app_secret = str(item.get("app_secret") or "").strip()
        if app_secret == "******":
            app_secret = str(old_item.get("app_secret") or "")

        smtp_pass = str(item.get("smtp_pass") or "").strip()
        if smtp_pass == "******":
            smtp_pass = str(old_item.get("smtp_pass") or "")

        channel_entry: Dict[str, Any] = {
            "id": channel_id,
            "name": channel_name,
            "type": channel_type,
            "enabled": bool(item.get("enabled", True)),
        }

        if channel_type == "feishu":
            is_app_mode = (
                item.get("feishu_mode") == "app"
                or bool(item.get("app_id"))
                or bool(item.get("receive_id"))
            )
            if is_app_mode:
                app_id = str(item.get("app_id") or "").strip()
                receive_id = str(item.get("receive_id") or "").strip()
                receive_id_type = str(item.get("receive_id_type") or "open_id").strip()
                if not app_id:
                    raise ValueError(f"App ID (app_id) is required for Feishu App channel '{channel_name}'")
                if not app_secret:
                    raise ValueError(f"App Secret (app_secret) is required for Feishu App channel '{channel_name}'")
                if not receive_id:
                    raise ValueError(f"Receive ID (receive_id) is required for Feishu App channel '{channel_name}'")
                channel_entry["feishu_mode"] = "app"
                channel_entry["app_id"] = app_id
                channel_entry["app_secret"] = app_secret
                channel_entry["receive_id"] = receive_id
                channel_entry["receive_id_type"] = receive_id_type
            else:
                url = str(item.get("url") or "").strip()
                if not url:
                    raise ValueError(f"Webhook URL or App ID/Secret is required for Feishu channel '{channel_name}'")
                channel_entry["feishu_mode"] = "webhook"
                channel_entry["url"] = url
                if secret:
                    channel_entry["secret"] = secret

        elif channel_type in {"dingtalk", "webhook"}:
            url = str(item.get("url") or "").strip()
            if not url:
                raise ValueError(f"Webhook URL is required for channel '{channel_name}'")
            channel_entry["url"] = url
            if secret:
                channel_entry["secret"] = secret

        if channel_type == "webhook":
            headers = item.get("headers")
            if isinstance(headers, dict):
                channel_entry["headers"] = headers

        if channel_type == "email":
            smtp_host = str(item.get("smtp_host") or "").strip()
            if not smtp_host:
                raise ValueError(f"SMTP host (smtp_host) is required for email channel '{channel_name}'")
            channel_entry["smtp_host"] = smtp_host
            channel_entry["smtp_port"] = int(item.get("smtp_port") or 465)
            channel_entry["smtp_user"] = str(item.get("smtp_user") or "").strip()
            channel_entry["smtp_pass"] = smtp_pass
            channel_entry["use_tls"] = bool(item.get("use_tls", True))
            channel_entry["sender"] = str(item.get("sender") or channel_entry["smtp_user"]).strip()

            recipients = item.get("recipients", [])
            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(",") if r.strip()]
            channel_entry["recipients"] = [str(r).strip() for r in recipients if str(r).strip()]
            if not channel_entry["recipients"]:
                raise ValueError(f"At least one recipient is required for email channel '{channel_name}'")

        normalized.append(channel_entry)

    if default_channel_id and default_channel_id not in seen_ids:
        raise ValueError(f"Default channel ID '{default_channel_id}' does not exist in saved channels")

    payload = {
        "default_channel_id": default_channel_id or (normalized[0]["id"] if normalized else None),
        "channels": normalized,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _gen_feishu_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _gen_dingtalk_url(url: str, secret: str) -> str:
    if not secret:
        return url
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    connector = "&" if "?" in url else "?"
    return f"{url}{connector}timestamp={timestamp}&sign={sign}"


def _http_post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    retries: int = 2,
) -> tuple[int, Dict[str, Any], str]:
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    hdrs.setdefault("Accept", "application/json")
    hdrs.setdefault("User-Agent", "NexusMind/0.3 (+notification-push)")
    hdrs.setdefault("Connection", "close")

    last_err = ""
    for attempt in range(max(1, retries + 1)):
        try:
            import httpx
            try:
                res = httpx.post(url, json=payload, headers=hdrs, timeout=timeout)
                content_type = res.headers.get("content-type", "")
                res_data = res.json() if "application/json" in content_type else {}
                return res.status_code, res_data, res.text
            except Exception as exc:
                last_err = str(exc)
                if attempt < retries:
                    time.sleep(0.5)
        except ModuleNotFoundError:
            pass

        import urllib.error
        import urllib.request
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                body_bytes = resp.read()
                body_text = body_bytes.decode("utf-8", errors="replace")
                try:
                    res_data = json.loads(body_text)
                except Exception:
                    res_data = {}
                return status_code, res_data, body_text
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            try:
                res_data = json.loads(body_text)
            except Exception:
                res_data = {}
            return exc.code, res_data, body_text
        except Exception as exc:
            last_err = str(exc)
            if attempt < retries:
                time.sleep(0.5)
                continue
            return 500, {}, last_err or "Connection failed"

    return 500, {}, last_err or "Unknown HTTP error"


def _send_feishu(channel: Dict[str, Any], title: str, content: str) -> Dict[str, Any]:
    lines = [line for line in content.splitlines() if line.strip()]
    content_paragraphs = []
    for line in lines[:30]:  # Limit lines for card
        content_paragraphs.append([{"tag": "text", "text": line}])

    is_app_mode = (
        channel.get("feishu_mode") == "app"
        or bool(channel.get("app_id"))
        or bool(channel.get("receive_id"))
    )

    if is_app_mode:
        app_id = str(channel.get("app_id") or "").strip()
        app_secret = str(channel.get("app_secret") or "").strip()
        receive_id = str(channel.get("receive_id") or "").strip()
        receive_id_type = str(channel.get("receive_id_type") or "open_id").strip() or "open_id"

        # Auto-infer receive_id_type if not explicitly set to a custom one
        if receive_id_type == "open_id":
            if receive_id.startswith("oc_"):
                receive_id_type = "chat_id"
            elif "@" in receive_id:
                receive_id_type = "email"

        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        token_payload = {
            "app_id": app_id,
            "app_secret": app_secret,
        }
        status_code, res_data, res_text = _http_post_json(token_url, token_payload, timeout=10.0)
        if status_code != 200 or res_data.get("code", -1) != 0:
            err_msg = res_data.get("msg") or res_text or f"HTTP {status_code}"
            return {"status": "error", "channel_id": channel.get("id"), "type": "feishu", "error": f"Feishu auth failed: {err_msg}"}

        tenant_token = res_data.get("tenant_access_token")
        if not tenant_token:
            return {"status": "error", "channel_id": channel.get("id"), "type": "feishu", "error": "Feishu auth returned no tenant_access_token"}

        send_url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
        post_obj = {
            "zh_cn": {
                "title": f"📢 {title}",
                "content": content_paragraphs,
            }
        }
        send_payload = {
            "receive_id": receive_id,
            "msg_type": "post",
            "content": json.dumps(post_obj, ensure_ascii=False),
        }
        send_headers = {"Authorization": f"Bearer {tenant_token}"}
        send_status, send_data, send_text = _http_post_json(send_url, send_payload, headers=send_headers, timeout=10.0)
        if send_status == 200 and send_data.get("code", -1) == 0:
            return {"status": "success", "channel_id": channel.get("id"), "type": "feishu", "response": send_data}
        else:
            err_msg = send_data.get("msg") or send_text or f"HTTP {send_status}"
            return {"status": "error", "channel_id": channel.get("id"), "type": "feishu", "error": f"Feishu send failed: {err_msg}"}

    # Webhook mode
    url = channel.get("url", "")
    secret = channel.get("secret")
    timestamp = int(time.time())

    payload: Dict[str, Any] = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"📢 {title}",
                    "content": content_paragraphs,
                }
            }
        },
    }

    if secret:
        payload["timestamp"] = str(timestamp)
        payload["sign"] = _gen_feishu_signature(secret, timestamp)

    status_code, res_data, res_text = _http_post_json(url, payload, timeout=10.0)
    if status_code == 200 and res_data.get("code", 0) == 0:
        return {"status": "success", "channel_id": channel.get("id"), "type": "feishu", "response": res_data}
    else:
        err_msg = res_data.get("msg") or res_text or f"HTTP {status_code}"
        return {"status": "error", "channel_id": channel.get("id"), "type": "feishu", "error": err_msg}


def _send_dingtalk(channel: Dict[str, Any], title: str, content: str) -> Dict[str, Any]:
    raw_url = channel["url"]
    secret = channel.get("secret", "")
    url = _gen_dingtalk_url(raw_url, secret)

    markdown_text = f"### 📢 {title}\n\n{content}"
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown_text,
        },
    }

    status_code, res_data, res_text = _http_post_json(url, payload, timeout=10.0)
    if status_code == 200 and res_data.get("errcode", 0) == 0:
        return {"status": "success", "channel_id": channel["id"], "type": "dingtalk", "response": res_data}
    else:
        err_msg = res_data.get("errmsg") or res_text or f"HTTP {status_code}"
        return {"status": "error", "channel_id": channel["id"], "type": "dingtalk", "error": err_msg}


def _send_webhook(
    channel: Dict[str, Any],
    title: str,
    content: str,
    event_type: str,
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    url = channel["url"]
    headers = channel.get("headers") or {}

    payload = {
        "event": event_type,
        "title": title,
        "content": content,
        "metadata": metadata or {},
        "timestamp": datetime.now().isoformat(),
    }

    status_code, res_data, res_text = _http_post_json(url, payload, headers=headers, timeout=10.0)
    if 200 <= status_code < 300:
        return {"status": "success", "channel_id": channel["id"], "type": "webhook", "http_code": status_code}
    else:
        return {"status": "error", "channel_id": channel["id"], "type": "webhook", "error": f"HTTP {status_code}: {res_text[:200]}"}


def _send_email(channel: Dict[str, Any], title: str, content: str) -> Dict[str, Any]:
    import smtplib

    smtp_host = channel["smtp_host"]
    smtp_port = channel.get("smtp_port", 465)
    smtp_user = channel.get("smtp_user", "")
    smtp_pass = channel.get("smtp_pass", "")
    use_tls = channel.get("use_tls", True)
    sender = channel.get("sender") or smtp_user
    recipients = channel.get("recipients", [])

    if not recipients:
        return {"status": "error", "channel_id": channel["id"], "type": "email", "error": "No recipients configured"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[NexusMind] {title}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    plain_part = MIMEText(content, "plain", "utf-8")
    html_body = f"""<html>
<head><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1e293b; background: #f8fafc; padding: 20px; }}
.card {{ max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
h2 {{ color: #0f172a; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; font-size: 20px; }}
pre {{ background: #f1f5f9; padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; font-family: monospace; font-size: 13px; }}
.footer {{ margin-top: 24px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 12px; }}
</style></head>
<body>
<div class="card">
  <h2>📢 {title}</h2>
  <pre>{content}</pre>
  <div class="footer">推送自 NexusMind 自动知识库系统 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
</body>
</html>"""
    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(plain_part)
    msg.attach(html_part)

    try:
        if smtp_port == 465 or not use_tls:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            if use_tls:
                server.starttls()

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(sender, recipients, msg.as_string())
        server.quit()
        return {"status": "success", "channel_id": channel["id"], "type": "email", "recipients": recipients}
    except Exception as exc:
        return {"status": "error", "channel_id": channel["id"], "type": "email", "error": str(exc)}


def test_notification_channel(channel_config: Dict[str, Any]) -> Dict[str, Any]:
    channel_type = str(channel_config.get("type") or "").strip().lower()
    test_title = f"NexusMind 通道测试: {channel_config.get('name', '未命名通道')}"
    test_content = (
        f"这是一条来自 NexusMind 的通道连通性测试消息。\n"
        f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"通道类型: {channel_type}\n"
        f"状态: 正常运行"
    )

    if channel_type == "feishu":
        return _send_feishu(channel_config, test_title, test_content)
    elif channel_type == "dingtalk":
        return _send_dingtalk(channel_config, test_title, test_content)
    elif channel_type == "webhook":
        return _send_webhook(channel_config, test_title, test_content, "test", {"test": True})
    elif channel_type == "email":
        return _send_email(channel_config, test_title, test_content)
    else:
        return {"status": "error", "error": f"Unsupported channel type: {channel_type}"}


test_notification_channel.__test__ = False


def send_notification(
    title: str,
    content: str,
    channel_ids: Optional[List[str]] = None,
    event_type: str = "general",
    metadata: Optional[Dict[str, Any]] = None,
    config_path: Optional[Path] = None,
    config_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = config_data if config_data is not None else load_notification_config(config_path)
    all_channels = config.get("channels", [])
    enabled_channels = [c for c in all_channels if c.get("enabled", True)]

    if not enabled_channels:
        return {
            "status": "warning",
            "message": "No enabled notification channels found",
            "sent_count": 0,
            "failed_count": 0,
            "results": [],
        }

    target_channels: List[Dict[str, Any]] = []

    if channel_ids and "all" in [c.lower() for c in channel_ids]:
        target_channels = enabled_channels
    elif channel_ids:
        lowered_targets = set(c.lower() for c in channel_ids)
        for c in enabled_channels:
            cid = c.get("id", "").lower()
            ctype = c.get("type", "").lower()
            if cid in lowered_targets or ctype in lowered_targets:
                target_channels.append(c)
    else:
        default_id = config.get("default_channel_id")
        if default_id:
            target_channels = [c for c in enabled_channels if c.get("id") == default_id]
        if not target_channels:
            target_channels = enabled_channels[:1]

    results = []
    sent_count = 0
    failed_count = 0

    for ch in target_channels:
        ch_type = ch.get("type")
        res: Dict[str, Any]
        try:
            if ch_type == "feishu":
                res = _send_feishu(ch, title, content)
            elif ch_type == "dingtalk":
                res = _send_dingtalk(ch, title, content)
            elif ch_type == "webhook":
                res = _send_webhook(ch, title, content, event_type, metadata)
            elif ch_type == "email":
                res = _send_email(ch, title, content)
            else:
                res = {"status": "error", "channel_id": ch.get("id"), "type": ch_type, "error": "Unknown type"}
        except Exception as exc:
            res = {"status": "error", "channel_id": ch.get("id"), "type": ch_type, "error": str(exc)}

        if res.get("status") == "success":
            sent_count += 1
        else:
            failed_count += 1
        results.append(res)

    status = "success" if failed_count == 0 else ("partial_success" if sent_count > 0 else "error")
    return {
        "status": status,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "results": results,
    }
