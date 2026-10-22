"""本地 API Token 鉴权（产品设计文档 P1-2）。

规则：
- 未配置 NEXUSMIND_API_TOKEN 时不启用（本地单机默认体验不变）。
- 启用后：来自非回环地址的 /api/ 与 /mcp/ 请求必须携带
  Authorization: Bearer <token> 或 X-NexusMind-Token: <token>。
- 回环地址（本机 Web 管理台、剪藏扩展）默认可信，避免控制台自锁。
"""
from __future__ import annotations

import os
from typing import Optional

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def configured_token() -> str:
    return os.environ.get("NEXUSMIND_API_TOKEN", "").strip()


def is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    return host.strip().lower() in _LOOPBACK_HOSTS


def token_required(client_host: Optional[str]) -> bool:
    """当前请求是否需要 Token：已配置 Token 且来源非回环。"""
    if not configured_token():
        return False
    return not is_loopback(client_host)


def check_token(client_host: Optional[str], authorization: Optional[str], header_token: Optional[str]) -> bool:
    """返回请求是否放行。"""
    if not token_required(client_host):
        return True
    expected = configured_token()
    if header_token and header_token.strip() == expected:
        return True
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip() == expected:
            return True
    return False
