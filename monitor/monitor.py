# -*- coding: utf-8 -*-
"""
1688 旺铺商品列表巡检程序
=========================
功能:
  1. 每 5 分钟巡检一次 mtop.1688.pc.plugin.shop.offerList.query 接口(自动翻页取全量商品)
  2. 每次巡检结果写入 monitor.xlsx:
       - 巡检记录: 每轮一行(时间/接口状态/取数方式/商品总数/本页条数/变化数/错误信息)
       - 变化记录: 字段变化明细(时间/商品ID/标题/字段/旧值/新值/变化量)
       - 商品快照: 全店商品最新状态(重启后从该表恢复对比基线)
  3. 日志同时输出到黑窗口(控制台)和 monitor.log
  4. 内置 127.0.0.1:18999 接收端, 供浏览器扩展转发接口数据(解决插件密钥问题的预留通道)

启动: 双击 run.bat(黑窗口)
依赖: openpyxl, requests(装到项目 .venv, 清华源)
"""

import hashlib
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

import requests
from openpyxl import Workbook, load_workbook

# Windows 控制台默认 GBK, 统一按 UTF-8 输出避免乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 路径与常量 ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(BASE_DIR, "monitor.xlsx")
LOG_PATH = os.path.join(BASE_DIR, "monitor.log")

APP_KEY = "12574478"
API = "mtop.1688.pc.plugin.shop.offerList.query"
BASE_URL = "https://h5api.m.1688.com/h5/mtop.1688.pc.plugin.shop.offerlist.query/1.1/"
BIZ = {"memberId": "b2b-319033927380e11", "sortType": "wangpu_score", "pageNum": 1, "pageSize": 300}
POLL_SECONDS = 300
HTTP_PORT = 18999

COOKIE = ('leftMenuLastMode=COLLAPSE; trackId=be24b3777739464f8ba780d146360aaa; '
          'keywordsHistory=%E6%89%8B%E6%9C%BA%E5%A3%B3; cookie2=1404d75bf1649ce274059fd7331ae840; '
          't=7bee0057fb1829e37ae8c5a33d4947af; _tb_token_=773ab3563338; lid=tb7763084704; '
          'ali_apache_track=c_mid=b2b-221455216111860f88|c_lid=tb7763084704|c_ms=1; '
          'taklid=1565d5e192e34548b1013653b703c3b5; leftMenuModeTip=shown; xlly_s=1; '
          'union={"amug_biz":"oneself","amug_fl_src":"awakeId_982","creative_url":"https%3A%2F%2Fdetail.1688.com%2Foffer%2F951308633342.html%3Ffromkv%3DcbuPcPlugin%3AimageSearchDrawerTable%26spm%3Da2639h.29135425.offerlist.i0%26source%3Daction%2523offerItem%253Borigin%2523www.1688.com%26amug_biz%3Doneself%26amug_fl_src%3DawakeId_982","creative_time":1788786755279}; '
          '_samesite_flag_=true; tracknick=; '
          'cookie1=Vvyi6qIHHwbJa7JYCsIgdDBrrpdsHM8SjV5ROrPjxWI%3D; cookie17=UUpgQhWS3aocZH7VIQ%3D%3D; '
          'sgcookie=E100VA8sqShBbw9VYAlGs%2FY6%2FxEIlYt8W%2F%2B%2B4nwK%2BUAeIox%2F2fHGqW3A9b%2Fd7eN7vdI11JqlPK8%2FY2Xmaqfcvmv013br8%2B%2Fz8Sd3kuKO7ij53uo%3D; sg=482; csg=f20a8741; '
          'unb=2214552161118; uc4=id4=0%40U2gqzcVL6qMJv1kX8mYcvnXE4M7k6ao2&nk4=0%40FY4JjCgQefmM%2FLhBNIc2Yi9OHYo9lXY%3D; '
          '_nk_=tb7763084704; last_mid=b2b-221455216111860f88; _csrf_token=1788786824109; '
          '__cn_logon__=true; __cn_logon_id__=tb7763084704; __last_loginid__=b2b-221455216111860f88; '
          '__last_memberid__=b2b-221455216111860f88; '
          '_user_vitals_session_data_={"user_line_track":true,"ul_session_id":"hgw91f9uzen","last_page_id":"detail.1688.com%2Fvozzckgi6h"}; '
          'cna=tqceI1CDDBwBASQKQsZS1YYu; oversearegion=CN; oversealanguage=zh; overseacurrency=CNY; '
          'overseacountries=CN; mtop_partitioned_detect=1; '
          '_m_h5_tk=ba83020e92227c3a9c5036142dcef178_1788796205866; _m_h5_tk_enc=02165cbb7279d867d9bd226ceb32656e; '
          'tfstk=gzEZuUX4VGINg-1uU8mVaGsIK_itum55ioGjn-2mCfcGWPg08xMWiI2c6Srqt5BtGmiG0rPU9E6tGOppmSlL5IGfBrl01W3jSc6vunyqTha1WqG23XVZ5OE4Hnk0nSBtGOQQBRnxm_17ggwTBYYAiUZZI2D3pxJMswgMqdX_r_15VM_MKm5NN-9yqrgnUYmmIfci-9kSEEmmSAjhLxDXsExgiJXE9YvMsmxGxpDshmc0imXUKXHmmAVmm9yn9xDhmR2DYYgGqmLbU6tJk2cuIX-D4LHZSRj-tnx0YAyEZRYemnqEQVrB9BPL1Va0e4E_ji-Kf8znxYwObHouIYPsO7jkYD2QKSg8JsKSJWrqyl0Mn9c3bWrtj5_D47oag4qi8KxbIJctYvqlhUhQYfN0b2XW4qi3V4mgRwCslckzilFw3nVud8ZtJo5ytjUseDD7BG-EqRDc42dxKibbDPRDoVDKLb6FLuXCMBeVEDSMkE3n2vl5CATvkVDKLb6FLELx-YHENOM1.; '
          'isg=BJycKqQMGjHKNu7k5iMIBoJJbbpOFUA_seTv03ad9AdqwT1Lniccz9djIyk5yXiX')

