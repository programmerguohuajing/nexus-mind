const app = document.getElementById("app");
const titleEl = document.getElementById("pageTitle");
const toastEl = document.getElementById("toast");
const serviceDot = document.getElementById("serviceDot");
const serviceText = document.getElementById("serviceText");
const state = { view: "dashboard", selectedNote: null, uploadFiles: [], runtime: null };
const t = (key, params) => window.NexusUI?.t(key, params) ?? key;

const titleKeys = {
  dashboard: "dashboard.title",
  search: "nav.search",
  graph: "nav.graph",
  ingest: "nav.ingest",
  compile: "nav.compile",
  governance: "nav.governance",
  workflow: "nav.workflow",
  review: "nav.review"
};

const esc = (value = "") => String(value)
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function toast(message, error = false) {
  toastEl.textContent = message;
  toastEl.className = "toast show" + (error ? " error" : "");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => toastEl.className = "toast", 2600);
}

async function api(url, options = {}) {
  const config = { ...options };
  if (!(config.body instanceof FormData)) {
    config.headers = { "Content-Type": "application/json", ...(config.headers || {}) };
  }
  const response = await fetch(url, config);
  if (!response.ok) {
    let detail = response.status + " " + response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}
function setLoading(active) {
  app.classList.toggle("loading", active);
}

function statsHtml(data) {
  const caps = state.runtime?.capabilities || {};
  const cards = [
    '<div class="card"><div class="stat-label">' + t("dashboard.allMarkdown") + '</div><div class="stat-value">' + data.notes + '</div><div class="stat-note">' + t("dashboard.vaultSize") + '</div></div>',
    '<div class="card"><div class="stat-label">' + t("dashboard.domainNotes") + '</div><div class="stat-value">' + data.domain_notes + '</div><div class="stat-note">' + t("dashboard.domainLayer") + '</div></div>',
    '<div class="card"><div class="stat-label">' + t("dashboard.rawSources") + '</div><div class="stat-value">' + data.raw_sources + '</div><div class="stat-note">' + t("dashboard.rawLayer") + '</div></div>'
  ];
  if (caps.knowledge_compile !== false) {
    cards.push('<div class="card"><div class="stat-label">' + t("dashboard.pending") + '</div><div class="stat-value">' + data.pending_compile + '</div><div class="stat-note">' + (data.pending_compile ? t("dashboard.pendingWait") : t("dashboard.queueEmpty")) + '</div></div>');
  }
  return '<div class="grid stats">' + cards.join("") + '</div>';
}

async function renderDashboard() {
  setLoading(true);
  try {
    const data = await api("/api/dashboard");
    const recent = data.recent_compilations.length
      ? data.recent_compilations.map(function(x) {
          return '<div class="list-item"><div><strong>' + esc(x) + '</strong><p>' + t("dashboard.compileAudit") + '</p></div><span class="badge ok">' + t("dashboard.completed") + '</span></div>';
        }).join("")
      : '<div class="empty">' + t("dashboard.noCompile") + '</div>';

    const caps = state.runtime?.capabilities || {};
    let sections = statsHtml(data);
    if (caps.governance !== false || caps.knowledge_compile !== false) {
      sections += '<div class="section-title"><h2>' + t("dashboard.health") + '</h2><span class="muted">' + t("dashboard.realtime") + '</span></div><div class="grid two">';
      if (caps.governance !== false) {
        sections += '<div class="card"><h3>' + t("dashboard.governance") + '</h3>'
          + '<div class="metric-line"><span class="muted">' + t("dashboard.broken") + '</span><strong>' + data.broken_links + '</strong></div>'
          + '<div class="metric-line"><span class="muted">' + t("dashboard.orphans") + '</span><strong>' + data.orphans + '</strong></div>'
          + '<div class="metric-line"><span class="muted">' + t("dashboard.version") + '</span><strong>v' + esc(data.version) + '</strong></div>'
          + '<div class="metric-line"><span class="muted">Vault</span><span class="path">' + esc(data.vault) + '</span></div>'
          + '<div class="actions" style="margin-top:14px"><button class="btn ghost" onclick="switchView(\'governance\')">' + t("dashboard.enterGovernance") + '</button></div></div>';
      }
      if (caps.knowledge_compile !== false) {
        sections += '<div class="card"><h3>' + t("dashboard.recentCompile") + '</h3><div class="list">' + recent + '</div>'
          + '<div class="actions" style="margin-top:14px"><button class="btn ghost" onclick="switchView(\'compile\')">' + t("dashboard.compileQueue") + '</button></div></div>';
      }
      sections += '</div>';
    }
    const quickActions = [
      '<button class="btn ghost" onclick="switchView(\'search\')">' + t("dashboard.search") + '</button>',
      caps.uploads === false ? '' : '<button class="btn ghost" onclick="switchView(\'ingest\')">' + t("dashboard.ingest") + '</button>',
      caps.knowledge_compile === false ? '' : '<button class="btn ghost" onclick="runCompile()">' + t("dashboard.compile") + '</button>',
      caps.weekly_review === false ? '' : '<button class="btn ghost" onclick="switchView(\'review\')">' + t("dashboard.review") + '</button>'
    ].join("");
    app.innerHTML = sections
      + '<div class="section-title"><h2>' + t("dashboard.quick") + '</h2><span class="muted">' + t("dashboard.common") + '</span></div>'
      + '<div class="card"><div class="actions">' + quickActions + '</div></div>';
  } catch (e) {
    app.innerHTML = '<div class="empty">' + esc(t("dashboard.loadFailed", { error: e.message })) + '</div>';
  } finally {
    setLoading(false);
  }
}
function stripFrontmatter(content) {
  if (!content.startsWith("---")) return content;
  const end = content.indexOf("\n---", 3);
  return end >= 0 ? content.slice(end + 4).replace(/^\s+/, "") : content;
}

function inlineMarkdown(value) {
  let text = esc(value);
  const codeTokens = [];
  text = text.replace(/`([^`]+)`/g, function(_, code) {
    const token = "@@INLINE_CODE_" + codeTokens.length + "@@";
    codeTokens.push("<code>" + code + "</code>");
    return token;
  });
  text = text.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, function(_, target, alias) {
    const label = alias || target.split("/").pop();
    return '<button class="wiki-link" data-wiki="' + esc(target) + '">' + esc(label) + '</button>';
  });
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  text = text.replace(/(^|\s)\*([^*]+)\*(?=\s|$)/g, "$1<em>$2</em>");
  codeTokens.forEach(function(html, index) {
    text = text.replace("@@INLINE_CODE_" + index + "@@", html);
  });
  return text;
}

function splitMarkdownRow(line) {
  let body = line.trim();
  if (body.startsWith("|")) body = body.slice(1);
  if (body.endsWith("|")) body = body.slice(0, -1);
  const cells = [];
  let current = "";
  let wikiDepth = 0;
  for (let i = 0; i < body.length; i++) {
    const pair = body.slice(i, i + 2);
    if (pair === "[[") { wikiDepth++; current += pair; i++; continue; }
    if (pair === "]]" && wikiDepth) { wikiDepth--; current += pair; i++; continue; }
    if (body[i] === "|" && wikiDepth === 0) {
      cells.push(current.trim());
      current = "";
    } else {
      current += body[i];
    }
  }
  cells.push(current.trim());
  return cells;
}

function renderMarkdown(content) {
  const lines = stripFrontmatter(content).replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inCode = false;
  let codeLang = "";
  let codeLines = [];
  let listType = null;

  function closeList() {
    if (listType) html.push("</" + listType + ">");
    listType = null;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^\s*```(.*)$/);
    if (fence) {
      closeList();
      if (!inCode) {
        inCode = true;
        codeLang = fence[1].trim();
        codeLines = [];
      } else {
        html.push('<pre class="md-code"><code data-lang="' + esc(codeLang) + '">' + esc(codeLines.join("\n")) + "</code></pre>");
        inCode = false;
        codeLang = "";
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }

    const next = lines[i + 1] || "";
    if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next)) {
      closeList();
      const headers = splitMarkdownRow(line);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitMarkdownRow(lines[i]));
        i++;
      }
      i--;
      html.push('<div class="md-table-wrap"><table><thead><tr>'
        + headers.map(function(cell) { return "<th>" + inlineMarkdown(cell) + "</th>"; }).join("")
        + "</tr></thead><tbody>"
        + rows.map(function(row) {
            return "<tr>" + row.map(function(cell) { return "<td>" + inlineMarkdown(cell) + "</td>"; }).join("") + "</tr>";
          }).join("")
        + "</tbody></table></div>");
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push("<h" + level + ">" + inlineMarkdown(heading[2]) + "</h" + level + ">");
      continue;
    }
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      closeList(); html.push("<hr>"); continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      closeList(); html.push("<blockquote>" + inlineMarkdown(quote[1]) + "</blockquote>"); continue;
    }
    const task = line.match(/^\s*[-*]\s+\[([ xX])\]\s+(.+)$/);
    if (task) {
      if (listType !== "ul") { closeList(); listType = "ul"; html.push('<ul class="md-list">'); }
      html.push('<li class="md-task"><input type="checkbox" disabled ' + (task[1].toLowerCase() === "x" ? "checked" : "") + '> <span>' + inlineMarkdown(task[2]) + "</span></li>");
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
    if (bullet) {
      if (listType !== "ul") { closeList(); listType = "ul"; html.push('<ul class="md-list">'); }
      html.push("<li>" + inlineMarkdown(bullet[1]) + "</li>");
      continue;
    }
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      if (listType !== "ol") { closeList(); listType = "ol"; html.push("<ol>"); }
      html.push("<li>" + inlineMarkdown(ordered[1]) + "</li>");
      continue;
    }
    closeList();
    if (!line.trim()) continue;
    html.push("<p>" + inlineMarkdown(line) + "</p>");
  }
  closeList();
  if (inCode) {
    html.push('<pre class="md-code"><code>' + esc(codeLines.join("\n")) + "</code></pre>");
  }
  return html.join("");
}

