from __future__ import annotations

import platform
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "packaging" / "nexusmind_agent_entry.py"


def main() -> int:
    system = platform.system().lower()
    icon = ROOT / "src" / "nexusmind" / "agent" / "assets" / (
        "nexusmind-agent.ico" if system == "windows" else "nexusmind-agent.png"
    )
    source_root = ROOT / "src"
    assets = source_root / "nexusmind" / "agent" / "assets"
    web_assets = source_root / "nexusmind" / "web"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--noupx",
        "--name",
        "NexusMindAgent",
        "--paths",
        str(source_root),
        "--windowed",
        "--icon",
        str(icon),
        "--hidden-import",
        "nexusmind.api.server",
        "--add-data",
        f"{assets}{__import__('os').pathsep}nexusmind/agent/assets",
        "--add-data",
        f"{web_assets}{__import__('os').pathsep}nexusmind/web",
    ]
    if system in {"windows", "linux"}:
        command.append("--onefile")
    command.append(str(ENTRY))

    if system == "windows":
        executable = ROOT / "dist" / "NexusMindAgent.exe"
        if executable.exists():
            try:
                executable.unlink()
            except OSError as exc:
                raise RuntimeError(
                    "Existing NexusMindAgent.exe is still locked. Close the running Agent and retry."
                ) from exc

    print("Running:", " ".join(command))
    subprocess.check_call(command, cwd=ROOT)

    if system == "windows":
        executable = ROOT / "dist" / "NexusMindAgent.exe"
        print(f"Smoke testing: {executable}")
        process = subprocess.Popen([str(executable)], cwd=ROOT)
        time.sleep(5)
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"NexusMindAgent.exe failed startup smoke test with exit code {exit_code}"
            )
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        print("Startup smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
