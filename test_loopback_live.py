# test_loopback_live.py - 实时测试系统内录 + Whisper 转写
import soundcard as sc
import soundfile as sf
import tempfile
import os

print("=" * 60)
print("🎧 WASAPI Loopback 实时测试")
print("=" * 60)

# 1. 获取设备
speaker = sc.default_speaker()
loopback = sc.get_microphone(id=str(speaker.id), include_loopback=True)
print(f"🎧 扬声器: {speaker.name}")
print(f"🎤 Loopback: {loopback.name}")

# 2. 录制
DURATION = 15
SAMPLE_RATE = 44100
print(f"\n⏺️ 开始录制 {DURATION} 秒...")
print("   >>> 请立即播放视频！ <<<")

with loopback.recorder(samplerate=SAMPLE_RATE) as mic:
    data = mic.record(numframes=SAMPLE_RATE * DURATION)

print(f"✅ 录制完成！采样点: {data.shape}")

# 3. 保存
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    temp_path = f.name
sf.write(temp_path, data, SAMPLE_RATE)
print(f"💾 已保存: {temp_path}")

# 4. Whisper 转写
print("\n🤖 正在加载 Whisper 'small' 模型 (GPU)...")
import whisper
model = whisper.load_model("small")
print("✅ 模型加载完成，正在转写...")

result = model.transcribe(temp_path, fp16=True)
text = result["text"].strip()
lang = result.get("language", "unknown")

print("\n" + "=" * 60)
print(f"📝 语言: {lang}")
print(f"📝 转写结果:\n{text}")
print("=" * 60)

os.remove(temp_path)