function bindWikiLinks(container) {
  container.querySelectorAll("[data-wiki]").forEach(function(el) {
    el.addEventListener("click", function() { openWikiLink(el.dataset.wiki); });
  });
}

async function openWikiLink(target) {
  try {
    const data = await api("/api/resolve-link?target=" + encodeURIComponent(target));
    if (data.status === "ambiguous") {
      toast(t("search.ambiguous", { count: data.matches.length }), true);
      return;
    }
    await navigateToNote(data.path);
  } catch (e) {
    toast(t("search.openFailed", { target }), true);
  }
}

async function navigateToNote(path) {
  if (state.view !== "search" || !document.getElementById("noteViewer")) {
    await window.switchView("search");
  }
  await openNote(path);
}

function searchTemplate() {
  return '<div class="toolbar">'
    + '<input id="searchQuery" class="input" placeholder="' + esc(t("search.placeholder")) + '" />'
    + '<select id="searchFolder" class="select">'
    + '<option value="40-Domain">' + t("search.domain") + '</option><option value="">' + t("search.all") + '</option>'
    + '<option value="20-Projects">' + t("search.projects") + '</option><option value="30-Logs">' + t("search.logs") + '</option>'
    + '<option value="60-References">' + t("search.raw") + '</option></select>'
    + '<button class="btn" onclick="runSearch()">' + t("search.action") + '</button></div>'
    + '<div class="split"><div class="card"><h3>' + t("search.results") + '</h3>'
    + '<div id="searchResults" class="list"><div class="empty">' + t("search.start") + '</div></div></div>'
    + '<div class="card viewer"><h3>' + t("search.note") + '</h3>'
    + '<div id="noteViewer" class="empty">' + t("search.select") + '</div></div></div>';
}

async function runSearch() {
  const query = document.getElementById("searchQuery").value.trim();
  const folder = document.getElementById("searchFolder").value || null;
  const resultsEl = document.getElementById("searchResults");
  resultsEl.innerHTML = '<div class="empty">' + t("search.searching") + '</div>';
  try {
    const data = await api("/mcp/vault_search", {
      method: "POST",
      body: JSON.stringify({ query: query, folder: folder, limit: 50 })
    });
    if (!data.matches.length) {
      resultsEl.innerHTML = '<div class="empty">' + t("search.empty") + '</div>';
      return;
    }
    resultsEl.innerHTML = data.matches.map(function(item) {
      const safePath = JSON.stringify(item.path).replaceAll('"', '&quot;');
      const tags = (item.tags || []).slice(0, 5).map(function(tag) {
        return '<span class="badge">' + esc(tag) + '</span>';
      }).join("");
      return '<div class="result" data-path="' + esc(item.path) + '">'
        + '<div class="result-head"><span class="result-title">' + esc(item.title) + '</span><span class="badge">' + item.score + '</span></div>'
        + '<div class="path">' + esc(item.path) + '</div>'
        + '<div class="snippet">' + esc(item.snippet || "") + '</div>'
        + '<div class="tags">' + tags + '</div></div>';
    }).join("");
    resultsEl.querySelectorAll(".result").forEach(function(el) {
      el.addEventListener("click", function() { openNote(el.dataset.path); });
    });
  } catch (e) {
    resultsEl.innerHTML = '<div class="empty">' + esc(t("search.failed", { error: e.message })) + '</div>';
  }
}

