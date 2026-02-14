# ball.py - 扶光悬浮球界面 (赛博战甲 v1.0)
"""
基于 PyQt6 的悬浮球 GUI

功能：
1. 状态可视化（静默/听/想/说）
2. 呼吸灯效果
3. 鼠标拖拽
4. 信号/槽机制连接大脑

使用方法：
    - 单击：唤醒/休眠
    - 双击：截图分析
    - 右键：菜单
"""

import sys
import logging
from typing import Optional

logger = logging.getLogger("Fuguang")

# 尝试导入 PyQt6
try:
    from PyQt6.QtWidgets import QApplication, QWidget, QMenu
    from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
    from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QAction, QBrush, QFont
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    logger.warning("⚠️ PyQt6 未安装，GUI 功能将受限")


class BallState:
    """悬浮球状态枚举"""
    IDLE = "IDLE"           # 静默 - 幽灵蓝
    LISTENING = "LISTENING" # 听 - 赤红
    THINKING = "THINKING"   # 想 - 荧光绿
    SPEAKING = "SPEAKING"   # 说 - 紫色
    ERROR = "ERROR"         # 错误 - 橙色


class FuguangSignals(QObject):
    """扶光信号中心 - 用于线程间通信"""
    
    # 状态变更信号 (从业务逻辑 -> UI)
    state_changed = pyqtSignal(str)  # 参数: 新状态
    
    # 用户交互信号 (从 UI -> 业务逻辑)
    wake_up = pyqtSignal()           # 唤醒
    sleep = pyqtSignal()             # 休眠
    screenshot_request = pyqtSignal() # 截图分析请求
    quit_request = pyqtSignal()      # 退出请求
    ball_moved = pyqtSignal()        # 悬浮球被拖动（通知 HUD 跟随）
    ptt_toggle = pyqtSignal(bool)    # PTT 切换 (True=开始录音, False=停止录音)


