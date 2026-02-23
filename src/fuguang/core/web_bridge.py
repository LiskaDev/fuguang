# ==================================================
# 🌐 web_bridge.py - 扶光 Web UI 桥接
# ==================================================
# FastAPI + WebSocket，提供 ChatGPT 风格 Web 界面
# 与 QQBridge 并列，共享同一个 Brain/Skills/Memory
# ==================================================

import asyncio
import json
import os
import uuid
import time
import logging
import tempfile
import threading
import secrets
from pathlib import Path
from typing import Optional
from .chat_store import ChatStore

logger = logging.getLogger("Fuguang.Web")


class WebBridge:
    """
    扶光 Web UI 桥接层

    提供 FastAPI HTTP + WebSocket 服务：
    - /                    → 静态前端 SPA
    - /api/auth/login      → 密码登录，返回 JWT
    - /api/chat            → WebSocket 聊天（流式输出）
    - /api/upload          → 文件上传 + 解析
    - /api/files/{file_id} → 下载扶光生成的文件
    """

    def __init__(self, config, brain, skills):
        self.brain = brain
        self.skills = skills
        self.config = config

        # Web UI 配置
        self.port = getattr(config, 'WEB_UI_PORT', 7860)
        self.password = getattr(config, 'WEB_UI_PASSWORD', 'fuguang')
        self.jwt_secret = getattr(config, 'WEB_UI_JWT_SECRET', secrets.token_hex(32))

        # 静态文件目录 (core/ → fuguang/ → static/)
        self.static_dir = Path(__file__).resolve().parent.parent / "static"

        # 上传/生成文件临时存储
        self.upload_dir = Path(tempfile.gettempdir()) / "fuguang_uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        # 文件注册表 {file_id: {"path": str, "name": str, "created": float}}
        self._files = {}

        # 聊天历史存储
        data_dir = getattr(config, 'DATA_DIR', Path('.') / 'data')
        db_path = Path(data_dir) / "web_chat.db"
        self.chat_store = ChatStore(str(db_path))

        # 运行状态
        self._running = False
        self._thread: Optional[threading.Thread] = None

        logger.info(f"🌐 [Web] WebBridge 初始化完成，端口: {self.port}")

    # ==================================================
    # 启动 / 停止
    # ==================================================

    def start(self):
        """在后台 daemon 线程中启动 Web 服务"""
        if self._running:
            logger.warning("🌐 [Web] WebBridge 已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True, name="WebBridge")
        self._thread.start()
        logger.info("🌐 [Web] WebBridge 后台线程已启动")

    def stop(self):
        """停止 Web 服务"""
        self._running = False
        logger.info("🌐 [Web] WebBridge 已停止")

    def _run_server(self):
        """后台线程入口：启动 uvicorn"""
        import uvicorn
        app = self._create_app()

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",  # 避免 uvicorn 日志刷屏
            access_log=False,
        )
        server = uvicorn.Server(config)
        logger.info(f"🌐 [Web] 服务启动: http://0.0.0.0:{self.port}")
        server.run()

    # ==================================================
    # FastAPI 应用
    # ==================================================

    def _create_app(self):
        """创建 FastAPI 应用并注册所有路由"""
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Depends
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, JSONResponse
        from starlette.middleware.cors import CORSMiddleware

        app = FastAPI(title="扶光 Web UI", docs_url=None, redoc_url=None)

        # CORS（允许本地开发调试）
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ---- JWT 工具函数 ----
        def _create_token(payload: dict) -> str:
            """简易 JWT：base64(header).base64(payload).hmac_sig"""
            import base64, hashlib, hmac
            header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
            payload["exp"] = int(time.time()) + 86400 * 7  # 7天有效
            body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
            sig = hmac.new(self.jwt_secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).hexdigest()
            return f"{header}.{body}.{sig}"

        def _verify_token(token: str) -> dict:
            """验证 JWT，返回 payload 或 None"""
            import base64, hashlib, hmac
            try:
                parts = token.split(".")
                if len(parts) != 3:
                    return None
                header, body, sig = parts
                expected = hmac.new(self.jwt_secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig, expected):
                    return None
                # 补齐 base64 padding
                body_padded = body + "=" * (4 - len(body) % 4)
                payload = json.loads(base64.urlsafe_b64decode(body_padded))
                if payload.get("exp", 0) < time.time():
                    return None
                return payload
            except Exception:
                return None

        # ---- 路由：前端 SPA ----
        @app.get("/")
        async def index():
            index_file = self.static_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file), media_type="text/html")
            return JSONResponse({"error": "前端文件未找到"}, status_code=404)

        # ---- 路由：登录 ----
        @app.post("/api/auth/login")
        async def login(body: dict):
            password = body.get("password", "")
            if password != self.password:
                raise HTTPException(status_code=401, detail="密码错误")
            token = _create_token({"role": "admin"})
            return {"token": token}

        # ---- 路由：WebSocket 聊天 ----
        @app.websocket("/api/chat")
        async def websocket_chat(ws: WebSocket):
            await ws.accept()

            # 认证：第一条消息必须是 token
            try:
                auth_msg = await asyncio.wait_for(ws.receive_json(), timeout=10)
                token = auth_msg.get("token", "")
                if not _verify_token(token):
                    await ws.send_json({"type": "error", "content": "认证失败，请重新登录"})
                    await ws.close(code=4001)
                    return
                await ws.send_json({"type": "auth", "content": "ok"})
            except Exception:
                await ws.close(code=4001)
                return

            logger.info("🌐 [Web] WebSocket 已连接并认证")

            # 当前会话 ID（客户端通过消息指定或自动创建）
            current_conv_id = None
            cancel_event = None  # 取消标志（每次请求重建）

            # 聊天循环
            try:
                while True:
                    data = await ws.receive_json()
                    msg_type = data.get("type", "chat")
                    content = data.get("content", "").strip()

                    if msg_type == "chat" and content:
                        # 如果客户端指定了 conversation_id 就用它
                        conv_id = data.get("conversation_id")
                        if conv_id:
                            current_conv_id = conv_id

                        # 如果还没有对话，自动创建
                        if not current_conv_id:
                            conv = self.chat_store.create_conversation()
                            current_conv_id = conv["id"]
                            # 通知客户端新对话 ID
                            await ws.send_json({
                                "type": "conversation_created",
                                "conversation_id": current_conv_id
                            })

                        # 保存用户消息（display_content 由客户端单独发送，这里存原始内容）
                        display_content = data.get("display_content", content)
                        await asyncio.to_thread(
                            self.chat_store.add_message, current_conv_id, "user", display_content
                        )

                        # 第一条消息自动生成标题
                        conv_info = await asyncio.to_thread(
                            self.chat_store.get_conversation, current_conv_id
                        )
                        if conv_info and conv_info["title"] == "新对话":
                            await asyncio.to_thread(
                                self.chat_store.auto_title, current_conv_id, display_content
                            )
                            # 通知客户端标题更新
                            updated = await asyncio.to_thread(
                                self.chat_store.get_conversation, current_conv_id
                            )
                            if updated:
                                await ws.send_json({
                                    "type": "title_updated",
                                    "conversation_id": current_conv_id,
                                    "title": updated["title"]
                                })

                        # 在线程池中运行 Brain.chat（避免阻塞事件循环）
                        await ws.send_json({"type": "thinking", "content": ""})
                        
                        # 创建取消标志
                        import threading as _threading
                        cancel_event = _threading.Event()
                        
                        # 进度回调：从 Brain 线程通过 WebSocket 发送实时工具状态
                        main_loop = asyncio.get_event_loop()
                        def _progress_cb(info: dict):
                            """Brain 线程回调 → 异步 WebSocket 发送"""
                            try:
                                msg_type = info.get("type", "")
                                if msg_type == "tool_call":
                                    tool_name = info.get("tool", "")
                                    coro = ws.send_json({
                                        "type": "tool_progress",
                                        "content": f"🔧 正在调用: {tool_name}"
                                    })
                                    asyncio.run_coroutine_threadsafe(coro, main_loop)
                                elif msg_type == "thinking":
                                    iteration = info.get("iteration", 1)
                                    if iteration > 1:
                                        coro = ws.send_json({
                                            "type": "tool_progress",
                                            "content": f"🤔 思考中 (第{iteration}轮)..."
                                        })
                                        asyncio.run_coroutine_threadsafe(coro, main_loop)
                                elif msg_type == "file":
                                    # 文件下载卡片 → 直接推送给前端
                                    coro = ws.send_json({
                                        "type": "file",
                                        "file_id": info.get("file_id", ""),
                                        "filename": info.get("filename", ""),
                                        "url": info.get("url", ""),
                                        "size": info.get("size", 0)
                                    })
                                    asyncio.run_coroutine_threadsafe(coro, main_loop)
                            except Exception:
                                pass
                        
                        # 并发执行：Brain 处理 + WebSocket 监听取消
                        cancelled = False  # 是否已取消
                        self._current_conversation_id = current_conv_id  # 供 _file_aware_executor 持久化文件卡片
                        brain_task = asyncio.create_task(
                            asyncio.to_thread(
                                self._process_with_brain, content, _progress_cb, cancel_event
                            )
                        )

                        # 在 Brain 处理期间监听 cancel/ping 消息
                        try:
                            while not brain_task.done():
                                # 等待消息或 brain 完成，先到先处理
                                listen_task = asyncio.create_task(ws.receive_json())
                                done, pending = await asyncio.wait(
                                    {brain_task, listen_task},
                                    return_when=asyncio.FIRST_COMPLETED
                                )
                                
                                if listen_task in done:
                                    # 收到 WebSocket 消息
                                    try:
                                        msg = listen_task.result()
                                        if msg.get("type") == "cancel":
                                            logger.info("🛑 [Web] 用户请求取消")
                                            cancel_event.set()
                                            cancelled = True
                                            # 立即回复客户端，不等 brain 结束
                                            hideThinking_msg = "好的指挥官，已停止当前操作。有什么需要可以随时告诉我~ [OK]"
                                            await asyncio.to_thread(
                                                self.chat_store.add_message, current_conv_id, "ai", hideThinking_msg
                                            )
                                            await ws.send_json({
                                                "type": "reply",
                                                "content": hideThinking_msg
                                            })
                                            # brain 线程会在后台自行结束，不阻塞
                                            break
                                        elif msg.get("type") == "ping":
                                            await ws.send_json({"type": "pong"})
                                    except Exception:
                                        pass
                                else:
                                    # brain 先完成了，取消监听
                                    listen_task.cancel()
                                    try:
                                        await listen_task
                                    except (asyncio.CancelledError, Exception):
                                        pass
                        except Exception:
                            pass

                        # 获取结果（如果没被取消）
                        if not cancelled:
                            try:
                                reply = brain_task.result()
                                # 保存 AI 回复
                                await asyncio.to_thread(
                                    self.chat_store.add_message, current_conv_id, "ai", reply
                                )
                                await ws.send_json({
                                    "type": "reply",
                                    "content": reply
                                })
                            except Exception as e:
                                logger.error(f"🌐 [Web] Brain 处理异常: {e}")
                                await ws.send_json({
                                    "type": "error",
                                    "content": f"处理出错了: {str(e)[:200]}"
                                })
                        
                        cancel_event = None

                    elif msg_type == "switch_conversation":
                        # 切换到指定对话
                        current_conv_id = data.get("conversation_id")

                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong"})
                    
                    elif msg_type == "cancel":
                        # Brain 没在运行时收到 cancel，忽略
                        if cancel_event:
                            cancel_event.set()

            except WebSocketDisconnect:
                logger.info("🌐 [Web] WebSocket 断开")
            except Exception as e:
                logger.error(f"🌐 [Web] WebSocket 异常: {e}")

        @app.post("/api/upload")
        async def upload_file_impl(file: UploadFile = File(...)):
            """上传文件，解析内容，返回解析结果和文件ID"""
            from .file_parser import parse_file, SUPPORTED_EXTENSIONS

            file_name = file.filename or "unknown"
            file_ext = os.path.splitext(file_name)[1].lower()

            # 扩展名检查
            if file_ext not in SUPPORTED_EXTENSIONS:
                return JSONResponse(
                    {"error": f"不支持的文件格式: {file_ext}"},
                    status_code=400
                )

            # 保存到临时文件
            file_id = str(uuid.uuid4())[:8]
            save_path = self.upload_dir / f"{file_id}_{file_name}"
            try:
                content = await file.read()
                if len(content) > 20 * 1024 * 1024:
                    return JSONResponse({"error": "文件太大，最多支持20MB"}, status_code=400)

                with open(save_path, "wb") as f:
                    f.write(content)

                # 注册文件
                self._files[file_id] = {
                    "path": str(save_path),
                    "name": file_name,
                    "created": time.time()
                }

                # 解析文件内容
                def _do_parse():
                    image_analyzer = None
                    # Web 端不使用视觉分析（避免触发 mouth.speak）
                    # 图片类文件直接标记，文档内嵌图片用占位符
                    return parse_file(str(save_path), file_name, image_analyzer=None)

                parsed = await asyncio.to_thread(_do_parse)

                return {
                    "file_id": file_id,
                    "file_name": file_name,
                    "parsed_content": parsed
                }

            except Exception as e:
                logger.error(f"🌐 [Web] 文件上传处理失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        # ---- 路由：文件下载（by file_id，实时推送用） ----
        @app.get("/api/files/{file_id}")
        async def download_file(file_id: str):
            file_info = self._files.get(file_id)
            if not file_info or not os.path.exists(file_info["path"]):
                raise HTTPException(status_code=404, detail="文件不存在")
            import mimetypes
            mime, _ = mimetypes.guess_type(file_info["name"])
            return FileResponse(
                file_info["path"],
                filename=file_info["name"],
                media_type=mime or "application/octet-stream"
            )

        # ---- 路由：temp_files 静态服务（持久化 URL，刷新后仍可访问） ----
        @app.get("/api/temp_files/{filename}")
        async def serve_temp_file(filename: str):
            temp_dir = self.config.PROJECT_ROOT / "temp_files"
            file_path = temp_dir / filename
            if not file_path.exists() or not file_path.is_file():
                raise HTTPException(status_code=404, detail="文件不存在")
            # 安全检查：防止路径遍历
            if not file_path.resolve().parent == temp_dir.resolve():
                raise HTTPException(status_code=403, detail="禁止访问")
            import mimetypes
            mime, _ = mimetypes.guess_type(filename)
            return FileResponse(
                str(file_path),
                media_type=mime or "application/octet-stream"
            )

        # ---- 路由：对话管理 ----
        @app.get("/api/conversations")
        async def list_conversations():
            convs = await asyncio.to_thread(self.chat_store.list_conversations)
            return {"conversations": convs}

        @app.post("/api/conversations")
        async def create_conversation(body: dict = None):
            title = (body or {}).get("title", "新对话")
            conv = await asyncio.to_thread(self.chat_store.create_conversation, title)
            return conv

        @app.delete("/api/conversations/{conv_id}")
        async def delete_conversation(conv_id: str):
            await asyncio.to_thread(self.chat_store.delete_conversation, conv_id)
            return {"ok": True}

        @app.put("/api/conversations/{conv_id}/title")
        async def rename_conversation(conv_id: str, body: dict):
            title = body.get("title", "")
            if title:
                await asyncio.to_thread(self.chat_store.update_title, conv_id, title)
            return {"ok": True}

        @app.get("/api/conversations/{conv_id}/messages")
        async def get_messages(conv_id: str):
            msgs = await asyncio.to_thread(self.chat_store.get_messages, conv_id)
            return {"messages": msgs}

        # ---- 挂载静态文件（CSS/JS/图片等）----
        if self.static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(self.static_dir)), name="static")

        return app

    # ==================================================
    # Brain 对接
    # ==================================================

    def _process_with_brain(self, user_input: str, progress_callback=None, cancel_event=None) -> str:
        """调用 Brain 处理消息（同步方法，在线程池中运行）"""

        # 1. 检索相关记忆
        memory_text = ""
        try:
            if hasattr(self.skills, 'memory') and self.skills.memory:
                memory_context = self.skills.memory.get_memory_context(user_input, n_results=3)
                if memory_context:
                    memory_text = memory_context
        except Exception as e:
            logger.warning(f"🌐 [Web] 记忆检索失败: {e}")

        # 2. 构建 System Prompt
        web_context = (
            "\n\n【当前通信渠道】你正在通过 Web 网页界面与指挥官对话。"
            "网页支持 Markdown 渲染和代码高亮，你可以自由使用 Markdown 格式。"
            "回复可以适当详细，不需要像 QQ 那样刻意简短。"
            "\n【重要】如果消息开头包含 [文件《...》内容：]，说明用户上传的文件已经被解析过了，"
            "其中的图片也已被AI视觉分析并以 [幻灯片图片：...] [文档内图片：...] 等形式嵌入文本。"
            "请直接基于这些已解析内容回答问题，不要再调用任何工具来分析文件。"
            "\n【网页端限制】你目前无法控制用户的桌面、键盘、鼠标、音量、浏览器或应用程序。"
            "不要尝试打开网站、控制音量、操作 GUI 或启动本地应用。"
        )
        system_content = self.brain.get_system_prompt() + memory_text + web_context

        # 3. 调用 Brain（带工具，但排除 Web 端不适用的本地工具）
        _web_excluded = {
            # 视觉
            "analyze_screen_content", "analyze_image_file",
            # GUI 桌面控制
            "send_hotkey", "open_application", "click_screen_text",
            "type_text", "click_by_description", "list_ui_elements",
            # 系统-本地
            "control_volume", "open_tool", "launch_application",
            "listen_to_system_audio", "toggle_auto_execute",
            # 浏览器-本地
            "open_website", "open_video", "browse_website",
        }
        web_tools = [t for t in self.skills.get_tools_schema()
                     if t.get("function", {}).get("name") not in _web_excluded]

        # 包装 tool_executor：拦截文件生成工具的 _pending_file_cards
        _original_executor = self.skills.execute_tool
        def _file_aware_executor(name, args):
            result = _original_executor(name, args)
            # 检查是否有待推送的文件卡片
            pending = getattr(self.skills, '_pending_file_cards', [])
            while pending:
                card_info = pending.pop(0)
                # 注册到 _files 表以供下载
                file_id = str(uuid.uuid4())[:8]
                self._files[file_id] = {
                    "path": card_info["filepath"],
                    "name": card_info["filename"],
                    "created": time.time()
                }
                # 构建持久化 URL（基于文件名，不依赖内存 file_id）
                import json as _json
                persistent_url = f"/api/temp_files/{card_info['filename']}"
                # 通过 progress_callback 推送文件卡片（实时）
                if progress_callback:
                    progress_callback({
                        "type": "file",
                        "file_id": file_id,
                        "filename": card_info["filename"],
                        "url": persistent_url,
                        "size": card_info["size"]
                    })
                # 持久化到数据库（刷新后可恢复）
                if hasattr(self, '_current_conversation_id') and self._current_conversation_id:
                    try:
                        file_msg = _json.dumps({
                            "filename": card_info["filename"],
                            "url": persistent_url,
                            "size": card_info["size"]
                        }, ensure_ascii=False)
                        self.chat_store.add_message(
                            self._current_conversation_id, "file", file_msg
                        )
                    except Exception as e:
                        logger.warning(f"🌐 [Web] 文件卡片持久化失败: {e}")
                logger.info(f"🌐 [Web] 文件卡片已推送: {card_info['filename']} -> {persistent_url}")
            return result

        try:
            ai_reply = self.brain.chat(
                user_input=user_input,
                system_content=system_content,
                tools_schema=web_tools,
                tool_executor=_file_aware_executor,
                progress_callback=progress_callback,
                cancel_event=cancel_event
            )
            return ai_reply or "（扶光沉默了...）"
        except Exception as e:
            logger.error(f"🌐 [Web] Brain.chat 异常: {e}")
            return f"处理出错了: {str(e)[:200]}"
