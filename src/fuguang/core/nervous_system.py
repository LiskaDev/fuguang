
import time
import logging
import re
import json
import os
import queue as _queue
import threading
import keyboard
import speech_recognition as sr
import datetime
from .. import heartbeat as fuguang_heartbeat
from ..camera import Camera
from ..gaze_tracker import GazeTracker
from .config import ConfigManager
from .mouth import Mouth
from .ears import Ears
from .brain import Brain
from .skills import SkillManager
from .eyes import Eyes
from .qq_bridge import QQBridge
from .web_bridge import WebBridge
from .chat_store import ChatStore

logger = logging.getLogger("Fuguang")

class NervousSystem:
    """
    协调与生命周期角色
    职责：状态管理、按键监听、主循环
    """

    VOICE_WAKE_DURATION = 30  # 语音唤醒持续时间(秒)

    def __init__(self):
        # 初始化各个器官
        self.config = ConfigManager()
        self.mouth = Mouth(self.config)
        self.brain = Brain(self.config, self.mouth)
        self.ears = Ears()
        self.skills = SkillManager(self.config, self.mouth, self.brain)

        # [修复] 根据配置决定是否启用摄像头
        if self.config.CAMERA_ENABLED:
            self.camera = Camera()
            self.gaze_tracker = GazeTracker(self.camera, self.mouth, fps=self.config.GAZE_TRACKING_FPS)
            logger.info("📷 摄像头模块已启用")
        else:
            self.camera = None
            self.gaze_tracker = None
            logger.info("📷 摄像头模块已禁用 (CAMERA_ENABLED=False)")
        
        # [新增] 初始化数字眼睛（情境感知）
        self.eyes = Eyes(self.config)

        # ========================================
        # [新增] GUI 回调钩子 (可选，不影响终端模式)
        # ========================================
        self.on_state_change = None   # (state: str) -> None, state: "IDLE"/"LISTENING"/"THINKING"/"SPEAKING"
        self.on_subtitle = None       # (text: str, persistent: bool) -> None
        self.on_speech_start = None   # (text: str) -> None
        self.on_speech_end = None     # () -> None
        self.on_expression_change = None  # (expression: str) -> None, 如 "Joy"/"Angry"/"Sorrow"
        
        # 状态变量
        self.AWAKE_STATE = "sleeping"  # sleeping / voice_wake
        self.IS_PTT_PRESSED = False
        self.LAST_ACTIVE_TIME = 0
        self.TEXT_INPUT_REQUESTED = False  # [新增] 打字输入模式标志
        
        # [修复C-5] 键盘钩子运行在独立线程，需线程锁保护共享状态
        self._input_state_lock = threading.Lock()
        
        # [新增] 害羞机制冷却时间
        self.last_shy_time = 0
        
        # [升级] 安保系统状态
        self.security_mode_active = False  # True=锁定中，拒绝一切指令
        self.last_security_warning_time = 0  # 上次警告时间（用于周期性警告）

        # === [新增] 主动性状态锁 (晨间协议) ===
        self.last_greet_date = None       # 上次打招呼的日期，防止重复
        self.is_processing_greet = False  # 防止多线程冲突

        # ========================================
        # [新增] GUI 线程安全操作队列
        # ========================================
        self._gui_action_queue = _queue.Queue()

        # ========================================
        # [新增] GUI 独立录音线程（点击悬浮球触发）
        # ========================================
        self._gui_recording_active = False   # 是否正在 GUI 录音
        self._gui_stop_event = threading.Event()  # 停止录音信号
        self._gui_record_thread = None

        # ========================================
        # [新增] GUI 聊天历史持久化（与 Web UI 共享数据库）
        # ========================================
        try:
            from pathlib import Path
            data_dir = getattr(self.config, 'DATA_DIR', Path('.') / 'data')
            db_path = Path(data_dir) / "web_chat.db"
            self.chat_store = ChatStore(str(db_path))
            # 每次启动创建新会话
            ts = datetime.datetime.now().strftime("%m-%d %H:%M")
            conv = self.chat_store.create_conversation(f"GUI 语音对话 {ts}")
            self._gui_conv_id = conv["id"]
            logger.info(f"💾 [ChatStore] GUI 会话已创建: {self._gui_conv_id}")
        except Exception as e:
            logger.warning(f"💾 [ChatStore] 初始化失败（不影响对话）: {e}")
            self.chat_store = None
            self._gui_conv_id = None

        # ========================================
        # [新增] VTube Studio 桥接（Live2D 外观）
        # ========================================
        self.vtube_bridge = None
        if getattr(self.config, 'VTS_ENABLED', False):
            try:
                from .vtube_bridge import VTubeBridge
                self.vtube_bridge = VTubeBridge(self.config)
                self.vtube_bridge.start()
                self.mouth.vtube_bridge = self.vtube_bridge  # 注入到 mouth
                logger.info("🎭 [VTS] VTube Studio 桥接已启动")
            except Exception as e:
                logger.error(f"🎭 [VTS] VTS 桥接启动失败（不影响其他功能）: {e}")

        # ========================================
        # [新增] QQ 消息桥接（NapCat OneBot）
        # ========================================
        self.qq_bridge = None
        if self.config.QQ_ENABLED:
            try:
                self.qq_bridge = QQBridge(
                    config=self.config,
                    brain=self.brain,
                    skills=self.skills,
                    mouth=self.mouth
                )
                self.qq_bridge.start()
                logger.info("📱 [QQ] QQ 消息桥接已启动")
            except Exception as e:
                logger.error(f"📱 [QQ] QQ 桥接启动失败（不影响其他功能）: {e}")

        # ========================================
        # [新增] Web UI 桥接（FastAPI + WebSocket）
        # ========================================
        self.web_bridge = None
        if getattr(self.config, 'WEB_UI_ENABLED', False):
            try:
                self.web_bridge = WebBridge(
                    config=self.config,
                    brain=self.brain,
                    skills=self.skills
                )
                self.web_bridge.start()
                logger.info(f"🌐 [Web] Web UI 已启动: http://0.0.0.0:{self.web_bridge.port}")
            except Exception as e:
                logger.error(f"🌐 [Web] Web UI 启动失败（不影响其他功能）: {e}")

        # 注册按键监听
        keyboard.hook(self._on_key_event)

        logger.info("🧠 神经系统初始化完毕...")
        logger.info("💡 提示: 按 F1 可切换到打字输入模式")


    def _on_key_event(self, event):
        """按键事件处理 [修复C-5] 使用锁保护共享状态 + 防抖"""
        # PTT 模式（右 Ctrl）
        if event.name == 'right ctrl':
            with self._input_state_lock:
                now = time.time()
                # 防抖：200ms 内重复事件忽略
                last_ptt = getattr(self, '_last_ptt_event_time', 0)
                if now - last_ptt < 0.2:
                    return
                self._last_ptt_event_time = now
                
                if event.event_type == 'down' and not self.IS_PTT_PRESSED:
                    self.IS_PTT_PRESSED = True
                    logger.info("🎤 [PTT] 键按下")
                    fuguang_heartbeat.update_interaction()
                elif event.event_type == 'up' and self.IS_PTT_PRESSED:
                    self.IS_PTT_PRESSED = False
                    self.LAST_ACTIVE_TIME = time.time()
                    logger.info("🎤 [PTT] 录音结束")
        
        # [新增] 打字输入模式（F1）
        elif event.name == 'f1' and event.event_type == 'down':
            with self._input_state_lock:
                self.TEXT_INPUT_REQUESTED = True
            logger.info("⌨️ [打字模式] 已触发，请在终端输入文字")

    # ========================================
    # [新增] GUI 回调触发器
    # ========================================
    def _emit_state(self, state: str):
        """触发状态变化回调 (IDLE/LISTENING/THINKING/SPEAKING)"""
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception as e:
                logger.warning(f"GUI 回调异常: {e}")
        
        # [VTS] 状态切换时触发对应热键
        if self.vtube_bridge:
            try:
                if state == "THINKING":
                    self.vtube_bridge.trigger_hotkey("thinking")
                elif state == "LISTENING":
                    self.vtube_bridge.trigger_hotkey("listening")
            except Exception as e:
                logger.warning(f"VTS 状态热键异常: {e}")
    
    def _emit_subtitle(self, text: str, persistent: bool = False):
        """触发字幕显示回调"""
        if self.on_subtitle:
            try:
                self.on_subtitle(text, persistent)
            except Exception as e:
                logger.warning(f"GUI 字幕回调异常: {e}")

    # ========================================
    # [新增] GUI 操作队列 (线程安全)
    # ========================================
    def queue_gui_action(self, action_type: str, **kwargs):
        """从 GUI 线程安全地提交操作到主循环
        
        Args:
            action_type: 操作类型 ("wake"/"sleep"/"screenshot"/"ingest_file"/"text_input")
            **kwargs: 操作参数
        """
        self._gui_action_queue.put((action_type, kwargs))
        logger.debug(f"📬 GUI 操作入队: {action_type}")

    def _process_gui_actions(self):
        """处理 GUI 提交的操作（在主循环每轮迭代的开头调用）"""
        while not self._gui_action_queue.empty():
            try:
                action_type, kwargs = self._gui_action_queue.get_nowait()
                logger.info(f"📬 处理 GUI 操作: {action_type}")
                
                if action_type == "wake":
                    self.AWAKE_STATE = "voice_wake"
                    self.LAST_ACTIVE_TIME = time.time()
                    self._emit_state("LISTENING")
                    self._emit_subtitle("指挥官，请说~")
                    fuguang_heartbeat.update_interaction()
                    
                elif action_type == "sleep":
                    self.AWAKE_STATE = "sleeping"
                    self._emit_state("IDLE")
                    self._emit_subtitle("休眠中...")
                    
                elif action_type == "screenshot":
                    self._handle_screenshot_from_gui()
                    
                elif action_type == "ingest_file":
                    file_path = kwargs.get("file_path", "")
                    self._handle_file_ingestion_from_gui(file_path)
                    
                elif action_type == "text_input":
                    text = kwargs.get("text", "")
                    if text:
                        self._process_command(text)
                        
            except _queue.Empty:
                break
            except Exception as e:
                logger.error(f"GUI 操作处理异常: {e}")

    # ========================================
    # [新增] GUI 独立录音（完全绕开主循环）
    # ========================================
    def start_gui_recording(self):
        """启动 GUI 独立录音线程（由悬浮球点击触发）
        
        设计要点：
        - 独立线程，不依赖主循环，点击立刻开录
        - 主循环检测 _gui_recording_active 跳过自己的麦克风操作，避免抢麦
        - 录完自动识别，结果通过队列送回主循环处理
        """
        if self._gui_recording_active:
            logger.warning("🎤 [GUI-PTT] 已在录音中，忽略重复启动")
            return
        
        self._gui_recording_active = True
        self._gui_stop_event.clear()
        
        # 确保已唤醒
        if self.AWAKE_STATE == "sleeping":
            self.AWAKE_STATE = "voice_wake"
        self.LAST_ACTIVE_TIME = time.time()
        fuguang_heartbeat.update_interaction()
        
        self._gui_record_thread = threading.Thread(
            target=self._gui_record_worker, daemon=True, name="GUI-PTT-Record"
        )
        self._gui_record_thread.start()
        logger.info("🎤 [GUI-PTT] 录音线程已启动")

    def stop_gui_recording(self):
        """停止 GUI 录音（由悬浮球再次点击触发）"""
        if not self._gui_recording_active:
            return
        self._gui_stop_event.set()
        logger.info("🎤 [GUI-PTT] 停止信号已发出")

    def _gui_record_worker(self):
        """GUI 录音工作线程：录音 → 识别 → 送结果回主循环"""
        try:
            with self.ears.get_microphone() as source:
                self._emit_state("LISTENING")
                self._emit_subtitle("正在倾听，再次点击结束...")
                self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.05)
                
                frames = []
                logger.info("🎤 [GUI-PTT] 开始录音...")
                
                while not self._gui_stop_event.is_set():
                    try:
                        buffer = source.stream.read(source.CHUNK)
                        frames.append(buffer)
                    except Exception:
                        break
                
                self._gui_recording_active = False
                
                if frames:
                    audio_data = b''.join(frames)
                    logger.info(f"🎤 [GUI-PTT] 录制完成，共 {len(audio_data)} 字节")
                    
                    self._emit_state("THINKING")
                    self._emit_subtitle("思考中...")
                    
                    text = self.ears.listen_ali(audio_data)
                    if text == "[NETWORK_ERROR]":
                        logger.warning("⚠️ [GUI-PTT] 网络连接中断")
                        print("⚠️ 网络连接中断，请检查WiFi")
                        self._emit_subtitle("网络连接中断，请检查WiFi")
                        try:
                            self.mouth.speak("指挥官，网络似乎断开了")
                        except Exception:
                            pass
                        time.sleep(3)
                        self._emit_state("IDLE")
                    elif text:
                        logger.info(f"👂 [GUI-PTT] 听到了: {text}")
                        fuguang_heartbeat.update_interaction()
                        self.LAST_ACTIVE_TIME = time.time()
                        # 送回主循环处理（会调用 _process_command）
                        self.queue_gui_action("text_input", text=text)
                    else:
                        logger.warning("🎤 [GUI-PTT] 未识别到语音")
                        self._emit_subtitle("没听清，请再试一次")
                        # 短暂显示后恢复
                        time.sleep(2)
                        self._emit_state("IDLE")
                else:
                    self._gui_recording_active = False
                    logger.warning("🎤 [GUI-PTT] 没有录到声音")
                    self._emit_subtitle("没有录到声音")
                    time.sleep(2)
                    self._emit_state("IDLE")
                    
        except Exception as e:
            logger.error(f"🎤 [GUI-PTT] 录音异常: {e}")
            self._gui_recording_active = False
            self._emit_subtitle(f"录音失败: {e}")
            time.sleep(2)
            self._emit_state("IDLE")

    def _handle_screenshot_from_gui(self):
        """GUI 触发的截图分析"""
        self._emit_state("THINKING")
        self._emit_subtitle("正在分析屏幕...")
        try:
            result = self.skills.analyze_screen_content("请描述你看到的内容")
            if result:
                self._process_response(result)
        except Exception as e:
            logger.error(f"截图分析失败: {e}")
            self.mouth.speak("抱歉指挥官，截图分析出了点问题。")
        finally:
            self._emit_state("IDLE")

    def _handle_file_ingestion_from_gui(self, file_path: str):
        """GUI 触发的文件吞噬"""
        if not file_path or not os.path.exists(file_path):
            self._emit_subtitle("文件路径无效")
            return
        
        filename = os.path.basename(file_path)
        self._emit_state("THINKING")
        self._emit_subtitle(f"正在消化: {filename}")
        try:
            result = self.skills.ingest_knowledge_file(file_path)
            # [修复#8] 向对话历史注入通知，让 AI 知道用户刚投喂了文件
            self.brain.chat_history.append({
                "role": "user",
                "content": f"【系统通知】用户刚刚投喂了文件: {filename}，内容已存入知识库。用户接下来可能会问关于这个文件的问题。"
            })
            self.brain.chat_history.append({
                "role": "assistant",
                "content": f"好的，{filename} 已经消化完毕，我可以回答关于它的问题了。"
            })
            self.mouth.speak(f"指挥官，{filename} 已消化，你可以问我关于它的问题了。")
        except Exception as e:
            logger.error(f"文件吞噬失败: {e}")
            self.mouth.speak("抱歉指挥官，文件消化失败了。")
        finally:
            self._emit_state("IDLE")

    def _check_timeout(self):
        """检查语音唤醒是否超时"""
        if self.AWAKE_STATE == "voice_wake":
            # GUI 录音活跃时不超时（用户正在操作）
            if self._gui_recording_active:
                self.LAST_ACTIVE_TIME = time.time()
                return
            elapsed = time.time() - self.LAST_ACTIVE_TIME
            if elapsed > self.VOICE_WAKE_DURATION:
                self.AWAKE_STATE = "sleeping"
                self._emit_state("IDLE")
                logger.info("💤 语音唤醒超时，回到待机")

    def _get_status_text(self) -> str:
        """获取当前状态文本"""
        if self.TEXT_INPUT_REQUESTED:
            return "⌨️ 打字输入模式"
        elif self.IS_PTT_PRESSED:
            return "🎤 PTT录音中"
        elif self.AWAKE_STATE == "sleeping":
            return "💤 待机中（按住CTRL说话 / F1打字）"
        elif self.AWAKE_STATE == "voice_wake":
            remaining = int(self.VOICE_WAKE_DURATION - (time.time() - self.LAST_ACTIVE_TIME))
            return f"🟢 唤醒中 ({remaining}s)"
        return "❓ 未知"


    def _process_response(self, ai_text: str):
        """处理 AI 响应，提取标签和命令"""
        if "<｜DSML｜" in ai_text or "<tool_code>" in ai_text:
            return

        cmd_expression = "Neutral"
        cmd_unity = ""

        tags = re.findall(r"\[(.*?)\]", ai_text)
        clean_text = re.sub(r"\[.*?\]", "", ai_text).strip()

        for tag in tags:
            if tag in ["Joy", "Angry", "Sorrow", "Fun", "Surprised", "Neutral",
                       "Shy", "Love", "Proud", "Confused", "Apologetic",
                       "Thinking", "Sleeping", "Working", "Wave"]:
                cmd_expression = tag
            elif tag == "CMD:MODE_ON":
                self.brain.IS_CREATION_MODE = True
                logger.info("🔓 创造模式已开启")
            elif tag == "CMD:MODE_OFF":
                self.brain.IS_CREATION_MODE = False
                logger.info("🔒 创造模式已关闭")
            elif tag == "CMD:SHUTDOWN":
                self.brain.summarize_and_exit()
            elif tag.startswith("CMD:"):
                cmd_unity = tag.replace("CMD:", "").lower()

        self.mouth.send_to_unity(cmd_expression)
        # [新增] 通知 GUI 切换表情 Emoji
        if self.on_expression_change:
            try:
                self.on_expression_change(cmd_expression)
            except Exception as e:
                logger.warning(f"GUI 表情回调异常: {e}")
        
        # [VTS] 触发 Live2D 模型表情
        if self.vtube_bridge:
            try:
                self.vtube_bridge.trigger_expression(cmd_expression)
            except Exception as e:
                logger.warning(f"VTS 表情触发异常: {e}")

        if cmd_unity:
            if self.brain.IS_CREATION_MODE:
                self.mouth.send_to_unity(cmd_unity)
                if clean_text:
                    self.mouth.speak(clean_text)
            else:
                self.mouth.speak("指挥官，物理操作需要先开启创造模式哦。")
                self.mouth.send_to_unity("Sorrow")
        else:
            if clean_text:
                self.mouth.speak(clean_text)

    def _handle_ai_response(self, user_input: str):
        """处理 AI 回复 (简化版 - 逻辑已移至 Brain.chat)"""
        self.LAST_ACTIVE_TIME = time.time()
        fuguang_heartbeat.update_interaction()
        
        # [持久化] 保存用户消息
        if self.chat_store and self._gui_conv_id:
            try:
                self.chat_store.add_message(self._gui_conv_id, "user", user_input)
            except Exception as e:
                logger.warning(f"💾 保存用户消息失败: {e}")
        
        # [GUI] 通知界面：开始思考
        self._emit_state("THINKING")
        self._emit_subtitle(f"👂 {user_input[:50]}..." if len(user_input) > 50 else f"👂 {user_input}")

        # 检索相关记忆 (使用 ChromaDB 向量数据库)
        memory_text = ""
        try:
            if hasattr(self.skills, 'memory') and self.skills.memory:
                # 使用新的向量数据库进行语义检索
                memory_context = self.skills.memory.get_memory_context(user_input, n_results=3)
                if memory_context:
                    memory_text = memory_context
                    has_recipe = "最佳实践" in memory_context
                    logger.info(f"📖 [RAG] 已注入长期记忆上下文{' (含配方⚡)' if has_recipe else ''}")
            else:
                # 备用：使用旧的记忆系统
                related_memories = self.brain.memory_system.search_memory(user_input)
                if related_memories:
                    memory_text = "\n【相关长期记忆】\n" + "\n".join(related_memories)
                    logger.info(f"🧠 激活记忆: {related_memories}")
        except Exception as e:
            logger.warning(f"⚠️ [RAG] 记忆检索失败（不影响对话）: {e}")
            memory_text = ""


        # 收集实时感知数据
        perception_data = self.eyes.get_perception_data()
        perception_data["user_present"] = self.gaze_tracker.has_face if hasattr(self.gaze_tracker, 'has_face') else None
        
        system_content = self.brain.get_system_prompt(dynamic_context=perception_data) + memory_text
        
        # [修复#4+#6] 视觉意图自动截屏 — 用户提到视觉关键词时，自动截屏分析并注入上下文
        # 收紧视觉关键词：移除"什么情况""怎么回事"等过于宽泛的词，避免误触发
        _VISUAL_KEYWORDS = ["屏幕", "报错", "这个错", "截图", "截屏", "界面上"]
        _EXCLUDE_KEYWORDS = ["打开", "启动", "运行", "执行", "创建", "写", "保存", "搜索", "查", "找", "多少", "几个", "记", "笔记"]
        
        # 检测视觉意图：有视觉关键词 且 没有排除关键词
        has_visual_kw = any(kw in user_input for kw in _VISUAL_KEYWORDS)
        has_exclude_kw = any(kw in user_input for kw in _EXCLUDE_KEYWORDS)
        
        if has_visual_kw and not has_exclude_kw:
            try:
                logger.info("👁️ [自动截屏] 检测到视觉意图，正在自动截屏分析...")
                screen_analysis = self.skills.analyze_screen_content(question=user_input)
                if screen_analysis and not screen_analysis.startswith("❌"):
                    system_content += f"\n\n【自动截屏分析结果】以下是当前屏幕的实时内容：\n{screen_analysis}\n请基于以上信息回答用户问题，不需要再次调用 analyze_screen_content。"
                    logger.info("✅ [自动截屏] 已将截屏分析结果注入上下文")
            except Exception as e:
                logger.warning(f"⚠️ [自动截屏] 失败（不影响对话）: {e}")

        # [自主模式] 告知 AI 当前执行模式
        if self.skills.auto_execute:
            system_content += "\n\n【自主执行模式已开启】指挥官已授权你自主执行所有操作（Shell命令、代码运行等），无需在回复中询问是否执行，直接调用工具完成任务。"
        
        logger.info(f"📜 System Prompt (前200字): {system_content[:200]}...")
        logger.info(f"👁️ 感知数据: app={perception_data.get('app', 'N/A')[:30]}")

        try:
            # 🧠 调用大脑进行思考 (工具调用逻辑已封装在 Brain.chat 中)
            self.mouth.start_thinking()
            
            ai_reply = self.brain.chat(
                user_input=user_input,
                system_content=system_content,
                tools_schema=self.skills.get_tools_schema(),
                tool_executor=self.skills.execute_tool
            )
            
            self.mouth.stop_thinking()
            
            # [持久化] 保存 AI 回复
            if ai_reply and self.chat_store and self._gui_conv_id:
                try:
                    # 保存清理后的文本（去掉表情标签）
                    clean = re.sub(r"\[.*?\]", "", ai_reply).strip()
                    if clean:
                        self.chat_store.add_message(self._gui_conv_id, "assistant", clean)
                except Exception as e:
                    logger.warning(f"💾 保存AI回复失败: {e}")

            # 处理回复（语音播放）
            if ai_reply and not ("<｜DSML｜" in ai_reply or "<tool_code>" in ai_reply):
                self._process_response(ai_reply)

        except Exception as e:
            logger.error(f"AI 处理异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
            # 根据异常类型给出更具体的提示
            error_msg = str(e).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                hint = "思考超时，网络有点慢..."
            elif "connection" in error_msg or "connect" in error_msg:
                hint = "⚠️ 网络连接中断，请检查WiFi"
            elif "token" in error_msg or "length" in error_msg:
                hint = "任务太复杂，超出处理能力..."
            else:
                hint = "连接受到干扰..."
            
            # GUI字幕 + 终端输出（确保两种模式都能看到）
            print(f"⚠️ {hint}")
            self._emit_subtitle(hint, persistent=True)
            self._emit_state("IDLE")
            
            # 尝试语音提示（断网时会静默失败）
            try:
                self.mouth.speak(f"指挥官，{hint}")
            except Exception:
                pass  # TTS也断网了，至少字幕还能看到
            self.mouth.send_to_unity("Sorrow")


    # ========================
    # 🌅 晨间协议 (The Morning Protocol)
    # ========================
    def _check_and_trigger_morning_greet(self, found, identity):
        """
        判断是否满足"晨间问候"的条件。
        条件：看到指挥官 + 今天没打过招呼 + 没有正在处理的问候。
        """
        if self.is_processing_greet:
            return

        current_date = datetime.date.today()
        current_hour = datetime.datetime.now().hour

        # 触发条件：
        # 1. 看到了人脸 (found)
        # 2. 确认是指挥官 (identity == "Commander")
        # 3. 今天还没打过招呼
        # 4. 时间范围（测试阶段放宽为全天）
        if (found and identity == "Commander" and
                self.last_greet_date != current_date and
                6 <= current_hour < 12):  # 正式上线改为 6 <= current_hour < 12

            logger.info("🌅 检测到指挥官上线，触发晨间协议...")
            self.is_processing_greet = True  # 上锁

            # 启动后台线程执行，不卡住主循环的眼球追踪
            import threading
            threading.Thread(
                target=self._execute_morning_routine,
                args=(current_date,),
                daemon=True
            ).start()

    def _execute_morning_routine(self, current_date):
        """
        后台执行晨间协议：构造 Prompt → 调用大脑（含工具调用）→ 播报。
        """
        try:
            # 1. 构造系统级触发 Prompt
            morning_trigger = (
                "【系统指令】指挥官刚刚坐到电脑前，现在是早晨。"
                "请执行【晨间汇报任务】：\n"
                "1. 简短问候（不要太啰嗦，符合你的性格）。\n"
                "2. 必须调用 search_web 工具查询今日天气。\n"
                "3. 查询 1 条最新的科技或AI界大新闻。\n"
                "4. 结合以上信息，生成一段温馨的早报。\n"
                "注意：请直接生成最终的语音播报内容，口语化一点，不要太长。"
            )

            logger.info("🤖 AI 正在后台搜集情报...")

            # 2. 收集实时感知数据，构建完整的 System Prompt
            perception_data = self.eyes.get_perception_data()
            perception_data["user_present"] = True  # 已确认指挥官在座

            system_content = self.brain.get_system_prompt(dynamic_context=perception_data)
            logger.info("📜 晨间协议 System Prompt 已构建")

            # 3. 调用大脑（复用完整的工具调用链）
            self.mouth.start_thinking()

            ai_reply = self.brain.chat(
                user_input=morning_trigger,
                system_content=system_content,
                tools_schema=self.skills.get_tools_schema(),
                tool_executor=self.skills.execute_tool
            )

            self.mouth.stop_thinking()

            # 4. 播报结果
            if ai_reply:
                logger.info(f"🗣️ 晨间播报: {ai_reply[:80]}...")
                self.mouth.send_to_unity("Joy")  # 开心表情
                self._process_response(ai_reply)

            # 5. 记录日期，今天不再重复
            self.last_greet_date = current_date
            logger.info("✅ 晨间协议执行完毕")

        except Exception as e:
            logger.error(f"❌ 晨间协议执行失败: {e}")
            import traceback
            traceback.print_exc()
            self.mouth.stop_thinking()

        finally:
            self.is_processing_greet = False  # 解锁

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
        self.LAST_ACTIVE_TIME = time.time()
        fuguang_heartbeat.update_interaction()

        # 音量控制 - 本地快捷
        if any(word in text for word in ["太小", "听不见", "听不清", "小了"]):
            self.skills.control_volume("up", 3 if "很" in text else 2)
            return
        if any(word in text for word in ["太吵", "太大", "大了"]):
            self.skills.control_volume("down", 3 if "很" in text else 2)
            return
        
        # [新增] 礼貌回应 - 如果包含操作动词则不走问候快捷，交给AI处理
        action_verbs = ["点击", "打开", "输入", "搜索", "分析", "看看", "帮我", "运行", "启动"]
        has_action = any(v in text for v in action_verbs)
        if any(w in text for w in ["你好", "哈喽", "Hello", "hi"]) and not has_action:
            self.mouth.wave()
            self.mouth.speak("你好呀指挥官")
            return
        if any(word in text for word in ["静音", "闭嘴", "安静"]):
            self.skills.control_volume("mute")
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

        # 软件启动 - 智能分流
        # [优化] 短句(如"打开记事本")走本地快捷秒开，长句(如"打开记事本，不对，我是说计算器")交给AI理解
        if any(t in text for t in ["打开", "启动", "运行", "想听", "想玩", "想看"]):
            if len(text) <= 10:  # 短句走快捷通道
                if self.skills.open_app(text):
                    return
            # 长句或复杂句一律交给 AI 理解语义

        # 本地查询 - 快速响应
        if "几点" in text or "时间" in text:
            self.mouth.speak(self.skills.get_time())
            return
        if "几号" in text or "日期" in text:
            self.mouth.speak(self.skills.get_date())
            return
        if "电量" in text:
            self.mouth.speak(self.skills.check_battery())
            return
        if "状态" in text:
            self.mouth.speak(self.skills.check_status())
            return

        # [自主模式] 检测开关指令
        auto_on_triggers = ["你自己解决", "不用问我", "自己搞定", "不用再问", "你全权处理", "自主执行", "全权处理"]
        auto_off_triggers = ["问一下我", "要问我", "经过我同意", "确认一下", "关闭自主"]
        if any(t in text for t in auto_on_triggers):
            self.skills.auto_execute = True
            self.mouth.speak("收到，指挥官。自主执行模式已开启，我会自行处理所有操作。")
            logger.info("🤖 [自主模式] 已开启 - 跳过执行确认")
            return
        if any(t in text for t in auto_off_triggers):
            self.skills.auto_execute = False
            self.mouth.speak("好的指挥官，已切换回安全模式，执行操作前会先征求你的同意。")
            logger.info("🛡️ [自主模式] 已关闭 - 恢复执行确认")
            return

        # 交给 AI 处理
        self._handle_ai_response(text)

    def run(self):
        """主循环 - 生命的脉动"""
        print("=" * 60)
        print("✅ Fuguang IDE v1.1 - Nervous System")
        print("=" * 60)
        print("🎤 模式1：按住右CTRL说话，松开结束")
        print("👄 模式2：喊 '扶光/阿光' 语音唤醒")
        print("📝 增强：智能笔记（保存到桌面）")
        print("💻 增强：代码生成（项目 generated/ 目录）")
        print("=" * 60)

        logger.info("🚀 神经系统启动")
        self.mouth.send_to_unity("Joy")
        fuguang_heartbeat.start_heartbeat()
        
        # [修复] 根据配置启动注视追踪器
        if self.gaze_tracker and self.config.GAZE_TRACKING_ENABLED:
            self.gaze_tracker.start()
            logger.info("👁️ 注视追踪已启动")
        elif not self.config.CAMERA_ENABLED:
            logger.info("👁️ 注视追踪已禁用 (CAMERA_ENABLED=False)")
        
        # [新增] 启动时挥手致意
        time.sleep(2) # 等Unity准备好
        self.mouth.wave() 
        self.mouth.speak("指挥官，我上线了。")


        while True:
            # [GUI] 处理来自悬浮球的操作队列
            self._process_gui_actions()
            
            self._check_timeout()
            self.skills.check_reminders()
            
            now = time.time()
            
            # ================================
            # 🛡️ 安保协议（必须在语音处理之前）
            # ================================
            if self.camera and self.config.CAMERA_ENABLED:
                found, face_x, face_y, identity = self.camera.get_face_info()
                
                # 更新 GazeTracker 状态
                if found and self.gaze_tracker:
                    self.gaze_tracker.has_face = True
                    self.gaze_tracker.face_enter_time = self.gaze_tracker.face_enter_time or now
                
                # --- 情况 A: 发现入侵者 ---
                if found and identity == "Stranger":
                    if not self.security_mode_active:
                        # 首次检测到陌生人，触发警报
                        logger.warning("🚨 警告：检测到未授权人员！系统锁定。")
                        self.mouth.send_to_unity("Angry")
                        self.mouth.speak("警告。无法识别身份。系统已锁定，请立即离开。")
                        self.security_mode_active = True
                        self.last_security_warning_time = now
                    
                    # 锁定期间，每 10 秒刷新愤怒表情（防止被覆盖）
                    if now - self.last_security_warning_time > 10:
                        self.mouth.send_to_unity("Angry")
                        self.last_security_warning_time = now
                    
                    # ⚠️ 关键：跳过后续所有逻辑，不听语音，不思考
                    time.sleep(0.1)
                    continue
                
                # --- 情况 B: 指挥官回归（快速解锁）---
                if found and identity == "Commander" and self.security_mode_active:
                    logger.info("✅ 身份确认：指挥官。警报解除。")
                    self.mouth.send_to_unity("Joy")
                    self.mouth.speak("警报解除。欢迎回来，指挥官！")
                    self.security_mode_active = False
                    self.LAST_ACTIVE_TIME = now
                    fuguang_heartbeat.update_interaction()
                
                # --- 没人脸 + 锁定超60秒 → 自动解锁（防止误判后永久锁死）---
                if not found and self.security_mode_active:
                    lock_duration = now - getattr(self, 'last_security_warning_time', now)
                    if lock_duration > 60:
                        logger.info("🔓 安保超时(60s无人脸)，自动解锁。")
                        self.security_mode_active = False
                
                # --- 情况 C: 正常状态下的情感交互 ---
                if self.gaze_tracker and self.gaze_tracker.has_face and identity == "Commander":
                    stare_duration = now - self.gaze_tracker.face_enter_time
                    
                    # 回头杀（仅限指挥官）
                    if self.config.WELCOME_BACK_ENABLED:
                        if stare_duration < 1.0 and (now - self.LAST_ACTIVE_TIME > self.config.WELCOME_BACK_TIMEOUT):
                            logger.info("💕 检测到指挥官回归！触发回头杀")
                            self.mouth.send_to_unity("Surprised")
                            self.mouth.speak("啊，指挥官你回来啦！")
                            self.LAST_ACTIVE_TIME = now
                            fuguang_heartbeat.update_interaction()
                    
                    # 害羞机制（仅限指挥官）
                    if self.config.SHY_MODE_ENABLED:
                        if stare_duration > self.config.SHY_STARE_DURATION and (now - self.last_shy_time > self.config.SHY_COOLDOWN):
                            logger.info("😳 被盯得不好意思了...")
                            self.mouth.send_to_unity("Fun")
                            
                            import random
                            shy_replies = [
                                "一直盯着我看，我会不好意思的...",
                                "指挥官，我脸上有代码吗？",
                                "再看...再看我就要把你吃掉了，开玩笑的。",
                                "你在观察我？那我也观察你！",
                            ]
                            self.mouth.speak(random.choice(shy_replies))
                            
                            self.last_shy_time = now
                            self.LAST_ACTIVE_TIME = now
                            fuguang_heartbeat.update_interaction()

            # ================================
            # 🌅 晨间协议触发器 (The Morning Protocol)
            # ================================
            if self.camera and self.config.CAMERA_ENABLED:
                self._check_and_trigger_morning_greet(found, identity)

            # 显示状态
            status_icon = "🔒" if self.security_mode_active else ("⌨️" if self.TEXT_INPUT_REQUESTED else ("🎤" if self.IS_PTT_PRESSED else "🟢" if self.AWAKE_STATE == "voice_wake" else "💤"))
            print(f"\r{status_icon} [{self._get_status_text()}]", end="", flush=True)

            # ========================
            # 模式0: 打字输入（F1 触发）
            # [修复H-9] GUI 模式下跳过 input() 避免阻塞
            # ========================
            if self.TEXT_INPUT_REQUESTED:
                with self._input_state_lock:
                    self.TEXT_INPUT_REQUESTED = False
                
                # 检测是否在 GUI 模式（stdin 不可用时跳过）
                import sys
                if sys.stdin and sys.stdin.isatty():
                    print()  # 换行
                    try:
                        user_text = input("📝 请输入消息 (回车发送): ").strip()
                        if user_text:
                            logger.info(f"⌨️ 收到打字输入: {user_text}")
                            fuguang_heartbeat.update_interaction()
                            self._process_command(user_text)
                        else:
                            logger.info("⌨️ 取消输入（空消息）")
                    except EOFError:
                        logger.warning("⌨️ 输入被取消")
                else:
                    logger.info("⌨️ GUI 模式下 F1 打字输入已禁用，请使用悬浮球交互")
                continue

            # ========================
            # 模式1: PTT（按住录音）
            # ========================
            # 🔒 安全检查：锁定状态下不响应语音
            if self.security_mode_active:
                if self.IS_PTT_PRESSED:
                    logger.warning("🔒 系统锁定中，拒绝语音指令")
                time.sleep(0.1)
                continue
            
            # [新增] GUI 录音活跃时，跳过主循环的麦克风操作（避免抢麦）
            if self._gui_recording_active:
                time.sleep(0.1)
                continue

            if self.IS_PTT_PRESSED:
                with self.ears.get_microphone() as source:
                    logger.info("🎤 [PTT] 正在录音，松开CTRL结束...")
                    self._emit_state("LISTENING")  # [GUI] 通知界面状态
                    self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.05)  # [优化] 缩短到50ms，按下即录

                    try:
                        frames = []
                        while self.IS_PTT_PRESSED:
                            try:
                                buffer = source.stream.read(source.CHUNK)
                                frames.append(buffer)
                            except Exception:
                                break

                        if frames:
                            audio_data = b''.join(frames)
                            logger.info(f"🎤 录制完成，共 {len(audio_data)} 字节")

                            text = self.ears.listen_ali(audio_data)

                            if text == "[NETWORK_ERROR]":
                                logger.warning("⚠️ [PTT] 网络连接中断")
                                print("⚠️ 网络连接中断，请检查WiFi")
                                self._emit_subtitle("⚠️ 网络连接中断，请检查WiFi", persistent=True)
                                self._emit_state("IDLE")
                                try:
                                    self.mouth.speak("指挥官，网络似乎断开了")
                                except Exception:
                                    pass
                            elif text:
                                logger.info(f"👂 听到了: {text}")
                                fuguang_heartbeat.update_interaction()
                                self._process_command(text)
                            else:
                                logger.warning("未识别到语音")
                                self._emit_subtitle("没听清，请再说一次")
                                self._emit_state("IDLE")

                        time.sleep(0.1)
                        continue

                    except Exception as e:
                        logger.error(f"PTT 异常: {e}")
                        try:
                            self.mouth.speak("指挥官，处理出了点问题，请再说一次")
                        except Exception:
                            pass
                        continue

            # ========================
            # 模式2: 语音唤醒 / 待机监听
            # ========================
            # 🔒 安全检查：锁定状态下也不响应语音唤醒
            if self.security_mode_active:
                time.sleep(0.1)
                continue
            
            with self.ears.get_microphone() as source:
                self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.1)  # [优化] 缩短噪声检测

                if self.IS_PTT_PRESSED or self._gui_recording_active:
                    time.sleep(0.1)
                    continue

                try:
                    limit = 3 if self.AWAKE_STATE == "sleeping" else 10
                    audio = self.ears.recognizer.listen(source, timeout=2, phrase_time_limit=limit)

                    if self.IS_PTT_PRESSED:
                        continue

                    audio_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    text = self.ears.listen_ali(audio_data)

                    if text == "[NETWORK_ERROR]":
                        logger.warning("⚠️ 网络连接中断，无法识别语音")
                        continue

                    if text:
                        logger.info(f"👂 听到了: {text}")
                        has_wake_word, matched_word, clean_text = self.ears.check_wake_word_pinyin(text)

                        if self.AWAKE_STATE == "sleeping":
                            if has_wake_word:
                                logger.info(f"⚡️ 语音唤醒成功: {matched_word}")
                                self.AWAKE_STATE = "voice_wake"
                                self.LAST_ACTIVE_TIME = time.time()
                                fuguang_heartbeat.update_interaction()
                                self._emit_state("LISTENING")  # [GUI] 通知界面
                                self.mouth.send_to_unity("Surprised")
                                self.mouth.speak("我在。")
                                if clean_text:
                                    self._process_command(clean_text)
                            # [修复] 移除 should_auto_respond：待机模式下只响应唤醒词
                            # 之前"时间""日期"等关键词会跳过唤醒词直接触发回复
                        else:
                            self.LAST_ACTIVE_TIME = time.time()
                            self._process_command(text)

                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"异常: {e}")
