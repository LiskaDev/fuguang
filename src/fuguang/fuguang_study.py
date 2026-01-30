"""
浮光 Study - AI 学习助手 (改进版 v0.5)

基于 ide.py v1.1 的优秀设计改进
改进要点：
1. 更完善的错误处理和日志系统
2. 优化的语音识别流程和唤醒逻辑
3. 增强的工具系统和 Function Calling
4. 更清晰的代码结构和注释
5. 更好的状态管理和超时控制

作者：ALan
改进日期：2026-01
"""

import os
import re
import sys
import json
import time
import socket
import struct
import logging
import warnings
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

import httpx
import keyboard
import requests
import speech_recognition as sr
from pypinyin import lazy_pinyin
from openai import OpenAI

# ═══════════════════════════════════════════════════════════════════════════════
#                              项目内部模块导入
# ═══════════════════════════════════════════════════════════════════════════════
from . import memory as fuguang_memory
from . import voice as fuguang_voice
from . import heartbeat as fuguang_heartbeat
from . import ali_ear as ali_ear
from .config import ConfigManager as GlobalConfig

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════════════════════════
#                              日志系统配置
# ═══════════════════════════════════════════════════════════════════════════════
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'fuguang_study.log', encoding='utf-8', mode='a')
    ]
)
logger = logging.getLogger("FuguangStudy")