class FloatingBall(QWidget):
    """扶光的赛博战甲 - 悬浮球 UI"""
    
    def __init__(self, signals: Optional[FuguangSignals] = None):
        """
        初始化悬浮球
        
        Args:
            signals: 信号对象，用于与业务逻辑通信
        """
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 未安装，请运行: pip install PyQt6")
            
        super().__init__()
        
        # 信号中心
        self.signals = signals or FuguangSignals()
        self.signals.state_changed.connect(self.set_state)
        
        # 状态颜色定义
        self.state_colors = {
            BallState.IDLE: (0, 191, 255),      # 幽灵蓝
            BallState.LISTENING: (255, 69, 0),   # 赤红
            BallState.THINKING: (50, 205, 50),   # 荧光绿
            BallState.SPEAKING: (148, 0, 211),   # 紫色
            BallState.ERROR: (255, 165, 0),      # 橙色
        }
        
        self.current_state = BallState.IDLE
        self.is_awake = False  # 是否处于唤醒状态
        self.is_recording = False  # 是否正在 PTT 录音
        
        # 呼吸灯效果
        self.opacity = 200
        self.direction = -3  # 更慢的呼吸
        self.pulse_speed = 100  # 毫秒 (原50ms太快)
        
        # 动画定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(self.pulse_speed)
        
        # 双击检测
        self.click_count = 0
        self.click_timer = QTimer(self)
        self.click_timer.timeout.connect(self._handle_click)
        
        # 鼠标拖拽
        self.old_pos = None
        self._is_dragging = False   # [修复#7] 拖拽标志，防止拖拽触发点击
        self._press_pos = None      # [修复#7] 记录按下位置，用于判断拖拽距离
        
        # 初始化 UI
        self._init_ui()
        
        logger.info("🔮 [GUI] 悬浮球已初始化")

    def _init_ui(self):
        """初始化 UI 属性"""
        # 无边框、置顶、透明背景
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 大小
        self.resize(100, 100)
        
        # 初始位置（右下角）
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - 120, screen.height() - 120)

    def set_state(self, state: str):
        """设置悬浮球状态"""
        if state in self.state_colors:
            self.current_state = state
            self.update()
            logger.debug(f"🔮 [GUI] 状态变更: {state}")

    # ========================
    # 绘制
    # ========================
    
    def paintEvent(self, event):
        """绘制悬浮球"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 获取当前颜色
        base_color = self.state_colors.get(self.current_state, (0, 0, 0))
        r, g, b = base_color
        alpha = int(self.opacity)  # QColor 需要整数
        
        # 径向渐变（立体感）
        gradient = QRadialGradient(50, 50, 50)
        gradient.setColorAt(0, QColor(r, g, b, 255))
        gradient.setColorAt(0.7, QColor(r, g, b, alpha))
        gradient.setColorAt(1, QColor(r, g, b, alpha // 3))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        
        # 主圆
        painter.drawEllipse(10, 10, 80, 80)
        
        # 中心高光
        highlight = QRadialGradient(40, 40, 20)
        highlight.setColorAt(0, QColor(255, 255, 255, 100))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawEllipse(25, 25, 30, 30)
        
        # 状态文字（小字）
        if self.is_awake:
            painter.setPen(QColor(255, 255, 255, 200))
            painter.setFont(QFont("微软雅黑", 8))
            state_text = {
                BallState.IDLE: "待命",
                BallState.LISTENING: "录音中" if self.is_recording else "倒听中",
                BallState.THINKING: "思考中",
                BallState.SPEAKING: "说话中",
                BallState.ERROR: "错误",
            }.get(self.current_state, "")
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, state_text)

    # ========================
    # 动画
    # ========================
    
    def _animate(self):
        """动画更新"""
        if self.current_state == BallState.IDLE:
            # 缓慢呼吸效果
            self.opacity += self.direction
            if self.opacity >= 220 or self.opacity <= 100:
                self.direction *= -1
        elif self.current_state == BallState.THINKING:
            # 中速脉动 (思考中)
            self.opacity += self.direction * 2
            if self.opacity >= 255 or self.opacity <= 150:
                self.direction *= -1
        elif self.current_state == BallState.LISTENING:
            # 柔和脉动 (聆听中)，比思考慢
            self.opacity += self.direction
            if self.opacity >= 255 or self.opacity <= 180:
                self.direction *= -1
        elif self.current_state == BallState.SPEAKING:
            # 律动效果 (说话中)
            self.opacity += self.direction * 1.5
            if self.opacity >= 255 or self.opacity <= 160:
                self.direction *= -1
        
        self.update()

    # ========================
    # 鼠标交互
    # ========================
    
    def mousePressEvent(self, event):
        """鼠标按下 — 只记录位置，不触发点击"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()
            self._press_pos = event.globalPosition().toPoint()
            self._is_dragging = False

    def mouseMoveEvent(self, event):
        """鼠标拖拽"""
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()
            # 通知 HUD 跟随移动
            self.signals.ball_moved.emit()
            
            # [修复#7] 如果移动距离超过 5px 阈值，判定为拖拽
            if self._press_pos:
                moved = event.globalPosition().toPoint() - self._press_pos
                if abs(moved.x()) > 5 or abs(moved.y()) > 5:
                    self._is_dragging = True

    def mouseReleaseEvent(self, event):
        """鼠标释放 — 只有非拖拽时才计入点击"""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging:
                # 不是拖拽，算作一次点击
                self.click_count += 1
                if not self.click_timer.isActive():
                    self.click_timer.start(300)
            else:
                # 拖拽结束，忽略点击
                self.click_count = 0
                self.click_timer.stop()
                logger.debug("🔮 [GUI] 拖拽结束，已忽略点击")
        self.old_pos = None
        self._press_pos = None
        self._is_dragging = False

    def _handle_click(self):
        """处理点击（区分单击/双击）
        
        单击行为（点击式 PTT）：
            - 休眠中 → 唤醒 + 开始录音
            - 录音中 → 停止录音（AI 处理语音）
            - 已唤醒未录音 → 开始录音
            - 说话中 → 打断 + 开始新录音
            - 思考中 → 等待（不打断）
        双击：截图分析（不变）
        """
        self.click_timer.stop()
        
        if self.click_count >= 2:
            # 双击 -> 截图分析
            logger.info("🔮 [GUI] 双击 - 触发截图分析")
            self.signals.screenshot_request.emit()
        else:
            # 单击 -> 点击式 PTT 录音
            if self.is_recording:
                # 正在录音 → 停止录音
                logger.info("🔮 [GUI] 单击 - 停止录音")
                self.is_recording = False
                self.signals.ptt_toggle.emit(False)
            elif self.current_state == BallState.THINKING:
                # AI 思考中 → 耐心等待
                logger.info("🔮 [GUI] 单击 - AI 思考中，请稍候")
            elif self.current_state == BallState.SPEAKING:
                # AI 说话中 → 打断 + 开始新录音
                logger.info("🔮 [GUI] 单击 - 打断说话 + 开始录音")
                self.is_recording = True
                self.signals.ptt_toggle.emit(True)  # app.py 会先打断语音再录音
            else:
                # 休眠 / 已唤醒未录音 → 开始录音
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
        
        # 唤醒/休眠
        toggle_action = QAction("休眠" if self.is_awake else "唤醒", self)
        toggle_action.triggered.connect(self._toggle_wake_sleep)
        menu.addAction(toggle_action)
        
        # 截图分析
        screenshot_action = QAction("📸 截图分析", self)
        screenshot_action.triggered.connect(self.signals.screenshot_request.emit)
        menu.addAction(screenshot_action)
        
        menu.addSeparator()
        
        # 退出
        quit_action = QAction("退出扶光", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        
        menu.exec(event.globalPos())

    def _quit(self):
        """退出"""
        self.signals.quit_request.emit()
        QApplication.instance().quit()

    def _toggle_wake_sleep(self):
        """切换唤醒/休眠状态（右键菜单用）"""
        if self.is_awake:
            # 如果正在录音，先停止
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

    # [修复H-6] 正式重载拖拽事件（替代 monkey-patch）
    def dragEnterEvent(self, event):
        """拖拽进入"""
        if hasattr(self, 'drag_enter_handler') and self.drag_enter_handler:
            self.drag_enter_handler(event)
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        """文件投放"""
        if hasattr(self, 'drop_handler') and self.drop_handler:
            self.drop_handler(event)
        else:
            super().dropEvent(event)


# ========================
# 独立测试
# ========================

def main():
    """独立运行测试"""
    app = QApplication(sys.argv)
    
    signals = FuguangSignals()
    ball = FloatingBall(signals)
    
    # 测试：3秒后切换状态
    def test_states():
        import itertools
        states = itertools.cycle([
            BallState.IDLE, 
            BallState.LISTENING, 
            BallState.THINKING, 
            BallState.SPEAKING
        ])
        
        def switch():
            state = next(states)
            print(f"切换状态: {state}")
            signals.state_changed.emit(state)
        
        timer = QTimer()
        timer.timeout.connect(switch)
        timer.start(2000)
        return timer
    
    timer = test_states()
    
    ball.show()
    print("悬浮球已启动！")
    print("- 单击: 开始/停止录音")
    print("- 双击: 截图分析")
    print("- 拖拽: 移动位置")
    print("- 右键: 菜单")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
