#!/usr/bin/env python3
"""桃園站前房地產分析 workflow 協調器 (orchestrator)。

讀取 workflow.yaml，依 phase 順序排程；同一 phase 內 mode=parallel 的 task 並行
執行。每個 task 對應 agents/ 下的子代理 prompt。

本協調器負責「排程 / 相依 / 並行 / 失敗策略」。實際的網路蒐集與 LLM 分析由
EXECUTOR 介面執行 —— 預設為 dry-run（印出執行計畫），可接上 Claude Agent SDK
或自訂 HTTP 抓取器後改為實跑。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：pip install pyyaml")

ROOT = pathlib.Path(__file__).parent


def load_workflow() -> dict:
    with open(ROOT / "workflow.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_task(task: dict, params: dict, executor) -> tuple[str, bool]:
    """執行單一 task，回傳 (task_id, 是否成功)。"""
    agent = task["agent"]
    prompt_path = ROOT / "agents" / f"{agent}.md"
    try:
        ok = executor(task=task, prompt_path=prompt_path, params=params)
        return task["id"], bool(ok)
    except Exception as exc:  # 單一 task 失敗不應拖垮整個 phase
        print(f"  [FAIL] {task['id']}: {exc}")
        return task["id"], False


def run_phase(phase: dict, params: dict, executor) -> dict[str, bool]:
    print(f"\n=== Phase: {phase['id']} ({phase['name']}) — mode={phase['mode']} ===")
    results: dict[str, bool] = {}
    tasks = phase.get("tasks", [])

    if phase["mode"] == "parallel":
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = [pool.submit(run_task, t, params, executor) for t in tasks]
            for fut in concurrent.futures.as_completed(futures):
                tid, ok = fut.result()
                results[tid] = ok
    else:  # sequential
        for t in tasks:
            tid, ok = run_task(t, params, executor)
            results[tid] = ok

    succeeded = sum(results.values())
    print(f"--- Phase {phase['id']} 完成：{succeeded}/{len(tasks)} 成功 ---")
    return results


def check_policy(phase_id: str, results: dict[str, bool], policy: dict) -> bool:
    """檢查是否允許進入下一階段。"""
    if phase_id != "collect":
        return all(results.values())
    # collect 階段套用最低成功門檻與必要來源
    platform_ok = sum(1 for k, v in results.items() if k.startswith("agent-") and v)
    if platform_ok < policy.get("collect_min_success", 1):
        print(f"!! 蒐集成功平台 {platform_ok} 低於門檻，中止。")
        return False
    for req in policy.get("required_sources", []):
        if not results.get(req, False):
            print(f"!! 必要來源 {req} 失敗，中止。")
            return False
    return True


def dry_run_executor(task: dict, prompt_path: pathlib.Path, params: dict) -> bool:
    """預設執行器：只列出將執行什麼，不實際連網。"""
    src = task.get("source", task["agent"])
    print(f"  [DRY-RUN] {task['id']:<20} agent={task['agent']:<18} 來源={src}")
    print(f"            prompt={prompt_path.relative_to(ROOT)} → output={task.get('output', '-')}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="桃園站前房地產分析 workflow")
    ap.add_argument("--execute", action="store_true",
                    help="實跑（需自行接上真實 executor，預設為 dry-run）")
    args = ap.parse_args()

    wf = load_workflow()
    params = wf.get("params", {})
    policy = wf.get("policy", {})
    executor = dry_run_executor  # TODO: --execute 時替換為真實 Agent/抓取執行器

    print(f"Workflow: {wf['name']} v{wf['version']}")
    print(f"目標區域: {', '.join(wf['target_areas'])}")

    for phase in wf["phases"]:
        results = run_phase(phase, params, executor)
        if not check_policy(phase["id"], results, policy):
            return 1

    print("\n✅ Workflow 全部階段完成。報告：reports/premium-potential-report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
