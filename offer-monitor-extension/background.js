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

function attachToExistingTabs() {
  chrome.tabs.query({ url: "https://detail.1688.com/*" }, (tabs) => {
    for (const t of tabs || []) {
      if (t.id != null) attachDebugger(t.id);
    }
  });
}

chrome.runtime.onInstalled.addListener(() => { schedule(); check(); pushSessionToMonitor(); attachToExistingTabs(); });
chrome.runtime.onStartup.addListener(() => { schedule(); check(); pushSessionToMonitor(); attachToExistingTabs(); });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") { check(); pushSessionToMonitor(); } });

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

// ---------------- 会话情报: 旁听插件密钥 + 推送本机巡检程序 ----------------
// 插件(1688 官方插件)发出的 offerList 请求带有效密钥, 且与本浏览器会话绑定。
// 本扩展与插件同 profile, 通过 webRequest 旁听拿到最新密钥,
// 连同实时 cookie 一起推送给本机巡检程序(127.0.0.1:18999/session),
// 巡检程序即可用与浏览器完全一致的凭据直连接口。
const LOCAL_SERVER = "http://127.0.0.1:18999";
let lastSecretPush = 0;

chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    const isOffer = details.url.toLowerCase().includes("offerlist");
    const h = (details.requestHeaders || []).find(
      (x) => x.name && x.name.toLowerCase() === "x-1688extension-secret");
    chrome.storage.local.get(["h5apiSeen", "h5apiWithSecret", "offerlistSeen", "offerlistWithSecret", "offerlistSamples"]).then((st) => {
      const patch = {
        h5apiSeen: (st.h5apiSeen || 0) + 1,
        h5apiWithSecret: (st.h5apiWithSecret || 0) + (h && h.value ? 1 : 0),
      };
      if (isOffer) {
        const samples = (st.offerlistSamples || []).slice(-4);
        samples.push({
          ts: Date.now(),
          url: details.url.slice(0, 900),
          hasSecret: !!(h && h.value),
          headerNames: (details.requestHeaders || []).map((x) => x.name).slice(0, 40),
        });
        patch.offerlistSeen = (st.offerlistSeen || 0) + 1;
        patch.offerlistWithSecret = (st.offerlistWithSecret || 0) + (h && h.value ? 1 : 0);
        patch.offerlistSamples = samples;
      }
      chrome.storage.local.set(patch);
    });
    if (h && h.value) {
      chrome.storage.local.set({ learnedSecret: h.value, learnedSecretTs: Date.now() });
      const now = Date.now();
      if (now - lastSecretPush > 30000) {
        lastSecretPush = now;
        pushSessionToMonitor();
      }
    }
  },
  { urls: ["https://h5api.m.1688.com/*"] },
  ["requestHeaders"]
);

// ---------------- CDP 调试器捕获(拿到 DNR 注入后的真实请求头与响应体) ----------------
// 插件密钥经 DNR 会话规则注入, webRequest 看不到; CDP(DevTools 协议)能看到最终发送的头。
// 附加到详情页标签后, 捕获插件 offerlist 请求的真实密钥与响应数据, 转发给本机程序。
const DEBUGGED_TABS = new Map();   // tabId -> 附加时间
const PENDING_BODY = new Map();    // requestId -> url
const CDP_ATTACH_MS = 3 * 60 * 1000;

function cdpLog(line) {
  chrome.storage.local.get("cdpLog").then((st) => {
    const arr = (st.cdpLog || []).slice(-19);
    arr.push({ ts: Date.now(), line: String(line).slice(0, 300) });
    chrome.storage.local.set({ cdpLog: arr });
  });
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "complete" && tab && tab.url && tab.url.startsWith("https://detail.1688.com")) {
    attachDebugger(tabId);
  }
});

function attachDebugger(tabId) {
  if (DEBUGGED_TABS.has(tabId)) return;
  chrome.debugger.attach({ tabId }, "1.3", () => {
    if (chrome.runtime.lastError) {
      cdpLog("附加失败: " + chrome.runtime.lastError.message);
      return;
    }
    chrome.debugger.sendCommand({ tabId }, "Network.enable", {}, () => {
      DEBUGGED_TABS.set(tabId, Date.now());
      cdpLog("CDP 已附加到标签 " + tabId + " (3分钟后自动解除)");
      setTimeout(() => detachDebugger(tabId), CDP_ATTACH_MS);
      pushSessionToMonitor();
    });
  });
}

function detachDebugger(tabId) {
  if (!DEBUGGED_TABS.has(tabId)) return;
  DEBUGGED_TABS.delete(tabId);
  chrome.debugger.detach({ tabId }, () => {});
  cdpLog("CDP 已从标签 " + tabId + " 解除");
}

