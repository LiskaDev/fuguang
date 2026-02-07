# full_whisper_test.py - 完整测试 Whisper（输出到文件）
import whisper
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_ROOT / "whisper_test_results.txt"

def main():
    results = []
    results.append("=" * 60)
    results.append("Whisper Transcription Test Results")
    results.append("=" * 60)
    
    # 加载模型
    results.append("\n[1] Loading Whisper 'base' model...")
    model = whisper.load_model("base")
    results.append("    Model loaded successfully!")
    
    # 测试文件列表
    test_files = [
        ("Chinese Audio", "（开心）哈哈哈，是我赢了。不服的话，我也给你个复仇的机会…如何？.wav"),
        ("English Song", "「风骚律师_愚蠢的事」Something_Stupid_-_Lola_Marsh.1597539394.mp4"),
    ]
    
    for i, (name, filename) in enumerate(test_files, 2):
        results.append(f"\n[{i}] Testing: {name}")
        results.append(f"    File: {filename}")
        
        filepath = PROJECT_ROOT / filename
        if not filepath.exists():
            results.append(f"    ERROR: File not found!")
            continue
        
        results.append(f"    Transcribing...")
        try:
            result = model.transcribe(str(filepath), fp16=False)
            lang = result.get("language", "unknown")
            text = result.get("text", "").strip()
            
            results.append(f"    Language: {lang}")
            results.append(f"    Text ({len(text)} chars):")
            results.append(f"    {text[:500]}...")
        except Exception as e:
            results.append(f"    ERROR: {e}")
    
    results.append("\n" + "=" * 60)
    results.append("Test Complete!")
    results.append("=" * 60)
    
    # 写入文件
    output = "\n".join(results)
    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"Results saved to: {OUTPUT_FILE}")
    print(output)

if __name__ == "__main__":
    main()
