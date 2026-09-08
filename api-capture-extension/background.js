/* 临时工具：监听 aaa.txt 之类的 API 请求
 * 检测到后依次执行：
 *   1) 原样重发一次，检查是否成功
 *   2) 修改翻页参数后重发，检查是否成功
 *   3) 都成功则翻页读取所有数据，汇总导出 xlsx
 */
importScripts('vendor/xlsx.full.min.js');

const DEFAULTS = {
  enabled: true,
  pattern: '\\.txt(\\?|$)', // 默认匹配所有 .txt 结尾的 URL，可改为 aaa\\.txt 精确匹配
  maxPages: 200,
  pageKeys: 'page,pageNum,pageNo,pageIndex,currentPage,current,p,offset,start,pageId',
  cooldownMs: 30000
};

let cfg = { ...DEFAULTS };
chrome.storage.local.get(DEFAULTS).then(v => { cfg = { ...DEFAULTS, ...v }; });
chrome.storage.onChanged.addListener((ch, area) => {
  if (area !== 'local') return;
  for (const k of Object.keys(DEFAULTS)) {
    if (ch[k]) cfg[k] = ch[k].newValue;
  }
});

/* ---------- 日志 ---------- */
async function log(msg, level = 'info') {
  const { logs = [] } = await chrome.storage.local.get('logs');
  logs.push({ t: new Date().toLocaleTimeString('zh-CN', { hour12: false }), msg, level });
  if (logs.length > 300) logs.splice(0, logs.length - 300);
  await chrome.storage.local.set({ logs });
}

/* ---------- 捕获请求 ---------- */
const BLOCKED_HEADERS = new Set([
  'host', 'content-length', 'cookie', 'user-agent', 'origin', 'referer',
  'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-dest', 'sec-fetch-user',
  'accept-encoding', 'connection', 'sec-ch-ua', 'sec-ch-ua-mobile', 'sec-ch-ua-platform',
  'pragma', 'cache-control', 'upgrade-insecure-requests', 'te', 'trailer'
]);

function decodeRequestBody(requestBody) {
  if (!requestBody) return null;
  if (requestBody.formData) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(requestBody.formData)) {
      params.append(k, Array.isArray(v) ? v[0] : v);
    }
    return params.toString();
  }
  if (requestBody.raw && requestBody.raw.length) {
    try { return new TextDecoder().decode(requestBody.raw[0].bytes); } catch (e) { return null; }
  }
  return null;
}

function normalizeHeaders(hs) {
  const out = {};
  for (const h of hs || []) out[h.name.toLowerCase()] = h.value;
  return out;
}

const lastTrigger = {};
const running = new Map();

chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (details.tabId < 0) return;
    if (details.type !== 'xmlhttprequest' && details.type !== 'fetch') return;
    if (!cfg.enabled) return;
    let re;
    try { re = new RegExp(cfg.pattern, 'i'); } catch (e) { return; }
    if (!re.test(details.url)) return;

    const key = details.method + ' ' + details.url;
    const now = Date.now();
    if (now - (lastTrigger[key] || 0) < cfg.cooldownMs) return; // 冷却，避免重复触发
    lastTrigger[key] = now;

    const req = {
      url: details.url,
      method: details.method,
      headers: normalizeHeaders(details.requestHeaders),
      bodyText: decodeRequestBody(details.requestBody)
    };
    processCapture(req, details.tabId).catch(e => log(`异常: ${e.message}`, 'error'));
  },
  { urls: ['<all_urls>'] },
  ['requestBody', 'extraHeaders']
);

/* ---------- 发送请求 ---------- */
function looksLikeJson(s) {
  const t = (s || '').trim();
  return t.startsWith('{') || t.startsWith('[');
}