EXTENSION_SECRET = ('tMrw7DZ7MZzkt0fGiWrinjC0W8MI3SSHnZL4lGZjc0Sbo+IJlD6Wb/RAlePuMMBfIGe/aJ5D2vuRaX+ukJW+UeVsm'
                    'DuPJcbqklV8mfWZCjON6Ifpl4qu/m3iQK2a/NkWxIKhuHhhYWX1CnSjLtrBFZ+JynVlSyHnz5y8D+RZIlL5MpfW5U'
                    '+SxapLtNFXJ+QcFQ/DNOZ7mK72aRYj5QrepnvWnW3CTQv63o4afXxlMwjPJprZDvCPx12jvDSY6amr4TacgkARme1'
                    'H1b75lnhdcL0spvCE')

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0")

FIELDS = [
    ("price", "价格"), ("agentPrice", "分销价"), ("saleQuantity", "销量"),
    ("agentBookedCount", "分销预定量"), ("evaluateCounts", "评价数"), ("thirtyBookCount", "30天预定数"),
]

logger = logging.getLogger("monitor")
XLSX_LOCK = threading.Lock()
EXT_QUEUE = []          # 扩展转发过来的数据
EXT_Q_LOCK = threading.Lock()
SESSION_LOCK = threading.Lock()   # COOKIE / EXTENSION_SECRET 为动态会话凭据, 可被扩展推送刷新
SESSION_CHANGED = threading.Event()  # 扩展推送新会话后立即唤醒巡检


def current_headers() -> dict:
    """每次请求实时取当前会话凭据(浏览器扩展会通过 /session 推送刷新)"""
    with SESSION_LOCK:
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "accept-encoding": "gzip, deflate",
            "origin": "https://www.1688.com",
            "referer": "https://www.1688.com/",
            "user-agent": USER_AGENT,
            "cookie": COOKIE,
            "x-1688extension-secret": EXTENSION_SECRET,
        }


# ---------------- 日志 ----------------
def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_PATH, encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ---------------- 接口调用 ----------------
def build_sign(token: str, t: int, app_key: str, data: str) -> str:
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode("utf-8")).hexdigest()


def merge_cookies(old: str, new: str) -> str:
    """按 cookie 名合并, 新值覆盖旧值, 保留新集合里没有的旧条目"""
    merged = dict(item.split("=", 1) for item in old.split("; ") if "=" in item)
    for item in new.split("; "):
        if "=" in item:
            k, v = item.split("=", 1)
            merged[k] = v
    return "; ".join(f"{k}={v}" for k, v in merged.items())


def get_token() -> str:
    """从当前会话 cookie 里取 _m_h5_tk 的 token 部分"""
    with SESSION_LOCK:
        cookie_s = COOKIE
    tk = dict(item.split("=", 1) for item in cookie_s.split("; ") if "=" in item).get("_m_h5_tk", "")
    return tk.split("_", 1)[0] if tk else ""


