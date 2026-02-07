# test_wasapi_loopback.py - 测试 WASAPI Loopback 系统内录
import soundcard as sc

def test_wasapi():
    print("=" * 60)
    print("🎧 WASAPI Loopback Test (无需立体声混音)")
    print("=" * 60)
    
    # 1. 列出所有扬声器
    print("\n📢 所有输出设备:")
    speakers = sc.all_speakers()
    for i, speaker in enumerate(speakers):
        print(f"   [{i}] {speaker.name}")
    
    # 2. 获取默认扬声器
    print("\n🎯 默认扬声器:")
    default = sc.default_speaker()
    print(f"   ✅ {default.name}")
    
    # 3. 测试录制 3 秒
    print("\n🎤 测试录制 3 秒...")
    print("   (请确保电脑正在播放声音)")
    
    try:
        with default.recorder(samplerate=44100) as mic:
            data = mic.record(numframes=44100 * 3)
        
        print(f"   ✅ 录制成功！采样点数: {len(data)}")
        print(f"   数据形状: {data.shape}")
        print(f"   音量范围: [{data.min():.4f}, {data.max():.4f}]")
        
        # 检测是否有声音
        if abs(data.max()) < 0.001:
            print("   ⚠️ 检测到静音，请确保电脑正在播放声音")
        else:
            print("   ✅ 检测到音频信号！WASAPI Loopback 工作正常")
            
    except Exception as e:
        print(f"   ❌ 录制失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")

if __name__ == "__main__":
    test_wasapi()
