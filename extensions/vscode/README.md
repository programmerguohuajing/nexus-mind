# NexusMind for VS Code

让知识回流到编码现场（产品设计文档 P3-2）：

- **相关知识侧边栏**：打开文件或选中代码后，自动用混合检索推荐相关知识卡片，点击在编辑器旁打开全文。
- **记录排查笔记**：选中报错堆栈 → 命令 `NexusMind: 记录排查笔记`，自动带上文件路径与行号写入知识库 Raw 层。
- **问知识库**：命令 `NexusMind: 问知识库`，基于 Ask My Vault 回答并列出来源。
- **项目知识清单**：命令 `NexusMind: 查看当前项目知识清单`，按 `.nexusmind.yaml` 项目绑定列出作用域内的知识。
- **状态栏**：显示本地服务健康状态，点击打开管理台。

## 开发与调试

```bash
cd extensions/vscode
npm install
npm run compile
```

然后用 VS Code 打开本目录，按 F5 启动扩展开发宿主。

先决条件：本地 NexusMind 服务已启动（`python scripts/vault_service.py`）。
设置项：`nexusmind.serverUrl`（默认 http://127.0.0.1:8301）、`nexusmind.apiToken`。
