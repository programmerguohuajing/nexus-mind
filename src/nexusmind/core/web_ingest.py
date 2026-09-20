from __future__ import annotations

import ipaddress
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

MAX_PAGE_BYTES = 5 * 1024 * 1024
USER_AGENT = "NexusMind/0.1 (+knowledge-ingest)"


_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)


def _is_blocked_ip(address: ipaddress._BaseAddress) -> bool:
    return any(address in network for network in _BLOCKED_NETWORKS)


def _validate_url(url: str, allow_private: bool = False) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅支持有效的 http/https 在线链接")
    hostname = parsed.hostname.lower()
    if allow_private:
        return parsed.geturl()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("不允许抓取本机或内网地址")
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise ValueError("不允许抓取本机或内网地址")
    except ValueError as exc:
        if "不允许抓取" in str(exc):
            raise
        import socket

        try:
            addresses = socket.getaddrinfo(hostname, parsed.port or 443)
        except socket.gaierror as dns_exc:
            raise ValueError("无法解析该链接的域名") from dns_exc
        for item in addresses:
            candidate = ipaddress.ip_address(item[4][0])
            if _is_blocked_ip(candidate):
                raise ValueError("不允许抓取解析到内网的地址")
    return parsed.geturl()


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._parts: list[str] = []
        self._block_tags = {"p", "article", "section", "main", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"}
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}:
            self._skip += 1
        if not self._skip and tag in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"} and self._skip:
            self._skip -= 1
        if not self._skip and tag in self._block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if not self._skip:
            value = data.strip()
            if value:
                self._parts.append(value + " ")

    def content(self) -> str:
        text = unescape("".join(self._parts))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


def extract_web_page(html: str, url: str) -> dict[str, Any]:
    parser = _ArticleParser()
    parser.feed(html)
    title = re.sub(r"\s+", " ", parser.title).strip()
    content = parser.content()
    if len(content) < 40:
        raise ValueError("未能从该网页提取到足够的正文内容")
    return {
        "title": title or urlparse(url).hostname or "网页资料",
        "content": content,
        "url": url,
        "characters": len(content),
    }


def fetch_web_page(url: str, allow_private: bool = False) -> dict[str, Any]:
    import httpx

    current = _validate_url(url, allow_private=allow_private)
    with httpx.Client(
        timeout=15.0,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for _ in range(5):
            response = client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("location")
                if not target:
                    raise ValueError("网页重定向缺少目标地址")
                current = str(response.url.join(target))
                current = _validate_url(current, allow_private=allow_private)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise ValueError("该链接不是可提取的 HTML 网页")
            if len(response.content) > MAX_PAGE_BYTES:
                raise ValueError("网页内容超过 5 MB，暂不支持直接抓取")
            return extract_web_page(response.text, current)
    raise ValueError("网页重定向次数过多")
