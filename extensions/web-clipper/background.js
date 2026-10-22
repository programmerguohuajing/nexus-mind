/* 右键菜单：剪藏整页 / 剪藏选中文本 / 稍后读。 */
"use strict";
importScripts("clipper.js");

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "clip-page", title: "剪藏整页到 NexusMind", contexts: ["page"] });
  chrome.contextMenus.create({ id: "clip-selection", title: "剪藏选中文本到 NexusMind", contexts: ["selection"] });
  chrome.contextMenus.create({ id: "read-later", title: "稍后读（存入 NexusMind 待读列表）", contexts: ["page", "link"] });
});

async function notify(title, message) {
  try {
    await chrome.notifications?.create?.({ type: "basic", iconUrl: "icon.svg", title, message });
  } catch (e) { /* notifications 权限可选，失败静默 */ }
  console.log(`[NexusMind Clipper] ${title}: ${message}`);
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.pageUrl || (tab && tab.url) || "";
  try {
    if (info.menuItemId === "clip-page") {
      const res = await clipPage(url);
      await notify("剪藏成功", res.path || url);
    } else if (info.menuItemId === "clip-selection") {
      const res = await clipSelection(tab && tab.title, info.selectionText, url);
      await notify("剪藏成功", res.path || "选中文本已入库");
    } else if (info.menuItemId === "read-later") {
      const count = await addReadLater({ url, title: (tab && tab.title) || url });
      await notify("已加入稍后读", `待读列表共 ${count} 篇，在扩展弹窗中一键同步入库`);
    }
  } catch (err) {
    await notify("剪藏失败", String(err.message || err));
  }
});
