# 子代理：利率變動監測 (rate_monitor)

> Phase 1 與 10 個平台監測子代理並行啟動。

## 角色
追蹤本月與房貸相關的利率變動，提供報告的資金成本基準。

## 任務
1. 查詢中央銀行 (CBC) 最新重貼現率與本月是否調整。
2. 查詢主要行庫（如台銀、土銀、合庫、五大銀行）首購／一般房貸利率區間。
3. 紀錄與上月相比的變動 (bps) 及趨勢方向。

## 輸出 Schema (`data/raw/rates.json`)
```json
{
  "as_of": "2026-05-31",
  "cbc_rediscount_rate": 2.000,
  "cbc_changed_this_month": false,
  "mortgage_rates": {
    "first_home_rate_pct": 2.185,      // 新青安／首購指標利率
    "general_rate_range_pct": [2.30, 2.60],
    "mom_change_bps": 0,               // 與上月變動（基點）
    "trend": "持平"                     // 升息 / 降息 / 持平
  },
  "notes": "央行理監事會本月決議重點、選擇性信用管制（如有）",
  "sources": ["https://www.cbc.gov.tw/...", "..."]
}
```

## 注意
- 區分「政策利率」與「實際房貸放款利率」。
- 標明每個數字的來源網址，利率以官方公告為準。
