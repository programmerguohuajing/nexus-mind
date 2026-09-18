# NexusMind User Manual

[中文](USER_MANUAL_CN.md)

## 1. Start NexusMind

After installing dependencies, run:

```bash
python scripts/vault_service.py
```

Open `http://127.0.0.1:8301/`.

NexusMind supports a completely empty first-run state. No prebuilt Vault content is required.

## 2. Configure Workflow Collection

Open **Workflow** from the sidebar.

Click **Add Folder** and select one or more local folders. You can reopen the picker repeatedly to append more folders; existing selections are preserved.

Selection behavior:

- Selecting a Git repository folder collects that repository.
- Selecting a parent folder collects direct Git child repositories.
- Duplicate paths are ignored.
- After removing or adding folders, click **Save Configuration**.
The collector records:

- current branch,
- daily commits,
- Conventional Commit type and scope,
- merge / PR hints,
- tags / releases,
- dirty working-tree status,
- changed-file summaries.

Automatic synchronization runs every five minutes by default. **Sync Now** can be used at any time.

## 3. Ingest References

Open **Ingestion**.

Supported file types:

- `.md`
- `.txt`
- `.pdf`
- `.docx`

Original files remain in the local Raw layer and a Markdown representation is generated for compilation. Image-only PDF OCR is not performed automatically.

## 4. Compile Knowledge

Open **Compile Queue** to review pending Raw sources.

Compiled knowledge is written to the Domain layer with provenance, audit information, and conflict preservation.

The Raw layer is protected from normal overwrite operations.
## 5. Search and Read Knowledge

Open **Knowledge Search** to:

- search titles and content,
- read rendered Markdown,
- follow Wikilinks,
- inspect forward links,
- inspect backlinks,
- scroll long notes inside the reader.

## 6. Knowledge Graph and Canvas

Open **Knowledge Graph** to:

- visualize Vault relationships,
- filter by Domain, Projects, or Logs,
- click graph nodes to open notes,
- browse existing `.canvas` files.

Obsidian is optional and is not required to run NexusMind.

## 7. Governance

Open **Knowledge Governance** to:

- inspect unresolved links,
- inspect orphan notes,
- rebuild indexes,
- review current Vault health.

Governance metrics are point-in-time snapshots unless historical snapshots are explicitly stored.
## 8. Weekly Review

Open **Weekly Review**, choose an ISO week, and generate a report.

The report combines:

- Git commits,
- Conventional Commit categories,
- active repositories,
- releases and tags,
- Daily Logs,
- knowledge compilation audit,
- governance status.

NexusMind extracts themes such as feature delivery, security hardening, bug fixes, CI/release engineering, and documentation, while retaining commit details for traceability.

## 9. Local Data and Privacy

The following are intentionally excluded from GitHub:

- `vault/`
- `workflow-config.json`
- `docs/`
- `.env*`
- caches, logs, and build output

Back up your personal Vault separately using a storage method appropriate for private data.

## 10. Stop and Restart

Press `Ctrl+C` in the service terminal to stop NexusMind.

Run `python scripts/vault_service.py` again to restart it. Saved local configuration remains available on that machine.

## 11. Deployment Modes

NexusMind supports three deployment modes:

- **Local**: full local folder browsing, Git collection, filesystem Vault, and PDF/DOCX extraction.
- **Docker**: run `docker compose up -d --build`; persistent data lives under `/data`. Mount host repositories into the container when Git collection is required.
- **Cloudflare Workers**: Python Worker + FastAPI + D1 + R2. The Worker never browses the user's computer; a Local Agent collects complete Git history and synchronizes structured events to the cloud.

Configure cloud replication on the Local Agent:

```text
NEXUSMIND_CLOUD_SYNC_URL=https://<worker>.workers.dev
NEXUSMIND_CLOUD_SYNC_TOKEN=<SYNC_TOKEN>
```

The cloud stores complete team Git history, while weekly reviews only use commits whose author email matches each repository's effective `user.email`.

## 12. Local Agent Desktop App

The Local Agent can run as a system-tray application so no terminal window needs to stay open.

The configuration window includes local API enable/disable, API host/port, local data directory, Cloud API URL, sync token, multiple Git collection folders, sync interval, start minimized, and start automatically at user login.

Click **Save and Hot Apply** after changing settings. The Agent restarts the active collector and optional local API process with the new configuration while keeping the tray application alive.

Closing the window only hides it. The tray menu provides **Open Configuration**, **Sync Now**, **Reload Configuration**, and **Quit**.

The Agent also monitors its configuration file and reloads external changes automatically.

Development launch:

```bash
pip install -e ".[agent]"
nexusmind-agent
```

Native build:

```bash
pip install -e ".[agent,build]"
python packaging/build_agent.py
```

## 13. MCP Client Configuration

NexusMind includes a local stdio MCP server. Use it when an MCP-compatible desktop client needs direct access to the local Vault.

Start it manually for verification:

```bash
nexusmind serve --stdio
```

Alternative:

```bash
python scripts/mcp_server.py
```

For normal MCP use, configure the MCP client to launch the process itself:

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

The stdio server exposes note read/write, search, broken-link/orphan inspection, compilation, ingestion, index rebuild, Canvas generation, and weekly review tools.

Main tool names:

- `vault_read`
- `vault_patch`
- `vault_search`
- `vault_list_unresolved`
- `vault_find_orphans`
- `vault_compile`
- `vault_compile_pending`
- `vault_incremental_compile`
- `vault_rebuild_indices`
- `vault_generate_canvas`
- `vault_ingest`
- `vault_weekly_review`

Important:

- `vault_patch` uses OCC version checks when `ifMatch` is supplied.
- the Raw reference layer remains protected from normal overwrite behavior;
- the MCP process uses the same `NEXUSMIND_VAULT_ROOT` as local NexusMind;
- stdio MCP is intended for Local / Local Agent use;
- Cloudflare `/mcp/*` HTTP routes are API endpoints, not a remote MCP transport endpoint.
