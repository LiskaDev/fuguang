
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
        # 项目根目录 (core/ -> fuguang/ -> src/ -> fuguang项目根)
        # __file__ = src/fuguang/core/config.py
        # parent = core/, parent.parent = fuguang/, parent.parent.parent = src/, parent^4 = fuguang项目根
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

        # Unity 通信配置
        self.UNITY_IP = GlobalConfig.UNITY_IP
        self.UNITY_PORT = GlobalConfig.UNITY_PORT
        
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
        
        # 心跳系统配置
        self.HEARTBEAT_IDLE_TIMEOUT = GlobalConfig.HEARTBEAT_IDLE_TIMEOUT