async function openNote(path) {
  const viewer = document.getElementById("noteViewer");
  if (!viewer) return;
  viewer.innerHTML = '<div class="empty">' + t("search.reading") + '</div>';
  try {
    const data = await api("/mcp/vault_read", {
      method: "POST",
      body: JSON.stringify({ path: path })
    });
    state.selectedNote = data;
    const backlinks = (data.backlinks || []).map(function(raw) {
      const target = raw.replace(/^\[\[/, "").replace(/\]\]$/, "");
      return '<button class="relation-link" data-note-path="' + esc(target) + '">' + esc(target.split("/").pop()) + '</button>';
    }).join("");
    const forward = (data.links || []).map(function(target) {
      return '<button class="relation-link" data-wiki="' + esc(target) + '">' + esc(target.split("/").pop()) + '</button>';
    }).join("");
    viewer.innerHTML = '<div class="result-head"><div><strong>' + esc(data.frontmatter?.title || path.split("/").pop()) + '</strong>'
      + '<div class="path">' + esc(path) + '</div></div><span class="badge">v ' + esc(data.version) + '</span></div>'
      + '<div class="tags">' + (data.tags || []).map(function(t) { return '<span class="badge">' + esc(t) + '</span>'; }).join("") + '</div>'
      + '<div class="note-relations"><div><span class="relation-label">正向链接 ' + data.links.length + '</span><div class="relation-items">' + (forward || '<span class="muted">无</span>') + '</div></div>'
      + '<div><span class="relation-label">反向链接 ' + data.backlinks.length + '</span><div class="relation-items">' + (backlinks || '<span class="muted">无</span>') + '</div></div></div>'
      + '<article class="markdown-body">' + renderMarkdown(data.content) + '</article>';
    bindWikiLinks(viewer);
    viewer.querySelectorAll("[data-note-path]").forEach(function(el) {
      el.addEventListener("click", function() { openNote(el.dataset.notePath); });
    });
  } catch (e) {
    viewer.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>';
  }
}
function ingestTemplate() {
  return '<div class="card ingest-card">'
    + '<div class="tabs"><button id="fileTab" class="tab active" onclick="selectIngestMode(\'file\')">本地文件</button>'
    + '<button id="webTab" class="tab" onclick="selectIngestMode(\'web\')">在线链接</button>'
    + '<button id="textTab" class="tab" onclick="selectIngestMode(\'text\')">粘贴文本</button></div>'
    + '<div id="fileIngestPanel">'
    + '<div id="uploadZone" class="upload-zone" onclick="document.getElementById(\'fileInput\').click()" '
    + 'ondragover="uploadDragOver(event)" ondragleave="uploadDragLeave(event)" ondrop="uploadDrop(event)">'
    + '<input id="fileInput" type="file" multiple accept=".md,.txt,.pdf,.docx" hidden onchange="addUploadFiles(this.files)" />'
    + '<div class="upload-title">拖拽文件到这里，或点击选择文件</div>'
    + '<div class="upload-hint">支持 MD / TXT / PDF / DOCX · 可多选 · 单个文件不超过 50 MB</div></div>'
    + '<div id="uploadQueue" class="upload-queue"></div>'
    + '<div class="form-grid upload-meta"><div class="form-group"><label>作者（可选）</label><input id="uploadAuthor" class="input" placeholder="Unknown" /></div>'
    + '<div class="form-group"><label>来源 URL（可选）</label><input id="uploadUrl" class="input" placeholder="https://..." /></div></div>'
    + '<div class="actions upload-actions"><button id="uploadButton" class="btn" onclick="uploadSelectedFiles()" disabled>开始入库</button>'
    + '<button class="btn ghost" onclick="clearUploadFiles()">清空</button></div>'
    + '<div id="uploadResult"></div>'
    + '<div class="section-title"><h2>已入库资料</h2><div class="actions"><button class="btn ghost" onclick="loadReferences()">刷新</button></div></div>'
    + '<div id="referenceList" class="card reference-list"><div class="empty">正在读取资料库…</div></div></div>'
    + '<div id="webIngestPanel" hidden>'
    + '<div class="web-ingest-intro"><strong>从在线链接提取网页正文</strong><p class="muted">NexusMind 会抓取网页、识别标题并提取主要文本内容，然后写入 Raw 层。本地 Agent 模式支持 localhost 和局域网地址；远端服务模式支持公网 HTTP/HTTPS 网页。</p></div>'
    + '<div class="form-grid"><div class="form-group full"><label>网页链接</label><input id="webIngestUrl" class="input" placeholder="https://example.com/article" /></div>'
    + '<div class="form-group"><label>作者（可选）</label><input id="webIngestAuthor" class="input" placeholder="Unknown" /></div></div>'
    + '<div class="actions" style="margin-top:12px"><button id="webIngestButton" class="btn" onclick="submitWebIngest()">抓取并入库</button></div>'
    + '<div id="webIngestResult"></div></div>'
    + '<div id="textIngestPanel" hidden>'
    + '<div class="form-grid"><div class="form-group"><label>标题</label><input id="ingestTitle" class="input" placeholder="资料标题" /></div>'
    + '<div class="form-group"><label>作者</label><input id="ingestAuthor" class="input" placeholder="Unknown" /></div>'
    + '<div class="form-group full"><label>来源 URL</label><input id="ingestUrl" class="input" placeholder="https://..." /></div>'
    + '<div class="form-group full"><label>Markdown / 文本内容</label><textarea id="ingestContent" class="textarea" placeholder="粘贴正文或 Markdown…"></textarea></div></div>'
    + '<div class="actions" style="margin-top:12px"><button class="btn" onclick="submitIngest()">写入 Raw 层</button></div></div></div>';
}

