import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# =====================================================
# 🛠️ PathManager (路径管理器)
# =====================================================
# 1. 获取项目根目录 (Project Root)
# Logic: config.py is in src/fuguang/ -> parent is src/ -> parent is Root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 加载 .env 文件
load_dotenv(PROJECT_ROOT / ".env")

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

# 6. Config Manager (从 .env 读取 API 密钥)
class ConfigManager:
    # === API 密钥（从 .env 读取）===
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    ALI_ACCESS_KEY_ID = os.getenv("ALI_ACCESS_KEY_ID", "")
    ALI_ACCESS_KEY_SECRET = os.getenv("ALI_ACCESS_KEY_SECRET", "")
    ALI_APPKEY = os.getenv("ALI_APPKEY", "")
    ALI_REGION_ID = os.getenv("ALI_REGION_ID", "cn-shanghai")
    
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    
    # === [新增] 智谱 API Key ===
    ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "***REDACTED_ZHIPU_KEY***")
    
    # 视觉识别配置
    VISION_USE_FLASH = False  # True=极速模式(glm-4v-flash, 2秒), False=标准模式(glm-4v, 4秒)
    VISION_QUALITY = 85       # 图片压缩质量 (60-95，越高越清晰但越慢)
    VISION_MAX_SIZE = 1280    # 图片最大边长 (768-2048，越大越清晰但越慢)

    UNITY_IP = os.getenv("UNITY_IP", "127.0.0.1")
    UNITY_PORT = int(os.getenv("UNITY_PORT", "5005"))
    
    # 摄像头配置（人脸检测）
    CAMERA_ENABLED = True  # 是否启用摄像头检测用户是否在座
    CAMERA_INDEX = 0       # 摄像头索引，0 通常是默认摄像头
    GAZE_TRACKING_ENABLED = True  # 是否启用注视追踪（角色眼神跟随用户）
    GAZE_TRACKING_FPS = 10        # 注视追踪刷新率 (建议 5-30，越高越丝滑但越耗CPU)
    IDENTITY_CHECK_INTERVAL = 2.0 # 身份识别间隔（秒），建议 2-10，越短响应越快但越耗CPU
    
    # 情感交互配置
    WELCOME_BACK_ENABLED = True   # 是否启用"回头杀"功能
    WELCOME_BACK_TIMEOUT = 600    # 回头杀：离开多久算"久"（秒），默认5分钟
    SHY_MODE_ENABLED = True       # 是否启用"害羞"功能
    SHY_STARE_DURATION = 30       # 害羞：盯着看多久触发（秒）
    SHY_COOLDOWN = 60             # 害羞：冷却时间（秒）
    
    # GUI 控制功能（智能鼠标点击）
    ENABLE_GUI_CONTROL = True     # 是否启用 GUI 自动化功能（点击屏幕文字、输入文本）
    GUI_CLICK_DELAY = 0.5         # 鼠标移动延迟（秒，模拟人类行为）
    GUI_USE_GLM_FALLBACK = True   # 当 OCR 找不到文字时，是否使用 GLM-4V 辅助定位
    
    # 心跳系统配置
    HEARTBEAT_IDLE_TIMEOUT = 1200  # 主动对话触发：空闲多久后触发（秒），默认20分钟

print(f"✅ [PathManager] Root: {PROJECT_ROOT}")
