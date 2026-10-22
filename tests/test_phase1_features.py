"""Phase 1 功能测试：OCR 入库 / 版本历史 / 重复检测 / 知识保鲜 / 模板库 / API 鉴权。"""
import io

import fitz
import pytest
from fastapi.testclient import TestClient

from nexusmind.api import server as server_module
from nexusmind.api.server import app
from nexusmind.core import api_auth
from nexusmind.core.compiler import patch_note
from nexusmind.core.duplicates import find_duplicate_pairs, ignore_pair, merge_notes
from nexusmind.core.freshness import list_stale_notes, mark_reviewed
from nexusmind.core.history import diff_snapshot, list_history, rollback_note
from nexusmind.core.ocr import ocr_image_bytes, ocr_pdf_bytes, ocr_status, pdf_needs_ocr
from nexusmind.core.templates import create_from_template, extract_action_items, list_templates
from nexusmind.core.uploads import ingest_uploaded_file

client = TestClient(app)


def _make_text_png(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=600, height=200)
    page.insert_text((40, 100), text, fontsize=32)
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


def _make_scanned_pdf(text: str) -> bytes:
    png = _make_text_png(text)
    doc = fitz.open()
    page = doc.new_page(width=600, height=200)
    page.insert_image(page.rect, stream=png)
    return doc.tobytes()


def _write_note(vault, rel, content, **kwargs):
    return patch_note(rel, content, if_match=kwargs.get("if_match", "NEW"),
                      actor="test", privileged=True, vault_root=vault)


# ---------------- OCR ----------------

def test_ocr_status_reports_engine():
    status = ocr_status()
    assert status["engine"] in ("tesseract", None)
    assert "install_hint" in status


def test_ocr_image_extracts_text():
    if not ocr_status()["available"]:
        pytest.skip("tesseract not installed")
    result = ocr_image_bytes(_make_text_png("Hello NexusMind OCR"), ".png", lang="eng")
    assert "Hello" in result["text"]
    assert result["confidence"] is not None


def test_image_upload_runs_ocr_into_markdown(tmp_path):
    if not ocr_status()["available"]:
        pytest.skip("tesseract not installed")
    result = ingest_uploaded_file("board.png", _make_text_png("Whiteboard Notes"), vault_root=tmp_path)
    assert result["source_type"] == "image"
    assert result["ocr"] and result["ocr"].get("ocr") is True
    markdown = (tmp_path / result["markdown_path"]).read_text(encoding="utf-8")
    assert "Whiteboard" in markdown
    assert "ocr: true" in markdown


def test_scanned_pdf_upload_uses_ocr(tmp_path):
    if not ocr_status()["available"]:
        pytest.skip("tesseract not installed")
    data = _make_scanned_pdf("Scanned Spec Page")
    assert pdf_needs_ocr(data) is True
    ocr_result = ocr_pdf_bytes(data, lang="eng")
    assert "Scanned" in ocr_result["text"]
    result = ingest_uploaded_file("scan.pdf", data, vault_root=tmp_path)
    markdown = (tmp_path / result["markdown_path"]).read_text(encoding="utf-8")
    assert "Scanned" in markdown
    assert "ocr: true" in markdown


# ---------------- 版本历史 ----------------

def test_history_snapshot_diff_and_rollback(tmp_path):
    first = _write_note(tmp_path, "20-Projects/demo.md", "# Demo\n\n第一版内容。")
    _write_note(tmp_path, "20-Projects/demo.md", "# Demo\n\n第二版内容，完全改写。",
                if_match=first["version"])
    history = list_history("20-Projects/demo.md", vault_root=tmp_path)
    assert history["total"] == 1
    old_version = history["versions"][0]["version"]
    assert old_version == first["version"]

    diff = diff_snapshot("20-Projects/demo.md", old_version, vault_root=tmp_path)
    assert "第一版内容" in diff["diff"]
    assert "第二版内容" in diff["diff"]

    rolled = rollback_note("20-Projects/demo.md", old_version, vault_root=tmp_path)
    assert rolled["status"] == "rolled_back"
    current = (tmp_path / "20-Projects/demo.md").read_text(encoding="utf-8")
    assert "第一版内容" in current
    # 回滚本身也是一次写入，历史中应保留被回滚前的版本
    assert list_history("20-Projects/demo.md", vault_root=tmp_path)["total"] == 2


