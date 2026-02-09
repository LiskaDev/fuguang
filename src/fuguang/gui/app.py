# app.py - 扶光 GUI 应用主入口 (Soul Injection v3.0)
"""
将大脑(NervousSystem)与身体(FloatingBall)融合的入口

架构:
- 主线程: PyQt6 GUI (FloatingBall)
- 工作线程: FuguangWorker (NervousSystem)
- 通信: Signal/Slot

启动方式:
    python -m fuguang.gui.app
"""

import sys
import os

# ===================================================
# 🛡️ DLL 冲突护身符 (必须在所有导入之前)
# ===================================================
# 1. 防止 OpenMP 冲突报错
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 2. 优先加载 Torch (解决 DLL 初始化顺序问题)
try:
    import torch
    print(f"✅ Torch 已加载: {torch.__version__}")
except ImportError:
    print("⚠️ Torch 未安装 (仅 UI 模式)")

# ===================================================

import logging
import threading
from pathlib import Path

# 确保项目路径正确
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# 3. 最后加载 PyQt6
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtCore import QThread, pyqtSignal, QObject, Qt, QTimer, QMimeData
from PyQt6.QtGui import QFont, QColor

from fuguang.gui.ball import FloatingBall, FuguangSignals, BallState
# NervousSystem 延迟导入，避免 pygame/torch 初始化冲突

logger = logging.getLogger("Fuguang")


class SubtitleBubble(QLabel):
    """字幕气泡 - 显示 AI 说话内容"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 样式
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(20, 20, 20, 200);
                color: white;
                border-radius: 10px;
                padding: 10px 15px;
                font-size: 14px;
            }
        """)
        self.setFont(QFont("微软雅黑", 11))
        self.setWordWrap(True)
        self.setMaximumWidth(400)
        self.setMinimumHeight(40)
        
        # 自动隐藏定时器
        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self.fade_out)
        
        self.hide()

    def show_message(self, text: str, duration: int = 8000):
        """显示消息
        
        Args:
            text: 要显示的文本
            duration: 显示时长(毫秒)，默认 8 秒，-1 表示不自动隐藏
        """
        self.setText(text)
        self.adjustSize()
        self.show()
        if duration > 0:
            self.hide_timer.start(duration)
        else:
            self.hide_timer.stop()  # 不自动隐藏

    def fade_out(self):
        """淡出隐藏"""
        self.hide_timer.stop()
        self.hide()

    def update_position(self, ball_x: int, ball_y: int):
        """根据悬浮球位置更新气泡位置"""
        # 显示在球的左边
        self.move(ball_x - self.width() - 20, ball_y + 20)


