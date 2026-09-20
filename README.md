# NexusMind

> A local-first, self-growing engineering knowledge system powered by Git activity, reference ingestion, knowledge compilation, and weekly review.

[中文](README_CN.md)
## What NexusMind Does

NexusMind turns real engineering activity into reusable local knowledge.

- **Configured Git collection**: only folders explicitly selected by the user are collected.
- **Multiple repositories**: add folders repeatedly; a selected folder can be a Git repository itself or a parent containing direct Git children.
- **Automatic work logs**: commits, branches, tags, and working-tree state are captured into Daily Logs.
- **Weekly engineering review**: Conventional Commits, repository activity, releases, and compiled knowledge are summarized into a readable work report.
- **Reference ingestion**: Markdown, TXT, PDF, and DOCX.
- **Knowledge compilation**: source material is incrementally compiled into reusable Domain notes.
- **Knowledge navigation**: search, Wikilinks, backlinks, graph visualization, and Canvas browsing.
- **Governance**: broken links, orphan notes, indexes, and optimistic concurrency control.

## Repository vs. Local Data

The GitHub repository intentionally contains only runnable product code and public product documentation.

The following are local-only and ignored by Git:

- `vault/`: personal knowledge, logs, uploaded files, and generated notes.
- `workflow-config.json`: local Git collection targets.
- `docs/`: internal design notes and local working documents.
- environment files, caches, logs, and build output.

A fresh clone therefore starts as a **blank NexusMind instance** with no private knowledge or author-specific business data.
## Quick Start

### Requirements

- Python 3.10+
- Git
- Windows, macOS, or Linux

### Install

```bash
git clone https://github.com/programmerguohuajing/nexus-mind.git
cd nexus-mind
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[local]"
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e ".[local]"
```

### Run

```bash
python scripts/vault_service.py
```

Open:

- Web console: `http://127.0.0.1:8301/`
- OpenAPI / Swagger: `http://127.0.0.1:8301/docs`

An empty knowledge base on first launch is expected.
### Configure Git Collection

Open:

`Workflow → Collection Scope → Add Folder`

The built-in folder picker supports:

- local disk browsing,
- multiple folder selection,
- repeated additions,
- duplicate prevention,
- removing individual folders,
- persistent configuration after saving.

NexusMind does **not** scan any folder by default.

### Use an External Vault

The default local Vault is `./vault`, which is excluded from Git.

Windows PowerShell:

```powershell
$env:NEXUSMIND_VAULT_ROOT="D:\Knowledge\NexusMind"
python scripts\vault_service.py
```

macOS / Linux:

