"use strict";

const statusEl = document.getElementById("status");
function setStatus(text, ok) {
  statusEl.textContent = text;
  statusEl.style.color = ok === false ? "#b42318" : "#027a48";
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function selectedText(tabId) {
  try {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => window.getSelection().toString(),
    });
    return (res && res.result) || "";
  } catch (e) {
    return "";
  }
}

async function withTags(promise) {
  const tags = document.getElementById("tags").value.split(",").map((s) => s.trim()).filter(Boolean);
  const result = await promise;
  // 标签作为附加说明再次提示用户：服务端入库后可在编译队列中统一打标。
  if (tags.length) setStatus(`已入库（标签待编译时添加：${tags.join(", ")}）`, true);
  return result;
}

document.addEventListener("DOMContentLoaded", async () => {
  const tab = await activeTab();
  document.getElementById("pageInfo").textContent = tab ? `${tab.title || ""}\n${tab.url || ""}` : "无活动标签页";

  document.getElementById("clipPage").addEventListener("click", async () => {
    setStatus("剪藏中…");
    try { const res = await withTags(clipPage(tab.url)); setStatus("已入库：" + (res.path || tab.url), true); }
    catch (err) { setStatus("失败：" + err.message, false); }
  });

  document.getElementById("clipSelection").addEventListener("click", async () => {
    setStatus("读取选中文本…");
    try {
      const text = await selectedText(tab.id);
      if (!text.trim()) { setStatus("当前页面没有选中文本", false); return; }
      const res = await withTags(clipSelection(tab.title, text, tab.url));
      setStatus("已入库：" + (res.path || "选中文本"), true);
    } catch (err) { setStatus("失败：" + err.message, false); }
  });

  document.getElementById("readLater").addEventListener("click", async () => {
    const count = await addReadLater({ url: tab.url, title: tab.title || tab.url });
    setStatus(`已加入稍后读（共 ${count} 篇）`, true);
  });

  document.getElementById("syncLater").addEventListener("click", async () => {
    setStatus("同步稍后读…");
    try { const r = await syncReadLater(); setStatus(`同步完成：成功 ${r.synced} 篇，剩余 ${r.remaining} 篇`, r.remaining === 0); }
    catch (err) { setStatus("失败：" + err.message, false); }
  });
});
