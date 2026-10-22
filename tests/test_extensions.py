"""扩展结构测试：VS Code 插件清单/命令/接口引用完整性。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vscode_extension_structure():
    ext_dir = ROOT / "extensions" / "vscode"
    package = json.loads((ext_dir / "package.json").read_text(encoding="utf-8"))
    assert package["engines"]["vscode"]
    commands = {item["command"] for item in package["contributes"]["commands"]}
    assert "nexusmind.captureNote" in commands
    assert "nexusmind.askVault" in commands
    assert "nexusmind.projectContext" in commands
    views = package["contributes"]["views"]["explorer"]
    assert views[0]["id"] == "nexusmind.related"

    source = (ext_dir / "src" / "extension.ts").read_text(encoding="utf-8")
    for endpoint in ("/mcp/vault_search", "/mcp/vault_ingest", "/api/ask", "/api/project/context", "/health"):
        assert endpoint in source, endpoint
    assert (ext_dir / "tsconfig.json").is_file()
    assert (ext_dir / "README.md").is_file()
