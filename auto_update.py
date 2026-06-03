"""
auto_update.py — 一键自动更新流水线
====================================
依次执行：
  1. sync_stock_daily   — 拉取原始行情数据入库
  2. index_update       — 更新基准指数数据
  3. liquidity_monitor  — 计算指标并生成 HTML 面板

用法：
  python auto_update.py            # 运行一次
  python auto_update.py --retry 3  # 失败自动重试 3 次
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime


STEPS = [
    ("sync_stock_daily.py",   "拉取原始行情数据"),
    ("index_update.py",       "更新基准指数数据"),
    ("liquidity_monitor.py",  "生成流动性监控面板"),
]


def run_step(script, description, retries=0):
    print(f"\n{'=' * 50}")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {description} ({script})")
    print(f"{'=' * 50}")

    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"  🔄 重试 {attempt}/{retries}...")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=False,
            text=True,
        )
        if result.returncode == 0:
            print(f"  ✅ {description} 完成")
            return
        print(f"  ❌ {script} 返回错误码 {result.returncode}")

    print(f"\n💥 {script} 执行失败，已重试 {retries} 次，流水线中止。")
    sys.exit(1)


def main():
    retries = 0
    if "--retry" in sys.argv:
        idx = sys.argv.index("--retry")
        retries = int(sys.argv[idx + 1])

    print(f"🚀 市场流动性监控 — 自动更新流水线")
    print(f"   启动时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"   重试次数: {retries}")

    for script, desc in STEPS:
        run_step(script, desc, retries=retries)

    # 复制到桌面
    src = "liquidity_dashboard.html"
    desktop = os.path.expanduser("~/Desktop")
    dst = os.path.join(desktop, "liquidity_dashboard.html")
    shutil.copy2(src, dst)

    print(f"\n🎉 全部完成！{datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"   面板已生成: {src}")
    print(f"   已复制到桌面: {dst}")


if __name__ == "__main__":
    main()
