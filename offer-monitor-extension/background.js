// 1688 旺铺商品列表监控 - 后台服务
// 每 5 分钟轮询 offerList.query, 与上次快照对比, 变化写入 storage(changes) 并亮角标
importScripts("md5.js");

const APP_KEY = "12574478";
const API = "mtop.1688.pc.plugin.shop.offerList.query";
const BASE_URL = "https://h5api.m.1688.com/h5/mtop.1688.pc.plugin.shop.offerlist.query/1.1/";
const BIZ = { memberId: "b2b-319033927380e11", sortType: "wangpu_score", pageNum: 1, pageSize: 300 };
const POLL_MINUTES = 5;
const DETAIL_URL = "https://detail.1688.com/offer/951308633342.html";
const FIELDS = ["price", "agentPrice", "saleQuantity", "agentBookedCount", "evaluateCounts", "thirtyBookCount"];

// md5 自校验: 用抓包里已知的 token/t/sign 三元组验证本实现
const MD5_SELF_TEST = md5(
  "ba83020e92227c3a9c5036142dcef178&1788786847907&12574478&" +
  '{"memberId":"b2b-319033927380e11","sortType":"wangpu_score","pageNum":1,"pageSize":300}'
) === "0c341bc9e34c648c0a45cfdd24007d05";

chrome.runtime.onInstalled.addListener(() => { schedule(); check(); });
chrome.runtime.onStartup.addListener(() => { schedule(); check(); });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") check(); });

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "CHECK_NOW") { check().then((r) => sendResponse(r)); return true; }
  if (msg && msg.type === "CLEAR_CHANGES") {
    chrome.storage.local.set({ changes: [] }).then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});

function schedule() {
  chrome.alarms.create("poll", { periodInMinutes: POLL_MINUTES });
}

async function buildUrl(pageNum) {
  const ck = await chrome.cookies.get({ url: "https://www.1688.com/", name: "_m_h5_tk" });
  if (!ck || !ck.value) throw new Error("未找到 _m_h5_tk cookie, 需在浏览器里登录 1688");
  const token = ck.value.split("_")[0];
  const dataStr = JSON.stringify({ ...BIZ, pageNum }); // 紧凑 JSON, 签名基于它
  const t = Date.now();
  const sign = md5(`${token}&${t}&${APP_KEY}&${dataStr}`);
  const p = new URLSearchParams({
    jsv: "2.7.2", appKey: APP_KEY, t: String(t), sign,
    dataType: "json", api: API, v: "1.1", type: "originaljson", data: dataStr,
  });
  return BASE_URL + "?" + p.toString();
}

// 后台直连(带本浏览器 cookie; 1688 插件若在网络层注入密钥则直接可用)
async function fetchPageDirect(pageNum) {
  const url = await buildUrl(pageNum);
  const resp = await fetch(url, { credentials: "include", headers: { accept: "*/*" } });
  return { status: resp.status, body: await resp.text() };
}

// 页面上下文取数(在 1688 页面的主世界里执行 fetch, 与插件自身调用同一环境)
async function fetchPageInTab(tabId, pageNum) {
  const url = await buildUrl(pageNum);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: async (u) => {
      try {
        const r = await fetch(u, { credentials: "include" });
        return { status: r.status, body: await r.text() };
      } catch (e) { return { status: 0, body: String(e) }; }
    },
    args: [url],
  });
  return results && results[0] ? results[0].result : null;
}

