"""
🎨 FigmaSkills — Figma 设计文件查看与协作
通过 Figma REST API 获取文件结构、导出图片、读写评论

工具列表：
  - get_figma_file:      获取 Figma 文件的完整节点结构
  - get_figma_node:      获取指定节点详情
  - get_figma_images:    导出指定节点为图片 URL
  - list_figma_comments: 读取文件评论
  - post_figma_comment:  发表评论
"""

import json
import logging
from typing import List, Optional

logger = logging.getLogger("Fuguang.Figma")

# httpx 可选导入
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("⚠️ httpx 未安装 (pip install httpx)，Figma 功能不可用")

FIGMA_API_BASE = "https://api.figma.com/v1"

# ============================================
# 工具 Schema (OpenAI Function Calling 格式)
# ============================================

_FIGMA_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_figma_file",
            "description": (
                "获取 Figma 文件的节点结构。"
                "file_key 是 Figma 文件 URL 中 figma.com/file/XXXXX/ 里那串字符。"
                "当用户说「看看这个Figma文件」「获取Figma结构」等时使用。"
                "返回文件名、页面和顶层节点信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": "Figma 文件 Key（URL 中 /file/XXXXX/ 部分）"
                    }
                },
                "required": ["file_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_figma_node",
            "description": (
                "获取 Figma 文件中指定节点的详细信息。"
                "需要先用 get_figma_file 获取节点 ID。"
                "当用户说「看看这个组件的详情」「这个节点的属性」等时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": "Figma 文件 Key"
                    },
                    "node_id": {
                        "type": "string",
                        "description": "节点 ID（格式如 '1:2'）"
                    }
                },
                "required": ["file_key", "node_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_figma_images",
            "description": (
                "将 Figma 文件中指定节点导出为图片 URL。"
                "支持 png、jpg、svg、pdf 格式。"
                "当用户说「导出这个组件」「把设计稿导出成图片」等时使用。"
                "返回每个节点对应的图片下载链接。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": "Figma 文件 Key"
                    },
                    "node_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要导出的节点 ID 列表（格式如 ['1:2', '3:4']）"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["png", "jpg", "svg", "pdf"],
                        "description": "导出格式，默认 png"
                    },
                    "scale": {
                        "type": "number",
                        "description": "导出缩放倍数（0.01-4），默认 2"
                    }
                },
                "required": ["file_key", "node_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_figma_comments",
            "description": (
                "读取 Figma 文件中的所有评论。"
                "当用户说「看看设计稿的评论」「Figma上有什么反馈」等时使用。"
                "返回评论者、内容、时间等信息。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": "Figma 文件 Key"
                    }
                },
                "required": ["file_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "post_figma_comment",
            "description": (
                "在 Figma 文件中发表评论。"
                "可以指定评论在画布上的坐标位置。"
                "当用户说「在Figma上留个评论」「给设计稿加个备注」等时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": "Figma 文件 Key"
                    },
                    "message": {
                        "type": "string",
                        "description": "评论内容"
                    },
                    "x": {
                        "type": "number",
                        "description": "评论在画布上的 X 坐标（可选，默认 0）"
                    },
                    "y": {
                        "type": "number",
                        "description": "评论在画布上的 Y 坐标（可选，默认 0）"
                    }
                },
                "required": ["file_key", "message"]
            }
        }
    }
]


# ============================================
# Skill Mixin
# ============================================