def make_url(page_num: int) -> str:
    data_str = json.dumps({**BIZ, "pageNum": page_num}, separators=(",", ":"), ensure_ascii=False)
    t = int(time.time() * 1000)
    token = get_token()
    sign = build_sign(token, t, APP_KEY, data_str)
    params = {
        "jsv": "2.7.2", "appKey": APP_KEY, "t": t, "sign": sign,
        "dataType": "json", "api": API, "v": "1.1",
        "type": "originaljson", "data": data_str,
    }
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_all():
    """直接调接口并翻页取全量, 返回 (ok, offers, total, ret, error)"""
    try:
        j = requests.get(make_url(1), headers=current_headers(), timeout=30).json()
        if j.get("ret") != ["SUCCESS::调用成功"]:
            return False, [], 0, j.get("ret", []), ""
        offers = list(j["data"].get("simpleOfferModelList") or [])
        total = j["data"].get("offerCount") or 0
        page = 2
        while len(offers) < total and page <= 10:
            jj = requests.get(make_url(page), headers=current_headers(), timeout=30).json()
            if jj.get("ret") != ["SUCCESS::调用成功"]:
                logger.warning("第 %d 页返回: %s", page, jj.get("ret"))
                break
            offers += jj["data"].get("simpleOfferModelList") or []
            page += 1
        return True, offers, total, j.get("ret", []), ""
    except Exception as e:
        return False, [], 0, [], repr(e)


# ---------------- xlsx 持久化 ----------------
def init_xlsx() -> None:
    if os.path.exists(XLSX_PATH):
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "巡检记录"
    ws.append(["时间", "接口状态", "取数方式", "商品总数", "本页条数", "变化数", "错误信息"])
    wb.create_sheet("变化记录").append(["时间", "商品ID", "商品标题", "字段", "旧值", "新值", "变化量"])
    wb.create_sheet("商品快照").append(["商品ID", "商品标题", "价格", "分销价", "销量", "分销预定量", "评价数", "30天预定数"])
    wb.save(XLSX_PATH)


def append_check_record(row) -> None:
    with XLSX_LOCK:
        wb = load_workbook(XLSX_PATH)
        wb["巡检记录"].append(row)
        wb.save(XLSX_PATH)


def append_changes(rows) -> None:
    if not rows:
        return
    with XLSX_LOCK:
        wb = load_workbook(XLSX_PATH)
        ws = wb["变化记录"]
        for r in rows:
            ws.append(r)
        wb.save(XLSX_PATH)


def rewrite_snapshot(snapshot: dict) -> None:
    with XLSX_LOCK:
        wb = load_workbook(XLSX_PATH)
        ws = wb["商品快照"]
        if ws.max_row > 1:
            ws.delete_rows(2, ws.max_row - 1)
        for oid, s in snapshot.items():
            ws.append([oid, s.get("title", ""), s.get("price"), s.get("agentPrice"),
                       s.get("saleQuantity"), s.get("agentBookedCount"),
                       s.get("evaluateCounts"), s.get("thirtyBookCount")])
        wb.save(XLSX_PATH)


