"""
🎬 BilibiliSkills — B站视频搜索与播放
通过 bilibili-api-python 搜索视频/番剧，构建带时间戳的 URL 打开浏览器

工具列表：
  - search_bilibili:       搜索 B站 视频或番剧，返回链接列表
  - play_bilibili:         精确播放番剧/视频（支持集数+时间戳跳转）
  - get_bilibili_subtitle: 提取视频字幕/CC 文本，用于内容分析和总结
"""

import asyncio
import webbrowser
import logging
import httpx
from typing import Optional

logger = logging.getLogger("Fuguang.Bilibili")

# bilibili-api 可选导入
try:
    from bilibili_api import search, video
    BILIBILI_AVAILABLE = True
except ImportError:
    BILIBILI_AVAILABLE = False
    logger.warning("⚠️ bilibili-api 未安装 (pip install bilibili-api-python)，B站功能不可用")

# ============================================
# 工具 Schema (OpenAI Function Calling 格式)
# ============================================

_BILIBILI_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_bilibili",
            "description": (
                "搜索B站(哔哩哔哩)视频或番剧。"
                "search_type='video' 搜普通视频(UP主投稿)；"
                "search_type='bangumi' 搜官方番剧/动漫/电视剧。"
                "返回标题、链接等信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如'凡人修仙传'、'Python教程'"
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["video", "bangumi"],
                        "description": "搜索类型：video=UP主视频(默认)，bangumi=官方番剧/动漫/电视剧",
                        "default": "video"
                    },
                    "page": {
                        "type": "integer",
                        "description": "搜索结果页码，默认第1页",
                        "default": 1
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_bilibili",
            "description": (
                "在浏览器中打开B站视频并跳转到指定时间。"
                "可通过BV号精确打开，也可通过关键词搜索并打开第一个结果。"
                "支持时间戳跳转。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（与bvid二选一），如'凡人修仙传 第156集'"
                    },
                    "bvid": {
                        "type": "string",
                        "description": "B站视频BV号（与keyword二选一），如'BV1xx411c7mD'"
                    },
                    "time": {
                        "type": "string",
                        "description": "跳转时间，格式 '分:秒' 或 '时:分:秒'，如 '13:26'。不填从头播放"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bilibili_subtitle",
            "description": (
                "提取B站视频的字幕/CC文本。可用于视频内容分析、总结、翻译等。"
                "需要提供BV号。返回字幕纯文本内容。"
                "注意：并非所有视频都有字幕，部分视频需要 AI 自动字幕已开启。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bvid": {
                        "type": "string",
                        "description": "B站视频BV号，如'BV17x411w7KC'"
                    },
                    "page": {
                        "type": "integer",
                        "description": "分P编号（从1开始），默认第1P",
                        "default": 1
                    }
                },
                "required": ["bvid"]
            }
        }
    }
]


# ============================================
# Skill Mixin
# ============================================

