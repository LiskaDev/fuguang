"""
扶光的数字之眼 (Eyes Module) - 情境感知
功能：获取当前窗口标题、读取剪贴板内容
"""
import ctypes
import logging

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

logger = logging.getLogger("Fuguang")


class Eyes:
    """
    数字之眼 - 情境感知模块
    
    用途：
    1. 获取当前活动窗口标题（知道用户在干什么）
    2. 读取剪贴板内容（用户复制的代码/文本）
    """
    
    def __init__(self, config=None):
        """
        初始化数字眼睛
        
        Args:
            config: ConfigManager 实例（可选，用于读取配置）
        """
        self.config = config
        
        # Windows API 句柄
        self.user32 = ctypes.windll.user32
        
        logger.info("👁️ 数字眼睛初始化完成")
    
    def get_active_window(self) -> str:
        """
        获取当前活动窗口的标题
        
        Returns:
            窗口标题字符串，失败时返回 "未知窗口"
        """
        try:
            hwnd = self.user32.GetForegroundWindow()
            length = self.user32.GetWindowTextLengthW(hwnd)
            
            if length == 0:
                return "桌面"
            
            buff = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buff, length + 1)
            
            window_title = buff.value
            
            # 简化标题（去掉常见后缀）
            if " - " in window_title:
                # 例如 "main.py - Visual Studio Code" -> "main.py - VS Code"
                pass  # 暂不处理，保留完整标题
            
            return window_title if window_title else "未知窗口"
            
        except Exception as e:
            logger.warning(f"获取窗口标题失败: {e}")
            return "未知窗口"
    
    def get_clipboard_content(self, limit: int = 500) -> str:
        """
        读取剪贴板内容
        
        Args:
            limit: 最大字符数限制（防止 Token 爆炸）
        
        Returns:
            剪贴板内容字符串
        """
        if not PYPERCLIP_AVAILABLE:
            return "（剪贴板功能未安装 pyperclip）"
        
        try:
            content = pyperclip.paste()
            
            if not content or not content.strip():
                return "（剪贴板为空）"
            
            # 清洗内容
            content = content.strip().replace('\r', '')
            
            # 限制长度
            if len(content) > limit:
                return content[:limit] + f"...(剩余{len(content)-limit}字已截断)"
            
            return content
            
        except Exception as e:
            logger.warning(f"读取剪贴板失败: {e}")
            return f"（读取失败）"
    
    def get_perception_data(self) -> dict:
        """
        获取所有感知数据（打包成字典）
        
        Returns:
            {
                "app": "VS Code - main.py",
                "clipboard": "error: xxx...",
            }
        """
        return {
            "app": self.get_active_window(),
            "clipboard": self.get_clipboard_content(limit=300),
        }
    
    def get_app_category(self) -> str:
        """
        根据窗口标题判断用户正在做什么类型的事
        
        Returns:
            "coding" | "browsing" | "gaming" | "meeting" | "unknown"
        """
        window = self.get_active_window().lower()
        
        # 编程相关
        coding_keywords = ["visual studio", "vscode", "pycharm", "sublime", "notepad++", "vim", ".py", ".js", ".cpp"]
        for kw in coding_keywords:
            if kw in window:
                return "coding"
        
        # 浏览器
        browser_keywords = ["chrome", "firefox", "edge", "safari", "bilibili", "youtube", "github"]
        for kw in browser_keywords:
            if kw in window:
                return "browsing"
        
        # 游戏
        gaming_keywords = ["game", "游戏", "steam", "黑神话", "原神", "英雄联盟", "valorant"]
        for kw in gaming_keywords:
            if kw in window:
                return "gaming"
        
        # 会议
        meeting_keywords = ["zoom", "teams", "腾讯会议", "钉钉", "飞书"]
        for kw in meeting_keywords:
            if kw in window:
                return "meeting"
        
        return "unknown"


# 全局单例
_eyes_instance = None


def get_eyes(config=None) -> Eyes:
    """获取 Eyes 单例"""
    global _eyes_instance
    if _eyes_instance is None:
        _eyes_instance = Eyes(config)
    return _eyes_instance


# 测试入口
if __name__ == "__main__":
    print("👁️ Eyes 模块测试")
    eyes = Eyes()
    
    print(f"当前窗口: {eyes.get_active_window()}")
    print(f"窗口类别: {eyes.get_app_category()}")
    print(f"剪贴板内容: {eyes.get_clipboard_content()[:100]}...")
    print(f"感知数据: {eyes.get_perception_data()}")
