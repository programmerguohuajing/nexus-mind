from pathlib import Path

from nexusmind.core.canvas import CanvasEdge, CanvasNode, generate_canvas
from nexusmind.core.compiler import auto_compile_pending_sources, compile_wiki_card, scan_uncompiled_sources
from nexusmind.core.indexer import find_broken_links, rebuild_all_indices
from nexusmind.core.ingest import ingest_article
from nexusmind.core.review import generate_weekly_review
from nexusmind.core.search import search_notes


def _seed_vault(root: Path) -> None:
    for folder in (
        "00-Meta",
        "20-Projects/Sample",
        "30-Logs/Daily",
        "40-Domain/00-Index",
        "60-References/Articles",
        "90-AI-Workspace/reviews",
    ):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "00-Meta/COMPILATION-LOG.md").write_text(
        "# 📜 知识库编译与审计流水账\n", encoding="utf-8"
    )
    (root / "40-Domain/00-Index/Agent-Index.md").write_text(
        "# Agent 逻辑索引\n", encoding="utf-8"
    )
    (root / "30-Logs/Daily/2026-09-17.md").write_text(
        "| 时间段 | 项目 | 产出 | 链接 |\n"
        "| --- | --- | --- | --- |\n"
        "| 09:00-10:00 | NexusMind | 完成检索模块 | [[Search]] |\n",
        encoding="utf-8",
    )


def test_ingest_compile_index_search_review_pipeline(tmp_path):
    _seed_vault(tmp_path)
    first = ingest_article(
        title="Agent Search Architecture",
        content="# Search\nMCP agent search uses progressive indexing.",
        author="Tester",
        url="https://example.com/a",
        vault_root=tmp_path,
    )
    second = ingest_article(
        title="Agent Search Architecture",
        content="# Search v2\nSecond immutable raw snapshot.",
        author="Tester",
        vault_root=tmp_path,
    )
    assert first["path"] != second["path"]
    assert len(scan_uncompiled_sources(vault_root=tmp_path)) == 2

    compiled = auto_compile_pending_sources(vault_root=tmp_path)
    assert len(compiled) == 2
    assert all(item["audit_logged"] for item in compiled)
    assert len(scan_uncompiled_sources(vault_root=tmp_path)) == 0

    index_res = rebuild_all_indices(vault_root=tmp_path)
    assert index_res["status"] == "success"
    master = (tmp_path / index_res["master_index"]).read_text(encoding="utf-8")
    assert "Agent" in master
    assert "Master 领域子索引" not in master
    assert (tmp_path / "40-Domain/00-Index/Agent-Index.md").exists()

    result = search_notes(
        "progressive indexing",
        folder="40-Domain",
        tags=["#atomic-card"],
        vault_root=tmp_path,
    )
    assert result["total"] >= 1
    assert result["matches"][0]["snippet"]

    review = generate_weekly_review("2026-W38", vault_root=tmp_path)
    assert review["logged_tasks_count"] == 1
    assert (tmp_path / review["path"]).exists()


def test_broken_links_and_canvas_validation(tmp_path):
    _seed_vault(tmp_path)
    note = tmp_path / "20-Projects/Sample/note.md"
    note.write_text(
        "# Note\n[[Missing#Section]]\n[[Existing|ok]]\n",
        encoding="utf-8",
    )
    existing = tmp_path / "20-Projects/Sample/Existing.md"
    existing.write_text("# Existing\n", encoding="utf-8")

    broken = find_broken_links(vault_root=tmp_path)
    broken_names = {item["broken_link"] for item in broken["broken_links"]}
    assert "[[Missing#Section]]" in broken_names
    assert "[[Existing|ok]]" not in broken_names

    nodes = [
        CanvasNode(
            id="n1",
            file="20-Projects/Sample/Existing.md",
            x=0,
            y=0,
            width=300,
            height=180,
        ),
        CanvasNode(
            id="n2",
            text="Summary",
            x=400,
            y=0,
            width=300,
            height=180,
        ),
    ]
    edges = [CanvasEdge(id="e1", fromNode="n1", toNode="n2")]
    canvas = generate_canvas(
        "90-AI-Workspace/test.canvas",
        nodes,
        edges,
        if_match="NEW",
        vault_root=tmp_path,
    )
    assert canvas["nodes"] == 2
    assert (tmp_path / "90-AI-Workspace/test.canvas").exists()


def test_compile_conflict_marker_is_preserved(tmp_path):
    _seed_vault(tmp_path)
    raw = tmp_path / "60-References/Articles/conflict.md"
    raw.write_text("# Raw\nnew fact\n", encoding="utf-8")

    result = compile_wiki_card(
        ["60-References/Articles/conflict.md"],
        "40-Domain/Architecture/Conflict.md",
        "# Conflict\nOld fact remains.\n",
        conflict_detected=True,
        conflict_summary="旧结论与新材料存在差异",
        if_match="NEW",
        vault_root=tmp_path,
    )
    card = (tmp_path / result["card_path"]).read_text(encoding="utf-8")
    assert "### ⚠️ 结论与事实演进对比" in card
    assert "旧结论与新材料存在差异" in card
    assert "[推测待验证]" in card
