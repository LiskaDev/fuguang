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

# 6. Config Manager (从环境变量读取)
class ConfigManager:
    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    # 阿里云
    ALI_ACCESS_KEY_ID = os.getenv("ALI_ACCESS_KEY_ID", "")
    ALI_ACCESS_KEY_SECRET = os.getenv("ALI_ACCESS_KEY_SECRET", "")
    ALI_APPKEY = os.getenv("ALI_APPKEY", "")
    ALI_REGION_ID = os.getenv("ALI_REGION_ID", "cn-shanghai")
    
    # Serper
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    
    # Unity
    UNITY_IP = os.getenv("UNITY_IP", "127.0.0.1")
    UNITY_PORT = int(os.getenv("UNITY_PORT", "5005"))

print(f"✅ [PathManager] Root: {PROJECT_ROOT}")
