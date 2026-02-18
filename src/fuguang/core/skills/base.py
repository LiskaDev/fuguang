"""
BaseSkillMixin — 技能系统的基础层
共享 __init__、常量、APP_REGISTRY、WEBSITE_REGISTRY
"""

import subprocess
import requests
import webbrowser
import time
import datetime
import psutil
import keyboard
import logging
import os
import json
import base64
import io
import sys
import numpy as np
from PIL import Image
import pyautogui
import pyaudio
import wave
import tempfile
import soundcard as sc
import soundfile as sf
from zhipuai import ZhipuAI

from ..config import ConfigManager
from ..mouth import Mouth
from ..brain import Brain
from ..memory import MemoryBank

logger = logging.getLogger("fuguang.skills")

# [视觉] 导入 OCR 引擎（优先 RapidOCR，回退 EasyOCR）
try:
    from rapidocr_onnxruntime import RapidOCR
    RAPIDOCR_AVAILABLE = True
except ImportError:
    RAPIDOCR_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

if not RAPIDOCR_AVAILABLE and not EASYOCR_AVAILABLE:
    logger.warning("⚠️ 无 OCR 引擎可用（需要 rapidocr-onnxruntime 或 easyocr）")

# [视觉] 导入 YOLO-World（零样本识别）
try:
    from ultralytics import YOLOWorld
    YOLOWORLD_AVAILABLE = True
except ImportError:
    YOLOWORLD_AVAILABLE = False
    logger.warning("⚠️ Ultralytics 未安装，YOLO-World 视觉识别功能将受限")

# [听觉] 导入 Whisper（语音转文字）
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError as e:
    WHISPER_AVAILABLE = False
    # [改进] 显示详细错误信息，帮助快速定位依赖冲突
    error_msg = str(e)
    if "Numba" in error_msg or "NumPy" in error_msg:
        logger.warning(f"⚠️ Whisper 导入失败（依赖冲突）: {error_msg}")
        logger.warning("💡 尝试修复: pip install 'numpy<2.4,>=2.0'")
    else:
        logger.warning(f"⚠️ Whisper 未安装: {error_msg}")
        logger.warning("💡 安装命令: pip install openai-whisper")

# [浏览器] 导入 Playwright
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("⚠️ Playwright 未安装，深度浏览功能将受限")

# [视觉] 导入 PyGetWindow
try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False

# [GUI] 导入 pywinauto (Windows UI Automation)
try:
    import pywinauto
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False
    logger.warning("⚠️ pywinauto 未安装，UIA 控件操作功能将受限")

# [浏览器] 导入 CyberGhost
try:
    from ..browser import CyberGhost
    CYBERGHOST_AVAILABLE = True
except ImportError:
    CYBERGHOST_AVAILABLE = False

# [知识库] 导入知识吞噬器
try:
    from ..ingest import KnowledgeEater
    EATER_AVAILABLE = True
except ImportError:
    EATER_AVAILABLE = False


