import sys
import argparse
import json
from pathlib import Path

from nexusmind import __version__
from nexusmind.config import DEFAULT_HOST, DEFAULT_PORT, PROJECT_ROOT, VAULT_ROOT
from nexusmind.core.compiler import auto_compile_pending_sources, scan_uncompiled_sources
from nexusmind.core.indexer import rebuild_all_indices, find_broken_links, find_orphans
from nexusmind.core.ingest import ingest_article
from nexusmind.core.review import generate_weekly_review
from nexusmind.core.search import search_notes
from nexusmind.api.mcp_stdio import run_stdio_server

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexusmind",
        description="NexusMind (知枢): Agent + Obsidian Self-Growing Knowledge Operating System CLI"
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available Commands")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start Vault MCP Server")
    serve_parser.add_argument("--host", default=DEFAULT_HOST, help="HTTP Server host")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP Server port")
    serve_parser.add_argument("--stdio", action="store_true", help="Start in stdio MCP mode for Claude Desktop / Cursor")

    # Compile command
    compile_parser = subparsers.add_parser("compile", help="Incremental LLM Wiki compilation")
    compile_parser.add_argument("--all", action="store_true", help="Compile all pending reference files")
    compile_parser.add_argument("--pending", action="store_true", help="Preview pending raw references only")

    search_parser = subparsers.add_parser("search", help="Search Vault notes")
    search_parser.add_argument("query", nargs="?", default="", help="Keyword or regex")
    search_parser.add_argument("--folder", help="Limit search to a Vault folder")
    search_parser.add_argument("--tag", action="append", default=[], help="Required tag; repeatable")
    search_parser.add_argument("--regex", action="store_true", help="Interpret query as regex")
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum results (1-200)")

    # Index command
    index_parser = subparsers.add_parser("index", help="Rebuild hierarchical index tree and inspect vault")
    index_parser.add_argument("--check-links", action="store_true", help="Check broken links and orphans")

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest raw reference article into 60-References")
    ingest_parser.add_argument("--title", required=True, help="Article title")
    ingest_parser.add_argument("--file", help="Path to markdown text file")
    ingest_parser.add_argument("--content", help="Raw markdown text string")
    ingest_parser.add_argument("--author", default="Unknown", help="Article author")
    ingest_parser.add_argument("--url", help="Original source URL")

    # Review command
    review_parser = subparsers.add_parser("review", help="Generate AI Weekly Review")
    review_parser.add_argument("--week", help="ISO Week format e.g. 2026-W38")

    # Check command
    check_parser = subparsers.add_parser("check", help="Run full system OCC and permission checks")

    return parser

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        if args.stdio:
            print("Starting NexusMind stdio MCP server...", file=sys.stderr)
            run_stdio_server()
        else:
            import uvicorn
            from nexusmind.api.server import app
            print(f"Starting NexusMind HTTP MCP Service at http://{args.host}:{args.port}, vault={VAULT_ROOT}")
            uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "compile":
        pending = scan_uncompiled_sources()
        if args.pending or not args.all:
            print(f"待编译 Raw：{len(pending)}")
            for path in pending:
                print("  -", path.relative_to(VAULT_ROOT).as_posix())
        else:
            print(f"🧠 Running LLM Wiki incremental compilation for vault={VAULT_ROOT}...")
            results = auto_compile_pending_sources()
            print(f"✅ Compilation finished. Processed {len(results)} pending references.")
            for item in results:
                print(f"  - Card: {item['card_path']} (Version: {item['version']})")

    elif args.command == "search":
        result = search_notes(
            args.query,
            folder=args.folder,
            tags=args.tag,
            regex=args.regex,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    elif args.command == "index":
        print(f"🌐 Rebuilding hierarchical index tree...")
        res = rebuild_all_indices()
        print("✅ Index tree updated:")
        print(f"  - Master Index: {res['master_index']}")
        for sub, count in res["sub_indices"].items():
            print(f"  - Sub Index: {sub} ({count} cards)")

        if args.check_links:
            bl = find_broken_links()
            orph = find_orphans()
            print(f"\n🔍 Audit results:")
            print(f"  - Broken links: {bl['total_broken']}")
            print(f"  - Orphan notes: {orph['total_orphans']}")

    elif args.command == "ingest":
        content = ""
        if args.file:
            content = Path(args.file).read_text(encoding="utf-8")
        elif args.content:
            content = args.content
        else:
            print("❌ Error: Must provide either --file or --content", file=sys.stderr)
            sys.exit(1)

        res = ingest_article(
            title=args.title,
            content=content,
            author=args.author,
            url=args.url
        )
        print(f"✅ Ingested successfully into `{res['path']}` (Version: {res['version']})")

    elif args.command == "review":
        print("📊 Running AI Weekly Review Pipeline...")
        res = generate_weekly_review(week_str=args.week)
        print(f"✅ Weekly review generated at `{res['path']}` ({res['logged_tasks_count']} log items processed)")

    elif args.command == "check":
        print("⚙️ Running NexusMind system checks...")
        scripts_path = PROJECT_ROOT / "scripts"
        if str(scripts_path) not in sys.path:
            sys.path.insert(0, str(scripts_path))
        from system_check import run_tests
        run_tests()

if __name__ == "__main__":
    main()
