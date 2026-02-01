import os
import sys
from pathlib import Path

# =====================================================
# 🛠️ PathManager (路径管理器)
# =====================================================
# 1. 获取项目根目录 (Project Root)
# Logic: config.py is in src/fuguang/ -> parent is src/ -> parent is Root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 2. 定义标准目录结构
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
GENERATED_DIR = PROJECT_ROOT / "generated"

# 3. 确保目录存在 (Auto-create)
for _dir in [CONFIG_DIR, DATA_DIR, LOG_DIR, SCRIPTS_DIR, GENERATED_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# 4. 定义核心文件路径
# 系统提示词 (System Prompt)
SYSTEM_PROMPT_FILE = CONFIG_DIR / "system_prompt.txt"

# 记忆数据库 (Memory)
MEMORY_FILE = DATA_DIR / "memory.json"
LONG_TERM_MEMORY_FILE = DATA_DIR / "long_term_memory.json"

# 桌面路径 (用于导出笔记)
DESKTOP_PATH = Path.home() / "Desktop"
print(f"✅ [PathManager] Desktop: {DESKTOP_PATH}")
NOTES_FILE = DESKTOP_PATH / "Fuguang_Notes.md"

# 5. Add project root to sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 5. Config Manager
class ConfigManager:
    # Hardcoded defaults (Lazy mode)
    DEEPSEEK_API_KEY = "***REDACTED_DEEPSEEK_KEY***"
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    
    ALI_ACCESS_KEY_ID = "***REDACTED_ALI_KEY_ID***"
    ALI_ACCESS_KEY_SECRET = "***REDACTED_ALI_KEY_SECRET***"
    ALI_APPKEY = "***REDACTED_ALI_APPKEY***"
    ALI_REGION_ID = "cn-shanghai"
    
    SERPER_API_KEY = "***REDACTED_SERPER_KEY***"
    
    UNITY_IP = "127.0.0.1"
    UNITY_PORT = 5005
    
    # 摄像头配置（人脸检测）
    CAMERA_ENABLED = True  # 是否启用摄像头检测用户是否在座
    CAMERA_INDEX = 0       # 摄像头索引，0 通常是默认摄像头
    GAZE_TRACKING_ENABLED = True  # 是否启用注视追踪（角色眼神跟随用户）
    GAZE_TRACKING_FPS = 10        # 注视追踪刷新率
    
    # 情感交互配置
    WELCOME_BACK_ENABLED = True   # 是否启用"回头杀"功能
    WELCOME_BACK_TIMEOUT = 300    # 回头杀：离开多久算"久"（秒），默认5分钟
    SHY_MODE_ENABLED = True       # 是否启用"害羞"功能
    SHY_STARE_DURATION = 10       # 害羞：盯着看多久触发（秒）
    SHY_COOLDOWN = 60             # 害羞：冷却时间（秒）
    
    # 心跳系统配置
    HEARTBEAT_IDLE_TIMEOUT = 1200  # 主动对话触发：空闲多久后触发（秒），默认20分钟

print(f"✅ [PathManager] Root: {PROJECT_ROOT}")
