# -*- coding: utf-8 -*-
"""
1688 旺铺店铺商品列表接口调用脚本
==================================
api : mtop.1688.pc.plugin.shop.offerList.query (v1.1)
作用: 按页获取指定店铺(memberId)的商品列表
结果: 写入本脚本同目录下的 bbb.txt

运行方式(统一用 venv):
    .venv/Scripts/python.exe fetch_offer_list.py
    (依赖安装: .venv/Scripts/python.exe -m pip install requests)

参数恒久性分析
--------------
【恒久不变】
- appKey=12574478               : air.1688.com(旺铺) 固定的 app key
- jsv=2.7.2 / dataType=json / type=originaljson / v=1.1
                                : MTOP 网关固定参数, 与业务无关
- api=mtop.1688.pc.plugin.shop.offerList.query : 接口名(URL 路径里是小写 offerlist)
- memberId=b2b-319033927380e11  : 店铺ID(换店铺才变)
- sortType / pageSize           : 业务参数, 可长期不变
- x-1688extension-secret 请求头  : 浏览器插件固定密钥(重装插件才变)
- Cookie 中账号级长期字段        : cna / unb / uc4 / cookie1 / cookie2 / lid /
                                  __last_loginid__ / __last_memberid__ 等

【每次请求都变】
- t    : 当前毫秒时间戳
- sign : md5(token + "&" + t + "&" + appKey + "&" + data), 每次随 t 重算

【时不时变化(过期后需从浏览器重新复制)】
- _m_h5_tk : 签名 token, 几小时~一天过期(值末尾 _1788796205866 即过期毫秒时间戳)
- tfstk / isg / sgcookie / sg / sgs / _csrf_token / _tb_token_
             : 安全风控 cookie, 定期轮换
- trackId / union / taklid / keywordsHistory 等行为类 cookie
             : 经常变, 但不影响接口返回

Cookie 失效时的更新方法:
    浏览器登录 https://air.1688.com 打开旺铺, F12 -> Network 找到本接口请求,
    把新的 Cookie(重点 _m_h5_tk / tfstk / isg)整段替换下方 COOKIE 变量即可。
"""

import hashlib
import json
import os
import time

import requests

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

# ---------------- 会话参数: 会过期, 从浏览器复制 ----------------
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
                    'DuPJcbqklV8mfWZCjON6Ifpl4qu/m3iQK2a/NkG0IW2nmhkYk/xCnSjLtrBFZ+JynVlSyHnz5y8D+RZIlL5MpfW5U'
                    '+SxapLtNFXJ+QcFQ/DNOZ7mK72aRYj5QrepnvWnW3CTQviwaYVbGdCHVaSPaS1P4frpiOypBH4s4qK1y6NgkgXn8'
                    'Bp0oC2gHRiXv9/pvCE')

HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "origin": "https://air.1688.com",
    "referer": "https://air.1688.com/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"),
    "cookie": COOKIE,
    "x-1688extension-secret": EXTENSION_SECRET,
    # 只声明 gzip/deflate: requests 原生支持, 避免服务器返回 zstd 时缺少 zstandard 库
    "accept-encoding": "gzip, deflate",
}

OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bbb.txt")


def build_sign(token: str, t: int, app_key: str, data: str) -> str:
    """MTOP h5 签名: md5(token & t & appKey & data)"""
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode("utf-8")).hexdigest()


def get_cookie_dict() -> dict:
    """把 COOKIE 字符串解析成字典(值里含 '=' 的用 maxsplit=1 处理)"""
    return dict(item.split("=", 1) for item in COOKIE.split("; ") if "=" in item)


def main() -> None:
    # Windows 控制台默认 GBK, 统一按 UTF-8 输出避免乱码
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # data 必须用紧凑 JSON(无空格), 签名基于它计算
    data_str = json.dumps(BIZ_DATA, separators=(",", ":"), ensure_ascii=False)
    t = int(time.time() * 1000)

    token = get_cookie_dict()["_m_h5_tk"].split("_", 1)[0]
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

    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    except requests.exceptions.ContentDecodingError:
        # 服务器强推 zstd 压缩且未装 zstandard 库时, 退回 identity 再手动解压
        raw = requests.get(BASE_URL, params=params,
                           headers={**HEADERS, "accept-encoding": "identity"}, timeout=30)
        try:
            import zstandard
            body_bytes = zstandard.ZstdDecompressor().decompress(raw.content)
        except ImportError:
            raise SystemExit(
                "响应为 zstd 压缩且缺少 zstandard 库, 请执行: "
                ".venv/Scripts/python.exe -m pip install zstandard")
        body = json.loads(body_bytes)
    else:
        resp.raise_for_status()
        body = resp.json()

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(body, ensure_ascii=False, indent=2))

    ret = body.get("ret", [])
    data = body.get("data") or {}
    print("ret        :", ret)
    print("offerCount :", data.get("offerCount"))
    print("本页条数    :", len(data.get("simpleOfferModelList") or []))
    print("已写入      :", OUT_FILE)
    if ret != ["SUCCESS::调用成功"]:
        print("提示: 返回非成功状态, 大概率是 _m_h5_tk / tfstk / isg 过期, "
              "请按脚本头注释更新 COOKIE 后重试")


if __name__ == "__main__":
    main()
