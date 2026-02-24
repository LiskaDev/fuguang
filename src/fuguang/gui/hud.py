# hud.py - 扶光全息 HUD (Holographic Head-Up Display v1.0)
"""
悬浮球旁的智能气泡窗口

功能：
1. Markdown 渲染（粗体、斜体、标题、列表）
2. 代码块语法高亮（Pygments）
3. 吸附跟随悬浮球
4. 平时隐藏，说话时浮现
5. 短消息自动消失，长回复持久显示

依赖：
    pip install markdown pygments
"""

import logging
from typing import Optional

logger = logging.getLogger("Fuguang")

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QTextBrowser, QApplication,
        QGraphicsDropShadowEffect, QSizePolicy
    )
    from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPen
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

# Markdown → HTML 转换
try:
    import markdown
    from markdown.extensions.codehilite import CodeHiliteExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
    from markdown.extensions.tables import TableExtension
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logger.warning("⚠️ markdown 未安装，HUD 将以纯文本模式显示")

# 代码高亮 CSS
try:
    from pygments.formatters import HtmlFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


# ================================
# 赛博主题 CSS
# ================================
_CYBER_CSS = """
body {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #E0E0E0;
    margin: 0;
    padding: 8px 12px;
    line-height: 1.6;
    background: transparent;
}
h1, h2, h3 {
    color: #00E5FF;
    margin: 6px 0 4px 0;
    font-weight: bold;
}
h1 { font-size: 16px; }
h2 { font-size: 14px; }
h3 { font-size: 13px; }
p {
    margin: 4px 0;
}
a {
    color: #00BCD4;
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
strong, b {
    color: #FFFFFF;
}
em, i {
    color: #B0BEC5;
}
code {
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    background-color: rgba(0, 229, 255, 0.08);
    color: #00E5FF;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
}
pre {
    background-color: rgba(0, 0, 0, 0.5);
    border: 1px solid rgba(0, 229, 255, 0.2);
    border-radius: 6px;
    padding: 10px;
    overflow-x: auto;
    margin: 6px 0;
}
pre code {
    background: none;
    padding: 0;
    color: #E0E0E0;
    font-size: 12px;
}
ul, ol {
    margin: 4px 0;
    padding-left: 20px;
}
li {
    margin: 2px 0;
}
blockquote {
    border-left: 3px solid #00E5FF;
    margin: 6px 0;
    padding: 4px 10px;
    color: #90A4AE;
    background: rgba(0, 229, 255, 0.05);
}
table {
    border-collapse: collapse;
    margin: 6px 0;
    width: 100%;
}
th, td {
    border: 1px solid rgba(0, 229, 255, 0.2);
    padding: 4px 8px;
    text-align: left;
}
th {
    background: rgba(0, 229, 255, 0.1);
    color: #00E5FF;
}
hr {
    border: none;
    border-top: 1px solid rgba(0, 229, 255, 0.3);
    margin: 8px 0;
}
/* 状态消息样式 */
.status-msg {
    color: #78909C;
    font-style: italic;
    text-align: center;
    padding: 4px;
}
/* ======== 聊天记录面板 ======== */
.chat-header {
    color: #00E5FF;
    font-size: 14px;
    font-weight: bold;
    text-align: center;
    padding: 6px 0 10px 0;
    border-bottom: 1px solid rgba(0, 229, 255, 0.2);
    margin-bottom: 8px;
}
.chat-bubble {
    padding: 8px 12px;
    border-radius: 10px;
    margin: 4px 0;
    max-width: 85%;
    word-wrap: break-word;
    line-height: 1.5;
    font-size: 12.5px;
}
.chat-bubble-user {
    background: rgba(0, 229, 255, 0.15);
    border: 1px solid rgba(0, 229, 255, 0.3);
    color: #E0F7FA;
    margin-left: auto;
    text-align: right;
}
.chat-bubble-ai {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #E0E0E0;
    margin-right: auto;
}
.chat-role {
    font-size: 10px;
    font-weight: bold;
    margin-bottom: 2px;
}
.chat-role-user { color: #00E5FF; text-align: right; }
.chat-role-ai { color: #B0BEC5; }
.chat-time {
    font-size: 9px;
    color: #546E7A;
    margin-top: 2px;
}
.chat-time-right { text-align: right; }
.chat-empty {
    color: #546E7A;
    text-align: center;
    padding: 20px;
    font-style: italic;
}
"""


def _get_highlight_css() -> str:
    """获取 Pygments 代码高亮 CSS（Monokai 暗色主题）"""
    if not PYGMENTS_AVAILABLE:
        return ""
    try:
        formatter = HtmlFormatter(style="monokai", noclasses=False)
        css = formatter.get_style_defs('.codehilite')
        # 覆盖背景色为透明（我们用自己的 pre 背景）
        css += "\n.codehilite { background: transparent !important; }"
        return css
    except Exception:
        return ""


