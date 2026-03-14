"""
扶光语音核心 (SiliconFlow CosyVoice2 + Pygame)
特点：流式合成，低延迟，支持 edge-tts 降级
"""
import asyncio
import re
import requests
import pygame
import time
import os
import threading
import keyboard  # 用于检测打断按键
import logging
from .config import DATA_DIR, ConfigManager

from pathlib import Path

logger = logging.getLogger("Fuguang.Voice")

# 临时音频文件
TEMP_AUDIO = DATA_DIR / "fuguang_temp.mp3"

# 🔥 线程锁（避免多线程同时播放语音冲突）
_speak_lock = threading.Lock()

# 🔥 全局打断标志
_interrupted = False

# ================================================================
# SiliconFlow CosyVoice2 配置
# ================================================================
SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
SILICONFLOW_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
SILICONFLOW_VOICE = "FunAudioLLM/CosyVoice2-0.5B:anna"


# 初始化 pygame 混音器
try:
    pygame.mixer.init()
    print("✅ 音频设备初始化成功")
except Exception as e:
    print(f"⚠️ 音频设备初始化失败: {e}")


def _generate_audio_cosyvoice(text: str, api_key: str) -> bool:
    """通过 SiliconFlow CosyVoice2 API 流式生成音频

    流式接收音频 chunks，边收边写入 mp3 文件。
    Returns True if successful, False otherwise.
    """
    global _interrupted

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": SILICONFLOW_MODEL,
        "input": text,
        "voice": SILICONFLOW_VOICE,
        "response_format": "mp3",
        "stream": True,
    }

    try:
        # 流式请求，边收边写
        response = requests.post(
            SILICONFLOW_API_URL,
            headers=headers,
            json=body,
            stream=True,
            timeout=30,
        )
        response.raise_for_status()

        # 确保目录存在
        TEMP_AUDIO.parent.mkdir(parents=True, exist_ok=True)

        # 流式写入文件
        total_bytes = 0
        with open(str(TEMP_AUDIO), "wb") as f:
            for chunk in response.iter_content(chunk_size=4096):
                if _interrupted:
                    logger.info("🎭 [TTS] 流式下载被打断")
                    return False
                if chunk:
                    f.write(chunk)
                    total_bytes += len(chunk)

        if total_bytes == 0:
            logger.warning("🎭 [TTS] CosyVoice2 返回空音频")
            return False

        logger.info(f"✅ CosyVoice2 音频生成完成 ({total_bytes} bytes)")
        return True

    except requests.exceptions.RequestException as e:
        logger.warning(f"🎭 [TTS] CosyVoice2 请求失败: {e}")
        return False
    except Exception as e:
        logger.warning(f"🎭 [TTS] CosyVoice2 异常: {e}")
        return False


async def _generate_audio_edge_tts(text: str, voice: str = "zh-CN-XiaoyiNeural"):
    """降级方案：edge-tts 合成音频"""
    import edge_tts
    TEMP_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(TEMP_AUDIO))
    logger.info(f"✅ edge-tts 音频生成完成 (降级模式)")


def _run_async(coro):
    """线程安全地运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def was_interrupted():
    """检查上次播放是否被用户打断"""
    return _interrupted


def clear_interrupt():
    """清除打断标志（在新对话开始时调用）"""
    global _interrupted
    _interrupted = False


def _clean_markdown(text: str) -> str:
    """清理 Markdown 格式符号，避免 TTS 朗读星号、井号等

    示例：
        '**专业解决方案总结：**' -> '专业解决方案总结：'
        '# 标题' -> '标题'
        '`code`' -> 'code'
        '- 列表项' -> '列表项'
    """
    # 粗体 **text** 或 __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # 斜体 *text* 或 _text_（单个）
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)
    # 行内代码 `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # 标题 # ## ### 等
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 无序列表 - 或 * 开头
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # 有序列表 1. 2. 等
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 链接 [text](url) -> text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # 残留的多余星号
    text = text.replace('*', '')
    # 代码块标记 ```
    text = text.replace('```', '')

    return text.strip()


def stop_speaking():
    """强制停止当前语音播放"""
    global _interrupted
    _interrupted = True
    try:
        pygame.mixer.music.stop()
    except Exception as e:
        # 已经停止或未初始化，忽略
        pass


def speak(text, voice="zh-CN-XiaoyiNeural"):
    """
    对外的主函数：合成并播放
    使用线程锁确保同一时间只有一个语音在播放

    优先使用 SiliconFlow CosyVoice2 API，失败时降级到 edge-tts。
    """
    if not text:
        return

    # 清理 Markdown 格式符号
    text = _clean_markdown(text)

    if not text:
        return

    # 🔥 获取锁，确保同一时间只有一个语音在播放
    with _speak_lock:
        print(f"🔊 扶光: {text}")

        # 1. 生成音频：优先 CosyVoice2，失败降级 edge-tts
        api_key = ConfigManager.SILICONFLOW_API_KEY
        generated = False

        if api_key:
            generated = _generate_audio_cosyvoice(text, api_key)
            if not generated:
                logger.info("🎭 [TTS] CosyVoice2 失败，降级到 edge-tts")

        if not generated:
            try:
                _run_async(_generate_audio_edge_tts(text, voice=voice))
                generated = True
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
                # 检测右Ctrl键打断
                if keyboard.is_pressed('right ctrl'):
                    print("⏹️ 语音被用户打断")
                    pygame.mixer.music.stop()
                    _interrupted = True
                    break
                time.sleep(0.05)

            # 🔥 关键修复:彻底释放文件占用
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
                time.sleep(0.2)
            except Exception as e:
                print(f"⚠️ 音频资源释放失败: {e}")

            # 🔥 改进：清理临时文件
            try:
                if TEMP_AUDIO.exists():
                    os.remove(TEMP_AUDIO)
            except Exception as cleanup_err:
                print(f"⚠️ 临时文件删除失败（将在下次覆盖）: {cleanup_err}")
                try:
                    temp_files = list(DATA_DIR.glob("*.mp3"))
                    if len(temp_files) > 10:
                        temp_files.sort(key=lambda f: f.stat().st_mtime)
                        for old_file in temp_files[:-5]:
                            old_file.unlink(missing_ok=True)
                        print("🧹 已清理过期临时音频文件")
                except Exception:
                    pass

        except Exception as e:
            print(f"❌ 播放失败: {e}")
        finally:
            # 🛡️ 确保资源被释放
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("✅ 扶光语音系统测试 (CosyVoice2)")
    print("=" * 60)
    speak("指挥官你好，我是扶光。这是我的新声音，听起来怎么样？")
    time.sleep(0.5)
    speak("我现在使用 CosyVoice2 语音合成了。")