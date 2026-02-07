# quick_whisper_test.py - 快速测试 Whisper
import whisper

print("=" * 50)
print("Whisper Quick Test")
print("=" * 50)

print("\n1. Loading Whisper model...")
model = whisper.load_model("base")
print("   Model loaded!")

print("\n2. Testing with fuguang_local.wav...")
result = model.transcribe(r"C:\Users\ALan\Desktop\fuguang\fuguang_local.wav", fp16=False)
print(f"   Language: {result['language']}")
print(f"   Text: {result['text']}")

print("\n" + "=" * 50)
print("Done!")