chrome.debugger.onEvent.addListener((source, method, params) => {
  if (!source.tabId || !DEBUGGED_TABS.has(source.tabId)) return;
  if (method === "Network.requestWillBeSent") {
    const url = params.request && params.request.url ? params.request.url : "";
    const headers = (params.request && params.request.headers) || {};
    // 捕获插件所有相关请求: offerlist / 插件后端 / 其他 h5api 调用
    if (url.toLowerCase().includes("offerlist.query")) {
      const secret = headers["x-1688extension-secret"] || headers["X-1688extension-Secret"];
      if (secret) {
        chrome.storage.local.set({ learnedSecret: secret, learnedSecretTs: Date.now() });
        cdpLog("CDP 学到插件密钥: " + secret.slice(0, 16) + "...");
        const now = Date.now();
        if (now - lastSecretPush > 30000) {
          lastSecretPush = now;
          pushSessionToMonitor();
        }
      } else {
        cdpLog("offerlist 无密钥头 | Referer=" + (headers["Referer"] || headers["referer"] || "-")
               + " | 头名: " + Object.keys(headers).slice(0, 40).join(","));
      }
      PENDING_BODY.set(params.requestId, url);
    } else if (/alibaba-inc\.com|creep|anti|token/i.test(url)) {
      cdpLog("疑似插件后端请求: " + url.slice(0, 200));
      PENDING_BODY.set(params.requestId, url);
    } else if (url.includes("h5api.m.1688.com") && /mtop\.1688\.pc\.plugin\./i.test(url)) {
      // 插件抽屉的新版私有接口(od.data.query 等), 记录完整 URL 与响应体
      cdpLog("plugin接口请求: " + url.slice(0, 600));
      PENDING_BODY.set(params.requestId, url);
    }
  } else if (method === "Network.responseReceived") {
    if (!PENDING_BODY.has(params.requestId)) return;
    const url = PENDING_BODY.get(params.requestId);
    if (params.response && params.response.status === 200) {
      chrome.debugger.sendCommand(
        { tabId: source.tabId },
        "Network.getResponseBody",
        { requestId: params.requestId },
        (r) => {
          PENDING_BODY.delete(params.requestId);
          if (!r || !r.body) return;
          if (url.toLowerCase().includes("offerlist.query")) {
            try {
              const j = JSON.parse(r.body);
              const ret = j && j.ret ? j.ret[0] : "?";
              if (j && j.ret && j.ret[0] === "SUCCESS::调用成功" && j.data && j.data.simpleOfferModelList) {
                cdpLog("插件 offerlist 响应成功, 商品 " + j.data.simpleOfferModelList.length + " 条, 已转发本机程序");
                forwardOfferlist({ all: j.data.simpleOfferModelList, offerCount: j.data.offerCount });
              } else {
                cdpLog("插件 offerlist 响应: ret=" + String(ret).slice(0, 100));
              }
            } catch (e) {
              cdpLog("插件 offerlist 响应非 JSON: " + r.body.slice(0, 120));
            }
          } else if (/mtop\.1688\.pc\.plugin\./i.test(url)) {
            cdpLog("plugin接口响应: " + r.body.slice(0, 400));
          } else {
            cdpLog("后端响应体: " + r.body.slice(0, 250));
          }
        }
      );
    } else {
      PENDING_BODY.delete(params.requestId);
    }
  }
});

// 插件后端的 token 请求若由插件 service worker 发起, 标签级 CDP 看不到,
// 用全量 webRequest 兜底捕获
chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    if (/alibaba-inc\.com|creep|anti|token/i.test(details.url)) {
      cdpLog("webRequest 后端请求: " + details.url.slice(0, 200));
    }
  },
  { urls: ["<all_urls>"] },
  ["requestHeaders"]
);

async function forwardOfferlist(outcome) {
  // 检查成功后, 把全量商品数据转发给本机巡检程序(持久化由程序负责)
  try {
    await fetch(`${LOCAL_SERVER}/offerlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simpleOfferModelList: outcome.all, offerCount: outcome.offerCount }),
    });
    console.log("巡检数据已转发给本机程序 (商品", outcome.all.length, "条)");
  } catch (e) {
    // 本机巡检程序未运行, 忽略
  }
}

async function pushSessionToMonitor() {
  try {
    const stored = await chrome.storage.local.get([
      "learnedSecret", "h5apiSeen", "h5apiWithSecret",
      "offerlistSeen", "offerlistWithSecret", "offerlistSamples", "cdpLog",
    ]);
    // 两种方式收集 cookie 并合并, 确保覆盖 _m_h5_tk 的域名作用域
    const c1 = await chrome.cookies.getAll({ domain: "1688.com" });
    const c2 = await chrome.cookies.getAll({ url: "https://h5api.m.1688.com/" });
    const map = new Map();
    for (const c of [...c1, ...c2]) map.set(c.name, c.value);
    const cookieStr = [...map.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
    await fetch(`${LOCAL_SERVER}/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret: stored.learnedSecret || "",
        cookie: cookieStr,
        diag: {
          h5apiSeen: stored.h5apiSeen || 0,
          h5apiWithSecret: stored.h5apiWithSecret || 0,
          hasMh5tk: map.has("_m_h5_tk"),
          offerlistSeen: stored.offerlistSeen || 0,
          offerlistWithSecret: stored.offerlistWithSecret || 0,
          offerlistSamples: stored.offerlistSamples || [],
          cdpLog: stored.cdpLog || [],
        },
      }),
    });
    console.log("会话信息已推送给本机巡检程序 (cookie", map.size, "个, _m_h5_tk:", map.has("_m_h5_tk"),
                ", h5api请求:", stored.h5apiSeen || 0, ", 带密钥:", stored.h5apiWithSecret || 0,
                ", offerlist请求:", stored.offerlistSeen || 0, ", 其中带密钥:", stored.offerlistWithSecret || 0, ")");
  } catch (e) {
    // 本机巡检程序未运行或不可达, 忽略
  }
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

// 后台直连(带本浏览器 cookie; 若已旁听到插件密钥则一并带上)
async function fetchPageDirect(pageNum) {
  const url = await buildUrl(pageNum);
  const stored = await chrome.storage.local.get("learnedSecret");
  const headers = { accept: "*/*" };
  if (stored.learnedSecret) headers["x-1688extension-secret"] = stored.learnedSecret;
  const resp = await fetch(url, { credentials: "include", headers });
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
    if (outcome.ok) {
      forwardOfferlist(outcome);
      pushSessionToMonitor();
    }
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
