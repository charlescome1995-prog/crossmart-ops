# -*- coding: utf-8 -*-
"""
CrossMart Ops — 入口
================================================================================
用法：
  python backend/run_ops.py "batana oil"          # 跑某关键词的竞品运营监测
  python backend/run_ops.py "batana oil" --no-ads # 跳过广告洞察（更快）
  python backend/run_ops.py "batana oil" --no-ai  # 跳过AI诊断
  python backend/run_ops.py --all                 # 跑配置里所有关键词

配置来源：backend/data/user_config.json（与 crossmart-monitor 共用结构）
  keywords[].related = 竞品 ASIN（卖家精灵竞品运营）
  asins[].main       = 自家 ASIN（积加真实运营数据）

⛔ 铁律：Edge 唯一默认账户（端口 9225），卖家精灵需已登录。
"""
import sys, os, json, argparse
from datetime import datetime, timedelta

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(_THIS, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'user_config.json')

import step1_collect_traffic as step1
import step2_analyze_ops as step2


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {'asins': [], 'keywords': []}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_own_asins(config):
    return [a.get('main') for a in config.get('asins', []) if a.get('main')]


def get_competitors_for_keyword(config, keyword):
    kw_l = keyword.strip().lower()
    for kw in config.get('keywords', []):
        if (kw.get('main', '').strip().lower()) == kw_l:
            return kw.get('related', [])
    return []


def fetch_jike(own_asins):
    """拉自家 ASIN 的积加真实运营数据，失败则返回空。"""
    if not own_asins:
        return {}
    try:
        from jike_client import get_jike_data_for_asins
        end = datetime.now().date()
        begin = end - timedelta(days=7)
        return get_jike_data_for_asins(own_asins,
                                       begin_date=begin.isoformat(),
                                       end_date=end.isoformat()) or {}
    except Exception as e:
        print(f"  [warn] 积加数据获取失败: {str(e)[:120]}")
        return {}


def run_keyword(config, keyword, with_ads=True, with_ai=True):
    print('\n' + '#' * 60)
    print(f'# CrossMart Ops — 关键词: {keyword}')
    print('#' * 60)
    competitors = get_competitors_for_keyword(config, keyword)
    own = get_own_asins(config)
    if not competitors:
        print(f"  [warn] 配置里关键词 '{keyword}' 无竞品 ASIN，跳过")
        return None
    print(f"  竞品 ASIN: {competitors}")
    print(f"  自家 ASIN: {own}")

    # STEP 1: 抓竞品运营数据
    step1.run_step1(competitors, with_ads=with_ads)
    # 自家真实数据
    jike_data = fetch_jike(own)
    # STEP 2: 合成 + AI 诊断
    return step2.run_step2(keyword, jike_data=jike_data, with_ai=with_ai)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('keyword', nargs='?', help='关键词')
    ap.add_argument('--all', action='store_true', help='跑配置里所有关键词')
    ap.add_argument('--no-ads', action='store_true')
    ap.add_argument('--no-ai', action='store_true')
    args = ap.parse_args()

    config = load_config()
    if args.all:
        for kw in config.get('keywords', []):
            run_keyword(config, kw.get('main'), with_ads=not args.no_ads, with_ai=not args.no_ai)
    elif args.keyword:
        run_keyword(config, args.keyword, with_ads=not args.no_ads, with_ai=not args.no_ai)
    else:
        print("用法: python backend/run_ops.py \"关键词\"  或  --all")
