"""Agent 项目绑定测试：.nexusmind.yaml 向上查找、Vault 侧映射、作用域清单。"""
from nexusmind.core.project_binding import (
    find_binding_file,
    project_context,
)


def _seed_vault(vault):
    (vault / "40-Domain/Pay").mkdir(parents=True)
    (vault / "40-Domain/Photo").mkdir(parents=True)
    (vault / "20-Projects/shop").mkdir(parents=True)
    (vault / "40-Domain/Pay/支付超时排查.md").write_text(
        "---\ntitle: 支付超时排查\ntags:\n  - \"#支付\"\n---\n\n# 支付超时排查\n\n支付网关超时处理。", encoding="utf-8"
    )
    (vault / "40-Domain/Photo/摄影构图.md").write_text(
        "---\ntitle: 摄影构图\ntags:\n  - \"#摄影\"\n---\n\n# 摄影构图\n\n三分法。", encoding="utf-8"
    )
    (vault / "20-Projects/shop/订单状态机.md").write_text(
        "---\ntitle: 订单状态机\ntags:\n  - \"#订单\"\n---\n\n# 订单状态机\n\n订单状态流转。", encoding="utf-8"
    )


def test_repo_binding_found_by_walking_up(tmp_path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    repo = tmp_path / "code" / "account-shop"
    deep = repo / "src" / "pages"
    deep.mkdir(parents=True)
    (repo / ".nexusmind.yaml").write_text(
        "project: account-shop\n"
        "description: 游戏账号交易平台\n"
        "scope:\n"
        "  folders:\n    - 40-Domain/Pay\n"
        "  tags:\n    - \"#订单\"\n",
        encoding="utf-8",
    )
    found = find_binding_file(deep)
    assert found == repo / ".nexusmind.yaml"

    ctx = project_context(project_path=str(deep), vault_root=vault)
    assert ctx["project"] == "account-shop"
    assert ctx["source"] == "repo"
    paths = {note["path"] for note in ctx["notes"]}
    assert "40-Domain/Pay/支付超时排查.md" in paths      # folder 命中
    assert "20-Projects/shop/订单状态机.md" in paths        # tag 命中
    assert "40-Domain/Photo/摄影构图.md" not in paths       # 作用域外


def test_vault_side_binding(tmp_path):
    vault = tmp_path / "vault"
    _seed_vault(vault)
    (vault / "00-Meta").mkdir(parents=True, exist_ok=True)
    (vault / "00-Meta/projects.yaml").write_text(
        "projects:\n"
        "  photo-app:\n"
        "    folders: [40-Domain/Photo]\n"
        "    tags: []\n",
        encoding="utf-8",
    )
    ctx = project_context(project="photo-app", vault_root=vault)
    assert ctx["source"] == "vault"
    assert [n["path"] for n in ctx["notes"]] == ["40-Domain/Photo/摄影构图.md"]


def test_missing_binding_gives_guidance(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = tmp_path / "plain-repo"
    repo.mkdir()
    ctx = project_context(project_path=str(repo), vault_root=vault)
    assert ctx["source"] == "none"
    assert ".nexusmind.yaml" in ctx["guidance"]
    assert ctx["notes"] == []
