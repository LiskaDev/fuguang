
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
from zhipuai import ZhipuAI

from .config import ConfigManager
from .mouth import Mouth
from .brain import Brain

logger = logging.getLogger("Fuguang")

# [视觉] 导入 OCR 工具（用于 GUI 控制）
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("⚠️ EasyOCR 未安装，GUI 控制功能将受限")

# [GUI] 导入窗口管理工具
try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False
    logger.warning("⚠️ PyGetWindow 未安装，窗口定位功能将受限")

# [视觉] 导入 YOLO-World（零样本目标检测）
try:
    from ultralytics import YOLOWorld
    YOLOWORLD_AVAILABLE = True
except ImportError:
    YOLOWORLD_AVAILABLE = False
    logger.warning("⚠️ Ultralytics 未安装，YOLO-World 视觉识别功能将受限")

class SkillManager:
    """
    执行能力角色
    职责：工具函数、软件启动、网络搜索
    """

    # 🔧 静态工具定义 Schema（不含需要动态时间的工具）
    _STATIC_TOOLS = [
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
                "description": "打开常用网站首页。支持: 淘宝/京东/B站/知乎/微博/GitHub等",
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
                "description": "控制系统音量。触发词: 声音大/小、音量增加/减少、静音、最大音量",
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
        # [已移除 set_reminder 到动态方法 get_tools_schema() 中]
        {
            "type": "function",
            "function": {
                "name": "execute_shell",
                "description": """【系统Shell】执行任意命令行指令。
                优先使用此工具进行系统操作（如文件管理、网络查询、进程管理等），因为比 GUI 点击更可靠。
                支持 PowerShell 语法。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的 Shell 命令"},
                        "background": {"type": "boolean", "description": "是否后台运行（默认False）"}
                    },
                    "required": ["command"]
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
        },
        {
            "type": "function",
            "function": {
                "name": "run_code",
                "description": """【代码执行器】运行 generated/ 目录下的 Python 脚本。
                使用场景: 写完代码后需要运行查看结果。
                注意: 执行前会请求指挥官确认，确保安全。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "要运行的文件名（如 heart.py）"}
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_web_page",
                "description": """【网页阅读器】读取并提取指定网页的文字内容。
                使用场景: 需要深入了解某个链接的详细内容时使用。
                注意: 只能读取公开网页，不支持需要登录的页面。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "要读取的网页 URL"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_screen_content",
                "description": """【视觉神经】(GLM-4V) 截取当前屏幕并进行视觉分析。
                使用场景: 用户说"看看屏幕"、"这个图片是什么"、"帮我读一下屏幕内容"时使用。
                注意: 这是一个耗时操作(约3-5秒)，请耐心等待。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "关于屏幕内容的具体问题"}
                    },
                    "required": ["question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_image_file",
                "description": """【本地图片分析】(GLM-4V) 分析指定路径的本地图片文件。
                使用场景: 用户说"帮我看看这张图片"、"分析一下 xxx.png"、"这个图片里是什么"时使用。
                支持格式: jpg, jpeg, png, bmp, webp。
                注意: 图片路径可以是相对路径(如 'jimi.png')或绝对路径。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图片文件的路径(相对或绝对)"},
                        "question": {"type": "string", "description": "关于图片内容的具体问题"}
                    },
                    "required": ["image_path", "question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_vision_history",
                "description": """【视觉历史记录】查看最近5次的视觉分析记录。
                使用场景: 用户说"刚才看到什么"、"之前分析的那个图片"、"回看一下历史记录"时使用。
                支持多轮对话: 可以让AI记住之前看过的内容，实现"继续看刚才那个画面的左上角"这样的对话。""",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "open_application",
                "description": """【应用启动】打开常用应用程序（记事本、浏览器、计算器等）。
                使用场景: 用户说"打开记事本"、"启动浏览器"、"打开计算器"等。
                支持的应用: notepad(记事本)、chrome(Chrome浏览器)、edge(Edge浏览器)、calc(计算器)、explorer(文件管理器)、cmd(命令行)等。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "应用名称，如 'notepad'、'chrome'、'calc'、'explorer'"},
                        "args": {"type": "string", "description": "可选参数，如打开特定网页、文件路径等"}
                    },
                    "required": ["app_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "click_screen_text",
                "description": """【GUI控制】智能寻找屏幕上的指定文字（按钮、链接、菜单）并模拟鼠标点击。
                使用场景: 用户说"帮我点击发送按钮"、"点一下文件菜单"、"点击确定"等。
                技术: 使用 EasyOCR 识别文字坐标，失败时可选用 GLM-4V 辅助定位。
                智能特性: 支持窗口过滤（解决多窗口歧义问题）。
                注意: 如果屏幕上有多个相同文字，可以先用 open_application 打开特定应用，再点击。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_text": {"type": "string", "description": "要点击的文字内容，如 '发送'、'File'、'确定'"},
                        "double_click": {"type": "boolean", "description": "是否双击（默认单击）"},
                        "window_title": {"type": "string", "description": "可选：指定窗口标题（用于过滤多窗口歧义），如 '记事本'、'Bilibili'"}
                    },
                    "required": ["target_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": """【键盘输入】在当前光标位置输入文字。
                使用场景: 用户说"帮我输入xxx"、"在输入框里打666"、"发送消息: 你好"等。
                注意: 需要先点击输入框再调用此工具。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要输入的内容"},
                        "press_enter": {"type": "boolean", "description": "输入完是否按回车（默认True）"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "click_by_description",
                "description": """【智能视觉点击】通过自然语言描述来寻找并点击屏幕上的任何 UI 元素（图标、按钮、图片等）。
                
使用场景:
- 点击图标: "点击 Chrome 图标"、"点击微信图标"
- 点击按钮: "点击红色按钮"、"点击关闭按钮"、"点击播放按钮"
- 点击输入框: "点击搜索框"、"点击输入框"
- 点击图片: "点击那张猫的图片"
- 社交媒体: "点击点赞按钮"、"点击收藏按钮"

⚠️ 重要提示:
1. description 参数必须用英文描述，AI识别效果更好！
2. 常见翻译示例:
   - "点击搜索框" → description="search box"
   - "点击关闭按钮" → description="close button"
   - "点击红色图标" → description="red icon"
   - "点击Chrome图标" → description="chrome icon"
   - "点击点赞按钮" → description="like button"
   - "点击播放按钮" → description="play button"
   
当用户说中文时，请自动翻译为英文后传入 description 参数。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "物体的英文描述（如 'red button', 'chrome icon', 'search box'）。必须用英文！"
                        },
                        "double_click": {
                            "type": "boolean",
                            "description": "是否双击（默认False）"
                        }
                    },
                    "required": ["description"]
                }
            }
        }
    ]

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
        self.reminders = self.load_reminders_from_disk()
        
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
                self.yolo_world = YOLOWorld('yolov8s-worldv2.pt')  # 使用 small 版本，速度快
                logger.info("✅ YOLO-World 视觉识别已就绪（零样本目标检测）")
            except Exception as e:
                self.yolo_world = None
                logger.error(f"❌ YOLO-World 加载失败: {e}")
        else:
            self.yolo_world = None
            logger.warning("⚠️ YOLO-World 未安装，图标识别功能将受限")
            
        # [视觉] 初始化 EasyOCR (文字识别)
        if EASYOCR_AVAILABLE:
            try:
                logger.info("📖 正在加载 EasyOCR 模型 (首次运行需下载)...")
                import easyocr
                self._ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
                logger.info("✅ EasyOCR 文字识别已就绪")
            except Exception as e:
                logger.error(f"❌ EasyOCR 加载失败: {e}")
                self._ocr_reader = None
    
    def get_tools_schema(self):
        """
        动态生成工具 Schema，让 set_reminder 包含当前时间
        [修复] 解决 AI 计算"一分钟后"时间错误的问题
        [升级] v1.2.0 增加 auto_action 支持自动执行操作
        """
        now = datetime.datetime.now()
        current_datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 动态生成 set_reminder 工具（包含当前时间 + 自动执行功能）
        set_reminder_tool = {
            "type": "function",
            "function": {
                "name": "set_reminder",
                "description": f"""设置定时提醒，支持自动执行操作。【当前时间是 {current_datetime_str}】
请根据此时间计算用户所说的相对时间（如'1分钟后'、'明天下午3点'），转换为 YYYY-MM-DD HH:MM:SS 格式。
⚠️ 重要：如果用户说"提醒我打开XX"或"X分钟后打开XX"，必须同时填写 auto_action 字段！""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_time": {
                            "type": "string", 
                            "description": f"目标触发时间，格式必须为：YYYY-MM-DD HH:MM:SS（当前时间是 {current_datetime_str}）"
                        },
                        "content": {
                            "type": "string", 
                            "description": "用户要求被提醒的事项内容，直接从用户原话中提取（如'打开B站'、'吃药'、'开会'等），不要填写占位符"
                        },
                        "auto_action": {
                            "type": "object",
                            "description": "【可选】如果用户要求在提醒时自动执行某操作（如'打开B站'、'打开网易云'），则填写此字段。系统会在时间到时自动调用对应工具。",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "enum": ["open_website", "open_video", "open_tool", "control_volume"],
                                    "description": "要自动执行的工具名称"
                                },
                                "arguments": {
                                    "type": "object",
                                    "description": "传递给工具的参数，如 {\"site_name\": \"B站\"} 或 {\"keyword\": \"原神攻略\"}"
                                }
                            },
                            "required": ["tool_name", "arguments"]
                        }
                    },
                    "required": ["content", "target_time"]
                }
            }
        }
        
        # 合并静态工具 + 动态工具
        return self._STATIC_TOOLS + [set_reminder_tool]
    
    def load_reminders_from_disk(self):
        if not self.config.REMINDERS_FILE.exists():
            return []
        try:
            with open(self.config.REMINDERS_FILE, 'r', encoding='utf-8') as f:
                logger.info("⏰ [Core] 已加载历史提醒")
                return json.load(f)
        except Exception as e:
            logger.error(f"加载提醒失败: {e}")
            return []

    def save_reminders_to_disk(self):
        try:
            with open(self.config.REMINDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存提醒失败: {e}")

    def _show_toast(self, title: str, message: str):
        """发送 Windows 系统通知"""
        try:
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.BalloonTipTitle = '{title}'
            $notify.BalloonTipText = '{message}'
            $notify.Visible = $True
            $notify.ShowBalloonTip(10000)
            """
            cmd = ["powershell", "-Command", ps_script]
            subprocess.Popen(cmd) 
        except Exception as e:
            logger.error(f"弹窗失败: {e}")

    # ========================
    # 🌍 联网搜索
    # ========================
    def search_web(self, query: str) -> str:
        """Serper API 搜索"""
        logger.info(f"🌍 正在搜索: {query}...")
        self.mouth.speak(f"正在帮指挥官查找 {query}...")

        try:
            url = "https://google.serper.dev/search"
            payload = {"q": query, "gl": "cn", "hl": "zh-cn", "num": 5}
            headers = {"X-API-KEY": self.config.SERPER_API_KEY, "Content-Type": "application/json"}

            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code != 200:
                return f"搜索失败,状态码 {response.status_code}"

            data = response.json()

            if "knowledgeGraph" in data:
                kg = data["knowledgeGraph"]
                return f"【快速答案】\n{kg.get('title', '')}\n{kg.get('description', '')}\n"

            if "organic" not in data or not data["organic"]:
                return "未找到有效搜索结果"

            results = data["organic"][:5]
            summary = f"✅ 搜索'{query}'找到 {len(results)} 条结果:\n\n"

            for i, res in enumerate(results, 1):
                title = res.get("title", "无标题")
                snippet = res.get("snippet", "无摘要")
                summary += f"【{i}】{title}\n{snippet[:200]}...\n\n"

            return summary.strip()

        except Exception as e:
            logger.error(f"搜索异常: {e}")
            return f"搜索失败: {str(e)}"

    # ========================
    # 📖 网页深度阅读
    # ========================
    def read_web_page(self, url: str) -> str:
        """读取并提取网页的文字内容"""
        from bs4 import BeautifulSoup
        
        logger.info(f"📖 正在阅读网页: {url}")
        self.mouth.speak("正在阅读网页内容...")
        
        try:
            # 模拟浏览器 User-Agent
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = response.apparent_encoding or 'utf-8'
            
            if response.status_code != 200:
                return f"❌ 网页访问失败，状态码: {response.status_code}"
            
            # 解析 HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 移除脚本、样式、导航等无关内容
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                tag.decompose()
            
            # 提取正文内容（优先查找主内容区域）
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
            
            if main_content:
                text = main_content.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)
            
            # 清理多余空行
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = '\n'.join(lines)
            
            # 限制长度（防止 Token 爆炸）
            max_chars = 3000
            if len(clean_text) > max_chars:
                clean_text = clean_text[:max_chars] + f"\n\n... (内容过长，已截取前 {max_chars} 字符)"
            
            # 获取页面标题
            title = soup.title.string if soup.title else "无标题"
            
            logger.info(f"✅ 网页读取成功: {title[:50]}")
            return f"📄 网页标题: {title}\n\n{clean_text}"
            
        except requests.Timeout:
            return "❌ 网页访问超时（15秒），请稍后重试。"
        except Exception as e:
            logger.error(f"网页读取失败: {e}")
            return f"❌ 网页读取失败: {str(e)}"

    # ========================
    # 📸 视觉神经 (GLM-4V)
    # ========================
    def analyze_screen_content(self, question: str) -> str:
        """
        截取屏幕并调用 GLM-4V 进行分析
        
        改进:
        - ✅ 修复 Base64 格式（添加 data URI 前缀）
        - ✅ 支持极速/标准模式切换
        - ✅ 优化提示词（让回答更简洁口语化）
        - ✅ 增加重试机制（网络波动时自动重试）
        - ✅ 智能缓存（避免重复分析同一画面）
        """
        if not self.vision_client:
            return "❌ 视觉模块未激活，请检查 ZHIPU_API_KEY 配置。"

        logger.info(f"📸 [视觉] 正在截取屏幕并发送给 GLM-4V...")
        self.mouth.speak("让我看看屏幕...")
        start_time = time.time()

        try:
            # 1. 截图
            screenshot = pyautogui.screenshot()
            
            # 2. 图片压缩 (使用配置的参数)
            max_size = self.config.VISION_MAX_SIZE
            screenshot.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # 3. 转成 Base64 (关键修复：添加 data URI 前缀)
            buffered = io.BytesIO()
            screenshot.save(buffered, format="JPEG", quality=self.config.VISION_QUALITY)
            img_bytes = buffered.getvalue()
            
            # 计算图片哈希（用于缓存判断）
            import hashlib
            img_hash = hashlib.md5(img_bytes).hexdigest()
            
            # 智能缓存：如果画面没变且问题相同，直接返回上次结果
            if img_hash == self._last_screenshot_hash and self._last_screenshot_result:
                logger.info("🎯 [缓存] 画面未变化，直接返回上次结果")
                return self._last_screenshot_result
            
            # Base64 编码并添加前缀（智谱 API 要求的格式）
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            img_data_uri = f"data:image/jpeg;base64,{img_base64}"
            
            # 选择模型（根据配置）
            model = "glm-4v-flash" if self.config.VISION_USE_FLASH else "glm-4v"
            
            # 4. 优化的提示词（让 GLM 的回答更符合扶光的口吻，并防止幻觉）
            optimized_prompt = (
                f"你是扶光，指挥官的AI助手。请【完全基于图片内容】回答，【绝对禁止编造】不在图片中的信息。\n\n"
                f"用户问题：{question}\n\n"
                f"必须遵守：\n"
                f"- 看到什么说什么，如果画面是空白/加载中/模糊，请直接说明。\n"
                f"- 如果看不清具体文字，不要瞎猜。\n"
                f"- 语气自然口语化，控制在 100 字以内。"
            )
            
            # 5. 调用 GLM-4V (带重试机制)
            max_retries = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    response = self.vision_client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": optimized_prompt
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": img_data_uri
                                        }
                                    }
                                ]
                            }
                        ],
                        temperature=0.7,  # 适中的创造性
                        top_p=0.9
                    )
                    
                    # 成功获取结果
                    analysis_result = response.choices[0].message.content
                    cost_time = time.time() - start_time
                    
                    # 更新缓存
                    self._last_screenshot_hash = img_hash
                    self._last_screenshot_result = f"【视觉观察】\n{analysis_result}"
                    
                    # 保存到历史记录
                    self._add_vision_history(
                        question=question,
                        result=analysis_result,
                        image_data=img_bytes,
                        source="screenshot"
                    )
                    
                    logger.info(f"👀 [GLM-{model}] 视觉分析完成 (耗时 {cost_time:.2f}s)")
                    return self._last_screenshot_result
                
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ 第 {attempt + 1} 次调用失败，正在重试... ({e})")
                        time.sleep(1)  # 等待 1 秒后重试
                    else:
                        raise  # 最后一次失败则抛出异常
            
        except Exception as e:
            logger.error(f"视觉分析失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 根据错误类型给出更友好的提示
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                return "❌ 指挥官，网络有点慢，视觉分析超时了..."
            elif "api" in error_msg or "key" in error_msg:
                return "❌ API 配置有问题，请检查 ZHIPU_API_KEY 是否正确。"
            else:
                return f"❌ 视觉分析出错了：{str(e)[:100]}..."

    def analyze_image_file(self, image_path: str, question: str) -> str:
        """
        分析本地图片文件（使用 GLM-4V）
        
        Args:
            image_path: 图片路径（支持相对路径）
            question: 关于图片的问题
        
        Returns:
            GPT-4V 的分析结果
        """
        if not self.vision_client:
            return "❌ 视觉模块未激活，请检查 ZHIPU_API_KEY 配置。"
        
        logger.info(f"🖼️ [视觉] 正在分析本地图片: {image_path}")
        self.mouth.speak("让我看看这张图片...")
        start_time = time.time()
        
        try:
            # 1. 处理路径（支持相对路径）
            import os
            if not os.path.isabs(image_path):
                # 相对于项目根目录
                project_root = self.config.PROJECT_ROOT
                image_path = os.path.join(project_root, image_path)
            
            if not os.path.exists(image_path):
                return f"❌ 找不到图片文件: {image_path}"
            
            # 2. 读取图片
            img = Image.open(image_path)
            
            # 3. 图片压缩（复用配置）
            max_size = self.config.VISION_MAX_SIZE
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # 4. 转成 Base64
            buffered = io.BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(buffered, format=img_format, quality=self.config.VISION_QUALITY)
            img_bytes = buffered.getvalue()
            
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            img_data_uri = f"data:image/{img_format.lower()};base64,{img_base64}"
            
            # 5. 选择模型
            model = "glm-4v-flash" if self.config.VISION_USE_FLASH else "glm-4v"
            
            # 6. 优化提示词
            optimized_prompt = (
                f"你是扶光，指挥官的AI助手。请简洁地回答问题，口语化一点。\n\n"
                f"用户问题：{question}\n\n"
                f"提示：描述画面的主要内容和视觉特点，控制在 100 字以内。"
            )
            
            # 7. 调用 GLM-4V
            response = self.vision_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": optimized_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": img_data_uri
                                }
                            }
                        ]
                    }
                ],
                temperature=0.7,
                top_p=0.9
            )
            
            analysis_result = response.choices[0].message.content
            cost_time = time.time() - start_time
            
            logger.info(f"👀 [GLM-{model}] 图片分析完成 (耗时 {cost_time:.2f}s)")
            return f"【图片分析】\n{analysis_result}"
        
        except Exception as e:
            logger.error(f"图片分析失败: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ 图片分析失败: {str(e)[:100]}..."
    
    def _add_vision_history(self, question: str, result: str, image_data: bytes, source: str):
        """
        添加视觉分析历史记录
        
        Args:
            question: 用户问题
            result: 分析结果
            image_data: 图片二进制数据
            source: 来源（screenshot 或 file:xxx.png）
        """
        try:
            import datetime
            timestamp = datetime.datetime.now()
            
            # 保存图片到磁盘
            image_filename = f"vision_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            image_path = self._vision_history_dir / image_filename
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            # 添加到历史记录
            history_item = {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "question": question,
                "result": result,
                "image_path": str(image_path),
                "source": source
            }
            
            self._vision_history.append(history_item)
            
            # 只保留最近 5 次
            if len(self._vision_history) > 5:
                # 删除最旧的图片文件
                old_item = self._vision_history.pop(0)
                old_image_path = old_item.get("image_path")
                if old_image_path and os.path.exists(old_image_path):
                    os.remove(old_image_path)
            
            logger.debug(f"📝 [历史] 已保存视觉分析记录 ({len(self._vision_history)}/5)")
            
        except Exception as e:
            logger.warning(f"⚠️ 保存视觉历史失败: {e}")
    
    def get_vision_history(self) -> str:
        """
        获取视觉分析历史记录（用于多轮对话）
        
        Returns:
            格式化的历史记录文本
        """
        if not self._vision_history:
            return "暂无视觉分析历史记录。"
        
        history_text = "【最近的视觉分析记录】\n\n"
        
        for i, item in enumerate(reversed(self._vision_history), 1):
            history_text += f"{i}. [{item['timestamp']}] {item['source']}\n"
            history_text += f"   问题: {item['question']}\n"
            history_text += f"   结果: {item['result'][:80]}...\n\n"
        
        return history_text

    # =========================
    # 🖱️ GUI 控制 (智能鼠标操作)
    # =========================
    
    def open_application(self, app_name: str, args: str = None) -> str:
        """
        打开常用应用程序
        
        Args:
            app_name: 应用名称 (notepad, chrome, edge, calc, explorer, cmd等)
            args: 可选参数（如网址、文件路径）
        
        Returns:
            执行结果描述
        """
        logger.info(f"🚀 [GUI] 正在打开应用: {app_name}")
        self.mouth.speak(f"正在打开 {app_name}...")
        
        try:
            # 应用映射表
            app_map = {
                "notepad": "notepad.exe",
                "记事本": "notepad.exe",
                "chrome": "chrome.exe",
                "谷歌浏览器": "chrome.exe",
                "edge": "msedge.exe",
                "浏览器": "msedge.exe",
                "calc": "calc.exe",
                "计算器": "calc.exe",
                "explorer": "explorer.exe",
                "文件管理器": "explorer.exe",
                "资源管理器": "explorer.exe",
                "cmd": "cmd.exe",
                "命令提示符": "cmd.exe",
                "terminal": "wt.exe",
                "终端": "wt.exe",
                "paint": "mspaint.exe",
                "画图": "mspaint.exe",
                "word": "winword.exe",
                "excel": "excel.exe",
                "powershell": "powershell.exe"
            }
            
            app_key = app_name.lower().strip()
            executable = app_map.get(app_key)
            
            if not executable:
                # 尝试直接执行
                executable = app_name if app_name.endswith(".exe") else f"{app_name}.exe"
            
            # 启动应用
            if args:
                cmd = f"{executable} {args}"
            else:
                cmd = executable
            
            subprocess.Popen(cmd, shell=True)
            time.sleep(1.5)  # 等待应用启动
            
            self.mouth.speak(f"已打开 {app_name}")
            logger.info(f"✅ [GUI] 成功启动: {executable}")
            return f"✅ 已打开 {app_name}"
            
        except Exception as e:
            logger.error(f"打开应用失败: {e}")
            return f"❌ 打开 {app_name} 失败: {str(e)}"
    
    def click_screen_text(self, target_text: str, double_click: bool = False, window_title: str = None) -> str:
        """
        智能寻找屏幕上的指定文字并点击
        
        技术方案：
        1. 优先使用 EasyOCR（快速、准确）
        2. 支持窗口过滤（解决多窗口歧义）
        3. 失败时可选用 GLM-4V 辅助定位
        
        Args:
            target_text: 要点击的文字内容
            double_click: 是否双击
            window_title: 可选，窗口标题关键词（用于过滤多窗口歧义）
        
        Returns:
            执行结果描述
        """
        if not self.config.ENABLE_GUI_CONTROL:
            return "❌ GUI 控制功能未启用，请在配置中开启 ENABLE_GUI_CONTROL。"
        
        logger.info(f"🖱️ [GUI] 正在寻找屏幕上的文字: '{target_text}'" + (f" (窗口: {window_title})" if window_title else ""))
        self.mouth.speak(f"正在寻找 {target_text}...")
        
        try:
            # 方法1：使用 EasyOCR (优先)
            if EASYOCR_AVAILABLE:
                result = self._click_with_ocr(target_text, double_click, window_title)
                if result:
                    return result
                
                logger.warning(f"⚠️ OCR 未找到 '{target_text}'")
                
                # 方法2：GLM-4V 辅助定位 (fallback)
                if self.config.GUI_USE_GLM_FALLBACK and self.vision_client:
                    logger.info("🔄 尝试使用 GLM-4V 辅助定位...")
                    result = self._click_with_glm(target_text, double_click)
                    if result:
                        return result
            else:
                return "❌ EasyOCR 未安装，请运行: pip install easyocr"
            
            return f"❌ 未在屏幕上找到文字 '{target_text}'，请确认：\n1. 文字是否清晰可见\n2. 是否被窗口遮挡\n3. 文字拼写是否正确"
        
        except Exception as e:
            logger.error(f"GUI 点击失败: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ 点击操作失败: {str(e)}"
    
    def _click_with_ocr(self, target_text: str, double_click: bool, window_title: str = None) -> str:
        """使用 EasyOCR 定位并点击（支持窗口过滤）"""
        try:
            # 1. 获取窗口信息（如果指定了 window_title）
            target_window = None
            if window_title and PYGETWINDOW_AVAILABLE:
                try:
                    import pygetwindow as gw
                    
                    # 窗口名称别名映射（支持中英文）
                    window_aliases = {
                        "记事本": ["记事本", "notepad"],
                        "浏览器": ["chrome", "edge", "firefox", "browser", "bilibili", "百度", "google"],
                        "计算器": ["计算器", "calculator"],
                        "资源管理器": ["资源管理器", "explorer", "文件"],
                        "画图": ["画图", "paint"],
                    }
                    
                    # 获取搜索关键词列表
                    search_keywords = [window_title.lower()]
                    for key, aliases in window_aliases.items():
                        if window_title in aliases or key == window_title:
                            search_keywords.extend(aliases)
                            break
                    
                    windows = gw.getAllWindows()
                    for win in windows:
                        win_title_lower = win.title.lower()
                        # 尝试所有关键词
                        for keyword in search_keywords:
                            if keyword in win_title_lower:
                                target_window = win
                                logger.info(f"🪟 [GUI] 找到目标窗口: {win.title}")
                                
                                # 🔧 修复1：如果窗口最小化，先激活它
                                if win.isMinimized:
                                    logger.info(f"📌 窗口已最小化，正在激活...")
                                    try:
                                        win.restore()  # 恢复窗口
                                        time.sleep(0.5)  # 等待窗口恢复
                                        self.mouth.speak(f"已激活窗口")
                                    except Exception as e:
                                        logger.warning(f"⚠️ 窗口激活失败: {e}")
                                elif not win.isActive:
                                    # 窗口可见但不在前台，激活它
                                    try:
                                        win.activate()
                                        time.sleep(0.3)
                                    except Exception as e:
                                        logger.warning(f"⚠️ 窗口激活失败: {e}")
                                
                                logger.info(f"📍 窗口位置: ({win.left}, {win.top}), 大小: {win.width}x{win.height}")
                                break
                        
                        if target_window:
                            break
                    
                    if not target_window:
                        logger.warning(f"⚠️ 未找到窗口: {window_title}，将全屏搜索")
                except Exception as e:
                    logger.warning(f"⚠️ 窗口查找失败: {e}")
            
            # 2. 截图（窗口激活后再截图）
            if target_window:
                time.sleep(0.2)  # 等待窗口完全显示
            screenshot = pyautogui.screenshot()
            screenshot_array = np.array(screenshot)
            
            # 3. 初始化 OCR 阅读器（支持中英文）
            if not getattr(self, '_ocr_reader', None) and EASYOCR_AVAILABLE:
                logger.info("📖 初始化 EasyOCR 阅读器（首次使用可能需要下载模型）...")
                import easyocr
                self._ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            
            # 4. OCR 识别
            logger.info("🔍 正在扫描屏幕文字...")
            results = self._ocr_reader.readtext(screenshot_array)
            
            # 5. 查找目标文字（支持精确+模糊匹配 + 窗口过滤）
            candidates = []
            target_lower = target_text.lower().strip()
            
            for detection in results:
                bbox, text, confidence = detection
                detected_text = text.strip()
                detected_lower = detected_text.lower()
                
                # 🔧 修复2：更精确的匹配策略
                match_score = 0
                
                # 精确匹配（最高优先级）
                if detected_lower == target_lower:
                    match_score = 100
                # 检测词是目标词（包含关系，但避免长串文字）
                elif target_lower in detected_lower:
                    # 如果识别文字远长于目标（如 "文件编辑查看" vs "文件"），降低匹配度
                    length_ratio = len(detected_text) / len(target_text)
                    if length_ratio <= 2.0:  # 长度不超过2倍，认为是合理的
                        match_score = 80 / length_ratio
                    else:
                        # 长度超过2倍，可能是一串文字，降低权重
                        match_score = 30 / length_ratio
                # 目标词包含检测词（反向匹配）
                elif detected_lower in target_lower:
                    match_score = 60
                
                if match_score == 0:
                    continue  # 不匹配，跳过
                
                # 计算坐标
                top_left, top_right, bottom_right, bottom_left = bbox
                
                # 🔧 修复2：更精确的坐标计算
                # 如果是部分匹配，尝试定位到目标词的位置
                if match_score < 100 and target_lower in detected_lower:
                    # 找到目标词在识别文字中的位置
                    target_index = detected_lower.index(target_lower)
                    target_ratio = target_index / len(detected_text) if len(detected_text) > 0 else 0
                    
                    # 根据比例调整 X 坐标（更靠近目标词的起始位置）
                    bbox_width = top_right[0] - top_left[0]
                    offset = bbox_width * target_ratio
                    target_width = bbox_width * (len(target_text) / len(detected_text))
                    
                    center_x = int(top_left[0] + offset + target_width / 2)
                    center_y = int((top_left[1] + bottom_left[1]) / 2)
                else:
                    # 完全匹配，使用中心点
                    center_x = int((top_left[0] + bottom_right[0]) / 2)
                    center_y = int((top_left[1] + bottom_right[1]) / 2)
                
                # 窗口过滤：如果指定了窗口，只选择窗口范围内的文字
                in_window = False
                if target_window:
                    if (target_window.left <= center_x <= target_window.left + target_window.width and
                        target_window.top <= center_y <= target_window.top + target_window.height):
                        in_window = True
                    else:
                        logger.debug(f"⏭️ 跳过窗口外的文字: '{detected_text}' ({center_x}, {center_y})")
                        continue
                
                candidates.append({
                    'text': detected_text,
                    'x': center_x,
                    'y': center_y,
                    'confidence': confidence,
                    'match_score': match_score,
                    'in_window': in_window or (target_window is None)
                })
                
                logger.debug(f"🎯 候选: '{detected_text}' (匹配度: {match_score:.1f}, 置信度: {confidence:.2f}, 坐标: {center_x}, {center_y})")
            
            # 6. 选择最佳候选（优先匹配度、窗口内、高置信度、屏幕上方）
            if not candidates:
                return None  # 未找到
            
            # 排序：匹配度优先 > 窗口内优先 > 置信度高优先 > Y坐标小优先
            candidates.sort(key=lambda c: (-c['match_score'], -c['in_window'], -c['confidence'], c['y']))
            best = candidates[0]
            
            logger.info(f"✅ 找到目标: '{best['text']}' (匹配度: {best['match_score']:.1f}, 置信度: {best['confidence']:.2f})")
            logger.info(f"📍 点击坐标: ({best['x']}, {best['y']})")
            
            if len(candidates) > 1:
                logger.info(f"💡 共有 {len(candidates)} 个候选，已自动选择最佳匹配")
            
            # 7. 移动鼠标并点击（模拟人类行为）
            pyautogui.moveTo(best['x'], best['y'], duration=self.config.GUI_CLICK_DELAY)
            time.sleep(0.1)
            
            if double_click:
                pyautogui.doubleClick()
                action = "双击"
            else:
                pyautogui.click()
                action = "点击"
            
            self.mouth.speak(f"已{action} {target_text}")
            return f"✅ 已{action}屏幕上的 '{best['text']}' (坐标: {best['x']}, {best['y']})"
        
        except Exception as e:
            logger.error(f"OCR 点击失败: {e}")
            import traceback
            traceback.print_exc()
            return None
            
            if len(candidates) > 1:
                logger.info(f"💡 共有 {len(candidates)} 个匹配，已自动选择" + 
                           (" 窗口内的" if target_window else " 置信度最高的"))
            
            # 7. 移动鼠标并点击（模拟人类行为）
            pyautogui.moveTo(best['x'], best['y'], duration=self.config.GUI_CLICK_DELAY)
            time.sleep(0.1)
            
            if double_click:
                pyautogui.doubleClick()
                action = "双击"
            else:
                pyautogui.click()
                action = "点击"
            
            self.mouth.speak(f"已{action} {target_text}")
            return f"✅ 已{action}屏幕上的 '{best['text']}' (坐标: {best['x']}, {best['y']})"
        
        except Exception as e:
            logger.error(f"OCR 点击失败: {e}")
            return None
    
    def _click_with_glm(self, target_text: str, double_click: bool) -> str:
        """使用 GLM-4V 辅助定位（实验性功能）"""
        try:
            logger.info("🤖 请求 GLM-4V 辅助定位...")
            
            # 截取屏幕
            screenshot = pyautogui.screenshot()
            
            # 压缩图片
            screenshot.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            screenshot.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            img_data_uri = f"data:image/jpeg;base64,{img_base64}"
            
            # 构造提示词（让 GLM 描述位置）
            prompt = f"请在这个屏幕截图中找到包含文字'{target_text}'的区域，并描述它的大概位置（如：屏幕左上角、右下角、中间偏上等）。"
            
            response = self.vision_client.chat.completions.create(
                model="glm-4v-flash",  # 使用快速模型
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": img_data_uri}}
                    ]
                }],
                temperature=0.3
            )
            
            location_desc = response.choices[0].message.content
            logger.info(f"🤖 GLM-4V 反馈: {location_desc}")
            
            # 注意：这只是辅助信息，不能精确点击
            return f"ℹ️ GLM-4V 提示：{location_desc}\n（暂不支持自动点击，请手动操作或尝试更清晰的截图）"
        
        except Exception as e:
            logger.error(f"GLM-4V 辅助定位失败: {e}")
            return None
    
    def type_text(self, text: str, press_enter: bool = True) -> str:
        """
        在当前光标位置输入文字
        
        Args:
            text: 要输入的内容
            press_enter: 是否按回车键
        
        Returns:
            执行结果描述
        """
        if not self.config.ENABLE_GUI_CONTROL:
            return "❌ GUI 控制功能未启用。"
        
        logger.info(f"⌨️ [GUI] 正在输入文字: {text[:20]}...")
        self.mouth.speak("正在输入...")
        
        try:
            # 使用剪贴板粘贴（避免输入法干扰）
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            
            if press_enter:
                time.sleep(0.1)
                pyautogui.press('enter')
            
            action = "已发送" if press_enter else "已输入"
            self.mouth.speak(f"{action}")
            return f"✅ {action}: {text}"
        
        except Exception as e:
            logger.error(f"文字输入失败: {e}")
            return f"❌ 输入失败: {str(e)}"

    def click_by_description(self, description: str, double_click: bool = False) -> str:
        """
        【YOLO-World 零样本视觉识别】通过自然语言描述来寻找并点击屏幕上的 UI 元素
        
        Args:
            description: 物体的英文描述（如 'red button', 'chrome icon', 'search box'）
            double_click: 是否双击
        
        Returns:
            执行结果描述
        """
        if not self.config.ENABLE_GUI_CONTROL:
            return "❌ GUI 控制功能未启用。"
        
        if not self.yolo_world:
            return "❌ YOLO-World 模型未加载。请运行: pip install ultralytics"
        
        logger.info(f"👁️ [YOLO] 正在全屏寻找: '{description}'")
        self.mouth.speak(f"正在寻找 {description}")
        
        try:
            # 1. 设置检测目标（YOLO-World 的核心特性：动态类别）
            self.yolo_world.set_classes([description])
            
            # 2. 截取屏幕
            screenshot = pyautogui.screenshot()
            screenshot_array = np.array(screenshot)
            
            # 3. 推理检测（conf=0.1 平衡阈值，兼顾精度和召回率）
            results = self.yolo_world.predict(screenshot_array, conf=0.1, verbose=False)
            
            # 4. 解析结果
            if len(results[0].boxes) > 0:
                # 按置信度排序，取最高的
                boxes = results[0].boxes
                confidences = boxes.conf.cpu().numpy()
                best_idx = confidences.argmax()
                
                box = boxes[best_idx]
                coords = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                confidence = confidences[best_idx]
                
                # 计算中心点
                x1, y1, x2, y2 = coords
                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)
                
                # 置信度过低时发出警告
                if confidence < 0.3:
                    logger.warning(f"⚠️ 置信度较低 ({confidence:.2%})，可能不准确")
                
                logger.info(f"✅ 找到目标！置信度: {confidence:.2%}, 坐标: ({center_x}, {center_y})")
                
                # 5. 平滑移动鼠标并点击
                pyautogui.moveTo(center_x, center_y, duration=0.3)
                time.sleep(0.1)
                
                if double_click:
                    pyautogui.doubleClick()
                    action = "双击"
                else:
                    pyautogui.click()
                    action = "点击"
                
                self.mouth.speak(f"已{action}")
                return f"✅ 已{action} '{description}' (坐标: {center_x}, {center_y}, 置信度: {confidence:.2%})"
            
            else:
                logger.warning(f"❌ 未找到: '{description}'")
                self.mouth.speak("没有找到目标")
                return f"❌ 抱歉，在屏幕上没有找到 '{description}'。\n提示: 请确保目标在屏幕上可见，或尝试换一个描述词（建议用英文，如 'red button'）。"

        
        except Exception as e:
            logger.error(f"视觉识别失败: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ 视觉识别失败: {str(e)}"

    # ========================
    # 📺 视频搜索
    # ========================
    def open_video(self, keyword: str) -> str:
        logger.info(f"📺 正在搜索视频: {keyword}")
        self.mouth.speak(f"正在帮你搜索 {keyword}...")

        try:
            url = f"https://search.bilibili.com/all?keyword={keyword}"
            webbrowser.open(url)
            return f"✅ 已打开B站搜索: {keyword}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"

    # ========================
    # 🌐 网站打开
    # ========================
    def open_website(self, site_name: str) -> str:
        logger.info(f"🌐 正在打开: {site_name}")
        self.mouth.speak(f"正在为你打开 {site_name}...")

        try:
            url = self.WEBSITE_REGISTRY.get(site_name)
            if url:
                webbrowser.open(url, new=2)
                return f"✅ 已打开: {site_name}"
            return f"❌ 未知网站: {site_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"

    # ========================
    # 🖥️ 系统 Shell
    # ========================
    def execute_shell(self, command: str, background: bool = False) -> str:
        """执行 Shell 命令 (PowerShell)"""
        logger.info(f"🐚 执行Shell指令: {command} (后台={background})")
        self.mouth.speak("正在执行指令...")
        
        try:
            # 使用列表形式调用 PowerShell
            cmd_args = ["powershell", "-Command", command]
            
            if background:
                # 后台运行 (不等待结果)
                subprocess.Popen(cmd_args, creationflags=subprocess.CREATE_NO_WINDOW)
                return f"✅ 指令已在后台启动: {command}"
            else:
                # 同步运行 (等待结果)
                result = subprocess.run(
                    cmd_args,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                output = result.stdout.strip()
                error = result.stderr.strip()
                
                if result.returncode == 0:
                    return f"✅ 执行成功:\n{output[:1000]}"
                else:
                    return f"❌ 执行出错:\n{error}\n(Output: {output})"
                    
        except Exception as e:
            return f"❌ Shell 执行失败: {str(e)}"

    # ========================
    # 🔊 音量控制
    # ========================
    def control_volume(self, action: str, level: int = None) -> str:
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

    # ========================
    # 🚀 软件启动
    # ========================
    def find_app_by_alias(self, text: str) -> tuple:
        text_lower = text.lower()
        for app_name, config in self.APP_REGISTRY.items():
            for alias in config["aliases"]:
                if alias.lower() in text_lower:
                    return app_name, config["cmd"]
        return None, None

    def open_app(self, text: str) -> bool:
        app_name, cmd = self.find_app_by_alias(text)

        if app_name:
            logger.info(f"🚀 启动: {app_name}")
            self.mouth.speak(f"正在打开{app_name}...")
            try:
                os.system(cmd)
                return True
            except Exception as e:
                logger.error(f"打开失败: {e}")
                self.mouth.speak(f"打开{app_name}失败了")
                return False
        return False

    def open_tool(self, tool_name: str) -> str:
        if self.open_app(tool_name):
            return "✅ 已打开"

        self.mouth.speak(f"正在打开{tool_name}...")
        try:
            os.system(f"start {tool_name}")
            return f"✅ 尝试启动: {tool_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"

    # ========================
    # ⏰ 定时提醒
    # ========================
    def set_reminder(self, content: str, target_time: str, auto_action: dict = None) -> str:
        """
        设置提醒 (IDE版: 笔记 + 弹窗 + 自动执行)
        [升级] v1.2.0 支持 auto_action 自动执行操作
        """
        try:
            datetime.datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S")
            logger.info(f"⏰ 设定提醒: {target_time} - {content}")
            
            # 构建提醒任务
            reminder_task = {
                "time": target_time, 
                "content": content
            }
            
            # 如果有自动执行动作，添加到任务中
            if auto_action and isinstance(auto_action, dict):
                reminder_task["auto_action"] = auto_action
                action_desc = f"（到时将自动执行: {auto_action.get('tool_name', '未知操作')}）"
                logger.info(f"⚡ 附带自动操作: {auto_action}")
                self.mouth.speak(f"好的，已设置提醒，会在 {target_time} 叫你，并自动帮你执行。")
            else:
                action_desc = ""
                self.mouth.speak(f"好的，已设置提醒，会在 {target_time} 叫你。")
            
            self.reminders.append(reminder_task)
            self.save_reminders_to_disk()
            
            # 自动记笔记
            self.take_note(f"设定提醒 {target_time}: {content}{action_desc}", category="待办")
            
            return f"✅ 已设定提醒: {target_time} {content}{action_desc}"
        except ValueError:
            return f"❌ 时间格式错误"

    def check_reminders(self):
        """
        检查并触发到期的提醒
        [升级] v1.2.0 支持自动执行 auto_action
        """
        current_time = datetime.datetime.now()
        active_reminders = []
        is_changed = False
        
        for task in self.reminders:
            task_time = datetime.datetime.strptime(task["time"], "%Y-%m-%d %H:%M:%S")
            
            if current_time >= task_time:
                logger.info(f"⏰ 触发提醒: {task['content']}")
                self.mouth.send_to_unity("Surprised")
                
                # 第一步：语音提醒
                self.mouth.speak(f"指挥官，{task['content']}")
                
                # 弹窗通知
                self._show_toast("Fuguang IDE 提醒", task['content'])
                
                # 第二步：检查是否有自动执行动作
                if "auto_action" in task and task["auto_action"]:
                    action = task["auto_action"]
                    tool_name = action.get("tool_name", "")
                    arguments = action.get("arguments", {})
                    
                    logger.info(f"⚡ 自动执行操作: {tool_name} -> {arguments}")
                    
                    # 第三步：调用对应工具
                    try:
                        result = self.execute_tool(tool_name, arguments)
                        logger.info(f"✅ 自动操作完成: {result}")
                        self.mouth.speak("已自动帮你执行~")
                    except Exception as e:
                        logger.error(f"❌ 自动操作失败: {e}")
                        self.mouth.speak("自动操作出了点问题...")
                
                is_changed = True
            else:
                active_reminders.append(task)
        
        if is_changed:
            self.reminders = active_reminders
            self.save_reminders_to_disk()

    # ========================
    # 📝 智能笔记
    # ========================
    def take_note(self, content: str, category: str = "随记") -> str:
        icons = {
            "工作": "💼", "生活": "🏠", "灵感": "💡",
            "待办": "📌", "学习": "📚", "代码": "💻", "随记": "📝"
        }
        icon = icons.get(category, "📝")

        month_str = datetime.datetime.now().strftime("%Y-%m")
        filename = self.config.NOTES_DIR / f"Fuguang_Notes_{month_str}.md"
        timestamp = datetime.datetime.now().strftime("%m-%d %H:%M")

        is_new_file = not filename.exists()

        try:
            with open(filename, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(f"# 📅 {month_str} 扶光笔记本\n\n")
                    f.write("| 时间 | 分类 | 内容 |\n")
                    f.write("|:---:|:---:|---|\n")

                clean_content = content.replace("\n", " ").replace("|", "/")
                row = f"| {timestamp} | {icon} {category} | {clean_content} |\n"
                f.write(row)

            logger.info(f"📝 已归档至 {filename} [{category}]")
            self.mouth.speak(f"已记录到桌面笔记本，分类是{category}。")

            # 自动打开笔记文件
            try:
                os.startfile(str(filename))
                logger.info(f"📂 已打开笔记文件")
            except Exception as e:
                logger.warning(f"打开文件失败: {e}")

            return f"✅ 已记录到桌面: {filename.name}"

        except Exception as e:
            logger.error(f"记录失败: {e}")
            return f"记录失败: {str(e)}"

    # ========================
    # 💻 代码生成
    # ========================
    def write_code(self, filename: str, code_content: str) -> str:
        """
        代码生成 - 保存到项目 generated/ 文件夹
        """
        if not filename.endswith(".py"):
            filename += ".py"

        full_path = self.config.GENERATED_DIR / filename

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(code_content)

            logger.info(f"💾 代码已生成: {full_path}")
            self.mouth.speak(f"代码已生成：{filename}，正在为你打开。")

            # 尝试用 VSCode 打开，失败则用默认程序
            try:
                result = subprocess.run(["code", str(full_path)],
                                        capture_output=True, timeout=5)
                if result.returncode != 0:
                    raise Exception("VSCode 启动失败")
                logger.info(f"📂 已用 VSCode 打开")
            except Exception:
                try:
                    os.startfile(str(full_path))
                    logger.info(f"📂 已用默认程序打开")
                except Exception as e:
                    logger.warning(f"打开文件失败: {e}")

            return f"✅ 代码已生成: generated/{filename}"

        except Exception as e:
            logger.error(f"代码生成失败: {e}")
            return f"代码生成失败: {str(e)}"

    # ========================
    # 🚀 代码执行器 (带安全锁)
    # ========================
    def run_code(self, filename: str) -> str:
        """
        运行 generated/ 目录下的 Python 脚本
        带 Human-in-the-loop 安全确认机制
        """
        import sys
        
        if not filename.endswith(".py"):
            filename += ".py"
            
        file_path = self.config.GENERATED_DIR / filename
        
        # 检查文件是否存在
        if not file_path.exists():
            return f"❌ 找不到文件: {filename}，请先使用 write_code 生成代码。"
        
        # 🛡️ 安全锁：请求指挥官确认
        print(f"\n{'='*50}")
        print(f"🚨 [安全警告] AI 请求运行代码")
        print(f"{'='*50}")
        print(f"📂 文件: {file_path}")
        print(f"\n📄 代码预览:")
        print("-" * 40)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code_content = f.read()
                # 显示前 500 字符
                preview = code_content[:500]
                if len(code_content) > 500:
                    preview += f"\n... (共 {len(code_content)} 字符)"
                print(preview)
        except Exception as e:
            print(f"(无法预览: {e})")
        print("-" * 40)
        
        # 请求确认
        print("\n🛑 是否允许运行？")
        print("   [y] 允许  [n] 拒绝  [v] 用 VSCode 打开查看")
        user_confirm = input("请输入选择: ").strip().lower()
        
        if user_confirm == 'v':
            try:
                subprocess.run(["code", str(file_path)], capture_output=True, timeout=5)
            except:
                os.startfile(str(file_path))
            return "📂 已打开代码供您查看，请确认后手动运行。"
        
        if user_confirm != 'y':
            logger.info("❌ 指挥官拒绝了代码执行请求")
            return "❌ 指挥官拒绝了代码执行请求。"
        
        # 执行代码
        logger.info(f"🚀 正在运行: {file_path}")
        self.mouth.speak("正在执行代码...")
        
        try:
            result = subprocess.run(
                [sys.executable, str(file_path)],
                capture_output=True,
                text=True,
                timeout=60,  # 60秒超时保护
                cwd=str(self.config.GENERATED_DIR)  # 在 generated 目录下运行
            )
            
            output = result.stdout
            error = result.stderr
            
            if result.returncode == 0:
                logger.info(f"✅ 代码执行成功")
                response = f"✅ 代码执行成功！"
                if output:
                    response += f"\n📤 输出结果:\n{output[:500]}"
                return response
            else:
                logger.error(f"❌ 代码执行出错: {error}")
                return f"❌ 代码执行出错:\n{error[:500]}"
                
        except subprocess.TimeoutExpired:
            logger.error("⏰ 代码执行超时")
            return "⏰ 代码执行超时（超过60秒），已强制终止。"
        except Exception as e:
            logger.error(f"运行失败: {e}")
            return f"❌ 运行失败: {str(e)}"

    # ========================
    # 🔧 本地快捷指令
    # ========================
    def get_time(self) -> str:
        return f"现在是 {datetime.datetime.now().strftime('%H点%M分')}。"

    def get_date(self) -> str:
        return f"今天是 {datetime.datetime.now().strftime('%Y年%m月%d日')}。"

    def check_battery(self) -> str:
        b = psutil.sensors_battery()
        return f"电量 {b.percent}%" if b else "无电池信息"

    def check_status(self) -> str:
        return f"CPU {psutil.cpu_percent()}%"

    # ========================
    # 🔧 工具执行器
    # ========================
    def execute_tool(self, func_name: str, func_args: dict) -> str:
        """统一的工具执行入口"""
        if func_name == "search_web":
            return self.search_web(func_args.get("query", ""))
        elif func_name == "set_reminder":
            return self.set_reminder(
                func_args.get("content", ""),
                func_args.get("target_time", ""),
                func_args.get("auto_action", None)  # [升级] v1.2.0 支持自动执行
            )
        elif func_name == "open_video":
            return self.open_video(func_args.get("keyword", ""))
        elif func_name == "open_website":
            return self.open_website(func_args.get("site_name", ""))
        elif func_name == "control_volume":
            return self.control_volume(
                func_args.get("action", "up"),
                func_args.get("level", 1)
            )
        elif func_name == "take_note":
            return self.take_note(
                func_args.get("content", ""),
                func_args.get("category", "随记")
            )
        elif func_name == "write_code":
            return self.write_code(
                func_args.get("filename", "script.py"),
                func_args.get("code_content", "")
            )
        elif func_name == "open_tool":
            return self.open_tool(func_args.get("tool_name", ""))
        elif func_name == "save_memory":
            content = func_args.get("content", "")
            importance = func_args.get("importance", 3)
            self.brain.memory_system.add_memory(content, importance)
            return f"✅ 已存入长期记忆: {content}"
        elif func_name == "execute_shell":
            return self.execute_shell(
                func_args.get("command", ""),
                func_args.get("background", False)
            )
        elif func_name == "run_code":
            return self.run_code(func_args.get("filename", ""))
        elif func_name == "read_web_page":
            return self.read_web_page(func_args.get("url", ""))
        elif func_name == "analyze_screen_content":
            return self.analyze_screen_content(func_args.get("question", ""))
        elif func_name == "analyze_image_file":
            return self.analyze_image_file(
                func_args.get("image_path", ""),
                func_args.get("question", "")
            )
        elif func_name == "get_vision_history":
            return self.get_vision_history()
        elif func_name == "open_application":
            return self.open_application(
                func_args.get("app_name", ""),
                func_args.get("args")
            )
        elif func_name == "click_screen_text":
            return self.click_screen_text(
                func_args.get("target_text", ""),
                func_args.get("double_click", False),
                func_args.get("window_title")
            )
        elif func_name == "type_text":
            return self.type_text(
                func_args.get("text", ""),
                func_args.get("press_enter", True)
            )
        elif func_name == "click_by_description":
            return self.click_by_description(
                func_args.get("description", ""),
                func_args.get("double_click", False)
            )
        else:
            return f"未知工具: {func_name}"
