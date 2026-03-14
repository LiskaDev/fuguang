"""
🎭 VTube Studio 桥接 (VTube Studio Bridge)
职责：通过 WebSocket 连接 VTube Studio API，实现 Live2D 模型的表情切换和嘴巴张合控制

架构：
  VTube Studio (ws://localhost:8001) ←── VTubeBridge (WS Client) ──→ NervousSystem / Mouth

消息流程：
  1. 连接 → 认证（token 持久化到 data/vts_token.txt）
  2. 查询可用热键 → 日志打印列表
  3. 表情切换：trigger_expression(emotion) → HotkeyTriggerRequest
  4. 嘴巴张合：start_speaking() / stop_speaking() → InjectParameterDataRequest 循环

启动方式：
  - NervousSystem.__init__ 中自动启动（VTS_ENABLED=true 时）
  - 后台 daemon 线程运行 asyncio 事件循环
"""

import asyncio
import json
import logging
import random
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Fuguang.VTS")


# ================================================================
# 自然运动控制器 (基于 VTS-AI-Plugin/vtuber_movement.py)
# 纯数学逻辑，随机头部晃动 + 眼球转动 + 眨眼
# ================================================================

# 需要在 VTS 中创建的自定义参数
CUSTOM_PARAMS = [
    {"parameterName": "AIFaceAngleX",  "explanation": "AI head X",   "min": -30, "max": 30,  "defaultValue": 0},
    {"parameterName": "AIFaceAngleY",  "explanation": "AI head Y",   "min": -30, "max": 30,  "defaultValue": 0},
    {"parameterName": "AIFaceAngleZ",  "explanation": "AI head Z",   "min": -90, "max": 90,  "defaultValue": 0},
    {"parameterName": "AIEyeLeftX",    "explanation": "AI eye X",    "min": -1,  "max": 1,   "defaultValue": 0},
    {"parameterName": "AIEyeLeftY",    "explanation": "AI eye Y",    "min": -1,  "max": 1,   "defaultValue": 0},
    {"parameterName": "AIEyeOpenLeft",  "explanation": "AI eyelid L", "min": 0,   "max": 1,   "defaultValue": 1},
    {"parameterName": "AIEyeOpenRight", "explanation": "AI eyelid R", "min": 0,   "max": 1,   "defaultValue": 1},
]


class NaturalMotion:
    """自然运动生成器 - 让 Live2D 模型看起来活着

    三个独立系统：
    1. 头部随机微晃 (FaceAngleX/Y/Z)
    2. 眼球随机转动 (EyeLeftX/Y)
    3. 随机眨眼 (EyeOpenLeft/Right)

    每帧调用 update(current_time) 更新状态，
    通过 get_parameters() 获取当前参数值列表。
    """

    def __init__(self):
        # --- 头部 ---
        self.head = [0.0, 0.0, 0.0]          # 当前值 [X, Y, Z]
        self._target_head = [0.0, 0.0, 0.0]  # 目标值
        self._next_head_move = 0.0            # 下次换目标的时间
        # 幅度范围 (度)
        self._head_range = [
            (-10, 10),   # X: 左右摇头
            (-8, 8),     # Y: 上下点头
            (-5, 5),     # Z: 歪头
        ]
        self._head_interval = (2.0, 5.0)     # 换目标间隔 (秒)

        # --- 眼球 ---
        self.eyes = [0.0, 0.0]               # 当前值 [X, Y]
        self._target_eyes = [0.0, 0.0]
        self._next_eye_move = 0.0
        self._eye_range = [
            (-0.5, 0.5),  # X: 左右看
            (-0.3, 0.3),  # Y: 上下看
        ]
        self._eye_interval = (1.0, 3.0)

        # --- 眨眼 ---
        self.eye_lids = [1.0, 1.0]           # 1=睁眼, 0=闭眼
        self._next_blink = 0.0
        self._blink_end = 0.0
        self._blink_interval = (2.0, 6.0)    # 眨眼间隔
        self._blink_duration = 0.12          # 闭眼持续时间 (秒)
        self._is_blinking = False

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def update(self, current_time: float):
        """每帧调用，更新所有运动状态"""
        self._update_head(current_time)
        self._update_eyes(current_time)
        self._update_blink(current_time)

    def _update_head(self, t: float):
        if t > self._next_head_move:
            self._next_head_move = t + random.uniform(*self._head_interval)
            for i in range(3):
                self._target_head[i] = random.uniform(*self._head_range[i])
        for i in range(3):
            self.head[i] = self._lerp(self.head[i], self._target_head[i], 0.1)

    def _update_eyes(self, t: float):
        if t > self._next_eye_move:
            self._next_eye_move = t + random.uniform(*self._eye_interval)
            for i in range(2):
                self._target_eyes[i] = random.uniform(*self._eye_range[i])
        for i in range(2):
            self.eyes[i] = self._lerp(self.eyes[i], self._target_eyes[i], 0.5)

    def _update_blink(self, t: float):
        if self._is_blinking:
            if t > self._blink_end:
                self.eye_lids = [1.0, 1.0]
                self._is_blinking = False
                self._next_blink = t + random.uniform(*self._blink_interval)
        else:
            if t > self._next_blink:
                self.eye_lids = [0.0, 0.0]
                self._is_blinking = True
                self._blink_end = t + self._blink_duration

    def get_parameters(self) -> list[dict]:
        """返回当前帧的 VTS 参数列表"""
        return [
            {"id": "AIFaceAngleX",  "value": self.head[0]},
            {"id": "AIFaceAngleY",  "value": self.head[1]},
            {"id": "AIFaceAngleZ",  "value": self.head[2]},
            {"id": "AIEyeLeftX",    "value": self.eyes[0]},
            {"id": "AIEyeLeftY",    "value": self.eyes[1]},
            {"id": "AIEyeOpenLeft",  "value": self.eye_lids[0]},
            {"id": "AIEyeOpenRight", "value": self.eye_lids[1]},
        ]

