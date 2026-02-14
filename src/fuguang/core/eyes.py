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
    
    # 常见网站名 → URL 映射（从窗口标题推断）
    _SITE_URL_MAP = {
        # 中文站
        "哔哩哔哩": "bilibili.com", "bilibili": "bilibili.com", "b站": "bilibili.com",
        "知乎": "zhihu.com", "百度": "baidu.com", "csdn": "csdn.net",
        "掘金": "juejin.cn", "简书": "jianshu.com", "微博": "weibo.com",
        "淘宝": "taobao.com", "京东": "jd.com", "豆瓣": "douban.com",
        "gitee": "gitee.com", "腾讯": "qq.com", "网易": "163.com",
        "小红书": "xiaohongshu.com", "抖音": "douyin.com",
        # 英文站
        "github": "github.com", "youtube": "youtube.com", "google": "google.com",
        "stackoverflow": "stackoverflow.com", "stack overflow": "stackoverflow.com",
        "reddit": "reddit.com", "twitter": "twitter.com", "medium": "medium.com",
        "wikipedia": "wikipedia.org", "amazon": "amazon.com",
        "notion": "notion.so", "figma": "figma.com",
        "chatgpt": "chat.openai.com", "claude": "claude.ai",
    }

    def _infer_url_from_title(self, window_title: str) -> str:
        """从窗口标题推断当前浏览的网站 URL"""
        title_lower = window_title.lower()
        for site_name, domain in self._SITE_URL_MAP.items():
            if site_name.lower() in title_lower:
                return f"https://www.{domain}"
        return ""

    def get_perception_data(self) -> dict:
        """
        获取所有感知数据（打包成字典）
        
        Returns:
            {
                "app": "VS Code - main.py",
                "clipboard": "error: xxx...",
                "app_category": "coding" | "browsing" | ...,
                "browser_hint": "用户正在浏览 bilibili.com，可用 browse_website 读取"
            }
        """
        window_title = self.get_active_window()
        category = self.get_app_category()
        clipboard = self.get_clipboard_content(limit=300)
        
        data = {
            "app": window_title,
            "clipboard": clipboard,
            "app_category": category,
        }
        
        # [修复#5] 浏览器增强感知：推断 URL 并告知 AI
        if category == "browsing":
            inferred_url = self._infer_url_from_title(window_title)
            
            # 也检查剪贴板是否有 URL
            clipboard_url = ""
            if clipboard.startswith("http://") or clipboard.startswith("https://"):
                clipboard_url = clipboard.split()[0]  # 取第一个 URL
            
            if clipboard_url:
                data["browser_hint"] = (
                    f"用户正在浏览器中查看网页，窗口标题: {window_title}。"
                    f"剪贴板中有 URL: {clipboard_url}。"
                    f"可以直接调用 browse_website(url='{clipboard_url}') 读取网页内容。"
                )
            elif inferred_url:
                data["browser_hint"] = (
                    f"用户正在浏览 {inferred_url} 相关页面，窗口标题: {window_title}。"
                    f"如果用户想了解网页内容，可以调用 browse_website 或 read_web_page 工具。"
                    f"如果需要精确 URL，可以让用户复制地址栏链接。"
                )
            else:
                data["browser_hint"] = (
                    f"用户正在使用浏览器，窗口标题: {window_title}。"
                    f"可以使用 browse_website(url) 或 read_web_page(url) 读取网页内容。"
                    f"如果不知道 URL，可以让用户复制地址栏链接，或根据标题关键词搜索。"
                )
        
        return data
    
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
