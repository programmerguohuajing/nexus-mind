from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "nexusmind" / "agent" / "assets"
    else:
        base = Path(__file__).resolve().parent / "assets"
    return base / name


def app_icon_path() -> Path:
    return asset_path("nexusmind-agent.png")


def exe_icon_path() -> Path:
    return asset_path("nexusmind-agent.ico")
