# -*- coding: utf-8 -*-
"""
CrossMart Ops — STEP 2: 合成运营数据 + AI 运营诊断（B 引擎）
================================================================================
输入：
  - ops-raw.json         （step1 卖家精灵竞品流量/广告数据）
  - jike 自家 ASIN 真实运营数据（acos / adsSpend / cvr / sessions）
输出：
  - frontend/data/ops-data-B.json   （前端仪表盘消费）

4 个仪表盘模块：
  1. traffic_radar    流量词雷达（竞品流量词 + 机会词）
  2. ad_competition   广告竞争分析（SP/SB分布 + 自家ACOS对比）
  3. traffic_structure 自然 vs 广告流量结构
  4. ai_diagnosis     AI 运营诊断（LLM 输出策略建议）
"""
import sys, os, json, argparse
from datetime import datetime

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)
sys.stdout.reconfigure(encoding='utf-8')

import llm_client
from llm_config import CHAT_MODEL

OUTPUT_DIR = os.path.join(_THIS, 'data', 'output')
FRONTEND_DATA = os.path.join(_THIS, '..', 'frontend', 'data')
os.makedirs(FRONTEND_DATA, exist_ok=True)


def _pct(part, whole):
    try:
        if whole and whole > 0:
            return round(part / whole * 100, 1)
    except Exception:
        pass
    return 0.0


def build_traffic_structure(reversing):
    """从 reversing 数据拆解自然 / 广告 / 推荐流量占比。"""
    total = reversing.get('total_kw', 0) or 0
    natural = reversing.get('natural_kw', 0) or 0
    # 推荐词 = AC + ER + 4星 + HR
    recommend = sum(reversing.get(k, 0) or 0 for k in ('ac_kw', 'er_kw', 'star4_kw', 'hr_kw'))
    # 广告 = SP + 视频 + 品牌
    ad = sum(reversing.get(k, 0) or 0 for k in ('sp_ad_kw', 'video_ad_kw', 'brand_ad_kw'))
    return {
        'total_kw': total,
        'natural_kw': natural,
        'recommend_kw': recommend,
        'ad_kw': ad,
        'natural_pct': _pct(natural, total),
        'recommend_pct': _pct(recommend, total),
        'ad_pct': _pct(ad, total),
        'sp_ad_kw': reversing.get('sp_ad_kw', 0) or 0,
        'video_ad_kw': reversing.get('video_ad_kw', 0) or 0,
        'brand_ad_kw': reversing.get('brand_ad_kw', 0) or 0,
    }


def ai_diagnose(payload):
    """喂运营数据给 LLM，输出运营诊断。"""
    system = (
        "You are a senior Amazon operations strategist AND a seasoned Amazon CPC advertising expert "
        "for cross-border e-commerce, proficient in Amazon advertising and ranking algorithms. "
        "Analyze competitor traffic structure, advertising mix and the seller's own real metrics. "
        "For ad decisions, reason across CTR, CPC, SPEND, CVR and ACOS dimensions. "
        "Output STRICT JSON only, no markdown fences."
    )
    prompt = f"""Based on the operations data below, produce an operations diagnosis.

DATA (JSON):
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return STRICT JSON with this schema (all text in English, concise & actionable):
{{
  "summary": "2-3 sentence overall operations health read",
  "keyword_opportunities": ["3-5 high-value keywords/angles we likely under-cover"],
  "ad_strategy": ["3-4 concrete advertising optimization moves"],
  "bid_actions": {{
    "add_keywords": ["search terms to ADD to manual targeting (high CVR / on-topic)"],
    "negate_keywords": ["search terms to NEGATE (high SPEND, high ACOS, low CVR)"],
    "raise_bid": ["keywords whose bid should be INCREASED (good CVR, losing impressions)"],
    "lower_bid": ["keywords whose bid should be DECREASED (high ACOS / high CPC, weak CVR)"]
  }},
  "organic_growth": ["3-4 steps to lift organic ranking (the ad->organic ranking path)"],
  "alerts": ["competitor/operational risks worth watching, e.g. a competitor leaning hard on ads"]
}}

Guidance for bid_actions (Amazon CPC best practice):
- ADD: search terms that are relevant and convert well but are not yet in manual targeting.
- NEGATE: terms burning spend with high ACOS and low/zero conversions.
- RAISE bid: converting keywords that are under-exposed (low impression share).
- LOWER bid: keywords with high ACOS or high CPC and weak conversion.
If the data is insufficient for a bucket, return an empty list for it (do not invent ASIN-specific numbers)."""
    try:
        raw = llm_client.chat_openai(prompt, system=system, model=CHAT_MODEL,
                                     max_tokens=2000, temperature=0.4)
        raw = raw.strip()
        if raw.startswith('```'):
            raw = raw.split('```', 2)[1] if '```' in raw else raw
            raw = raw.lstrip('json').strip().rstrip('`').strip()
        # 抓第一个 { 到最后一个 }
        s, e = raw.find('{'), raw.rfind('}')
        if s >= 0 and e > s:
            raw = raw[s:e+1]
        return json.loads(raw)
    except Exception as ex:
        return {'summary': f'(AI diagnosis unavailable: {str(ex)[:120]})',
                'keyword_opportunities': [], 'ad_strategy': [],
                'bid_actions': {'add_keywords': [], 'negate_keywords': [],
                                'raise_bid': [], 'lower_bid': []},
                'organic_growth': [], 'alerts': []}


