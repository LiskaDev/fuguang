
import time
import logging
import re
import json
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

        # 状态变量
        self.AWAKE_STATE = "sleeping"  # sleeping / voice_wake
        self.IS_PTT_PRESSED = False
        self.LAST_ACTIVE_TIME = 0
        
        # [新增] 害羞机制冷却时间
        self.last_shy_time = 0
        
        # [升级] 安保系统状态
        self.security_mode_active = False  # True=锁定中，拒绝一切指令
        self.last_security_warning_time = 0  # 上次警告时间（用于周期性警告）

        # 注册按键监听
        keyboard.hook(self._on_key_event)

        logger.info("🧠 神经系统初始化完毕...")

    def _on_key_event(self, event):
        """按键事件处理"""
        if event.name == 'right ctrl':
            if event.event_type == 'down' and not self.IS_PTT_PRESSED:
                self.IS_PTT_PRESSED = True
                logger.info("🎤 [PTT] 键按下")
                fuguang_heartbeat.update_interaction()
            elif event.event_type == 'up' and self.IS_PTT_PRESSED:
                self.IS_PTT_PRESSED = False
                self.LAST_ACTIVE_TIME = time.time()
                logger.info("🎤 [PTT] 录音结束")

    def _check_timeout(self):
        """检查语音唤醒是否超时"""
        if self.AWAKE_STATE == "voice_wake":
            elapsed = time.time() - self.LAST_ACTIVE_TIME
            if elapsed > self.VOICE_WAKE_DURATION:
                self.AWAKE_STATE = "sleeping"
                logger.info("💤 语音唤醒超时，回到待机")

    def _get_status_text(self) -> str:
        """获取当前状态文本"""
        if self.IS_PTT_PRESSED:
            return "🎤 PTT录音中"
        elif self.AWAKE_STATE == "sleeping":
            return "💤 待机中（按住CTRL说话或叫我名字）"
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
            if tag in ["Joy", "Angry", "Sorrow", "Fun", "Surprised", "Neutral"]:
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
        """处理 AI 回复"""
        self.LAST_ACTIVE_TIME = time.time()
        fuguang_heartbeat.update_interaction()

        # 检索相关记忆
        related_memories = self.brain.memory_system.search_memory(user_input)
        memory_text = ""
        if related_memories:
            memory_text = "\n【相关长期记忆】\n" + "\n".join(related_memories)
            logger.info(f"🧠 激活记忆: {related_memories}")

        # [新增] 收集实时感知数据
        perception_data = self.eyes.get_perception_data()
        perception_data["user_present"] = self.gaze_tracker.has_face if hasattr(self.gaze_tracker, 'has_face') else None
        
        system_content = self.brain.get_system_prompt(dynamic_context=perception_data) + memory_text
        logger.info(f"📜 System Prompt (前200字): {system_content[:200]}...")
        logger.info(f"👁️ 感知数据: app={perception_data.get('app', 'N/A')[:30]}")
        
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
                # self.mouth.speak("让我想想...") # (可选)

                response = self.brain.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    tools=self.skills.get_tools_schema(),  # [修复] 使用动态方法获取工具列表
                    tool_choice="auto",
                    stream=False,
                    temperature=0.8,
                    max_tokens=4096  # [修复] 增大 token 限制，支持生成复杂代码（如贪吃蛇游戏）
                )


                message = response.choices[0].message

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
                        result = self.skills.execute_tool(func_name, func_args)

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
                ai_reply = "指挥官，这个问题有点复杂，我需要更多时间思考..."

            self.brain.chat_history.append({"role": "user", "content": user_input})
            self.brain.chat_history.append({"role": "assistant", "content": ai_reply})
            self.brain.trim_history()

            if ai_reply and not ("<｜DSML｜" in ai_reply or "<tool_code>" in ai_reply):
                self._process_response(ai_reply)

            self.mouth.stop_thinking()

            current_mem = self.brain.load_memory()
            current_mem["last_interaction"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.brain.save_memory(current_mem)
            
            # 🧠 潜意识记忆：后台分析对话，自动归档重要信息
            self.brain.analyze_and_store_memory(user_input, ai_reply)


        except Exception as e:
            logger.error(f"AI 处理异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
            # 根据异常类型给出更具体的提示
            error_msg = str(e).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                self.mouth.speak("指挥官，思考时间太长了，网络有点慢...")
            elif "token" in error_msg or "length" in error_msg:
                self.mouth.speak("指挥官，这个任务太复杂了，超出了我的处理能力...")
            else:
                self.mouth.speak("指挥官，连接受到干扰...")
            self.mouth.send_to_unity("Sorrow")

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
        
        # [新增] 礼貌回应
        if any(w in text for w in ["你好", "哈喽", "Hello", "hi"]):
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

        # 软件启动 - 本地快捷
        if any(t in text for t in ["打开", "启动", "运行", "想听", "想玩", "想看"]):
            if self.skills.open_app(text):
                return

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
                
                # --- 情况 B: 指挥官回归 ---
                if found and identity == "Commander" and self.security_mode_active:
                    logger.info("✅ 身份确认：指挥官。警报解除。")
                    self.mouth.send_to_unity("Joy")
                    self.mouth.speak("警报解除。欢迎回来，指挥官！")
                    self.security_mode_active = False
                    self.LAST_ACTIVE_TIME = now
                    fuguang_heartbeat.update_interaction()
                
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

            # 显示状态
            status_icon = "🔒" if self.security_mode_active else ("🎤" if self.IS_PTT_PRESSED else "🟢" if self.AWAKE_STATE == "voice_wake" else "💤")
            print(f"\r{status_icon} [{self._get_status_text()}]", end="", flush=True)

            # ========================
            # 模式1: PTT（按住录音）
            # ========================
            # 🔒 安全检查：锁定状态下不响应语音
            if self.security_mode_active:
                if self.IS_PTT_PRESSED:
                    logger.warning("🔒 系统锁定中，拒绝语音指令")
                time.sleep(0.1)
                continue
            
            if self.IS_PTT_PRESSED:
                with self.ears.get_microphone() as source:
                    logger.info("🎤 [PTT] 正在录音，松开CTRL结束...")
                    self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.2)

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
            # 🔒 安全检查：锁定状态下也不响应语音唤醒
            if self.security_mode_active:
                time.sleep(0.1)
                continue
            
            with self.ears.get_microphone() as source:
                self.ears.recognizer.adjust_for_ambient_noise(source, duration=0.3)

                if self.IS_PTT_PRESSED:
                    time.sleep(0.1)
                    continue

                try:
                    limit = 3 if self.AWAKE_STATE == "sleeping" else 10
                    audio = self.ears.recognizer.listen(source, timeout=2, phrase_time_limit=limit)

                    if self.IS_PTT_PRESSED:
                        continue

                    audio_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    text = self.ears.listen_ali(audio_data)

                    if text:
                        logger.info(f"👂 听到了: {text}")
                        has_wake_word, matched_word, clean_text = self.ears.check_wake_word_pinyin(text)

                        if self.AWAKE_STATE == "sleeping":
                            if has_wake_word:
                                logger.info(f"⚡️ 语音唤醒成功: {matched_word}")
                                self.AWAKE_STATE = "voice_wake"
                                self.LAST_ACTIVE_TIME = time.time()
                                fuguang_heartbeat.update_interaction()
                                self.mouth.send_to_unity("Surprised")
                                self.mouth.speak("我在。")
                                if clean_text:
                                    self._process_command(clean_text)
                            elif self.brain.should_auto_respond(text):
                                self._process_command(text)
                        else:
                            self.LAST_ACTIVE_TIME = time.time()
                            self._process_command(text)

                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"异常: {e}")
