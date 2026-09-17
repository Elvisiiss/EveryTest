# -*- coding: utf-8 -*-
"""
1688 旺铺店铺商品列表接口 —— 浏览器长期方案
============================================
背景:
  静态复制的 Cookie 里, _m_h5_tk / tfstk / isg 等风控 cookie 由浏览器 JS
  定期刷新(几分钟~几小时), 过期后接口返回 1001::系统开小差了。
  air.1688.com 已 404, 页面环境改用 www.1688.com。
  本方案用 Playwright 驱动本机 Edge(独立持久化用户目录, 登录态只登一次),
  每次运行时先打开 www.1688.com 让页面生成新鲜 cookie 和签名 token,
  再按最接近真实浏览器的顺序发请求, 结果写入 bbb.txt。

请求方式(按真实度排序, 自动降级):
  1. 页面内 fetch       —— 与站点自身调用完全一致(推荐路径)
  2. context.request    —— 浏览器网络栈(带/不带插件密钥)
  若首轮全部 1001/1006, 等 60 秒自动重试一轮; 失败时不覆盖 bbb.txt。

首次使用:
  1. .venv/Scripts/python.exe -m pip install playwright
     (浏览器直接用系统已装的 Edge; 若机器无 Edge, 改 channel="chromium"
      并执行 .venv/Scripts/python.exe -m playwright install chromium)
  2. 运行脚本会弹出浏览器窗口, 扫码登录一次(登录态保存在 ./.browser_profile)
  3. 之后每次运行直接复用登录态

运行:
  .venv/Scripts/python.exe fetch_offer_list_browser.py            # 有头(推荐, 稳)
  .venv/Scripts/python.exe fetch_offer_list_browser.py --headless # 无头(已有登录态时可试)
"""

import argparse
import hashlib
import json
import os
import sys
import time
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

# Windows 控制台默认 GBK, 统一按 UTF-8 输出避免乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 恒久参数 ----------------
APP_KEY = "12574478"
API = "mtop.1688.pc.plugin.shop.offerList.query"
V = "1.1"
JSV = "2.7.2"
BASE_URL = "https://h5api.m.1688.com/h5/mtop.1688.pc.plugin.shop.offerlist.query/1.1/"

# 业务参数(换店铺/翻页时改这里)
BIZ_DATA = {
    "memberId": "b2b-319033927380e11",
    "sortType": "wangpu_score",
    "pageNum": 1,
    "pageSize": 300,
}

# 插件密钥(动态轮换: 失效时从真实浏览器的插件请求头里取新值替换)
EXTENSION_SECRET = ('tMrw7DZ7MZzkt0fGiWrinjC0W8MI3SSHnZL4lGZjc0Sbo+IJlD6Wb/RAlePuMMBfIGe/aJ5D2vuRaX+ukJW+UeVsm'
                    'DuPJcbqklV8mfWZCjON6Ifpl4qu/m3iQK2a/NkWxIKhuHhhYWX1CnSjLtrBFZ+JynVlSyHnz5y8D+RZIlL5MpfW5U'
                    '+SxapLtNFXJ+QcFQ/DNOZ7mK72aRYj5QrepnvWnW3CTQv63o4afXxlMwjPJprZDvCPx12jvDSY6amr4TacgkARme1'
                    'H1b75lnhdcL0spvCE')

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0")

# air.1688.com 已 404, 页面环境改用 www.1688.com(店铺商品详情页作为触发 MTOP 的备选)
HOME_URL = "https://www.1688.com/"
ORIGIN = "https://www.1688.com"
DETAIL_URL = "https://detail.1688.com/offer/951308633342.html"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(BASE_DIR, ".browser_profile")
OUT_FILE = os.path.join(BASE_DIR, "bbb.txt")

LOGIN_TIMEOUT_S = 600   # 首次登录最多等 10 分钟
TOKEN_TIMEOUT_S = 60    # 等 _m_h5_tk 生成最多 60 秒
RETRY_GAP_S = 60        # 全部 1001/1006 时的重试间隔


def build_sign(token: str, t: int, app_key: str, data: str) -> str:
    """MTOP h5 签名: md5(token & t & appKey & data)"""
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode("utf-8")).hexdigest()


def context_cookies(context) -> dict:
    """取 www.1688.com 域名链上的全部 cookie 转成 {name: value}"""
    return {c["name"]: c["value"] for c in context.cookies(HOME_URL)}


def is_logged_in(context) -> bool:
    return context_cookies(context).get("__cn_logon__") == "true"


def get_m_h5_token(context):
    """取 _m_h5_tk 的 token 部分(下划线前), 没有则返回 None"""
    tk = context_cookies(context).get("_m_h5_tk", "")
    return tk.split("_", 1)[0] if tk else None


def build_url(token: str) -> str:
    """按当前时间与签名组装完整请求 URL"""
    data_str = json.dumps(BIZ_DATA, separators=(",", ":"), ensure_ascii=False)
    t = int(time.time() * 1000)
    sign = build_sign(token, t, APP_KEY, data_str)
    params = {
        "jsv": JSV,
        "appKey": APP_KEY,
        "t": t,
        "sign": sign,
        "dataType": "json",
        "api": API,
        "v": V,
        "type": "originaljson",
        "data": data_str,
    }
    return f"{BASE_URL}?{urlencode(params)}"


