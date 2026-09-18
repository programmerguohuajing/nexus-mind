# NexusMind

> Local-first, self-growing engineering knowledge system powered by Git activity, Markdown knowledge compilation, weekly review, and a Web console.

NexusMind is designed to grow from real work instead of requiring manual knowledge-base maintenance. It can collect configured Git repositories, summarize engineering activity, ingest local references, compile reusable knowledge, and generate evidence-based weekly reports.

**Obsidian is optional.** NexusMind runs independently through its FastAPI service and Web console.

[中文](#中文说明) · [English](#english)

---

# 中文说明

## 核心能力

- **Git 工作流自动采集**：仅采集用户在 Web 管理台明确选择的文件夹。
- **多仓库支持**：可多次添加多个目录；目录本身是 Git 仓库时直接采集，也可扫描其直接 Git 子目录。
- **工作日志自动生长**：commit、branch、Tag、未提交状态自动进入 Daily Log。
- **周复盘提炼**：按 Conventional Commit、仓库、Release/Tag、知识编译结果生成工作周报。
- **资料入库**：支持 Markdown、TXT、PDF、DOCX。
- **知识编译**：Raw 资料增量编译为可复用的 Domain 知识卡片。
- **知识搜索**：全文搜索、Wikilink、Backlinks、知识图谱与 Canvas 浏览。
- **治理能力**：死链、孤岛、索引与 OCC 并发保护。
## 仓库与本地数据边界

公开仓库只保存**可运行的项目代码和产品文档**。以下内容默认不会提交：

- `vault/`：你的本地知识、日志、上传资料和生成内容。
- `workflow-config.json`：你的本机 Git 采集目录配置。
- `docs/`：本地设计过程、走查、草稿等内部文档。
- `.env*`、缓存、构建产物和日志。

因此新克隆的仓库是一个**空白 NexusMind 实例**，不会携带作者的业务数据或个人知识库。

## 快速开始

### 1. 环境要求

- Python 3.10+
- Git
- Windows / macOS / Linux

### 2. 安装

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
### 3. 启动

```bash
python scripts/vault_service.py
```

默认地址：

- Web 管理台: `http://127.0.0.1:8301/`
- OpenAPI / Swagger: `http://127.0.0.1:8301/docs`

首次运行时没有本地知识数据是正常的。

### 4. 配置 Git 采集范围

进入：

`工作流 → 采集范围配置 → 添加文件夹`

目录选择器支持：

- 浏览本机磁盘和目录。
- 一次选择多个文件夹。
- 多次打开选择器继续追加。
- 自动去重。
- 主列表单独删除目录。
- 保存后定时同步。

NexusMind **不会默认扫描任何目录**。

### 5. 使用空白 Vault

默认 Vault 路径是项目根目录下的 `vault/`，该目录属于本地数据，不进入 Git。

也可以指定外部 Vault：

Windows:

```powershell
$env:NEXUSMIND_VAULT_ROOT="D:\Knowledge\NexusMind"
python scripts\vault_service.py
```
macOS / Linux:

```bash
export NEXUSMIND_VAULT_ROOT="$HOME/Knowledge/NexusMind"
python scripts/vault_service.py
```

## 常用配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NEXUSMIND_HOST` | `127.0.0.1` | 服务监听地址 |
| `NEXUSMIND_PORT` | `8301` | Web/API 端口 |
| `NEXUSMIND_VAULT_ROOT` | `./vault` | 本地知识库路径 |
| `NEXUSMIND_GIT_SYNC_INTERVAL` | `300` | Git 自动同步周期，秒；最小 60 |

## 项目结构

```text
nexus-mind/
├─ src/nexusmind/        # 后端核心、API、CLI、Web 静态前端
├─ scripts/              # 服务启动与维护脚本
├─ tests/                # 自动化测试
├─ README.md             # 中英文项目说明
├─ USER_MANUAL.md        # 中英文用户手册
├─ pyproject.toml
└─ requirements.txt
```

本地运行后可能出现 `vault/` 和 `workflow-config.json`，它们被 Git 忽略。

## 测试

```bash
pip install -e ".[dev]"
python -m pytest -q
```

详细操作请参阅 [USER_MANUAL.md](USER_MANUAL.md)。
---

# English

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
