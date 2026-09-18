# NexusMind

> A local-first, self-growing engineering knowledge system powered by Git activity, reference ingestion, knowledge compilation, and weekly review.

[中文](README.md)
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
pip install -e .
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e .
```

### Run

```bash
python scripts/vault_service.py
```

Open:

- Web console: `http://127.0.0.1:8301/`
- OpenAPI / Swagger: `http://127.0.0.1:8301/docs`

An empty knowledge base on first launch is expected.
## Configure Git Collection

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

## Use an External Vault

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
├─ README.md             # Bilingual project overview
├─ USER_MANUAL.md        # Bilingual user manual
├─ pyproject.toml
└─ requirements.txt
```

Local runtime data such as `vault/` and `workflow-config.json` is intentionally excluded from source control.

## Test

```bash
pip install -e ".[dev]"
python -m pytest -q
```

For end-user instructions, see [USER_MANUAL.md](USER_MANUAL.md).