def test_history_api_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "VAULT_ROOT", tmp_path)
    first = _write_note(tmp_path, "20-Projects/api.md", "v1 body")
    _write_note(tmp_path, "20-Projects/api.md", "v2 body", if_match=first["version"])
    resp = client.get("/api/history", params={"path": "20-Projects/api.md"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    version = resp.json()["versions"][0]["version"]
    resp = client.post("/api/history/rollback", json={"path": "20-Projects/api.md", "version": version})
    assert resp.status_code == 200
    assert "v1 body" in (tmp_path / "20-Projects/api.md").read_text(encoding="utf-8")


# ---------------- 重复检测与合并 ----------------

_LONG_A = "# 支付超时排查\n\n" + "支付网关超时后先看回调日志，再检查重试队列与幂等键，最后核对商户配置。" * 6
_LONG_B = "# 支付超时处理手册\n\n" + "支付网关超时后先看回调日志，再检查重试队列与幂等键，最后核对商户配置。" * 6


def test_duplicate_detection_ignore_and_merge(tmp_path):
    _write_note(tmp_path, "40-Domain/Pay/a.md", _LONG_A)
    _write_note(tmp_path, "40-Domain/Pay/b.md", _LONG_B)
    _write_note(tmp_path, "40-Domain/Pay/c.md", "# 完全不同的主题\n\n" + "蓝天白云与草原风光的摄影技巧完全不相关的内容填充。" * 6)

    found = find_duplicate_pairs(vault_root=tmp_path, threshold=0.8)
    pair_paths = {(p["path_a"], p["path_b"]) for p in found["pairs"]}
    assert ("40-Domain/Pay/a.md", "40-Domain/Pay/b.md") in pair_paths

    ignore_pair("40-Domain/Pay/a.md", "40-Domain/Pay/b.md", vault_root=tmp_path)
    found_after = find_duplicate_pairs(vault_root=tmp_path, threshold=0.8)
    assert ("40-Domain/Pay/a.md", "40-Domain/Pay/b.md") not in {
        (p["path_a"], p["path_b"]) for p in found_after["pairs"]
    }

    merged = merge_notes("40-Domain/Pay/a.md", "40-Domain/Pay/b.md", vault_root=tmp_path)
    assert merged["status"] == "merged"
    stub = (tmp_path / "40-Domain/Pay/b.md").read_text(encoding="utf-8")
    assert "merged_into" in stub
    assert "40-Domain/Pay/a.md" in stub


# ---------------- 知识保鲜 ----------------

def test_stale_notes_and_mark_reviewed(tmp_path):
    card = (
        "---\ntitle: 旧卡片\nlast_compiled_at: 2025-01-01\nreview_after: 90d\n---\n\n# 旧卡片\n\n内容。"
    )
    _write_note(tmp_path, "40-Domain/Old/card.md", card)
    fresh = (
        "---\ntitle: 新卡片\nlast_reviewed: 2999-01-01\nreview_after: 90d\n---\n\n# 新卡片\n\n内容。"
    )
    _write_note(tmp_path, "40-Domain/Old/fresh.md", fresh)

    stale = list_stale_notes(vault_root=tmp_path)
    paths = [item["path"] for item in stale["stale_notes"]]
    assert "40-Domain/Old/card.md" in paths
    assert "40-Domain/Old/fresh.md" not in paths

    reviewed = mark_reviewed("40-Domain/Old/card.md", vault_root=tmp_path)
    assert reviewed["status"] == "reviewed"
    stale_after = list_stale_notes(vault_root=tmp_path)
    assert "40-Domain/Old/card.md" not in [i["path"] for i in stale_after["stale_notes"]]


# ---------------- 模板库 ----------------

def test_templates_seed_create_and_action_items(tmp_path):
    listing = list_templates(vault_root=tmp_path)
    ids = {item["id"] for item in listing["templates"]}
    assert {"meeting", "adr", "incident"}.issubset(ids)

    created = create_from_template("meeting", "支付周会", vault_root=tmp_path)
    assert created["status"] == "created"
    note = (tmp_path / created["path"]).read_text(encoding="utf-8")
    assert "支付周会" in note
    assert "{{title}}" not in note
    assert "template: meeting" in note

    items = extract_action_items(note)
    assert items and items[0]["owner"] == "负责人"
    done_items = extract_action_items("- [x] 已完成事项 (@张三 ddl:2026-10-01)\n- [ ] 待办 (@李四)")
    assert done_items[0]["done"] is True and done_items[0]["ddl"] == "2026-10-01"
    assert done_items[1]["owner"] == "李四" and done_items[1]["ddl"] is None


# ---------------- API Token 鉴权 ----------------

def test_api_auth_logic(monkeypatch):
    monkeypatch.setenv("NEXUSMIND_API_TOKEN", "secret-token")
    assert api_auth.token_required("127.0.0.1") is False
    assert api_auth.token_required("192.168.1.20") is True
    assert api_auth.check_token("192.168.1.20", None, None) is False
    assert api_auth.check_token("192.168.1.20", "Bearer secret-token", None) is True
    assert api_auth.check_token("192.168.1.20", None, "secret-token") is True
    assert api_auth.check_token("192.168.1.20", "Bearer wrong", None) is False
    monkeypatch.delenv("NEXUSMIND_API_TOKEN")
    assert api_auth.token_required("192.168.1.20") is False


def test_api_token_middleware_blocks_remote_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(server_module, "VAULT_ROOT", tmp_path)
    monkeypatch.setenv("NEXUSMIND_API_TOKEN", "secret-token")
    blocked = client.get("/api/templates")
    assert blocked.status_code == 401
    allowed = client.get("/api/templates", headers={"Authorization": "Bearer secret-token"})
    assert allowed.status_code == 200
    assert allowed.json()["total"] >= 3
