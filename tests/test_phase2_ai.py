"""Phase 2 测试：Embedding/语义检索/混合检索、LLM 网关降级、Ask、智能建议、日报叙事。"""
import pytest
from fastapi.testclient import TestClient

from nexusmind.api import server as server_module
from nexusmind.api.server import app
from nexusmind.core import llm as llm_module
from nexusmind.core.ask import ask_vault
from nexusmind.core.embeddings import (
    cosine,
    hybrid_search,
    index_status,
    local_embed,
    rebuild_vector_index,
    semantic_search,
)
from nexusmind.core.llm import LlmUnavailable, llm_status
from nexusmind.core.narrative import generate_daily_narrative
from nexusmind.core.smart import apply_suggestions, suggest_for_note, suggest_links

client = TestClient(app)

PAYMENT_NOTE = """---
title: "支付超时排查"
tags:
  - "#支付"
---

# 支付超时排查

支付网关超时后先看回调日志，再检查重试队列与幂等键，最后核对商户配置。
支付回调延迟常见原因是网关重试风暴与数据库锁等待。
"""

REDIS_NOTE = """---
title: "Redis 缓存穿透"
tags:
  - "#缓存"
---

# Redis 缓存穿透

缓存穿透指查询不存在的数据导致请求直达数据库。解决方案：布隆过滤器拦截、
空值缓存、接口限流。缓存击穿则用互斥锁或逻辑过期处理。
"""

PHOTO_NOTE = """---
title: "摄影构图入门"
tags:
  - "#摄影"
---

# 摄影构图入门

三分法构图把画面横竖三等分，主体放在交叉点上。清晨与黄昏的光线最柔和，
适合拍摄风光与人像。
"""


def _seed(vault):
    (vault / "40-Domain/Pay").mkdir(parents=True)
    (vault / "40-Domain/Cache").mkdir(parents=True)
    (vault / "40-Domain/Photo").mkdir(parents=True)
    (vault / "40-Domain/Pay/支付超时排查.md").write_text(PAYMENT_NOTE, encoding="utf-8")
    (vault / "40-Domain/Cache/Redis缓存穿透.md").write_text(REDIS_NOTE, encoding="utf-8")
    (vault / "40-Domain/Photo/摄影构图入门.md").write_text(PHOTO_NOTE, encoding="utf-8")
    return vault


# ---------------- Embedding 与检索 ----------------

def test_local_embed_similarity_ordering():
    a = local_embed("支付网关超时排查 回调 重试")
    b = local_embed("支付超时后检查回调日志与重试队列")
    c = local_embed("摄影构图三分法与光线")
    assert cosine(a, b) > cosine(a, c)


def test_semantic_and_hybrid_search(tmp_path):
    _seed(tmp_path)
    rebuilt = rebuild_vector_index(vault_root=tmp_path)
    assert rebuilt["documents"] == 3
    status = index_status(vault_root=tmp_path)
    assert status["exists"] and status["documents"] == 3

    semantic = semantic_search("支付网关超时应该怎么排查", vault_root=tmp_path, limit=3)
    assert semantic["matches"][0]["path"] == "40-Domain/Pay/支付超时排查.md"

    semantic2 = semantic_search("缓存穿透怎么解决", vault_root=tmp_path, limit=3)
    assert semantic2["matches"][0]["path"] == "40-Domain/Cache/Redis缓存穿透.md"

    hybrid = hybrid_search("支付超时", vault_root=tmp_path, limit=3)
    assert hybrid["mode"] == "hybrid"
    assert hybrid["matches"][0]["path"] == "40-Domain/Pay/支付超时排查.md"


def test_index_incremental_update(tmp_path):
    _seed(tmp_path)
    rebuild_vector_index(vault_root=tmp_path)
    (tmp_path / "40-Domain/Photo/摄影构图入门.md").write_text(
        PHOTO_NOTE.replace("三分法", "黄金分割"), encoding="utf-8"
    )
    result = semantic_search("黄金分割构图", vault_root=tmp_path, limit=3)
    assert result["matches"][0]["path"] == "40-Domain/Photo/摄影构图入门.md"


# ---------------- LLM 网关 ----------------

