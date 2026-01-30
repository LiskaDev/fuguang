
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
        # 项目根目录 (core/ -> fuguang/ -> src/ -> Root)
        self.PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

        # 核心目录结构
        self.CONFIG_DIR = self.PROJECT_ROOT / "config"
        self.DATA_DIR = self.PROJECT_ROOT / "data"
        self.LOG_DIR = self.PROJECT_ROOT / "logs"
        self.GENERATED_DIR = self.PROJECT_ROOT / "generated" 

        # 确保目录存在
        for _dir in [self.CONFIG_DIR, self.DATA_DIR, self.LOG_DIR, self.GENERATED_DIR]:
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
