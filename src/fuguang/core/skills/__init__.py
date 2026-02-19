"""
skills/ 包 — SkillManager 组合器
通过 Mixin 多继承，将 Base / Vision / GUI / Browser / System / Memory / MCP 组合在一起，
对外保持完全一致的 API：self.skills.execute_tool / self.skills.get_tools_schema 等。
"""
import datetime, logging

from .base import BaseSkillMixin
from .vision import VisionSkills
from .gui import GUISkills
from .browser import BrowserSkills
from .system import SystemSkills
from .memory import MemorySkills
from .skill_mcp import MCPSkills
from .email import EmailSkills

logger = logging.getLogger("fuguang.skills")


class SkillManager(
    BaseSkillMixin,
    VisionSkills,
    GUISkills,
    BrowserSkills,
    SystemSkills,
    MemorySkills,
    MCPSkills,
    EmailSkills,
):
    """
    技能管理器（协调器）
    通过 Mixin 组合继承了所有技能领域的方法和 Schema。
    """

    def __init__(self, config, mouth, brain):
        # 只调用 BaseSkillMixin.__init__，它负责全部共享初始化
        BaseSkillMixin.__init__(self, config, mouth, brain)

    # ========================
    # 📋 工具 Schema 动态生成
    # ========================
    def get_tools_schema(self):
        """
        动态生成完整工具 Schema。
        set_reminder 需要注入当前时间，因此单独动态构建。
        """
        now = datetime.datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        set_reminder_tool = {
            "type": "function",
            "function": {
                "name": "set_reminder",
                "description": f"设置定时提醒，支持自动执行操作。【当前时间是 {ts}】\n"
                    f"请根据此时间计算用户所说的相对时间，转换为 YYYY-MM-DD HH:MM:SS 格式。\n"
                    f"⚠️ 如果用户说\"提醒我打开XX\"，必须同时填写 auto_action 字段！",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_time": {
                            "type": "string",
                            "description": f"目标触发时间 YYYY-MM-DD HH:MM:SS（当前: {ts}）"
                        },
                        "content": {
                            "type": "string",
                            "description": "提醒事项内容"
                        },
                        "auto_action": {
                            "type": "object",
                            "description": "【可选】到时自动执行的操作",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "enum": ["open_website", "open_video", "open_tool", "control_volume"],
                                    "description": "要自动执行的工具"
                                },
                                "arguments": {
                                    "type": "object",
                                    "description": "传递给工具的参数"
                                }
                            },
                            "required": ["tool_name", "arguments"]
                        }
                    },
                    "required": ["content", "target_time"]
                }
            }
        }

        # 合并各 Mixin 的静态 Schema + 动态 set_reminder
        all_tools = []
        all_tools.extend(getattr(self, '_VISION_TOOLS', []))
        all_tools.extend(getattr(self, '_GUI_TOOLS', []))
        all_tools.extend(getattr(self, '_BROWSER_TOOLS', []))
        all_tools.extend(getattr(self, '_SYSTEM_TOOLS', []))
        all_tools.extend(getattr(self, '_MEMORY_TOOLS', []))
        all_tools.extend(getattr(self, '_MCP_TOOLS', []))
        all_tools.extend(getattr(self, '_EMAIL_TOOLS', []))
        all_tools.append(set_reminder_tool)
        return all_tools

    # ========================
    # ⚙️ 工具执行统一入口
    # ========================
    def execute_tool(self, func_name: str, func_args: dict) -> str:
        """统一的工具执行入口"""
        # --- Browser ---
        if func_name == "search_web":
            return self.search_web(func_args.get("query", ""))
        elif func_name == "read_web_page":
            return self.read_web_page(func_args.get("url", ""))
        elif func_name == "open_website":
            return self.open_website(func_args.get("site_name", ""))
        elif func_name == "open_video":
            return self.open_video(func_args.get("keyword", ""))
        elif func_name == "browse_website":
            return self.browse_website(func_args.get("url", ""), func_args.get("take_screenshot", False))

        # --- Vision ---
        elif func_name == "analyze_screen_content":
            return self.analyze_screen_content(func_args.get("question", ""))
        elif func_name == "analyze_image_file":
            return self.analyze_image_file(func_args.get("image_path", ""), func_args.get("question", ""))
        elif func_name == "get_vision_history":
            return self.get_vision_history()

        # --- GUI ---
        elif func_name == "open_application":
            return self.open_application(func_args.get("app_name", ""), func_args.get("args"))
        elif func_name == "click_screen_text":
            return self.click_screen_text(func_args.get("target_text", ""), func_args.get("double_click", False), func_args.get("window_title"))
        elif func_name == "type_text":
            return self.type_text(func_args.get("text", ""), func_args.get("press_enter", True))
        elif func_name == "click_by_description":
            return self.click_by_description(func_args.get("description", ""), func_args.get("double_click", False))
        elif func_name == "list_ui_elements":
            return self.list_ui_elements(func_args.get("window_title", ""))
        elif func_name == "send_hotkey":
            return self.send_hotkey(func_args.get("keys", []))

        # --- System ---
        elif func_name == "create_file_directly":
            return self.create_file_directly(func_args.get("file_path", ""), func_args.get("content", ""))
        elif func_name == "execute_shell":
            return self.execute_shell(func_args.get("command", ""), func_args.get("background", False))
        elif func_name == "execute_shell_command":
            return self.execute_shell_command(func_args.get("command", ""), func_args.get("timeout", 60))
        elif func_name == "launch_application":
            return self.launch_application(func_args.get("app_name", ""))
        elif func_name == "list_installed_applications":
            return self.list_installed_applications()
        elif func_name == "control_volume":
            return self.control_volume(func_args.get("action", "up"), func_args.get("level", 1))
        elif func_name == "take_note":
            return self.take_note(func_args.get("content", ""), func_args.get("category", "随记"))
        elif func_name == "write_code":
            return self.write_code(func_args.get("filename", "script.py"), func_args.get("code_content", ""))
        elif func_name == "run_code":
            return self.run_code(func_args.get("filename", ""))
        elif func_name == "open_tool":
            return self.open_tool(func_args.get("tool_name", ""))
        elif func_name == "set_reminder":
            return self.set_reminder(func_args.get("content", ""), func_args.get("target_time", ""), func_args.get("auto_action", None))
        elif func_name == "toggle_auto_execute":
            return self.toggle_auto_execute(func_args.get("enable", True))
        elif func_name == "transcribe_media_file":
            return self.transcribe_media_file(func_args.get("file_path", ""))
        elif func_name == "listen_to_system_audio":
            return self.listen_to_system_audio(func_args.get("duration", 30))

        # --- Memory ---
        elif func_name == "save_to_long_term_memory":
            return self.save_to_long_term_memory(func_args.get("content", ""), func_args.get("category", "general"))
        elif func_name == "save_memory":
            content = func_args.get("content", "")
            importance = func_args.get("importance", 3)
            self.brain.memory_system.add_memory(content, importance)
            return f"✅ 已存入长期记忆: {content}"
        elif func_name == "ingest_knowledge_file":
            return self.ingest_knowledge_file(func_args.get("file_path", ""))
        elif func_name == "forget_knowledge":
            return self.forget_knowledge(func_args.get("source_name", ""))
        elif func_name == "forget_memory":
            return self.forget_memory(func_args.get("keyword", ""))
        elif func_name == "list_learned_files":
            return self.list_learned_files()
        elif func_name == "remember_recipe":
            return self.remember_recipe(func_args.get("trigger", ""), func_args.get("solution", ""))
        elif func_name == "recall_recipe":
            return self.recall_recipe(func_args.get("query", ""))
        elif func_name == "export_recipes_to_obsidian":
            return self.export_recipes_to_obsidian()

        # --- Email ---
        elif func_name == "check_email":
            return self.check_email(include_spam=func_args.get("include_spam", False))
        elif func_name == "read_email":
            return self.read_email(
                index=func_args.get("index", 1),
                show_full=func_args.get("show_full", False)
            )
        elif func_name == "config_email_filter":
            return self.config_email_filter(
                action=func_args.get("action", "list"),
                category=func_args.get("category", ""),
                value=func_args.get("value", "")
            )
        elif func_name == "search_email":
            return self.search_email(
                sender=func_args.get("sender", ""),
                keyword=func_args.get("keyword", ""),
                days_back=func_args.get("days_back", 7),
                max_results=func_args.get("max_results", 10)
            )
        elif func_name == "reply_email":
            return self.reply_email(
                index=func_args.get("index", 1),
                content=func_args.get("content", ""),
                confirm=func_args.get("confirm", False)
            )

        # --- MCP (外部工具服务器) ---
        elif func_name.startswith("mcp_"):
            return self.execute_mcp_tool(func_name, func_args)

        else:
            return f"未知工具: {func_name}"

    # ========================
    # 🔧 向后兼容
    # ========================
    def load_reminders_from_disk(self):
        """向后兼容：旧代码中可能仍引用此方法名"""
        return self._load_reminders_from_disk()

    def save_reminders_to_disk(self):
        """向后兼容"""
        return self._save_reminders_to_disk()
