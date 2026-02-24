# ball.py - 扶光悬浮球界面 (Lottie Vector v3.0)
"""
基于 PyQt6 的悬浮球 GUI — Lottie 矢量动画版

功能：
1. 状态可视化（Lottie 矢量动画 — 无限清晰）
2. 情绪表达（AI 表情标签驱动 Emoji 切换）
3. 表情切换 CSS 压扁弹开过渡（GPU 加速，无闪烁）
4. 鼠标拖拽
5. 信号/槽机制连接大脑

技术架构：
    QWebEngineView 内嵌 lottie_player.html
    → dotlottie-player 组件渲染 Lottie JSON
    → CSS transform scaleY() 做压扁/弹开过渡
    → Python 通过 runJavaScript() 调用 JS 切换表情

新增表情：
    只需两步：
    1. 将新表情 Lottie JSON 放入 gui/emotions/ 目录（如 excited.json）
    2. 在 EXPRESSION_EMOJI_MAP 中添加映射：{"Excited": "excited"}
    下载 URL：https://fonts.gstatic.com/s/e/notoemoji/latest/{unicode_codepoint}/lottie.json
    预览站：https://googlefonts.github.io/noto-emoji-animation/
"""

import sys
import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger("Fuguang")

# 尝试导入 PyQt6
try:
    from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QLabel
    from PyQt6.QtCore import (
        Qt, QPoint, QTimer, pyqtSignal, QObject, QSize, QUrl
    )
    from PyQt6.QtGui import QPainter, QColor, QAction
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    logger.warning("⚠️ PyQt6 未安装，GUI 功能将受限")

# 尝试导入 WebEngine（Lottie 渲染需要）
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    logger.warning("⚠️ PyQt6-WebEngine 未安装，将回退到 GIF 模式")


# 资源目录
EMOTIONS_DIR = Path(__file__).parent / "emotions"
HTML_TEMPLATE = Path(__file__).parent / "lottie_player.html"


class BallState:
    """悬浮球状态枚举"""
    IDLE = "IDLE"           # 静默 → neutral emoji
    LISTENING = "LISTENING" # 听 → listening emoji
    THINKING = "THINKING"   # 想 → thinking emoji
    SPEAKING = "SPEAKING"   # 说 → 由 AI 表情标签驱动
    ERROR = "ERROR"         # 错误 → error emoji


# 状态 → 默认 Emoji 映射
STATE_EMOJI_MAP = {
    BallState.IDLE: "neutral",
    BallState.LISTENING: "listening",
    BallState.THINKING: "thinking",
    BallState.SPEAKING: "joy",
    BallState.ERROR: "error",
}

# AI 表情标签 → Emoji 文件名映射
EXPRESSION_EMOJI_MAP = {
    # 基础 6 种
    "Joy": "joy",
    "Angry": "angry",
    "Sorrow": "sorrow",
    "Fun": "fun",
    "Surprised": "surprised",
    "Neutral": "neutral",
    # 扩展表情
    "Thinking": "thinking",
    "Shy": "shy",
    "Love": "love",
    "Proud": "proud",
    "Confused": "confused",
    "Apologetic": "apologetic",
    "Sleeping": "sleeping",
    "Working": "working",
    "Wave": "wave",
}


class FuguangSignals(QObject):
    """扶光信号中心 - 用于线程间通信"""
    
    state_changed = pyqtSignal(str)
    expression_changed = pyqtSignal(str)
    
    wake_up = pyqtSignal()
    sleep = pyqtSignal()
    screenshot_request = pyqtSignal()
    quit_request = pyqtSignal()
    ball_moved = pyqtSignal()
    ptt_toggle = pyqtSignal(bool)
    chat_history_request = pyqtSignal()  # [新增] 请求显示聊天记录