```bash
export NEXUSMIND_VAULT_ROOT="$HOME/Knowledge/NexusMind"
python scripts/vault_service.py
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `NEXUSMIND_HOST` | `127.0.0.1` | Bind host |
| `NEXUSMIND_PORT` | `8301` | Web/API port |
| `NEXUSMIND_VAULT_ROOT` | `./vault` | Local knowledge directory |
| `NEXUSMIND_GIT_SYNC_INTERVAL` | `300` | Git sync interval in seconds, minimum 60 |
## Project Layout

```text
nexus-mind/
├─ src/nexusmind/        # Core backend, API, CLI, and Web UI
├─ scripts/              # Service and maintenance scripts
├─ tests/                # Automated tests
├─ README.md             # English project overview (default)
├─ README_CN.md          # 中文项目说明
├─ USER_MANUAL.md        # English user manual (default)
├─ USER_MANUAL_CN.md     # 中文用户手册
└─ pyproject.toml
```

Local runtime data such as `vault/` and `workflow-config.json` is intentionally excluded from source control.

## Deployment Modes

### Local

Local mode provides the complete feature set: local folder browsing, Git Log/Status collection, PDF/DOCX extraction, and a filesystem Vault.

```bash
pip install -e ".[local]"
python scripts/vault_service.py
```

### Docker

```bash
docker compose up -d --build
```

The `nexusmind-data` volume persists `/data`. To collect Git repositories from Docker, mount a host source directory such as `D:/codex:/workspaces:ro`, then select paths under `/workspaces` in the Web console.

### Cloudflare Workers

Cloud mode uses **Python Workers + FastAPI + D1 + R2**. A Worker does not browse your computer or execute local `git`; the Local Agent collects complete Git history and performs incremental two-way knowledge-base synchronization over HTTPS. Text knowledge files synchronize bidirectionally between the local Vault and D1 with create, update, delete, version checks, and conflict protection, while Git activity remains a structured event stream in D1. Cloud weekly reviews filter Git events by each repository's effective `user.email`.

Cloudflare deployment requires Python 3.13+, Node.js/npm, and `uv >= 0.12.3`:

```bash
cp wrangler.example.jsonc wrangler.jsonc
npx wrangler d1 create nexusmind
npx wrangler r2 bucket create nexusmind-files
```

Copy the generated D1 `database_id` into `wrangler.jsonc`, then run:

```bash
npx wrangler secret put SYNC_TOKEN
npx wrangler d1 migrations apply nexusmind --remote
uv sync --group cloudflare
uv run --group cloudflare pywrangler deploy
```

Configure the Local Agent for two-way knowledge-base and Git activity synchronization:

```text
NEXUSMIND_CLOUD_SYNC_URL=https://<worker>.workers.dev
NEXUSMIND_CLOUD_SYNC_TOKEN=<same value as SYNC_TOKEN>
```

## MCP Integration

NexusMind includes a local **stdio MCP server** for MCP-compatible clients such as Claude Desktop and Cursor. The MCP server operates on the same local Vault and permission/OCC rules as the Web/API service.

### Start the MCP server

After installing the local dependencies:

```bash
pip install -e ".[local]"
nexusmind serve --stdio
```

The equivalent script entrypoint is:

```bash
python scripts/mcp_server.py
```

The stdio process must be started by the MCP client. Do not run it as a normal interactive shell service and then try to connect to a TCP port.

### Configure the Vault used by MCP

By default MCP uses the same local Vault configuration as NexusMind. To point it at a different Vault, set:

```text
NEXUSMIND_VAULT_ROOT=/absolute/path/to/vault
```

Windows example:

```powershell
$env:NEXUSMIND_VAULT_ROOT="D:\Knowledge\NexusMind"
nexusmind serve --stdio
```

macOS / Linux:

```bash
export NEXUSMIND_VAULT_ROOT="$HOME/Knowledge/NexusMind"
nexusmind serve --stdio
```

### MCP client configuration

When `nexusmind` is installed and available on `PATH`, a typical stdio MCP configuration is:

```json
{
  "mcpServers": {
    "nexusmind": {
      "command": "nexusmind",
      "args": ["serve", "--stdio"],
      "env": {
        "NEXUSMIND_VAULT_ROOT": "/absolute/path/to/vault"
      }
    }
  }
}
```

On Windows, use a Windows path for `NEXUSMIND_VAULT_ROOT`, for example `D:\\Knowledge\\NexusMind`.

If the executable is not on `PATH`, use an absolute executable path or invoke the project script through Python.

### MCP tools

The current stdio server exposes these tools:

- `vault_read`: read note content, version, frontmatter, tags, links, and backlinks.
- `vault_patch`: create/update writable notes with OCC `ifMatch` protection.
- `vault_search`: search by text/regex, folder, tags, and frontmatter properties.
- `vault_list_unresolved`: list unresolved Wikilinks / broken links.
- `vault_find_orphans`: list notes without incoming links.
- `vault_compile`: compile Raw sources into a Domain knowledge card.
- `vault_compile_pending`: preview uncompiled Raw sources.
- `vault_incremental_compile`: compile all pending Raw sources and rebuild indexes.
- `vault_rebuild_indices`: rebuild the Master Index and sub-indexes.
- `vault_generate_canvas`: generate a validated Obsidian Canvas.
- `vault_ingest`: ingest Markdown into the immutable Raw reference layer.
- `vault_weekly_review`: generate an ISO-week review.

### Deployment boundaries

- **Local / Local Agent**: full stdio MCP support. This is the recommended MCP mode.
- **Docker**: MCP can run inside the container, but the MCP client must launch the container command with stdio attached and the Vault must be mounted into the container.
- **Cloudflare Workers**: the current Worker exposes HTTP knowledge endpoints under `/mcp/*`, but it is **not** a remote MCP transport endpoint. The standard MCP stdio server remains a Local Agent capability.
## Local Agent Desktop App

For daily use, the recommended Local Agent is the tray application rather than a permanently open terminal.

Install and start it in development mode:

```bash
pip install -e ".[agent]"
nexusmind-agent
```

The Agent configuration window manages:

- local API enable/disable, host, port, and data directory;
- Cloud / Cloudflare API URL and sync token;
- one or more Git collection folders;
- automatic sync interval;
- start minimized;
- start automatically when the user logs in.

Closing the configuration window keeps the Agent running in the system tray. Use the tray menu to reopen configuration, sync immediately, reload configuration, or quit.

Saving configuration performs a **hot apply**: the active collector and optional local API process are restarted with the new settings without quitting the Agent. The configuration file is also monitored, so external edits are reloaded automatically.

Build a native package on the target operating system:

```bash
pip install -e ".[agent,build]"
python packaging/build_agent.py
```

Build outputs are:

- Windows: `dist/NexusMindAgent.exe`
- macOS: `dist/NexusMindAgent.app`
- Linux: `dist/NexusMindAgent`

GitHub Actions also contains a Windows/macOS/Linux build matrix. Each platform is built natively because PyInstaller binaries are platform-specific.

## Test

```bash
pip install -e ".[local,dev]"
python -m pytest -q
```

For end-user instructions, see [USER_MANUAL.md](USER_MANUAL.md).
