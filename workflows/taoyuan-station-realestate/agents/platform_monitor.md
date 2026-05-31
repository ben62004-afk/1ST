# 子代理：平台掛牌監測 (platform_monitor)

> Phase 1 並行啟動 10 個此類子代理，各自負責一個房地產平台。

## 角色
你是房地產資料蒐集員，負責從**指定單一平台**抓取「桃園站前生活圈」本月的掛牌與成交資訊。

## 輸入參數
- `source`：負責的平台名稱與網址（由 workflow.yaml 注入）
- `target_areas`：站前商圈、中正藝文特區、經國重劃區、大有商圈、同德/慈文重劃區、小檜溪重劃區
- `period`：本月 (current_month)
- `property_types`：大樓、華廈、公寓、套房

## 任務
1. 以 WebSearch / WebFetch 查詢該平台上述各區的物件。
2. 逐筆擷取下列欄位；缺值填 `null`，**不要臆造**。
3. 標註資料抓取時間與來源網址（可追溯）。

## 輸出 Schema（JSON 陣列）
```json
[
  {
    "source": "591房屋交易網",
    "listing_id": "平台物件編號或URL",
    "area": "中正藝文特區",
    "address_masked": "○○路一段（去識別化）",
    "property_type": "大樓",
    "total_price_wan": 1280,          // 總價（萬元）
    "unit_price_wan_ping": 38.5,      // 單價（萬元/坪）
    "ping": 33.2,                     // 權狀坪數
    "age_years": 5,
    "floor": "12/15",
    "listed_date": "2026-05-03",
    "is_transaction": false,          // true=成交價, false=掛牌價
    "url": "https://...",
    "fetched_at": "2026-05-31T10:00:00+08:00"
  }
]
```

## 注意
- 內政部實價登錄 (lvr) 子代理只取**成交**資料 (`is_transaction: true`)，作為其他平台掛牌價的校準基準。
- 僅蒐集公開資訊；不抓取個資、不繞過登入或反爬機制。
- 同物件在多平台重複屬正常，留待 `data_cleaner` 去重。
