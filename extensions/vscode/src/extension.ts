import * as vscode from "vscode";

/* NexusMind VS Code 插件（产品设计文档 P3-2）：让知识回流到编码现场。
 * - 侧边栏：根据当前文件/选中代码语义推荐相关知识卡片；
 * - 命令：选中报错一键记排查笔记、问知识库、查看当前项目知识清单；
 * - 状态栏：本地服务健康状态，点击打开管理台。
 */

interface SearchMatch {
  path: string;
  title: string;
  score: number;
  snippet?: string;
}

function config() {
  const cfg = vscode.workspace.getConfiguration("nexusmind");
  return {
    serverUrl: (cfg.get<string>("serverUrl") || "http://127.0.0.1:8301").replace(/\/$/, ""),
    apiToken: cfg.get<string>("apiToken") || "",
  };
}

async function api(path: string, body?: unknown): Promise<any> {
  const { serverUrl, apiToken } = config();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiToken) headers["X-NexusMind-Token"] = apiToken;
  const resp = await fetch(serverUrl + path, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`NexusMind HTTP ${resp.status}（请确认本地服务已启动：${serverUrl}）`);
  }
  return resp.json();
}

class RelatedItem extends vscode.TreeItem {
  constructor(match: SearchMatch) {
    super(match.title, vscode.TreeItemCollapsibleState.None);
    this.description = `相关度 ${match.score}`;
    this.tooltip = `${match.path}\n\n${match.snippet || ""}`;
    this.contextValue = "nexusmindNote";
    this.command = {
      command: "nexusmind.openNote",
      title: "打开笔记",
      arguments: [match.path],
    };
  }
}

class RelatedProvider implements vscode.TreeDataProvider<RelatedItem> {
  private emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;
  private matches: SearchMatch[] = [];
  private message = "打开一个文件后自动推荐相关知识";

  refresh(): void {
    this.emitter.fire();
  }

  setMessage(message: string): void {
    this.message = message;
    this.matches = [];
    this.refresh();
  }

  async updateForEditor(editor: vscode.TextEditor | undefined): Promise<void> {
    if (!editor) {
      this.setMessage("未打开文件");
      return;
    }
    const doc = editor.document;
    const selection = editor.selection;
    const selected = !selection.isEmpty ? doc.getText(selection) : "";
    const contextText = (selected || doc.getText(new vscode.Range(0, 0, Math.min(60, doc.lineCount), 0))).slice(0, 1500);
    const query = `${doc.fileName.split(/[\\/]/).pop()} ${contextText}`.trim();
    try {
      const data = await api("/mcp/vault_search", { query, mode: "hybrid", limit: 12 });
      this.matches = (data.matches || []) as SearchMatch[];
      this.message = this.matches.length ? "" : "没有找到相关知识";
      this.refresh();
    } catch (err) {
      this.setMessage(`服务不可达：${(err as Error).message}`);
    }
  }

  getTreeItem(item: RelatedItem): vscode.TreeItem {
    return item;
  }

  getChildren(): RelatedItem[] {
    if (!this.matches.length) {
      const placeholder = new vscode.TreeItem(this.message);
      return [placeholder as RelatedItem];
    }
    return this.matches.map((m) => new RelatedItem(m));
  }
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

async function openNote(path: string): Promise<void> {
  try {
    const data = await api("/mcp/vault_read", { path });
    const panel = vscode.window.createWebviewPanel("nexusmindNote", data.path, vscode.ViewColumn.Beside, {});
    panel.webview.html = `<!doctype html><html><body style="font-family: sans-serif; padding: 16px">
      <h2>${escapeHtml(data.path)}</h2>
      <pre style="white-space: pre-wrap">${escapeHtml(data.content || "")}</pre>
      <p>反向链接：${(data.backlinks || []).map(escapeHtml).join("、") || "无"}</p>
    </body></html>`;
  } catch (err) {
    void vscode.window.showErrorMessage((err as Error).message);
  }
}

async function captureNote(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    void vscode.window.showWarningMessage("先打开文件并选中要记录的内容（如报错堆栈）");
    return;
  }
  const selected = editor.document.getText(editor.selection);
  if (!selected.trim()) {
    void vscode.window.showWarningMessage("请先选中报错堆栈或代码片段");
    return;
  }
  const title = await vscode.window.showInputBox({ prompt: "排查笔记标题", value: "排查记录" });
  if (!title) return;
  const rel = vscode.workspace.asRelativePath(editor.document.uri);
  const line = editor.selection.start.line + 1;
  const content = [
    `来源文件：${rel}:${line}`,
    "",
    "```",
    selected,
    "```",
    "",
    "## 初步分析",
    "",
    "（待补充）",
  ].join("\n");
  try {
    const res = await api("/mcp/vault_ingest", { title, content, author: "VS Code" });
    void vscode.window.showInformationMessage(`已记录到知识库：${res.path}（提交后将自动进入 Daily Log）`);
  } catch (err) {
    void vscode.window.showErrorMessage((err as Error).message);
  }
}

