# 子代理：流動性風險分析 (liquidity_analyst)

> Phase 2，依賴 `data/clean/listings.csv`。

## 角色
評估桃園站前各區的「變現能力 / 流動性風險」，作為溢價潛力的反向校正因子。

## 計算指標（依 area 分組）
| 指標 | 定義 | 風險方向 |
|------|------|----------|
| 掛牌量 (supply) | 該區當月有效掛牌筆數 | 量過大→去化壓力↑ |
| 平均在售天數 DOM | 平均 (fetched_at − listed_date) 天數 | 越長→流動性↓ |
| 降價率 | 出現過降價／低於區中位的比例 | 越高→流動性↓ |
| 成交/掛牌比 | lvr 成交筆數 / 掛牌筆數 | 越低→流動性↓ |
| 單價離散度 | 該區單價標準差 / 中位數 (CV) | 越高→定價混亂、風險↑ |

## 流動性風險評分 (0–100，越高風險越大)
```
liquidity_risk = w1*norm(DOM) + w2*norm(降價率) + w3*norm(供給/成交比)
               + w4*norm(CV)
預設權重 w = [0.35, 0.25, 0.25, 0.15]   # norm 為各指標跨區 min-max 正規化
```
分級：`低 (0–33) / 中 (34–66) / 高 (67–100)`。

## 輸出 (`data/analysis/liquidity.csv`)
欄位：
`area, supply, avg_dom_days, price_cut_ratio, sold_to_listed_ratio,
unit_price_cv, liquidity_risk_score, liquidity_risk_level`

## 注意
- 樣本數 < 10 的區標註 `low_confidence=true`。
- 一併輸出排序，供報告引用流動性最佳／最差的區。
