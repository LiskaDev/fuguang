"""
扶光语音核心 (SiliconFlow CosyVoice2 + PyAudio PCM 流式播放)
特点：真正边收边播，音频振幅驱动 VTS 嘴巴动作，支持 edge-tts 降级
"""
import asyncio
import re
import struct
import math
import requests
import pygame
import pyaudio
import numpy as np
import time
import os
import threading
import keyboard
import logging
from .config import DATA_DIR, ConfigManager
from typing import Optional, Callable

from pathlib import Path

logger = logging.getLogger("Fuguang.Voice")

# 临时音频文件 (仅 edge-tts 降级使用)
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

# PCM 流式播放参数
PCM_SAMPLE_RATE = 24000
PCM_CHANNELS = 1
PCM_FORMAT = pyaudio.paInt16  # 16-bit signed int
PCM_CHUNK_SIZE = 4096  # HTTP chunk size (bytes)

# RMS 归一化参数
RMS_MAX = 2000.0  # 语音 RMS 归一化上限（越小嘴巴幅度越大）
RMS_SMOOTH_FACTOR = 0.6  # 平滑系数：smoothed = 0.4 * prev + 0.6 * current（越大响应越快）

# ================================================================
# 回调：嘴巴开合 (由 mouth.py 注入)
# ================================================================
on_mouth_update: Optional[Callable[[float], None]] = None

# 初始化 pygame 混音器 (仅 edge-tts 降级使用)
try:
    pygame.mixer.init()
    print("✅ 音频设备初始化成功 (pygame，降级备用)")
except Exception as e:
    print(f"⚠️ pygame 音频设备初始化失败: {e}")


def _speak_cosyvoice_pcm(text: str, api_key: str) -> bool:
    """CosyVoice2 PCM 流式合成 + pyaudio 实时播放 + RMS 驱动嘴巴

    真正的边收边播：HTTP 返回的每个 PCM chunk 直接送入 pyaudio 播放，
    同时计算音量 RMS 驱动 VTS 嘴巴动作。

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
        "response_format": "pcm",
        "sample_rate": PCM_SAMPLE_RATE,
        "stream": True,
    }

    pa = None
    stream = None

    try:
        # 发起流式 HTTP 请求
        response = requests.post(
            SILICONFLOW_API_URL,
            headers=headers,
            json=body,
            stream=True,
            timeout=30,
        )
        response.raise_for_status()

        # 初始化 pyaudio 输出流
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=PCM_FORMAT,
            channels=PCM_CHANNELS,
            rate=PCM_SAMPLE_RATE,
            output=True,
            frames_per_buffer=1024,
        )

        total_bytes = 0
        smoothed_rms = 0.0  # 平滑后的 RMS 值
        leftover = b""  # 缓冲：确保每次写入都是 2 字节对齐（16-bit PCM）

        # 边收边播
        for chunk in response.iter_content(chunk_size=PCM_CHUNK_SIZE):
            # 检查打断
            if _interrupted:
                logger.info("⏹️ [TTS] PCM 流式播放被打断")
                break

            if keyboard.is_pressed('right ctrl'):
                _interrupted = True
                print("⏹️ 语音被用户打断")
                break

            if not chunk:
                continue

            # 拼接上次剩余的字节，确保 2 字节对齐
            data = leftover + chunk
            usable = len(data) - (len(data) % 2)  # 截断到偶数
            leftover = data[usable:]               # 剩余存下次
            aligned = data[:usable]

            if not aligned:
                continue

            # 1. 实时播放
            stream.write(aligned)
            total_bytes += len(aligned)

            # 2. 计算 RMS 音量 → 驱动嘴巴
            if on_mouth_update:
                samples = np.frombuffer(aligned, dtype=np.int16)
                rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
                normalized = min(1.0, rms / RMS_MAX)
                # lerp 平滑
                smoothed_rms = (1 - RMS_SMOOTH_FACTOR) * smoothed_rms + RMS_SMOOTH_FACTOR * normalized
                on_mouth_update(smoothed_rms)

        if total_bytes == 0:
            logger.warning("🎭 [TTS] CosyVoice2 返回空音频")
            return False

        logger.info(f"✅ CosyVoice2 PCM 流式播放完成 ({total_bytes} bytes)")
        return True

    except requests.exceptions.RequestException as e:
        logger.warning(f"🎭 [TTS] CosyVoice2 请求失败: {e}")
        return False
    except Exception as e:
        logger.warning(f"🎭 [TTS] CosyVoice2 PCM 播放异常: {e}")
        return False
    finally:
        # 关闭 pyaudio 资源
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        if pa:
            try:
                pa.terminate()
            except Exception:
                pass
        # 播放结束，关闭嘴巴
        if on_mouth_update:
            on_mouth_update(0.0)


async def _generate_audio_edge_tts(text: str, voice: str = "zh-CN-XiaoyiNeural"):
    """降级方案：edge-tts 合成音频文件"""
    import edge_tts
    TEMP_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(TEMP_AUDIO))
    logger.info("✅ edge-tts 音频生成完成 (降级模式)")


def _play_with_pygame():
    """用 pygame 播放 mp3 文件 (edge-tts 降级路径)"""
    global _interrupted

    try:
        pygame.mixer.music.load(str(TEMP_AUDIO))
        pygame.mixer.music.play()

        # 嘴巴固定张开 (降级模式没有 RMS，用固定值)
        if on_mouth_update:
            on_mouth_update(0.8)

        while pygame.mixer.music.get_busy():
            if keyboard.is_pressed('right ctrl'):
                print("⏹️ 语音被用户打断")
                pygame.mixer.music.stop()
                _interrupted = True
                break
            time.sleep(0.05)

        # 释放资源
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            time.sleep(0.2)
        except Exception:
            pass

        # 清理临时文件
        try:
            if TEMP_AUDIO.exists():
                os.remove(TEMP_AUDIO)
        except Exception:
            pass

    except Exception as e:
        print(f"❌ pygame 播放失败: {e}")
    finally:
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        # 关闭嘴巴
        if on_mouth_update:
            on_mouth_update(0.0)


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
    """清理 Markdown 格式符号，避免 TTS 朗读星号、井号等"""
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
    except Exception:
        pass


def speak(text, voice="zh-CN-XiaoyiNeural"):
    """
    对外的主函数：合成并播放

    CosyVoice2 路径（主）：PCM 流式 → pyaudio 实时播放 → RMS 驱动嘴巴
    edge-tts 路径（降级）：mp3 文件 → pygame 播放 → 固定嘴巴 0.8
    """
    if not text:
        return

    text = _clean_markdown(text)
    if not text:
        return

    with _speak_lock:
        print(f"🔊 扶光: {text}")

        global _interrupted
        _interrupted = False

        # 优先尝试 CosyVoice2 PCM 流式播放
        api_key = ConfigManager.SILICONFLOW_API_KEY
        played = False

        if api_key:
            played = _speak_cosyvoice_pcm(text, api_key)
            if not played and not _interrupted:
                logger.info("🎭 [TTS] CosyVoice2 失败，降级到 edge-tts")

        # 降级：edge-tts + pygame
        if not played and not _interrupted:
            try:
                _run_async(_generate_audio_edge_tts(text, voice=voice))
                _play_with_pygame()
            except Exception as e:
                print(f"❌ 语音合成失败: {e}")


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("✅ 扶光语音系统测试 (CosyVoice2 PCM 流式)")
    print("=" * 60)
    speak("指挥官你好，我是扶光。现在我的嘴巴会跟着声音动了。")
    time.sleep(0.5)
    speak("这是第二句测试。")