function selectIngestMode(mode) {
  const isFile = mode === "file";
  const isWeb = mode === "web";
  const isText = mode === "text";
  document.getElementById("fileIngestPanel").hidden = !isFile;
  document.getElementById("webIngestPanel").hidden = !isWeb;
  document.getElementById("textIngestPanel").hidden = !isText;
  document.getElementById("fileTab").classList.toggle("active", isFile);
  document.getElementById("webTab").classList.toggle("active", isWeb);
  document.getElementById("textTab").classList.toggle("active", isText);
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function addUploadFiles(fileList) {
  const allowed = [".md", ".txt", ".pdf", ".docx"];
  Array.from(fileList || []).forEach(function(file) {
    const lower = file.name.toLowerCase();
    const valid = allowed.some(function(ext) { return lower.endsWith(ext); });
    if (!valid) return toast("不支持的文件：" + file.name, true);
    if (file.size > 50 * 1024 * 1024) return toast("文件超过 50 MB：" + file.name, true);
    const duplicate = state.uploadFiles.some(function(x) {
      return x.name === file.name && x.size === file.size && x.lastModified === file.lastModified;
    });
    if (!duplicate) state.uploadFiles.push(file);
  });
  renderUploadQueue();
}

function renderUploadQueue() {
  const el = document.getElementById("uploadQueue");
  const button = document.getElementById("uploadButton");
  if (!el || !button) return;
  button.disabled = state.uploadFiles.length === 0;
  if (!state.uploadFiles.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = '<div class="upload-list-head"><span>已选择文件</span><span>' + state.uploadFiles.length + ' 个</span></div>'
    + state.uploadFiles.map(function(file, index) {
      return '<div class="upload-file"><div class="file-main"><strong>' + esc(file.name) + '</strong><span>' + formatFileSize(file.size) + '</span></div>'
        + '<span class="badge">待上传</span><button class="file-remove" onclick="removeUploadFile(' + index + ')" aria-label="移除">×</button></div>';
    }).join("");
}

function removeUploadFile(index) {
  state.uploadFiles.splice(index, 1);
  renderUploadQueue();
}

function clearUploadFiles() {
  state.uploadFiles = [];
  const input = document.getElementById("fileInput");
  if (input) input.value = "";
  renderUploadQueue();
  const result = document.getElementById("uploadResult");
  if (result) result.innerHTML = "";
}

function uploadDragOver(event) {
  event.preventDefault();
  event.currentTarget.classList.add("dragging");
}

function uploadDragLeave(event) {
  event.currentTarget.classList.remove("dragging");
}

function uploadDrop(event) {
  event.preventDefault();
  event.currentTarget.classList.remove("dragging");
  addUploadFiles(event.dataTransfer.files);
}

async function uploadSelectedFiles() {
  if (!state.uploadFiles.length) return;
  const button = document.getElementById("uploadButton");
  button.disabled = true;
  button.textContent = "正在入库…";
  const form = new FormData();
  state.uploadFiles.forEach(function(file) { form.append("files", file); });
  form.append("author", document.getElementById("uploadAuthor").value.trim() || "Unknown");
  const sourceUrl = document.getElementById("uploadUrl").value.trim();
  if (sourceUrl) form.append("source_url", sourceUrl);
  try {
    const data = await api("/api/uploads", { method: "POST", body: form });
    const resultEl = document.getElementById("uploadResult");
    resultEl.innerHTML = '<div class="upload-summary">' + data.succeeded + ' 个成功，' + data.failed + ' 个失败</div>'
      + '<div class="list">' + data.results.map(function(item) {
          const ok = item.status === "ingested_successfully";
          return '<div class="list-item"><div><strong>' + esc(item.filename) + '</strong><p>'
            + esc(ok ? item.markdown_path : item.error) + '</p></div><span class="badge ' + (ok ? "ok" : "warn") + '">'
            + (ok ? "已入库" : "失败") + '</span></div>';
        }).join("") + '</div>'
      + (data.succeeded ? '<div class="actions" style="margin-top:12px"><button class="btn ghost" onclick="switchView(\'compile\')">查看编译队列</button></div>' : "");
    toast("文件入库完成：" + data.succeeded + "/" + data.total);
    state.uploadFiles = [];
    renderUploadQueue();
    await loadReferences();
  } catch (e) {
    toast(e.message, true);
  } finally {
    button.textContent = "开始入库";
    button.disabled = state.uploadFiles.length === 0;
  }
}

async function submitWebIngest() {
  const url = document.getElementById("webIngestUrl").value.trim();
  const author = document.getElementById("webIngestAuthor").value.trim() || "Unknown";
  const button = document.getElementById("webIngestButton");
  const resultEl = document.getElementById("webIngestResult");
  if (!url) return toast("请输入网页链接", true);

  button.disabled = true;
  button.textContent = "正在抓取…";
  resultEl.innerHTML = '<div class="empty">正在抓取并提取网页正文…</div>';
  try {
    const result = await api("/api/web-ingest", {
      method: "POST",
      body: JSON.stringify({ url: url, author: author })
    });
    resultEl.innerHTML = '<div class="upload-summary">网页已入库</div>'
      + '<div class="list"><div class="list-item"><div><strong>' + esc(result.title || "网页资料") + '</strong>'
      + '<p>' + esc(result.path) + ' · ' + esc(String(result.characters || 0)) + ' 字符</p></div>'
      + '<span class="badge ok">已入库</span></div></div>';
    toast("网页抓取并入库完成");
    await loadReferences();
  } catch (e) {
    resultEl.innerHTML = '<div class="empty">' + esc(e.message) + '</div>';
    toast(e.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "抓取并入库";
  }
}

async function loadReferences() {
  const el = document.getElementById("referenceList");
  if (!el) return;
  el.innerHTML = '<div class="empty">正在读取资料库…</div>';
  try {
    const data = await api("/api/references");
    if (!data.items.length) {
      el.innerHTML = '<div class="empty">暂无已入库文件</div>';
      return;
    }
    el.innerHTML = '<div class="reference-head"><span>文件</span><span>类型</span><span>大小</span><span>状态</span></div>'
      + data.items.map(function(item) {
          const status = item.compiled ? "已编译" : (item.extracted ? "待编译" : "未提取");
          const statusClass = item.compiled ? "ok" : (item.extracted ? "warn" : "");
          const notePath = item.markdown_path
            ? '<div class="reference-sub">' + esc(item.markdown_path) + '</div>'
            : '<div class="reference-sub">未生成 Markdown</div>';
          return '<div class="reference-row">'
            + '<div class="reference-name"><strong>' + esc(item.filename) + '</strong>'
            + '<div class="reference-sub">' + esc(item.original_path) + '</div>' + notePath + '</div>'
            + '<span class="badge">' + esc((item.source_type || "").toUpperCase()) + '</span>'
            + '<span class="reference-size">' + formatFileSize(item.bytes) + '</span>'
            + '<span class="badge ' + statusClass + '">' + status + '</span></div>';
        }).join("");
  } catch (e) {
    el.innerHTML = '<div class="empty">读取资料列表失败：' + esc(e.message) + '</div>';
  }
}

async function submitIngest() {
  const payload = {
    title: document.getElementById("ingestTitle").value.trim(),
    author: document.getElementById("ingestAuthor").value.trim() || "Unknown",
    url: document.getElementById("ingestUrl").value.trim() || null,
    content: document.getElementById("ingestContent").value
  };
  if (!payload.title || !payload.content.trim()) return toast("标题和正文不能为空", true);
  try {
    const result = await api("/mcp/vault_ingest", { method: "POST", body: JSON.stringify(payload) });
    toast("已入库：" + result.path);
    document.getElementById("ingestContent").value = "";
  } catch (e) { toast(e.message, true); }
}

async function renderCompile() {
  app.innerHTML = '<div class="grid two"><div class="card"><h3>待编译素材</h3>'
    + '<div id="pendingList" class="list"><div class="empty">正在扫描…</div></div></div>'
    + '<div class="card"><h3>增量编译控制</h3><p class="muted">扫描 Raw 层未处理素材，编译为带来源锚点的正式知识卡片，并维护索引与审计日志。</p>'
    + '<div class="code-note">Raw 资料只读 · 编译结果可追溯 · 冲突记录保留</div>'
    + '<div class="actions" style="margin-top:16px"><button class="btn" onclick="runCompile()">编译全部待处理素材</button>'
    + '<button class="btn ghost" onclick="loadPending()">重新扫描</button></div></div></div>';
  await loadPending();
}

async function loadPending() {
  const el = document.getElementById("pendingList");
  try {
    const data = await api("/mcp/vault_compile_pending");
    if (!data.sources.length) {
      el.innerHTML = '<div class="empty">编译队列为空<br><span class="muted">所有 Raw 素材均已处理</span></div>';
      return;
    }
    el.innerHTML = data.sources.map(function(path) {
      return '<div class="list-item"><div><strong>' + esc(path.split("/").pop()) + '</strong><p>' + esc(path) + '</p></div><span class="badge warn">pending</span></div>';
    }).join("");
  } catch (e) { el.innerHTML = '<div class="empty">' + esc(e.message) + '</div>'; }
}

async function runCompile() {
  try {
    toast("正在执行增量编译…");
    const result = await api("/mcp/vault_incremental_compile", { method: "POST" });
    toast("编译完成：处理 " + result.results.length + " 条素材");
    if (state.view === "compile") await loadPending();
    if (state.view === "dashboard") await renderDashboard();
  } catch (e) { toast(e.message, true); }
}
async function renderGovernance() {
  app.innerHTML = '<div class="grid stats compact-stats">'
    + '<div class="card"><div class="stat-label">未解析链接</div><div id="brokenCount" class="stat-value">—</div><div class="stat-note">Wikilink 目标不存在</div></div>'
    + '<div class="card"><div class="stat-label">知识孤岛</div><div id="orphanCount" class="stat-value">—</div><div class="stat-note">没有传入反链</div></div></div>'
    + '<div class="section-title"><h2>治理工具</h2><div class="actions">'
    + '<button class="btn ghost" onclick="rebuildIndices()">重建索引</button><button class="btn ghost" onclick="loadGovernance()">重新扫描</button></div></div>'
    + '<div class="grid two"><div class="card"><h3>未解析链接</h3><div id="brokenList" class="list"><div class="empty">扫描中…</div></div></div>'
    + '<div class="card"><h3>知识孤岛</h3><div id="orphanList" class="list"><div class="empty">扫描中…</div></div></div></div>';
  await loadGovernance();
}

async function loadGovernance() {
  try {
    const results = await Promise.all([api("/mcp/vault_list_unresolved"), api("/mcp/vault_find_orphans")]);
    const broken = results[0], orphans = results[1];
    document.getElementById("brokenCount").textContent = broken.total_broken;
    document.getElementById("orphanCount").textContent = orphans.total_orphans;
    document.getElementById("brokenList").innerHTML = broken.broken_links.length
      ? broken.broken_links.slice(0, 50).map(function(x) {
          return '<div class="list-item"><div><strong>' + esc(x.broken_link) + '</strong><p>' + esc(x.source) + '</p></div><span class="badge warn">未解析</span></div>';
        }).join("")
      : '<div class="empty">没有死链</div>';
    document.getElementById("orphanList").innerHTML = orphans.orphans.length
      ? orphans.orphans.slice(0, 50).map(function(x) {
          return '<div class="list-item"><div><strong>' + esc(x.split("/").pop()) + '</strong><p>' + esc(x) + '</p></div><span class="badge">孤岛</span></div>';
        }).join("")
      : '<div class="empty">没有知识孤岛</div>';
  } catch (e) { toast(e.message, true); }
}

async function rebuildIndices() {
  try {
    const data = await api("/mcp/vault_rebuild_indices", { method: "POST" });
    toast("索引已重建：" + Object.keys(data.sub_indices).length + " 个子域");
    await loadGovernance();
  } catch (e) { toast(e.message, true); }
}

async function renderGraph() {
  app.innerHTML = '<div class="toolbar">'
    + '<select id="graphFolder" class="select"><option value="">全库</option><option value="40-Domain">正式知识</option>'
    + '<option value="20-Projects">项目</option><option value="30-Logs">日志</option></select>'
    + '<button class="btn" onclick="loadKnowledgeGraph()">刷新图谱</button></div>'
    + '<div class="graph-layout"><div class="card graph-card"><div class="section-title"><h2>知识关系图</h2><span id="graphStats" class="muted">加载中…</span></div>'
    + '<div id="knowledgeGraph" class="graph-stage"><div class="empty">正在构建关系图…</div></div></div>'
    + '<div class="card canvas-card"><div class="section-title"><h2>Canvas</h2><span id="canvasCount" class="muted">加载中…</span></div>'
    + '<div class="canvas-layout"><div id="canvasList" class="canvas-list"></div><div id="canvasViewer" class="canvas-stage"><div class="empty">选择 Canvas 查看</div></div></div></div></div>';
  await Promise.all([loadKnowledgeGraph(), loadCanvases()]);
}

function graphPositions(nodes, width, height) {
  const sorted = nodes.slice().sort(function(a, b) { return (b.degree || 0) - (a.degree || 0); });
  const centerX = width / 2, centerY = height / 2;
  const maxRadius = Math.min(width, height) * 0.42;
  const positions = {};
  sorted.forEach(function(node, index) {
    if (index === 0) {
      positions[node.id] = { x: centerX, y: centerY };
      return;
    }
    const ring = Math.floor(Math.sqrt(index));
    const ringStart = ring * ring;
    const ringSize = Math.max(6, ring * 6);
    const pos = index - ringStart;
    const angle = (Math.PI * 2 * pos / ringSize) - Math.PI / 2;
    const radius = Math.min(maxRadius, 90 + ring * 68);
    positions[node.id] = {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius
    };
  });
  return positions;
}

async function loadKnowledgeGraph() {
  const stage = document.getElementById("knowledgeGraph");
  const stats = document.getElementById("graphStats");
  if (!stage) return;
  stage.innerHTML = '<div class="empty">正在构建关系图…</div>';
  try {
    const folder = document.getElementById("graphFolder")?.value || "";
    const data = await api("/api/graph" + (folder ? "?folder=" + encodeURIComponent(folder) : ""));
    stats.textContent = data.node_count + " 个节点 · " + data.edge_count + " 条关系";
    if (!data.nodes.length) {
      stage.innerHTML = '<div class="empty">当前范围没有 Markdown 节点</div>';
      return;
    }
    const width = 1200, height = 680;
    const positions = graphPositions(data.nodes, width, height);
    const edges = data.edges.map(function(edge) {
      const a = positions[edge.source], b = positions[edge.target];
      if (!a || !b) return "";
      return '<line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" class="graph-edge" />';
    }).join("");
    const nodes = data.nodes.map(function(node) {
      const pos = positions[node.id];
      const radius = Math.max(7, Math.min(17, 7 + (node.degree || 0) * 1.2));
      const label = node.title.length > 18 ? node.title.slice(0, 18) + "…" : node.title;
      return '<g class="graph-node" data-path="' + esc(node.path) + '" transform="translate(' + pos.x + ',' + pos.y + ')">'
        + '<circle r="' + radius + '"></circle>'
        + '<text y="' + (radius + 14) + '" text-anchor="middle">' + esc(label) + '</text></g>';
    }).join("");
    stage.innerHTML = '<svg class="knowledge-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img">' + edges + nodes + '</svg>';
    stage.querySelectorAll(".graph-node").forEach(function(el) {
      el.addEventListener("click", function() { navigateToNote(el.dataset.path); });
    });
  } catch (e) {
    stage.innerHTML = '<div class="empty">图谱加载失败：' + esc(e.message) + '</div>';
  }
}

async function loadCanvases() {
  const list = document.getElementById("canvasList");
  const count = document.getElementById("canvasCount");
  if (!list) return;
  try {
    const data = await api("/api/canvases");
    count.textContent = data.total + " 个";
    if (!data.items.length) {
      list.innerHTML = '<div class="empty">暂无 Canvas</div>';
      return;
    }
    list.innerHTML = data.items.map(function(item) {
      return '<button class="canvas-item" data-canvas="' + esc(item.path) + '"><strong>' + esc(item.name) + '</strong>'
        + '<span>' + item.nodes + ' 节点 · ' + item.edges + ' 连线</span></button>';
    }).join("");
    list.querySelectorAll("[data-canvas]").forEach(function(el) {
      el.addEventListener("click", function() { openCanvas(el.dataset.canvas); });
    });
    await openCanvas(data.items[0].path);
  } catch (e) {
    list.innerHTML = '<div class="empty">Canvas 列表读取失败：' + esc(e.message) + '</div>';
  }
}

async function openCanvas(path) {
  const viewer = document.getElementById("canvasViewer");
  if (!viewer) return;
  viewer.innerHTML = '<div class="empty">正在读取 Canvas…</div>';
  try {
    const data = await api("/api/canvas?path=" + encodeURIComponent(path));
    const nodes = data.nodes || [];
    const edges = data.edges || [];
    if (!nodes.length) {
      viewer.innerHTML = '<div class="empty">Canvas 没有节点</div>';
      return;
    }
    const minX = Math.min.apply(null, nodes.map(function(n) { return Number(n.x || 0); }));
    const minY = Math.min.apply(null, nodes.map(function(n) { return Number(n.y || 0); }));
    const maxX = Math.max.apply(null, nodes.map(function(n) { return Number(n.x || 0) + Number(n.width || 260); }));
    const maxY = Math.max.apply(null, nodes.map(function(n) { return Number(n.y || 0) + Number(n.height || 140); }));
    const pad = 60;
    const byId = {};
    nodes.forEach(function(n) { byId[n.id] = n; });
    const edgeHtml = edges.map(function(edge) {
      const from = byId[edge.fromNode], to = byId[edge.toNode];
      if (!from || !to) return "";
      const x1 = Number(from.x || 0) + Number(from.width || 260) / 2;
      const y1 = Number(from.y || 0) + Number(from.height || 140) / 2;
      const x2 = Number(to.x || 0) + Number(to.width || 260) / 2;
      const y2 = Number(to.y || 0) + Number(to.height || 140) / 2;
      return '<line class="canvas-edge" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"></line>';
    }).join("");
    const nodeHtml = nodes.map(function(node) {
      const x = Number(node.x || 0), y = Number(node.y || 0);
      const w = Number(node.width || 260), h = Number(node.height || 140);
      const label = node.file ? node.file.split("/").pop() : (node.text || node.id);
      const attr = node.file ? ' data-note="' + esc(node.file) + '"' : "";
      return '<g class="canvas-node"' + attr + '><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="8"></rect>'
        + '<foreignObject x="' + (x + 12) + '" y="' + (y + 10) + '" width="' + (w - 24) + '" height="' + (h - 20) + '">'
        + '<div xmlns="http://www.w3.org/1999/xhtml" class="canvas-node-label">' + esc(label) + '</div></foreignObject></g>';
    }).join("");
    const vb = [minX - pad, minY - pad, Math.max(400, maxX - minX + pad * 2), Math.max(300, maxY - minY + pad * 2)].join(" ");
    viewer.innerHTML = '<div class="canvas-path">' + esc(path) + '</div><svg class="canvas-svg" viewBox="' + vb + '">' + edgeHtml + nodeHtml + '</svg>';
    viewer.querySelectorAll("[data-note]").forEach(function(el) {
      el.addEventListener("click", function() { navigateToNote(el.dataset.note); });
    });
    document.querySelectorAll(".canvas-item").forEach(function(el) {
      el.classList.toggle("active", el.dataset.canvas === path);
    });
  } catch (e) {
    viewer.innerHTML = '<div class="empty">Canvas 读取失败：' + esc(e.message) + '</div>';
  }
}

async function renderWorkflow() {
  if (state.runtime?.mode === "cloudflare") {
    app.innerHTML = '<div class="section-title"><h2>' + t("workflow.cloudTitle") + '</h2><span class="muted">' + t("workflow.cloudHint") + '</span></div>'
      + '<div class="card"><h3>' + t("workflow.cloudApi") + '</h3>'
      + '<p class="muted">' + t("workflow.cloudBody") + '</p></div>'
      + '<div class="section-title"><h2>' + t("workflow.syncStatus") + '</h2><div class="actions"><button class="btn ghost" onclick="loadWorkflow()">' + t("workflow.refresh") + '</button></div></div>'
      + '<div id="workflowSummary" class="grid stats"></div>'
      + '<div class="section-title"><h2>' + t("workflow.syncedRepos") + '</h2><span class="muted">' + t("workflow.fromAgent") + '</span></div>'
      + '<div id="workflowRepos" class="card"><div class="empty">' + t("workflow.loading") + '</div></div>';
    await loadWorkflow();
    return;
  }
  app.innerHTML = '<div class="section-title"><h2>采集范围配置</h2><span class="muted">选择一个或多个本机文件夹</span></div>'
    + '<div class="card workflow-config">'
    + '<div class="workflow-folder-actions"><div><strong>采集文件夹</strong>'
    + '<div class="reference-sub">可多次添加；每次选择都会追加到现有配置，不会覆盖已选目录</div></div>'
    + '<button class="btn ghost" onclick="openFolderPicker()">添加文件夹</button></div>'
    + '<div id="workflowTargets" class="workflow-targets"></div>'
    + '<div class="actions" style="margin-top:12px"><button class="btn" onclick="saveWorkflowConfig()">保存配置</button></div></div>'
    + '<div class="section-title"><h2>采集状态</h2><div class="actions">'
    + '<button class="btn" onclick="syncWorkflow()">立即同步</button>'
    + '<button class="btn ghost" onclick="loadWorkflow()">刷新状态</button></div></div>'
    + '<div id="workflowSummary" class="grid stats"></div>'
    + '<div class="section-title"><h2>已采集仓库</h2><span class="muted">根据已选文件夹解析</span></div>'
    + '<div id="workflowRepos" class="card"><div class="empty">正在读取配置…</div></div>';
  state.workflowTargets = [];
  await loadWorkflowConfig();
  await loadWorkflow();
}

async function loadWorkflowConfig() {
  try {
    const data = await api("/api/workflow/config");
    state.workflowTargets = (data.targets || []).map(function(item) {
      return { type: "directory", path: item.path, enabled: item.enabled !== false };
    });
    renderWorkflowTargets();
  } catch (e) {
    toast("读取采集配置失败：" + e.message, true);
  }
}

function renderWorkflowTargets() {
  const el = document.getElementById("workflowTargets");
  if (!el) return;
  if (!state.workflowTargets.length) {
    el.innerHTML = '<div class="empty workflow-empty">尚未配置采集目标。保存空配置时不会扫描任何 Git 仓库。</div>';
    return;
  }
  el.innerHTML = state.workflowTargets.map(function(item, index) {
    return '<div class="workflow-target"><span class="badge">文件夹</span>'
      + '<div class="workflow-target-path">' + esc(item.path) + '</div>'
      + '<button class="file-remove" onclick="removeWorkflowTarget(' + index + ')" aria-label="删除">×</button></div>';
  }).join("");
}

async function openFolderPicker() {
  document.getElementById("folderPickerOverlay")?.remove();
  state.folderPickerSelections = [];
  state.folderPickerPath = null;
  document.body.insertAdjacentHTML("beforeend",
    '<div id="folderPickerOverlay" class="folder-picker-overlay"><div class="folder-picker">'
    + '<div class="folder-picker-head"><div><strong>添加采集文件夹</strong><div class="reference-sub">选择本次要新增的一个或多个文件夹；已配置目录不会被替换</div></div>'
    + '<button class="file-remove" id="folderPickerClose">×</button></div>'
    + '<div class="folder-picker-toolbar"><button class="btn ghost" id="folderPickerUp">上一级</button>'
    + '<div id="folderPickerPath" class="folder-picker-path">磁盘</div>'
    + '<button class="btn ghost" id="folderPickerCurrent" hidden>选择当前文件夹</button></div>'
    + '<div id="folderPickerList" class="folder-picker-list"><div class="empty">正在读取目录…</div></div>'
    + '<div class="folder-picker-selected"><div class="folder-picker-selected-title">本次已选择 <span id="folderPickerCount">0</span> 个文件夹</div>'
    + '<div id="folderPickerSelectedList" class="folder-picker-selected-list"></div></div>'
    + '<div class="folder-picker-foot"><button class="btn ghost" id="folderPickerCancel">取消</button>'
    + '<button class="btn" id="folderPickerConfirm">确定</button></div></div></div>');
  document.getElementById("folderPickerClose").onclick = closeFolderPicker;
  document.getElementById("folderPickerCancel").onclick = closeFolderPicker;
  document.getElementById("folderPickerConfirm").onclick = confirmFolderPicker;
  document.getElementById("folderPickerUp").onclick = folderPickerUp;
  document.getElementById("folderPickerCurrent").onclick = selectCurrentFolder;
  renderFolderPickerSelections();
  await loadFolderPicker(null);
}

function closeFolderPicker() {
  document.getElementById("folderPickerOverlay")?.remove();
}

function folderPathSelected(path) {
  return (state.folderPickerSelections || []).some(function(item) {
    return item.toLowerCase() === path.toLowerCase();
  });
}

function setFolderSelection(path, selected) {
  const current = state.folderPickerSelections || [];
  const exists = current.findIndex(function(item) { return item.toLowerCase() === path.toLowerCase(); });
  if (selected && exists < 0) current.push(path);
  if (!selected && exists >= 0) current.splice(exists, 1);
  state.folderPickerSelections = current;
  renderFolderPickerSelections();
}

function renderFolderPickerSelections() {
  const count = document.getElementById("folderPickerCount");
  const list = document.getElementById("folderPickerSelectedList");
  if (!count || !list) return;
  count.textContent = (state.folderPickerSelections || []).length;
  list.innerHTML = (state.folderPickerSelections || []).length
    ? state.folderPickerSelections.map(function(path) {
        return '<span class="folder-selected-chip"><span>' + esc(path) + '</span><button data-remove-folder="' + esc(path) + '">×</button></span>';
      }).join("")
    : '<span class="muted">尚未选择</span>';
  list.querySelectorAll("[data-remove-folder]").forEach(function(button) {
    button.onclick = function() {
      setFolderSelection(button.dataset.removeFolder, false);
      loadFolderPicker(state.folderPickerPath);
    };
  });
}

async function loadFolderPicker(path) {
  const list = document.getElementById("folderPickerList");
  if (!list) return;
  list.innerHTML = '<div class="empty">正在读取目录…</div>';
  try {
    const url = "/api/fs/directories" + (path ? "?path=" + encodeURIComponent(path) : "");
    const data = await api(url);
    state.folderPickerPath = data.path;
    state.folderPickerParent = data.parent;
    document.getElementById("folderPickerPath").textContent = data.path || "磁盘";
    document.getElementById("folderPickerUp").disabled = !data.path;
    document.getElementById("folderPickerCurrent").hidden = !data.path;

    const entries = data.path
      ? data.directories
      : (data.roots || []).map(function(root) { return { name: root, path: root, is_git: false }; });

    if (!entries.length) {
      list.innerHTML = '<div class="empty">此目录下没有子文件夹</div>';
      return;
    }
    list.innerHTML = entries.map(function(item) {
      const checked = folderPathSelected(item.path) ? " checked" : "";
      return '<div class="folder-picker-row">'
        + '<input type="checkbox" data-folder-select="' + esc(item.path) + '"' + checked + ' />'
        + '<button class="folder-picker-name" data-folder-open="' + esc(item.path) + '"><span class="folder-icon">📁</span>'
        + '<span>' + esc(item.name) + '</span></button>'
        + (item.is_git ? '<span class="badge ok">Git</span>' : '<span></span>') + '</div>';
    }).join("");
    list.querySelectorAll("[data-folder-open]").forEach(function(button) {
      button.onclick = function() { loadFolderPicker(button.dataset.folderOpen); };
    });
    list.querySelectorAll("[data-folder-select]").forEach(function(input) {
      input.onchange = function() { setFolderSelection(input.dataset.folderSelect, input.checked); };
    });
  } catch (e) {
    list.innerHTML = '<div class="empty">无法读取目录：' + esc(e.message) + '</div>';
  }
}

function folderPickerUp() {
  if (state.folderPickerParent) loadFolderPicker(state.folderPickerParent);
  else loadFolderPicker(null);
}

function selectCurrentFolder() {
  if (!state.folderPickerPath) return;
  setFolderSelection(state.folderPickerPath, !folderPathSelected(state.folderPickerPath));
  loadFolderPicker(state.folderPickerPath);
}

function confirmFolderPicker() {
  const existing = state.workflowTargets || [];
  const merged = existing.slice();
  (state.folderPickerSelections || []).forEach(function(path) {
    const duplicate = merged.some(function(item) {
      return item.path.toLowerCase() === path.toLowerCase();
    });
    if (!duplicate) {
      merged.push({ type: "directory", path: path, enabled: true });
    }
  });
  state.workflowTargets = merged;
  renderWorkflowTargets();
  closeFolderPicker();
}

function removeWorkflowTarget(index) {
  state.workflowTargets.splice(index, 1);
  renderWorkflowTargets();
}

async function saveWorkflowConfig() {
  try {
    const data = await api("/api/workflow/config", {
      method: "PUT",
      body: JSON.stringify({ targets: state.workflowTargets })
    });
    state.workflowTargets = data.targets || [];
    renderWorkflowTargets();
    toast("采集范围已保存");
    await loadWorkflow();
  } catch (e) {
    toast("保存失败：" + e.message, true);
  }
}

async function loadWorkflow() {
  const summary = document.getElementById("workflowSummary");
  const repos = document.getElementById("workflowRepos");
  try {
    const data = await api("/api/workflow");
    const cloudMode = state.runtime?.mode === "cloudflare";
    summary.innerHTML =
      '<div class="card"><div class="stat-label">' + (cloudMode ? "同步仓库" : "采集文件夹") + '</div><div class="stat-value">' + (cloudMode ? data.repository_count : data.targets.length) + '</div><div class="stat-note">' + (cloudMode ? "Local Agent 上报" : (data.configured ? "已配置" : "未配置")) + '</div></div>'
      + '<div class="card"><div class="stat-label">Git 仓库</div><div class="stat-value">' + data.repository_count + '</div><div class="stat-note">' + (cloudMode ? "D1 事件库" : "由配置解析") + '</div></div>'
      + '<div class="card"><div class="stat-label">今日 Commit</div><div class="stat-value">' + data.commit_count + '</div><div class="stat-note">' + (cloudMode ? "D1 已同步事件" : "同步后写入 Daily Log") + '</div></div>'
      + '<div class="card"><div class="stat-label">今日 Tag</div><div class="stat-value">' + data.tag_count + '</div><div class="stat-note">Release 线索</div></div>';
    if (!data.configured) {
      repos.innerHTML = cloudMode
        ? '<div class="empty">尚未收到 Local Agent 的 Git 同步数据</div>'
        : '<div class="empty">尚未配置采集范围<br><span class="muted">点击“选择文件夹”，可一次选择多个目录，保存后开始采集</span></div>';
      return;
    }
    if (!data.repositories.length) {
      repos.innerHTML = '<div class="empty">当前配置没有解析到 Git 仓库</div>';
      return;
    }
    repos.innerHTML = data.repositories.map(function(repo) {
      const tree = repo.working_tree;
      const status = tree.dirty ? '<span class="badge warn">有改动</span>' : '<span class="badge ok">干净</span>';
      const commits = repo.commits.length
        ? '<div class="workflow-commits">' + repo.commits.slice(0, 8).map(function(c) {
            return '<div><span class="commit-hash">' + esc(c.short) + '</span> ' + esc(c.subject) + '</div>';
          }).join("") + '</div>'
        : '<div class="reference-sub">今天暂无提交</div>';
      return '<div class="workflow-repo"><div class="workflow-repo-head"><div><strong>' + esc(repo.name) + '</strong>'
        + '<div class="reference-sub">' + esc(repo.path) + '</div></div><div class="actions">'
        + '<span class="badge">' + esc(repo.branch) + '</span>' + status + '</div></div>'
        + '<div class="workflow-meta">当前仓库用户：' + esc((repo.current_user?.name || "Unknown") + " <" + (repo.current_user?.email || "未配置 user.email") + ">") + '</div>'
        + '<div class="workflow-meta">Git Pull：' + esc(repo.pull?.success ? (repo.pull?.message || "成功") : (repo.pull?.message || "失败")) + '</div>'
        + '<div class="workflow-meta">今日全部用户 ' + repo.commit_count + ' commits · ' + repo.merge_count + ' merge/PR · '
        + repo.tag_count + ' tags · ' + tree.changed_count + ' 未提交文件</div>' + commits + '</div>';
    }).join("");
  } catch (e) {
    repos.innerHTML = '<div class="empty">读取工作流失败：' + esc(e.message) + '</div>';
  }
}

async function syncWorkflow() {
  try {
    toast("正在同步 Git 工作活动…");
    const data = await api("/api/workflow/sync", { method: "POST" });
    if (!data.configured) {
      toast("尚未配置采集范围", true);
      return;
    }
    toast("同步完成：" + data.repository_count + " 个仓库，" + data.commit_count + " 个提交");
    await loadWorkflow();
  } catch (e) {
    toast(e.message, true);
  }
}

function reviewTemplate() {
  return '<div class="grid two"><div class="card"><h3>' + t("review.generate") + '</h3>'
    + '<p class="muted">' + t("review.description") + '</p>'
    + '<div class="form-group"><label>' + t("review.isoWeek") + '</label><input id="reviewWeek" class="input" placeholder="2026-W38" /></div>'
    + '<div class="form-group"><label>' + t("review.scope") + '</label><select id="reviewAuthorScope" class="input"><option value="current_user">' + t("review.currentUser") + '</option><option value="all_users">' + t("review.allUsers") + '</option></select></div>'
    + '<div class="actions" style="margin-top:14px"><button class="btn" onclick="runReview()">' + t("review.generate") + '</button></div></div>'
    + '<div class="card viewer"><h3>' + t("review.result") + '</h3><div id="reviewResult" class="empty">' + t("review.resultHint") + '</div></div></div>';
}

async function runReview() {
  const week = document.getElementById("reviewWeek").value.trim() || null;
  const authorScope = document.getElementById("reviewAuthorScope").value;
  const resultEl = document.getElementById("reviewResult");
  try {
    const result = await api("/mcp/vault_weekly_review", { method: "POST", body: JSON.stringify({ week: week, author_scope: authorScope }) });
    const note = await api("/mcp/vault_read", { method: "POST", body: JSON.stringify({ path: result.path }) });
    resultEl.className = "review-report";
    resultEl.innerHTML = '<div class="result-head"><div><strong>' + esc(t("review.weekly", { week: result.week })) + '</strong>'
      + '<div class="path">' + esc(result.path) + '</div></div><div class="actions">'
      + '<span class="badge ok">' + result.git_commits + ' commits</span>'
      + '<span class="badge">' + esc(authorScope === "all_users" ? t("review.allUsers") : t("review.currentUser")) + '</span>'
      + '<span class="badge">' + esc(t("review.activeRepos", { count: (result.git_active_repositories || []).length })) + '</span>'
      + '<span class="badge">' + esc(t("review.knowledgeTopics", { count: result.knowledge_topics || 0 })) + '</span></div></div>'
      + '<article class="markdown-body review-markdown">' + renderMarkdown(note.content) + '</article>';
    bindWikiLinks(resultEl);
    toast(t("review.done"));
  } catch (e) {
    resultEl.className = "empty";
    resultEl.textContent = t("review.failed", { error: e.message });
  }
}
async function loadRuntime() {
  try {
    state.runtime = await api("/api/runtime");
  } catch (_) {
    state.runtime = { mode: "local", capabilities: {} };
  }
  const capabilities = state.runtime.capabilities || {};
  const viewCaps = {
    ingest: "uploads",
    compile: "knowledge_compile",
    governance: "governance",
    review: "weekly_review"
  };
  Object.keys(viewCaps).forEach(function(view) {
    const button = document.querySelector('.nav-item[data-view="' + view + '"]');
    if (button && capabilities[viewCaps[view]] === false) button.hidden = true;
  });
}

async function checkHealth() {
  try {
    const data = await api("/health");
    serviceDot.classList.add("ok");
    serviceText.textContent = t("status.ok", { version: data.version });
  } catch (_) {
    serviceDot.classList.remove("ok");
    serviceText.textContent = t("status.unavailable");
  }
}

async function renderCurrent() {
  const caps = state.runtime?.capabilities || {};
  const unsupported =
    (state.view === "compile" && caps.knowledge_compile === false)
    || (state.view === "governance" && caps.governance === false)
    || (state.view === "ingest" && caps.uploads === false)
    || (state.view === "review" && caps.weekly_review === false);
  if (unsupported) {
    state.view = "dashboard";
    document.querySelectorAll(".nav-item").forEach(function(el) {
      el.classList.toggle("active", el.dataset.view === "dashboard");
    });
  }
  titleEl.textContent = t(titleKeys[state.view]);
  if (state.view === "dashboard") return renderDashboard();
  if (state.view === "search") app.innerHTML = searchTemplate();
  if (state.view === "graph") return renderGraph();
  if (state.view === "ingest") { app.innerHTML = ingestTemplate(); return loadReferences(); }
  if (state.view === "compile") return renderCompile();
  if (state.view === "governance") return renderGovernance();
  if (state.view === "workflow") return renderWorkflow();
  if (state.view === "review") app.innerHTML = reviewTemplate();
}

window.switchView = async function(view) {
  state.view = view;
  document.querySelectorAll(".nav-item").forEach(function(el) {
    el.classList.toggle("active", el.dataset.view === view);
  });
  await renderCurrent();
  window.NexusUI?.localize(app);
};

document.getElementById("nav").addEventListener("click", function(event) {
  const button = event.target.closest("[data-view]");
  if (button) switchView(button.dataset.view);
});

document.getElementById("refreshBtn").addEventListener("click", function() {
  renderCurrent();
});

document.addEventListener("keydown", function(event) {
  if (event.key === "Enter" && state.view === "search" && document.activeElement?.id === "searchQuery") {
    runSearch();
  }
});

async function bootstrap() {
  window.NexusUI?.bind();
  await loadRuntime();
  await checkHealth();
  await renderCurrent();
  window.NexusUI?.localize(app);
}

window.addEventListener("nexusmind:languagechange", async function() {
  await checkHealth();
  await renderCurrent();
  window.NexusUI?.localize(app);
});

bootstrap();
