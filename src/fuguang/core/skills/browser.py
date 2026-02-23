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
    # ---- Playwright MCP 工具 ----
    {"type":"function","function":{"name":"browser_open","description":"【Playwright】后台打开网页并返回页面标题和正文文本（截取前3000字）。适合需要JS渲染的页面。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"browser_screenshot","description":"【截图工具】后台打开网页并全页截图,截图会自动作为图片发送给用户。当用户说截图/截屏/给我发XX网站的图时必须使用此工具。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"browser_click","description":"【Playwright】后台打开网页并点击指定CSS选择器的元素。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"},"selector":{"type":"string","description":"CSS 选择器（如 '#submit-btn'、'.nav-link'、'button[type=submit]'）"}},"required":["url","selector"]}}},
    {"type":"function","function":{"name":"browser_fill_form","description":"【Playwright】后台打开网页并填写表单。fields 是 {CSS选择器: 填入值} 的字典。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"},"fields":{"type":"object","description":"表单字段 {CSS选择器: 值}，如 {'#username': 'admin', '#password': '123'}"}},"required":["url","fields"]}}},
    {"type":"function","function":{"name":"browser_get_text","description":"【Playwright】后台打开网页并提取指定CSS选择器元素的文字内容。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"},"selector":{"type":"string","description":"CSS 选择器"}},"required":["url","selector"]}}},
    {"type":"function","function":{"name":"browser_run_js","description":"【Playwright】后台打开网页并执行 JavaScript 代码，返回执行结果。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"目标网页 URL"},"script":{"type":"string","description":"要执行的 JavaScript 代码"}},"required":["url","script"]}}},
]


class BrowserSkills:
    """浏览器类技能 Mixin"""
    _BROWSER_TOOLS = _BROWSER_TOOLS_SCHEMA

    # ========================
    # 🌍 联网搜索
    # ========================
    def search_web(self, query: str) -> str:
        """
        【联网搜索】通过Google Serper API获取实时搜索结果，适合新闻/天气/游戏攻略等实时信息。
        
        ✅ 适合场景：需要最新/实时信息（如"今天天气"、"最新新闻"、"游戏攻略"）
        ❌ 不适合：常识性问题（如"Python是什么"），应该用AI自己的知识回答
        
        Args:
            query: 搜索关键词
            
        Returns:
            搜索结果摘要（前5条）
        """
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
        """
        【网页阅读】提取网页正文内容（自动去除广告/导航栏/脚本），支持中文编码。
        
        功能：自动解析HTML，提取主要文本内容，最多返回3000字符
        
        Args:
            url: 完整的网页URL（如 https://example.com/article）
            
        Returns:
            网页标题和正文内容
        """
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
        """
        【快速访问】打开预定义的常用网站，支持中文别名。
        
        支持的网站：百度、GitHub、B站、网易云音乐、Steam、Epic等
        
        Args:
            site_name: 网站名称（支持中文，如"B站"、"百度"、"GitHub"）
            
        Returns:
            打开结果
        """
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
        """
        【深度浏览】使用Playwright浏览器引擎访问网页，支持JavaScript渲染和截图。
        
        比read_web_page更强大：支持动态内容、可截图、可交互
        
        Args:
            url: 完整的网页URL
            take_screenshot: 是否保存网页截图到screenshots目录
            
        Returns:
            网页内容摘要或截图路径
        """
        if not self.ghost:
            return self.read_web_page(url)
        logger.info(f"🌐 [深度浏览] AI 请求访问: {url}")
        self.mouth.speak("正在深度访问网页...")
        try:
            return self.ghost.browse_and_extract(url, take_screenshot=take_screenshot)
        except Exception as e:
            logger.error(f"❌ 深度浏览失败: {e}")
            return self.read_web_page(url)

    # ======================================================
    # 🤖 Playwright MCP — Headless 浏览器自动化工具
    # ======================================================

    def _get_headless_page(self, url: str, timeout: int = 30000):
        """
        启动 headless Playwright 浏览器并导航到指定 URL。
        使用独立的实例，不影响现有 _get_browser_page() 的 headed 浏览器。

        Args:
            url: 目标网页 URL
            timeout: 导航超时（毫秒），默认 30 秒

        Returns:
            (playwright, browser, page) 三元组，调用方需自行关闭
        """
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        page.set_default_timeout(timeout)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return pw, browser, page

    @staticmethod
    def _close_headless(pw, browser):
        """安全关闭 headless 浏览器"""
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    # ---------- 工具方法 ----------

    def browser_open(self, url: str) -> str:
        """
        【Playwright】后台打开网页，返回标题和正文文本（截取前3000字）。

        Args:
            url: 目标网页 URL

        Returns:
            页面标题 + 正文文本
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装，请运行: pip install playwright && playwright install chromium"

        logger.info(f"🤖 [browser_open] {url}")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            title = page.title() or "无标题"
            # 提取正文：移除 script/style 后取 innerText
            text = page.evaluate("""() => {
                document.querySelectorAll('script, style, nav, header, footer, aside, iframe, noscript')
                    .forEach(el => el.remove());
                return document.body ? document.body.innerText : '';
            }""")
            text = text.strip()
            max_chars = 3000
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (截取前 {max_chars} 字)"
            return f"🌐 页面标题: {title}\n\n{text}"
        except Exception as e:
            logger.error(f"❌ [browser_open] 失败: {e}")
            return f"❌ 打开网页失败: {e}"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

    def browser_screenshot(self, url: str) -> str:
        """
        【Playwright】后台打开网页并截图，保存到 temp_files/ 目录。

        Args:
            url: 目标网页 URL

        Returns:
            截图文件路径
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装，请运行: pip install playwright && playwright install chromium"

        import hashlib
        from pathlib import Path

        logger.info(f"📸 [browser_screenshot] {url}")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            # 等待页面渲染稳定
            page.wait_for_load_state("networkidle", timeout=15000)

            # 生成文件名
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            temp_dir = self.config.PROJECT_ROOT / "temp_files"
            temp_dir.mkdir(exist_ok=True)
            filepath = temp_dir / f"screenshot_{url_hash}.png"

            page.screenshot(path=str(filepath), full_page=True)
            title = page.title() or "无标题"
            logger.info(f"✅ [browser_screenshot] 已保存: {filepath}")
            # 注册文件卡片 → Web UI 自动推送下载（与 PDF/DOCX 同机制）
            self._register_file_card(str(filepath), filepath.name)
            return (
                f"📸 网页截图已保存\n"
                f"页面标题: {title}\n"
                f"截图路径: {filepath}\n"
                f"💡 可用 analyze_image_file(image_path='{filepath}') 分析截图内容"
            )
        except Exception as e:
            logger.error(f"❌ [browser_screenshot] 失败: {e}")
            return f"❌ 截图失败: {e}"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

    def browser_click(self, url: str, selector: str) -> str:
        """
        【Playwright】后台打开网页并点击指定元素。

        Args:
            url: 目标网页 URL
            selector: CSS 选择器

        Returns:
            点击结果
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"

        logger.info(f"🖱️ [browser_click] {url} -> {selector}")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            page.click(selector, timeout=10000)
            # 等待点击后页面变化
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            new_url = page.url
            title = page.title() or "无标题"
            return (
                f"✅ 已点击元素 `{selector}`\n"
                f"当前页面: {title}\n"
                f"当前 URL: {new_url}"
            )
        except Exception as e:
            logger.error(f"❌ [browser_click] 失败: {e}")
            return f"❌ 点击失败: {e}\n💡 请检查 CSS 选择器是否正确"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

    def browser_fill_form(self, url: str, fields: dict) -> str:
        """
        【Playwright】后台打开网页并填写表单。

        Args:
            url: 目标网页 URL
            fields: 表单字段 {CSS选择器: 值}

        Returns:
            填写结果
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"

        if not fields or not isinstance(fields, dict):
            return "❌ fields 参数必须是 {CSS选择器: 值} 格式的字典"

        logger.info(f"📝 [browser_fill_form] {url} ({len(fields)} 个字段)")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            filled = []
            errors = []
            for selector, value in fields.items():
                try:
                    page.fill(selector, str(value), timeout=10000)
                    filled.append(f"  ✅ `{selector}` = \"{value}\"")
                except Exception as e:
                    errors.append(f"  ❌ `{selector}`: {e}")

            lines = [f"📝 表单填写完成（{len(filled)}/{len(fields)} 成功）\n"]
            if filled:
                lines.append("成功填写:")
                lines.extend(filled)
            if errors:
                lines.append("\n填写失败:")
                lines.extend(errors)
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"❌ [browser_fill_form] 失败: {e}")
            return f"❌ 表单填写失败: {e}"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

    def browser_get_text(self, url: str, selector: str) -> str:
        """
        【Playwright】后台打开网页并提取指定元素的文字内容。

        Args:
            url: 目标网页 URL
            selector: CSS 选择器

        Returns:
            元素文字内容
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"

        logger.info(f"📋 [browser_get_text] {url} -> {selector}")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            elements = page.query_selector_all(selector)
            if not elements:
                return f"⚠️ 未找到匹配 `{selector}` 的元素"

            lines = [f"📋 找到 {len(elements)} 个匹配元素：\n"]
            for i, el in enumerate(elements[:10], 1):
                text = el.inner_text().strip()
                if len(text) > 200:
                    text = text[:200] + "..."
                lines.append(f"  {i}. {text}")

            if len(elements) > 10:
                lines.append(f"\n  ... 还有 {len(elements) - 10} 个元素未显示")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"❌ [browser_get_text] 失败: {e}")
            return f"❌ 提取文字失败: {e}"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

    def browser_run_js(self, url: str, script: str) -> str:
        """
        【Playwright】后台打开网页并执行 JavaScript。

        Args:
            url: 目标网页 URL
            script: JavaScript 代码

        Returns:
            JS 执行结果
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "❌ Playwright 未安装"

        if not script.strip():
            return "❌ JavaScript 代码不能为空"

        logger.info(f"⚡ [browser_run_js] {url}")
        pw = browser = page = None
        try:
            pw, browser, page = self._get_headless_page(url)
            result = page.evaluate(script)

            # 格式化结果
            import json as _json
            if result is None:
                result_str = "(无返回值)"
            elif isinstance(result, (dict, list)):
                result_str = _json.dumps(result, ensure_ascii=False, indent=2)
            else:
                result_str = str(result)

            # 截断保护
            if len(result_str) > 4000:
                result_str = result_str[:4000] + f"\n\n... (结果过长，已截取前 4000 字)"

            return f"⚡ JavaScript 执行结果：\n\n{result_str}"
        except Exception as e:
            logger.error(f"❌ [browser_run_js] 失败: {e}")
            return f"❌ JavaScript 执行失败: {e}"
        finally:
            if pw and browser:
                self._close_headless(pw, browser)

