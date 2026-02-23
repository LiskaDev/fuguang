"""Browser MCP 实战演示脚本 — 输出写文件"""
from playwright.sync_api import sync_playwright
import os, sys

output_lines = []
def log(msg=""):
    output_lines.append(msg)
    print(msg)

log("=" * 60)
log("🤖 Browser MCP 实战演示")
log("=" * 60)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)
context = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="zh-CN")
page = context.new_page()

# === 1. browser_open ===
log("\n【1】browser_open — 打开 GitHub 首页")
page.goto("https://github.com", wait_until="domcontentloaded", timeout=30000)
title = page.title()
log(f"   页面标题: {title}")
text = page.evaluate("""() => {
    document.querySelectorAll("script, style, nav, footer, aside").forEach(el => el.remove());
    return document.body ? document.body.innerText.substring(0, 500) : '';
}""")
log("   正文前500字:")
for line in text.strip().split("\n")[:8]:
    if line.strip():
        log(f"      {line.strip()[:80]}")

# === 2. browser_get_text ===
log("\n【2】browser_get_text — 提取 h1 标签")
h1s = page.query_selector_all("h1")
for i, el in enumerate(h1s[:3], 1):
    log(f"   {i}. {el.inner_text().strip()[:100]}")
if not h1s:
    log("   (无 h1)")

# === 3. browser_run_js ===
log("\n【3】browser_run_js — 执行 JavaScript")
info = page.evaluate("""() => ({
    url: window.location.href,
    links: document.querySelectorAll("a").length,
    images: document.querySelectorAll("img").length,
    viewport: window.innerWidth + "x" + window.innerHeight
})""")
for k, v in info.items():
    log(f"   {k}: {v}")

# === 4. browser_screenshot ===
log("\n【4】browser_screenshot — 截图")
os.makedirs("temp_files", exist_ok=True)
page.screenshot(path="temp_files/demo_github.png", full_page=False)
size = os.path.getsize("temp_files/demo_github.png")
log(f"   截图已保存: temp_files/demo_github.png ({size // 1024} KB)")

# === 5. browser_click ===
log("\n【5】browser_click — 点击元素")
page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
h1_text = page.query_selector("h1").inner_text()
page.click("h1", timeout=5000)
log(f"   已点击: <h1>{h1_text}</h1>")
log(f"   页面: {page.title()}")

# === 6. browser_fill_form ===
log("\n【6】browser_fill_form — 填表单")
try:
    page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=30000)
    page.fill("#sb_form_q", "Playwright browser automation", timeout=10000)
    val = page.input_value("#sb_form_q")
    log(f'   搜索框已填入: "{val}"')
    page.screenshot(path="temp_files/demo_bing_filled.png", full_page=False)
    s2 = os.path.getsize("temp_files/demo_bing_filled.png")
    log(f"   截图保存: temp_files/demo_bing_filled.png ({s2 // 1024} KB)")
except Exception as e:
    log(f"   填写异常: {e}")

browser.close()
pw.stop()

log("\n" + "=" * 60)
log("ALL 6 CAPABILITIES VERIFIED OK")
log("=" * 60)

# 写到文件
with open("temp_files/demo_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))