async function sendRequest(req) {
  const init = { method: req.method, credentials: 'include', cache: 'no-store' };
  const h = {};
  for (const [k, v] of Object.entries(req.headers || {})) {
    if (BLOCKED_HEADERS.has(k) || k === 'content-type') continue;
    h[k] = v;
  }
  if (req.bodyText != null) {
    init.body = req.bodyText;
    if (req.headers && req.headers['content-type']) h['content-type'] = req.headers['content-type'];
    else if (looksLikeJson(req.bodyText)) h['content-type'] = 'application/json';
  }
  if (Object.keys(h).length) init.headers = h;

  const resp = await fetch(req.url, init);
  const text = await resp.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) {}
  return { status: resp.status, ok: resp.ok, text, json };
}

/* ---------- 翻页参数处理 ---------- */
function getPageKeys() {
  return cfg.pageKeys.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
}

function pageInfo(req) {
  const u = new URL(req.url);
  const keys = getPageKeys();
  for (const k of keys) {
    const v = u.searchParams.get(k);
    if (v != null && /^\d+$/.test(v)) return { loc: 'url', key: k, val: parseInt(v, 10) };
  }
  if (req.bodyText && looksLikeJson(req.bodyText)) {
    try {
      const b = JSON.parse(req.bodyText);
      if (b && typeof b === 'object' && !Array.isArray(b)) {
        for (const k of keys) {
          if (typeof b[k] === 'number') return { loc: 'body', key: k, val: b[k] };
        }
      }
    } catch (e) {}
  }
  return null;
}

function setPage(req, info, val) {
  const r = { ...req };
  if (info.loc === 'url') {
    const u = new URL(r.url);
    u.searchParams.set(info.key, String(val));
    r.url = u.toString();
  } else {
    try {
      const b = JSON.parse(r.bodyText);
      b[info.key] = val;
      r.bodyText = JSON.stringify(b);
    } catch (e) { return null; }
  }
  return r;
}

// offset/start 风格按每页条数递增，其余按 1 递增
function stepSize(req, info) {
  if (info.key !== 'offset' && info.key !== 'start') return 1;
  const u = new URL(req.url);
  for (const k of ['size', 'limit', 'pagesize', 'count', 'perpage', 'per_page']) {
    const v = u.searchParams.get(k);
    if (v && /^\d+$/.test(v) && +v > 0) return +v;
  }
  return 1;
}

/* ---------- 从响应中提取数据行 ---------- */
function extractRows(json) {
  if (Array.isArray(json)) return json;
  if (json && typeof json === 'object') {
    for (const k of ['data', 'list', 'items', 'rows', 'records', 'result', 'results',
                     'content', 'datas', 'recordsList', 'pageList']) {
      const v = json[k];
      if (Array.isArray(v)) {
        const arr = v.filter(x => x && typeof x === 'object');
        if (arr.length) return arr;
        return v.map(x => ({ value: x })); // 基本类型数组包一层
      }
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const inner = extractRows(v);
        if (inner.length) return inner;
      }
    }
    let best = [];
    for (const k of Object.keys(json)) {
      const v = json[k];
      if (Array.isArray(v)) {
        const arr = v.filter(x => x && typeof x === 'object');
        if (arr.length > best.length) best = arr;
      }
    }
    if (best.length) return best;
    return [json]; // 单条对象
  }
  return [];
}

function flattenRows(rows) {
  return rows.map(r => {
    const out = {};
    for (const [k, v] of Object.entries(r)) {
      if (v === null || v === undefined) out[k] = '';
      else if (typeof v === 'object') out[k] = JSON.stringify(v);
      else out[k] = v;
    }
    return out;
  });
}

