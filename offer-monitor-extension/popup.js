const FIELD_LABELS = {
  price: "价格",
  agentPrice: "分销价",
  saleQuantity: "销量",
  agentBookedCount: "分销预定量",
  evaluateCounts: "评价数",
  thirtyBookCount: "30天预定数",
  offerCount: "商品总数",
  "__新增商品__": "新增商品",
  "__下架/移除__": "下架/移除",
};

function fmtTime(ts) {
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function deltaHtml(d) {
  if (d === "" || d === undefined) return "";
  const n = Number(d);
  if (Number.isNaN(n)) return d;
  if (n > 0) return `<span class="up">+${n}</span>`;
  if (n < 0) return `<span class="down">${n}</span>`;
  return "0";
}

async function render() {
  const data = await chrome.storage.local.get(["status", "changes"]);
  const s = data.status || {};
  const changes = data.changes || [];

  const retOk = s.lastRet && s.lastRet.startsWith("SUCCESS");
  const statusEl = document.getElementById("status");
  statusEl.innerHTML = `
    <div class="row">最近检查: <b>${s.lastCheckTs ? fmtTime(s.lastCheckTs) : "-"}</b>
      <span class="${retOk ? "ok" : "err"}">${s.lastRet || "-"}</span></div>
    <div class="row">监控商品: <b>${s.offers ?? "-"}</b> 条 · 取数方式: <b>${s.via || "-"}</b> ·
      md5校验: <b class="${s.md5SelfTest ? "ok" : "err"}">${s.md5SelfTest ? "通过" : "失败"}</b></div>
    ${s.error ? `<div class="row err">${s.error}</div>` : ""}
    <div class="row muted">轮询间隔 5 分钟; 首次运行建立基线, 之后的变化都会记录在下方。</div>`;

  const listEl = document.getElementById("changes");
  if (!changes.length) {
    listEl.innerHTML = `<div class="empty">暂无变化记录</div>`;
    return;
  }
  let html = `<table><thead><tr><th>时间</th><th>商品</th><th>字段</th><th>旧值 → 新值</th><th>变化量</th></tr></thead><tbody>`;
  for (const c of changes.slice(0, 300)) {
    const label = FIELD_LABELS[c.field] || c.field;
    const title = c.title ? `${c.title}<br><span class="muted">#${c.offerId}</span>` : `#${c.offerId}`;
    html += `<tr>
      <td class="time">${fmtTime(c.ts)}</td>
      <td class="title">${title}</td>
      <td>${label}</td>
      <td>${c.old} → ${c.new}</td>
      <td>${deltaHtml(c.delta)}</td>
    </tr>`;
  }
  html += `</tbody></table>`;
  if (changes.length > 300) html += `<div class="muted" style="padding:6px 14px;">仅显示最近 300 条(共 ${changes.length} 条)</div>`;
  listEl.innerHTML = html;
}

// 打开弹窗即清除角标
chrome.action.setBadgeText({ text: "" });

document.getElementById("btnCheck").addEventListener("click", async () => {
  const r = document.getElementById("checkResult");
  r.textContent = "检查中 ...";
  const res = await chrome.runtime.sendMessage({ type: "CHECK_NOW" });
  r.textContent = res && res.ok
    ? `本轮变化 ${res.changeCount ?? 0} 条 (${res.via || "-"})`
    : `失败: ${res ? res.error : "无响应"}`;
  render();
});

document.getElementById("btnClear").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "CLEAR_CHANGES" });
  render();
});

render();