def try_variants(page, context, url):
    """依次尝试两种方式, 返回 (body, 成功, 来源说明)"""
    # 1) 页面内 fetch: 与站点自身调用完全一致(带 30 秒超时)
    try:
        result = page.evaluate(
            """
            async (url) => {
                const ctrl = new AbortController();
                const timer = setTimeout(() => ctrl.abort(), 30000);
                try {
                    const r = await fetch(url, { credentials: "include", signal: ctrl.signal });
                    const text = await r.text();
                    return { status: r.status, body: text };
                } finally { clearTimeout(timer); }
            }
            """,
            url,
        )
        body = json.loads(result["body"])
        if body.get("ret") == ["SUCCESS::调用成功"]:
            return body, True, "页面内 fetch"
        print("  页面内 fetch 返回:", body.get("ret"))
    except Exception as e:
        print("  页面内 fetch 异常:", repr(e))

    # 2) 浏览器网络栈 + 插件密钥
    try:
        r = context.request.get(url, headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "origin": ORIGIN,
            "referer": HOME_URL,
            "x-1688extension-secret": EXTENSION_SECRET,
        })
        body = r.json()
        if body.get("ret") == ["SUCCESS::调用成功"]:
            return body, True, "context.request(带插件密钥)"
        print("  context.request(带密钥) 返回:", body.get("ret"))
    except Exception as e:
        print("  context.request(带密钥) 异常:", repr(e))

    # 3) 浏览器网络栈, 不带插件密钥
    try:
        r = context.request.get(url, headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "origin": ORIGIN,
            "referer": HOME_URL,
        })
        body = r.json()
        if body.get("ret") == ["SUCCESS::调用成功"]:
            return body, True, "context.request(无密钥)"
        print("  context.request(无密钥) 返回:", body.get("ret"))
    except Exception as e:
        print("  context.request(无密钥) 异常:", repr(e))

    return None, False, ""


def main() -> None:
    parser = argparse.ArgumentParser(description="浏览器方案: 实时 cookie 调用旺铺商品列表接口")
    parser.add_argument("--headless", action="store_true", help="无头模式(需要已有登录态)")
    args = parser.parse_args()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="msedge",
            headless=args.headless,
            viewport={"width": 1280, "height": 800},
            user_agent=USER_AGENT,
        )
        page = context.pages[0] if context.pages else context.new_page()

        print(f"打开 {HOME_URL} ...")
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)

        # ---------- 未登录: 等待人工登录 ----------
        if not is_logged_in(context):
            print("\n>>> 已弹出浏览器窗口, 请扫码/账号登录 1688。")
            print(f">>> 脚本最多等待 {LOGIN_TIMEOUT_S} 秒, 登录完成后自动继续 ...")
            deadline = time.time() + LOGIN_TIMEOUT_S
            while time.time() < deadline:
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    raise SystemExit("浏览器窗口被关闭, 脚本退出")
                if is_logged_in(context):
                    break
            else:
                raise SystemExit("等待登录超时, 请重新运行脚本")
            print("检测到登录态 ✓, 回到首页等待风控 cookie 生成 ...")
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)

        # ---------- 等 _m_h5_tk 出现(首页未生成时, 去商品详情页触发 MTOP) ----------
        token = get_m_h5_token(context)
        candidates = [HOME_URL, DETAIL_URL]
        deadline = time.time() + TOKEN_TIMEOUT_S
        while not token and time.time() < deadline:
            page.wait_for_timeout(3000)
            for target in candidates:
                if token:
                    break
                try:
                    print(f"  _m_h5_tk 未就绪, 打开 {target} 触发 MTOP ...")
                    page.goto(target, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print("  打开页面异常:", repr(e))
                token = get_m_h5_token(context)
        if not token:
            raise SystemExit(f"{TOKEN_TIMEOUT_S} 秒内未获取到 _m_h5_tk, 请确认登录态有效后重试")
        print(f"获取到签名 token: {token[:8]}...")

        # ---------- 组装 URL 并按真实度降级尝试 ----------
        url = build_url(token)

        print("发送请求 ...")
        body, ok, via = try_variants(page, context, url)
        if not ok:
            print(f"首轮未成功, {RETRY_GAP_S} 秒后重试一轮 ...")
            page.wait_for_timeout(RETRY_GAP_S * 1000)
            body, ok, via = try_variants(page, context, url)

        if ok:
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(body, ensure_ascii=False, indent=2))
            data = body.get("data") or {}
            print(f"\n成功方式    : {via}")
            print("ret        :", body.get("ret"))
            print("offerCount :", data.get("offerCount"))
            print("本页条数    :", len(data.get("simpleOfferModelList") or []))
            print("已写入      :", OUT_FILE)
        else:
            print("\n所有方式均未成功(1001/1006 多为风控)。建议: 隔 10~15 分钟再运行; "
                  "或确认浏览器窗口里已正常登录且能打开 1688 页面。bbb.txt 未被覆盖。")

        page.wait_for_timeout(3000)
        context.close()


if __name__ == "__main__":
    main()
