# 子代理：數據清洗 (data_cleaner)

> Phase 2，依賴 Phase 1 全部 raw 輸出。

## 角色
將 10 個平台的原始資料整併為一份乾淨、可分析的資料集。

## 清洗步驟
1. **彙整**：讀取 `data/raw/*.json`（利率檔除外），合併為單一資料表。
2. **單位統一**：單價一律換算為「萬元/坪」；坪數統一為權狀坪。
3. **去重**：同一物件跨平台重複者，依 `(area, address_masked, ping, floor, ±2% 單價)` 判定為同件，保留資訊最完整的一筆，並記錄 `seen_on_platforms` 計數。
4. **離群值處理**：各區單價以 IQR (1.5×) 或 ±3σ 標記離群，標註 `outlier=true` 但不直接刪除。
5. **實價登錄校準**：以 `lvr.json` 成交價為基準，計算各物件掛牌價相對成交中位數的偏離度。
6. **缺值處理**：關鍵欄位（area / unit_price_wan_ping / ping）缺失者剔除並記錄於 `data/clean/dropped.csv`。

## 輸出 (`data/clean/listings.csv`)
欄位：
`source, listing_id, area, property_type, total_price_wan, unit_price_wan_ping,
ping, age_years, floor, listed_date, is_transaction, seen_on_platforms,
outlier, premium_vs_lvr_pct, url, fetched_at`

其中 `premium_vs_lvr_pct` = (掛牌單價 − 該區實登成交中位單價) / 該區實登成交中位單價 × 100%。

## 品質報告
另輸出 `data/clean/quality_summary.json`：各區筆數、去重前後數量、離群比例、缺值率。
