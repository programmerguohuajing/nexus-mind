from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "packaging" / "nexusmind_agent_entry.py"


def main() -> int:
    system = platform.system().lower()
    icon = ROOT / "src" / "nexusmind" / "agent" / "assets" / (
        "nexusmind-agent.ico" if system == "windows" else "nexusmind-agent.png"
    )
    assets = ROOT / "src" / "nexusmind" / "agent" / "assets"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "NexusMindAgent",
        "--windowed",
        "--icon",
        str(icon),
        "--hidden-import",
        "nexusmind.api.server",
        "--collect-data",
        "nexusmind",
        "--add-data",
        f"{assets}{__import__('os').pathsep}nexusmind/agent/assets",
    ]
    if system in {"windows", "linux"}:
        command.append("--onefile")
    command.append(str(ENTRY))
    print("Running:", " ".join(command))
    subprocess.check_call(command, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
