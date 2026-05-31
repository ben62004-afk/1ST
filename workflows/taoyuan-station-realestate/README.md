# 桃園站前房地產市場分析 Workflow

針對 **桃園站前生活圈** 的房地產市場，每月蒐集最新成交價格與利率變動，並行監測
10 個房地產平台的掛牌資訊，進行數據清洗與流動性風險分析，最後產出**各區溢價潛力
對比報告**。

## 流程總覽

```
Phase 1  數據蒐集（並行 11 個子代理）
  ├─ agent-01 ~ agent-10  platform_monitor   ← 10 個房地產平台
  └─ agent-rate           rate_monitor       ← 央行/行庫利率
        │  (≥6 平台成功 + 實價登錄 + 利率，否則中止)
        ▼
Phase 2  數據清洗與分析（並行）
  ├─ data_cleaner       去重 / 單位統一 / 離群值 / 實登校準
  └─ liquidity_analyst  DOM / 降價率 / 成交掛牌比 → 流動性風險評分
        │
        ▼
Phase 3  溢價潛力對比報告
  └─ report_writer  →  reports/premium-potential-report.md
```

## 監測的 10 個平台
591房屋交易網、樂屋網、永慶房屋、信義房屋、住商不動產、台灣房屋、中信房屋、
好房網、屋比，以及 **內政部實價登錄**（官方成交基準）。

## 目錄結構
```
workflows/taoyuan-station-realestate/
├── workflow.yaml              # 宣告式流程定義（phase / task / 相依 / 失敗策略）
├── run.py                     # 協調器：排程、並行、失敗門檻控制
├── agents/                    # 6 種子代理 prompt
│   ├── platform_monitor.md    #   平台掛牌監測（×10 並行）
│   ├── rate_monitor.md        #   利率變動監測
│   ├── data_cleaner.md        #   數據清洗
│   ├── liquidity_analyst.md   #   流動性風險分析
│   └── report_writer.md       #   溢價潛力報告彙整
├── templates/
│   └── premium-report.md      # 最終報告模板
├── data/                      # 執行產物（raw / clean / analysis）
└── reports/                   # 最終報告輸出
```

## 執行
```bash
cd workflows/taoyuan-station-realestate
pip install pyyaml

# 演練（印出執行計畫，不連網）
python run.py

# 實跑：將 run.py 的 executor 接上 Claude Agent SDK 或自訂抓取器後
python run.py --execute
```

> `run.py` 預設為 **dry-run**，負責排程/並行/相依/失敗策略；實際的網路蒐集與
> LLM 分析需在 `dry_run_executor` 位置接上真實執行器（例如 Claude Agent SDK，
> 將各 `agents/*.md` 作為子代理 prompt）。

## 失敗策略
- 單一平台失敗不阻斷整體。
- 進入 Phase 2 需：成功平台 ≥ 6，且 **實價登錄** 與 **利率** 來源皆成功。
- 每個 task 重試 3 次，退避 2s / 4s / 8s。

## 注意事項
- 僅蒐集公開資訊，不抓取個資、不繞過登入或反爬機制。
- 所有數字須可回溯至 `data/` 檔案，樣本不足須在報告中聲明。
- 報告為市場分析，非投資建議。