def load_baseline() -> dict:
    """从 xlsx 商品快照表恢复上次基线(程序重启后变化对比不中断)"""
    if not os.path.exists(XLSX_PATH):
        return {}
    wb = load_workbook(XLSX_PATH, read_only=True)
    snap = {}
    try:
        ws = wb["商品快照"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            snap[str(row[0])] = {"title": row[1] or "", "price": row[2], "agentPrice": row[3],
                                 "saleQuantity": row[4], "agentBookedCount": row[5],
                                 "evaluateCounts": row[6], "thirtyBookCount": row[7]}
    finally:
        wb.close()
    return snap


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------- 巡检与对比 ----------------
def process_offers(offers, via) -> dict:
    """对比快照, 写 xlsx, 返回新快照; 传入 offers=[] 且 status 非空表示失败轮"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    baseline = BASELINE.copy()
    changes = []
    new_snap = {}

    for o in offers:
        oid = str(o.get("offerId"))
        new_snap[oid] = {"title": o.get("title") or "", **{f: o.get(f) for f, _ in FIELDS}}

    if baseline:
        new_ids = set(new_snap)
        for oid, prev in baseline.items():
            if oid not in new_ids:
                changes.append([now_str, oid, prev.get("title", ""), "下架/移除", "", "", ""])
        for oid, cur in new_snap.items():
            prev = baseline.get(oid)
            if prev is None:
                changes.append([now_str, oid, cur.get("title", ""), "新增商品", "", "", ""])
                continue
            for f, label in FIELDS:
                a, b = to_num(prev.get(f)), to_num(cur.get(f))
                if a != b:
                    changes.append([now_str, oid, cur.get("title", ""), label, prev.get(f), cur.get(f), b - a])

    rewrite_snapshot(new_snap)
    append_changes(changes)
    append_check_record([now_str, "SUCCESS::调用成功", via, len(offers), len(offers), len(changes), ""])

    logger.info("巡检成功(%s): 商品 %d 条, 本轮变化 %d 条", via, len(offers), len(changes))
    for c in changes[:50]:
        if c[3] in ("新增商品", "下架/移除"):
            logger.info("  变化: [%s] %s %s", c[3], c[1], c[2])
        else:
            logger.info("  变化: [%s] #%s %s: %s -> %s (%+.0f)", c[3], c[1], c[2], c[4], c[5], c[6])
    return new_snap


def process_failure(ret, error, via) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = (ret or ["EXCEPTION"])[0] if ret else "EXCEPTION"
    append_check_record([now_str, status, via, None, 0, 0, error or ""])
    logger.warning("巡检失败(%s): 状态=%s 错误=%s", via, status, error or "-")


# ---------------- 扩展转发接收端(解决插件密钥问题的预留通道) ----------------
class HttpHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        if self.path == "/session":
            # 浏览器扩展推送的最新会话凭据(密钥 + cookie), 刷新动态凭据(按名合并)
            global COOKIE, EXTENSION_SECRET
            secret = body.get("secret") or ""
            cookie = body.get("cookie") or ""
            diag = body.get("diag") or {}
            with SESSION_LOCK:
                if cookie:
                    COOKIE = merge_cookies(COOKIE, cookie)
                if secret:
                    EXTENSION_SECRET = secret
            logger.info("会话已刷新(来源:浏览器扩展): secret=%s, cookie合计=%d个, 含_m_h5_tk=%s | "
                        "扩展侧诊断: h5api请求=%s(带密钥%s), offerlist请求=%s(带密钥%s)",
                        secret[:16] or "(空)", len(COOKIE.split("; ")),
                        "_m_h5_tk=" in COOKIE,
                        diag.get("h5apiSeen", 0), diag.get("h5apiWithSecret", 0),
                        diag.get("offerlistSeen", 0), diag.get("offerlistWithSecret", 0))
            for s in (diag.get("offerlistSamples") or [])[-3:]:
                logger.info("  offerlist样例: 带密钥=%s 头名=%s URL=%s",
                            s.get("hasSecret"), s.get("headerNames"), s.get("url"))
            for line in (diag.get("cdpLog") or [])[-14:]:
                logger.info("  [CDP] %s", line.get("line"))
            SESSION_CHANGED.set()
            self.send_response(200)
            self.end_headers()
            return

        if self.path == "/offerlist":
            # 扩展直接转发接口数据
            with EXT_Q_LOCK:
                EXT_QUEUE.append(body)
            self.send_response(200)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def serve_http() -> None:
    try:
        HTTPServer(("127.0.0.1", HTTP_PORT), HttpHandler).serve_forever()
    except OSError as e:
        logger.warning("HTTP 接收端启动失败: %s", e)


BASELINE = {}


def main() -> None:
    setup_logging()
    init_xlsx()
    global BASELINE
    BASELINE = load_baseline()

    logger.info("=" * 60)
    logger.info("1688 旺铺商品巡检程序启动")
    logger.info("巡检间隔: %d 秒 | xlsx: %s | 日志: %s", POLL_SECONDS, XLSX_PATH, LOG_PATH)
    logger.info("扩展数据接收端: http://127.0.0.1:%d/offerlist (POST)", HTTP_PORT)
    logger.info("基线快照: %d 个商品(来自上次运行)", len(BASELINE))
    logger.info("=" * 60)

    threading.Thread(target=serve_http, daemon=True).start()

    while True:
        # 优先处理扩展转发的数据
        with EXT_Q_LOCK:
            payload = EXT_QUEUE.pop(0) if EXT_QUEUE else None
        if payload is not None:
            try:
                offers = payload.get("simpleOfferModelList") or payload.get("offers") or []
                if offers:
                    BASELINE = process_offers(offers, via="扩展转发")
                    logger.info("已处理扩展转发数据")
                else:
                    logger.warning("扩展转发的数据为空")
            except Exception as e:
                logger.error("处理扩展转发数据异常: %s", repr(e))
        else:
            ok, offers, total, ret, error = fetch_all()
            if ok:
                BASELINE = process_offers(offers, via="直连")
            else:
                process_failure(ret, error, via="直连")

        # 等待下一个巡检周期; 扩展推送新会话时会被立即唤醒
        SESSION_CHANGED.wait(POLL_SECONDS)
        SESSION_CHANGED.clear()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("收到退出信号, 程序结束")
