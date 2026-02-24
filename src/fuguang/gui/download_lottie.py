"""
下载 Google Noto Animated Emoji 的 Lottie JSON 文件

URL 格式: https://fonts.gstatic.com/s/e/notoemoji/latest/{codepoint}/lottie.json

使用方法: python download_lottie.py
"""
import urllib.request
import os
from pathlib import Path

# 目标目录
EMOTIONS_DIR = Path(__file__).parent / "emotions"
EMOTIONS_DIR.mkdir(exist_ok=True)

# Emoji 名称 → Unicode 码点映射
EMOJI_MAP = {
    "neutral":    "1f610",   # 😐 Neutral Face
    "joy":        "1f604",   # 😄 Grinning Face with Smiling Eyes
    "angry":      "1f624",   # 😤 Face with Steam From Nose
    "sorrow":     "1f622",   # 😢 Crying Face
    "fun":        "1f60f",   # 😏 Smirking Face
    "surprised":  "1f632",   # 😲 Astonished Face
    "thinking":   "1f914",   # 🤔 Thinking Face
    "shy":        "1f633",   # 😳 Flushed Face
    "love":       "1f970",   # 🥰 Smiling Face with Hearts
    "proud":      "1f929",   # 🤩 Star-Struck
    "confused":   "1f635",   # 😵 Face with Crossed-Out Eyes
    "apologetic": "1f625",   # 😥 Sad but Relieved Face
    "sleeping":   "1f634",   # 😴 Sleeping Face
    "working":    "2699_fe0f",  # ⚙️ Gear
    "wave":       "1f44b",   # 👋 Waving Hand
    "error":      "26a0_fe0f",  # ⚠️ Warning
    "listening":  "1f44b",   # 👋 Waving Hand (same as wave)
}

BASE_URL = "https://fonts.gstatic.com/s/e/notoemoji/latest/{code}/lottie.json"

def download_all():
    total = len(EMOJI_MAP)
    success = 0
    failed = []
    
    for name, code in EMOJI_MAP.items():
        target = EMOTIONS_DIR / f"{name}.json"
        url = BASE_URL.format(code=code)
        
        if target.exists():
            print(f"  ✓ {name}.json 已存在，跳过")
            success += 1
            continue
        
        print(f"  ⬇ 下载 {name}.json ({code})...", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                target.write_bytes(data)
                size_kb = len(data) / 1024
                print(f"OK ({size_kb:.1f} KB)")
                success += 1
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(name)
    
    print(f"\n完成: {success}/{total} 成功")
    if failed:
        print(f"失败: {failed}")

if __name__ == "__main__":
    print(f"📦 Lottie JSON 下载器 → {EMOTIONS_DIR}\n")
    download_all()
