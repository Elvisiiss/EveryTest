const $ = id => document.getElementById(id);

const DEFAULTS = {
  enabled: true,
  pattern: '\\.txt(\\?|$)',
  maxPages: 200,
  pageKeys: 'page,pageNum,pageNo,pageIndex,currentPage,current,p,offset,start,pageId'
};

chrome.storage.local.get(DEFAULTS).then(v => {
  $('enabled').checked = !!v.enabled;
  $('pattern').value = v.pattern;
  $('pageKeys').value = v.pageKeys;
  $('maxPages').value = v.maxPages;
});

$('save').addEventListener('click', () => {
  chrome.storage.local.set({
    enabled: $('enabled').checked,
    pattern: $('pattern').value,
    pageKeys: $('pageKeys').value,
    maxPages: parseInt($('maxPages').value, 10) || 200
  });
});

$('clear').addEventListener('click', () => {
  chrome.storage.local.set({ logs: [] });
});

function render() {
  chrome.storage.local.get('logs').then(({ logs = [] }) => {
    const el = $('log');
    if (!logs.length) {
      el.textContent = '（暂无日志。打开目标网页，让页面发出 .txt 请求即可触发）';
      return;
    }
    el.innerHTML = logs.map(l => {
      const cls = l.level === 'ok' ? 'ok' : l.level === 'warn' ? 'warn' : l.level === 'error' ? 'error' : '';
      return `<div class="${cls}">[${l.t}] ${escapeHtml(l.msg)}</div>`;
    }).join('');
    el.scrollTop = el.scrollHeight;
  });
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

render();
setInterval(render, 1000);
