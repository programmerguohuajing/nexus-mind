# NexusMind

> 本地优先、自生长的工程知识系统：从 Git 工作活动、资料、知识编译和周复盘中持续形成可复用知识。

[English](README.md)
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
pip install -e ".[local]"
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e ".[local]"
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
├─ README.md             # English project overview（默认）
├─ README_CN.md          # 中文项目说明
├─ USER_MANUAL.md        # English user manual（默认）
├─ USER_MANUAL_CN.md     # 中文用户手册
└─ pyproject.toml
```

本地运行后可能出现 `vault/` 和 `workflow-config.json`，它们被 Git 忽略。

## 三种部署模式

### 本地直接运行

本地模式提供完整能力，包括本机文件夹选择、Git Log/Status 采集、PDF/DOCX 提取和本地 Vault：

```bash
pip install -e ".[local]"
python scripts/vault_service.py
```

### Docker

```bash
docker compose up -d --build
```

默认使用 Docker volume `nexusmind-data` 持久化 `/data`。如果需要在容器内采集 Git，请把宿主机代码目录额外挂载到容器，例如 `D:/codex:/workspaces:ro`，然后在 Web 管理台选择 `/workspaces` 下的目录。

### Cloudflare Workers

Cloudflare 模式使用 **Python Worker + FastAPI + D1 + R2**。Worker 不直接访问用户电脑文件系统，也不执行本机 `git`；本地 NexusMind 作为 Local Agent 负责采集完整 Git Log，再通过 HTTPS 同步到 Worker。云端周复盘只使用各仓库当前 `user.email` 对应的本人提交。

Cloudflare 部署要求 Python 3.13+、Node.js/npm 和 `uv >= 0.12.3`：

```bash
copy wrangler.example.jsonc wrangler.jsonc
npx wrangler d1 create nexusmind
npx wrangler r2 bucket create nexusmind-files
```

把 D1 输出的 `database_id` 填入 `wrangler.jsonc`，然后：

```bash
npx wrangler secret put SYNC_TOKEN
npx wrangler d1 migrations apply nexusmind --remote
uv sync --group cloudflare
uv run --group cloudflare pywrangler deploy
```

本地 Agent 配置云端同步：

```text
NEXUSMIND_CLOUD_SYNC_URL=https://<worker>.workers.dev
NEXUSMIND_CLOUD_SYNC_TOKEN=<与 SYNC_TOKEN 相同>
```

## MCP 集成

NexusMind 内置本地 **stdio MCP Server**，可以供 Claude Desktop、Cursor 等支持 MCP 的客户端直接调用。MCP 与 Web/API 使用同一个本地 Vault，并遵循相同的权限规则和 OCC 并发保护。

### 启动 MCP 服务

安装本地依赖后：

```bash
pip install -e ".[local]"
nexusmind serve --stdio
```

也可以直接使用项目脚本：

```bash
python scripts/mcp_server.py
```

stdio MCP 进程应由 MCP 客户端负责启动。它不是一个需要手工常驻后再连接 TCP 端口的网络服务。

### 配置 MCP 使用的 Vault

默认情况下，MCP 使用 NexusMind 相同的本地 Vault 配置。如果需要指定其他 Vault，可以设置：

```text
NEXUSMIND_VAULT_ROOT=/absolute/path/to/vault
```

Windows 示例：

```powershell
$env:NEXUSMIND_VAULT_ROOT="D:\Knowledge\NexusMind"
nexusmind serve --stdio
```

macOS / Linux：

```bash
export NEXUSMIND_VAULT_ROOT="$HOME/Knowledge/NexusMind"
nexusmind serve --stdio
```

### MCP 客户端配置

安装 NexusMind 后，如果 `nexusmind` 命令已经在 `PATH` 中，典型的 stdio MCP 配置如下：

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

Windows 下请把 `NEXUSMIND_VAULT_ROOT` 改成 Windows 路径，例如 `D:\\Knowledge\\NexusMind`。

如果 `nexusmind` 不在 `PATH` 中，可以把 `command` 改成可执行文件绝对路径，或者通过 Python 调用项目里的 `scripts/mcp_server.py`。

### MCP 工具

当前 stdio MCP Server 暴露以下工具：

- `vault_read`：读取笔记正文、版本、Frontmatter、标签、正反向链接。
- `vault_patch`：通过 OCC `ifMatch` 创建或更新允许写入的笔记。
- `vault_search`：按全文/正则、目录、标签和 Frontmatter 属性搜索。
- `vault_list_unresolved`：检查未解析 Wikilink / 死链。
- `vault_find_orphans`：检查没有传入反链的孤岛笔记。
- `vault_compile`：把 Raw 来源编译成 Domain 正式知识卡片。
- `vault_compile_pending`：预览尚未编译的 Raw 来源。
- `vault_incremental_compile`：编译全部待处理 Raw 并重建索引。
- `vault_rebuild_indices`：重建 Master Index 和二级索引。
- `vault_generate_canvas`：生成经过校验的 Obsidian Canvas。
- `vault_ingest`：向不可覆盖的 Raw 参考资料层写入 Markdown。
- `vault_weekly_review`：按 ISO 周生成周复盘。

### 不同部署模式下的边界

- **Local / Local Agent**：完整支持 stdio MCP，也是推荐的 MCP 使用方式。
- **Docker**：可以在容器内运行 MCP，但 MCP 客户端需要以 stdio 方式启动容器命令，并把 Vault 挂载到容器中。
- **Cloudflare Workers**：当前 Worker 提供了 `/mcp/*` HTTP 知识接口，但它们**不是远程 MCP Transport**；标准 stdio MCP Server 仍属于 Local Agent 能力。
## 本地 Agent 桌面程序

日常使用建议运行系统托盘 Agent，而不是长期保持 CMD/终端窗口开启。

开发环境安装与启动：

```bash
pip install -e ".[agent]"
nexusmind-agent
```

Agent 配置窗口可以管理：

- 是否启动本地 API、Host、Port 和本地数据目录；
- Cloud / Cloudflare API 地址与同步 Token；
- 一个或多个 Git 采集文件夹；
- 自动同步周期；
- 启动后最小化；
- 用户登录系统后自动启动。

关闭配置窗口不会退出 Agent，程序会继续驻留系统托盘。托盘菜单支持重新打开配置、立即同步、重新加载配置和退出。

点击“保存并热更新”后会立即应用新配置：采集任务和可选本地 API 会按新配置重新运行，不需要退出 Agent。配置文件本身也会被监控，外部修改后同样可以自动重新加载。

在对应目标系统上构建原生程序：

```bash
pip install -e ".[agent,build]"
python packaging/build_agent.py
```

构建产物：

- Windows：`dist/NexusMindAgent.exe`
- macOS：`dist/NexusMindAgent.app`
- Linux：`dist/NexusMindAgent`

GitHub Actions 已提供 Windows / macOS / Linux 三平台构建矩阵。由于 PyInstaller 产物与目标平台绑定，每个平台采用原生构建。

## 测试

```bash
pip install -e ".[local,dev]"
python -m pytest -q
```

详细操作请参阅 [USER_MANUAL_CN.md](USER_MANUAL_CN.md)。
