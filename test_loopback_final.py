# test_loopback_final.py - 系统内录测试 (ASCII safe)
import soundcard as sc
import soundfile as sf
import tempfile
import os
import sys

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("[WASAPI Loopback Test]")
print("=" * 60)

# 1. Get device
speaker = sc.default_speaker()
loopback = sc.get_microphone(id=str(speaker.id), include_loopback=True)
print(f"Speaker: {speaker.name}")
print(f"Loopback: {loopback.name}")

# 2. Record
DURATION = 15
SAMPLE_RATE = 44100
print(f"\n>>> Recording {DURATION} seconds... PLAY VIDEO NOW! <<<")

with loopback.recorder(samplerate=SAMPLE_RATE) as mic:
    data = mic.record(numframes=SAMPLE_RATE * DURATION)

print(f"Recording done! Shape: {data.shape}")

# 3. Save
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    temp_path = f.name
sf.write(temp_path, data, SAMPLE_RATE)

# 4. Whisper
print("\nLoading Whisper 'small' model (GPU)...")
import whisper
model = whisper.load_model("small")
print("Model loaded. Transcribing...")

result = model.transcribe(temp_path, fp16=True)
text = result["text"].strip()
lang = result.get("language", "unknown")

print("\n" + "=" * 60)
print(f"Language: {lang}")
print(f"Transcription:")
print(text)
print("=" * 60)

# Save result
with open("loopback_result.txt", "w", encoding="utf-8") as f:
    f.write(f"Language: {lang}\n")
    f.write(f"Transcription:\n{text}\n")

os.remove(temp_path)
print("\nResult saved to loopback_result.txt")
