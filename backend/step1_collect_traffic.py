# -*- coding: utf-8 -*-
"""
CrossMart Ops — STEP 1: 采集竞品运营数据（卖家精灵 查流量来源 / 广告洞察）
================================================================================
基于实地探查的真实页面结构：
  - 查流量来源 /v3/reversing/sources?asin=XXX
      表头：全部流量词 / 自然搜索词 / AC推荐词 / ER推荐词 / 4星推荐词 / HR推荐词
            / SP广告词 / 视频广告词 / 品牌广告词
  - 广告洞察 /v3/ads-insights （填ASIN→查询，拿广告位/SP-SB分布）

⛔ 铁律：浏览器只用 Edge 唯一默认账户（端口 9225，不指定 profile）。
⚠️ 卖家精灵需已登录（默认账户带登录态缓存）。
"""
import sys, os, re, json, time, argparse
from datetime import datetime

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)
sys.stdout.reconfigure(encoding='utf-8')

from browser.cdp_bridge import CDPBrowser

OUTPUT_DIR = os.path.join(_THIS, 'data', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

SPRITE_BASE = "https://www.sellersprite.com"


def _safe(s):
    return re.sub(r'[^a-zA-Z0-9]+', '_', str(s)).strip('_')[:50]


def _num(s):
    """'1,401' -> 1401，无法解析返回 0（容错纯逗号/空串）"""
    if s is None:
        return 0
    digits = re.sub(r'[^\d]', '', str(s))
    return int(digits) if digits else 0


def collect_reversing(br, asin, timeout=15):
    """查流量来源：输入ASIN→查询→解析流量来源拆解。

    返回 dict：total_kw / natural_kw / ac_kw / er_kw / star4_kw / hr_kw
              / sp_ad_kw / video_ad_kw / brand_ad_kw / product_title
    """
    print(f"  [reversing] 查流量来源: {asin}")
    br.navigate(f"{SPRITE_BASE}/v3/reversing", wait_min=3, wait_max=5)
    time.sleep(3)
    # 填 ASIN
    js_input = '''(() => {
        const inputs=[...document.querySelectorAll('input[type=text]')];
        let t=inputs.find(i=>(i.placeholder||'').includes('ASIN'));
        if(!t) return 'no-input';
        t.focus(); t.value=%s;
        t.dispatchEvent(new Event('input',{bubbles:true}));
        t.dispatchEvent(new Event('change',{bubbles:true}));
        return 'ok';
    })()''' % json.dumps(asin)
    r1 = br.eval(js_input)
    if r1 != 'ok':
        print(f"    [warn] 未找到ASIN输入框: {r1}")
        return {'_error': 'no_input'}
    time.sleep(1)
    # 点立即查询
    br.eval('''(() => {
        const b=[...document.querySelectorAll('button,.el-button')].find(x=>(x.innerText||'').includes('立即查询'));
        if(b){b.click();return 'clicked';} return 'no-btn';
    })()''')
    # 等结果（url 会跳到 /sources）
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = br.eval("location.href") or ""
        if '/sources' in url:
            break
        time.sleep(1)
    time.sleep(4)

    # 解析结果行（流量来源拆解在首行）
    # ⚠️ Element UI 固定列会渲染成独立子表，必须用 header-wrapper / body-wrapper 精确定位主表，
    #    表头 th 与数据行 td 按 index 一一对齐。
    js_data = r'''(() => {
        const out={ths:[],first_row:[],title:''};
        out.ths=[...document.querySelectorAll('.el-table__header-wrapper thead th')]
                 .map(t=>(t.innerText||'').trim());
        const row=document.querySelector('.el-table__body-wrapper tbody tr');
        if(row){
            out.first_row=[...row.querySelectorAll('td')]
                .map(c=>(c.innerText||'').trim().replace(/\n+/g,' '));
        }
        // 产品标题在首行某一格（含较长英文文本）
        out.first_row.forEach(c=>{ if(!out.title && c.length>20 && /[A-Za-z]/.test(c)) out.title=c.slice(0,120); });
        return JSON.stringify(out);
    })()'''
    raw = br.eval(js_data) or '{}'
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    ths = parsed.get('ths', [])
    row = parsed.get('first_row', [])
    # 按表头映射数字列（header th 与 body td 按 index 对齐）
    label_map = {
        '全部流量词': 'total_kw', '自然搜索词': 'natural_kw', 'AC推荐词': 'ac_kw',
        'ER推荐词': 'er_kw', '4星推荐词': 'star4_kw', 'HR推荐词': 'hr_kw',
        'SP广告词': 'sp_ad_kw', '视频广告词': 'video_ad_kw', '品牌广告词': 'brand_ad_kw',
    }
    data = {'asin': asin, 'product_title': parsed.get('title', '')}
    for i, th in enumerate(ths):
        if i >= len(row):
            continue
        for lbl, key in label_map.items():
            # 精确匹配表头（去空格），命中即取同 index 的数据格
            if lbl == th.replace(' ', '') or lbl in th:
                data[key] = _num(row[i])
    print(f"    全部流量词={data.get('total_kw','?')} 自然={data.get('natural_kw','?')} "
          f"SP广告={data.get('sp_ad_kw','?')} 视频广告={data.get('video_ad_kw','?')} 品牌={data.get('brand_ad_kw','?')}")
    return data


def collect_ads(br, asin, timeout=15):
    """广告洞察：输入ASIN→查询→抓广告位/分布概要文本。"""
    print(f"  [ads] 广告洞察: {asin}")
    br.navigate(f"{SPRITE_BASE}/v3/ads-insights", wait_min=3, wait_max=5)
    time.sleep(3)
    js_input = '''(() => {
        const inputs=[...document.querySelectorAll('input[type=text]')];
        let t=inputs.find(i=>(i.placeholder||'').includes('ASIN')||(i.placeholder||'').includes('产品链接'));
        if(!t) return 'no-input';
        t.focus(); t.value=%s;
        t.dispatchEvent(new Event('input',{bubbles:true}));
        t.dispatchEvent(new Event('change',{bubbles:true}));
        return 'ok';
    })()''' % json.dumps(asin)
    if br.eval(js_input) != 'ok':
        return {'_error': 'no_input'}
    time.sleep(1)
    br.eval('''(() => {
        const b=[...document.querySelectorAll('button,.el-button')].find(x=>(x.innerText||'').includes('立即查询'));
        if(b){b.click();return 1;} return 0;
    })()''')
    time.sleep(8)
    js_data = r'''(() => {
        const out={ths:[],rows:[],kpis:[]};
        document.querySelectorAll('th').forEach(t=>{const x=(t.innerText||'').trim();if(x)out.ths.push(x);});
        out.ths=[...new Set(out.ths)].slice(0,30);
        [...document.querySelectorAll('.el-table__row, tbody tr')].slice(0,5).forEach(r=>{
            out.rows.push([...r.querySelectorAll('td')].map(c=>(c.innerText||'').trim().replace(/\n+/g,' ').slice(0,40)));
        });
        document.querySelectorAll('[class*=count], [class*=number], [class*=stat], [class*=kpi]').forEach(s=>{
            const x=(s.innerText||'').trim(); if(x&&x.length<40) out.kpis.push(x);
        });
        out.kpis=[...new Set(out.kpis)].slice(0,20);
        return JSON.stringify(out);
    })()'''
    raw = br.eval(js_data) or '{}'
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    parsed['asin'] = asin
    print(f"    广告表头 {len(parsed.get('ths',[]))} 列, 数据行 {len(parsed.get('rows',[]))}")
    return parsed


def run_step1(asins, with_ads=True):
    print('=' * 60)
    print(f' OPS STEP 1 — 采集竞品运营数据：{len(asins)} 个 ASIN')
    print('=' * 60)
    br = CDPBrowser(auto_start=False)
    results = {}
    for idx, asin in enumerate(asins):
        print(f"\n--- [{idx+1}/{len(asins)}] {asin} ---")
        entry = {'asin': asin, 'timestamp': datetime.now().isoformat()}
        try:
            entry['reversing'] = collect_reversing(br, asin)
        except Exception as e:
            entry['reversing'] = {'_error': str(e)[:150]}
            print(f"    [err] reversing: {str(e)[:120]}")
        if with_ads:
            try:
                entry['ads'] = collect_ads(br, asin)
            except Exception as e:
                entry['ads'] = {'_error': str(e)[:150]}
                print(f"    [err] ads: {str(e)[:120]}")
        results[asin] = entry
        time.sleep(3)
    out_path = os.path.join(OUTPUT_DIR, 'ops-raw.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ 采集完成 → {out_path}")
    return results


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('asins', nargs='+', help='ASIN 列表')
    ap.add_argument('--no-ads', action='store_true', help='跳过广告洞察（更快）')
    args = ap.parse_args()
    run_step1(args.asins, with_ads=not args.no_ads)
