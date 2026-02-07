# verify_whisper_upgrade.py - 完整验证 CUDA + Small 模型
import whisper
import torch
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_ROOT / "whisper_upgrade_results.txt"

def main():
    results = []
    results.append("=" * 70)
    results.append("🎧 Whisper CUDA + Small Model Verification Test")
    results.append("=" * 70)
    
    # 1. 系统检查
    results.append("\n📊 [1] System Check")
    results.append(f"    PyTorch Version: {torch.__version__}")
    results.append(f"    CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        results.append(f"    GPU: {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        results.append(f"    VRAM: {vram:.1f} GB")
    
    # 2. 加载模型
    results.append("\n🚀 [2] Loading Whisper 'small' Model")
    start = time.time()
    model = whisper.load_model("small")
    load_time = time.time() - start
    device = str(next(model.parameters()).device)
    results.append(f"    Model Size: small (~244M params)")
    results.append(f"    Load Time: {load_time:.1f}s")
    results.append(f"    Device: {device}")
    results.append(f"    FP16 (Half Precision): Enabled")
    
    # 3. 测试中文音频
    results.append("\n🇨🇳 [3] Chinese Audio Test")
    chinese_file = PROJECT_ROOT / "（开心）哈哈哈，是我赢了。不服的话，我也给你个复仇的机会…如何？.wav"
    if chinese_file.exists():
        results.append(f"    File: {chinese_file.name}")
        start = time.time()
        result = model.transcribe(str(chinese_file), fp16=True)
        elapsed = time.time() - start
        results.append(f"    Processing Time: {elapsed:.2f}s")
        results.append(f"    Detected Language: {result['language']}")
        results.append(f"    Transcription ({len(result['text'])} chars):")
        results.append(f"    >>> {result['text']}")
    else:
        results.append("    ❌ File not found!")
    
    # 4. 测试英文歌曲
    results.append("\n🇺🇸 [4] English Song Test")
    english_file = PROJECT_ROOT / "「风骚律师_愚蠢的事」Something_Stupid_-_Lola_Marsh.1597539394.mp4"
    if english_file.exists():
        results.append(f"    File: {english_file.name}")
        start = time.time()
        result = model.transcribe(str(english_file), fp16=True)
        elapsed = time.time() - start
        results.append(f"    Processing Time: {elapsed:.2f}s")
        results.append(f"    Detected Language: {result['language']}")
        results.append(f"    Transcription ({len(result['text'])} chars):")
        # 截取前 300 字符
        text_preview = result['text'][:300] + "..." if len(result['text']) > 300 else result['text']
        results.append(f"    >>> {text_preview}")
    else:
        results.append("    ❌ File not found!")
    
    # 5. 总结
    results.append("\n" + "=" * 70)
    results.append("✅ Verification Complete!")
    results.append(f"   Model: small | Device: {device} | FP16: True")
    results.append("=" * 70)
    
    # 输出结果
    output = "\n".join(results)
    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(output)

if __name__ == "__main__":
    main()