async function askVault(): Promise<void> {
  const question = await vscode.window.showInputBox({ prompt: "向你的知识库提问" });
  if (!question) return;
  const channel = vscode.window.createOutputChannel("NexusMind 问答");
  channel.show();
  channel.appendLine(`问：${question}\n思考中…`);
  try {
    const data = await api("/api/ask", { question });
    channel.appendLine(`\n答（${data.mode}）：\n${data.answer}`);
    if (data.citations?.length) {
      channel.appendLine("\n来源：");
      for (const c of data.citations) channel.appendLine(`- ${c.path}`);
    }
  } catch (err) {
    channel.appendLine(`\n失败：${(err as Error).message}`);
  }
}

async function projectContext(): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) {
    void vscode.window.showWarningMessage("未打开工作区文件夹");
    return;
  }
  try {
    const data = await api(`/api/project/context?project_path=${encodeURIComponent(folders[0].uri.fsPath)}`);
    const channel = vscode.window.createOutputChannel("NexusMind 项目知识");
    channel.show();
    channel.appendLine(`项目：${data.project}（绑定来源：${data.source}）`);
    channel.appendLine(`作用域：folders=${(data.scope?.folders || []).join(", ")} tags=${(data.scope?.tags || []).join(", ")}`);
    channel.appendLine(`\n知识清单（${data.total}）：`);
    for (const note of data.notes || []) channel.appendLine(`- ${note.path} · ${note.title}`);
    if (data.guidance) channel.appendLine(`\n${data.guidance}`);
  } catch (err) {
    void vscode.window.showErrorMessage((err as Error).message);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const provider = new RelatedProvider();
  context.subscriptions.push(vscode.window.registerTreeDataProvider("nexusmind.related", provider));

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 90);
  status.command = "nexusmind.openConsole";
  context.subscriptions.push(status);

  const health = async () => {
    try {
      const data = await api("/health");
      status.text = `$(book) NexusMind ${data.version || ""}`;
      status.tooltip = `知识库服务正常：${data.vault || ""}`;
    } catch {
      status.text = "$(book) NexusMind 离线";
      status.tooltip = "本地服务未启动：python scripts/vault_service.py";
    }
    status.show();
  };
  void health();
  const timer = setInterval(health, 30000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });

  let debounce: NodeJS.Timeout | undefined;
  const scheduleUpdate = (editor: vscode.TextEditor | undefined) => {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(() => void provider.updateForEditor(editor), 600);
  };
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(scheduleUpdate),
    vscode.window.onDidChangeTextEditorSelection((e) => scheduleUpdate(e.textEditor)),
    vscode.commands.registerCommand("nexusmind.showRelated", () => provider.updateForEditor(vscode.window.activeTextEditor)),
    vscode.commands.registerCommand("nexusmind.openNote", (path: string) => openNote(path)),
    vscode.commands.registerCommand("nexusmind.captureNote", captureNote),
    vscode.commands.registerCommand("nexusmind.askVault", askVault),
    vscode.commands.registerCommand("nexusmind.projectContext", projectContext),
    vscode.commands.registerCommand("nexusmind.openConsole", () => {
      void vscode.env.openExternal(vscode.Uri.parse(config().serverUrl + "/"));
    }),
  );
  scheduleUpdate(vscode.window.activeTextEditor);
}

export function deactivate(): void {}
