# browser.py - 赛博幽灵 (The Web Walker) v1.0
"""
基于 Playwright 的高级浏览器自动化模块

功能：
1. 深度访问网页（支持 JS 动态加载）
2. 网页截图（配合 GLM-4V 视觉分析）
3. 表单填写（登录、搜索等）
4. 元素点击（模拟真人操作）

使用场景：
- 静态网页 → 用 read_web_page（快）
- 动态/需要 JS 的网页 → 用 CyberGhost（强）
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("Fuguang")

# 尝试导入 Playwright
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("⚠️ Playwright 未安装，深度浏览功能将受限")


class CyberGhost:
    """扶光的赛博幽灵 - 浏览器自动化控制器"""
    
    def __init__(self, headless: bool = True, screenshot_dir: str = "data/screenshots"):
        """
        初始化赛博幽灵
        
        Args:
            headless: 无头模式（True=后台运行，False=显示浏览器窗口）
            screenshot_dir: 截图保存目录
        """
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        
        # 确保截图目录存在
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
        
        # 浏览器 User-Agent（模拟正常用户）
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        
        logger.info(f"🌐 [CyberGhost] 初始化完成 (headless={headless})")

    def browse_and_extract(self, url: str, wait_for_js: bool = True, 
                           take_screenshot: bool = False) -> str:
        """
        深度访问网页，渲染 JS，提取主要内容
        
        Args:
            url: 目标网址
            wait_for_js: 是否等待 JS 加载完成
            take_screenshot: 是否保存截图
            
        Returns:
            网页标题和正文内容
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装，请运行: pip install playwright && playwright install chromium"
        
        logger.info(f"🌐 [幽灵] 正在潜入: {url} ...")
        
        try:
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(headless=self.headless)
                
                # 创建浏览器上下文（模拟正常用户）
                context = browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                
                page = context.new_page()
                
                # 访问网页
                page.goto(url, timeout=60000)
                
                # 等待 JS 加载
                if wait_for_js:
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except PlaywrightTimeout:
                        logger.warning("⚠️ 网络空闲超时，继续处理...")
                
                # 获取标题
                title = page.title() or "无标题"
                
                # 截图（可选）
                screenshot_path = None
                if take_screenshot:
                    import time
                    screenshot_path = os.path.join(
                        self.screenshot_dir, 
                        f"web_{int(time.time())}.png"
                    )
                    page.screenshot(path=screenshot_path, full_page=False)
                    logger.info(f"📸 [幽灵] 截图已保存: {screenshot_path}")
                
                # 提取正文（使用 innerText 自动去除 HTML 标签）
                body = page.locator("body")
                content = body.inner_text() if body else ""
                
                browser.close()
                
                # 清洗内容：去除多余空行
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                cleaned_content = "\n".join(lines)
                
                # 截断防止 Token 爆炸
                max_chars = 4000
                if len(cleaned_content) > max_chars:
                    cleaned_content = cleaned_content[:max_chars] + f"\n\n... (内容过长，已截取前 {max_chars} 字符)"
                
                logger.info(f"✅ [幽灵] 抓取完成: {title} ({len(cleaned_content)} 字符)")
                
                result = f"📄 【网页标题】: {title}\n\n【网页正文】:\n{cleaned_content}"
                
                if screenshot_path:
                    result += f"\n\n📸 截图保存于: {screenshot_path}"
                
                return result
                
        except PlaywrightTimeout:
            return f"❌ 网页加载超时 (60s): {url}"
        except Exception as e:
            logger.error(f"❌ [幽灵] 访问失败: {e}")
            return f"❌ 深度访问失败: {str(e)}"

    def fill_and_submit(self, url: str, form_data: dict, 
                        submit_selector: str = None) -> str:
        """
        填写网页表单并提交
        
        Args:
            url: 目标网址
            form_data: 表单数据 {"selector": "value", ...}
            submit_selector: 提交按钮的选择器
            
        Returns:
            操作结果
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"
        
        logger.info(f"📝 [幽灵] 正在填写表单: {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()
                
                page.goto(url, timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                
                # 填写表单
                for selector, value in form_data.items():
                    page.fill(selector, value)
                    logger.debug(f"  填写: {selector} = {value[:20]}...")
                
                # 提交
                if submit_selector:
                    page.click(submit_selector)
                    page.wait_for_load_state("networkidle", timeout=10000)
                
                result_title = page.title()
                browser.close()
                
                return f"✅ 表单已提交，跳转到: {result_title}"
                
        except Exception as e:
            logger.error(f"❌ [幽灵] 表单操作失败: {e}")
            return f"❌ 表单操作失败: {str(e)}"

    def click_element(self, url: str, selector: str) -> str:
        """
        访问网页并点击指定元素
        
        Args:
            url: 目标网址
            selector: CSS 选择器或文本选择器
            
        Returns:
            操作结果
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"
        
        logger.info(f"👆 [幽灵] 正在点击: {selector} @ {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()
                
                page.goto(url, timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                
                # 尝试点击
                page.click(selector, timeout=10000)
                page.wait_for_load_state("networkidle", timeout=10000)
                
                new_title = page.title()
                new_url = page.url
                browser.close()
                
                return f"✅ 点击成功，当前页面: {new_title}\nURL: {new_url}"
                
        except Exception as e:
            logger.error(f"❌ [幽灵] 点击失败: {e}")
            return f"❌ 点击失败: {str(e)}"

    def get_page_screenshot(self, url: str) -> Optional[str]:
        """
        访问网页并截图（用于 GLM-4V 分析）
        
        Args:
            url: 目标网址
            
        Returns:
            截图路径 或 None
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1920, "height": 1080}
                )
                page = context.new_page()
                
                page.goto(url, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=15000)
                
                import time
                screenshot_path = os.path.join(
                    self.screenshot_dir, 
                    f"web_{int(time.time())}.png"
                )
                page.screenshot(path=screenshot_path)
                browser.close()
                
                logger.info(f"📸 [幽灵] 网页截图: {screenshot_path}")
                return screenshot_path
                
        except Exception as e:
            logger.error(f"❌ [幽灵] 截图失败: {e}")
            return None


# 单独测试
if __name__ == "__main__":
    ghost = CyberGhost(headless=True)
    
    # 测试：Hacker News (动态加载)
    print("测试 Hacker News:")
    result = ghost.browse_and_extract("https://news.ycombinator.com/")
    print(result[:500])
