# -*- coding: utf-8 -*-
"""
1688 旺铺商品列表接口 —— 真实 Edge 用户目录方案(终极版)
========================================================
背景(排查结论):
  x-1688extension-secret 由 1688 浏览器插件动态生成, 且与浏览器会话绑定:
    旧密钥 + 任意会话 -> 1001
    新密钥 + 陌生会话 -> 1003
    无密钥           -> 1006
  air.1688.com 已 404。因此唯一可靠做法: 在用户真实 Edge 用户目录(插件所在)
  里运行 —— 插件自行注入当前有效密钥, 会话 cookie 天然匹配。

工作方式:
  1. 等用户完全退出 Edge(用户目录被锁时无法启动)
  2. Playwright 用真实用户目录启动 Edge(插件照常加载, 登录态照旧)
  3. 打开商品详情页(插件工作区), 两种方式取数:
     A) 脚本主动用页面 fetch 调接口 —— 若插件通过 webRequest 注入密钥则直接成功
     B) 用户像平时一样在窗口里打开插件商品列表, 脚本自动监听并捕获该接口响应
  4. 首次拿到 SUCCESS 响应即写入 bbb.txt, 关闭窗口

运行前: 请完全退出 Edge(含托盘/后台进程, 任务管理器确认无 msedge.exe)
运行:   .venv/Scripts/python.exe fetch_offer_list_real.py
运行后: 完成即可重新打开 Edge, 不影响原登录态。

注意: 若 1688 插件装在非默认配置文件里, 改下方 PROFILE_DIR 指向对应目录。
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

# Windows 控制台默认 GBK, 统一按 UTF-8 输出避免乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 配置 ----------------
# 真实 Edge 用户目录(默认配置文件). 插件装在别的配置文件时改这里
PROFILE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data")
PROFILE_ARG = "--profile-directory=Default"

# 插件工作区页面(商品详情页, 抽屉/表格在此打开)
DETAIL_URL = "https://detail.1688.com/offer/951308633342.html"

# 接口恒久参数与业务参数(同前两个脚本)
APP_KEY = "12574478"
API = "mtop.1688.pc.plugin.shop.offerList.query"
BASE_URL = "https://h5api.m.1688.com/h5/mtop.1688.pc.plugin.shop.offerlist.query/1.1/"
BIZ_DATA = {
    "memberId": "b2b-319033927380e11",
    "sortType": "wangpu_score",
    "pageNum": 1,
    "pageSize": 300,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "bbb.txt")

CLOSE_EDGE_TIMEOUT_S = 180   # 等用户退出 Edge 最多 3 分钟
LOGIN_TIMEOUT_S = 600        # 若未登录, 等人工登录最多 10 分钟
CAPTURE_TIMEOUT_S = 300      # 等插件请求/用户操作最多 5 分钟


def build_sign(token: str, t: int, app_key: str, data: str) -> str:
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode("utf-8")).hexdigest()


def edge_process_count() -> int:
    """统计当前 msedge.exe 进程数(含后台)"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        return sum(1 for line in out.splitlines() if line.strip().lower().startswith('"msedge.exe"'))
    except Exception:
        return 0


def wait_edge_closed(force_close: bool) -> None:
    """等用户退出 Edge, 否则用户目录被锁无法启动。

    force_close=True 时: 用户关掉窗口后, 残留的后台 msedge.exe 进程
    (Edge 启动增强/后台运行) 由脚本强制结束, 再启动浏览器。
    """
    deadline = time.time() + CLOSE_EDGE_TIMEOUT_S
    last_msg = 0.0
    while edge_process_count() > 0 and time.time() < deadline:
        if force_close and time.time() - last_msg > 5:
            print(">>> 关闭窗口后仍有残留 Edge 后台进程, 脚本将强制结束它们(不影响登录态) ...")
            try:
                subprocess.run(["taskkill", "/F", "/T", "/IM", "msedge.exe"],
                               capture_output=True, timeout=30)
            except Exception as e:
                print("    结束进程失败:", repr(e))
        elif not force_close and time.time() - last_msg > 15:
            print(">>> 检测到 Edge 仍在运行。请完全退出 Edge(任务栏右键退出; 若一直检测到, "
                  "可加 --force-close 参数让脚本清掉残留后台进程), 脚本会自动继续 ...")
        last_msg = time.time()
        time.sleep(2)
    if edge_process_count() > 0:
        raise SystemExit("Edge 未退出, 用户目录被占用。请退出 Edge 后重新运行(可加 --force-close)。")


def context_cookies(context) -> dict:
    return {c["name"]: c["value"] for c in context.cookies("https://www.1688.com/")}


def is_logged_in(context) -> bool:
    return context_cookies(context).get("__cn_logon__") == "true"


