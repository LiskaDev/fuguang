"""
BrowserSkills — 🌐 浏览器类技能
网页搜索、阅读、深度浏览（Playwright）、视频播放
"""
import logging, webbrowser, time
import requests

from .base import PLAYWRIGHT_AVAILABLE

logger = logging.getLogger("fuguang.skills")

_BROWSER_TOOLS_SCHEMA = [
    {"type":"function","function":{"name":"search_web","description":"联网搜索实时信息。适合场景: 新闻/天气/游戏攻略/最新数据等。⚠️ 对于常识性知识，请直接用你自己的知识回答，不要调用此工具。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"搜索关键词"}},"required":["query"]}}},
    {"type":"function","function":{"name":"open_website","description":"打开常用网站首页。支持: 淘宝/京东/B站/知乎/微博/GitHub等","parameters":{"type":"object","properties":{"site_name":{"type":"string","description":"网站名称"}},"required":["site_name"]}}},
    {"type":"function","function":{"name":"open_video","description":"【自动搜索并播放视频】在B站搜索视频并自动点击播放第一个结果。支持silent=true快速模式。","parameters":{"type":"object","properties":{"keyword":{"type":"string","description":"搜索关键词"},"silent":{"type":"boolean","description":"静默模式（默认false）","default":False}},"required":["keyword"]}}},
    {"type":"function","function":{"name":"read_web_page","description":"【网页阅读器】读取并提取指定网页的文字内容。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"要读取的网页 URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"browse_website","description":"【深度浏览】使用全功能浏览器访问网页，支持 JavaScript 动态加载。比 read_web_page 更强大。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"},"take_screenshot":{"type":"boolean","description":"是否保存网页截图"}},"required":["url"]}}},
]


