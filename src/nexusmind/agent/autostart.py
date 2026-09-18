from __future__ import annotations

import platform
from pathlib import Path

from nexusmind.agent.configuration import startup_command, user_config_dir


def set_autostart(enabled: bool) -> None:
    system = platform.system().lower()
    if system == "windows":
        _set_windows(enabled)
    elif system == "darwin":
        _set_macos(enabled)
    else:
        _set_linux(enabled)


def _set_windows(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key, "NexusMindAgent", 0, winreg.REG_SZ, startup_command()
            )
        else:
            try:
                winreg.DeleteValue(key, "NexusMindAgent")
            except FileNotFoundError:
                pass


def _set_macos(enabled: bool) -> None:
    target = Path.home() / "Library/LaunchAgents/com.nexusmind.agent.plist"
    if not enabled:
        target.unlink(missing_ok=True)
        return
    command = startup_command()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.nexusmind.agent</string>
<key>ProgramArguments</key><array>
<string>/bin/sh</string><string>-lc</string><string>{command}</string>
</array>
<key>RunAtLoad</key><true/>
</dict></plist>
""",
        encoding="utf-8",
    )


def _set_linux(enabled: bool) -> None:
    target = Path.home() / ".config/autostart/nexusmind-agent.desktop"
    if not enabled:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=NexusMind Agent\n"
        f"Exec={startup_command()}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
