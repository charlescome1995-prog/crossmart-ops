# CrossMart Ops — Operations Monitor

竞品运营监测板块（crossmart 项目第四站），聚焦流量词、广告、自然排名、转化漏斗。

## 4 个仪表盘模块
1. **🛰️ Traffic Radar** — 竞品流量词来源拆解（全部/自然/推荐/广告流量词）
2. **🧬 Traffic Structure** — 自然 vs 推荐 vs 广告 流量结构占比
3. **📢 Ad Competition** — 竞品广告词分布（SP/视频/品牌）+ 自家真实 ACOS/CVR 对比（积加）
4. **🤖 AI Operations Diagnosis** — 火山方舟 LLM 输出抢词建议/广告优化/排名路径/预警

## 数据源
- **卖家精灵**：查流量来源 `/v3/reversing`（流量词结构）+ 广告洞察 `/v3/ads-insights`（真实投放规模：投放小组/SP/SBV/广告活动数，6个月）
- **积加 API**：自家 ASIN 真实 ACOS / 广告花费 / Session / CVR
- **火山方舟 LLM**：运营策略诊断

## 定时抓取
- Windows 任务计划 **CrossMartOps_0600**（每天 06:00）→ `_run_0600.bat` → `backend/scheduled_run.py`
- 流程：确保 Edge 9225 → `run_ops.py --all` → 自动 git push frontend/data 触发 Pages 部署
- 错开 monitor（monitor 是 0500/1100/2100）

## 用法
```bash
# 跑某关键词的竞品运营监测
python backend/run_ops.py "batana oil"

# 跑配置里所有关键词
python backend/run_ops.py --all

# 选项
python backend/run_ops.py "batana oil" --no-ads   # 跳过广告洞察（更快）
python backend/run_ops.py "batana oil" --no-ai    # 跳过 AI 诊断
```

⛔ **铁律**：浏览器只用 Edge 唯一默认账户（端口 9225，不指定 profile），卖家精灵需已登录。

## 配置
`backend/data/user_config.json`（与 crossmart-monitor 共用结构）：
- `keywords[].related` = 竞品 ASIN（卖家精灵竞品运营）
- `asins[].main` = 自家 ASIN（积加真实运营数据）

## 架构
```
crossmart-ops/
├── backend/
│   ├── run_ops.py               # 入口
│   ├── step1_collect_traffic.py # 抓竞品流量/广告（卖家精灵）
│   ├── step2_analyze_ops.py     # 合成 + AI 诊断
│   ├── jike_client.py           # 积加 API（自家真实数据）
│   ├── llm_client.py / llm_config.py
│   └── browser/                 # 9225 CDP 桥（共享）
├── frontend/
│   ├── ops.html                 # 运营仪表盘
│   └── data/ops-data.json
└── .github/workflows/deploy.yml
```

## 线上
https://charlescome1995-prog.github.io/crossmart-ops/ops.html
