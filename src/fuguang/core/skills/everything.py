"""
🔍 EverythingSkills — Everything 本地文件搜索
通过 Everything HTTP API 进行极速文件搜索、按扩展名筛选、打开文件所在位置

工具列表：
  - search_files:        搜索文件/文件夹
  - search_files_by_ext: 按扩展名搜索
  - open_file_location:  在资源管理器打开文件所在文件夹

依赖：Everything 已安装并开启 HTTP 服务器（工具 → 选项 → HTTP服务器）
"""

import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger("Fuguang.Everything")

# httpx 可选导入（用于 HTTP 请求）
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("⚠️ httpx 未安装 (pip install httpx)，Everything 搜索不可用")

# ============================================
# 工具 Schema (OpenAI Function Calling 格式)
# ============================================

_EVERYTHING_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "使用 Everything 极速搜索本地文件和文件夹。"
                "当用户说「帮我找一下XX文件」「搜索叫XX的文件」「电脑上有没有XX」等时使用。"
                "支持 Everything 高级语法：通配符 *、路径筛选、正则等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（支持 Everything 语法，如 *.py、path:C:\\Projects 等）"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回数量，默认 20"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files_by_ext",
            "description": (
                "按文件扩展名搜索本地文件。"
                "当用户说「找所有blend文件」「有哪些unity场景文件」「列出所有py脚本」等时使用。"
                "可附加关键词缩小范围，如搜索名称包含'test'的py文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ext": {
                        "type": "string",
                        "description": "文件扩展名（不带点号），如 blend、unity、py、docx"
                    },
                    "query": {
                        "type": "string",
                        "description": "附加关键词（可选），在指定扩展名的文件中进一步筛选"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回数量，默认 20"
                    }
                },
                "required": ["ext"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_file_location",
            "description": (
                "在 Windows 资源管理器中打开文件所在文件夹并选中该文件。"
                "当用户说「打开这个文件的位置」「在文件夹里找到它」等时使用。"
                "通常配合 search_files 的结果使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "文件的完整路径"
                    }
                },
                "required": ["filepath"]
            }
        }
    }
]


# ============================================
# Skill Mixin
# ============================================

