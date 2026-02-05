
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
from .config import ConfigManager
from .mouth import Mouth
from .config import ConfigManager
from .mouth import Mouth
from .brain import Brain

logger = logging.getLogger("Fuguang")

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
        self.brain = brain
        self.reminders = self.load_reminders_from_disk()
    
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
        elif func_name == "run_code":
            return self.run_code(func_args.get("filename", ""))
        elif func_name == "read_web_page":
            return self.read_web_page(func_args.get("url", ""))
        else:
            return f"未知工具: {func_name}"
