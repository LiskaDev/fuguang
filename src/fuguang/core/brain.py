
import json
import os
import time
import datetime
import logging
import httpx
from openai import OpenAI
from .config import ConfigManager
from .mouth import Mouth
from .. import memory as fuguang_memory

logger = logging.getLogger("Fuguang")

class Brain:
    """
    思考与记忆角色
    职责：AI 客户端、聊天历史、记忆、System Prompt
    """

    MAX_HISTORY = 20
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

        # 短期对话历史
        self.chat_history = []

        # 状态
        self.IS_CREATION_MODE = False

    def load_memory(self) -> dict:
        """加载短期记忆"""
        if not self.config.MEMORY_FILE.exists():
            return {"user_profile": {}, "short_term_summary": "暂无记录"}
        try:
            with open(self.config.MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"user_profile": {}, "short_term_summary": "文件损坏"}

    def save_memory(self, memory_data: dict):
        """保存短期记忆"""
        try:
            with open(self.config.MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=4)
            logger.info("💾 记忆已保存")
        except Exception as e:
            logger.error(f"记忆保存失败: {e}")

    def get_system_prompt(self, dynamic_context: dict = None) -> str:
        """
        生成动态 System Prompt
        
        Args:
            dynamic_context: 实时感知数据，包含:
                - app: 当前活动窗口标题
                - clipboard: 剪贴板内容
                - user_present: 用户是否在座（可选）
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.datetime.now().weekday()]
        current_date = f"{datetime.datetime.now().strftime('%Y-%m-%d')} {weekday}"
        mode_status = "🔓已解锁" if self.IS_CREATION_MODE else "🔒已锁定"

        memory = self.load_memory()
        user_profile = json.dumps(memory.get("user_profile", {}), ensure_ascii=False)
        summary = memory.get("short_term_summary", "暂无")

        # 构建感知信息（如果提供了）
        perception_section = ""
        if dynamic_context:
            app_name = dynamic_context.get("app", "未知")
            clipboard = dynamic_context.get("clipboard", "无")
            user_present = dynamic_context.get("user_present", None)
            visual_status = ""
            if user_present is not None:
                visual_status = "指挥官在座位上" if user_present else "座位无人"
            
            perception_section = f"""

【实时感知状态】
- 用户正在操作: {app_name}
- 剪贴板内容: {clipboard}
{f'- 视觉状态: {visual_status}' if visual_status else ''}
（当用户问"这个"、"这段代码"、"帮我看看"时，指的就是剪贴板内容；当用户问"我在干嘛"时请根据当前窗口回答）
"""

        try:
            with open(self.config.SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                template = f.read()
            prompt = template.format(
                current_time=current_time,
                current_date=current_date,
                mode_status=mode_status,
                history_summary=f"【用户档案】{user_profile}\n【上次话题摘要】{summary}"
            )
            # 追加感知信息
            return prompt + perception_section
        except Exception:
            return f"你是沈扶光，说话简洁。[Neutral]{perception_section}"

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

    def summarize_and_exit(self):
        """整理记忆并退出"""
        logger.info("正在整理今日记忆...")
        self.mouth.speak("指挥官，正在同步记忆数据...")

        if len(self.chat_history) < 2:
            self.mouth.speak("晚安。")
            os._exit(0)

        conversation_text = ""
        for msg in self.chat_history:
            role = "阿鑫" if msg["role"] == "user" else "扶光"
            conversation_text += f"{role}: {msg['content']}\n"

        try:
            summary_prompt = [
                {"role": "system", "content": "请简要总结以下对话中的关键信息。100字以内。"},
                {"role": "user", "content": conversation_text}
            ]
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=summary_prompt,
                max_tokens=200,
                temperature=0.5
            )
            new_summary = response.choices[0].message.content
            logger.info(f"📝 今日日记: {new_summary}")

            mem = self.load_memory()
            old = mem.get("short_term_summary", "")
            mem["short_term_summary"] = f"{new_summary} | (旧: {old[:50]}...)"
            self.save_memory(mem)

        except Exception as e:
            logger.error(f"总结失败: {e}")

        self.mouth.speak("记忆同步完成，晚安。")
        time.sleep(1)
        os._exit(0)
