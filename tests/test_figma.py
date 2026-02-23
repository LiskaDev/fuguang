"""
test_figma.py — Figma 技能单元测试
不调用真实 API，全部通过 mock 测试。
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestFigmaSchema:
    """测试 Figma Schema 定义"""

    def test_figma_tools_schema_exists(self):
        """_FIGMA_TOOLS Schema 列表存在且包含 5 个工具"""
        skills_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "figma.py"
        source = skills_file.read_text(encoding="utf-8")
        assert "_FIGMA_TOOLS" in source
        assert "get_figma_file" in source
        assert "get_figma_node" in source
        assert "get_figma_images" in source
        assert "list_figma_comments" in source
        assert "post_figma_comment" in source

    def test_figma_schema_registered_in_init(self):
        """__init__.py 中注册了 _FIGMA_TOOLS"""
        init_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "__init__.py"
        source = init_file.read_text(encoding="utf-8")
        assert "_FIGMA_TOOLS" in source
        assert "FigmaSkills" in source


class TestFigmaTools:
    """测试 Figma 工具方法（用 mock 替代真实 API）"""

    def _make_skill(self, api_key="test-figma-key"):
        """构造一个最小的 FigmaSkills 实例"""
        from fuguang.core.skills.figma import FigmaSkills

        skill = FigmaSkills()
        skill.config = MagicMock()
        skill.config.FIGMA_API_KEY = api_key
        return skill

    def test_no_api_key_returns_friendly_message(self):
        """未配置 API Key 时返回友好提示"""
        skill = self._make_skill(api_key="")
        result = skill.get_figma_file("test_key")
        assert "❌" in result
        assert "FIGMA_API_KEY" in result

    @patch("fuguang.core.skills.figma.httpx.Client")
    def test_get_figma_file_success(self, MockClient):
        """正常获取文件结构"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "name": "测试设计稿",
            "lastModified": "2025-01-01T00:00:00Z",
            "document": {
                "children": [
                    {
                        "name": "Page 1",
                        "id": "0:1",
                        "children": [
                            {"name": "Frame 1", "id": "1:2", "type": "FRAME"}
                        ]
                    }
                ]
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.get_figma_file("abc123")

        assert "🎨" in result
        assert "测试设计稿" in result
        assert "Page 1" in result
        assert "Frame 1" in result

    @patch("fuguang.core.skills.figma.httpx.Client")
    def test_get_figma_images_success(self, MockClient):
        """正常导出图片"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "images": {
                "1:2": "https://figma-cdn.example.com/image1.png",
                "3:4": "https://figma-cdn.example.com/image2.png"
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.get_figma_images("abc123", ["1:2", "3:4"])

        assert "🖼️" in result
        assert "figma-cdn.example.com" in result

    @patch("fuguang.core.skills.figma.httpx.Client")
    def test_post_figma_comment_success(self, MockClient):
        """正常发表评论"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "comment_123"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.post_figma_comment("abc123", "这里颜色不对")

        assert "✅" in result
        assert "comment_123" in result

    @patch("fuguang.core.skills.figma.httpx.Client")
    def test_list_figma_comments_empty(self, MockClient):
        """无评论时返回友好提示"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"comments": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.list_figma_comments("abc123")
        assert "暂无评论" in result

    def test_empty_node_ids_rejected(self):
        """空节点列表被拒绝"""
        skill = self._make_skill()
        result = skill.get_figma_images("abc123", [])
        assert "❌" in result

    def test_empty_comment_rejected(self):
        """空评论被拒绝"""
        skill = self._make_skill()
        result = skill.post_figma_comment("abc123", "   ")
        assert "❌" in result
