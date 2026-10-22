# NexusMind Web Clipper（浏览器剪藏扩展）

把网页一键剪藏到本地 NexusMind 知识库：整页抓取走服务端正文提取，选中文本直接入库，还支持稍后读列表批量同步。

## 安装（开发者模式）

1. 启动本地 NexusMind 服务：`python scripts/vault_service.py`
2. Chrome / Edge 打开 `chrome://extensions`（Edge 为 `edge://extensions`），开启「开发者模式」。
3. 点击「加载已解压的扩展程序」，选择本目录 `extensions/web-clipper`。

## 使用

- 工具栏弹窗：剪藏整页 / 剪藏选中文本 / 稍后读 / 同步稍后读列表。
- 右键菜单：页面上右键可用同样的三个动作。
- 设置页（扩展详情 → 扩展程序选项）：修改服务地址、API Token、作者署名。

## 与服务端的对应关系

| 动作 | 接口 |
|---|---|
| 剪藏整页 | `POST /api/web-ingest`（服务端抓取正文并写入 Raw 层） |
| 剪藏选中文本 | `POST /mcp/vault_ingest`（直接写入 Raw 层） |
| 稍后读 | 先存扩展本地列表，同步时逐个调用整页剪藏 |

当服务端设置了环境变量 `NEXUSMIND_API_TOKEN` 且请求来自非回环地址时，必须在设置页填写相同 Token。