def build_url(context) -> str:
    """用上下文里的 _m_h5_tk 组装带签名的完整请求 URL(密钥由插件注入)"""
    tk = context_cookies(context).get("_m_h5_tk", "")
    token = tk.split("_", 1)[0] if tk else ""
    if not token:
        raise RuntimeError("上下文里没有 _m_h5_tk")
    data_str = json.dumps(BIZ_DATA, separators=(",", ":"), ensure_ascii=False)
    t = int(time.time() * 1000)
    sign = build_sign(token, t, APP_KEY, data_str)
    params = {
        "jsv": "2.7.2", "appKey": APP_KEY, "t": t, "sign": sign,
        "dataType": "json", "api": API, "v": "1.1",
        "type": "originaljson", "data": data_str,
    }
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_via_page(page, url):
    """在详情页上下文里发 fetch(插件若经 webRequest 注入密钥则会成功)"""
    return page.evaluate(
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


def main() -> None:
    parser = argparse.ArgumentParser(description="真实 Edge 用户目录方案")
    parser.add_argument("--force-close", action="store_true",
                        help="关闭 Edge 窗口后, 强制结束残留的后台 msedge.exe 进程再启动")
    args = parser.parse_args()

    if not os.path.isdir(PROFILE_DIR):
        raise SystemExit(f"找不到 Edge 用户目录: {PROFILE_DIR}\n请修改脚本顶部 PROFILE_DIR。")

    print("1/4 检查 Edge 是否已退出 ...")
    wait_edge_closed(args.force_close)
    print("    Edge 已退出 ✓")

    with sync_playwright() as p:
        print("2/4 用真实用户目录启动 Edge(插件随行) ...")
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="msedge",
            headless=False,  # 扩展程序仅在有头模式下加载
            args=[PROFILE_ARG, "--disable-features=msEdgeFirstRunExperience"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()

        # 监听 offerList.query 的响应(插件自己发的, 或我们 fetch 触发的)
        captured_success = []

        def on_response(resp):
            if "offerlist.query" not in resp.url.lower():
                return
            try:
                body = resp.json()
            except Exception:
                return
            print("    监听到接口响应, ret =", body.get("ret"))
            if body.get("ret") == ["SUCCESS::调用成功"]:
                captured_success.append(body)

        page.on("response", on_response)

        print(f"3/4 打开插件工作区页面: {DETAIL_URL}")
        page.goto(DETAIL_URL, wait_until="domcontentloaded", timeout=60000)

        # 未登录则等人工登录
        if not is_logged_in(context):
            print("\n>>> 窗口里未检测到登录态, 请先登录 1688(脚本等待中) ...")
            deadline = time.time() + LOGIN_TIMEOUT_S
            while time.time() < deadline and not is_logged_in(context):
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    raise SystemExit("浏览器窗口被关闭, 脚本退出")
            if not is_logged_in(context):
                raise SystemExit("等待登录超时, 请重试")

        success = None

        # ---------- 方式 A: 脚本主动触发(给插件 content script 一点就绪时间) ----------
        print("4/4 尝试取数 ...")
        page.wait_for_timeout(8000)
        try:
            url = build_url(context)
            print("    脚本主动 fetch ...")
            result = fetch_via_page(page, url)
            body = json.loads(result["body"])
            print("    fetch 返回:", body.get("ret"))
            if body.get("ret") == ["SUCCESS::调用成功"]:
                success = body
        except Exception as e:
            print("    主动 fetch 不可用:", repr(e))

        # ---------- 方式 B: 用户操作插件, 脚本监听捕获 ----------
        if success is None and not captured_success:
            print("\n>>> 自动方式未成功。请在浏览器窗口里像平时一样打开插件的商品列表"
                  "(抽屉/表格), 脚本会自动捕获接口响应 ...")
            deadline = time.time() + CAPTURE_TIMEOUT_S
            while not captured_success and time.time() < deadline:
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    raise SystemExit("浏览器窗口被关闭, 脚本退出")
        if success is None and captured_success:
            success = captured_success[0]

        if success is not None:
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(success, ensure_ascii=False, indent=2))
            data = success.get("data") or {}
            print("\n成功 ✓")
            print("ret        :", success.get("ret"))
            print("offerCount :", data.get("offerCount"))
            print("本页条数    :", len(data.get("simpleOfferModelList") or []))
            print("已写入      :", OUT_FILE)
        else:
            print("\n未捕获到成功响应。请确认: 1) 插件已登录且能正常打开商品列表; "
                  "2) 目标接口确实由插件触发。bbb.txt 未被覆盖。")

        page.wait_for_timeout(3000)
        context.close()
        print("浏览器已关闭, 现在可以重新打开 Edge。")


if __name__ == "__main__":
    main()
