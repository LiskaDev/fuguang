"""
📱 QQ 消息桥接 (QQ Message Bridge)
职责：通过 NapCat (OneBot v11) 连接 QQ，实现 QQ 消息 ↔ 扶光 Brain 的双向通信

架构：
  NapCat WS Server (port 8080) ←── QQBridge (WS Client) ──→ Brain + Skills

消息流程：
  1. NapCat 推送 OneBot 事件 → QQBridge 解析
  2. 提取私聊/群聊(@机器人)消息 → 调用 Brain.chat (含工具调用)
  3. 回复文本通过 WS 发回 NapCat → 投递到 QQ

启动方式：
  - NervousSystem.__init__ 中自动启动（QQ_ENABLED=true 时）
  - 后台 daemon 线程运行 asyncio 事件循环
"""

import asyncio
import json
import re
import time
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger("Fuguang.QQ")


class QQBridge:
    """
    NapCat OneBot v11 桥接层

    连接 NapCat 的 WebSocket Server，接收 QQ 消息，
    调用扶光 Brain 处理后回复。
    """

    def __init__(self, config, brain, skills, mouth=None):
        """
        Args:
            config: CoreConfig / ConfigManager 实例
            brain:  Brain 实例（对话 + 工具调用）
            skills: SkillManager 实例（工具 Schema + 执行）
            mouth:  Mouth 实例（可选，用于本地语音播报 QQ 消息）
        """
        self.brain = brain
        self.skills = skills
        self.mouth = mouth
        self.config = config

        # NapCat WebSocket 地址
        self.ws_url = f"ws://127.0.0.1:{config.NAPCAT_WS_PORT}"
        self.self_id: Optional[int] = None  # 机器人 QQ 号（从事件中获取）

        # 消息去重
        self._processed_msgs = set()
        self._MAX_CACHE = 500

        # 运行状态
        self._running = False
        self._thread: Optional[threading.Thread] = None

        logger.info(f"📱 [QQ] QQBridge 初始化完成，目标: {self.ws_url}")

    # ==================================================
    # 启动 / 停止
    # ==================================================

    def start(self):
        """在后台 daemon 线程中启动 QQ 桥接"""
        if self._running:
            logger.warning("📱 [QQ] QQBridge 已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="QQBridge")
        self._thread.start()
        logger.info("📱 [QQ] QQBridge 后台线程已启动")

    def stop(self):
        """停止桥接"""
        self._running = False
        logger.info("📱 [QQ] QQBridge 已停止")

    def _run_loop(self):
        """后台线程入口：运行 asyncio 事件循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_loop())
        except Exception as e:
            logger.error(f"📱 [QQ] 事件循环异常退出: {e}")
        finally:
            loop.close()

    # ==================================================
    # WebSocket 主循环
    # ==================================================

    async def _ws_loop(self):
        """WebSocket 客户端主循环（自动重连）"""
        try:
            import websockets
        except ImportError:
            logger.error("📱 [QQ] 缺少 websockets 库，请安装: pip install websockets")
            return

        while self._running:
            try:
                logger.info(f"📱 [QQ] 正在连接 NapCat: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("📱 [QQ] ✅ 已连接到 NapCat!")
                    if self.mouth:
                        self.mouth.speak("QQ消息通道已连接")

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw)
                            await self._handle_event(ws, data)
                        except json.JSONDecodeError:
                            pass
                        except Exception as e:
                            logger.error(f"📱 [QQ] 处理消息异常: {e}")

            except Exception as e:
                if self._running:
                    logger.warning(f"📱 [QQ] 连接断开: {e}，5秒后重连...")
                    await asyncio.sleep(5)

    # ==================================================
    # 事件处理
    # ==================================================

    async def _handle_event(self, ws, data: dict):
        """处理 OneBot v11 事件"""
        post_type = data.get("post_type")

        # 获取机器人自身 QQ 号
        if "self_id" in data and self.self_id is None:
            self.self_id = data["self_id"]
            logger.info(f"📱 [QQ] 机器人 QQ: {self.self_id}")

        # 心跳 / 生命周期事件 → 跳过
        if post_type == "meta_event":
            return

        # 只处理消息事件
        if post_type != "message":
            return

        # 消息去重
        msg_id = data.get("message_id")
        if msg_id:
            if msg_id in self._processed_msgs:
                return
            self._processed_msgs.add(msg_id)
            if len(self._processed_msgs) > self._MAX_CACHE:
                to_remove = list(self._processed_msgs)[:self._MAX_CACHE // 2]
                for mid in to_remove:
                    self._processed_msgs.discard(mid)

        # 忽略自己的消息
        user_id = data.get("user_id")
        if user_id == self.self_id:
            return

        msg_type = data.get("message_type")  # "private" 或 "group"
        message = data.get("message", [])
        sender = data.get("sender", {})
        user_name = sender.get("nickname", str(user_id))

        # 提取纯文本
        text = self._extract_text(message)

        # 群消息：只有 @机器人 时才回复
        if msg_type == "group":
            if not self._check_at_me(message):
                return
            text = re.sub(r'\s+', ' ', text).strip()
            group_id = data.get("group_id")
            logger.info(f"📱 [QQ] 群 {group_id} - {user_name}: {text[:80]}")
        elif msg_type == "private":
            logger.info(f"📱 [QQ] 私聊 - {user_name}({user_id}): {text[:80]}")
        else:
            return

        if not text:
            text = "你好"

        # ========================================
        # 调用扶光 Brain 处理（含记忆 + 工具调用）
        # ========================================
        try:
            reply = await asyncio.to_thread(
                self._process_with_brain, text, user_name
            )
        except Exception as e:
            logger.error(f"📱 [QQ] Brain 处理异常: {e}")
            reply = "抱歉指挥官，我处理消息时遇到了问题..."

        # 格式化回复（QQ 不支持 Markdown）
        reply = self._format_for_qq(reply)

        # 发送回复
        if msg_type == "private":
            await self._send_private_msg(ws, user_id, reply)
        else:
            await self._send_group_msg(ws, data.get("group_id"), reply)

    # ==================================================
    # Brain 对接
    # ==================================================

    def _process_with_brain(self, user_input: str, user_name: str) -> str:
        """
        调用 Brain 处理消息（同步，在线程池中运行）

        复用 NervousSystem._handle_ai_response 的核心逻辑：
        1. 检索记忆
        2. 构建 system prompt
        3. 调用 Brain.chat（含工具调用）
        """
        # 1. 检索相关记忆
        memory_text = ""
        try:
            if hasattr(self.skills, 'memory') and self.skills.memory:
                memory_context = self.skills.memory.get_memory_context(user_input, n_results=3)
                if memory_context:
                    memory_text = memory_context
        except Exception as e:
            logger.warning(f"📱 [QQ] 记忆检索失败: {e}")

        # 2. 构建 System Prompt（加入 QQ 上下文提示）
        qq_context = (
            "\n\n【当前通信渠道】你正在通过 QQ 消息与指挥官对话。"
            "回复要简洁（QQ 不适合长篇大论），不要使用 Markdown 格式。"
            f"对方昵称: {user_name}"
        )
        system_content = self.brain.get_system_prompt() + memory_text + qq_context

        # 3. 调用 Brain
        try:
            ai_reply = self.brain.chat(
                user_input=user_input,
                system_content=system_content,
                tools_schema=self.skills.get_tools_schema(),
                tool_executor=self.skills.execute_tool
            )
            return ai_reply or "（扶光沉默了...）"
        except Exception as e:
            logger.error(f"📱 [QQ] Brain.chat 异常: {e}")
            return f"处理出错了: {str(e)[:100]}"

    # ==================================================
    # 消息解析工具
    # ==================================================

    def _extract_text(self, message: list) -> str:
        """从 OneBot 消息段中提取纯文本"""
        parts = []
        for seg in message:
            if seg.get("type") == "text":
                parts.append(seg.get("data", {}).get("text", ""))
        return " ".join(parts).strip()

    def _check_at_me(self, message: list) -> bool:
        """检查消息是否 @了机器人"""
        if self.self_id is None:
            return False
        for seg in message:
            if seg.get("type") == "at":
                qq = seg.get("data", {}).get("qq", "")
                if str(qq) == str(self.self_id):
                    return True
        return False

    def _format_for_qq(self, text: str) -> str:
        """将 AI 回复格式化为 QQ 友好格式（去 Markdown）"""
        if not text:
            return ""
        # 去除 Markdown 加粗/斜体
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        # 去除 Markdown 链接 [text](url) → text (url)
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1 (\2)', text)
        # 去除代码块标记
        text = re.sub(r'```\w*\n?', '', text)
        # 去除行内代码
        text = re.sub(r'`(.+?)`', r'\1', text)
        # 去除标题标记
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 限制长度（QQ 消息不宜太长）
        if len(text) > 2000:
            text = text[:2000] + "\n\n... (消息过长已截断)"
        return text.strip()

    # ==================================================
    # 发送消息
    # ==================================================

    async def _send_private_msg(self, ws, user_id: int, message: str):
        """发送私聊消息"""
        payload = {
            "action": "send_private_msg",
            "params": {
                "user_id": user_id,
                "message": message
            }
        }
        await ws.send(json.dumps(payload))
        logger.info(f"📱 [QQ] → 私聊 {user_id}: {message[:60]}...")

    async def _send_group_msg(self, ws, group_id: int, message: str):
        """发送群聊消息"""
        payload = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": message
            }
        }
        await ws.send(json.dumps(payload))
        logger.info(f"📱 [QQ] → 群 {group_id}: {message[:60]}...")