class EverythingSkills:
    """Everything 本地文件搜索技能 Mixin"""

    _EVERYTHING_TOOLS = _EVERYTHING_TOOLS_SCHEMA if HTTPX_AVAILABLE else []

    # ------------------------------------------
    # 初始化 & 启动检测
    # ------------------------------------------
    def _init_everything(self):
        """启动时检查 Everything HTTP 服务连通性"""
        if not HTTPX_AVAILABLE:
            logger.info("⚠️ [Everything] httpx 未安装，文件搜索功能已跳过")
            return

        port = getattr(self.config, 'EVERYTHING_PORT', 80)
        logger.info(f"🔌 [Everything] 正在连接 localhost:{port}...")
        try:
            with httpx.Client(timeout=5) as client:
                # 用极简查询测试连通性
                resp = client.get(
                    f"http://localhost:{port}/",
                    params={"s": "", "json": 1, "count": 0}
                )
                resp.raise_for_status()
                tool_count = len(self._EVERYTHING_TOOLS)
                logger.info(f"✅ [Everything] 已就绪（端口 {port}），{tool_count} 个工具已注册")
        except httpx.ConnectError:
            logger.warning(
                f"❌ [Everything] 无法连接 localhost:{port}\n"
                f"   请确认：1) Everything 已启动  2) 工具 → 选项 → HTTP服务器 → 已启用\n"
                f"   工具已注册，启动 Everything HTTP 后即可使用"
            )
        except httpx.RequestError as e:
            logger.warning(f"⚠️ [Everything] 连接异常: {e}，工具已注册但当前不可用")
        except Exception as e:
            logger.warning(f"⚠️ [Everything] 检测异常: {e}")

    # ------------------------------------------
    # 内部：HTTP 请求
    # ------------------------------------------
    def _everything_request(self, query: str, max_results: int = 20) -> Optional[dict]:
        """
        调用 Everything HTTP API

        Returns:
            成功返回 JSON dict，失败返回 None
        """
        port = getattr(self.config, 'EVERYTHING_PORT', 80)
        url = f"http://localhost:{port}/"
        params = {
            "s": query,
            "json": 1,
            "count": max_results,
            "path_column": 1,
            "size_column": 1,
            "date_modified_column": 1,
        }

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            logger.error(f"❌ [Everything] 无法连接 localhost:{port}，请确认 Everything 已启动且 HTTP 服务已开启")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ [Everything] HTTP {e.response.status_code}: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"❌ [Everything] 请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ [Everything] 解析响应失败: {e}")
            return None

    def _check_everything_ready(self) -> Optional[str]:
        """检查 Everything 功能是否可用，返回错误信息或 None"""
        if not HTTPX_AVAILABLE:
            return "❌ httpx 未安装，请运行: pip install httpx"
        return None

    @staticmethod
    def _format_size(size_bytes) -> str:
        """格式化文件大小"""
        try:
            size = int(size_bytes)
        except (TypeError, ValueError):
            return "未知"
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    # ------------------------------------------
    # 工具方法
    # ------------------------------------------

    def search_files(self, query: str, max_results: int = 20) -> str:
        """
        使用 Everything 搜索本地文件和文件夹。

        Args:
            query: 搜索关键词
            max_results: 最大返回数量

        Returns:
            搜索结果
        """
        err = self._check_everything_ready()
        if err:
            return err

        if not query.strip():
            return "❌ 请输入搜索关键词"

        max_results = max(1, min(50, max_results))
        data = self._everything_request(query, max_results)
        if data is None:
            port = getattr(self.config, 'EVERYTHING_PORT', 80)
            return (
                f"❌ Everything 搜索失败\n"
                f"请确认：\n"
                f"  1. Everything 软件已启动\n"
                f"  2. HTTP 服务已开启（工具 → 选项 → HTTP服务器）\n"
                f"  3. 端口为 {port}（当前配置）"
            )

        results = data.get("results", [])
        total = data.get("totalResults", 0)

        if not results:
            return f"📂 未找到匹配「{query}」的文件"

        lines = [f"🔍 搜索「{query}」找到 {total} 个结果"]
        if total > max_results:
            lines[0] += f"（显示前 {max_results} 个）"
        lines.append("")

        for i, item in enumerate(results, 1):
            name = item.get("name", "未知")
            path = item.get("path", "")
            size = item.get("size", 0)
            item_type = item.get("type", "file")

            full_path = f"{path}\\{name}" if path else name

            if item_type == "folder":
                lines.append(f"  {i}. 📁 {name}")
                lines.append(f"     路径: {full_path}")
            else:
                size_str = self._format_size(size)
                lines.append(f"  {i}. 📄 {name} ({size_str})")
                lines.append(f"     路径: {full_path}")
            lines.append("")

        lines.append("💡 用 open_file_location(filepath='完整路径') 在资源管理器中打开")
        return "\n".join(lines)

    def search_files_by_ext(self, ext: str, query: str = "",
                            max_results: int = 20) -> str:
        """
        按扩展名搜索本地文件。

        Args:
            ext: 文件扩展名（不带点号）
            query: 附加关键词
            max_results: 最大返回数量

        Returns:
            搜索结果
        """
        err = self._check_everything_ready()
        if err:
            return err

        ext = ext.strip().lstrip(".")
        if not ext:
            return "❌ 请指定文件扩展名（如 py、blend、docx）"

        # 构建 Everything 搜索语法：ext:py keyword
        search_query = f"ext:{ext}"
        if query.strip():
            search_query += f" {query.strip()}"

        max_results = max(1, min(50, max_results))
        data = self._everything_request(search_query, max_results)
        if data is None:
            port = getattr(self.config, 'EVERYTHING_PORT', 80)
            return (
                f"❌ Everything 搜索失败\n"
                f"请确认 Everything 已启动，HTTP 端口 {port}"
            )

        results = data.get("results", [])
        total = data.get("totalResults", 0)

        keyword_info = f"（关键词: {query}）" if query.strip() else ""
        if not results:
            return f"📂 未找到 .{ext} 文件{keyword_info}"

        lines = [f"🔍 搜索 .{ext} 文件{keyword_info}，找到 {total} 个"]
        if total > max_results:
            lines[0] += f"（显示前 {max_results} 个）"
        lines.append("")

        for i, item in enumerate(results, 1):
            name = item.get("name", "未知")
            path = item.get("path", "")
            size = item.get("size", 0)
            size_str = self._format_size(size)
            full_path = f"{path}\\{name}" if path else name

            lines.append(f"  {i}. 📄 {name} ({size_str})")
            lines.append(f"     路径: {full_path}")
            lines.append("")

        lines.append("💡 用 open_file_location(filepath='完整路径') 在资源管理器中打开")
        return "\n".join(lines)

    def open_file_location(self, filepath: str) -> str:
        """
        在 Windows 资源管理器中打开文件所在文件夹并选中该文件。

        Args:
            filepath: 文件的完整路径

        Returns:
            操作结果
        """
        if not filepath.strip():
            return "❌ 请提供文件路径"

        filepath = filepath.strip()

        if os.path.exists(filepath):
            try:
                subprocess.Popen(f'explorer /select,"{filepath}"')
                return f"✅ 已在资源管理器中打开并选中：\n{filepath}"
            except Exception as e:
                return f"❌ 打开资源管理器失败: {e}"
        else:
            # 文件不存在时尝试打开父目录
            parent = os.path.dirname(filepath)
            if os.path.exists(parent):
                try:
                    subprocess.Popen(f'explorer "{parent}"')
                    return f"⚠️ 文件不存在，已打开所在目录：\n{parent}"
                except Exception as e:
                    return f"❌ 打开资源管理器失败: {e}"
            else:
                return f"❌ 路径不存在: {filepath}"
