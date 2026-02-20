"""
🎬 BilibiliSkills — B站视频搜索与播放
通过 bilibili-api-python 搜索视频/番剧，构建带时间戳的 URL 打开浏览器

工具列表：
  - search_bilibili:  搜索 B站 视频或番剧，返回链接列表
  - play_bilibili:    播放视频/番剧（支持集数 + 时间戳跳转）
"""

import asyncio
import re
import webbrowser
import logging
from typing import Optional

logger = logging.getLogger("Fuguang.Bilibili")

# bilibili-api 可选导入
try:
    from bilibili_api import search, video, bangumi
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
                "在浏览器中打开B站视频或番剧。"
                "可通过BV号打开视频，或通过关键词搜索打开。"
                "番剧支持指定集数（如episode=156打开第156集）。"
                "支持时间戳跳转（如time='13:26'跳到13分26秒）。"
                "优先搜索番剧，如果没找到番剧则搜索普通视频。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（与bvid二选一），如'凡人修仙传'"
                    },
                    "bvid": {
                        "type": "string",
                        "description": "B站视频BV号（与keyword二选一），如'BV1xx411c7mD'"
                    },
                    "episode": {
                        "type": "integer",
                        "description": "番剧集数（从1开始），如156表示第156集。仅对番剧有效"
                    },
                    "time": {
                        "type": "string",
                        "description": "跳转时间，格式 '分:秒' 或 '时:分:秒'，如 '13:26'。不填从头播放"
                    }
                },
                "required": []
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
        """搜索B站视频或番剧"""
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

        lines.append("💡 说\"打开第X个\"或用 play_bilibili(bvid='BVxxx') 播放")
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
            areas = item.get("areas", "")
            eps_count = item.get("eps", [])
            total_eps = len(eps_count) if isinstance(eps_count, list) else "?"
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

        lines.append("💡 说\"打开第X个番剧第Y集\"即可观看指定集数")
        return "\n".join(lines)

    # ------------------------------------------
    # 播放
    # ------------------------------------------
    def play_bilibili(self, keyword: str = "", bvid: str = "",
                      episode: int = 0, time: str = "") -> str:
        """
        在浏览器中打开B站视频/番剧，支持集数和时间戳跳转

        Args:
            keyword: 搜索关键词
            bvid: BV号
            episode: 番剧集数（从1开始）
            time: 跳转时间 '分:秒'
        """
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装"

        seconds = self._parse_time_to_seconds(time) if time else 0

        try:
            # ===== 1. 直接用 BV 号打开 =====
            if bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
                if seconds > 0:
                    url += f"?t={seconds}"
                webbrowser.open(url)
                time_info = f"，跳转到 {time}" if time else ""
                return f"✅ 已打开B站视频 {bvid}{time_info}"

            if not keyword:
                return "请提供搜索关键词或BV号"

            # ===== 2. 从关键词中提取集数（如果没有明确传 episode） =====
            if not episode:
                episode = self._extract_episode_number(keyword)

            # ===== 3. 先搜番剧 =====
            try:
                bangumi_result = asyncio.run(
                    search.search_by_type(keyword, search_type=search.SearchObjectType.BANGUMI, page=1)
                )
                bangumi_items = bangumi_result.get("result", [])
            except Exception:
                bangumi_items = []

            if bangumi_items:
                first = bangumi_items[0]
                title = self._clean_html(first.get("title", ""))
                season_id = first.get("season_id", "")

                if season_id and episode:
                    # 获取具体集数的 ep_id
                    return self._open_bangumi_episode(season_id, title, episode, seconds, time)
                elif season_id:
                    # 没指定集数，直接打开番剧首页
                    url = f"https://www.bilibili.com/bangumi/play/ss{season_id}"
                    if seconds > 0:
                        url += f"?t={seconds}"
                    webbrowser.open(url)
                    time_info = f"，跳转到 {time}" if time else ""
                    return f"✅ 已打开番剧「{title}」{time_info}\n链接: {url}"

            # ===== 4. 番剧没找到，搜普通视频 =====
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

    def _open_bangumi_episode(self, season_id: int, title: str,
                              episode: int, seconds: int, time_str: str) -> str:
        """
        获取番剧指定集数的 ep_id 并打开

        Args:
            season_id: 番剧 season ID
            title: 番剧标题
            episode: 集数（从1开始）
            seconds: 跳转秒数
            time_str: 原始时间字符串
        """
        try:
            b = bangumi.Bangumi(ssid=season_id)
            episodes = asyncio.run(b.get_episodes())

            if not episodes:
                return f"番剧「{title}」没有可用集数"

            total = len(episodes)

            if episode < 1 or episode > total:
                return f"番剧「{title}」共 {total} 集，没有第 {episode} 集"

            ep = episodes[episode - 1]
            ep_id = ep.get_epid()

            url = f"https://www.bilibili.com/bangumi/play/ep{ep_id}"
            if seconds > 0:
                url += f"?t={seconds}"

            webbrowser.open(url)
            time_info = f"，跳转到 {time_str}" if time_str else ""
            return f"✅ 已打开番剧「{title}」第 {episode} 集 (共{total}集){time_info}\n链接: {url}"

        except Exception as e:
            logger.error(f"🎬 [B站] 获取番剧集数失败: {e}")
            # 降级：打开番剧首页
            url = f"https://www.bilibili.com/bangumi/play/ss{season_id}"
            webbrowser.open(url)
            return f"⚠️ 获取第 {episode} 集失败({str(e)[:50]})，已打开番剧首页\n链接: {url}"

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
    def _extract_episode_number(text: str) -> int:
        """
        从文本中提取集数

        '凡人修仙传 第156集' → 156
        '凡人修仙传 156集'   → 156
        '凡人修仙传 第156话' → 156
        '凡人修仙传 ep156'   → 156
        '凡人修仙传'         → 0 (未识别)
        """
        if not text:
            return 0
        # 尝试匹配多种中文集数格式
        patterns = [
            r'第\s*(\d+)\s*[集话]',      # 第156集 / 第156话
            r'(\d+)\s*[集话]',            # 156集 / 156话
            r'[Ee][Pp]?\s*(\d+)',          # EP156 / ep156 / E156
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        return 0

    @staticmethod
    def _clean_html(text: str) -> str:
        """去除B站搜索结果中的 HTML 标签"""
        if not text:
            return ""
        return text.replace("<em class=\"keyword\">", "").replace("</em>", "")
