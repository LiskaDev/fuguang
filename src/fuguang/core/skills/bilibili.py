"""
🎬 BilibiliSkills — B站视频搜索与播放
通过 bilibili-api-python 搜索视频/番剧，构建带时间戳的 URL 打开浏览器

工具列表：
  - search_bilibili: 搜索 B站 视频/番剧，返回链接列表
  - play_bilibili:   精确播放番剧/视频（支持集数+时间戳跳转）
"""

import asyncio
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
                "搜索B站(哔哩哔哩)视频。返回视频标题、UP主、播放量和链接。"
                "用于搜索任何B站内容：视频、番剧、UP主等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如'凡人修仙传'、'怪物猎人荒野'、'Python教程'"
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
                "可以通过BV号精确打开（如play_bilibili(bvid='BV1xx411c7mD', time='13:26')），"
                "也可以通过关键词搜索并打开第一个结果。"
                "支持番剧集数跳转。"
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
                        "description": "跳转时间，格式 '分:秒' 或 '时:分:秒'，如 '13:26' 或 '1:02:30'。不填则从头播放"
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

    def search_bilibili(self, keyword: str, page: int = 1) -> str:
        """
        搜索B站视频，返回格式化的结果列表

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            格式化的搜索结果文本
        """
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装，请运行: pip install bilibili-api-python"

        try:
            # bilibili-api 是异步的，需要在事件循环中运行
            result = asyncio.run(
                search.search_by_type(keyword, search_type=search.SearchObjectType.VIDEO, page=page)
            )

            videos = result.get("result", [])
            if not videos:
                return f"未找到与 '{keyword}' 相关的B站视频"

            # 格式化结果（最多显示 8 条）
            lines = [f"🔍 B站搜索「{keyword}」结果：\n"]
            for i, v in enumerate(videos[:8], 1):
                title = v.get("title", "未知标题")
                # 去除 HTML 高亮标签
                title = title.replace("<em class=\"keyword\">", "").replace("</em>", "")
                author = v.get("author", "未知UP主")
                play = v.get("play", 0)
                bvid = v.get("bvid", "")
                duration = v.get("duration", "")

                # 播放量格式化
                if isinstance(play, int) and play >= 10000:
                    play_str = f"{play/10000:.1f}万"
                else:
                    play_str = str(play)

                url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
                lines.append(f"{i}. {title}")
                lines.append(f"   UP主: {author} | 播放: {play_str} | 时长: {duration}")
                if url:
                    lines.append(f"   链接: {url}")
                lines.append("")

            lines.append("💡 可以说\"打开第X个\"或\"播放BVxxx\"来观看")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"🎬 [B站] 搜索失败: {e}")
            return f"搜索B站时出错: {str(e)[:200]}"

    def play_bilibili(self, keyword: str = "", bvid: str = "", time: str = "") -> str:
        """
        在浏览器中打开B站视频，支持时间戳跳转

        Args:
            keyword: 搜索关键词（与bvid二选一）
            bvid: BV号（与keyword二选一）
            time: 跳转时间，格式 '分:秒' 或 '时:分:秒'

        Returns:
            操作结果文本
        """
        if not BILIBILI_AVAILABLE:
            return "❌ bilibili-api 未安装，请运行: pip install bilibili-api-python"

        # 解析时间戳为秒数
        seconds = self._parse_time_to_seconds(time) if time else 0

        try:
            # 如果提供了 BV 号，直接拼 URL
            if bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
                if seconds > 0:
                    url += f"?t={seconds}"
                webbrowser.open(url)
                time_info = f"，跳转到 {time}" if time else ""
                return f"✅ 已打开B站视频 {bvid}{time_info}"

            # 否则搜索
            if not keyword:
                return "请提供搜索关键词或BV号"

            result = asyncio.run(
                search.search_by_type(keyword, search_type=search.SearchObjectType.VIDEO, page=1)
            )

            videos = result.get("result", [])
            if not videos:
                return f"未找到与 '{keyword}' 相关的B站视频"

            # 取第一个结果
            first = videos[0]
            title = first.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
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

    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> int:
        """
        将时间字符串解析为秒数

        支持格式:
          '13:26'      → 806秒
          '1:02:30'    → 3750秒
          '806'        → 806秒（纯数字直接当秒数）
        """
        if not time_str:
            return 0

        time_str = time_str.strip()

        # 纯数字 → 直接当秒数
        if time_str.isdigit():
            return int(time_str)

        parts = time_str.split(":")
        try:
            if len(parts) == 2:
                # 分:秒
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                # 时:分:秒
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass

        return 0
