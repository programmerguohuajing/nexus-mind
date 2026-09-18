# NexusMind User Manual / 用户手册

[中文](#中文用户手册) · [English](#english-user-manual)

---

# 中文用户手册

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
---

# English User Manual

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