class FuguangWorker(QThread):
    """扶光工作线程 - 运行 AI 大脑"""
    
    # 发送给 UI 的信号
    state_changed = pyqtSignal(str)      # 状态变更
    subtitle_update = pyqtSignal(str)    # 字幕更新 (自动 8 秒隐藏)
    subtitle_long = pyqtSignal(str)      # 持久字幕 (不自动隐藏)
    file_ingested = pyqtSignal(str)      # 文件吞噬完成
    
    def __init__(self, signals: FuguangSignals):
        super().__init__()
        self.signals = signals
        self.nervous_system = None
        self.is_running = True
        self.is_awake = False
        self.pending_screenshot = False
        self.pending_file = None
        
        # 连接来自 UI 的信号
        self.signals.wake_up.connect(self._on_wake_up)
        self.signals.sleep.connect(self._on_sleep)
        self.signals.screenshot_request.connect(self._on_screenshot_request)
        self.signals.quit_request.connect(self._on_quit)

    def run(self):
        """工作线程主循环 - 完全复用 NervousSystem.run()"""
        demo_mode = False
        
        try:
            # 延迟导入 NervousSystem（避免 pygame/torch 初始化冲突）
            self.subtitle_update.emit("正在初始化大脑...")
            from fuguang.core.nervous_system import NervousSystem
            
            # 初始化神经系统
            self.nervous_system = NervousSystem()
            self.subtitle_update.emit("扶光已就绪！")
            
            # 注入 GUI 回调（使用原生回调机制）
            self._inject_gui_callbacks()
            
        except Exception as e:
            logger.error(f"❌ 大脑初始化失败: {e}")
            import traceback
            traceback.print_exc()
            self.subtitle_update.emit(f"⚠️ 演示模式 (大脑离线)")
            demo_mode = True
            
        if demo_mode:
            # 演示模式：只响应基本交互
            while self.is_running:
                self._run_demo_cycle()
        else:
            # 🚀 完整模式：直接调用 NervousSystem.run()
            # 这里使用 run_in_gui_mode() 因为 run() 内部有阻塞循环
            self._run_with_nervous_system()

    def _run_demo_cycle(self):
        """演示模式主循环"""
        if self.is_awake:
            self.state_changed.emit(BallState.LISTENING)
            self.msleep(2000)
            self.subtitle_update.emit("👋 演示模式：我在听（但无法处理）")
            self.msleep(3000)
        else:
            self.msleep(100)

    def _run_with_nervous_system(self):
        """完整模式：直接运行 NervousSystem.run()"""
        try:
            logger.info("🚀 完整模式启动：调用 NervousSystem.run()")
            self.nervous_system.run()
        except Exception as e:
            logger.error(f"❌ NervousSystem 崩溃: {e}")
            import traceback
            traceback.print_exc()
            self.subtitle_update.emit(f"⚠️ 系统崩溃: {str(e)[:30]}")

    def _inject_gui_callbacks(self):
        """注入 GUI 回调到 NervousSystem（使用原生回调机制）"""
        ns = self.nervous_system
        
        # 1. 状态变化回调
        def on_state_change(state: str):
            self.state_changed.emit(state)
        ns.on_state_change = on_state_change
        
        # 2. 字幕显示回调
        def on_subtitle(text: str, persistent: bool = False):
            if persistent:
                self.subtitle_long.emit(text)
            else:
                self.subtitle_update.emit(text)
        ns.on_subtitle = on_subtitle
        
        # 3. TTS 开始说话回调
        def on_speech_start(text: str):
            self.state_changed.emit(BallState.SPEAKING)
            display_text = text if len(text) <= 200 else text[:200] + "..."
            self.subtitle_long.emit(display_text)
        ns.mouth.on_speech_start = on_speech_start
        
        # 4. TTS 结束回调
        def on_speech_end():
            # TTS 结束后恢复为 IDLE
            self.state_changed.emit(BallState.IDLE)
        ns.mouth.on_speech_end = on_speech_end
        
        logger.info("🔌 GUI 回调已注入到 NervousSystem")

    def _execute_screenshot_analysis(self):
        """执行截图分析"""
        if not self.nervous_system:
            return
            
        self.state_changed.emit(BallState.THINKING)
        self.subtitle_update.emit("正在分析屏幕...")
        
        try:
            result = self.nervous_system.skills.analyze_screen_content("请描述你看到的内容")
            self.nervous_system.mouth.speak(result)
        except Exception as e:
            self.subtitle_update.emit(f"分析失败: {e}")

    def _execute_file_ingestion(self, file_path: str):
        """执行文件吞噬"""
        if not self.nervous_system:
            return
            
        self.state_changed.emit(BallState.THINKING)
        self.subtitle_update.emit(f"正在吞噬: {os.path.basename(file_path)}")
        
        try:
            result = self.nervous_system.skills.ingest_knowledge_file(file_path)
            self.file_ingested.emit(result)
            self.nervous_system.mouth.speak(f"文件已消化，你可以问我关于它的问题了")
        except Exception as e:
            self.subtitle_update.emit(f"吞噬失败: {e}")

    def _on_wake_up(self):
        """唤醒"""
        self.is_awake = True
        self.state_changed.emit(BallState.LISTENING)
        self.subtitle_update.emit("指挥官，请说~")
        # 不说话，只显示字幕，避免打断用户

    def _on_sleep(self):
        """休眠"""
        self.is_awake = False
        self.state_changed.emit(BallState.IDLE)
        self.subtitle_update.emit("休眠中...")

    def _on_screenshot_request(self):
        """截图请求"""
        self.pending_screenshot = True

    def _on_quit(self):
        """退出"""
        self.is_running = False
        self.quit()


class FuguangApp:
    """扶光 GUI 应用"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # 创建信号中心
        self.signals = FuguangSignals()
        
        # 创建 UI 组件
        self.ball = FloatingBall(self.signals)
        self.subtitle = SubtitleBubble()
        
        # 创建工作线程
        self.worker = FuguangWorker(self.signals)
        
        # 连接工作线程信号到 UI
        self.worker.state_changed.connect(self.ball.set_state)
        self.worker.subtitle_update.connect(self._on_subtitle_update)
        self.worker.subtitle_long.connect(self._on_subtitle_long)  # 持久字幕
        self.worker.file_ingested.connect(self._on_file_ingested)
        
        # 启用拖拽
        self.ball.setAcceptDrops(True)
        self.ball.dragEnterEvent = self._on_drag_enter
        self.ball.dropEvent = self._on_drop
        
        # 更新字幕位置定时器
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_subtitle_position)
        self.position_timer.start(100)

    def _on_subtitle_update(self, text: str):
        """更新字幕 (自动隐藏)"""
        if text:
            self.subtitle.show_message(text)
            self._update_subtitle_position()
        else:
            self.subtitle.hide()

    def _on_subtitle_long(self, text: str):
        """持久字幕 (不自动隐藏，用于 TTS 期间)"""
        self.subtitle.show_message(text, duration=-1)  # -1 = 不自动隐藏
        self._update_subtitle_position()

    def _on_file_ingested(self, result: str):
        """文件吞噬完成"""
        self.subtitle.show_message(result, 8000)

    def _update_subtitle_position(self):
        """更新字幕位置"""
        if self.subtitle.isVisible():
            self.subtitle.update_position(self.ball.x(), self.ball.y())

    def _on_drag_enter(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.ball.set_state(BallState.THINKING)

    def _on_drop(self, event):
        """文件投放"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            logger.info(f"📁 拖拽文件: {file_path}")
            self.worker.pending_file = file_path
        self.ball.set_state(BallState.IDLE)

    def run(self):
        """启动应用"""
        print("🔮 扶光 GUI 模式启动中...")
        
        # 显示 UI
        self.ball.show()
        
        # 启动工作线程
        self.worker.start()
        
        print("✅ 扶光已就绪！")
        print("   - 单击悬浮球: 唤醒/休眠")
        print("   - 双击: 截图分析")
        print("   - 拖拽文件: 知识吞噬")
        print("   - 右键: 菜单")
        
        # 进入事件循环
        return self.app.exec()


def main():
    """主入口"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    
    app = FuguangApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
