# test_whisper.py - 测试 Whisper 语音转写功能
import sys
import os
from pathlib import Path

# 设置 UTF-8 编码 (解决 Windows GBK 问题)
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')

# 添加 src 到路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fuguang.core.config import ConfigManager

# 简单模拟依赖
class MockMouth:
    def speak(self, text): print(f"[Mouth] {text}")
    def send_expression(self, *args): pass

class MockBrain:
    pass

def test_whisper():
    print("=" * 50)
    print("Whisper Test")
    print("=" * 50)
    
    # 初始化
    config = ConfigManager()
    mouth = MockMouth()
    brain = MockBrain()
    
    from fuguang.core.skills import SkillManager
    skills = SkillManager(config, mouth, brain)
    
    print("\n" + "-" * 50)
    
    # 测试 1: 中文语音
    print("\nTest 1: Chinese Audio (wav)")
    chinese_file = PROJECT_ROOT / "（开心）哈哈哈，是我赢了。不服的话，我也给你个复仇的机会…如何？.wav"
    if chinese_file.exists():
        result = skills.transcribe_media_file(str(chinese_file))
        print(result[:500] if len(result) > 500 else result)
    else:
        print(f"File not found: {chinese_file.name}")
    
    print("\n" + "-" * 50)
    
    # 测试 2: 英文歌曲
    print("\nTest 2: English Song (mp4)")
    english_file = PROJECT_ROOT / "「风骚律师_愚蠢的事」Something_Stupid_-_Lola_Marsh.1597539394.mp4"
    if english_file.exists():
        result = skills.transcribe_media_file(str(english_file))
        print(result[:500] if len(result) > 500 else result)
    else:
        print(f"File not found: {english_file.name}")
    
    print("\n" + "=" * 50)
    print("Test Complete!")

if __name__ == "__main__":
    test_whisper()