def test_llm_off_degrades(monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    status = llm_status()
    assert status["available"] is False
    assert status["provider"] == "off"
    with pytest.raises(LlmUnavailable):
        llm_module.generate("hello")


# ---------------- Ask My Vault ----------------

def test_ask_extractive_mode_with_citations(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    _seed(tmp_path)
    result = ask_vault("支付超时怎么排查", vault_root=tmp_path)
    assert result["mode"] == "extractive"
    assert "支付" in result["answer"]
    citation_paths = [c["path"] for c in result["citations"]]
    assert "40-Domain/Pay/支付超时排查.md" in citation_paths


def test_ask_no_match_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    _seed(tmp_path)
    result = ask_vault("quantum gravity wave detection methods", vault_root=tmp_path)
    assert result["mode"] == "no_match"
    assert result["citations"] == []
    assert "没有找到" in result["answer"]


def test_ask_with_llm_validates_citations(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "auto")
    monkeypatch.setattr(llm_module, "_ollama_alive", lambda: True)

    def fake_post(url, payload, headers=None, timeout=None):
        return {"message": {"content": "支付超时先看回调日志并检查重试队列。[[40-Domain/Pay/支付超时排查.md]] 另见 [[不存在的笔记.md]]"}}

    monkeypatch.setattr(llm_module, "_post_json", fake_post)
    result = ask_vault("支付超时怎么排查", vault_root=tmp_path)
    assert result["mode"] == "llm"
    citation_paths = [c["path"] for c in result["citations"]]
    assert "40-Domain/Pay/支付超时排查.md" in citation_paths
    assert all("不存在" not in p for p in citation_paths)


def test_ask_save_creates_qa_note(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    _seed(tmp_path)
    result = ask_vault("支付超时怎么排查", vault_root=tmp_path, save=True)
    assert result["saved_path"] and result["saved_path"].startswith("20-QA/")
    saved = (tmp_path / result["saved_path"]).read_text(encoding="utf-8")
    assert "支付超时怎么排查" in saved


# ---------------- 智能建议与补链 ----------------

def test_suggestions_and_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    _seed(tmp_path)
    target = tmp_path / "40-Domain/Pay/支付回调重试.md"
    target.write_text(
        "# 支付回调重试\n\n支付回调失败时进入重试队列，配合幂等键防止重复入账。支付场景必须保证最终一致性。\n",
        encoding="utf-8",
    )
    suggestion = suggest_for_note("40-Domain/Pay/支付回调重试.md", vault_root=tmp_path)
    assert suggestion["summary"]
    tag_names = [t["tag"] for t in suggestion["tags"]]
    assert "#支付" in tag_names

    links = suggest_links("40-Domain/Pay/支付回调重试.md", vault_root=tmp_path, min_score=0.05)
    link_paths = [s["path"] for s in links["suggestions"]]
    assert "40-Domain/Pay/支付超时排查.md" in link_paths

    applied = apply_suggestions(
        "40-Domain/Pay/支付回调重试.md",
        summary=suggestion["summary"],
        tags=["#支付"],
        links=["40-Domain/Pay/支付超时排查.md"],
        vault_root=tmp_path,
    )
    assert applied["status"] == "applied"
    text = target.read_text(encoding="utf-8")
    assert "summary:" in text
    assert "## 相关链接" in text
    assert "[[40-Domain/Pay/支付超时排查.md]]" in text


# ---------------- Daily Log 叙事 ----------------

_DAILY_LOG = """---
date: 2026-10-22
tags:
  - "#daily-log"
---

<!-- nexusmind:git-activity:start -->
## Git 工作活动（自动采集）

> NexusMind 自动同步于 2026-10-22 10:00:00。此区块由系统维护，可重复刷新。

### shop-api
- 项目活动：[[20-Projects/Repositories/shop-api/Repository-Activity|shop-api]]
- 仓库：/code/shop-api
- 分支：main
- 当前仓库用户：jing <jing@example.com>
- Git Pull：成功（ok）
- 今日全部用户提交：3 个；Merge/PR 线索：0 个；Tag：1 个
- 工作区：干净（0 个文件）
  - a1b2c3d feat(payment): 增加支付回调重试 — jing <jing@example.com>
  - e4f5a6b fix(payment): 修复超时幂等键冲突 — jing <jing@example.com>
  - c7d8e9f docs: 更新支付接入文档 — jing <jing@example.com>
  - Release/Tag：v1.2.0 — target-author <jing@example.com>

<!-- nexusmind:git-activity:end -->
"""


def test_daily_narrative_template_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    daily_dir = tmp_path / "30-Logs/Daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-10-22.md").write_text(_DAILY_LOG, encoding="utf-8")
    result = generate_daily_narrative("2026-10-22", vault_root=tmp_path)
    assert result["mode"] == "template"
    assert result["facts"]["commits"] == 3
    assert result["facts"]["tags"] == ["v1.2.0"]
    assert "3 次" in result["narrative"] or "3 个" in result["narrative"]
    assert "a1b2c3d" not in result["narrative"]  # 日报不列 hash


# ---------------- API ----------------

def test_ai_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSMIND_LLM_PROVIDER", "off")
    monkeypatch.setattr(server_module, "VAULT_ROOT", tmp_path)
    _seed(tmp_path)
    status = client.get("/api/ai/status")
    assert status.status_code == 200
    assert "llm" in status.json() and "embedding" in status.json()

    asked = client.post("/api/ask", json={"question": "支付超时怎么排查"})
    assert asked.status_code == 200
    assert asked.json()["mode"] in ("extractive", "llm")

    semantic = client.post("/mcp/vault_search", json={"query": "缓存穿透", "mode": "semantic"})
    assert semantic.status_code == 200
    assert semantic.json()["matches"][0]["path"] == "40-Domain/Cache/Redis缓存穿透.md"