async function waitTabLoaded(tabId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

async function collectAll() {
  // 方式一: 后台直连
  try {
    const first = await fetchPageDirect(1);
    const j = JSON.parse(first.body);
    if (j && j.ret && j.ret[0] === "SUCCESS::调用成功") {
      const all = [...(j.data.simpleOfferModelList || [])];
      const offerCount = j.data.offerCount || 0;
      for (let p = 2; all.length < offerCount && p <= 10; p++) {
        const jj = JSON.parse((await fetchPageDirect(p)).body);
        if (!(jj.ret && jj.ret[0] === "SUCCESS::调用成功")) break;
        all.push(...(jj.data.simpleOfferModelList || []));
      }
      return { ok: true, via: "后台直连", all, offerCount, ret: j.ret };
    }
    console.log("后台直连返回:", j && j.ret);
  } catch (e) {
    console.warn("后台直连异常:", e);
  }

  // 方式二: 页面上下文(1688 页面主世界)
  let tab = null;
  const tabs = await chrome.tabs.query({ url: ["https://detail.1688.com/*", "https://www.1688.com/*"] });
  tab = (tabs || []).find((t) => t.id != null);
  if (!tab) {
    tab = await chrome.tabs.create({ url: DETAIL_URL, active: false });
    await waitTabLoaded(tab.id, 30000);
  }
  const first = await fetchPageInTab(tab.id, 1);
  if (!first || !first.body) return { ok: false, via: "页面上下文", error: "页面上下文取数失败" };
  let j;
  try { j = JSON.parse(first.body); } catch (e) { return { ok: false, via: "页面上下文", error: "响应不是 JSON: " + e }; }
  if (!(j.ret && j.ret[0] === "SUCCESS::调用成功")) {
    return { ok: false, via: "页面上下文", ret: j.ret, error: "页面上下文返回: " + JSON.stringify(j.ret) };
  }
  const all = [...(j.data.simpleOfferModelList || [])];
  const offerCount = j.data.offerCount || 0;
  for (let p = 2; all.length < offerCount && p <= 10; p++) {
    const r = await fetchPageInTab(tab.id, p);
    const jj = JSON.parse(r.body);
    if (!(jj.ret && jj.ret[0] === "SUCCESS::调用成功")) break;
    all.push(...(jj.data.simpleOfferModelList || []));
  }
  return { ok: true, via: "页面上下文", all, offerCount, ret: j.ret };
}

function pick(o) {
  const s = { title: o.title || "" };
  for (const f of FIELDS) s[f] = o[f];
  return s;
}

function toNum(v) {
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

function mkChange(ts, id, title, field, oldV, newV, delta) {
  return { ts, offerId: String(id), title, field, old: String(oldV), new: String(newV), delta };
}

async function compareAndStore(outcome) {
  const now = Date.now();
  const status = {
    lastCheckTs: now,
    lastRet: outcome.ret ? outcome.ret[0] : "FAILED",
    via: outcome.via || "-",
    offers: outcome.all ? outcome.all.length : 0,
    md5SelfTest: MD5_SELF_TEST,
    error: outcome.error || "",
  };
  const patch = { status };
  let newChangeCount = 0;

  if (outcome.ok) {
    const stored = await chrome.storage.local.get("snapshot");
    const oldSnap = stored.snapshot ? stored.snapshot.offers : null;
    const oldCount = stored.snapshot ? stored.snapshot.offerCount : null;
    const newSnap = {};
    for (const o of outcome.all) newSnap[o.offerId] = pick(o);
    const changes = [];

    if (oldSnap) {
      for (const o of outcome.all) {
        const prev = oldSnap[o.offerId];
        if (!prev) {
          changes.push(mkChange(now, o.offerId, o.title, "__新增商品__", "", "", ""));
          continue;
        }
        for (const f of FIELDS) {
          const a = toNum(prev[f]);
          const b = toNum(o[f]);
          if (a !== b) changes.push(mkChange(now, o.offerId, o.title, f, prev[f], o[f], b - a));
        }
      }
      const newIds = new Set(outcome.all.map((o) => String(o.offerId)));
      for (const id of Object.keys(oldSnap)) {
        if (!newIds.has(id)) changes.push(mkChange(now, id, oldSnap[id].title || "", "__下架/移除__", "", "", ""));
      }
      if (oldCount != null && oldCount !== outcome.offerCount) {
        changes.push(mkChange(now, "-", "店铺商品总数", "offerCount", oldCount, outcome.offerCount, outcome.offerCount - oldCount));
      }
    }

    if (changes.length) {
      const cur = await chrome.storage.local.get("changes");
      patch.changes = [...changes, ...(cur.changes || [])].slice(0, 2000);
      newChangeCount = changes.length;
    }
    patch.snapshot = { offers: newSnap, offerCount: outcome.offerCount, ts: now };
  }

  await chrome.storage.local.set(patch);

  if (newChangeCount > 0) {
    chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
    chrome.action.setBadgeText({ text: String(newChangeCount > 999 ? "999+" : newChangeCount) });
  } else {
    chrome.action.setBadgeText({ text: "" });
  }
  return { changeCount: newChangeCount };
}

let busy = false;
async function check() {
  if (!MD5_SELF_TEST) {
    await chrome.storage.local.set({
      status: { lastCheckTs: Date.now(), lastRet: "MD5_SELF_TEST_FAILED", via: "-", offers: 0, md5SelfTest: false, error: "md5 自校验失败, 请重新加载扩展" },
    });
    return { ok: false, error: "md5 自校验失败" };
  }
  if (busy) return { ok: false, error: "已有检查在进行中" };
  busy = true;
  try {
    const outcome = await collectAll();
    const meta = await compareAndStore(outcome);
    return { ok: outcome.ok, changeCount: meta.changeCount, via: outcome.via, ret: outcome.ret ? outcome.ret[0] : "", error: outcome.error || "" };
  } catch (e) {
    await chrome.storage.local.set({
      status: { lastCheckTs: Date.now(), lastRet: "EXCEPTION", via: "-", offers: 0, md5SelfTest: MD5_SELF_TEST, error: String(e) },
    });
    return { ok: false, error: String(e) };
  } finally {
    busy = false;
  }
}
