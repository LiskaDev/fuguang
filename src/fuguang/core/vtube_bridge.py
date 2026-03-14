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
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Fuguang.VTS")

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

                    # 查询可用热键
                    await self._fetch_hotkeys(ws)

                    # 保持连接，处理嘴巴张合等持续任务
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
    # 保持连接 + 嘴巴张合循环
    # ==================================================

    async def _keep_alive(self, ws):
        """保持连接活跃，处理嘴巴张合等持续任务"""
        interval = 1.0 / self.MOUTH_FPS  # 100ms

        while self._running:
            try:
                # 嘴巴张合：说话时持续发送参数
                if self._speaking and self._mouth_value > 0:
                    await self._inject_parameter(ws, "MouthOpen", self._mouth_value)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.warning(f"🎭 [VTS] keep_alive 异常: {e}")
                self.connected = False
                break

    async def _inject_parameter(self, ws, param_id: str, value: float):
        """注入单个参数值到 VTS"""
        request = {
            "apiName": self.API_NAME,
            "apiVersion": self.API_VERSION,
            "requestID": f"fuguang_param_{param_id}",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": True,
                "mode": "set",
                "parameterValues": [
                    {
                        "id": param_id,
                        "value": value,
                    }
                ]
            }
        }
        await ws.send(json.dumps(request))
        # 不等待响应，避免阻塞（fire-and-forget）
        # 消费响应以防堆积
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.05)
        except (asyncio.TimeoutError, Exception):
            pass

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
        """设置嘴巴张开程度（兼容接口）

        Args:
            value: 0.0（闭合）到 1.0（完全张开）
        """
        if value > 0:
            self.start_speaking(value)
        else:
            self.stop_speaking()
