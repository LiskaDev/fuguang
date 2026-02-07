# test_whisper_cuda.py - 测试 CUDA 加速的 Whisper small 模型
import whisper
import torch
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parent

def main():
    print("=" * 60)
    print("Whisper CUDA + Small Model Test")
    print("=" * 60)
    
    # 检查 CUDA
    print(f"\nPyTorch: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    
    # 加载模型
    print("\n[1] Loading Whisper 'small' model...")
    start = time.time()
    model = whisper.load_model("small")
    print(f"    Loaded in {time.time()-start:.1f}s")
    print(f"    Device: {next(model.parameters()).device}")
    
    # 测试中文音频
    print("\n[2] Testing Chinese audio with GPU...")
    chinese_file = PROJECT_ROOT / "（开心）哈哈哈，是我赢了。不服的话，我也给你个复仇的机会…如何？.wav"
    if chinese_file.exists():
        start = time.time()
        result = model.transcribe(str(chinese_file), fp16=True)
        elapsed = time.time() - start
        print(f"    Time: {elapsed:.2f}s")
        print(f"    Language: {result['language']}")
        print(f"    Text: {result['text']}")
    else:
        print(f"    File not found!")
    
    print("\n" + "=" * 60)
    print("Done!")

if __name__ == "__main__":
    main()