class FloatingBall(QWidget):
    """扶光的赛博战甲 - Lottie 矢量动画悬浮球 UI"""
    
    BALL_SIZE = 250

    def __init__(self, signals: Optional[FuguangSignals] = None):
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 未安装，请运行: pip install PyQt6")
            
        super().__init__()
        
        # 信号中心
        self.signals = signals or FuguangSignals()
        self.signals.state_changed.connect(self.set_state)
        self.signals.expression_changed.connect(self.set_expression)
        
        self.current_state = BallState.IDLE
        self.is_awake = False
        self.is_recording = False
        
        # Emoji 状态
        self._current_emoji = ""
        self._webview_ready = False
        self._pending_load = None  # 等待 webview 加载完成后再切换
        
        # 双击检测
        self.click_count = 0
        self.click_timer = QTimer(self)
        self.click_timer.timeout.connect(self._handle_click)
        
        # 鼠标拖拽
        self.old_pos = None
        self._is_dragging = False
        self._press_pos = None
        
        # 初始化 UI
        self._init_ui()
        
        logger.info("🔮 [GUI] Lottie 矢量悬浮球已初始化 (250×250)")

    def _init_ui(self):
        """初始化 UI 属性"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(self.BALL_SIZE, self.BALL_SIZE)
        
        if WEBENGINE_AVAILABLE:
            self._init_webview()
        else:
            self._init_fallback_label()
        
        # 初始位置（右下角）
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.BALL_SIZE - 20, screen.height() - self.BALL_SIZE - 20)

    def _init_webview(self):
        """初始化 QWebEngineView（Lottie 渲染）"""
        self._webview = QWebEngineView(self)
        self._webview.setGeometry(0, 0, self.BALL_SIZE, self.BALL_SIZE)
        
        # 透明背景
        self._webview.page().setBackgroundColor(QColor(0, 0, 0, 0))
        
        # 启用必要的 WebEngine 设置
        settings = self._webview.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        # 让鼠标事件透传到父 widget
        self._webview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # 加载 HTML 模板
        html_url = QUrl.fromLocalFile(str(HTML_TEMPLATE))
        self._webview.loadFinished.connect(self._on_webview_ready)
        self._webview.load(html_url)
        
        logger.debug(f"🔮 [GUI] WebEngine 加载: {html_url.toString()}")

    def _init_fallback_label(self):
        """GIF 回退模式（PyQtWebEngine 未安装时）"""
        from PyQt6.QtGui import QMovie
        self._emoji_label = QLabel(self)
        self._emoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._emoji_label.setGeometry(0, 0, self.BALL_SIZE, self.BALL_SIZE)
        self._emoji_label.setStyleSheet("background: transparent;")
        self._emoji_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # 加载默认 GIF
        gif_path = EMOTIONS_DIR / "neutral.gif"
        if gif_path.exists():
            movie = QMovie(str(gif_path))
            movie.setScaledSize(QSize(self.BALL_SIZE, self.BALL_SIZE))
            self._emoji_label.setMovie(movie)
            movie.start()
        
        self._webview_ready = True  # 回退模式直接就绪
        logger.info("🔮 [GUI] 回退到 GIF 模式")

    def _on_webview_ready(self, ok: bool):
        """WebView HTML 加载完成回调"""
        if ok:
            self._webview_ready = True
            logger.info("🔮 [GUI] Lottie 播放器就绪")
            
            # 加载默认表情
            if self._pending_load:
                self._do_switch(self._pending_load)
                self._pending_load = None
            else:
                self._do_load("neutral")
        else:
            logger.error("🔮 [GUI] Lottie 播放器加载失败")

    # ========================
    # Emoji 切换核心（Lottie + CSS 过渡）
    # ========================
    
    def _get_emoji_json_path(self, name: str) -> Optional[str]:
        """获取 Lottie JSON 文件的 file:// URL"""
        json_path = EMOTIONS_DIR / f"{name}.json"
        if json_path.exists():
            # 转换为 file:// URL（WebEngine 需要）
            return QUrl.fromLocalFile(str(json_path)).toString()
        logger.warning(f"🔮 [GUI] Lottie 文件不存在: {json_path}")
        return None

    def _do_load(self, name: str):
        """直接加载 Lottie（无过渡，用于初始化）"""
        url = self._get_emoji_json_path(name)
        if not url:
            if name != "neutral":
                url = self._get_emoji_json_path("neutral")
            if not url:
                return
        
        js = f'loadEmoji("{url}");'
        self._webview.page().runJavaScript(js)
        self._current_emoji = name
        logger.debug(f"🔮 [GUI] Lottie 初始加载: {name}")

    def _do_switch(self, name: str):
        """带压扁弹开过渡切换（CSS 动画）"""
        url = self._get_emoji_json_path(name)
        if not url:
            if name != "neutral":
                url = self._get_emoji_json_path("neutral")
                name = "neutral"
            if not url:
                return
        
        js = f'switchEmoji("{url}");'
        self._webview.page().runJavaScript(js)
        self._current_emoji = name
        logger.debug(f"🔮 [GUI] Lottie 切换: {name}")

    def _switch_emoji(self, name: str):
        """切换 Emoji（统一入口）"""
        if name == self._current_emoji:
            return
        
        if not self._webview_ready:
            self._pending_load = name
            return
        
        if WEBENGINE_AVAILABLE:
            self._do_switch(name)
        else:
            self._switch_gif_fallback(name)

    def _switch_gif_fallback(self, name: str):
        """GIF 回退切换"""
        from PyQt6.QtGui import QMovie
        gif_path = EMOTIONS_DIR / f"{name}.gif"
        if not gif_path.exists():
            gif_path = EMOTIONS_DIR / "neutral.gif"
        if gif_path.exists():
            movie = QMovie(str(gif_path))
            movie.setScaledSize(QSize(self.BALL_SIZE, self.BALL_SIZE))
            self._emoji_label.setMovie(movie)
            movie.start()
            self._current_emoji = name

    def set_state(self, state: str):
        """设置悬浮球状态 — 自动映射到对应 emoji"""
        if state not in STATE_EMOJI_MAP:
            return
        self.current_state = state
        emoji_name = STATE_EMOJI_MAP[state]
        self._switch_emoji(emoji_name)
        logger.debug(f"🔮 [GUI] 状态变更: {state} → {emoji_name}")

    def set_expression(self, expression: str):
        """设置 AI 表情 — 由 AI 回复中的表情标签驱动"""
        emoji_name = EXPRESSION_EMOJI_MAP.get(expression)
        if emoji_name:
            self._switch_emoji(emoji_name)
            logger.debug(f"🔮 [GUI] AI 表情: {expression} → {emoji_name}")
        else:
            logger.debug(f"🔮 [GUI] 未知表情标签: {expression}，忽略")

    # ========================
    # 绘制
    # ========================
    
    def paintEvent(self, event):
        """绘制透明背景"""
        pass

    # ========================
    # 鼠标交互
    # ========================
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()
            self._press_pos = event.globalPosition().toPoint()
            self._is_dragging = False

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()
            self.signals.ball_moved.emit()
            
            if self._press_pos:
                moved = event.globalPosition().toPoint() - self._press_pos
                if abs(moved.x()) > 5 or abs(moved.y()) > 5:
                    self._is_dragging = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging:
                self.click_count += 1
                if not self.click_timer.isActive():
                    self.click_timer.start(300)
            else:
                self.click_count = 0
                self.click_timer.stop()
        self.old_pos = None
        self._press_pos = None
        self._is_dragging = False

    def _handle_click(self):
        """处理点击（区分单击/双击）"""
        self.click_timer.stop()
        
        if self.click_count >= 2:
            logger.info("🔮 [GUI] 双击 - 触发截图分析")
            self.signals.screenshot_request.emit()
        else:
            if self.is_recording:
                logger.info("🔮 [GUI] 单击 - 停止录音")
                self.is_recording = False
                self.signals.ptt_toggle.emit(False)
            elif self.current_state == BallState.THINKING:
                logger.info("🔮 [GUI] 单击 - AI 思考中，请稍候")
            elif self.current_state == BallState.SPEAKING:
                logger.info("🔮 [GUI] 单击 - 打断说话 + 开始录音")
                self.is_recording = True
                self.signals.ptt_toggle.emit(True)
            else:
                if not self.is_awake:
                    logger.info("🔮 [GUI] 单击 - 唤醒 + 开始录音")
                    self.is_awake = True
                    self.signals.wake_up.emit()
                else:
                    logger.info("🔮 [GUI] 单击 - 开始录音")
                self.is_recording = True
                self.set_state(BallState.LISTENING)
                self.signals.ptt_toggle.emit(True)
        
        self.click_count = 0

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(30, 30, 30, 230);
                color: white;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QMenu::item:selected {
                background-color: rgba(0, 120, 215, 200);
            }
        """)
        
        toggle_action = QAction("休眠" if self.is_awake else "唤醒", self)
        toggle_action.triggered.connect(self._toggle_wake_sleep)
        menu.addAction(toggle_action)
        
        screenshot_action = QAction("📸 截图分析", self)
        screenshot_action.triggered.connect(self.signals.screenshot_request.emit)
        menu.addAction(screenshot_action)
        
        history_action = QAction("📜 聊天记录", self)
        history_action.triggered.connect(self.signals.chat_history_request.emit)
        menu.addAction(history_action)
        
        menu.addSeparator()
        
        quit_action = QAction("退出扶光", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        menu.exec(event.globalPos())

    def _quit(self):
        self.signals.quit_request.emit()
        QApplication.instance().quit()

    def _toggle_wake_sleep(self):
        if self.is_awake:
            if self.is_recording:
                self.is_recording = False
                self.signals.ptt_toggle.emit(False)
            self.is_awake = False
            self.set_state(BallState.IDLE)
            self.signals.sleep.emit()
        else:
            self.is_awake = True
            self.set_state(BallState.LISTENING)
            self.signals.wake_up.emit()

    def dragEnterEvent(self, event):
        if hasattr(self, 'drag_enter_handler') and self.drag_enter_handler:
            self.drag_enter_handler(event)
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if hasattr(self, 'drop_handler') and self.drop_handler:
            self.drop_handler(event)
        else:
            super().dropEvent(event)


# ========================
# 独立测试
# ========================

def main():
    """独立运行测试 — 演示 Lottie 矢量表情切换（含压扁弹开过渡）"""
    app = QApplication(sys.argv)
    
    signals = FuguangSignals()
    ball = FloatingBall(signals)
    
    def test_expressions():
        import itertools
        expressions = itertools.cycle([
            "Neutral", "Joy", "Angry", "Sorrow", "Fun", 
            "Surprised", "Thinking", "Shy", "Love", "Proud"
        ])
        
        def switch():
            expr = next(expressions)
            print(f"切换表情: {expr}")
            signals.expression_changed.emit(expr)
        
        timer = QTimer()
        timer.timeout.connect(switch)
        timer.start(3000)
        return timer
    
    timer = test_expressions()
    
    ball.show()
    print("🎨 Lottie 矢量悬浮球已启动！（无限清晰 + CSS 压扁弹开过渡）")
    print(f"- 表情资源: {EMOTIONS_DIR}")
    print(f"- Lottie JSON 数量: {len(list(EMOTIONS_DIR.glob('*.json')))}")
    print(f"- 表情映射: {len(EXPRESSION_EMOJI_MAP)} 种")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
