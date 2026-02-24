# app.py - 扶光 GUI 应用主入口 (Soul Injection v4.0)
"""
将大脑(NervousSystem)与身体(FloatingBall)融合的入口

架构:
- 主线程: PyQt6 GUI (FloatingBall + HolographicHUD)
- 工作线程: FuguangWorker (NervousSystem)
- 通信: Signal/Slot

启动方式:
    python -m fuguang.gui.app
"""

import sys
import os

# ===================================================
# 🛡️ Torch 预加载 (确保 CUDA 正确初始化)
# ===================================================
# 优先加载 Torch，确保 GPU 资源最先被正确初始化
# 注：Conda 环境已彻底解决 OpenMP DLL 冲突，无需再设置 KMP_DUPLICATE_LIB_OK
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
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor

from fuguang.gui.ball import FloatingBall, FuguangSignals, BallState
from fuguang.gui.hud import HolographicHUD
# NervousSystem 延迟导入，避免 pygame/torch 初始化冲突

logger = logging.getLogger("Fuguang")


class FuguangWorker(QThread):
    """扶光工作线程 - 运行 AI 大脑"""
    
    # 发送给 UI 的信号
    state_changed = pyqtSignal(str)      # 状态变更
    subtitle_update = pyqtSignal(str)    # 字幕更新 (自动 8 秒隐藏)
    subtitle_long = pyqtSignal(str)      # 持久字幕 (不自动隐藏)
    file_ingested = pyqtSignal(str)      # 文件吞噬完成
    expression_changed = pyqtSignal(str) # [新增] AI 表情标签变更
    
    def __init__(self, signals: FuguangSignals):
        super().__init__()
        self.signals = signals
        self.nervous_system = None
        self.is_running = True
        self.is_awake = False  # [修复C-1] 演示模式下的唤醒状态
        
        # 连接来自 UI 的信号
        self.signals.wake_up.connect(self._on_wake_up)
        self.signals.sleep.connect(self._on_sleep)
        self.signals.screenshot_request.connect(self._on_screenshot_request)
        self.signals.quit_request.connect(self._on_quit)
        self.signals.ptt_toggle.connect(self._on_ptt_toggle)

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
            self.subtitle_long.emit(text)
        ns.mouth.on_speech_start = on_speech_start
        
        # 4. TTS 结束回调
        def on_speech_end():
            # 如果 GUI 录音正在进行（用户打断了语音并开始新录音），不要重置为 IDLE
            if self.nervous_system and self.nervous_system._gui_recording_active:
                self.state_changed.emit(BallState.LISTENING)
            else:
                self.state_changed.emit(BallState.IDLE)
        ns.mouth.on_speech_end = on_speech_end
        
        # 5. [新增] AI 表情标签回调 → 驱动 GUI Emoji 切换
        def on_expression_change(expression: str):
            self.expression_changed.emit(expression)
        ns.on_expression_change = on_expression_change
        
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
        """唤醒 - 通过操作队列发送给 NervousSystem"""
        self.is_awake = True  # [修复C-1] 同步演示模式状态
        if self.nervous_system:
            self.nervous_system.queue_gui_action("wake")
        else:
            # 演示模式：直接发信号
            self.state_changed.emit(BallState.LISTENING)
            self.subtitle_update.emit("指挥官，请说~")

    def _on_sleep(self):
        """休眠 - 通过操作队列发送给 NervousSystem"""
        self.is_awake = False  # [修复C-1] 同步演示模式状态
        if self.nervous_system:
            self.nervous_system.queue_gui_action("sleep")
        else:
            self.state_changed.emit(BallState.IDLE)
            self.subtitle_update.emit("休眠中...")

    def _on_screenshot_request(self):
        """截图请求 - 通过操作队列发送给 NervousSystem"""
        if self.nervous_system:
            self.nervous_system.queue_gui_action("screenshot")
        else:
            self.subtitle_update.emit("⚙️ 大脑离线，无法截图")

    def _on_ptt_toggle(self, start: bool):
        """PTT 录音切换（由悬浮球点击触发）
        
        设计：使用独立录音线程，完全绕开主循环，点击立刻生效。
        start=True: 打断任何正在播放的语音 + 启动录音线程
        start=False: 发送停止信号，录音线程自行收尾（识别+处理）
        """
        if self.nervous_system:
            if start:
                # 先打断正在播放的语音（线程安全，无副作用）
                from fuguang import voice as fuguang_voice
                fuguang_voice.stop_speaking()
                # 启动独立录音线程
                self.nervous_system.start_gui_recording()
            else:
                self.nervous_system.stop_gui_recording()
        else:
            if start:
                self.state_changed.emit(BallState.LISTENING)
                self.subtitle_update.emit("正在倾听，再次点击结束...")
            else:
                self.state_changed.emit(BallState.IDLE)
                self.subtitle_update.emit("⚙️ 大脑离线，无法处理语音")

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
        
        # 🔮 全息 HUD（替代旧版 SubtitleBubble，支持 Markdown + 代码高亮）
        self.hud = HolographicHUD(parent_ball=self.ball)
        
        # 创建工作线程
        self.worker = FuguangWorker(self.signals)
        
        # 连接工作线程信号到 UI
        self.worker.state_changed.connect(self.ball.set_state)
        self.worker.expression_changed.connect(self.ball.set_expression)  # [新增] AI 表情 → Emoji
        self.worker.subtitle_update.connect(self._on_subtitle_update)
        self.worker.subtitle_long.connect(self._on_subtitle_long)
        self.worker.file_ingested.connect(self._on_file_ingested)
        
        # [修复H-6] 通过正式方法启用拖拽（不再 monkey-patch）
        self.ball.setAcceptDrops(True)
        self.ball.drag_enter_handler = self._on_drag_enter
        self.ball.drop_handler = self._on_drop
        
        # HUD 位置跟随定时器（100ms 刷新）
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_hud_position)
        self.position_timer.start(100)
        
        # 拖拽时实时跟随（比定时器更流畅）
        self.signals.ball_moved.connect(self._update_hud_position)

    def _on_subtitle_update(self, text: str):
        """更新 HUD 短消息（自动 8 秒隐藏）"""
        if text:
            self.hud.show_message(text)
        else:
            self.hud.clear()

    def _on_subtitle_long(self, text: str):
        """显示 AI 完整回复（Markdown 渲染，不自动隐藏）"""
        if text:
            self.hud.show_response(text)
        else:
            self.hud.clear()

    def _on_file_ingested(self, result: str):
        """文件吞噬完成"""
        self.hud.show_message(result, 8000)

    def _update_hud_position(self):
        """HUD 位置跟随悬浮球"""
        self.hud.update_position()

    def _on_drag_enter(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.ball.set_state(BallState.THINKING)

    def _on_drop(self, event):
        """文件投放 - 通过操作队列发送给 NervousSystem"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            logger.info(f"📁 拖拽文件: {file_path}")
            if self.worker.nervous_system:
                self.worker.nervous_system.queue_gui_action("ingest_file", file_path=file_path)
            else:
                self.worker.subtitle_update.emit("⚙️ 大脑离线，无法处理文件")
        self.ball.set_state(BallState.IDLE)

    def run(self):
        """启动应用"""
        print("🔮 扶光 GUI 模式启动中...")
        
        # 显示 UI
        self.ball.show()
        
        # 启动工作线程
        self.worker.start()
        
        print("✅ 扶光已就绪！")
        print("   - 单击悬浮球: 开始/停止录音")
        print("   - 双击: 截图分析")
        print("   - 拖拽文件: 知识吞噬")
        print("   - 右键: 菜单（唤醒/休眠/退出）")
        
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
