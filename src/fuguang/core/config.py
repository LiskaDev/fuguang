
from pathlib import Path
import logging
from ..config import ConfigManager as GlobalConfig

logger = logging.getLogger("Fuguang")

class ConfigManager:
    """
    管家角色 - 统一管理所有配置
    职责：API Key、路径、IP/端口配置
    """

    def __init__(self):
        # 🔍 项目根目录（使用标记文件搜索法，更健壮）
        # 从当前文件向上搜索，直到找到包含 README.md 的目录
        self.PROJECT_ROOT = self._find_project_root()
        
        # 如果搜索失败，使用备用方法（parent^4）
        if self.PROJECT_ROOT is None:
            logger.warning("⚠️ 未找到项目根目录标记文件，使用备用路径计算")
            self.PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

        # 核心目录结构
        self.CONFIG_DIR = self.PROJECT_ROOT / "config"
        self.DATA_DIR = self.PROJECT_ROOT / "data"
        self.LOG_DIR = self.PROJECT_ROOT / "logs"
        self.GENERATED_DIR = self.PROJECT_ROOT / "generated"
        self.FACE_DB_DIR = self.DATA_DIR / "face_db"  # [新增] 人脸数据库目录

        # 确保目录存在
        for _dir in [self.CONFIG_DIR, self.DATA_DIR, self.LOG_DIR, self.GENERATED_DIR, self.FACE_DB_DIR]:
            _dir.mkdir(parents=True, exist_ok=True)

        # 桌面路径 (用于笔记)
        self.DESKTOP_PATH = Path.home() / "Desktop"
        if not self.DESKTOP_PATH.exists():
            self.DESKTOP_PATH = Path.home() / "桌面"
        if not self.DESKTOP_PATH.exists():
            self.DESKTOP_PATH = self.PROJECT_ROOT

        self.NOTES_DIR = self.DESKTOP_PATH

        # 核心文件路径
        self.SYSTEM_PROMPT_FILE = self.CONFIG_DIR / "system_prompt.txt"
        self.MEMORY_FILE = self.DATA_DIR / "memory.json"
        self.LONG_TERM_MEMORY_FILE = self.DATA_DIR / "long_term_memory.json"
        # [新增] 提醒事项存储文件
        self.REMINDERS_FILE = self.DATA_DIR / "reminders.json"

        # API 配置 (从全局配置读取)
        self.DEEPSEEK_API_KEY = GlobalConfig.DEEPSEEK_API_KEY
        self.DEEPSEEK_BASE_URL = GlobalConfig.DEEPSEEK_BASE_URL
        self.SERPER_API_KEY = GlobalConfig.SERPER_API_KEY
        self.ZHIPU_API_KEY = GlobalConfig.ZHIPU_API_KEY
        self.GITHUB_TOKEN = GlobalConfig.GITHUB_TOKEN
        self.OBSIDIAN_VAULT_PATH = GlobalConfig.OBSIDIAN_VAULT_PATH
        self.FIGMA_API_KEY = GlobalConfig.FIGMA_API_KEY
        self.EVERYTHING_PORT = GlobalConfig.EVERYTHING_PORT
        
        # 📧 邮件监控配置 (用户邮箱)
        self.EMAIL_QQ = GlobalConfig.EMAIL_QQ
        self.EMAIL_AUTH_CODE = GlobalConfig.EMAIL_AUTH_CODE
        self.EMAIL_CHECK_INTERVAL = GlobalConfig.EMAIL_CHECK_INTERVAL
        
        # 📧 扶光专属邮箱 (AI身份，可选)
        self.EMAIL_AI_QQ = GlobalConfig.EMAIL_AI_QQ
        self.EMAIL_AI_AUTH_CODE = GlobalConfig.EMAIL_AI_AUTH_CODE
        
        # 视觉识别配置
        self.VISION_USE_FLASH = GlobalConfig.VISION_USE_FLASH
        self.VISION_QUALITY = GlobalConfig.VISION_QUALITY
        self.VISION_MAX_SIZE = GlobalConfig.VISION_MAX_SIZE

        # Unity 通信配置
        self.UNITY_IP = GlobalConfig.UNITY_IP
        self.UNITY_PORT = GlobalConfig.UNITY_PORT
        self.UNITY_MCP_PORT = GlobalConfig.UNITY_MCP_PORT
        self.UNITY_MCP_PROJECT_PATH = GlobalConfig.UNITY_MCP_PROJECT_PATH
        
        # 摄像头配置
        self.CAMERA_ENABLED = GlobalConfig.CAMERA_ENABLED
        self.CAMERA_INDEX = GlobalConfig.CAMERA_INDEX
        self.GAZE_TRACKING_ENABLED = GlobalConfig.GAZE_TRACKING_ENABLED
        self.GAZE_TRACKING_FPS = GlobalConfig.GAZE_TRACKING_FPS
        self.IDENTITY_CHECK_INTERVAL = GlobalConfig.IDENTITY_CHECK_INTERVAL
        
        # 情感交互配置
        self.WELCOME_BACK_ENABLED = GlobalConfig.WELCOME_BACK_ENABLED
        self.WELCOME_BACK_TIMEOUT = GlobalConfig.WELCOME_BACK_TIMEOUT
        self.SHY_MODE_ENABLED = GlobalConfig.SHY_MODE_ENABLED
        self.SHY_STARE_DURATION = GlobalConfig.SHY_STARE_DURATION
        self.SHY_COOLDOWN = GlobalConfig.SHY_COOLDOWN
        
        # GUI 控制配置
        self.ENABLE_GUI_CONTROL = GlobalConfig.ENABLE_GUI_CONTROL
        self.GUI_CLICK_DELAY = GlobalConfig.GUI_CLICK_DELAY
        self.GUI_USE_GLM_FALLBACK = GlobalConfig.GUI_USE_GLM_FALLBACK
        
        # 心跳系统配置
        self.HEARTBEAT_IDLE_TIMEOUT = GlobalConfig.HEARTBEAT_IDLE_TIMEOUT
        
        # 📱 QQ 接入 (NapCat)
        self.QQ_ENABLED = GlobalConfig.QQ_ENABLED
        self.NAPCAT_WS_PORT = GlobalConfig.NAPCAT_WS_PORT
        self.ADMIN_QQ = GlobalConfig.ADMIN_QQ
        self.QQ_GROUP_MODE = GlobalConfig.QQ_GROUP_MODE
        
        # 🌐 Web UI (FastAPI + WebSocket)
        self.WEB_UI_ENABLED = GlobalConfig.WEB_UI_ENABLED
        self.WEB_UI_PORT = GlobalConfig.WEB_UI_PORT
        self.WEB_UI_PASSWORD = GlobalConfig.WEB_UI_PASSWORD
        self.WEB_UI_JWT_SECRET = GlobalConfig.WEB_UI_JWT_SECRET
        
        # 🎭 VTube Studio (Live2D 外观)
        self.VTS_ENABLED = GlobalConfig.VTS_ENABLED
        self.VTS_PORT = GlobalConfig.VTS_PORT
        
        # 🔍 验证关键文件是否存在
        self._validate_paths()
    
    def _find_project_root(self) -> Path:
        """
        使用标记文件搜索项目根目录
        搜索 README.md 或 .git 目录，更健壮且不依赖目录层级
        """
        current = Path(__file__).resolve()
        # 最多向上搜索 10 层
        for _ in range(10):
            # 检查标记文件
            if (current / "README.md").exists() or (current / ".git").exists():
                logger.debug(f"✅ 找到项目根目录: {current}")
                return current
            
            # 向上一层
            parent = current.parent
            if parent == current:  # 已到达文件系统根目录
                break
            current = parent
        
        logger.warning("⚠️ 未找到项目根目录 (README.md 或 .git)")
        return None
    
    def _validate_paths(self):
        """验证关键文件/目录是否存在"""
        if not self.SYSTEM_PROMPT_FILE.exists():
            logger.warning(f"⚠️ System Prompt 文件不存在: {self.SYSTEM_PROMPT_FILE}")
        if not self.CONFIG_DIR.exists():
            logger.warning(f"⚠️ 配置目录不存在: {self.CONFIG_DIR}")
        
        logger.info(f"✅ 项目根目录: {self.PROJECT_ROOT}")