class BaseSkillMixin:
    """
    基础 Mixin — 保存所有共享属性和初始化逻辑
    """

    # 🚀 软件启动注册表
    APP_REGISTRY = {
        "记事本": {"aliases": ["记事本", "notepad", "文本编辑"], "cmd": "notepad"},
        "计算器": {"aliases": ["计算器", "计算", "calc"], "cmd": "calc"},
        "画图": {"aliases": ["画图", "画画", "paint"], "cmd": "mspaint"},
        "任务管理器": {"aliases": ["任务管理器", "进程", "taskmgr"], "cmd": "taskmgr"},
        "控制面板": {"aliases": ["控制面板", "control"], "cmd": "control"},
        "文件管理器": {"aliases": ["文件管理器", "资源管理器", "explorer"], "cmd": "explorer"},
        "命令行": {"aliases": ["命令行", "cmd", "终端"], "cmd": "cmd"},
        "设置": {"aliases": ["设置", "系统设置"], "cmd": "ms-settings:"},
        "浏览器": {"aliases": ["浏览器", "上网", "edge"], "cmd": "start msedge"},
        "微信": {"aliases": ["微信", "wechat"], "cmd": "start WeChat"},
        "QQ": {"aliases": ["qq", "扣扣"], "cmd": "start QQ"},
        "VSCode": {"aliases": ["vscode", "代码编辑器", "code"], "cmd": "code"},
        "Steam": {"aliases": ["steam", "游戏"], "cmd": "start steam://open/games"},
    }

    # 网站注册表
    WEBSITE_REGISTRY = {
        "淘宝": "https://www.taobao.com",
        "京东": "https://www.jd.com",
        "B站": "https://www.bilibili.com",
        "知乎": "https://www.zhihu.com",
        "微博": "https://weibo.com",
        "抖音": "https://www.douyin.com",
        "小红书": "https://www.xiaohongshu.com",
        "百度": "https://www.baidu.com",
        "GitHub": "https://github.com",
        "网易云": "https://music.163.com",
        "Steam": "https://store.steampowered.com",
        "Epic": "https://www.epicgames.com/store/zh-CN",
    }

    def __init__(self, config: ConfigManager, mouth: Mouth, brain: Brain):
        self.config = config
        self.mouth = mouth
        self.brain = brain
        self.reminders = self._load_reminders_from_disk()
        
        # [自主模式] 是否自动执行 Shell/代码，无需人工确认
        # 用户可以通过语音"你自己解决"/"不用问我了"开启，重启后重置
        self.auto_execute = False
        
        # [视觉] 初始化智谱客户端
        if hasattr(config, 'ZHIPU_API_KEY') and config.ZHIPU_API_KEY:
            self.vision_client = ZhipuAI(api_key=config.ZHIPU_API_KEY)
            model_name = "GLM-4V-Flash (极速)" if config.VISION_USE_FLASH else "GLM-4V (标准)"
            logger.info(f"✅ 智谱AI 视觉模块已就绪 [{model_name}]")
        else:
            self.vision_client = None
            logger.warning("⚠️ 未配置 ZHIPU_API_KEY，视觉功能将无法使用")
        
        # [视觉] 缓存机制（避免重复截图）
        self._last_screenshot_hash = None
        self._last_screenshot_result = None
        
        # [视觉] 历史记录（最近 5 次分析）
        self._vision_history = []  # 列表格式: [{"timestamp", "question", "result", "image_path"}]
        self._vision_history_dir = self.config.PROJECT_ROOT / "data" / "vision_history"
        self._vision_history_dir.mkdir(exist_ok=True)
        
        # [视觉] 初始化 YOLO-World 模型（零样本目标检测）
        if YOLOWORLD_AVAILABLE:
            try:
                logger.info("🚀 正在加载 YOLO-World 模型（首次运行需下载 ~200MB）...")
                import torch
                self.yolo_world = YOLOWorld('yolov8s-worldv2.pt')  # 使用 small 版本，速度快
                # 确保所有模型组件在同一设备上（优先使用CPU避免设备冲突）
                device = 'cpu'  # 统一使用CPU，避免cuda/cpu混用导致的错误
                self.yolo_world.to(device)
                logger.info(f"✅ YOLO-World 视觉识别已就绪（零样本目标检测，设备: {device}）")
            except Exception as e:
                self.yolo_world = None
                logger.error(f"❌ YOLO-World 加载失败: {e}")
        else:
            self.yolo_world = None
            logger.warning("⚠️ YOLO-World 未安装，图标识别功能将受限")
            
        # [视觉] 初始化 OCR (优先 RapidOCR，回退 EasyOCR)
        self._ocr_engine = None  # 'rapid' | 'easy'
        self._ocr_reader = None
        if RAPIDOCR_AVAILABLE:
            try:
                self._ocr_reader = RapidOCR()
                self._ocr_engine = 'rapid'
                logger.info("✅ RapidOCR 中文文字识别已就绪（ONNX 推理）")
            except Exception as e:
                logger.error(f"❌ RapidOCR 加载失败: {e}")
                self._ocr_reader = None
        
        if self._ocr_reader is None and EASYOCR_AVAILABLE:
            try:
                logger.info("📖 正在加载 EasyOCR 模型 (首次运行需下载)...")
                import easyocr
                self._ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
                self._ocr_engine = 'easy'
                logger.info("✅ EasyOCR 文字识别已就绪（回退引擎）")
            except Exception as e:
                logger.error(f"❌ EasyOCR 加载失败: {e}")
                self._ocr_reader = None
        
        # [听觉] Whisper 模型（懒加载，首次使用时才加载）
        self.whisper_model = None
        
        # [记忆] 向量数据库长期记忆 (海马体)
        # 优先复用 Brain 的 MemoryBank 实例（避免双实例浪费内存）
        try:
            if hasattr(self.brain, 'memory_system') and self.brain.memory_system:
                self.memory = self.brain.memory_system
                logger.info("✅ 长期记忆系统已就绪（共享 Brain 实例）")
            else:
                self.memory = MemoryBank(
                    persist_dir=str(self.config.PROJECT_ROOT / "data" / "memory_db"),
                    obsidian_vault_path=getattr(self.config, 'OBSIDIAN_VAULT_PATH', '')
                )
                logger.info("✅ 长期记忆系统已就绪（独立实例）")
        except Exception as e:
            self.memory = None
            logger.error(f"❌ 长期记忆系统加载失败: {e}")
        
        # [知识库] 初始化知识吞噬器
        if self.memory and EATER_AVAILABLE:
            self.eater = KnowledgeEater(self.memory)
            logger.info("✅ 知识吞噬系统已就绪")
        else:
            self.eater = None
        
        # [浏览器] 赛博幽灵 - Playwright 深度浏览
        if CYBERGHOST_AVAILABLE:
            try:
                self.ghost = CyberGhost(
                    headless=True,
                    screenshot_dir=str(self.config.PROJECT_ROOT / "data" / "screenshots")
                )
                logger.info("✅ 赛博幽灵已就绪")
            except Exception as e:
                logger.warning(f"⚠️ CyberGhost 初始化失败: {e}")
                self.ghost = None
        else:
            self.ghost = None

        # [性能优化] 浏览器实例复用（避免每次启动新浏览器）
        self._browser = None
        self._browser_page = None
        self._playwright = None
        logger.info("⚡ 浏览器复用机制已启用")
        
        # [🧩 MCP] 初始化外部工具服务器
        if hasattr(self, '_init_mcp'):
            try:
                self._init_mcp()
            except Exception as e:
                logger.warning(f"⚠️ [MCP] 初始化失败（不影响核心功能）: {e}")
        
        # [📧 邮件] 初始化邮件监控后台线程
        if hasattr(self, '_init_email_monitor'):
            try:
                self._init_email_monitor()
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 初始化失败（不影响核心功能）: {e}")
    
    # ------ 内部辅助方法 ------
    
    def _load_reminders_from_disk(self):
        if not self.config.REMINDERS_FILE.exists():
            return []
        try:
            with open(self.config.REMINDERS_FILE, 'r', encoding='utf-8') as f:
                logger.info("⏰ [Core] 已加载历史提醒")
                return json.load(f)
        except Exception as e:
            logger.error(f"加载提醒失败: {e}")
            return []

    def _save_reminders_to_disk(self):
        try:
            with open(self.config.REMINDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存提醒失败: {e}")

    def _show_toast(self, title: str, message: str):
        """发送 Windows 系统通知 [修复M-6] 防止 PowerShell 注入"""
        try:
            import re
            # [修复] 更彻底的 PowerShell 注入防护：只保留安全字符
            def sanitize_ps(text: str) -> str:
                # 移除所有 PowerShell 特殊字符：' ` $ ( ) { } ; | & < > \
                cleaned = re.sub(r'''['"`$(){};&|<>\\]''', '', text)
                return cleaned[:200]  # 限制长度防止溢出
            
            safe_title = sanitize_ps(title)
            safe_message = sanitize_ps(message)
            
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.BalloonTipTitle = '{safe_title}'
            $notify.BalloonTipText = '{safe_message}'
            $notify.Visible = $True
            $notify.ShowBalloonTip(10000)
            """
            cmd = ["powershell", "-Command", ps_script]
            subprocess.Popen(cmd) 
        except Exception as e:
            logger.error(f"弹窗失败: {e}")
