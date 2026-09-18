from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _headings(path: Path) -> list[int]:
    levels = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^(#{1,6})\s+", line)
        if match:
            levels.append(len(match.group(1)))
    return levels


def test_default_docs_are_english_with_chinese_companions():
    readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
    readme_cn = (ROOT / "README_CN.md").read_text(encoding="utf-8-sig")
    manual = (ROOT / "USER_MANUAL.md").read_text(encoding="utf-8-sig")
    manual_cn = (ROOT / "USER_MANUAL_CN.md").read_text(encoding="utf-8-sig")

    assert "## What NexusMind Does" in readme
    assert "## 核心能力" in readme_cn
    assert "## 1. Start NexusMind" in manual
    assert "## 1. 启动系统" in manual_cn


def test_language_switch_links_are_bidirectional():
    readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
    readme_cn = (ROOT / "README_CN.md").read_text(encoding="utf-8-sig")
    manual = (ROOT / "USER_MANUAL.md").read_text(encoding="utf-8-sig")
    manual_cn = (ROOT / "USER_MANUAL_CN.md").read_text(encoding="utf-8-sig")

    assert "[中文](README_CN.md)" in readme
    assert "[English](README.md)" in readme_cn
    assert "[中文](USER_MANUAL_CN.md)" in manual
    assert "[English](USER_MANUAL.md)" in manual_cn


def test_bilingual_docs_keep_the_same_heading_structure():
    assert _headings(ROOT / "README.md") == _headings(ROOT / "README_CN.md")
    assert _headings(ROOT / "USER_MANUAL.md") == _headings(ROOT / "USER_MANUAL_CN.md")


def test_bilingual_docs_share_operational_examples():
    pairs = [
        ("README.md", "README_CN.md"),
        ("USER_MANUAL.md", "USER_MANUAL_CN.md"),
    ]
    required = [
        "python scripts/vault_service.py",
        "docker compose up -d --build",
        "NEXUSMIND_CLOUD_SYNC_URL",
        "NEXUSMIND_CLOUD_SYNC_TOKEN",
        'pip install -e ".[agent]"',
        "python packaging/build_agent.py",
        "nexusmind serve --stdio",
        "python scripts/mcp_server.py",
        "NEXUSMIND_VAULT_ROOT",
        '"mcpServers"',
        "vault_read",
        "vault_weekly_review",
    ]
    for english_name, chinese_name in pairs:
        english = (ROOT / english_name).read_text(encoding="utf-8-sig")
        chinese = (ROOT / chinese_name).read_text(encoding="utf-8-sig")
        for token in required:
            assert token in english
            assert token in chinese
