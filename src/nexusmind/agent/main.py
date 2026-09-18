from __future__ import annotations

import argparse
import os
import sys


def run_api_service() -> int:
    import traceback
    from pathlib import Path

    data_root = Path(
        os.environ.get("NEXUSMIND_DATA_ROOT", Path.home() / ".nexusmind")
    )
    error_log = data_root / "agent-api-error.log"
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")

        import uvicorn
        from nexusmind.api.server import app

        host = os.environ.get("NEXUSMIND_HOST", "127.0.0.1")
        port = int(os.environ.get("NEXUSMIND_PORT", "8301"))
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
        return 0
    except Exception:
        data_root.mkdir(parents=True, exist_ok=True)
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


def run_gui(minimized: bool = False) -> int:
    try:
        from nexusmind.agent.gui import run_agent_gui
    except ImportError as exc:
        raise SystemExit(
            "NexusMind Agent GUI dependencies are missing. "
            'Install with: pip install -e ".[agent]"'
        ) from exc
    return run_agent_gui(minimized=minimized)


def main() -> int:
    parser = argparse.ArgumentParser(prog="nexusmind-agent")
    parser.add_argument("--api-service", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args()
    if args.api_service:
        return run_api_service()
    return run_gui(minimized=args.minimized)


if __name__ == "__main__":
    sys.exit(main())
