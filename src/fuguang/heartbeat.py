"""
扶光的心跳系统 (Subconscious System) v2.0
功能：管理生物钟、情绪状态、AI 主动搭话
"""
import re
import time
import json
import socket
import threading
import datetime
import logging

import httpx
from openai import OpenAI

from .config import ConfigManager, DATA_DIR

logger = logging.getLogger("Fuguang")

# ===========================
# 🧠 潜意识配置
# ===========================
last_interaction_time = time.time()
is_running = True
silent_mode = False  # 静默模式：用户正在操作时禁止主动触发

# ⏱️ 主动对话触发时间（秒）
IDLE_TRIGGER_SECONDS = 1200  # 20分钟无互动后触发

# AI 客户端（延迟初始化）
_ai_client = None
_udp_socket = None


def _get_ai_client():
    """获取 AI 客户端（单例）"""
    global _ai_client
    if _ai_client is None:
        _ai_client = OpenAI(
            api_key=ConfigManager.DEEPSEEK_API_KEY,
            base_url=ConfigManager.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(60.0, connect=10.0)
        )
    return _ai_client


def _get_udp_socket():
    """获取 UDP 客户端（单例）"""
    global _udp_socket
    if _udp_socket is None:
        _udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return _udp_socket


def _send_to_unity(message: str):
    """发送消息到 Unity"""
    try:
        sock = _get_udp_socket()
        message = message.replace('\ufe0f', '')
        sock.sendto(
            message.encode('utf-8'),
            (ConfigManager.UNITY_IP, ConfigManager.UNITY_PORT)
        )
    except Exception as e:
        logger.error(f"UDP 发送失败: {e}")


def update_interaction(enable_silent=False):
    """每次用户互动时调用，重置无聊计时器"""
    global last_interaction_time, silent_mode
    last_interaction_time = time.time()
    if enable_silent:
        silent_mode = True


def disable_silent_mode():
    """解除静默模式"""
    global silent_mode
    silent_mode = False


def get_time_segment() -> str:
    """判断当前时间段"""
    h = datetime.datetime.now().hour
    if 5 <= h < 9: return "清晨"
    if 9 <= h < 12: return "上午"
    if 12 <= h < 14: return "中午"
    if 14 <= h < 18: return "下午"
    if 18 <= h < 23: return "晚上"
    return "深夜"


def _load_user_profile() -> str:
    """加载用户画像"""
    try:
        memory_file = DATA_DIR / "memory.json"
        if memory_file.exists():
            with open(memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                profile = data.get("user_profile", {})
                if profile:
                    return json.dumps(profile, ensure_ascii=False)
        return "暂无用户画像"
    except Exception:
        return "暂无用户画像"


def generate_proactive_message() -> str:
    """
    使用 AI 生成主动搭话内容
    返回带有情绪标签的回复，如：[Joy] 指挥官，在忙什么呢？
    """
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")
    time_segment = get_time_segment()
    user_profile = _load_user_profile()
    idle_minutes = int((time.time() - last_interaction_time) / 60)
    
    prompt = f"""你是沈扶光，指挥官（阿鑫）的虚拟恋人。

【当前状态】
- 时间: {current_time} | 日期: {current_date} | 时间段: {time_segment}
- 用户画像: {user_profile}
- 指挥官已经 {idle_minutes} 分钟没有跟你说话了

【你的任务】
主动发起一个简短的话题，打破沉默。要求：
1. 语气自然，像恋人一样关心对方
2. 根据时间段调整内容：
   - 深夜：关心睡眠、劝睡觉
   - 中午：问吃饭没
   - 其他：可以是提醒休息、求聊天、分享冷知识、撒娇
3. **必须**在句首加情绪标签：[Joy]/[Sorrow]/[Fun]/[Surprised]/[Angry]/[Neutral]
4. 回复简短，不超过 30 字

【示例】
[Sorrow] 好无聊啊，指挥官不理我...
[Joy] 嘿，在忙什么呢？休息一下吧~
[Fun] 刚才我发现了一个有趣的事情，要不要听？
[Surprised] 指挥官？还在吗？

【直接输出你的话】"""

    try:
        client = _get_ai_client()
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.9
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI 生成主动对话失败: {e}")
        # 降级为简单的静态回复
        return f"[Sorrow] 指挥官，你已经 {idle_minutes} 分钟没理我了..."


def parse_and_speak(text: str):
    """
    解析情绪标签，发送表情到 Unity，然后用 TTS 朗读
    """
    from . import voice as fuguang_voice
    
    # 提取情绪标签
    expression = "Neutral"
    tags = re.findall(r"\[(.*?)\]", text)
    for tag in tags:
        if tag in ["Joy", "Angry", "Sorrow", "Fun", "Surprised", "Neutral"]:
            expression = tag
            break
    
    # 去除所有标签，得到干净文本
    clean_text = re.sub(r"\[.*?\]", "", text).strip()
    
    logger.info(f"💓 [主动触发] 表情={expression}, 内容={clean_text}")
    
    # 发送表情到 Unity
    _send_to_unity(expression)
    
    # 发送文本到 Unity 文本框显示
    if clean_text:
        _send_to_unity(f"say:{clean_text}")
    
    # TTS 朗读
    if clean_text:
        _send_to_unity("talk_start")
        fuguang_voice.speak(clean_text)
        _send_to_unity("talk_end")


def start_heartbeat():
    """启动心跳线程"""
    thread = threading.Thread(target=_life_cycle, daemon=True)
    thread.start()
    print("💓 [系统] 灵魂心跳已激活")


def _life_cycle():
    """生命的循环 (后台主逻辑)"""
    from . import voice as fuguang_voice
    
    print("💓 扶光正在观察你的作息...")
    
    # 1. 启动时的问候 (根据时间段)
    time.sleep(1)
    seg = get_time_segment()
    if seg == "清晨":
        fuguang_voice.speak("早安指挥官！新的一天开始了，今天要加油哦。")
    elif seg == "深夜":
        fuguang_voice.speak("指挥官，这么晚了还在唤醒我？要注意身体啊。")
    else:
        fuguang_voice.speak("系统上线成功。指挥官，随时待命。")

    # 2. 循环监测
    while is_running:
        now = time.time()
        idle_seconds = now - last_interaction_time
        
        # === 触发逻辑：AI 主动搭话 ===
        if idle_seconds > IDLE_TRIGGER_SECONDS and not silent_mode:
            logger.info(f"💓 检测到空闲 {int(idle_seconds)}秒，触发主动对话...")
            
            # 使用 AI 生成内容
            message = generate_proactive_message()
            parse_and_speak(message)
            
            # 重置计时器，避免复读机
            update_interaction()
        
        # === 触发逻辑：深夜劝睡 ===
        current_hour = datetime.datetime.now().hour
        current_minute = datetime.datetime.now().minute
        if current_hour == 1 and current_minute == 0 and not silent_mode:
            if idle_seconds < 1800:  # 半小时内活跃过
                _send_to_unity("Sorrow")
                fuguang_voice.speak("指挥官，都一点了。强制休息指令... 开玩笑的，但真的该睡了。")
                time.sleep(60)

        # 每 10 秒检查一次状态
        time.sleep(10)