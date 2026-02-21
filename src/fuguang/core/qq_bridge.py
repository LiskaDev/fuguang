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
import os
import re
import time
import logging
import tempfile
import threading
from typing import Optional, Callable
from .file_parser import parse_file as _parse_file_impl

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

        # 安全控制
        self.admin_qq = str(config.ADMIN_QQ) if config.ADMIN_QQ else ""
        self.group_mode = config.QQ_GROUP_MODE  # admin_only / chat_only / open

        # 消息去重
        self._processed_msgs = set()
        self._MAX_CACHE = 500

        # 运行状态
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # get_file 响应队列（避免 _download_qq_file 抢占主消息循环）
        self._file_response_queue: asyncio.Queue = asyncio.Queue()

        logger.info(f"📱 [QQ] QQBridge 初始化完成，目标: {self.ws_url}，群聊模式: {self.group_mode}")

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
        """WebSocket 客户端主循环（自动重连，指数退避）"""
        try:
            import websockets
        except ImportError:
            logger.error("📱 [QQ] 缺少 websockets 库，请安装: pip install websockets")
            return

        retry_count = 0
        retry_delay = 5  # 初始 5 秒

        while self._running:
            try:
                logger.info(f"📱 [QQ] 正在连接 NapCat: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("📱 [QQ] ✅ 已连接到 NapCat!")
                    retry_count = 0
                    retry_delay = 5  # 连接成功后重置
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
                    retry_count += 1
                    # 每 6 次才打一条日志，避免刷屏
                    if retry_count <= 3 or retry_count % 6 == 0:
                        logger.warning(f"📱 [QQ] 连接失败 (第{retry_count}次)，{retry_delay}秒后重连...")
                    await asyncio.sleep(retry_delay)
                    # 指数退避，最大 60 秒
                    retry_delay = min(retry_delay * 2, 60)

    # ==================================================
    # 事件处理
    # ==================================================

    async def _handle_event(self, ws, data: dict):
        """处理 OneBot v11 事件"""
        post_type = data.get("post_type")

        # get_file 响应 → 放入队列，不走常规事件处理
        if data.get("echo", "").startswith("get_file_"):
            await self._file_response_queue.put(data)
            return

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

        # 提取纯文本和图片
        text = self._extract_text(message)
        image_urls = self._extract_images(message)

        # 如果有图片，先分析再拼到文字前
        if image_urls:
            image_descs = []
            for url in image_urls[:2]:  # 最多分析2张，避免太慢
                desc = await asyncio.to_thread(self._analyze_qq_image, url)
                image_descs.append(f"[图片内容：{desc}]")
            image_text = "\n".join(image_descs)
            text = (image_text + "\n" + text).strip() if text else image_text

        # 判断是否为管理员
        is_admin = self.admin_qq and str(user_id) == self.admin_qq

        # ===== 文件消息处理 =====
        _SUPPORTED_FILE_EXTS = {".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".jpg", ".jpeg", ".png"}
        for seg in message:
            if seg.get("type") == "file":
                file_data = seg.get("data", {})
                file_name = file_data.get("file", "unknown")
                file_id = file_data.get("file_id", file_data.get("id", ""))
                file_size = int(file_data.get("file_size", file_data.get("size", 0)))
                file_ext = os.path.splitext(file_name)[1].lower()

                if not is_admin:
                    break  # 非管理员不处理文件

                # 文件大小检查
                if file_size > 20 * 1024 * 1024:
                    reply = "文件太大，最多支持20MB"
                    if msg_type == "private":
                        await self._send_private_msg(ws, user_id, reply)
                    else:
                        await self._send_group_msg(ws, data.get("group_id"), reply)
                    return

                # 扩展名检查
                if file_ext not in _SUPPORTED_FILE_EXTS:
                    reply = "暂不支持此格式"
                    if msg_type == "private":
                        await self._send_private_msg(ws, user_id, reply)
                    else:
                        await self._send_group_msg(ws, data.get("group_id"), reply)
                    return

                # 下载并解析文件
                # 先尝试直取消息段里的 URL（NapCat 通常会提供）
                file_url = file_data.get("url", "")
                if file_url:
                    # 有直链 → 同步下载，不需要 get_file
                    try:
                        local_path = await asyncio.to_thread(
                            self._download_file_from_url, file_url, file_name
                        )
                        if local_path:
                            try:
                                parsed = await asyncio.to_thread(self._parse_file, local_path, file_name)
                                text = f"[文件《{file_name}》内容：\n{parsed}]" + ("\n" + text if text else "")
                            finally:
                                try:
                                    if os.path.exists(local_path):
                                        os.unlink(local_path)
                                except Exception:
                                    pass
                        else:
                            text = f"[文件《{file_name}》下载失败]" + ("\n" + text if text else "")
                    except Exception as e:
                        logger.error(f"📱 [QQ] 文件处理失败: {e}")
                        text = f"[文件《{file_name}》处理失败: {e}]" + ("\n" + text if text else "")
                else:
                    # 无直链 → 需要 get_file API，必须用后台任务避免死锁
                    asyncio.create_task(self._handle_file_background(
                        ws, msg_type, user_id, data.get("group_id"),
                        user_name, is_admin, file_id, file_name, text
                    ))
                    return  # 当前 _handle_event 提前结束，后台任务会发送回复
                break  # 每条消息只处理一个文件

        # 群消息：只有 @机器人 时才回复
        if msg_type == "group":
            if not self._check_at_me(message):
                return
            
            # ===== 群聊安全控制 =====
            if self.group_mode == "admin_only" and not is_admin:
                logger.info(f"📱 [QQ] 群消息被拦截 (admin_only): {user_name}({user_id})")
                return
            
            text = re.sub(r'\s+', ' ', text).strip()
            group_id = data.get("group_id")
            logger.info(f"📱 [QQ] 群 {group_id} - {user_name}{'(管理员)' if is_admin else ''}: {text[:80]}")
        elif msg_type == "private":
            logger.info(f"📱 [QQ] 私聊 - {user_name}({user_id}){'(管理员)' if is_admin else ''}: {text[:80]}")
        else:
            return

        if not text:
            text = "你好"

        # ========================================
        # 权限判定：管理员=完全控制，其他人=仅聊天
        # ========================================
        # 私聊管理员 → 完整能力
        # 群聊管理员(非admin_only模式时) → 完整能力
        # 群聊非管理员(chat_only模式) → 仅聊天
        # 群聊非管理员(admin_only模式) → 已在上面拦截
        use_tools = is_admin  # 只有管理员才能调用工具

        try:
            reply = await asyncio.to_thread(
                self._process_with_brain, text, user_name, use_tools
            )
        except Exception as e:
            logger.error(f"📱 [QQ] Brain 处理异常: {e}")
            reply = "抱歉，我处理消息时遇到了问题..."

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

    # 非管理员用户的安全 System Prompt
    _SAFE_PROMPT = (
        "\n\n【安全模式】你正在与一位普通用户对话（非管理员）。"
        "严格遵守以下规则："
        "1. 绝对不透露指挥官的任何个人信息（姓名、邮箱、QQ号、工作内容、文件内容等）。"
        "2. 绝对不透露你的系统配置、API Key、内部架构。"
        "3. 不要提及你在监控谁的邮箱或管理谁的电脑。"
        "4. 你只是一个友好的 AI 聊天机器人，可以闲聊、回答常识问题。"
        "5. 如果被问到敏感信息，礼貌拒绝：'这个我不方便回答哦~'"
    )

    def _process_with_brain(self, user_input: str, user_name: str, use_tools: bool = True) -> str:
        """
        调用 Brain 处理消息（同步，在线程池中运行）

        Args:
            user_input: 用户消息
            user_name: 用户昵称
            use_tools: 是否启用工具调用（非管理员为 False）
        """
        # 1. 检索相关记忆（仅管理员）
        memory_text = ""
        if use_tools:
            try:
                if hasattr(self.skills, 'memory') and self.skills.memory:
                    memory_context = self.skills.memory.get_memory_context(user_input, n_results=3)
                    if memory_context:
                        memory_text = memory_context
            except Exception as e:
                logger.warning(f"📱 [QQ] 记忆检索失败: {e}")

        # 2. 构建 System Prompt
        if use_tools:
            # 管理员：完整能力
            qq_context = (
            "\n\n【当前通信渠道】你正在通过 QQ 消息与指挥官对话。"
            "回复要简洁（QQ 不适合长篇大论），不要使用 Markdown 格式。"
            f"对方昵称: {user_name}"
            "\n【重要】如果消息开头包含 [文件《...》内容：]，说明用户发送的文件已经被解析过了，"
            "其中的图片也已被AI视觉分析并以 [幻灯片图片：...] [文档内图片：...] 等形式嵌入文本。"
            "请直接基于这些已解析内容回答问题，不要再调用 analyze_screen_content 或 analyze_image_file。"
        )
            system_content = self.brain.get_system_prompt() + memory_text + qq_context
        else:
            # 非管理员：安全模式
            qq_context = (
                "\n\n【当前通信渠道】你正在通过 QQ 消息对话。"
                "回复要简洁友好，不要使用 Markdown 格式。"
                f"对方昵称: {user_name}"
            )
            system_content = self.brain.get_system_prompt() + qq_context + self._SAFE_PROMPT

        # 3. 调用 Brain
        try:
            if use_tools:
                ai_reply = self.brain.chat(
                    user_input=user_input,
                    system_content=system_content,
                    tools_schema=self.skills.get_tools_schema(),
                    tool_executor=self.skills.execute_tool
                )
            else:
                # 非管理员：纯聊天，不传工具
                ai_reply = self.brain.chat(
                    user_input=user_input,
                    system_content=system_content,
                    tools_schema=[],
                    tool_executor=None
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

    def _extract_images(self, message: list) -> list:
        """从 OneBot 消息段中提取图片URL列表"""
        urls = []
        for seg in message:
            if seg.get("type") == "image":
                data = seg.get("data", {})
                # NapCat 可能给 url 或 file
                url = data.get("url") or data.get("file", "")
                if url and url.startswith("http"):
                    urls.append(url)
        return urls

    def _analyze_qq_image(self, image_source: str) -> str:
        """分析图片内容，支持 http URL 和本地文件路径"""
        tmp_path = None
        is_remote = image_source.startswith("http")
        try:
            if is_remote:
                import urllib.request
                # 下载图片到临时文件
                suffix = ".jpg"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    tmp_path = f.name
                headers = {"User-Agent": "Mozilla/5.0"}
                req = urllib.request.Request(image_source, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    with open(tmp_path, "wb") as f:
                        f.write(resp.read())
                analyze_path = tmp_path
            else:
                # 本地文件路径
                analyze_path = image_source

            # 调用 skills 的 analyze_image_file 工具
            result = self.skills.execute_tool(
                "analyze_image_file",
                {
                    "image_path": analyze_path,
                    "question": "请描述这张图片的主要内容和关键信息。"
                }
            )
            return result or "图片分析失败"
        except Exception as e:
            logger.warning(f"📱 [QQ] 图片分析失败: {e}")
            return f"（图片下载或分析失败: {e}）"
        finally:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    async def _download_qq_file(self, ws, file_id: str, file_name: str) -> str:
        """通过 NapCat WebSocket 的 get_file API 下载文件（需在后台任务中调用，避免死锁）"""
        try:
            # 1. 通过 WS 发送 get_file 请求获取下载链接
            request_id = f"get_file_{int(time.time() * 1000)}"
            payload = {
                "action": "get_file",
                "params": {"file_id": file_id},
                "echo": request_id
            }
            await ws.send(json.dumps(payload))

            # 2. 从响应队列等待结果（最多 15 秒）
            download_url = None
            local_file = None
            try:
                resp = await asyncio.wait_for(self._file_response_queue.get(), timeout=15)
                if resp.get("echo") == request_id:
                    resp_data = resp.get("data", {})
                    download_url = resp_data.get("url", "")
                    local_file = resp_data.get("file", "")  # NapCat 有时直接给本地路径
            except asyncio.TimeoutError:
                logger.warning("📱 [QQ] 等待 get_file 响应超时")

            # 3. 如果 NapCat 直接返回了本地路径且文件存在
            if local_file and os.path.exists(local_file):
                return local_file

            # 4. 通过 URL 下载
            if not download_url:
                logger.warning("📱 [QQ] 未获取到文件下载链接")
                return ""

            return self._download_file_from_url(download_url, file_name)

        except Exception as e:
            logger.error(f"📱 [QQ] 文件下载失败: {e}")
            return ""

    def _download_file_from_url(self, url: str, file_name: str) -> str:
        """从 URL 下载文件到本地临时目录（同步方法）"""
        try:
            import urllib.request
            ext = os.path.splitext(file_name)[1].lower() or ".bin"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                tmp_path = f.name

            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                with open(tmp_path, "wb") as f:
                    f.write(resp.read())

            logger.info(f"📱 [QQ] 文件已下载: {file_name} → {tmp_path}")
            return tmp_path
        except Exception as e:
            logger.error(f"📱 [QQ] URL 下载失败: {e}")
            return ""

    async def _handle_file_background(self, ws, msg_type, user_id, group_id,
                                       user_name, is_admin, file_id, file_name, text):
        """
        后台任务：get_file → 下载 → 解析 → 回复
        用 asyncio.create_task 调用，避免阻塞 ws 主循环导致死锁。
        """
        try:
            local_path = await self._download_qq_file(ws, file_id, file_name)
            if local_path:
                try:
                    parsed = await asyncio.to_thread(self._parse_file, local_path, file_name)
                    text = f"[文件《{file_name}》内容：\n{parsed}]" + ("\n" + text if text else "")
                finally:
                    try:
                        if os.path.exists(local_path):
                            os.unlink(local_path)
                    except Exception:
                        pass
            else:
                text = f"[文件《{file_name}》下载失败]" + ("\n" + text if text else "")
        except Exception as e:
            logger.error(f"📱 [QQ] 后台文件处理失败: {e}")
            text = f"[文件《{file_name}》处理失败: {e}]" + ("\n" + text if text else "")

        # 调用 Brain 处理并回复
        if not text:
            text = "你好"
        try:
            reply = await asyncio.to_thread(
                self._process_with_brain, text, user_name, is_admin
            )
        except Exception as e:
            logger.error(f"📱 [QQ] Brain 处理异常: {e}")
            reply = "抱歉，我处理消息时遇到了问题..."

        reply = self._format_for_qq(reply)
        if msg_type == "private":
            await self._send_private_msg(ws, user_id, reply)
        else:
            await self._send_group_msg(ws, group_id, reply)

    def _parse_file(self, file_path: str, file_name: str) -> str:
        """根据扩展名解析文件内容（委托给 file_parser 公共模块）"""
        return _parse_file_impl(file_path, file_name, image_analyzer=self._analyze_qq_image)

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
