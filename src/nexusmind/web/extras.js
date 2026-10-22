/* NexusMind 扩展视图：问知识 / 模板库 / 治理增强（Phase 1-3 功能的 Web 入口）。
 * 独立脚本注入导航与视图，复用管理台既有样式类，不改动 app.js 主逻辑。 */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  const app = document.getElementById("app");
  const nav = document.getElementById("nav");
  const title = document.getElementById("pageTitle");
  if (!app || !nav) return;

  async function api(url, options) {
    const resp = await fetch(url, Object.assign({ headers: { "Content-Type": "application/json" } }, options || {}));
    if (!resp.ok) {
      let detail = "HTTP " + resp.status;
      try { detail = (await resp.json()).detail || detail; } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function toastMsg(msg) {
    const toast = document.getElementById("toast");
    if (toast) { toast.textContent = msg; toast.classList.add("show"); setTimeout(() => toast.classList.remove("show"), 2400); }
  }

  function activate(btn, heading) {
    nav.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    btn.classList.add("active");
    if (title) title.textContent = heading;
  }

  function addNavItem(label, heading, render) {
    const btn = document.createElement("button");
    btn.className = "nav-item";
    btn.textContent = label;
    btn.addEventListener("click", () => { activate(btn, heading); render(); });
    nav.appendChild(btn);
    return btn;
  }

  /* ---------- 问知识（Phase 2: Ask My Vault） ---------- */
  function renderAsk() {
    app.innerHTML = `
      <div class="card">
        <h3>🤖 问知识（Ask My Vault）</h3>
        <p class="hint">基于你自己的知识库回答问题，答案带来源引用；知识库里没有的内容会明确说明。</p>
        <div class="form-grid">
          <input class="input" id="askInput" placeholder="例如：支付超时一般怎么排查？" />
          <button class="btn" id="askSubmit">提问</button>
        </div>
        <div style="margin-top:10px">
          <label><input type="checkbox" id="askSave" /> 保存本次问答为笔记</label>
        </div>
        <div id="askOutput" style="margin-top:14px"></div>
      </div>`;
    const submit = async () => {
      const q = document.getElementById("askInput").value.trim();
      const out = document.getElementById("askOutput");
      if (!q) { toastMsg("先输入问题"); return; }
      out.innerHTML = "<p class='hint'>正在检索知识库…</p>";
      try {
        const data = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q, save: document.getElementById("askSave").checked }) });
        const cites = (data.citations || []).map((c) => `<li><code>${esc(c.path)}</code> · 相似度 ${esc(c.score)}</li>`).join("");
        out.innerHTML = `<div class="card"><p style="white-space:pre-wrap">${esc(data.answer)}</p>
          ${cites ? `<p class="hint">来源引用：</p><ul>${cites}</ul>` : ""}
          <p class="hint">模式：${esc(data.mode)}${data.saved_path ? " · 已保存：" + esc(data.saved_path) : ""}</p></div>`;
      } catch (err) { out.innerHTML = `<p class="hint">提问失败：${esc(err.message)}</p>`; }
    };
    document.getElementById("askSubmit").addEventListener("click", submit);
    document.getElementById("askInput").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  }

  /* ---------- 模板库（Phase 1） ---------- */
  async function renderTemplates() {
    app.innerHTML = "<p class='hint'>加载模板…</p>";
    try {
      const data = await api("/api/templates");
      const cards = data.templates.map((t) => `
        <div class="card">
          <h4>${esc(t.name)} ${t.builtin ? '<span class="badge">内置</span>' : ""}</h4>
          <p class="hint">${esc(t.description)}</p>
          <p class="hint">默认目录：<code>${esc(t.default_folder)}</code></p>
          <input class="input tpl-title" data-tpl="${esc(t.id)}" placeholder="笔记标题" />
          <button class="btn tpl-create" data-tpl="${esc(t.id)}">用此模板新建</button>
        </div>`).join("");
      app.innerHTML = `<div class="grid">${cards}</div>
        <div class="card"><h3>📋 查看行动项</h3>
          <div class="form-grid"><input class="input" id="aiPath" placeholder="笔记路径，如 30-Logs/Meetings/2026-10-22-支付周会.md" />
          <button class="btn" id="aiLoad">提取行动项</button></div>
          <div id="aiOutput"></div></div>`;
      app.querySelectorAll(".tpl-create").forEach((btn) => btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-tpl");
        const input = app.querySelector(`.tpl-title[data-tpl="${id}"]`);
        const noteTitle = input.value.trim();
        if (!noteTitle) { toastMsg("先填写笔记标题"); return; }
        try {
          const res = await api("/api/templates/create", { method: "POST", body: JSON.stringify({ template_id: id, title: noteTitle }) });
          toastMsg("已创建：" + res.path);
        } catch (err) { toastMsg("创建失败：" + err.message); }
      }));
      document.getElementById("aiLoad").addEventListener("click", async () => {
        const path = document.getElementById("aiPath").value.trim();
        const out = document.getElementById("aiOutput");
        if (!path) return;
        try {
          const data = await api("/api/templates/action-items?path=" + encodeURIComponent(path));
          out.innerHTML = data.items.length
            ? "<ul>" + data.items.map((i) => `<li>${i.done ? "✅" : "⬜"} ${esc(i.text)}${i.owner ? "（@" + esc(i.owner) + "）" : ""}${i.ddl ? " · 截止 " + esc(i.ddl) : ""}</li>`).join("") + "</ul>"
            : "<p class='hint'>没有解析到行动项。</p>";
        } catch (err) { out.innerHTML = `<p class="hint">提取失败：${esc(err.message)}</p>`; }
      });
    } catch (err) { app.innerHTML = `<p class="hint">模板加载失败：${esc(err.message)}</p>`; }
  }

  /* ---------- 治理增强（Phase 1：重复/保鲜/历史） ---------- */
  async function renderGovernancePlus() {
    app.innerHTML = "<p class='hint'>正在扫描重复内容与保鲜状态…</p>";
    try {
      const [dups, stale] = await Promise.all([api("/api/governance/duplicates"), api("/api/governance/stale")]);
      const dupHtml = dups.pairs.length ? dups.pairs.map((p, idx) => `
        <div class="card"><p><code>${esc(p.path_a)}</code> ↔ <code>${esc(p.path_b)}</code></p>
        <p class="hint">相似度 ${esc(p.score)}</p>
        <button class="btn dup-merge" data-a="${esc(p.path_a)}" data-b="${esc(p.path_b)}">合并（保留前者）</button>
        <button class="btn ghost dup-ignore" data-a="${esc(p.path_a)}" data-b="${esc(p.path_b)}">忽略</button></div>`).join("")
        : "<p class='hint'>未发现疑似重复。</p>";
      const staleHtml = stale.stale_notes.length ? stale.stale_notes.map((s) => `
        <div class="card"><p><code>${esc(s.path)}</code></p>
        <p class="hint">逾期 ${esc(s.days_overdue)} 天 · 应复审日 ${esc(s.due_date)} · 周期 ${esc(s.review_after_days)} 天</p>
        <button class="btn stale-review" data-path="${esc(s.path)}">确认已复审</button></div>`).join("")
        : "<p class='hint'>没有过期的知识卡片。</p>";
      app.innerHTML = `
        <div class="card"><h3>🧬 疑似重复（${dups.total}）</h3>${dupHtml}</div>
        <div class="card"><h3>⏰ 待复审（${stale.total}）</h3>${staleHtml}
          <button class="btn" id="digestPush">推送复审摘要到通知渠道</button></div>
        <div class="card"><h3>🕘 版本历史与回滚</h3>
          <div class="form-grid"><input class="input" id="histPath" placeholder="笔记路径，如 40-Domain/Pay/卡片.md" />
          <button class="btn" id="histLoad">查看历史</button></div>
          <div id="histOutput"></div></div>`;
      app.querySelectorAll(".dup-merge").forEach((btn) => btn.addEventListener("click", async () => {
        if (!confirm("把后者合并为前者的重定向？")) return;
        try { await api("/api/governance/duplicates/merge", { method: "POST", body: JSON.stringify({ primary: btn.dataset.a, secondary: btn.dataset.b }) }); toastMsg("已合并"); renderGovernancePlus(); }
        catch (err) { toastMsg("合并失败：" + err.message); }
      }));
      app.querySelectorAll(".dup-ignore").forEach((btn) => btn.addEventListener("click", async () => {
        try { await api("/api/governance/duplicates/ignore", { method: "POST", body: JSON.stringify({ path_a: btn.dataset.a, path_b: btn.dataset.b }) }); renderGovernancePlus(); }
        catch (err) { toastMsg("操作失败：" + err.message); }
      }));
      app.querySelectorAll(".stale-review").forEach((btn) => btn.addEventListener("click", async () => {
        try { await api("/api/governance/reviewed", { method: "POST", body: JSON.stringify({ path: btn.dataset.path }) }); toastMsg("已确认复审"); renderGovernancePlus(); }
        catch (err) { toastMsg("操作失败：" + err.message); }
      }));
      document.getElementById("digestPush").addEventListener("click", async () => {
        try { const r = await api("/api/governance/freshness-digest?push=true"); toastMsg(r.notification_result ? "已推送" : "无过期卡片，未推送"); }
        catch (err) { toastMsg("推送失败：" + err.message); }
      });
      document.getElementById("histLoad").addEventListener("click", async () => {
        const path = document.getElementById("histPath").value.trim();
        const out = document.getElementById("histOutput");
        if (!path) return;
        try {
          const data = await api("/api/history?path=" + encodeURIComponent(path));
          out.innerHTML = data.versions.length
            ? data.versions.map((v) => `<p><code>${esc(v.version)}</code> · ${esc(v.created_at)} · ${esc(v.size)} 字节
                <button class="btn ghost hist-rollback" data-version="${esc(v.version)}">回滚到此版本</button></p>`).join("")
            : "<p class='hint'>暂无历史版本（笔记被覆盖写入后才会产生）。</p>";
          out.querySelectorAll(".hist-rollback").forEach((btn) => btn.addEventListener("click", async () => {
            if (!confirm("回滚会把当前内容再存一份历史，确认回滚？")) return;
            try { await api("/api/history/rollback", { method: "POST", body: JSON.stringify({ path, version: btn.dataset.version }) }); toastMsg("已回滚"); }
            catch (err) { toastMsg("回滚失败：" + err.message); }
          }));
        } catch (err) { out.innerHTML = `<p class="hint">查询失败：${esc(err.message)}</p>`; }
      });
    } catch (err) { app.innerHTML = `<p class="hint">治理增强加载失败：${esc(err.message)}</p>`; }
  }

  addNavItem("问知识", "问知识 · Ask My Vault", renderAsk);
  addNavItem("模板库", "笔记模板库", renderTemplates);
  addNavItem("治理增强", "治理增强 · 重复 / 保鲜 / 历史", renderGovernancePlus);
})();