# ═══════════════════════════════════════════════════════════════════════════════
#                              配置管理器 (ConfigManager)
# ═══════════════════════════════════════════════════════════════════════════════
class ConfigManager:
    """
    集中管理所有配置项：
    - 项目路径、资源目录
    - API 密钥和端点
    - Unity 通信参数
    - 唤醒词列表
    """
    
    # 项目根目录
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    
    # 核心目录结构
    CONFIG_DIR = PROJECT_ROOT / "config"
    DATA_DIR = PROJECT_ROOT / "data"
    LOG_DIR = PROJECT_ROOT / "logs"
    GENERATED_DIR = PROJECT_ROOT / "generated"
    
    # 桌面路径 (用于笔记)
    DESKTOP_PATH = Path.home() / "Desktop"
    if not DESKTOP_PATH.exists():
        DESKTOP_PATH = Path.home() / "桌面"
    if not DESKTOP_PATH.exists():
        DESKTOP_PATH = PROJECT_ROOT
    NOTES_DIR = DESKTOP_PATH
    
    # 核心文件路径
    SYSTEM_PROMPT_FILE = CONFIG_DIR / "system_prompt.txt"
    MEMORY_FILE = DATA_DIR / "memory.json"
    LONG_TERM_MEMORY_FILE = DATA_DIR / "long_term_memory.json"
    NOTES_FILE = DATA_DIR / "notes.json"
    # [新增] 提醒事项存储文件
    REMINDERS_FILE = DATA_DIR / "reminders.json"
    
    # API 配置
    DEEPSEEK_API_KEY = GlobalConfig.DEEPSEEK_API_KEY
    DEEPSEEK_BASE_URL = GlobalConfig.DEEPSEEK_BASE_URL
    DEEPSEEK_MODEL = "deepseek-chat"
    
    # Unity UDP 配置
    UNITY_IP = GlobalConfig.UNITY_IP
    UNITY_PORT = GlobalConfig.UNITY_PORT
    
    # 唤醒词配置
    WAKE_WORDS = ["扶光", "浮光", "小光", "阿光", "光光"]
    VOICE_WAKE_DURATION = 30  # 语音唤醒持续时间(秒)
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        for directory in [cls.CONFIG_DIR, cls.DATA_DIR, cls.LOG_DIR, 
                         cls.GENERATED_DIR, cls.NOTES_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 项目根目录: {cls.PROJECT_ROOT}")
        logger.info(f"📁 代码生成目录: {cls.GENERATED_DIR}")
        logger.info(f"📁 笔记目录: {cls.NOTES_DIR}")


# ═══════════════════════════════════════════════════════════════════════════════
#                              嘴巴 (Mouth) - 语音输出与 Unity 通信
# ═══════════════════════════════════════════════════════════════════════════════
class Mouth:
    """
    负责所有输出功能：
    - TTS 语音合成与播放
    - Unity 角色控制通信
    - 表情/动作指令发送
    """
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    def send_to_unity(self, message: str):
        """发送消息到 Unity"""
        try:
            message = message.replace('\ufe0f', '')  # 移除 emoji 变体选择器
            self.udp_socket.sendto(
                message.encode('utf-8'),
                (self.config.UNITY_IP, self.config.UNITY_PORT)
            )
        except Exception as e:
            logger.error(f"UDP 发送失败: {e}")
    
    def speak(self, text: str, voice: str = "zh-CN-XiaoyiNeural"):
        """
        使用 TTS 引擎朗读文本
        
        Args:
            text: 要朗读的文本
            voice: 语音角色
        """
        if not text or not text.strip():
            return
        
        # [修复] 如果用户已打断，跳过后续所有语音
        if fuguang_voice.was_interrupted():
            logger.info(f"⏭️ 跳过语音（已被打断）: {text[:20]}...")
            return
        
        fuguang_heartbeat.update_interaction()
        self.send_to_unity(f"say:{text}")
        
        try:
            self.send_to_unity("talk_start")
            fuguang_voice.speak(text, voice=voice)
            self.send_to_unity("talk_end")
        except Exception as e:
            logger.error(f"语音播放失败: {e}")
            self.send_to_unity("talk_end")
    
    def clear_interrupt(self):
        """清除打断状态（在新对话开始时调用）"""
        fuguang_voice.clear_interrupt()
    
    def speak_thinking(self):
        """播放思考提示音"""
        self.speak("让我想想...")

    def start_thinking(self):
        """发送开始思考指令"""
        self.send_to_unity("think_start")

    def stop_thinking(self):
        """发送停止思考指令"""
        self.send_to_unity("think_end")

    def wave(self):
        """发送挥手指令"""
        self.send_to_unity("wave")


# ═══════════════════════════════════════════════════════════════════════════════
#                              耳朵 (Ears) - 语音识别与唤醒检测
# ═══════════════════════════════════════════════════════════════════════════════
class Ears:
    """
    负责所有输入功能：
    - 麦克风音频采集
    - 语音识别 (ASR)
    - 唤醒词检测
    """
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 3000
        self.recognizer.dynamic_energy_threshold = True
    
    def check_wake_word_pinyin(self, text: str) -> tuple:
        """
        基于拼音的唤醒词检测
        
        Args:
            text: 识别到的文本
            
        Returns:
            (是否包含唤醒词, 匹配的唤醒词, 去除唤醒词后的文本)
        """
        if not text:
            return False, "", ""
        
        user_pinyin = lazy_pinyin(text)
        
        for word in self.config.WAKE_WORDS:
            word_pinyin = lazy_pinyin(word)
            n = len(word_pinyin)
            for i in range(len(user_pinyin) - n + 1):
                if user_pinyin[i:i + n] == word_pinyin:
                    clean_text = text[len(word):].strip()
                    clean_text = clean_text.lstrip("，。！？、")
                    return True, word, clean_text
        
        return False, "", text
    
    def listen_ali(self, audio_data: bytes) -> str:
        """
        使用阿里云 ASR 进行语音识别
        
        Args:
            audio_data: 音频数据
            
        Returns:
            识别到的文本
        """
        try:
            return ali_ear.listen_ali(audio_data)
        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ""
    
    def get_microphone(self, sample_rate: int = 16000):
        """获取麦克风上下文"""
        return sr.Microphone(sample_rate=sample_rate)


# ═══════════════════════════════════════════════════════════════════════════════
#                              大脑 (Brain) - AI 推理与记忆管理
# ═══════════════════════════════════════════════════════════════════════════════
class Brain:
    """
    核心智能模块：
    - 对话历史管理
    - 长短期记忆
    - AI 推理调用
    - 系统提示词管理
    """
    
    MAX_HISTORY = 20  # 最大历史对话轮次
    QUICK_LOCAL_TRIGGERS = ["几点", "时间", "几号", "日期", "电量", "状态"]
    
    def __init__(self, config: ConfigManager, mouth: Mouth):
        self.config = config
        self.mouth = mouth
        
        # AI 客户端
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0)
        )
        
        # 长期记忆系统
        self.memory_system = fuguang_memory.MemorySystem()
        
        # 对话历史 (确保启动时为空)
        self.chat_history = []
        
        # 状态
        self.is_creation_mode = False
    
    def load_memory(self) -> dict:
        """加载短期记忆"""
        if not self.config.MEMORY_FILE.exists():
            return {"user_profile": {}, "short_term_summary": "暂无记录"}
        try:
            with open(self.config.MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"记忆加载失败: {e}")
            return {"user_profile": {}, "short_term_summary": "文件损坏"}
    
    def save_memory(self, memory_data: dict):
        """保存短期记忆"""
        try:
            with open(self.config.MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=4)
            logger.info("💾 记忆已保存")
        except Exception as e:
            logger.error(f"记忆保存失败: {e}")
    
    def get_system_prompt(self) -> str:
        """
        生成动态 System Prompt
        
        Returns:
            包含记忆和人设的系统提示词
        """
        current_time = datetime.now().strftime("%H:%M")
        current_date = datetime.now().strftime("%Y-%m-%d")
        mode_status = "🔓已解锁" if self.is_creation_mode else "🔒已锁定"
        
        memory = self.load_memory()
        user_profile = json.dumps(memory.get("user_profile", {}), ensure_ascii=False)
        summary = memory.get("short_term_summary", "暂无")
        
        try:
            with open(self.config.SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                template = f.read()
            prompt = template.format(
                current_time=current_time,
                current_date=current_date,
                mode_status=mode_status,
                history_summary=f"【用户档案】{user_profile}\n【上次话题摘要】{summary}"
            )
            return prompt
        except Exception as e:
            logger.warning(f"系统提示词加载失败: {e}")
            return "你是浮光，一个友好的AI助手。[Neutral]"
    
    def trim_history(self):
        """修剪对话历史，防止过长"""
        if len(self.chat_history) <= self.MAX_HISTORY * 2:
            return
        
        target_len = self.MAX_HISTORY * 2 - 10
        for i in range(len(self.chat_history) - target_len, len(self.chat_history)):
            if i >= 0 and self.chat_history[i]["role"] == "user":
                self.chat_history = self.chat_history[i:]
                return
        
        self.chat_history = self.chat_history[-(self.MAX_HISTORY * 2):]
    
    def should_auto_respond(self, text: str) -> bool:
        """判断是否应该自动响应本地指令"""
        return any(trigger in text for trigger in self.QUICK_LOCAL_TRIGGERS)
    
    def remember(self, content: str, importance: int = 3):
        """记住信息到长期记忆"""
        self.memory_system.add_memory(content, importance)
    
    def recall(self, query: str) -> list:
        """从长期记忆中检索相关信息"""
        return self.memory_system.search_memory(query)
    
    def summarize_and_exit(self):
        """整理记忆并退出"""
        logger.info("正在整理今日记忆...")
        self.mouth.speak("正在同步记忆数据...")
        
        if len(self.chat_history) < 2:
            self.mouth.speak("晚安。")
            os._exit(0)
        
        # 构建对话文本
        conversation_text = ""
        for msg in self.chat_history:
            role = "用户" if msg["role"] == "user" else "浮光"
            conversation_text += f"{role}: {msg['content']}\n"
        
        try:
            summary_prompt = [
                {"role": "system", "content": "请简要总结以下对话中的关键信息。100字以内。"},
                {"role": "user", "content": conversation_text}
            ]
            response = self.client.chat.completions.create(
                model=self.config.DEEPSEEK_MODEL,
                messages=summary_prompt,
                max_tokens=200,
                temperature=0.5
            )
            new_summary = response.choices[0].message.content
            logger.info(f"📝 今日摘要: {new_summary}")
            
            # 保存摘要
            mem = self.load_memory()
            old = mem.get("short_term_summary", "")
            mem["short_term_summary"] = f"{new_summary} | (旧: {old[:50]}...)"
            self.save_memory(mem)
        
        except Exception as e:
            logger.error(f"总结失败: {e}")
        
        self.mouth.speak("记忆同步完成，晚安。")
        time.sleep(1)
        os._exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#                              技能管理器 (SkillManager) - Function Calling
# ═══════════════════════════════════════════════════════════════════════════════
class SkillManager:
    """
    管理所有可用技能（工具）：
    - 技能定义与注册
    - 技能执行与结果处理
    - 应用程序控制
    """
    
    # 应用程序注册表 (可根据实际情况修改路径)
    APP_REGISTRY = {
        "记事本": {"aliases": ["记事本", "notepad"], "cmd": "notepad"},
        "计算器": {"aliases": ["计算器", "calc"], "cmd": "calc"},
        "画图": {"aliases": ["画图", "paint"], "cmd": "mspaint"},
        "任务管理器": {"aliases": ["任务管理器", "taskmgr"], "cmd": "taskmgr"},
        "文件管理器": {"aliases": ["文件管理器", "explorer"], "cmd": "explorer"},
        "浏览器": {"aliases": ["浏览器", "edge"], "cmd": "start msedge"},
        "VSCode": {"aliases": ["vscode", "code"], "cmd": "code"},
        "微信": {"aliases": ["微信", "wechat"], "cmd": "start WeChat"},
        "QQ": {"aliases": ["qq"], "cmd": "start QQ"},
    }
    
    # 网站注册表
    WEBSITE_REGISTRY = {
        "淘宝": "https://www.taobao.com",
        "京东": "https://www.jd.com",
        "B站": "https://www.bilibili.com",
        "知乎": "https://www.zhihu.com",
        "百度": "https://www.baidu.com",
        "GitHub": "https://github.com",
    }
    
    # 工具定义 Schema
    TOOLS_SCHEMA = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "联网搜索实时信息。适合场景: 新闻/天气/游戏攻略/最新数据等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_website",
                "description": "打开常用网站首页。支持: 淘宝/京东/B站/知乎等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "site_name": {"type": "string", "description": "网站名称"}
                    },
                    "required": ["site_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_video",
                "description": "在B站搜索视频内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["keyword"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "control_volume",
                "description": "控制系统音量。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["up", "down", "mute", "max"]},
                        "level": {"type": "integer", "description": "调节级别(1-10)"}
                    },
                    "required": ["action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "save_memory",
                "description": "将用户的重要信息存入长期记忆。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要记忆的内容"},
                        "importance": {"type": "integer", "description": "重要程度(1-5)"}
                    },
                    "required": ["content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_reminder",
                "description": "设置定时提醒。注意：请AI根据当前时间，自动将用户的口语时间（如'10分钟后'、'明天下午3点'）计算为标准的格式化时间字符串。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_time": {"type": "string", "description": "目标触发时间，格式必须为：YYYY-MM-DD HH:MM:SS"},
                        "content": {"type": "string", "description": "提醒内容"}
                    },
                    "required": ["content", "target_time"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "take_note",
                "description": """【智能笔记】记录重要信息到桌面。
                触发词: "记录"、"记一下"、"备忘"
                AI会自动判断分类并格式化内容。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "笔记内容（AI会格式化）"},
                        "category": {
                            "type": "string",
                            "enum": ["工作", "生活", "灵感", "待办", "学习", "代码", "随记"],
                            "description": "AI根据内容自动推断的分类"
                        }
                    },
                    "required": ["content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_code",
                "description": """【AI代码生成器】根据用户需求动态生成Python代码。
                触发词: "写个脚本"、"生成代码"、"帮我写个程序"
                代码保存到项目 generated/ 文件夹并用VSCode打开。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "文件名（英文，如 snake_game.py）"},
                        "code_content": {"type": "string", "description": "完整的Python代码内容（含注释）"}
                    },
                    "required": ["filename", "code_content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_tool",
                "description": "打开Windows内置工具。支持: 记事本/计算器/画图/任务管理器等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "description": "工具名称(中文)"}
                    },
                    "required": ["tool_name"]
                }
            }
        }
    ]
    
    def __init__(self, config: ConfigManager, mouth: Mouth, brain: Brain):
        self.config = config
        self.mouth = mouth
        self.brain = brain
        self.reminders = self.load_reminders_from_disk() # [修改] 启动时加载硬盘记忆

    # [新增] 从硬盘加载
    def load_reminders_from_disk(self):
        if not self.config.REMINDERS_FILE.exists():
            return []
        try:
            with open(self.config.REMINDERS_FILE, 'r', encoding='utf-8') as f:
                logger.info("⏰ 已加载历史提醒")
                return json.load(f)
        except Exception as e:
            logger.error(f"加载提醒失败: {e}")
            return []

    # [新增] 保存到硬盘
    def save_reminders_to_disk(self):
        try:
            with open(self.config.REMINDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存提醒失败: {e}")
    
    def get_tools(self) -> list:
        """
        动态生成工具定义，让 set_reminder 包含当前时间
        [修复] 解决 AI 计算"一分钟后"时间错误的问题
        """
        now = datetime.now()
        current_datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 复制静态工具列表
        tools = []
        for tool in self.TOOLS_SCHEMA:
            if tool["function"]["name"] == "set_reminder":
                # 动态生成 set_reminder 工具（包含当前时间）
                tools.append({
                    "type": "function",
                    "function": {
                        "name": "set_reminder",
                        "description": f"设置定时提醒。【当前时间是 {current_datetime_str}】请根据此时间计算用户所说的相对时间（如'1分钟后'、'明天下午3点'），转换为 YYYY-MM-DD HH:MM:SS 格式。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target_time": {"type": "string", "description": f"目标触发时间，格式必须为：YYYY-MM-DD HH:MM:SS（当前时间是 {current_datetime_str}）"},
                                "content": {"type": "string", "description": "用户要求被提醒的事项内容，直接从用户原话中提取，不要填写占位符"}
                            },
                            "required": ["content", "target_time"]
                        }
                    }
                })
            else:
                tools.append(tool)
        
        return tools
    
    # ─────────────────────────────────────────────────────────────────────────
    #                              技能实现
    # ─────────────────────────────────────────────────────────────────────────
    
    def search_web(self, query: str) -> str:
        """联网搜索"""
        logger.info(f"🌍 搜索: {query}")
        self.mouth.speak(f"正在帮你查找 {query}")
        
        try:
            # 这里可以接入实际的搜索API，这里用简单的示例
            import webbrowser
            search_url = f"https://www.bing.com/search?q={query}"
            webbrowser.open(search_url)
            return f"已在浏览器打开搜索结果: {query}"
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return f"搜索失败: {str(e)}"
    
    def open_website(self, site_name: str) -> str:
        """打开网站"""
        logger.info(f"🌐 打开网站: {site_name}")
        self.mouth.speak(f"正在为你打开 {site_name}")
        
        try:
            import webbrowser
            url = self.WEBSITE_REGISTRY.get(site_name)
            if url:
                webbrowser.open(url, new=2)
                return f"✅ 已打开: {site_name}"
            return f"❌ 未知网站: {site_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"
    
    def open_video(self, keyword: str) -> str:
        """B站搜索视频"""
        logger.info(f"📺 搜索视频: {keyword}")
        self.mouth.speak(f"正在帮你搜索 {keyword}")
        
        try:
            import webbrowser
            url = f"https://search.bilibili.com/all?keyword={keyword}"
            webbrowser.open(url)
            return f"✅ 已打开B站搜索: {keyword}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"
    
    def control_volume(self, action: str, level: int = None) -> str:
        """音量控制"""
        logger.info(f"🔊 音量控制: {action}, 级别: {level}")
        
        try:
            if level is None:
                level = 1
            
            if action == "up":
                for _ in range(level):
                    keyboard.press_and_release('volume up')
                    time.sleep(0.1)
                self.mouth.speak(f"音量已增大{level}格")
                return f"✅ 音量已增大 {level} 格"
            
            elif action == "down":
                for _ in range(level):
                    keyboard.press_and_release('volume down')
                    time.sleep(0.1)
                self.mouth.speak(f"音量已减小{level}格")
                return f"✅ 音量已减小 {level} 格"
            
            elif action == "mute":
                keyboard.press_and_release('volume mute')
                self.mouth.speak("已切换静音状态")
                return "✅ 已切换静音状态"
            
            elif action == "max":
                for _ in range(50):
                    keyboard.press_and_release('volume up')
                    time.sleep(0.05)
                self.mouth.speak("音量已最大")
                return "✅ 音量已调到最大"
            
            return f"❌ 未知操作: {action}"
        
        except Exception as e:
            return f"❌ 控制失败: {str(e)}"
    
    def save_memory(self, content: str, importance: int = 3) -> str:
        """保存到长期记忆"""
        try:
            self.brain.remember(content, importance)
            return f"✅ 已存入长期记忆: {content}"
        except Exception as e:
            return f"❌ 记忆保存失败: {str(e)}"
    
    def set_reminder(self, content: str, target_time: str) -> str:
        """
        设置提醒
        Args:
            content: 内容
            target_time: 目标时间字符串 "YYYY-MM-DD HH:MM:SS"
        """
        try:
            # 验证时间格式是否正确，防止 AI 乱填
            datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S")
            
            logger.info(f"⏰ 设定提醒: {target_time} - {content}")
            self.mouth.speak(f"好的，我记下了，会在 {target_time} 提醒你：{content}")
            
            # 存入内存并同步到硬盘
            self.reminders.append({"time": target_time, "content": content})
            self.save_reminders_to_disk()
            
            # [新增] 同步写入到桌面笔记
            self.take_note(f"设定提醒 {target_time}: {content}", category="待办")
            
            return f"✅ 已设定提醒：{target_time} 提醒 {content} (已同步到笔记)"
        except ValueError:
            return f"❌ 时间格式错误，必须是 YYYY-MM-DD HH:MM:SS"
    
    def check_reminders(self):
        """检查并触发到期的提醒"""
        current_time = datetime.now()
        active_reminders = []
        is_changed = False
        
        for task in self.reminders:
            task_time = datetime.strptime(task["time"], "%Y-%m-%d %H:%M:%S")
            
            # 如果时间到了（当前时间 >= 任务时间）
            if current_time >= task_time:
                logger.info(f"⏰ 触发提醒: {task['content']}")
                self.mouth.send_to_unity("Surprised")
                # 播放提示音或特定的语音
                self.mouth.speak(f"指挥官，时间到了！记得：{task['content']}")
                is_changed = True # 标记有变动，需要保存
            else:
                # 还没过期的任务，保留在列表里
                active_reminders.append(task)
        
        # 如果有任务被触发并移除了，更新列表并保存到硬盘
        if is_changed:
            self.reminders = active_reminders
            self.save_reminders_to_disk()
    
    def take_note(self, content: str, category: str = "随记") -> str:
        """智能笔记"""
        icons = {
            "工作": "💼", "生活": "🏠", "灵感": "💡",
            "待办": "📌", "学习": "📚", "代码": "💻", "随记": "📝"
        }
        icon = icons.get(category, "📝")
        
        month_str = datetime.now().strftime("%Y-%m")
        filename = self.config.NOTES_DIR / f"Fuguang_Notes_{month_str}.md"
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        
        is_new_file = not filename.exists()
        
        try:
            with open(filename, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(f"# 📅 {month_str} 浮光笔记本\n\n")
                    f.write("| 时间 | 分类 | 内容 |\n")
                    f.write("|:---:|:---:|---|\n")
                
                clean_content = content.replace("\n", " ").replace("|", "/")
                row = f"| {timestamp} | {icon} {category} | {clean_content} |\n"
                f.write(row)
            
            logger.info(f"📝 已归档至 {filename} [{category}]")
            self.mouth.speak(f"已记录到桌面笔记本，分类是{category}")
            
            # 自动打开笔记文件
            try:
                os.startfile(str(filename))
            except Exception as e:
                logger.warning(f"打开文件失败: {e}")
            
            return f"✅ 已记录到桌面: {filename.name}"
        
        except Exception as e:
            logger.error(f"记录失败: {e}")
            return f"记录失败: {str(e)}"
    
    def write_code(self, filename: str, code_content: str) -> str:
        """代码生成"""
        if not filename.endswith(".py"):
            filename += ".py"
        
        full_path = self.config.GENERATED_DIR / filename
        
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(code_content)
            
            logger.info(f"💾 代码已生成: {full_path}")
            self.mouth.speak(f"代码已生成：{filename}，正在为你打开")
            
            # 尝试用 VSCode 打开
            try:
                result = subprocess.run(["code", str(full_path)],
                                      capture_output=True, timeout=5)
                if result.returncode != 0:
                    raise Exception("VSCode 启动失败")
                logger.info("📂 已用 VSCode 打开")
            except Exception:
                try:
                    os.startfile(str(full_path))
                    logger.info("📂 已用默认程序打开")
                except Exception as e:
                    logger.warning(f"打开文件失败: {e}")
            
            return f"✅ 代码已生成: generated/{filename}"
        
        except Exception as e:
            logger.error(f"代码生成失败: {e}")
            return f"代码生成失败: {str(e)}"
    
    def find_app_by_alias(self, text: str) -> tuple:
        """根据别名查找应用"""
        text_lower = text.lower()
        for app_name, config in self.APP_REGISTRY.items():
            for alias in config["aliases"]:
                if alias.lower() in text_lower:
                    return app_name, config["cmd"]
        return None, None
    
    def open_app(self, text: str) -> bool:
        """启动应用"""
        app_name, cmd = self.find_app_by_alias(text)
        
        if app_name:
            logger.info(f"🚀 启动: {app_name}")
            self.mouth.speak(f"正在打开{app_name}")
            try:
                os.system(cmd)
                return True
            except Exception as e:
                logger.error(f"打开失败: {e}")
                self.mouth.speak(f"打开{app_name}失败了")
                return False
        return False
    
    def open_tool(self, tool_name: str) -> str:
        """打开工具"""
        if self.open_app(tool_name):
            return "✅ 已打开"
        
        self.mouth.speak(f"正在打开{tool_name}")
        try:
            os.system(f"start {tool_name}")
            return f"✅ 尝试启动: {tool_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"
    
    # ─────────────────────────────────────────────────────────────────────────
    #                              工具执行器
    # ─────────────────────────────────────────────────────────────────────────
    
    def execute(self, tool_name: str, arguments: dict) -> str:
        """
        执行指定的工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            执行结果字符串
        """
        handlers = {
            "search_web": lambda: self.search_web(arguments.get("query", "")),
            "open_website": lambda: self.open_website(arguments.get("site_name", "")),
            "open_video": lambda: self.open_video(arguments.get("keyword", "")),
            "control_volume": lambda: self.control_volume(
                arguments.get("action", "up"), 
                arguments.get("level", 1)
            ),
            "save_memory": lambda: self.save_memory(
                arguments.get("content", ""),
                arguments.get("importance", 3)
            ),
            "set_reminder": lambda: self.set_reminder(
                arguments.get("content", ""),
                arguments.get("target_time", "") # 这里变了
            ),
            "take_note": lambda: self.take_note(
                arguments.get("content", ""),
                arguments.get("category", "随记")
            ),
            "write_code": lambda: self.write_code(
                arguments.get("filename", "script.py"),
                arguments.get("code_content", "")
            ),
            "open_tool": lambda: self.open_tool(arguments.get("tool_name", "")),
        }
        
        handler = handlers.get(tool_name)
        if handler:
            try:
                return handler()
            except Exception as e:
                return f"执行失败: {str(e)}"
        else:
            return f"未知工具: {tool_name}"


# ═══════════════════════════════════════════════════════════════════════════════
#                              神经系统 (NervousSystem) - 主控制器
# ═══════════════════════════════════════════════════════════════════════════════
class NervousSystem:
    """
    主控制系统，协调各模块：
    - 键盘事件监听 (PTT)
    - 唤醒词检测流程
    - 命令处理管道
    - 主循环控制
    """
    
    def __init__(self):
        # 初始化配置和模块
        self.config = ConfigManager()
        ConfigManager.ensure_directories()
        
        self.mouth = Mouth(self.config)
        self.ears = Ears(self.config)
        self.brain = Brain(self.config, self.mouth)
        self.skills = SkillManager(self.config, self.mouth, self.brain)
        
        # 状态变量
        self.awake_state = "sleeping"  # sleeping / voice_wake
        self.is_ptt_pressed = False
        self.last_active_time = 0
        
        # 注册按键监听
        keyboard.hook(self._on_key_event)
        
        logger.info("🧠 神经系统初始化完毕")
    
    def _on_key_event(self, event):
        """按键事件处理"""
        if event.name == 'right ctrl':
            if event.event_type == 'down' and not self.is_ptt_pressed:
                self.is_ptt_pressed = True
                logger.info("🎤 [PTT] 键按下")
                fuguang_heartbeat.update_interaction()
            elif event.event_type == 'up' and self.is_ptt_pressed:
                self.is_ptt_pressed = False
                self.last_active_time = time.time()
                logger.info("🎤 [PTT] 录音结束")
    
    def _check_timeout(self):
        """检查语音唤醒是否超时"""
        if self.awake_state == "voice_wake":
            elapsed = time.time() - self.last_active_time
            if elapsed > self.config.VOICE_WAKE_DURATION:
                self.awake_state = "sleeping"
                logger.info("💤 语音唤醒超时，回到待机")
    
    def _get_status_text(self) -> str:
        """获取当前状态文本"""
        if self.is_ptt_pressed:
            return "🎤 PTT录音中"
        elif self.awake_state == "sleeping":
            return "💤 待机中（按住CTRL说话或叫我名字）"
        elif self.awake_state == "voice_wake":
            remaining = int(self.config.VOICE_WAKE_DURATION - (time.time() - self.last_active_time))
            return f"🟢 唤醒中 ({remaining}s)"
        return "❓ 未知"
    
    def _process_response(self, ai_text: str):
        """处理 AI 响应，提取标签和命令"""
        if "<｜DSML｜" in ai_text or "<tool_code>" in ai_text:
            return
        
        cmd_expression = "Neutral"
        cmd_unity = ""
        
        # 提取标签
        tags = re.findall(r"\[(.*?)\]", ai_text)
        clean_text = re.sub(r"\[.*?\]", "", ai_text).strip()
        
        for tag in tags:
            if tag in ["Joy", "Angry", "Sorrow", "Fun", "Surprised", "Neutral"]:
                cmd_expression = tag
            elif tag == "CMD:MODE_ON":
                self.brain.is_creation_mode = True
                logger.info("🔓 创造模式已开启")
            elif tag == "CMD:MODE_OFF":
                self.brain.is_creation_mode = False
                logger.info("🔒 创造模式已关闭")
            elif tag == "CMD:SHUTDOWN":
                self.brain.summarize_and_exit()
            elif tag.startswith("CMD:"):
                cmd_unity = tag.replace("CMD:", "").lower()
        
        self.mouth.send_to_unity(cmd_expression)
        
        if cmd_unity:
            if self.brain.is_creation_mode:
                self.mouth.send_to_unity(cmd_unity)
                if clean_text:
                    self.mouth.speak(clean_text)
            else:
                self.mouth.speak("物理操作需要先开启创造模式哦")
                self.mouth.send_to_unity("Sorrow")
        else:
            if clean_text:
                self.mouth.speak(clean_text)
    
    def _handle_ai_response(self, user_input: str):
        """处理 AI 回复"""
        self.last_active_time = time.time()
        fuguang_heartbeat.update_interaction()
        
        # [修复] 新对话开始，清除之前的打断状态
        self.mouth.clear_interrupt()
        
        # 检索相关记忆
        related_memories = self.brain.recall(user_input)
        memory_text = ""
        if related_memories:
            memory_text = "\n【相关长期记忆】\n" + "\n".join(related_memories)
            logger.info(f"🧠 激活记忆: {related_memories}")
        
        # 构建消息
        system_content = self.brain.get_system_prompt() + memory_text
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.brain.chat_history)
        messages.append({"role": "user", "content": user_input})
        
        try:
            max_iterations = 3
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                logger.info(f"🤖 AI思考轮次: {iteration}")
                
                self.mouth.start_thinking()  # <--- 让她开始托腮思考

                response = self.brain.client.chat.completions.create(
                    model=self.config.DEEPSEEK_MODEL,
                    messages=messages,
                    tools=self.skills.get_tools(),
                    tool_choice="auto",
                    stream=False,
                    temperature=0.8,
                    max_tokens=4096
                )
                
                self.mouth.stop_thinking()   # <--- 收到回复，停止思考，恢复站立

                
                message = response.choices[0].message
                
                # 处理工具调用
                if message.tool_calls:
                    logger.info(f"🔧 AI请求使用工具: {len(message.tool_calls)} 个")
                    
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in message.tool_calls
                        ]
                    })
                    
                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        func_args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"📞 调用工具: {func_name}")
                        result = self.skills.execute(func_name, func_args)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result
                        })
                    
                    continue
                
                else:
                    ai_reply = message.content
                    break
            
            else:
                ai_reply = "这个问题有点复杂，我需要更多时间思考..."
            
            # 保存对话历史
            self.brain.chat_history.append({"role": "user", "content": user_input})
            self.brain.chat_history.append({"role": "assistant", "content": ai_reply})
            self.brain.trim_history()
            
            # 处理响应
            if ai_reply and not ("<｜DSML｜" in ai_reply or "<tool_code>" in ai_reply):
                self._process_response(ai_reply)
            
            # 更新记忆
            current_mem = self.brain.load_memory()
            current_mem["last_interaction"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.brain.save_memory(current_mem)
        
        except Exception as e:
            logger.error(f"AI 处理异常: {e}")
            import traceback
            traceback.print_exc()
            self.mouth.speak_error("连接受到干扰...")
    
    def _extract_level(self, text: str) -> int:
        """提取音量级别"""
        for i, cn in enumerate(["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"], 1):
            if cn in text or str(i) in text:
                return i
        if "很多" in text or "非常" in text:
            return 5
        return 1
    
    def _process_command(self, text: str):
        """处理用户命令 (分流本地/AI)"""
        self.last_active_time = time.time()
        fuguang_heartbeat.update_interaction()
        
        # 音量控制 - 本地快捷
        if any(word in text for word in ["太小", "听不见", "听不清", "小了"]):
            self.skills.control_volume("up", 3 if "很" in text else 2)
            return
        if any(word in text for word in ["太吵", "太大", "大了"]):
            self.skills.control_volume("down", 3 if "很" in text else 2)
            return
        if any(word in text for word in ["静音", "闭嘴", "安静"]):
            self.skills.control_volume("mute")
            return
        
        # [新增] 礼貌回应
        if any(w in text for w in ["你好", "哈喽", "Hello", "hi"]):
            self.mouth.wave()
            self.mouth.speak("你好呀指挥官")
            return
        if "声音" in text or "音量" in text:
            if "最大" in text:
                self.skills.control_volume("max")
                return
            elif any(w in text for w in ["大", "增", "加", "高"]):
                self.skills.control_volume("up", self._extract_level(text))
                return
            elif any(w in text for w in ["小", "减", "低", "降"]):
                self.skills.control_volume("down", self._extract_level(text))
                return
        
        # 软件启动 - 本地快捷
        if any(t in text for t in ["打开", "启动", "运行"]):
            if self.skills.open_app(text):
                return
        
        # 本地查询 - 快速响应
        if "几点" in text or "时间" in text:
            self.mouth.speak(datetime.now().strftime("现在是 %H点%M分"))
            return
        if "几号" in text or "日期" in text:
            self.mouth.speak(datetime.now().strftime("今天是 %Y年%m月%d日"))
            return
        
        # 交给 AI 处理
        self._handle_ai_response(text)
    
    def run(self):
        """主循环 - 生命的脉动"""
        print("=" * 60)
        print("       浮光 Study AI 助手 v0.5 (改进版)")
        print("=" * 60)
        print("  按住 右Ctrl 说话 | 唤醒词: 浮光/扶光/小光/阿光/光光")
        print("  Ctrl+Shift+Q 退出")
        print("=" * 60)
        
        logger.info("🚀 神经系统启动")
        self.mouth.send_to_unity("Joy")
        fuguang_heartbeat.start_heartbeat()
        
        # [新增] 启动时挥手致意
        time.sleep(2) # 等Unity准备好
        self.mouth.wave() 
        self.mouth.speak("指挥官，我上线了。")
        
        try:
            while True:
                self._check_timeout()
                self.skills.check_reminders()
                
                # 显示状态
                status_icon = "🎤" if self.is_ptt_pressed else "🟢" if self.awake_state == "voice_wake" else "💤"
                print(f"\r{status_icon} [{self._get_status_text()}]", end="", flush=True)
                
                # ========================
                # 模式1: PTT（按住录音）
                # ========================
                if self.is_ptt_pressed:
                    with self.ears.get_microphone() as source:
                        logger.info("🎤 [PTT] 正在录音，松开CTRL结束...")
                        self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                        
                        try:
                            frames = []
                            while self.is_ptt_pressed:
                                try:
                                    buffer = source.stream.read(source.CHUNK)
                                    frames.append(buffer)
                                except Exception:
                                    break
                            
                            if frames:
                                audio_data = b''.join(frames)
                                logger.info(f"🎤 录制完成，共 {len(audio_data)} 字节")
                                
                                text = self.ears.listen_ali(audio_data)
                                
                                if text:
                                    logger.info(f"👂 听到了: {text}")
                                    fuguang_heartbeat.update_interaction()
                                    self._process_command(text)
                                else:
                                    logger.warning("未识别到语音")
                            
                            time.sleep(0.1)
                            continue
                        
                        except Exception as e:
                            logger.error(f"PTT 异常: {e}")
                            continue
                
                # ========================
                # 模式2: 语音唤醒 / 待机监听
                # ========================
                with self.ears.get_microphone() as source:
                    self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    
                    if self.is_ptt_pressed:
                        time.sleep(0.1)
                        continue
                    
                    try:
                        limit = 3 if self.awake_state == "sleeping" else 10
                        audio = self.ears.recognizer.listen(source, timeout=2, phrase_time_limit=limit)
                        
                        if self.is_ptt_pressed:
                            continue
                        
                        audio_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                        text = self.ears.listen_ali(audio_data)
                        
                        if text:
                            logger.info(f"👂 听到了: {text}")
                            has_wake_word, matched_word, clean_text = self.ears.check_wake_word_pinyin(text)
                            
                            if self.awake_state == "sleeping":
                                if has_wake_word:
                                    logger.info(f"⚡️ 语音唤醒成功: {matched_word}")
                                    self.awake_state = "voice_wake"
                                    self.last_active_time = time.time()
                                    fuguang_heartbeat.update_interaction()
                                    self.mouth.send_to_unity("Surprised")
                                    self.mouth.speak("我在")
                                    if clean_text:
                                        self._process_command(clean_text)
                                elif self.brain.should_auto_respond(text):
                                    self._process_command(text)
                            else:
                                self.last_active_time = time.time()
                                self._process_command(text)
                    
                    except sr.WaitTimeoutError:
                        pass
                    except Exception as e:
                        logger.error(f"异常: {e}")
        
        except KeyboardInterrupt:
            logger.info("\n检测到中断信号")
        
        finally:
            self._shutdown()
    
    def _shutdown(self):
        """关闭清理"""
        logger.info("正在关闭...")
        self.brain.summarize_and_exit()
        keyboard.unhook_all()
        logger.info("再见！")


# ═══════════════════════════════════════════════════════════════════════════════
#                              程序入口
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    system = NervousSystem()
    system.run()