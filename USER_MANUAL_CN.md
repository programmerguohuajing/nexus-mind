# NexusMind 用户手册

[English](USER_MANUAL.md)

## 1. 启动系统

安装依赖后运行：

```bash
python scripts/vault_service.py
```

浏览器打开 `http://127.0.0.1:8301/`。

NexusMind 可以在没有任何历史 Vault 数据的情况下启动。首次运行看到空白数据属于正常状态。

## 2. 工作流采集

进入左侧 **工作流**。

点击 **添加文件夹**，在目录选择器中选择一个或多个本机目录。可以多次打开选择器继续追加，已有目录不会被覆盖。

选择规则：

- 选择 Git 仓库目录：采集该仓库。
- 选择上级目录：采集其直接子目录中的 Git 仓库。
- 重复目录会自动去重。
- 删除目录后需要点击 **保存配置**。
保存后系统会按照配置采集：

- 当前分支；
- 当天 Commit；
- Conventional Commit 类型与 scope；
- Merge / PR 线索；
- Tag / Release；
- 工作区未提交状态；
- 变更文件摘要。

默认每 5 分钟同步一次，也可以点击 **立即同步**。

## 3. 资料入库

进入 **资料入库**。

支持上传：

- `.md`
- `.txt`
- `.pdf`
- `.docx`

原文件保存在本地 Vault 的 Raw 区域，同时生成可编译 Markdown。PDF 目前提取可搜索文本层，不对纯扫描图片自动 OCR。

## 4. 编译知识

进入 **编译队列** 查看尚未编译的 Raw 资料。

编译后知识进入 Domain 层，并保留来源引用、审计记录和冲突信息。

Raw 层按设计不允许普通写操作覆盖原始来源。
## 5. 知识搜索与阅读

进入 **知识搜索**：

- 搜索标题和正文；
- 打开 Markdown 富文本卡片；
- 点击 Wikilink 跳转；
- 查看正向链接；
- 查看 Backlinks；
- 内容过长时卡片内部滚动。

## 6. 知识图谱与 Canvas

进入 **知识图谱**：

- 查看全库关系；
- 过滤正式知识、项目或日志；
- 点击图节点打开知识卡片；
- 浏览现有 `.canvas` 文件及节点关系。

Obsidian 不是必需客户端，只是可选的兼容编辑器。

## 7. 知识治理

进入 **知识治理**：

- 查看未解析链接；
- 查看孤岛笔记；
- 重建索引；
- 检查 Vault 结构健康状态。

治理结果属于当前快照，不应在没有历史快照时解释成趋势。
## 8. 周复盘

进入 **周复盘**，选择 ISO 周并生成。

周报会结合：

- Git Commit；
- Conventional Commit 分类；
- 活跃仓库；
- Release / Tag；
- Daily Log；
- 知识编译记录；
- 治理状态。

系统会提炼功能交付、安全加固、问题修复、CI/发布工程、文档沉淀等主线，并保留 Commit 明细用于追溯。

## 9. 本地数据与隐私

以下数据默认不进入 GitHub：

- `vault/`
- `workflow-config.json`
- `docs/`
- `.env*`
- 缓存、日志、构建产物

如需备份个人 Vault，请使用你自己的私有存储方案，不建议直接提交到项目仓库。

## 10. 停止与重新启动

终端中按 `Ctrl+C` 停止服务。

再次运行 `python scripts/vault_service.py` 即可启动；已保存的本地配置仍会生效。

## 11. 部署方式

NexusMind 支持三种部署方式：

- **本地直接运行**：完整支持本机文件夹选择、Git 采集、本地 Vault、PDF/DOCX 提取。
- **Docker**：使用 `docker compose up -d --build`，数据持久化在 `/data`；如需采集 Git，需要把宿主机代码目录挂载到容器。
- **Cloudflare Workers**：使用 Python Worker + FastAPI + D1 + R2。Worker 不访问本机目录，本地 NexusMind 作为 Local Agent 采集完整 Git Log 并同步到云端。

云端同步需要在 Local Agent 设置：

```text
NEXUSMIND_CLOUD_SYNC_URL=https://<worker>.workers.dev
NEXUSMIND_CLOUD_SYNC_TOKEN=<SYNC_TOKEN>
```

Cloudflare 端会保存完整团队 Git Log，但周复盘只使用各仓库当前 `user.email` 对应的本人提交。

---

## 12. 本地 Agent 桌面程序

Local Agent 可以作为系统托盘程序运行，因此不需要长期保留 CMD 或终端窗口。

配置窗口包含本地 API 开关、Host/Port、本地数据目录、Cloud API 地址、同步 Token、多个 Git 采集文件夹、同步周期、启动后最小化和用户登录后自动启动。

修改配置后点击 **保存并热更新**。Agent 会在保持托盘程序运行的情况下，按新配置重新启动采集任务和可选本地 API 进程。

关闭窗口只会隐藏界面。托盘菜单提供 **打开配置**、**立即同步**、**重新加载配置** 和 **退出**。

Agent 同时监控配置文件，外部修改后也会自动重新加载。

开发环境启动：

```bash
pip install -e ".[agent]"
nexusmind-agent
```

原生构建：

```bash
pip install -e ".[agent,build]"
python packaging/build_agent.py
```

## 13. MCP 客户端配置

NexusMind 内置本地 stdio MCP Server。当 Claude Desktop、Cursor 等 MCP 客户端需要直接访问本地 Vault 时，可以使用这一入口。

手工验证 MCP 服务：

```bash
nexusmind serve --stdio
```

也可以使用：

```bash
python scripts/mcp_server.py
```

正常使用时，应让 MCP 客户端自己启动 stdio 进程：

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

stdio MCP Server 当前提供笔记读取/修改、搜索、死链/孤岛检查、知识编译、资料入库、索引重建、Canvas 生成和周复盘等工具。

主要工具名称：

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

注意：

- `vault_patch` 在提供 `ifMatch` 时使用 OCC 版本校验；
- Raw 参考资料层仍然遵守不可普通覆盖的保护规则；
- MCP 进程与本地 NexusMind 使用同一个 `NEXUSMIND_VAULT_ROOT`；
- stdio MCP 主要用于 Local / Local Agent 模式；
- Cloudflare 的 `/mcp/*` HTTP 路由目前属于 API 接口，不是远程 MCP Transport。