def run_step2(keyword_label, raw_path=None, jike_data=None, with_ai=True):
    raw_path = raw_path or os.path.join(OUTPUT_DIR, 'ops-raw.json')
    if not os.path.exists(raw_path):
        print(f"  [err] 找不到 {raw_path}，先跑 step1")
        return None
    with open(raw_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    jike_data = jike_data or {}

    competitors = []
    structures = []
    for asin, entry in raw.items():
        rev = entry.get('reversing', {}) or {}
        if rev.get('_error'):
            continue
        struct = build_traffic_structure(rev)
        comp = {
            'asin': asin,
            'product_title': rev.get('product_title', ''),
            'total_kw': struct['total_kw'],
            'natural_kw': struct['natural_kw'],
            'ad_kw': struct['ad_kw'],
            'recommend_kw': struct['recommend_kw'],
            'natural_pct': struct['natural_pct'],
            'ad_pct': struct['ad_pct'],
            'recommend_pct': struct['recommend_pct'],
            'sp_ad_kw': struct['sp_ad_kw'],
            'video_ad_kw': struct['video_ad_kw'],
            'brand_ad_kw': struct['brand_ad_kw'],
            'ads_detail': entry.get('ads', {}),
        }
        competitors.append(comp)
        structures.append({'asin': asin, **struct})

    # 自家真实运营数据（jike）
    own = []
    for asin, jk in jike_data.items():
        if not jk:
            continue
        own.append({
            'asin': asin,
            'product_name': jk.get('productName', ''),
            'orders': jk.get('orders'),
            'units': jk.get('unitsOrdered'),
            'sales': jk.get('orderProductSales'),
            'sessions': jk.get('sessions'),
            'cvr': jk.get('cvr'),
            'acos': jk.get('acos'),
            'ad_spend': jk.get('adsSpend'),
            'rank': jk.get('mainSellerRank'),
        })

    ai = {}
    if with_ai:
        print("  [AI] 运营诊断中...")
        ai = ai_diagnose({'competitors': competitors, 'own_products': own})

    result = {
        'engine': 'B',
        'keyword': keyword_label,
        'generated_at': datetime.now().isoformat(),
        'traffic_radar': competitors,
        'traffic_structure': structures,
        'ad_competition': {
            'competitors': [{'asin': c['asin'], 'sp_ad_kw': c['sp_ad_kw'],
                             'video_ad_kw': c['video_ad_kw'], 'brand_ad_kw': c['brand_ad_kw'],
                             'ad_pct': c['ad_pct'],
                             # 广告洞察真实投放规模
                             'ad_groups': (c.get('ads_detail') or {}).get('ad_groups'),
                             'sp_groups': (c.get('ads_detail') or {}).get('sp_groups'),
                             'sbv_groups': (c.get('ads_detail') or {}).get('sbv_groups'),
                             'ad_campaigns': (c.get('ads_detail') or {}).get('ad_campaigns')}
                            for c in competitors],
            'own': own,
        },
        'ai_diagnosis': ai,
    }
    out = os.path.join(FRONTEND_DATA, 'ops-data-B.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # 同时写 default
    with open(os.path.join(FRONTEND_DATA, 'ops-data.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 合成完成 → {out}（竞品 {len(competitors)} / 自家 {len(own)}）")
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('keyword', help='关键词标签')
    ap.add_argument('--no-ai', action='store_true')
    args = ap.parse_args()
    run_step2(args.keyword, with_ai=not args.no_ai)