/* ---------- 第 3 步：翻页读取全部数据 ---------- */
async function collectAll(req, info) {
  const rows = [];
  const seen = new Set();
  const firstVal = (info.key === 'offset' || info.key === 'start') ? 0 : 1;
  let cur = setPage(req, info, firstVal); // 从第一页开始
  let page = firstVal;
  let emptyPages = 0;

  for (let i = 0; i < cfg.maxPages; i++) {
    const res = await sendRequest(cur);
    if (!res.ok) {
      await log(`第 ${i + 1} 次翻页请求失败 HTTP ${res.status}，停止抓取`, 'error');
      break;
    }
    const arr = extractRows(res.json);
    let added = 0;
    for (const row of arr) {
      const k = JSON.stringify(row);
      if (seen.has(k)) continue;
      seen.add(k);
      rows.push(row);
      added++;
    }
    await log(`翻页 ${page}：获取 ${arr.length} 条（新增 ${added} 条）`);
    if (arr.length === 0) {
      if (++emptyPages >= 2) { await log('连续空页，认为已到最后一页', 'warn'); break; }
    } else {
      emptyPages = 0;
      if (added === 0) { await log('数据与之前完全重复，翻页参数可能未生效，停止', 'warn'); break; }
    }
    const nextInfo = pageInfo(cur);
    if (!nextInfo) break;
    const inc = stepSize(cur, nextInfo);
    cur = setPage(cur, nextInfo, nextInfo.val + inc);
    page = nextInfo.val + inc;
  }
  return rows;
}

/* ---------- 导出 xlsx ---------- */
function buildXlsx(rows) {
  let sheetRows = flattenRows(rows);
  if (!sheetRows.length) sheetRows = [{ '提示': '未获取到数据' }];
  const ws = XLSX.utils.json_to_sheet(sheetRows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '数据');
  return XLSX.write(wb, { bookType: 'xlsx', type: 'base64' });
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/[^a-zA-Z0-9.-]+/g, '_'); } catch (e) { return 'unknown'; }
}
function ts() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}
function shortUrl(url) {
  return url.length > 90 ? url.slice(0, 90) + '…' : url;
}

/* ---------- 主流程 ---------- */
async function processCapture(req, tabId) {
  const key = req.method + ' ' + req.url;
  if (running.has(key)) return;
  running.set(key, true);

  await log(`=== 检测到请求 (tab ${tabId}): ${req.method} ${shortUrl(req.url)} ===`);
  try {
    const info = pageInfo(req);
    if (!info) await log('未找到翻页参数，将跳过第 2 步、仅抓取单页', 'warn');

    // 第 1 步：原样重发，检查是否成功
    const r1 = await sendRequest(req);
    if (!r1.ok) {
      await log(`[1/3] 原样重发失败: HTTP ${r1.status}，终止`, 'error');
      return;
    }
    const rows1 = extractRows(r1.json);
    await log(`[1/3] 原样重发成功: HTTP ${r1.status}，解析出 ${rows1.length} 条数据`, 'ok');

    // 第 2 步：修改翻页参数后重发，检查是否成功
    if (info) {
      const req2 = setPage(req, info, info.val + stepSize(req, info));
      const r2 = await sendRequest(req2);
      if (!r2.ok) {
        await log(`[2/3] 翻页重发失败: HTTP ${r2.status}，终止`, 'error');
        return;
      }
      const rows2 = extractRows(r2.json);
      await log(`[2/3] 翻页重发成功: HTTP ${r2.status}，解析出 ${rows2.length} 条数据`, 'ok');
      if (rows1.length && rows2.length &&
          JSON.stringify(rows1[0]) === JSON.stringify(rows2[0])) {
        await log('提示: 两页首条数据相同，翻页参数可能未生效', 'warn');
      }
    } else {
      await log('[2/3] 跳过（未找到翻页参数）', 'warn');
    }

    // 第 3 步：前两步成功，读取所有数据导出 xlsx
    const rows = info ? await collectAll(req, info) : rows1;
    await log(`[3/3] 共获取 ${rows.length} 条数据，生成 xlsx…`);
    const b64 = buildXlsx(rows);
    const filename = `api-capture/${hostOf(req.url)}_${ts()}.xlsx`;
    const id = await chrome.downloads.download({
      url: 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + b64,
      filename,
      conflictAction: 'uniquify'
    });
    await log(`[3/3] 完成！已导出 ${filename}（${rows.length} 行）`, 'ok');
  } catch (e) {
    await log(`异常: ${e && e.message ? e.message : e}`, 'error');
  } finally {
    running.delete(key);
  }
}
