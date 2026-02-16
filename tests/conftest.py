"""
扶光测试 — 公共 Fixtures
提供 mock 对象，使测试可以脱离硬件（摄像头/麦克风/GPU）运行。
"""
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# 确保 src 在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@pytest.fixture
def mock_config():
    """模拟 ConfigManager，不依赖真实文件"""
    config = MagicMock()
    config.PROJECT_ROOT = PROJECT_ROOT
    config.CONFIG_DIR = PROJECT_ROOT / "config"
    config.DATA_DIR = PROJECT_ROOT / "data"
    config.LOG_DIR = PROJECT_ROOT / "logs"
    config.GENERATED_DIR = PROJECT_ROOT / "generated"
    config.FACE_DB_DIR = PROJECT_ROOT / "data" / "face_db"
    config.DESKTOP_PATH = Path.home() / "Desktop"
    config.NOTES_DIR = Path.home() / "Desktop"
    config.SYSTEM_PROMPT_FILE = PROJECT_ROOT / "config" / "system_prompt.txt"
    config.MEMORY_FILE = PROJECT_ROOT / "data" / "memory.json"
    config.LONG_TERM_MEMORY_FILE = PROJECT_ROOT / "data" / "long_term_memory.json"
    config.REMINDERS_FILE = PROJECT_ROOT / "data" / "reminders.json"
    config.DEEPSEEK_API_KEY = "test-key"
    config.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    config.SERPER_API_KEY = "test-serper"
    config.ZHIPU_API_KEY = "test-zhipu"
    config.CAMERA_ENABLED = False
    config.OBSIDIAN_VAULT_PATH = ""
    return config


@pytest.fixture
def mock_mouth():
    """模拟 Mouth（语音合成），不播放声音"""
    mouth = MagicMock()
    mouth.speak = MagicMock(return_value=None)
    mouth.send_to_unity = MagicMock(return_value=None)
    mouth.start_thinking = MagicMock(return_value=None)
    mouth.stop_thinking = MagicMock(return_value=None)
    return mouth


@pytest.fixture
def mock_brain(mock_config, mock_mouth):
    """模拟 Brain，不调用真实 API"""
    brain = MagicMock()
    brain.config = mock_config
    brain.mouth = mock_mouth
    brain.chat_history = []
    brain.IS_CREATION_MODE = False
    brain.performance_log = []
    brain.system_hints = []
    brain.memory_system = MagicMock()
    return brain
