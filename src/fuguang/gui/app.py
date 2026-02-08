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
import logging
import threading
from pathlib import Path

# 确保项目路径正确
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

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

    def show_message(self, text: str, duration: int = 5000):
        """显示消息"""
        self.setText(text)
        self.adjustSize()
        self.show()
        self.hide_timer.start(duration)

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
    subtitle_update = pyqtSignal(str)    # 字幕更新
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
        """工作线程主循环"""
        demo_mode = False
        
        try:
            # 延迟导入 NervousSystem（避免 pygame/torch 初始化冲突）
            self.subtitle_update.emit("正在初始化大脑...")
            from fuguang.core.nervous_system import NervousSystem
            
            # 初始化神经系统
            self.nervous_system = NervousSystem()
            self.subtitle_update.emit("扶光已就绪，点击唤醒我~")
            
            # 修改 nervous_system 的状态回调
            self._patch_nervous_system()
            
        except Exception as e:
            logger.error(f"❌ 大脑初始化失败: {e}")
            self.subtitle_update.emit(f"⚠️ 演示模式 (大脑离线)")
            demo_mode = True
            
        # 进入主循环
        while self.is_running:
            try:
                if demo_mode:
                    # 演示模式：只响应基本交互
                    self._run_demo_cycle()
                elif self.is_awake:
                    self._run_awake_cycle()
                else:
                    self.msleep(100)
                    
                # 检查待处理的任务
                if self.pending_screenshot:
                    if demo_mode:
                        self.subtitle_update.emit("📸 (演示) 截图功能需要完整大脑")
                    else:
                        self._execute_screenshot_analysis()
                    self.pending_screenshot = False
                    
                if self.pending_file:
                    if demo_mode:
                        self.subtitle_update.emit(f"📁 (演示) 收到文件: {os.path.basename(self.pending_file)}")
                    else:
                        self._execute_file_ingestion(self.pending_file)
                    self.pending_file = None
                    
            except Exception as e:
                logger.error(f"❌ 循环错误: {e}")
                self.msleep(1000)

    def _run_demo_cycle(self):
        """演示模式主循环"""
        if self.is_awake:
            self.state_changed.emit(BallState.LISTENING)
            self.msleep(2000)
            self.subtitle_update.emit("👋 演示模式：我在听（但无法处理）")
            self.msleep(3000)
        else:
            self.msleep(100)

    def _patch_nervous_system(self):
        """给 NervousSystem 打补丁，接入状态回调"""
        ns = self.nervous_system
        
        # 保存原始方法
        original_handle_ai = ns._handle_ai_response
        original_mouth_speak = ns.mouth.speak
        
        # 包装 _handle_ai_response
        def wrapped_handle_ai(user_input):
            self.state_changed.emit(BallState.THINKING)
            self.subtitle_update.emit("正在思考...")
            result = original_handle_ai(user_input)
            return result
        
        # 包装 mouth.speak
        def wrapped_speak(text, *args, **kwargs):
            self.state_changed.emit(BallState.SPEAKING)
            self.subtitle_update.emit(text[:100] + "..." if len(text) > 100 else text)
            result = original_mouth_speak(text, *args, **kwargs)
            # 说完后恢复
            if self.is_awake:
                self.state_changed.emit(BallState.LISTENING)
            else:
                self.state_changed.emit(BallState.IDLE)
            return result
        
        ns._handle_ai_response = wrapped_handle_ai
        ns.mouth.speak = wrapped_speak

    def _run_awake_cycle(self):
        """唤醒状态下的主循环（简化版）"""
        ns = self.nervous_system
        
        # 使用 PTT 模式监听
        self.state_changed.emit(BallState.LISTENING)
        self.subtitle_update.emit("我在听...")
        
        try:
            # 监听语音
            text = ns.ears.listen_once(timeout=5)
            
            if text:
                self.subtitle_update.emit(f"你说: {text}")
                ns._handle_ai_response(text)
            else:
                # 超时，回到待命
                self.msleep(100)
                
        except Exception as e:
            logger.warning(f"监听错误: {e}")
            self.msleep(500)

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
        if self.nervous_system:
            self.nervous_system.mouth.speak("我在")

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
        """更新字幕"""
        self.subtitle.show_message(text)
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