def _md_to_html(text: str) -> str:
    """将 Markdown 文本转换为 HTML"""
    if not MARKDOWN_AVAILABLE:
        # 回退：简单的纯文本转 HTML
        import html
        escaped = html.escape(text)
        return f"<p>{escaped.replace(chr(10), '<br>')}</p>"
    
    try:
        extensions = [
            FencedCodeExtension(),
            TableExtension(),
            'nl2br',  # 换行符转 <br>
        ]
        # 如果 Pygments 可用，启用代码高亮
        if PYGMENTS_AVAILABLE:
            extensions.insert(0, CodeHiliteExtension(
                linenums=False,
                css_class='codehilite',
                guess_lang=True
            ))
        
        html_content = markdown.markdown(text, extensions=extensions)
        return html_content
    except Exception as e:
        logger.warning(f"Markdown 转换失败: {e}")
        import html
        return f"<p>{html.escape(text)}</p>"


class HolographicHUD(QWidget):
    """
    扶光全息 HUD — 赛博气泡窗口
    
    Features:
    - Markdown 渲染 + 代码高亮
    - 吸附跟随悬浮球
    - 自动显隐 + 淡入淡出
    - 赛博朋克主题
    """
    
    # 布局偏好
    MARGIN = 15           # 与悬浮球的间距
    MAX_WIDTH = 480       # 最大宽度（加宽以容纳表格）
    MIN_WIDTH = 200       # 最小宽度
    MAX_HEIGHT = 700      # 最大高度（超出滚动）
    
    def __init__(self, parent_ball=None):
        if not PYQT_AVAILABLE:
            raise ImportError("PyQt6 未安装")
        super().__init__()
        
        self.parent_ball = parent_ball
        self._current_text = ""
        
        self._init_ui()
        self._init_animations()
        self.hide()
        
        logger.info("🔮 [HUD] 全息投影已初始化")
    
    def _init_ui(self):
        """初始化 UI"""
        # 窗口属性：无边框、置顶、透明、不聚焦
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # 大小约束
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.setMaximumHeight(self.MAX_HEIGHT)
        
        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        
        # QTextBrowser - 支持 HTML 渲染
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont("Microsoft YaHei", 11))
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 构建完整 CSS（赛博主题 + Pygments 高亮）
        full_css = _CYBER_CSS + "\n" + _get_highlight_css()
        
        # 设置 QTextBrowser 样式
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: rgba(10, 15, 20, 220);
                border: 1px solid rgba(0, 229, 255, 0.3);
                border-radius: 10px;
                padding: 2px;
                selection-background-color: rgba(0, 229, 255, 0.3);
                selection-color: white;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.2);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 229, 255, 0.4);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # 保存 CSS 供后续使用
        self._full_css = full_css
        
        layout.addWidget(self.browser)
        
        # 投影阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 229, 255, 60))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        
        # 自动隐藏定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._auto_hide)
    
    def _init_animations(self):
        """初始化动画（留空，后续可加淡入淡出）"""
        # 淡入淡出可以用 QPropertyAnimation + QGraphicsOpacityEffect
        # 但 WA_TranslucentBackground 与 opacity effect 有兼容性问题
        # 暂时用 show/hide，后续可升级
        pass
    
    # ========================
    # 公开 API
    # ========================
    
    def show_message(self, text: str, duration: int = 8000):
        """
        显示短消息（状态提示等），自动消失
        
        Args:
            text: 纯文本消息
            duration: 显示时长(ms)，8000 = 8秒，-1 = 不自动隐藏
        """
        if not text:
            self._auto_hide()
            return
        
        self._current_text = text
        
        # 短消息用居中斜体样式
        html = f'<div class="status-msg">{text}</div>'
        self._set_html(html)
        self._show_at_ball()
        
        if duration > 0:
            self._hide_timer.start(duration)
        else:
            self._hide_timer.stop()
    
    def show_response(self, text: str, duration: int = -1):
        """
        显示 AI 回复（支持 Markdown 渲染）

        Args:
            text: Markdown/纯文本
            duration: 显示时长(ms)，-1 = 不自动隐藏（TTS结束后由外部关闭）
        """
        if not text:
            self._auto_hide()
            return

        # [安全] 限制文本长度，防止极长内容导致渲染卡顿
        MAX_CHARS = 10000
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + f"\n\n... (内容过长，已截取前 {MAX_CHARS} 字符)"
            logger.warning(f"⚠️ HUD文本被截断: 原长度超过 {MAX_CHARS} 字符")

        self._current_text = text

        # Markdown → HTML
        html = _md_to_html(text)
        self._set_html(html)
        self._show_at_ball()

        if duration > 0:
            self._hide_timer.start(duration)
        else:
            self._hide_timer.stop()

    def show_chat_history(self, messages: list):
        """
        显示聊天记录回看面板

        Args:
            messages: [{role: 'user'|'assistant', content: str, created_at: float}, ...]
        """
        if not messages:
            html = '<div class="chat-empty">暂无聊天记录</div>'
            self._set_html(html)
            self._show_at_ball()
            self._hide_timer.stop()
            return

        import datetime
        parts = ['<div class="chat-header">📜 聊天记录</div>']

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            ts = msg.get('created_at', 0)

            # 格式化时间
            try:
                time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
            except Exception:
                time_str = ''

            if role == 'user':
                parts.append(f'''
                <div style="display:flex; flex-direction:column; align-items:flex-end;">
                    <div class="chat-role chat-role-user">👤 指挥官</div>
                    <div class="chat-bubble chat-bubble-user">{self._escape(content)}</div>
                    <div class="chat-time chat-time-right">{time_str}</div>
                </div>''')
            else:
                # AI 回复支持 Markdown
                ai_html = _md_to_html(content)
                parts.append(f'''
                <div style="display:flex; flex-direction:column; align-items:flex-start;">
                    <div class="chat-role chat-role-ai">🤖 扶光</div>
                    <div class="chat-bubble chat-bubble-ai">{ai_html}</div>
                    <div class="chat-time">{time_str}</div>
                </div>''')

        html = '\n'.join(parts)
        self._set_html(html)
        self._show_at_ball()
        self._hide_timer.stop()  # 聊天记录不自动隐藏

        # 滚动到底部（显示最新消息）
        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @staticmethod
    def _escape(text: str) -> str:
        """HTML 转义"""
        import html as _html
        return _html.escape(text).replace('\n', '<br>')
    
    def update_position(self):
        """根据悬浮球位置更新 HUD 位置（吸附逻辑）"""
        if not self.parent_ball or not self.isVisible():
            return
        
        ball = self.parent_ball
        ball_x = ball.x()
        ball_y = ball.y()
        ball_w = ball.width()
        
        screen = QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()
        
        hud_w = self.width()
        hud_h = self.height()
        
        # 策略：优先显示在球的左边（因为球通常在右下角）
        x = ball_x - hud_w - self.MARGIN
        
        # 如果左边放不下，放右边
        if x < screen_geo.x():
            x = ball_x + ball_w + self.MARGIN
        
        # 如果右边也放不下，放左边但紧贴屏幕边缘
        if x + hud_w > screen_geo.x() + screen_geo.width():
            x = screen_geo.x() + 10
        
        # 垂直：与球顶部对齐，但不超出屏幕
        y = ball_y
        if y + hud_h > screen_geo.y() + screen_geo.height():
            y = screen_geo.y() + screen_geo.height() - hud_h - 10
        if y < screen_geo.y():
            y = screen_geo.y() + 10
        
        self.move(x, y)
    
    def clear(self):
        """清空并隐藏 HUD"""
        self._hide_timer.stop()
        self._current_text = ""
        self.hide()
    
    # ========================
    # 内部方法
    # ========================
    
    def _set_html(self, body_html: str):
        """设置完整的 HTML 文档到 QTextBrowser"""
        full_html = f"""
        <!DOCTYPE html>
        <html><head><style>{self._full_css}</style></head>
        <body>{body_html}</body></html>
        """
        self.browser.setHtml(full_html)
        
        # 自适应高度，超过 MAX_HEIGHT 时允许滚动
        doc = self.browser.document()
        doc.setTextWidth(self.MAX_WIDTH - 30)  # 减去内边距
        ideal_height = int(doc.size().height()) + 30  # 加上容器 padding
        height = min(ideal_height, self.MAX_HEIGHT)
        height = max(height, 60)  # 最小高度
        
        # 固定宽度，动态高度（超出 MAX_HEIGHT 时依赖滚动条）
        self.setFixedWidth(self.MAX_WIDTH)
        self.setFixedHeight(height)
        
        # 超出时显示滚动条，否则隐藏
        if ideal_height > self.MAX_HEIGHT:
            self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.update()
    
    def _show_at_ball(self):
        """在球旁边显示"""
        self.show()
        self.update_position()
        self.raise_()  # 确保在最前
    
    def _auto_hide(self):
        """自动隐藏"""
        self._hide_timer.stop()
        self.hide()
    
    def paintEvent(self, event):
        """绘制圆角半透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 圆角矩形路径
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        
        # 半透明黑色背景
        painter.fillPath(path, QBrush(QColor(10, 15, 20, 220)))
        
        # 赛博青描边
        pen = QPen(QColor(0, 229, 255, 50))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)
    
    def mousePressEvent(self, event):
        """点击 HUD 气泡可以关闭它"""
        if event.button() == Qt.MouseButton.RightButton:
            self.clear()