class BrowserSkills:
    """浏览器类技能 Mixin"""
    _BROWSER_TOOLS = _BROWSER_TOOLS_SCHEMA

    # ========================
    # 🌍 联网搜索
    # ========================
    def search_web(self, query: str) -> str:
        logger.info(f"🌍 正在搜索: {query}...")
        self.mouth.speak(f"正在帮指挥官查找 {query}...")
        try:
            url = "https://google.serper.dev/search"
            payload = {"q": query, "gl": "cn", "hl": "zh-cn", "num": 5}
            headers = {"X-API-KEY": self.config.SERPER_API_KEY, "Content-Type": "application/json"}
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code != 200:
                return f"搜索失败,状态码 {response.status_code}"
            data = response.json()
            if "knowledgeGraph" in data:
                kg = data["knowledgeGraph"]
                return f"【快速答案】\n{kg.get('title', '')}\n{kg.get('description', '')}\n"
            if "organic" not in data or not data["organic"]:
                return "未找到有效搜索结果"
            results = data["organic"][:5]
            summary = f"✅ 搜索'{query}'找到 {len(results)} 条结果:\n\n"
            for i, res in enumerate(results, 1):
                summary += f"【{i}】{res.get('title', '无标题')}\n{res.get('snippet', '无摘要')[:200]}...\n\n"
            return summary.strip()
        except Exception as e:
            logger.error(f"搜索异常: {e}")
            return f"搜索失败: {str(e)}"

    # ========================
    # 📖 网页深度阅读
    # ========================
    def read_web_page(self, url: str) -> str:
        from bs4 import BeautifulSoup
        logger.info(f"📖 正在阅读网页: {url}")
        self.mouth.speak("正在阅读网页内容...")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = response.apparent_encoding or 'utf-8'
            if response.status_code != 200:
                return f"❌ 网页访问失败，状态码: {response.status_code}"
            soup = BeautifulSoup(response.text, 'lxml')
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                tag.decompose()
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
            text = main_content.get_text(separator='\n', strip=True) if main_content else soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = '\n'.join(lines)
            max_chars = 3000
            if len(clean_text) > max_chars:
                clean_text = clean_text[:max_chars] + f"\n\n... (内容过长，已截取前 {max_chars} 字符)"
            title = soup.title.string if soup.title else "无标题"
            return f"📄 网页标题: {title}\n\n{clean_text}"
        except requests.Timeout:
            return "❌ 网页访问超时（15秒），请稍后重试。"
        except Exception as e:
            return f"❌ 网页读取失败: {str(e)}"

    # ========================
    # 🌐 网站打开
    # ========================
    def open_website(self, site_name: str) -> str:
        logger.info(f"🌐 正在打开: {site_name}")
        self.mouth.speak(f"正在为你打开 {site_name}...")
        try:
            url = self.WEBSITE_REGISTRY.get(site_name)
            if url:
                webbrowser.open(url, new=2)
                return f"✅ 已打开: {site_name}"
            return f"❌ 未知网站: {site_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"

    # ========================
    # 🌐 浏览器管理（性能优化）
    # ========================
    def _get_browser_page(self):
        if not PLAYWRIGHT_AVAILABLE:
            return None
        try:
            if self._browser and self._browser.is_connected():
                if not self._browser_page or self._browser_page.is_closed():
                    self._browser_page = self._browser.new_page()
                return self._browser_page
            logger.info("🚀 启动浏览器（首次或重连）...")
            from playwright.sync_api import sync_playwright
            if not self._playwright:
                self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=False)
            context = self._browser.new_context(
                user_agent=self.ghost.user_agent if self.ghost else "Mozilla/5.0",
                viewport={"width": 1920, "height": 1080}, locale="zh-CN")
            self._browser_page = context.new_page()
            return self._browser_page
        except Exception as e:
            logger.error(f"❌ 浏览器启动失败: {e}"); return None

    def _close_browser(self):
        try:
            if self._browser: self._browser.close()
            if self._playwright: self._playwright.stop()
            self._browser = None; self._browser_page = None; self._playwright = None
        except Exception as e:
            logger.warning(f"浏览器关闭异常: {e}")

    # ========================
    # 📺 视频搜索
    # ========================
    def open_video(self, keyword: str, silent: bool = False) -> str:
        """在B站搜索视频并自动播放第一个结果"""
        logger.info(f"📺 正在搜索视频: {keyword}")
        if not silent:
            self.mouth.speak(f"正在帮你搜索并播放 {keyword}...")
        try:
            import urllib.parse
            encoded_keyword = urllib.parse.quote(keyword)
            
            # [修复#12] 先通过 B站搜索 API 获取第一个视频的 bvid
            try:
                search_url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={encoded_keyword}&page=1&page_size=1"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.bilibili.com'
                }
                resp = requests.get(search_url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("data", {}).get("result", [])
                    if results:
                        first = results[0]
                        bvid = first.get("bvid", "")
                        title = first.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
                        if bvid:
                            video_url = f"https://www.bilibili.com/video/{bvid}"
                            webbrowser.open(video_url, new=2)
                            if not silent:
                                self.mouth.speak(f"已打开视频: {title[:30]}")
                            return f"✅ 正在播放: {title} ({video_url})"
            except Exception as e:
                logger.warning(f"⚠️ B站 API 搜索失败，回退到搜索页: {e}")
            
            # 回退：直接打开搜索页面
            url = f"https://search.bilibili.com/all?keyword={encoded_keyword}"
            webbrowser.open(url, new=2)
            if not silent:
                self.mouth.speak("已打开B站搜索页面，请选择你想看的视频~")
            return f"✅ 已在默认浏览器中打开B站搜索: {keyword}"
        except Exception as e:
            return f"❌ 视频播放失败: {str(e)}"

    # ========================
    # 🌐 赛博幽灵：深度浏览
    # ========================
    def browse_website(self, url: str, take_screenshot: bool = False) -> str:
        if not self.ghost:
            return self.read_web_page(url)
        logger.info(f"🌐 [深度浏览] AI 请求访问: {url}")
        self.mouth.speak("正在深度访问网页...")
        try:
            return self.ghost.browse_and_extract(url, take_screenshot=take_screenshot)
        except Exception as e:
            logger.error(f"❌ 深度浏览失败: {e}")
            return self.read_web_page(url)