class FigmaSkills:
    """Figma 设计文件查看与协作技能 Mixin"""

    _FIGMA_TOOLS = _FIGMA_TOOLS_SCHEMA if HTTPX_AVAILABLE else []

    # ------------------------------------------
    # 初始化 & 启动检测
    # ------------------------------------------
    def _init_figma(self):
        """启动时检查 Figma API 连通性"""
        if not HTTPX_AVAILABLE:
            logger.info("⚠️ [Figma] httpx 未安装，Figma 功能已跳过")
            return

        api_key = getattr(self.config, 'FIGMA_API_KEY', '')
        if not api_key:
            logger.info("⚠️ [Figma] 未配置 FIGMA_API_KEY，Figma 功能已跳过")
            return

        # 尝试调一个轻量接口验证 Key 有效性
        logger.info("🔌 [Figma] 正在验证 API Key...")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{FIGMA_API_BASE}/me",
                    headers={"X-Figma-Token": api_key}
                )
                resp.raise_for_status()
                user_info = resp.json()
                handle = user_info.get("handle", "未知用户")
                tool_count = len(self._FIGMA_TOOLS)
                logger.info(f"✅ [Figma] 已就绪（用户: {handle}），{tool_count} 个工具已注册")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("❌ [Figma] API Key 无效或已过期，Figma 功能不可用")
            else:
                logger.warning(f"⚠️ [Figma] 验证失败 (HTTP {e.response.status_code})，工具已注册但可能不可用")
        except httpx.RequestError as e:
            logger.warning(f"⚠️ [Figma] 网络不可达 ({e})，工具已注册但可能不可用")
        except Exception as e:
            logger.warning(f"⚠️ [Figma] 验证异常: {e}")

    # ------------------------------------------
    # 内部：HTTP 请求
    # ------------------------------------------
    def _figma_request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        """
        发起 Figma API 请求

        Returns:
            成功返回 JSON dict，失败返回 None（错误已记日志）
        """
        api_key = getattr(self.config, 'FIGMA_API_KEY', '')
        if not api_key:
            return None

        url = f"{FIGMA_API_BASE}{path}"
        headers = {"X-Figma-Token": api_key}

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.request(method, url, headers=headers, **kwargs)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                logger.error("❌ [Figma] API Key 无权限或已过期")
            elif status == 404:
                logger.error(f"❌ [Figma] 文件或节点不存在: {path}")
            else:
                logger.error(f"❌ [Figma] HTTP {status}: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"❌ [Figma] 网络请求失败: {e}")
            return None

    def _check_figma_ready(self) -> Optional[str]:
        """检查 Figma 功能是否可用，返回错误信息或 None"""
        if not HTTPX_AVAILABLE:
            return "❌ httpx 未安装，请运行: pip install httpx"
        api_key = getattr(self.config, 'FIGMA_API_KEY', '')
        if not api_key:
            return "❌ Figma API Key 未配置（需要在 .env 中设置 FIGMA_API_KEY）"
        return None

    @staticmethod
    def _truncate(text: str, max_len: int = 4000) -> str:
        """截断保护，防止 token 爆炸"""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"\n\n... (内容过长，已截取前 {max_len} 字)"

    # ------------------------------------------
    # 工具方法
    # ------------------------------------------

    def get_figma_file(self, file_key: str) -> str:
        """
        获取 Figma 文件的节点结构。

        Args:
            file_key: Figma 文件 Key（URL 中 /file/XXXXX/ 部分）

        Returns:
            文件结构信息
        """
        err = self._check_figma_ready()
        if err:
            return err

        data = self._figma_request("GET", f"/files/{file_key}?depth=2")
        if not data:
            return f"❌ 获取 Figma 文件失败（file_key: {file_key}），请检查 Key 是否正确"

        name = data.get("name", "未知")
        last_modified = data.get("lastModified", "未知")
        document = data.get("document", {})
        children = document.get("children", [])

        lines = [
            f"🎨 Figma 文件: {name}",
            f"最后修改: {last_modified}",
            f"页面数量: {len(children)}",
            "",
        ]

        for i, page in enumerate(children, 1):
            page_name = page.get("name", "未命名")
            page_id = page.get("id", "?")
            page_children = page.get("children", [])
            lines.append(f"📄 {i}. {page_name} (ID: {page_id}, {len(page_children)} 个子节点)")

            for j, node in enumerate(page_children[:10], 1):
                node_name = node.get("name", "未命名")
                node_id = node.get("id", "?")
                node_type = node.get("type", "未知")
                lines.append(f"   {j}. [{node_type}] {node_name} (ID: {node_id})")

            if len(page_children) > 10:
                lines.append(f"   ... 还有 {len(page_children) - 10} 个节点")
            lines.append("")

        lines.append("💡 用 get_figma_node(file_key, node_id) 查看节点详情")
        lines.append("💡 用 get_figma_images(file_key, node_ids) 导出节点为图片")

        return self._truncate("\n".join(lines))

    def get_figma_node(self, file_key: str, node_id: str) -> str:
        """
        获取 Figma 文件中指定节点的详细信息。

        Args:
            file_key: Figma 文件 Key
            node_id: 节点 ID（格式如 '1:2'）

        Returns:
            节点详情
        """
        err = self._check_figma_ready()
        if err:
            return err

        data = self._figma_request("GET", f"/files/{file_key}/nodes?ids={node_id}")
        if not data:
            return f"❌ 获取节点失败（file_key: {file_key}, node_id: {node_id}）"

        nodes = data.get("nodes", {})
        node_data = nodes.get(node_id, {})
        doc = node_data.get("document", {})

        if not doc:
            return f"❌ 节点 {node_id} 不存在或无数据"

        name = doc.get("name", "未命名")
        node_type = doc.get("type", "未知")
        visible = doc.get("visible", True)

        lines = [
            f"🔍 节点详情: {name}",
            f"类型: {node_type}",
            f"ID: {node_id}",
            f"可见: {'是' if visible else '否'}",
        ]

        # 尺寸信息
        bbox = doc.get("absoluteBoundingBox")
        if bbox:
            lines.append(f"位置: ({bbox.get('x', 0):.0f}, {bbox.get('y', 0):.0f})")
            lines.append(f"尺寸: {bbox.get('width', 0):.0f} × {bbox.get('height', 0):.0f}")

        # 子节点
        children = doc.get("children", [])
        if children:
            lines.append(f"\n子节点 ({len(children)} 个):")
            for i, child in enumerate(children[:15], 1):
                c_name = child.get("name", "未命名")
                c_id = child.get("id", "?")
                c_type = child.get("type", "未知")
                lines.append(f"  {i}. [{c_type}] {c_name} (ID: {c_id})")
            if len(children) > 15:
                lines.append(f"  ... 还有 {len(children) - 15} 个子节点")

        # 样式信息
        fills = doc.get("fills", [])
        if fills:
            lines.append(f"\n🎨 填充: {len(fills)} 个")
            for fill in fills[:3]:
                fill_type = fill.get("type", "SOLID")
                color = fill.get("color", {})
                if color:
                    r = int(color.get("r", 0) * 255)
                    g = int(color.get("g", 0) * 255)
                    b = int(color.get("b", 0) * 255)
                    lines.append(f"  {fill_type}: RGB({r}, {g}, {b})")

        return self._truncate("\n".join(lines))

    def get_figma_images(self, file_key: str, node_ids: List[str],
                         format: str = "png", scale: float = 2) -> str:
        """
        将 Figma 文件中指定节点导出为图片 URL。

        Args:
            file_key: Figma 文件 Key
            node_ids: 要导出的节点 ID 列表
            format: 导出格式（png/jpg/svg/pdf）
            scale: 缩放倍数（0.01-4）

        Returns:
            各节点的图片 URL
        """
        err = self._check_figma_ready()
        if err:
            return err

        if not node_ids:
            return "❌ 请指定要导出的节点 ID"

        # 限制一次最多 20 个节点
        if len(node_ids) > 20:
            return f"❌ 单次最多导出 20 个节点，当前指定了 {len(node_ids)} 个"

        ids_param = ",".join(node_ids)
        scale = max(0.01, min(4, scale))  # 限制范围

        data = self._figma_request(
            "GET",
            f"/images/{file_key}?ids={ids_param}&format={format}&scale={scale}"
        )
        if not data:
            return f"❌ 导出图片失败（file_key: {file_key}）"

        err_msg = data.get("err")
        if err_msg:
            return f"❌ Figma 返回错误: {err_msg}"

        images = data.get("images", {})
        if not images:
            return "❌ 未生成任何图片，请检查节点 ID 是否正确"

        lines = [f"🖼️ 图片导出完成（{format.upper()}, {scale}x）：\n"]
        for node_id, url in images.items():
            if url:
                lines.append(f"  📌 节点 {node_id}:")
                lines.append(f"     {url}")
            else:
                lines.append(f"  ⚠️ 节点 {node_id}: 导出失败（可能是空节点）")
            lines.append("")

        lines.append(f"共 {len(images)} 个节点，链接有效期约 14 天")
        return "\n".join(lines)

    def list_figma_comments(self, file_key: str) -> str:
        """
        读取 Figma 文件中的所有评论。

        Args:
            file_key: Figma 文件 Key

        Returns:
            评论列表
        """
        err = self._check_figma_ready()
        if err:
            return err

        data = self._figma_request("GET", f"/files/{file_key}/comments")
        if not data:
            return f"❌ 获取评论失败（file_key: {file_key}）"

        comments = data.get("comments", [])
        if not comments:
            return "💬 该文件暂无评论"

        lines = [f"💬 共 {len(comments)} 条评论：\n"]
        for i, c in enumerate(comments[:20], 1):
            user = c.get("user", {}).get("handle", "未知用户")
            message = c.get("message", "")
            created = c.get("created_at", "")[:10]  # 只取日期部分
            resolved = c.get("resolved_at")

            status = "✅ 已解决" if resolved else "💬"
            lines.append(f"{i}. {status} {user} ({created})")
            lines.append(f"   {message[:100]}")
            if len(message) > 100:
                lines.append(f"   ... (评论较长，共 {len(message)} 字)")
            lines.append("")

        if len(comments) > 20:
            lines.append(f"... 还有 {len(comments) - 20} 条评论未显示")

        return self._truncate("\n".join(lines))

    def post_figma_comment(self, file_key: str, message: str,
                           x: float = 0, y: float = 0) -> str:
        """
        在 Figma 文件中发表评论。

        Args:
            file_key: Figma 文件 Key
            message: 评论内容
            x: 画布 X 坐标
            y: 画布 Y 坐标

        Returns:
            操作结果
        """
        err = self._check_figma_ready()
        if err:
            return err

        if not message.strip():
            return "❌ 评论内容不能为空"

        payload = {
            "message": message,
            "client_meta": {"x": x, "y": y}
        }

        data = self._figma_request(
            "POST",
            f"/files/{file_key}/comments",
            json=payload
        )
        if not data:
            return f"❌ 发表评论失败（file_key: {file_key}）"

        comment_id = data.get("id", "未知")
        return (
            f"✅ 评论发表成功\n"
            f"评论 ID: {comment_id}\n"
            f"内容: {message[:60]}\n"
            f"位置: ({x}, {y})"
        )
