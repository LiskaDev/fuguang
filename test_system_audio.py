# test_system_audio.py - 测试系统内录功能
import pyaudio

def scan_audio_devices():
    """扫描所有音频输入设备，检查是否有立体声混音"""
    print("=" * 60)
    print("🎧 System Audio Devices Scan")
    print("=" * 60)
    
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    print(f"\n共发现 {numdevices} 个音频设备:\n")
    
    stereo_mix_found = False
    
    for i in range(numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        name = device_info.get('name')
        input_channels = device_info.get('maxInputChannels')
        output_channels = device_info.get('maxOutputChannels')
        
        if input_channels > 0:
            device_type = "🎤 输入"
            
            # 检查是否是立体声混音
            if "Stereo Mix" in name or "立体声混音" in name or "stereo mix" in name.lower():
                print(f"[{i}] {name}")
                print(f"    类型: {device_type} | 通道数: {input_channels}")
                print(f"    ✅ 这是系统内录设备！")
                stereo_mix_found = True
            else:
                print(f"[{i}] {name}")
                print(f"    类型: {device_type} | 通道数: {input_channels}")
    
    print("\n" + "-" * 60)
    
    if stereo_mix_found:
        print("✅ 找到立体声混音设备！系统内录功能可用。")
    else:
        print("❌ 未找到立体声混音设备！")
        print("\n请按以下步骤启用：")
        print("1. 右键任务栏右下角的喇叭图标 -> 声音设置")
        print("2. 找到'更多声音设置'或'管理声音设备'")
        print("3. 切换到'录制'选项卡")
        print("4. 右键空白处 -> 勾选'显示禁用的设备'")
        print("5. 找到'立体声混音'(Stereo Mix) -> 右键 -> 启用")
    
    print("\n" + "=" * 60)
    p.terminate()
    
    return stereo_mix_found

if __name__ == "__main__":
    scan_audio_devices()
