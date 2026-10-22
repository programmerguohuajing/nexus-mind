/* NexusMind Web Clipper 共享逻辑：配置读取与 API 调用。 */
"use strict";

const DEFAULTS = { serverUrl: "http://127.0.0.1:8301", apiToken: "", author: "Web Clipper" };

async function getConfig() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return Object.assign({}, DEFAULTS, stored);
}

async function apiFetch(path, body) {
  const cfg = await getConfig();
  const headers = { "Content-Type": "application/json" };
  if (cfg.apiToken) headers["X-NexusMind-Token"] = cfg.apiToken;
  const resp = await fetch(cfg.serverUrl.replace(/\/$/, "") + path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = "HTTP " + resp.status;
    try { detail = (await resp.json()).detail || detail; } catch (e) { /* ignore */ }
    throw new Error(detail + "（请确认 NexusMind 本地服务已启动）");
  }
  return resp.json();
}

/** 整页剪藏：由本地服务抓取正文（复用服务端 web_ingest）。 */
async function clipPage(url, author) {
  return apiFetch("/api/web-ingest", { url, author: author || (await getConfig()).author });
}

/** 选中文本剪藏：直接把文本写入 Raw 层。 */
async function clipSelection(title, text, url, author) {
  const content = (text || "").trim();
  if (!content) throw new Error("没有可剪藏的文本");
  return apiFetch("/mcp/vault_ingest", {
    title: (title || "网页摘录").slice(0, 80),
    content: content + (url ? `\n\n> 来源：${url}` : ""),
    author: author || (await getConfig()).author,
    url: url || undefined,
  });
}

/** 稍后读：仅在扩展本地保存 URL+标题，之后可一键批量入库。 */
async function addReadLater(item) {
  const { readLater = [] } = await chrome.storage.local.get("readLater");
  if (!readLater.some((x) => x.url === item.url)) {
    readLater.push(Object.assign({ addedAt: new Date().toISOString() }, item));
    await chrome.storage.local.set({ readLater });
  }
  return readLater.length;
}

async function syncReadLater() {
  const { readLater = [] } = await chrome.storage.local.get("readLater");
  const remaining = [];
  let synced = 0;
  for (const item of readLater) {
    try { await clipPage(item.url); synced += 1; }
    catch (e) { remaining.push(item); }
  }
  await chrome.storage.local.set({ readLater: remaining });
  return { synced, remaining: remaining.length };
}
