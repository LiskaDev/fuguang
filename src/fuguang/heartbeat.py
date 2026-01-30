"""
扶光的心跳系统 (Subconscious System)
功能：管理生物钟、情绪状态、主动搭话
"""
import time
import threading
import random
import datetime
from . import voice as fuguang_voice  # 调用嘴巴

# ===========================
# 🧠 潜意识配置
# ===========================
# 上次互动时间戳
last_interaction_time = time.time()
is_running = True
# 🔥 静默模式：当用户正在操作时，禁止主动触发
silent_mode = False

# 闲聊文案库 (当她无聊时会说的话)
IDLE_THOUGHTS = [
    "指挥官，你盯着屏幕看了很久了，眼睛不酸吗？",
    "好安静啊，要不要我给你讲个冷笑话？",
    "刚才我在后台跑了一遍数据，发现今天的内存占用有点高呢。",
    "你在忙什么呢？我也想帮忙，虽然我只能帮你搜搜资料。",
    "指挥官？还在吗？我看不到你，有点心慌。",
    "突然想听歌了，你想听吗？",
    "如果你累了，可以把耳机摘下来休息一会儿。",
]

# 状态标记
current_mood = "normal"  # normal, happy, angry

def update_interaction(enable_silent=False):
    """每次你跟她说话，就调用这个，重置她的无聊计时器"""
    global last_interaction_time, silent_mode
    last_interaction_time = time.time()
    if enable_silent:
        silent_mode = True
    # print("💓 [心跳] 互动时间已更新")

def disable_silent_mode():
    """解除静默模式"""
    global silent_mode
    silent_mode = False

def get_time_segment():
    """判断当前时间段"""
    h = datetime.datetime.now().hour
    if 5 <= h < 9: return "morning"
    if 9 <= h < 12: return "forenoon"
    if 12 <= h < 14: return "noon"
    if 14 <= h < 18: return "afternoon"
    if 18 <= h < 23: return "evening"
    return "late_night"

def start_heartbeat():
    """启动心跳线程"""
    thread = threading.Thread(target=_life_cycle, daemon=True)
    thread.start()
    print("💓 [系统] 灵魂心跳已激活")

def _life_cycle():
    """生命的循环 (后台主逻辑)"""
    print("💓 扶光正在观察你的作息...")
    
    # 1. 启动时的问候 (根据时间段)
    time.sleep(1) # 等系统加载完
    seg = get_time_segment()
    if seg == "morning":
        fuguang_voice.speak("早安指挥官！新的一天开始了，今天要加油哦。")
    elif seg == "late_night":
        fuguang_voice.speak("指挥官，这么晚了还在唤醒我？要注意身体啊。")
    else:
        fuguang_voice.speak("系统上线成功。指挥官，随时待命。")

    # 2. 循环监测
    while is_running:
        now = time.time()
        idle_seconds = now - last_interaction_time
        
        # === 触发逻辑：无聊碎碎念 ===
        # 🔥 改成 20 分钟 (1200秒)
        if idle_seconds > 1200 and not silent_mode: 
            # 增加随机性，不要每次刚到20分钟就触发，而是每20分钟有 30% 概率触发
            if random.random() < 0.3:
                thought = random.choice(IDLE_THOUGHTS)
                print(f"💓 [主动触发] {thought}")
                fuguang_voice.speak(thought)
                
                # 说完之后，假装刚刚互动过，避免复读机
                update_interaction()
        
        # === 触发逻辑：深夜劝睡 ===
        # 如果到了凌晨 1 点，且刚才还在互动
        if datetime.datetime.now().hour == 1 and datetime.datetime.now().minute == 0 and not silent_mode:
             if idle_seconds < 1800: # 半小时内活跃过
                 fuguang_voice.speak("指挥官，一点了。强制休息指令... 开玩笑的，但真的该睡了。")
                 time.sleep(60) # 避免这一分钟内重复触发

        # 每 10 秒检查一次状态
        time.sleep(10)