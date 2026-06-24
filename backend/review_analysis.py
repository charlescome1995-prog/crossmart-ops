# -*- coding: utf-8 -*-
"""
CrossMart Ops — 卖家精灵评论分析(VOC)读取模块
================================================
安全说明：
  本模块【不直接抓取亚马逊评论页】（避免真实账户被反爬标记/封IP）。
  评论数据由卖家精灵浏览器插件预先采集生成「评论分析报告」，
  本模块仅连 Edge 9225 读取卖家精灵已生成的报告页面（与抓流量词同机制，零新增风险）。

数据来源：
  - 报告列表：https://www.sellersprite.com/v3/review-analysis
  - 报告详情：https://www.sellersprite.com/v3/review-analysis/details?list=<报告ID>&_sign=<签名>

可提取字段：
  - 报告列表：ASIN / 评分 / 评分数 / 评论数 / 首次留评 / 最近留评 / 状态 / 详情链接
  - 详情页：评论标签词云(en/zh/次数/占比) / 特点评分 / 星级统计

依赖：闫旭需先用卖家精灵插件对目标竞品 ASIN 采集评论生成报告。
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
REVIEW_LIST_URL = f"{SPRITE_BASE}/v3/review-analysis"


def _num(s):
    if s is None:
        return 0
    digits = re.sub(r'[^\d.]', '', str(s))
    try:
        return float(digits) if '.' in digits else int(digits)
    except Exception:
        return 0


def list_reports(br):
    """读评论分析报告列表，返回每条报告的 ASIN / 评分 / 评论数 / 详情链接。"""
    print("  [review] 打开评论分析报告列表...")
    br.navigate(REVIEW_LIST_URL, wait_min=4, wait_max=6)
    time.sleep(3)
    js = r'''(() => {
        var out = [];
        var seen = new Set();
        // 详情链接（每条已完成报告都有 details?list=）
        document.querySelectorAll('a[href*="details?list="]').forEach(function(a){
            var href = a.getAttribute('href') || '';
            if (seen.has(href)) return;
            seen.add(href);
            // 向上找所在行，提取 ASIN / 数值
            var row = a.closest('tr') || a.closest('[class*=row]') || a.parentElement;
            var txt = row ? (row.innerText || '') : '';
            var asinM = txt.match(/B0[A-Z0-9]{8}/);
            out.push({
                detail_href: href,
                asin: asinM ? asinM[0] : '',
                row_text: txt.replace(/\s+/g, ' ').slice(0, 300)
            });
        });
        return JSON.stringify(out);
    })()'''
    try:
        data = json.loads(br.eval(js) or '[]')
    except Exception:
        data = []
    print(f"  [review] 发现 {len(data)} 条报告")
    return data


def parse_report_detail(br, detail_href):
    """进入某份报告详情页，提取评论标签词云 + 特点评分 + 星级统计。"""
    url = detail_href if detail_href.startswith('http') else (SPRITE_BASE + detail_href)
    print(f"  [review] 读取报告详情: {url[:90]}")
    br.navigate(url, wait_min=5, wait_max=7)
    time.sleep(4)

    # 评论标签词云：形如 backpack (背包 | 222 / 6.9%)
    js_tags = r'''(() => {
        var all = document.body.innerText;
        var re = /([a-zA-Z][a-zA-Z0-9'\-\s]+?)\s*\(([^|()]+?)\s*\|\s*(\d+)\s*\/\s*([\d.]+)%\)/g;
        var m, tags = [];
        while ((m = re.exec(all)) !== null && tags.length < 40) {
            var en = m[1].trim();
            // 过滤掉前文混入的长串（取最后一个换行后的纯词）
            if (en.indexOf('\n') >= 0) en = en.split('\n').pop().trim();
            tags.push({en: en, zh: m[2].trim(), count: +m[3], pct: +m[4]});
        }
        return JSON.stringify(tags);
    })()'''

    # 特点评分：形如 轻的 4.9 / 耐用性 4.6（成对出现的 标签+评分）
    js_features = r'''(() => {
        var out = [];
        var nodes = document.querySelectorAll('[class*=feature] *, [class*=character] *');
        var txt = document.body.innerText;
        // 用正则抓「中文/英文标签 + 4.x分」对
        var re = /([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z\s]{1,12})\s*\n?\s*([1-5]\.\d)\b/g;
        var m, seen = new Set();
        while ((m = re.exec(txt)) !== null && out.length < 15) {
            var label = m[1].trim();
            var score = parseFloat(m[2]);
            if (label && score >= 1 && score <= 5 && !seen.has(label) && label.length <= 12) {
                seen.add(label);
                out.push({label: label, score: score});
            }
        }
        return JSON.stringify(out);
    })()'''

    js_meta = r'''(() => {
        var t = document.title || '';
        var asinM = t.match(/B0[A-Z0-9]{8}/) || document.body.innerText.match(/B0[A-Z0-9]{8}/);
        return JSON.stringify({title: t, asin: asinM ? asinM[0] : ''});
    })()'''

    # 评论列表：原文 + 中文翻译 + 点赞 + 时间（词云缺失时仍可喂 AI 分析痛点）
    js_reviews = r'''(() => {
        var txt = document.body.innerText;
        var i = txt.indexOf('评论列表');
        if (i < 0) return '[]';
        var seg = txt.slice(i, i + 6000);
        // 按「点赞: N 评论时间: YYYY-MM-DD」切块
        var blocks = seg.split(/点赞:\s*\d+/);
        var out = [];
        var dateRe = /评论时间:\s*(\d{4}-\d{2}-\d{2})/;
        for (var k = 0; k < blocks.length && out.length < 30; k++) {
            var b = blocks[k].trim();
            if (b.length < 15) continue;
            var dm = b.match(dateRe);
            // 去掉尾部的日期残留
            var body = b.replace(/Size:[^|]*\|?\s*Color:[^\n]*/g, '').trim();
            out.push({text: body.slice(0, 500), date: dm ? dm[1] : ''});
        }
        return JSON.stringify(out);
    })()'''

    try:
        tags = json.loads(br.eval(js_tags) or '[]')
    except Exception:
        tags = []
    try:
        features = json.loads(br.eval(js_features) or '[]')
    except Exception:
        features = []
    try:
        meta = json.loads(br.eval(js_meta) or '{}')
    except Exception:
        meta = {}
    try:
        reviews = json.loads(br.eval(js_reviews) or '[]')
    except Exception:
        reviews = []

    return {
        'asin': meta.get('asin', ''),
        'title': meta.get('title', ''),
        'review_tags': tags,
        'feature_scores': features,
        'reviews': reviews,
        'detail_url': url,
    }


def collect_review_analysis(br, max_reports=10):
    """主流程：列出报告 → 逐个读详情 → 返回结构化评论分析数据。"""
    reports = list_reports(br)
    results = []
    for r in reports[:max_reports]:
        href = r.get('detail_href')
        if not href:
            continue
        try:
            detail = parse_report_detail(br, href)
            if not detail.get('asin'):
                detail['asin'] = r.get('asin', '')
            detail['review_count_hint'] = r.get('row_text', '')
            results.append(detail)
            time.sleep(2)
        except Exception as e:
            print(f"  [review] 报告读取失败: {str(e)[:80]}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max', type=int, default=10, help='最多读取报告数')
    ap.add_argument('--out', default=None, help='输出json路径')
    args = ap.parse_args()

    os.environ.setdefault('CDP_PORT', '9225')
    br = CDPBrowser(auto_start=False)
    br.connect_tab(tab_url_filter='sellersprite') if hasattr(br, 'connect_tab') else None

    data = collect_review_analysis(br, max_reports=args.max)
    out = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'sellersprite_review_analysis',
        'report_count': len(data),
        'reports': data,
    }
    out_path = args.out or os.path.join(OUTPUT_DIR, 'review-analysis-raw.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ 评论分析数据 → {out_path}（{len(data)} 份报告）")
    for d in data:
        print(f"     {d.get('asin','?')}: {len(d.get('review_tags',[]))} 标签 / {len(d.get('feature_scores',[]))} 特点评分 / {len(d.get('reviews',[]))} 条评论")


if __name__ == '__main__':
    main()
