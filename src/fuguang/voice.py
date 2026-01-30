"""
扶光语音核心 (EdgeTTS + Pygame)
特点：云端合成，音质极佳，晓晓 (Xiaoxiao) 音色
"""
import asyncio
import edge_tts
import pygame
import time
import os
import threading
import keyboard  # [新增] 用于检测打断按键
from .config import DATA_DIR
from pathlib import Path

# 临时音频文件
TEMP_AUDIO = DATA_DIR / "fuguang_temp.mp3"

# 🔥 线程锁（避免多线程同时播放语音冲突）
_speak_lock = threading.Lock()

# 🔥 全局打断标志
_interrupted = False

# 🔥 全局事件循环（避免重复创建）
_loop = None

def get_event_loop():
    """获取或创建事件循环"""
    global _loop
    if _loop is None or _loop.is_closed():
        try:
            _loop = asyncio.get_event_loop()
        except RuntimeError:
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
    return _loop

# 初始化 pygame 混音器
try:
    pygame.mixer.init()
    print("✅ 音频设备初始化成功")
except Exception as e:
    print(f"⚠️ 音频设备初始化失败: {e}")

async def generate_audio(text, voice="zh-CN-XiaoyiNeural"):
    """
    异步生成音频文件
    voice: 
      - zh-CN-XiaoxiaoNeural (温柔女声)
      - zh-CN-XiaoyiNeural (甜美女声)
      - zh-CN-YunxiNeural (沉稳男声)
    """
    # Ensure directory exists
    TEMP_AUDIO.parent.mkdir(parents=True, exist_ok=True) 
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(TEMP_AUDIO))
    print(f"✅ Audio saved to: {TEMP_AUDIO}")

def was_interrupted():
    """检查上次播放是否被用户打断"""
    return _interrupted

def clear_interrupt():
    """清除打断标志（在新对话开始时调用）"""
    global _interrupted
    _interrupted = False

def stop_speaking():
    """强制停止当前语音播放"""
    global _interrupted
    _interrupted = True
    try:
        pygame.mixer.music.stop()
    except:
        pass

def speak(text, voice="zh-CN-XiaoyiNeural"):
    """
    对外的主函数：合成并播放
    使用线程锁确保同一时间只有一个语音在播放
    """
    if not text: 
        return
    
    # 🔥 获取锁，确保同一时间只有一个语音在播放
    with _speak_lock:
        print(f"🔊 扶光: {text}")
        
        # 1. 生成音频 (使用全局事件循环)
        try:
            loop = get_event_loop()
            loop.run_until_complete(generate_audio(text, voice=voice))
        except Exception as e:
            print(f"❌ 语音合成失败: {e}")
            return

        # 2. 播放音频
        try:
            pygame.mixer.music.load(str(TEMP_AUDIO))
            pygame.mixer.music.play()
            
            # 阻塞等待播放结束，支持右Ctrl打断
            global _interrupted
            _interrupted = False
            
            while pygame.mixer.music.get_busy():
                # [新增] 检测右Ctrl键打断
                if keyboard.is_pressed('right ctrl'):
                    print("⏹️ 语音被用户打断")
                    pygame.mixer.music.stop()
                    _interrupted = True
                    break
                time.sleep(0.05)  # 缩短检测间隔，提高响应速度
            
            # 🔥 关键修复:彻底释放文件占用
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            time.sleep(0.2)  # 给系统一点时间释放文件
            
            # 🔥 改进：清理临时文件，失败时记录日志
            try:
                if TEMP_AUDIO.exists():
                    os.remove(TEMP_AUDIO)
            except Exception as cleanup_err:
                print(f"⚠️ 临时文件删除失败（将在下次覆盖）: {cleanup_err}")
                # 定期清理：如果临时文件夹超过10个文件，清理旧文件
                try:
                    temp_files = list(DATA_DIR.glob("*.mp3"))
                    if len(temp_files) > 10:
                        temp_files.sort(key=lambda f: f.stat().st_mtime)
                        for old_file in temp_files[:-5]:  # 保留最新5个
                            old_file.unlink(missing_ok=True)
                        print("🧹 已清理过期临时音频文件")
                except Exception:
                    pass
                
        except Exception as e:
            print(f"❌ 播放失败: {e}")

# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("✅ 扶光语音系统测试")
    print("=" * 60)
    speak("指挥官你好，我是扶光。这是我的新声音，听起来怎么样？")
    time.sleep(0.5)
    speak("我现在可以切换不同的音色了。", voice="zh-CN-YunxiNeural")