# ================================================================
# 扶光表情标签 → VTS 热键名 映射表
# 键 = 扶光 AI 输出的表情标签 (如 [Joy], [Angry])
# 值 = VTS 中对应的热键名称 (case-insensitive 匹配)
# ================================================================
EMOTION_HOTKEY_MAP = {
    "Joy": "fun",
    "Angry": "angry",
    "Sorrow": "sorrow",
    "Fun": "fun",
    "Surprised": "surprised",
    "Shy": "shy",
    "Love": "shy",           # Love 复用 shy 表情
    "Proud": "fun",           # Proud 复用 fun 表情
    "Confused": "thinking",   # Confused 复用 thinking 表情
    "Thinking": "thinking",
    "Sleeping": "shy",        # Sleeping 复用 shy 表情
    "Apologetic": "shy",      # Apologetic 复用 shy 表情
}


class VTubeBridge:
    """
    VTube Studio API 桥接层

    连接 VTS 的 WebSocket API，控制 Live2D 模型的表情和嘴巴。
    所有公开方法都是线程安全的（通过 asyncio 事件循环调度）。
    连接失败时静默降级，不影响扶光正常运行。
    """

    PLUGIN_NAME = "Fuguang AI Pet"
    PLUGIN_DEVELOPER = "ALan"
    API_NAME = "VTubeStudioPublicAPI"
    API_VERSION = "1.0"

    # 嘴巴张合参数发送频率 (每秒次数)
    MOUTH_FPS = 10

    def __init__(self, config):
        """
        Args:
            config: ConfigManager 实例
        """
        self.config = config
        self.port = getattr(config, 'VTS_PORT', 8001)

        # 连接状态
        self.connected = False
        self._authenticated = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None

        # 嘴巴张合控制
        self._speaking = False
        self._mouth_value = 0.0

        # 可用热键缓存 (连接后填充)
        self._available_hotkeys: list[dict] = []

        # 当前激活的表情热键 (用于切换时先关闭上一个)
        self._last_expression: Optional[str] = None

        # 自然运动控制器
        self._motion = NaturalMotion()

        # Token 持久化路径
        data_dir = getattr(config, 'DATA_DIR', Path('.') / 'data')
        self._token_file = Path(data_dir) / "vts_token.txt"

        logger.info(f"🎭 [VTS] VTubeBridge 初始化完成，目标: ws://localhost:{self.port}")

    # ==================================================
    # 启动 / 停止
    # ==================================================

    def start(self):
        """在后台 daemon 线程中启动 VTS 桥接"""
        if self._running:
            logger.warning("🎭 [VTS] VTubeBridge 已在运行")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="VTubeBridge"
        )
        self._thread.start()
        logger.info("🎭 [VTS] VTubeBridge 后台线程已启动")

    def stop(self):
        """停止桥接"""
        self._running = False
        self._speaking = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("🎭 [VTS] VTubeBridge 已停止")

    def _run_loop(self):
        """后台线程入口：运行 asyncio 事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_loop())
        except Exception as e:
            logger.error(f"🎭 [VTS] 事件循环异常退出: {e}")
        finally:
            self._loop.close()
            self._loop = None

    # ==================================================
    # WebSocket 主循环（自动重连）
    # ==================================================

    async def _ws_loop(self):
        """WebSocket 客户端主循环（自动重连，指数退避）"""
        try:
            import websockets
        except ImportError:
            logger.error("🎭 [VTS] 缺少 websockets 库，请安装: pip install websockets")
            return

        retry_count = 0
        retry_delay = 5  # 初始 5 秒

        while self._running:
            try:
                ws_url = f"ws://localhost:{self.port}"
                logger.info(f"🎭 [VTS] 正在连接: {ws_url}")

                async with websockets.connect(ws_url) as ws:
                    self._ws = ws
                    logger.info("🎭 [VTS] ✅ WebSocket 已连接")
                    retry_count = 0
                    retry_delay = 5

                    # 认证
                    auth_ok = await self._authenticate(ws)
                    if not auth_ok:
                        logger.warning("🎭 [VTS] 认证失败，30秒后重试")
                        self._ws = None
                        await asyncio.sleep(30)
                        continue

                    self.connected = True
                    self._authenticated = True
                    logger.info("🎭 [VTS] ✅ 认证成功！")

                    # 创建自定义参数（自然运动用）
                    await self._create_custom_parameters(ws)

                    # 查询可用热键
                    await self._fetch_hotkeys(ws)

                    # 保持连接，处理嘴巴张合 + 自然运动
                    await self._keep_alive(ws)

            except Exception as e:
                self.connected = False
                self._authenticated = False
                self._ws = None

                if self._running:
                    retry_count += 1
                    if retry_count <= 3 or retry_count % 6 == 0:
                        logger.warning(
                            f"🎭 [VTS] 连接失败 (第{retry_count}次): {e}，"
                            f"{retry_delay}秒后重连..."
                        )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)

    # ==================================================
    # 认证流程
    # ==================================================

    async def _authenticate(self, ws) -> bool:
        """完成 VTS 认证流程（token 持久化）"""
        # 1. 尝试用已保存的 token 认证
        saved_token = self._load_token()
        if saved_token:
            logger.info("🎭 [VTS] 尝试用已保存的 token 认证...")
            if await self._auth_with_token(ws, saved_token):
                return True
            logger.warning("🎭 [VTS] 已保存的 token 无效，重新请求授权...")

        # 2. 请求新 token（VTS 弹出授权窗口）
        logger.info('🎭 [VTS] 请求新 token（请在 VTS 中点击"允许"）...')
        new_token = await self._request_token(ws)
        if not new_token:
            return False

        # 3. 用新 token 认证
        if await self._auth_with_token(ws, new_token):
            self._save_token(new_token)
            logger.info("🎭 [VTS] Token 已保存到 data/vts_token.txt")
            return True

        return False

    async def _request_token(self, ws) -> Optional[str]:
        """发送 AuthenticationTokenRequest，等待用户在 VTS 中点击允许"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": "fuguang_token_req",
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": self.PLUGIN_NAME,
                "pluginDeveloper": self.PLUGIN_DEVELOPER,
            }
        }
        await ws.send(json.dumps(request))

        try:
            # 等待最多 60 秒（用户需要手动点击 VTS 弹窗）
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            resp = json.loads(raw)

            if resp.get("messageType") == "AuthenticationTokenResponse":
                token = resp.get("data", {}).get("authenticationToken", "")
                if token:
                    return token

            # 用户拒绝或报错
            error_msg = resp.get("data", {}).get("message", "未知错误")
            logger.warning(f"🎭 [VTS] Token 请求失败: {error_msg}")
            return None

        except asyncio.TimeoutError:
            logger.warning("🎭 [VTS] 等待用户授权超时（60秒）")
            return None

    async def _auth_with_token(self, ws, token: str) -> bool:
        """用 token 进行会话认证"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": "fuguang_auth",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": self.PLUGIN_NAME,
                "pluginDeveloper": self.PLUGIN_DEVELOPER,
                "authenticationToken": token,
            }
        }
        await ws.send(json.dumps(request))

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            resp = json.loads(raw)

            if resp.get("messageType") == "AuthenticationResponse":
                return resp.get("data", {}).get("authenticated", False)

            return False

        except asyncio.TimeoutError:
            logger.warning("🎭 [VTS] 认证响应超时")
            return False

    # ==================================================
    # Token 持久化
    # ==================================================

    def _load_token(self) -> Optional[str]:
        """从文件加载已保存的 token"""
        try:
            if self._token_file.exists():
                token = self._token_file.read_text(encoding="utf-8").strip()
                if token:
                    return token
        except Exception as e:
            logger.warning(f"🎭 [VTS] 读取 token 失败: {e}")
        return None

    def _save_token(self, token: str):
        """保存 token 到文件"""
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            self._token_file.write_text(token, encoding="utf-8")
        except Exception as e:
            logger.warning(f"🎭 [VTS] 保存 token 失败: {e}")

    # ==================================================
    # 热键查询
    # ==================================================

    async def _fetch_hotkeys(self, ws):
        """查询当前模型的可用热键列表"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": "fuguang_hotkeys",
            "messageType": "HotkeysInCurrentModelRequest",
            "data": {}
        }
        await ws.send(json.dumps(request))

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            resp = json.loads(raw)

            if resp.get("messageType") == "HotkeysInCurrentModelResponse":
                hotkeys = resp.get("data", {}).get("availableHotkeys", [])
                self._available_hotkeys = hotkeys
                model_name = resp.get("data", {}).get("modelName", "未知")

                logger.info(f"🎭 [VTS] 当前模型: {model_name}，可用热键 {len(hotkeys)} 个:")
                for hk in hotkeys:
                    logger.info(
                        f"  🔑 [{hk.get('type', '?')}] "
                        f"名称=\"{hk.get('name', '?')}\" "
                        f"ID={hk.get('hotkeyID', '?')[:16]}..."
                    )

        except asyncio.TimeoutError:
            logger.warning("🎭 [VTS] 查询热键超时")
        except Exception as e:
            logger.warning(f"🎭 [VTS] 查询热键失败: {e}")

    # ==================================================
    # 自定义参数创建（自然运动用）
    # ==================================================

    async def _create_custom_parameters(self, ws):
        """在 VTS 中创建 7 个自定义参数（幂等，重复创建不报错）"""
        for param in CUSTOM_PARAMS:
            request = {
                "apiName": self.API_NAME,
                "apiVersion": self.API_VERSION,
                "requestID": f"fuguang_create_{param['parameterName']}",
                "messageType": "ParameterCreationRequest",
                "data": param
            }
            try:
                await ws.send(json.dumps(request))
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                resp = json.loads(raw)
                if resp.get("messageType") == "APIError":
                    logger.warning(
                        f"🎭 [VTS] 创建参数 {param['parameterName']} 失败: "
                        f"{resp.get('data', {}).get('message', '')}"
                    )
            except Exception as e:
                logger.warning(f"🎭 [VTS] 创建参数 {param['parameterName']} 异常: {e}")

        logger.info(
            "🎭 [VTS] ✅ 7 个自定义参数已创建：\n"
            "  AIFaceAngleX/Y/Z (头部) + AIEyeLeftX/Y (眼球) + AIEyeOpenLeft/Right (眼皮)\n"
            "  ⚠️ 请到 VTS 中将这些参数映射到模型的对应参数上！\n"
            "  操作：VTS → 参数设置 → 找到 AI* 开头的参数 → 映射到 FaceAngle/EyeBall/EyeOpen 等"
        )

    # ==================================================
    # 保持连接 + 自然运动 + 嘴巴张合循环
    # ==================================================

    async def _keep_alive(self, ws):
        """保持连接活跃，每帧更新自然运动 + 嘴巴张合"""
        interval = 1.0 / self.MOUTH_FPS  # 100ms = 10fps

        while self._running:
            try:
                current_time = time.time()

                # 更新自然运动状态
                self._motion.update(current_time)

                # 收集所有要注入的参数
                params = self._motion.get_parameters()

                # 嘴巴张合：说话时叠加
                if self._speaking and self._mouth_value > 0:
                    params.append({"id": "MouthOpen", "value": self._mouth_value})

                # 批量注入
                await self._inject_parameters(ws, params)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.warning(f"🎭 [VTS] keep_alive 异常: {e}")
                self.connected = False
                break

    async def _inject_parameters(self, ws, params: list[dict]):
        """批量注入多个参数到 VTS（一次 WebSocket 请求）"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": "fuguang_motion",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": True,
                "mode": "set",
                "parameterValues": params
            }
        }
        await ws.send(json.dumps(request))
        # 消费响应以防堆积
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.05)
        except (asyncio.TimeoutError, Exception):
            pass

    async def _inject_parameter(self, ws, param_id: str, value: float):
        """注入单个参数值到 VTS"""
        await self._inject_parameters(ws, [{"id": param_id, "value": value}])

    async def _trigger_hotkey_async(self, ws, hotkey_name: str):
        """异步触发热键"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": f"fuguang_hotkey_{hotkey_name}",
            "messageType": "HotkeyTriggerRequest",
            "data": {
                "hotkeyID": hotkey_name,  # VTS 支持按名称触发 (case-insensitive)
            }
        }
        await ws.send(json.dumps(request))
        # 消费响应
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2)
            resp = json.loads(raw)
            if resp.get("messageType") == "APIError":
                error_msg = resp.get("data", {}).get("message", "")
                logger.debug(f"🎭 [VTS] 热键 '{hotkey_name}' 触发失败: {error_msg}")
            else:
                logger.debug(f"🎭 [VTS] 热键 '{hotkey_name}' 已触发")
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.debug(f"🎭 [VTS] 热键响应处理异常: {e}")

    # ==================================================
    # 公开 API（线程安全，从任意线程调用）
    # ==================================================

    def trigger_hotkey(self, hotkey_name: str):
        """触发 VTS 热键（按名称，case-insensitive）

        线程安全：可从任意线程调用。
        降级：未连接时静默返回。

        Args:
            hotkey_name: VTS 热键名称
        """
        if not self.connected or not self._loop or not self._ws:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._trigger_hotkey_async(self._ws, hotkey_name),
                self._loop
            )
        except Exception as e:
            logger.debug(f"🎭 [VTS] trigger_hotkey 调度失败: {e}")

    def trigger_expression(self, emotion: str):
        """根据扶光表情标签触发 VTS 表情热键

        VTS 的 ToggleExpression 是叠加模式，触发新表情不会自动清除旧的。
        所以切换时需要：先再触发一次上一个表情（关闭它）→ 再触发新表情（打开它）。

        Args:
            emotion: 扶光表情标签，如 "Joy", "Angry", "Thinking" 等
        """
        hotkey_name = EMOTION_HOTKEY_MAP.get(emotion)
        if not hotkey_name:
            return  # 未映射的表情（如 Neutral, Wave, Working）静默跳过

        # 同一个表情不重复触发（避免关掉又开）
        if hotkey_name == self._last_expression:
            return

        # 关掉上一个表情（再触发一次 = Toggle Off）
        if self._last_expression:
            self.trigger_hotkey(self._last_expression)

        # 触发新表情（Toggle On）
        self.trigger_hotkey(hotkey_name)
        self._last_expression = hotkey_name
        logger.debug(f"🎭 [VTS] 表情切换: {emotion} → {hotkey_name}")

    def start_speaking(self, mouth_value: float = 0.8):
        """开始说话 - 启动嘴巴张合参数持续发送

        Args:
            mouth_value: 嘴巴张开程度 (0.0-1.0)
        """
        if not self.connected:
            return
        self._mouth_value = max(0.0, min(1.0, mouth_value))
        self._speaking = True
        logger.debug(f"🎭 [VTS] 嘴巴张开: {self._mouth_value}")

    def stop_speaking(self):
        """停止说话 - 停止循环发送 + 主动发一次 MouthOpen=0.0 立即关嘴"""
        self._speaking = False
        self._mouth_value = 0.0

        # 主动发送一次 0.0 立即关嘴（不依赖 VTS 的 ~1秒参数超时回弹）
        if self.connected and self._loop and self._ws:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._inject_parameter(self._ws, "MouthOpen", 0.0),
                    self._loop
                )
            except Exception as e:
                logger.debug(f"🎭 [VTS] 关嘴指令发送失败: {e}")

        logger.debug("🎭 [VTS] 嘴巴关闭")

    def set_mouth_open(self, value: float):
        """设置嘴巴张开程度（音量驱动，每个音频 chunk 调用一次）

        Args:
            value: 0.0（闭合）到 1.0（完全张开），已经过 RMS+平滑处理
        """
        self._mouth_value = max(0.0, min(1.0, value))
        self._speaking = self._mouth_value > 0.01
