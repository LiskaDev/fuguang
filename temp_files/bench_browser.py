"""Browser MCP 速度测试"""
import time, os, ssl

# === 1. Playwright headless ===
print("=== Playwright ===")
from playwright.sync_api import sync_playwright

t0 = time.time()
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)
t_launch = time.time() - t0

ctx = browser.new_context(viewport={"width": 1920, "height": 1080})
page = ctx.new_page()

t1 = time.time()
page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
page.title()
page.evaluate("() => document.body.innerText")
t_page = time.time() - t1

t2 = time.time()
page.goto("https://github.com", wait_until="domcontentloaded", timeout=30000)
page.title()
page.evaluate("() => document.body.innerText.substring(0, 1000)")
t_page2 = time.time() - t2

t3 = time.time()
page.screenshot(path="temp_files/bench_screenshot.png", full_page=False)
t_screenshot = time.time() - t3

browser.close()
pw.stop()

# === 2. httpx (skip SSL for conda) ===
print("=== httpx ===")
import httpx

client = httpx.Client(verify=False, timeout=15, follow_redirects=True)

t4 = time.time()
client.get("https://example.com")
t_req1 = time.time() - t4

t5 = time.time()
client.get("https://github.com")
t_req2 = time.time() - t5
client.close()

# === output ===
lines = []
lines.append("=" * 55)
lines.append("          Browser MCP 速度基准测试")
lines.append("=" * 55)
lines.append(f"  Playwright 冷启动:         {t_launch:.2f}s (仅第一次)")
lines.append(f"  Playwright example.com:    {t_page:.2f}s")
lines.append(f"  Playwright github.com:     {t_page2:.2f}s")
lines.append(f"  Playwright 截图:           {t_screenshot:.2f}s")
lines.append(f"  httpx     example.com:     {t_req1:.2f}s")
lines.append(f"  httpx     github.com:      {t_req2:.2f}s")
lines.append("=" * 55)
ratio = t_page2 / t_req2 if t_req2 > 0 else 0
lines.append(f"  Playwright / httpx 倍率:   {ratio:.1f}x")
lines.append("=" * 55)

for l in lines:
    print(l)

with open("temp_files/bench_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
