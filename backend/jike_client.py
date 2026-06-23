"""
积加 ERP API 客户端
API 文档: https://open.gerpgo.com/api/open

限流规则：每 5 秒 1 次请求
白名单 IP：121.35.1.52（本地网络）
"""

import json
import time
import requests
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "data" / "jike_config.json"
TOKEN_CACHE_PATH = Path(__file__).parent / "data" / "jike_token_cache.json"

BASE_URL = "https://open.gerpgo.com/api/open"


# ─────────────────────────── 凭证 & Token ───────────────────────────

def load_config():
    """加载积加凭证配置"""
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_token_cache(token, expires_at):
    """缓存 access_token"""
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"token": token, "expires_at": expires_at}, f)


def load_token_cache():
    """读取缓存的 access_token"""
    if not TOKEN_CACHE_PATH.exists():
        return None
    try:
        with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() < data.get("expires_at", 0) - 300:
            return data.get("token")
    except Exception:
        pass
    return None


def invalidate_token_cache():
    """主动清除 token 缓存（401 时调用，强制重新获取）"""
    try:
        TOKEN_CACHE_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def get_access_token(app_id: str, app_key: str) -> str:
    """获取 access_token，先查缓存，无效则重新请求"""
    cached = load_token_cache()
    if cached:
        return cached

    url = f"{BASE_URL}/api_token"
    payload = {
        "appId": app_id,
        "appKey": app_key,
    }
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    result = resp.json()

    # 检查业务错误码
    if result.get('code') == 40302:
        # IP 无访问权限，抛出明确异常供调用方识别
        raise PermissionError(f"积加API IP无访问权限: {result.get('messages', '')}")
    if result.get('code') != 200:
        raise Exception(f"获取 access_token 失败: code={result.get('code')}, msg={result.get('messages', '')}")
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = result.get("data", {})
    token = data.get("accessToken")
    expires_in = data.get("expiresIn", 3600)

    save_token_cache(token, time.time() + expires_in)
    return token


# ─────────────────────────── 销售表现 API ───────────────────────────

