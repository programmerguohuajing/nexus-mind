(function () {
  const messages = {
    "zh-CN": {
      "app.subtitle": "知识库管理",
      "app.title": "NexusMind · 知识库管理台",
      "nav.dashboard": "总览",
      "nav.search": "知识搜索",
      "nav.graph": "知识图谱",
      "nav.ingest": "资料入库",
      "nav.compile": "编译队列",
      "nav.governance": "知识治理",
      "nav.workflow": "工作流",
      "nav.review": "周复盘",
      "nav.notifications": "推送渠道",
      "notifications.title": "推送渠道管理",
      "notifications.subtitle": "配置飞书、钉钉、邮件及通用 Webhook 通知渠道",
      "notifications.add": "添加推送渠道",
      "notifications.pushReport": "一键推送复盘报告",
      "notifications.pushNotice": "选择推送渠道",
      "action.refresh": "刷新",
      "action.apiDocs": "API 文档",
      "status.connecting": "正在连接服务…",
      "status.ok": "服务正常 · v{version}",
      "status.unavailable": "服务不可用",
      "settings.language": "语言",
      "settings.theme": "主题",
      "language.zh": "中文",
      "language.en": "English",
      "theme.system": "跟随系统",
      "theme.light": "浅色",
      "theme.dark": "深色",
      "theme.ocean": "海洋",
      "theme.forest": "森林",
      "dashboard.title": "知识库总览",
      "dashboard.allMarkdown": "全部 Markdown",
      "dashboard.vaultSize": "Vault 内容规模",
      "dashboard.domainNotes": "正式知识卡片",
      "dashboard.domainLayer": "40-Domain 编译层",
      "dashboard.rawSources": "Raw 原始资料",
      "dashboard.rawLayer": "60-References 只读层",
      "dashboard.pending": "待编译",
      "dashboard.pendingWait": "等待增量编译",
      "dashboard.queueEmpty": "队列已清空",
      "dashboard.health": "知识健康度",
      "dashboard.realtime": "实时扫描",
      "dashboard.governance": "治理状态",
      "dashboard.broken": "未解析链接",
      "dashboard.orphans": "知识孤岛",
      "dashboard.version": "服务版本",
      "dashboard.enterGovernance": "进入知识治理",
      "dashboard.recentCompile": "最近知识编译",
      "dashboard.compileAudit": "编译审计记录",
      "dashboard.completed": "已完成",
      "dashboard.noCompile": "暂无编译记录",
      "dashboard.compileQueue": "查看编译队列",
      "dashboard.quick": "快捷操作",
      "dashboard.common": "常用入口",
      "dashboard.search": "搜索知识",
      "dashboard.ingest": "导入资料",
      "dashboard.compile": "执行增量编译",
      "dashboard.review": "生成周复盘",
      "dashboard.loadFailed": "加载总览失败：{error}",
      "search.placeholder": "搜索知识、概念、关键词…",
      "search.domain": "正式知识",
      "search.all": "全库",
      "search.projects": "项目",
      "search.logs": "日志",
      "search.raw": "Raw 资料",
      "search.action": "搜索",
      "search.results": "搜索结果",
      "search.start": "输入关键词开始检索",
      "search.note": "知识卡片",
      "search.select": "选择左侧结果查看完整内容",
      "search.searching": "检索中…",
      "search.empty": "没有找到匹配知识",
      "search.failed": "搜索失败：{error}",
      "search.reading": "正在读取…",
      "search.openFailed": "无法打开链接：{target}",
      "search.ambiguous": "链接存在多个候选：{count} 个",
      "workflow.cloudTitle": "云端工作流",
      "workflow.cloudHint": "Git 数据由 Local Agent 同步到 NexusMind Cloud API",
      "workflow.cloudApi": "NexusMind Cloud API",
      "workflow.cloudBody": "远端服务不访问本机磁盘，也不直接执行 Git 命令。请在本机 NexusMind Agent 中配置采集目录和云端同步连接。",
      "workflow.syncStatus": "同步状态",
      "workflow.refresh": "刷新状态",
      "workflow.syncedRepos": "已同步仓库",
      "workflow.fromAgent": "来自 Local Agent",
      "workflow.loading": "正在读取云端仓库状态…",
      "review.generate": "生成周复盘",
      "review.description": "Git 活动始终采集所有用户；生成复盘时可选择当前仓库用户或所有用户作为统计口径。",
      "review.isoWeek": "ISO 周",
      "review.scope": "Git 统计范围",
      "review.currentUser": "当前工作目录 / 仓库配置的当前用户",
      "review.allUsers": "所有用户",
      "review.result": "生成结果",
      "review.resultHint": "生成后会在这里显示周报内容",
      "review.weekly": "{week} 工作周报",
      "review.activeRepos": "{count} 活跃仓库",
      "review.knowledgeTopics": "{count} 知识主题",
      "review.done": "工作周报已生成",
      "review.failed": "生成失败：{error}",
      "common.loading": "加载中…",
      "common.scan": "扫描中…",
      "common.unknown": "未知"
    },
    "en-US": {
      "app.subtitle": "Knowledge Management",
      "app.title": "NexusMind · Knowledge Console",
      "nav.dashboard": "Overview",
      "nav.search": "Knowledge Search",
      "nav.graph": "Knowledge Graph",
      "nav.ingest": "Import",
      "nav.compile": "Compile Queue",
      "nav.governance": "Governance",
      "nav.workflow": "Workflow",
      "nav.review": "Weekly Review",
      "nav.notifications": "Notifications",
      "notifications.title": "Notification Channels",
      "notifications.subtitle": "Configure Feishu, DingTalk, Email, and Generic Webhook push channels",
      "notifications.add": "Add Channel",
      "notifications.pushReport": "Push Report",
      "notifications.pushNotice": "Select Channels",
      "action.refresh": "Refresh",
      "action.apiDocs": "API Docs",
      "status.connecting": "Connecting…",
      "status.ok": "Service healthy · v{version}",
      "status.unavailable": "Service unavailable",
      "settings.language": "Language",
      "settings.theme": "Theme",
      "language.zh": "中文",
      "language.en": "English",
      "theme.system": "System",
      "theme.light": "Light",
      "theme.dark": "Dark",
      "theme.ocean": "Ocean",
      "theme.forest": "Forest",
      "dashboard.title": "Knowledge Overview",
      "dashboard.allMarkdown": "All Markdown",
      "dashboard.vaultSize": "Vault content size",
      "dashboard.domainNotes": "Knowledge Cards",
      "dashboard.domainLayer": "40-Domain compiled layer",
      "dashboard.rawSources": "Raw Sources",
      "dashboard.rawLayer": "60-References read-only layer",
      "dashboard.pending": "Pending Compile",
      "dashboard.pendingWait": "Waiting for incremental compile",
      "dashboard.queueEmpty": "Queue is clear",
      "dashboard.health": "Knowledge Health",
      "dashboard.realtime": "Live scan",
      "dashboard.governance": "Governance Status",
      "dashboard.broken": "Unresolved Links",
      "dashboard.orphans": "Orphan Notes",
      "dashboard.version": "Service Version",
      "dashboard.enterGovernance": "Open Governance",
      "dashboard.recentCompile": "Recent Compiles",
      "dashboard.compileAudit": "Compile audit record",
      "dashboard.completed": "Completed",
      "dashboard.noCompile": "No compile history",
      "dashboard.compileQueue": "View Compile Queue",
      "dashboard.quick": "Quick Actions",
      "dashboard.common": "Common actions",
      "dashboard.search": "Search Knowledge",
      "dashboard.ingest": "Import Sources",
      "dashboard.compile": "Run Incremental Compile",
      "dashboard.review": "Generate Weekly Review",
      "dashboard.loadFailed": "Failed to load overview: {error}",
      "search.placeholder": "Search knowledge, concepts, keywords…",
      "search.domain": "Knowledge",
      "search.all": "All Vault",
      "search.projects": "Projects",
      "search.logs": "Logs",
      "search.raw": "Raw Sources",
      "search.action": "Search",
      "search.results": "Search Results",
      "search.start": "Enter keywords to search",
      "search.note": "Knowledge Card",
      "search.select": "Select a result to view the full note",
      "search.searching": "Searching…",
      "search.empty": "No matching knowledge found",
      "search.failed": "Search failed: {error}",
      "search.reading": "Loading…",
      "search.openFailed": "Unable to open link: {target}",
      "search.ambiguous": "Multiple link candidates found: {count}",
      "workflow.cloudTitle": "Cloud Workflow",
      "workflow.cloudHint": "Git data is synchronized by Local Agent to NexusMind Cloud API",
      "workflow.cloudApi": "NexusMind Cloud API",
      "workflow.cloudBody": "The remote service does not access local disks or execute Git commands directly. Configure collection folders and cloud sync in NexusMind Agent.",
      "workflow.syncStatus": "Sync Status",
      "workflow.refresh": "Refresh Status",
      "workflow.syncedRepos": "Synced Repositories",
      "workflow.fromAgent": "From Local Agent",
      "workflow.loading": "Loading cloud repository status…",
      "review.generate": "Generate Weekly Review",
      "review.description": "Git activity always collects all authors. Choose the current repository user or all users when generating a review.",
      "review.isoWeek": "ISO Week",
      "review.scope": "Git Statistics Scope",
      "review.currentUser": "Current working-directory / repository user",
      "review.allUsers": "All Users",
      "review.result": "Generated Result",
      "review.resultHint": "The weekly report will appear here after generation",
      "review.weekly": "{week} Weekly Review",
      "review.activeRepos": "{count} active repositories",
      "review.knowledgeTopics": "{count} knowledge topics",
      "review.done": "Weekly review generated",
      "review.failed": "Generation failed: {error}",
      "common.loading": "Loading…",
      "common.scan": "Scanning…",
      "common.unknown": "Unknown"
    }
  };
  const supportedLanguages = ["zh-CN", "en-US"];
  const supportedThemes = ["system", "light", "dark", "ocean", "forest"];
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function defaultLanguage() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlLang = urlParams.get("lang");
    if (urlLang && supportedLanguages.includes(urlLang)) return urlLang;
    return "zh-CN";
  }

  const urlParams = new URLSearchParams(window.location.search);
  const urlLang = urlParams.get("lang");
  if (urlLang && supportedLanguages.includes(urlLang)) {
    localStorage.setItem("nexusmind.language", urlLang);
  }

  let language = localStorage.getItem("nexusmind.language") || defaultLanguage();
  if (!supportedLanguages.includes(language)) language = "zh-CN";
  let theme = localStorage.getItem("nexusmind.theme") || "system";
  if (!supportedThemes.includes(theme)) theme = "system";

  function t(key, params) {
    const table = messages[language] || messages["zh-CN"];
    let value = table[key] ?? messages["zh-CN"][key] ?? key;
    Object.entries(params || {}).forEach(([name, replacement]) => {
      value = value.replaceAll("{" + name + "}", String(replacement));
    });
    return value;
  }

  const literalEn = {
    "本地文件": "Local Files", "粘贴文本": "Paste Text",
    "拖拽文件到这里，或点击选择文件": "Drop files here, or click to choose",
    "支持 MD / TXT / PDF / DOCX · 可多选 · 单个文件不超过 50 MB": "Supports MD / TXT / PDF / DOCX · Multiple files · 50 MB max per file",
    "作者（可选）": "Author (optional)", "来源 URL（可选）": "Source URL (optional)",
    "开始入库": "Import", "清空": "Clear", "已入库资料": "Imported Sources",
    "正在读取资料库…": "Loading source library…", "标题": "Title", "作者": "Author",
    "来源 URL": "Source URL", "Markdown / 文本内容": "Markdown / Text Content",
    "写入 Raw 层": "Write to Raw Layer", "待编译素材": "Pending Sources",
    "正在扫描…": "Scanning…", "增量编译控制": "Incremental Compile",
    "扫描 Raw 层未处理素材，编译为带来源锚点的正式知识卡片，并维护索引与审计日志。": "Scan unprocessed Raw sources, compile traceable knowledge cards, and maintain indexes and audit logs.",
    "Raw 资料只读 · 编译结果可追溯 · 冲突记录保留": "Raw sources are read-only · Compiles are traceable · Conflicts are preserved",
    "编译全部待处理素材": "Compile All Pending", "重新扫描": "Rescan",
    "编译队列为空": "Compile queue is empty", "所有 Raw 素材均已处理": "All Raw sources are processed",
    "治理工具": "Governance Tools", "重建索引": "Rebuild Indexes",
    "Wikilink 目标不存在": "Wikilink target does not exist", "没有传入反链": "No incoming backlinks",
    "没有死链": "No broken links", "没有知识孤岛": "No orphan notes",
    "全库": "All Vault", "正式知识": "Knowledge", "项目": "Projects", "日志": "Logs",
    "刷新图谱": "Refresh Graph", "知识关系图": "Knowledge Relationship Graph",
    "正在构建关系图…": "Building graph…", "选择 Canvas 查看": "Select a Canvas to view",
    "暂无 Canvas": "No Canvas files", "采集范围配置": "Collection Scope",
    "选择一个或多个本机文件夹": "Choose one or more local folders",
    "采集文件夹": "Collection Folders", "添加文件夹": "Add Folder", "保存配置": "Save Configuration",
    "采集状态": "Collection Status", "立即同步": "Sync Now", "已采集仓库": "Collected Repositories",
    "根据已选文件夹解析": "Resolved from selected folders", "正在读取配置…": "Loading configuration…",
    "可多次添加；每次选择都会追加到现有配置，不会覆盖已选目录": "You can add folders repeatedly; new selections are appended without replacing existing ones.",
    "同步状态": "Sync Status", "刷新状态": "Refresh Status", "正在读取仓库状态…": "Loading repository status…",
    "加载中…": "Loading…", "未解析链接": "Unresolved Links", "知识孤岛": "Orphan Notes",
    "文件": "File", "类型": "Type", "大小": "Size", "状态": "Status",
    "待上传": "Pending Upload", "已编译": "Compiled", "待编译": "Pending Compile", "未提取": "Not Extracted",
    "未生成 Markdown": "Markdown not generated", "暂无已入库文件": "No imported files",
    "正在入库…": "Importing…", "已入库": "Imported", "失败": "Failed",
    "刷新": "Refresh", "资料标题": "Source title", "粘贴正文或 Markdown…": "Paste text or Markdown…",
    "当前范围没有 Markdown 节点": "No Markdown nodes in this scope",
    "正在读取 Canvas…": "Loading Canvas…", "Canvas 没有节点": "Canvas has no nodes",
    "在线链接": "Online URL", "从在线链接提取网页正文": "Extract Web Page Content",
    "NexusMind 会抓取网页、识别标题并提取主要文本内容，然后写入 Raw 层。本地 Agent 模式支持 localhost 和局域网地址；远端服务模式支持公网 HTTP/HTTPS 网页。": "NexusMind fetches the page, detects its title, extracts the main text, and writes it to the Raw layer. Local Agent mode supports localhost and LAN addresses; remote service mode supports public HTTP/HTTPS pages.",
    "网页链接": "Web URL", "抓取并入库": "Fetch & Import", "正在抓取…": "Fetching…",
    "正在抓取并提取网页正文…": "Fetching and extracting page content…", "网页已入库": "Web page imported",
    "已入库": "Imported", "作者（可选）": "Author (optional)"
  };

  const skipSelector = ".markdown-body,.snippet,.path,.result-title,.canvas-node-label,pre,code";
  function localize(root) {
    if (language !== "en-US" || !root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      const parent = node.parentElement;
      if (!parent || parent.closest(skipSelector)) return;
      const raw = node.nodeValue;
      const trimmed = raw.trim();
      if (!trimmed || !literalEn[trimmed]) return;
      node.nodeValue = raw.replace(trimmed, literalEn[trimmed]);
    });
    root.querySelectorAll?.("[placeholder]").forEach((element) => {
      const value = element.getAttribute("placeholder");
      if (literalEn[value]) element.setAttribute("placeholder", literalEn[value]);
    });
  }

  function resolvedTheme(value) {
    if (value !== "system") return value;
    return systemDark.matches ? "dark" : "light";
  }

  function applyTheme() {
    const resolved = resolvedTheme(theme);
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themeChoice = theme;
    document.documentElement.style.colorScheme = resolved === "dark" ? "dark" : "light";
  }

  function syncPicker(id, value) {
    const picker = typeof id === "string" ? document.getElementById(id) : id;
    if (!picker) return;
    const targetValue = value !== undefined ? value : picker.dataset.value;
    let current = targetValue !== undefined ? picker.querySelector('[data-value="' + targetValue + '"]') : null;
    if (!current) current = picker.querySelector(".top-picker-menu button.active") || picker.querySelector("[data-value]");
    const valueEl = picker.querySelector(".picker-value");
    if (current && valueEl) {
      valueEl.textContent = current.textContent;
      picker.dataset.value = current.dataset.value;
    }
    picker.querySelectorAll("[data-value]").forEach((item) => {
      const active = current ? item === current : item.dataset.value === targetValue;
      item.classList.toggle("active", active);
      item.setAttribute("aria-checked", active ? "true" : "false");
    });
  }

  function getPickerValue(id, defaultValue) {
    const picker = typeof id === "string" ? document.getElementById(id) : id;
    if (!picker) return defaultValue ?? "";
    return picker.dataset.value ?? picker.querySelector(".top-picker-menu button.active")?.dataset.value ?? defaultValue ?? "";
  }

  function closePickers(except) {
    document.querySelectorAll(".ui-picker.open").forEach((picker) => {
      if (picker === except) return;
      picker.classList.remove("open");
      picker.querySelector(".top-picker-button")?.setAttribute("aria-expanded", "false");
    });
  }

  function setupPicker(id, onSelect, initialValue) {
    const picker = typeof id === "string" ? document.getElementById(id) : id;
    if (!picker) return;
    if (initialValue !== undefined) {
      picker.dataset.value = initialValue;
      syncPicker(picker, initialValue);
    } else if (picker.dataset.value !== undefined) {
      syncPicker(picker, picker.dataset.value);
    } else {
      const activeBtn = picker.querySelector(".top-picker-menu button.active") || picker.querySelector(".top-picker-menu button");
      if (activeBtn) {
        picker.dataset.value = activeBtn.dataset.value;
        syncPicker(picker, activeBtn.dataset.value);
      }
    }

    if (typeof onSelect === "function") picker.__onSelect = onSelect;
    if (picker.dataset.bound === "true") return;
    picker.dataset.bound = "true";

    const trigger = picker.querySelector(".top-picker-button");
    trigger?.addEventListener("click", (event) => {
      event.stopPropagation();
      const willOpen = !picker.classList.contains("open");
      closePickers(picker);
      picker.classList.toggle("open", willOpen);
      trigger.setAttribute("aria-expanded", willOpen ? "true" : "false");
    });

    picker.querySelectorAll("[data-value]").forEach((item) => {
      item.addEventListener("click", (event) => {
        event.stopPropagation();
        const val = item.dataset.value;
        picker.dataset.value = val;
        syncPicker(picker, val);
        picker.classList.remove("open");
        trigger?.setAttribute("aria-expanded", "false");
        if (typeof picker.__onSelect === "function") {
          picker.__onSelect(val);
        }
      });
    });
  }

  function renderPickerHTML(config) {
    const idAttr = config.id ? ' id="' + config.id + '"' : "";
    const extraClass = config.className ? " " + config.className : "";
    const initialVal = config.value !== undefined ? config.value : (config.options[0] ? config.options[0].value : "");
    const initialOpt = config.options.find(function(o) { return o.value === initialVal; }) || config.options[0] || { label: "" };
    
    const menuButtons = config.options.map(function(opt) {
      const i18nAttr = opt.i18n ? ' data-i18n="' + opt.i18n + '"' : "";
      const activeClass = opt.value === initialVal ? ' class="active" aria-checked="true"' : ' aria-checked="false"';
      return '<button type="button" data-value="' + (opt.value ?? "") + '"' + i18nAttr + activeClass + '>' + opt.label + '</button>';
    }).join("");

    return '<div class="ui-picker' + extraClass + '"' + idAttr + ' data-value="' + (initialVal ?? "") + '">'
      + '<button class="top-picker-button" type="button" aria-haspopup="menu" aria-expanded="false">'
      + '<span class="picker-value">' + initialOpt.label + '</span>'
      + '<span class="picker-chevron" aria-hidden="true"></span></button>'
      + '<div class="top-picker-menu" role="menu">' + menuButtons + '</div></div>';
  }

  function applyStaticTranslations() {
    document.documentElement.lang = language;
    document.title = t("app.title");
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    syncPicker("languagePicker", language);
    syncPicker("themePicker", theme);
    document.querySelectorAll(".ui-picker").forEach(function(picker) {
      if (picker.id !== "languagePicker" && picker.id !== "themePicker") {
        syncPicker(picker, picker.dataset.value);
      }
    });
  }

  function setLanguage(value) {
    if (!supportedLanguages.includes(value) || value === language) return;
    language = value;
    localStorage.setItem("nexusmind.language", language);
    applyStaticTranslations();
    window.dispatchEvent(new CustomEvent("nexusmind:languagechange", { detail: { language } }));
  }

  function setTheme(value) {
    if (!supportedThemes.includes(value)) return;
    theme = value;
    localStorage.setItem("nexusmind.theme", theme);
    applyTheme();
    syncPicker("themePicker", theme);
    window.dispatchEvent(new CustomEvent("nexusmind:themechange", { detail: { theme } }));
  }

  function bind() {
    applyTheme();
    applyStaticTranslations();
    setupPicker("languagePicker", setLanguage);
    setupPicker("themePicker", setTheme);
    document.addEventListener("click", () => closePickers());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closePickers();
    });
    const appRoot = document.getElementById("app");
    if (appRoot && !window.__nexusUiObserver) {
      window.__nexusUiObserver = new MutationObserver(() => localize(appRoot));
      window.__nexusUiObserver.observe(appRoot, { childList: true, subtree: true });
    }
  }

  systemDark.addEventListener?.("change", () => {
    if (theme === "system") applyTheme();
  });

  window.NexusUI = {
    t,
    bind,
    setLanguage,
    setTheme,
    localize,
    syncPicker,
    setupPicker,
    getPickerValue,
    renderPickerHTML,
    getLanguage: () => language,
    getTheme: () => theme,
    supportedLanguages: supportedLanguages.slice(),
    supportedThemes: supportedThemes.slice()
  };

  applyTheme();
})();