class BilibiliSkills:
    """B站视频搜索与播放技能 Mixin"""

    _BILIBILI_TOOLS = _BILIBILI_TOOLS_SCHEMA if BILIBILI_AVAILABLE else []

    # ------------------------------------------
    # 搜索
    # ------------------------------------------
    def search_bilibili(self, keyword: str, search_type: str = "video", page: int = 1) -> str:
        """
        搜索B站视频或番剧

        Args:
            keyword: 搜索关键词
            search_type: "video" 或 "bangumi"
            page: 页码
        """
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装，请运行: pip install bilibili-api-python"

        try:
            if search_type == "bangumi":
                return self._search_bangumi(keyword, page)
            else:
                return self._search_video(keyword, page)
        except Exception as e:
            logger.error(f"🎬 [B站] 搜索失败: {e}")
            return f"搜索B站时出错: {str(e)[:200]}"

    def _search_video(self, keyword: str, page: int = 1) -> str:
        """搜索普通视频"""
        result = asyncio.run(
            search.search_by_type(keyword, search_type=search.SearchObjectType.VIDEO, page=page)
        )

        videos = result.get("result", [])
        if not videos:
            return f"未找到与 '{keyword}' 相关的B站视频"

        lines = [f"🔍 B站视频搜索「{keyword}」：\n"]
        for i, v in enumerate(videos[:8], 1):
            title = self._clean_html(v.get("title", ""))
            author = v.get("author", "未知")
            play = v.get("play", 0)
            bvid = v.get("bvid", "")
            duration = v.get("duration", "")

            play_str = f"{play/10000:.1f}万" if isinstance(play, int) and play >= 10000 else str(play)
            url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""

            lines.append(f"{i}. {title}")
            lines.append(f"   UP主: {author} | 播放: {play_str} | 时长: {duration}")
            if url:
                lines.append(f"   BV号: {bvid} | 链接: {url}")
            lines.append("")

        lines.append("💡 说\"打开第X个\"或用 play_bilibili 播放")
        return "\n".join(lines)

    def _search_bangumi(self, keyword: str, page: int = 1) -> str:
        """搜索番剧/动漫/电视剧"""
        result = asyncio.run(
            search.search_by_type(keyword, search_type=search.SearchObjectType.BANGUMI, page=page)
        )

        items = result.get("result", [])
        if not items:
            return f"未找到与 '{keyword}' 相关的B站番剧"

        lines = [f"🎬 B站番剧搜索「{keyword}」：\n"]
        for i, item in enumerate(items[:5], 1):
            title = self._clean_html(item.get("title", ""))
            season_id = item.get("season_id", "")
            media_id = item.get("media_id", "")
            areas = item.get("areas", "")
            styles = item.get("styles", "")
            eps_count = item.get("eps", [])
            total_eps = len(eps_count) if isinstance(eps_count, list) else "?"
            cv = item.get("cv", "未知")
            desc = item.get("desc", "")[:80]

            url = f"https://www.bilibili.com/bangumi/play/ss{season_id}" if season_id else ""

            lines.append(f"{i}. 📺 {title}")
            if areas:
                lines.append(f"   地区: {areas} | 集数: {total_eps}")
            if desc:
                lines.append(f"   简介: {desc}")
            if url:
                lines.append(f"   链接: {url}")
            lines.append("")

        lines.append("💡 说\"打开第X个番剧\"即可观看")
        return "\n".join(lines)

    # ------------------------------------------
    # 播放
    # ------------------------------------------
    def play_bilibili(self, keyword: str = "", bvid: str = "", time: str = "") -> str:
        """在浏览器中打开B站视频，支持时间戳跳转"""
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装"

        seconds = self._parse_time_to_seconds(time) if time else 0

        try:
            # 直接用 BV 号打开
            if bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
                if seconds > 0:
                    url += f"?t={seconds}"
                webbrowser.open(url)
                time_info = f"，跳转到 {time}" if time else ""
                return f"✅ 已打开B站视频 {bvid}{time_info}"

            if not keyword:
                return "请提供搜索关键词或BV号"

            # ===== 智能搜索：先搜番剧，没有再搜视频 =====
            # 1. 先尝试番剧搜索
            try:
                bangumi_result = asyncio.run(
                    search.search_by_type(keyword, search_type=search.SearchObjectType.BANGUMI, page=1)
                )
                bangumi_items = bangumi_result.get("result", [])
            except Exception:
                bangumi_items = []

            if bangumi_items:
                # 找到官方番剧
                first = bangumi_items[0]
                title = self._clean_html(first.get("title", ""))
                season_id = first.get("season_id", "")
                if season_id:
                    url = f"https://www.bilibili.com/bangumi/play/ss{season_id}"
                    if seconds > 0:
                        url += f"?t={seconds}"
                    webbrowser.open(url)
                    time_info = f"，跳转到 {time}" if time else ""
                    return f"✅ 已打开番剧「{title}」{time_info}\n链接: {url}"

            # 2. 番剧没找到，搜普通视频
            result = asyncio.run(
                search.search_by_type(keyword, search_type=search.SearchObjectType.VIDEO, page=1)
            )
            videos = result.get("result", [])
            if not videos:
                return f"未找到与 '{keyword}' 相关的B站内容"

            first = videos[0]
            title = self._clean_html(first.get("title", ""))
            found_bvid = first.get("bvid", "")
            author = first.get("author", "")

            if not found_bvid:
                return f"找到了 '{title}' 但无法获取视频链接"

            url = f"https://www.bilibili.com/video/{found_bvid}"
            if seconds > 0:
                url += f"?t={seconds}"

            webbrowser.open(url)
            time_info = f"，跳转到 {time}" if time else ""
            return f"✅ 已打开「{title}」(UP主: {author}){time_info}\n链接: {url}"

        except Exception as e:
            logger.error(f"🎬 [B站] 播放失败: {e}")
            return f"打开B站视频时出错: {str(e)[:200]}"

    # ------------------------------------------
    # 字幕提取
    # ------------------------------------------
    def get_bilibili_subtitle(self, bvid: str, page: int = 1) -> str:
        """
        提取B站视频字幕文本

        Args:
            bvid: BV号
            page: 分P编号（从1开始）

        Returns:
            字幕纯文本或错误信息
        """
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装"

        try:
            v = video.Video(bvid=bvid)

            # 1. 获取视频信息（拿 cid）
            info = asyncio.run(v.get_info())
            pages = info.get("pages", [])
            title = info.get("title", "未知视频")

            if not pages:
                return f"视频 {bvid} 没有分P信息"

            page_idx = max(0, min(page - 1, len(pages) - 1))
            cid = pages[page_idx]["cid"]
            page_title = pages[page_idx].get("part", "")

            # 2. 获取字幕列表
            subtitle_info = asyncio.run(v.get_subtitle(cid=cid))
            subtitles = subtitle_info.get("subtitles", [])

            if not subtitles:
                return f"视频「{title}」没有可用字幕（可能未开启AI字幕或UP主未上传字幕）"

            # 3. 选择中文字幕（优先）
            chosen = None
            for sub in subtitles:
                lang = sub.get("lan", "")
                if "zh" in lang or "cn" in lang or "ai-zh" in lang:
                    chosen = sub
                    break
            if not chosen:
                chosen = subtitles[0]  # 没有中文就用第一个

            subtitle_url = chosen.get("subtitle_url", "")
            if not subtitle_url:
                return f"字幕URL为空"

            # 确保 URL 有协议头
            if subtitle_url.startswith("//"):
                subtitle_url = "https:" + subtitle_url

            # 4. 下载字幕 JSON
            resp = httpx.get(subtitle_url, timeout=10)
            resp.raise_for_status()
            subtitle_data = resp.json()

            # 5. 提取纯文本
            body = subtitle_data.get("body", [])
            if not body:
                return f"字幕文件为空"

            text_lines = [item.get("content", "") for item in body if item.get("content")]
            full_text = "\n".join(text_lines)

            # 6. 截断（避免太长）
            if len(full_text) > 8000:
                full_text = full_text[:8000] + "\n\n... (字幕内容过长，已截断)"

            header = f"📝 视频「{title}」"
            if page_title:
                header += f" - {page_title}"
            header += f" 的字幕内容（{chosen.get('lan_doc', '未知语言')}）：\n"
            header += f"共 {len(text_lines)} 句\n\n"

            return header + full_text

        except Exception as e:
            logger.error(f"🎬 [B站] 字幕提取失败: {e}")
            return f"提取字幕时出错: {str(e)[:200]}"

    # ------------------------------------------
    # 工具方法
    # ------------------------------------------
    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> int:
        """
        将时间字符串解析为秒数
        '13:26' → 806, '1:02:30' → 3750, '806' → 806
        """
        if not time_str:
            return 0
        time_str = time_str.strip()
        if time_str.isdigit():
            return int(time_str)
        parts = time_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
        return 0

    @staticmethod
    def _clean_html(text: str) -> str:
        """去除B站搜索结果中的 HTML 标签"""
        if not text:
            return ""
        return text.replace("<em class=\"keyword\">", "").replace("</em>", "")
