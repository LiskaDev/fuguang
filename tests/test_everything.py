"""
test_everything.py — Everything 文件搜索技能单元测试
不依赖真实 Everything 服务，全部通过 mock 测试。
"""
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestEverythingSchema:
    """测试 Everything Schema 定义"""

    def test_everything_tools_schema_exists(self):
        """_EVERYTHING_TOOLS Schema 列表存在且包含 3 个工具"""
        skills_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "everything.py"
        source = skills_file.read_text(encoding="utf-8")
        assert "_EVERYTHING_TOOLS" in source
        assert "search_files" in source
        assert "search_files_by_ext" in source
        assert "open_file_location" in source

    def test_everything_schema_registered_in_init(self):
        """__init__.py 中注册了 _EVERYTHING_TOOLS"""
        init_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "__init__.py"
        source = init_file.read_text(encoding="utf-8")
        assert "_EVERYTHING_TOOLS" in source
        assert "EverythingSkills" in source


class TestEverythingTools:
    """测试 Everything 工具方法"""

    def _make_skill(self, port=80):
        """构造一个最小的 EverythingSkills 实例"""
        from fuguang.core.skills.everything import EverythingSkills

        skill = EverythingSkills()
        skill.config = MagicMock()
        skill.config.EVERYTHING_PORT = port
        return skill

    @patch("fuguang.core.skills.everything.httpx.Client")
    def test_search_files_success(self, MockClient):
        """正常搜索文件"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalResults": 2,
            "results": [
                {"name": "test.py", "path": "C:\\Projects", "type": "file", "size": 1234},
                {"name": "test2.py", "path": "C:\\Projects", "type": "file", "size": 5678},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.search_files("test.py")

        assert "🔍" in result
        assert "test.py" in result
        assert "test2.py" in result

    @patch("fuguang.core.skills.everything.httpx.Client")
    def test_search_files_by_ext_success(self, MockClient):
        """按扩展名搜索"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "totalResults": 1,
            "results": [
                {"name": "scene.blend", "path": "D:\\Art", "type": "file", "size": 1048576},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.search_files_by_ext("blend")

        assert ".blend" in result
        assert "scene.blend" in result

    @patch("fuguang.core.skills.everything.httpx.Client")
    def test_search_no_results(self, MockClient):
        """无结果时返回友好提示"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"totalResults": 0, "results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        MockClient.return_value = mock_client

        skill = self._make_skill()
        result = skill.search_files("不存在的文件xyz")
        assert "未找到" in result

    def test_empty_query_rejected(self):
        """空查询被拒绝"""
        skill = self._make_skill()
        result = skill.search_files("")
        assert "❌" in result

    def test_empty_ext_rejected(self):
        """空扩展名被拒绝"""
        skill = self._make_skill()
        result = skill.search_files_by_ext("")
        assert "❌" in result

    def test_open_file_location_empty_path(self):
        """空路径被拒绝"""
        skill = self._make_skill()
        result = skill.open_file_location("")
        assert "❌" in result

    @patch("fuguang.core.skills.everything.os.path.exists", return_value=False)
    def test_open_file_location_not_found(self, mock_exists):
        """文件不存在时的处理"""
        skill = self._make_skill()
        result = skill.open_file_location("C:\\不存在\\fake.txt")
        assert "❌" in result or "⚠️" in result

    def test_format_size(self):
        """文件大小格式化"""
        from fuguang.core.skills.everything import EverythingSkills
        assert "B" in EverythingSkills._format_size(500)
        assert "KB" in EverythingSkills._format_size(2048)
        assert "MB" in EverythingSkills._format_size(5 * 1024 * 1024)
        assert "GB" in EverythingSkills._format_size(2 * 1024 * 1024 * 1024)