def fetch_sales_by_asin(token: str, asin: str,
                        begin_date: str = None,
                        end_date: str = None) -> dict:
    """
    查询单个 ASIN 的销售表现数据。

    请求体（来自积加 OpenAPI 文档）：
    {
        "beginDate": "2026-06-02",
        "endDate": "2026-06-09",
        "groupByType": "asin",
        "pageSize": 20,
        "asin": "B0FVSS8SR1",
        "showCurrencyType": "USD",
        "page": 1
    }

    注意：限流每 5 秒 1 次，调用方需控制频率。
    """
    import datetime

    today = datetime.date.today()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")
    if not begin_date:
        begin_date = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    url = f"{BASE_URL}/operation/sts/salesAnalysis/page"
    headers = {
        "Content-Type": "application/json",
        "accessToken": token
    }
    payload = {
        "beginDate": begin_date,
        "endDate": end_date,
        "groupByType": "asin",
        "pagesize": 20,
        "asin": asin,
        "showCurrencyType": "USD",
        "page": 1
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    result = resp.json()

    # 检查业务错误码
    code = result.get('code')
    if code == 40302:
        raise PermissionError(f"积加API IP无访问权限: {result.get('messages', '')}")
    if code == 401 or code == 40005:
        raise PermissionError(f"积加API Token无效/过期: {result.get('messages', '')}")
    if code == 509:
        raise RuntimeError(f"积加API 限流(509): {result.get('messages', '')}")
    if code != 200:
        raise RuntimeError(f"积加API 错误: code={code}, msg={result.get('messages', '')}")

    data_obj = result.get("data")
    if data_obj is None:
        return result, []
    rows = data_obj.get("rows") if isinstance(data_obj, dict) else []
    if rows is None:
        rows = []
    return result, rows


# ─────────────────────────── 主入口 ───────────────────────────

def get_jike_data_for_asins(asin_list: list,
                             begin_date: str = None,
                             end_date: str = None) -> dict:
    """
    对外主入口：给定 ASIN 列表，返回积加数据字典。

    限流：每 5 秒发一次请求，自动 sleep 控制频率。

    返回格式:
        {
            "ASIN": {
                "orderProductSales": float,   # 销售额（USD）
                "unitsOrdered": int,           # 销量
                "orders": int,                 # 订单量
                "sessions": int,              # Sessions
                "pageViews": int,              # 页面浏览量
                "cvr": float,                  # 转化率（%）
                "mainSellerRank": int,        # 大类排名
                "sellerRank": int,             # 小类排名
                "star": float,                 # 评分
                "reviewQuantity": int,         # 评论数
                "listingState": str,           # 商品运营状态
                "productName": str,             # 产品名称
                "marketName": str,              # 站点名称
                "_raw": dict                   # 原始数据
            }
        }

    Args:
        asin_list: ASIN 列表（单个也会包装成列表）
        begin_date: 开始日期，默认最近7天
        end_date: 结束日期，默认今天

    Returns:
        dict: 每个 ASIN 的积加数据
    """
    config = load_config()
    if not config:
        raise Exception("积加配置未找到，请先配置 APP_ID 和 APP_KEY")

    app_id = config.get("appId")
    app_key = config.get("appKey")
    if not app_id or not app_key:
        raise Exception("积加配置缺少 appId 或 appKey")

    token = get_access_token(app_id, app_key)

    out = {}

    for i, asin in enumerate(asin_list):
        asin = asin.strip()
        if not asin:
            continue

        # 限流：每 5 秒 1 次，最后一次不需要等
        if i > 0:
            print(f"  [积加] 限流等待 5s...")
            time.sleep(5)

        print(f"  [积加] 查询 ASIN: {asin}")

        # 509 时最多重试 3 次，每次等 6 秒
        for retry in range(3):
            result, rows = fetch_sales_by_asin(token, asin, begin_date, end_date)
            code = result.get("code")
            if code == 200:
                break
            if code == 401 or code == 40005:
                invalidate_token_cache()
            if code == 509:
                print(f"  [积加] ASIN {asin} 限流(509)，等待 6s 后重试...")
                time.sleep(6)
                continue
            # 其他错误不重试
            print(f"  [积加] ASIN {asin} 查询失败: code={code}, message={result.get('message','')}")
            rows = []
            break
        else:
            # 3 次重试都失败了
            print(f"  [积加] ASIN {asin} 重试 3 次后仍失败")
            rows = []

        # 同一 ASIN 可能返回多条（父ASIN + 子ASIN），全部收录
        for row in rows:
            a = row.get("asin", "")
            if not a or a == "-":
                continue

            sales_obj = row.get("orderProductSalesAmount") or {}
            if isinstance(sales_obj, dict):
                sales_amount = sales_obj.get("currencyAmount")
            else:
                sales_amount = row.get("orderProductSales")

            out[a] = {
                "orderProductSales": sales_amount,
                "unitsOrdered": row.get("unitsOrdered"),
                "orders": row.get("orders"),
                "sessions": row.get("sessions"),
                "pageViews": row.get("pageViews"),
                "cvr": row.get("cvr"),
                "mainSellerRank": row.get("mainSellerRank"),
                "sellerRank": row.get("sellerRank"),
                "star": row.get("star"),
                "reviewQuantity": row.get("reviewQuantity"),
                "listingState": row.get("listingState"),
                "productName": row.get("productName"),
                "marketName": row.get("marketName"),
                "acos": row.get("acos"),
                "adsSpend": row.get("adsSpend"),
                "fbaQuantity": row.get("fbaQuantity"),
                "fbaTurnover": row.get("fbaTurnover"),
                "salesGrossProfitRate": row.get("salesGrossProfitRate"),
                "_raw": row
            }

    return out


if __name__ == "__main__":
    config = load_config()
    if not config:
        print("未配置 jike_config.json，请先配置 APP_ID 和 APP_KEY")
    else:
        print("已配置 appId:", config.get("appId"))
        try:
            token = get_access_token(config["appId"], config["appKey"])
            print("access_token 获取成功:", token[:20] + "...")

            # 测试查询
            result = get_jike_data_for_asins(["B09VYQRRHF"])
            for asin, data in result.items():
                print(f"\n{asin}:")
                print(f"  销售额={data['orderProductSales']}, 销量={data['unitsOrdered']}, "
                      f"订单={data['orders']}, sessions={data['sessions']}, "
                      f"pageViews={data['pageViews']}, CVR={data['cvr']}, "
                      f"评分={data['star']}, 评论={data['reviewQuantity']}")
        except Exception as e:
            print("access_token 获取失败:", e)