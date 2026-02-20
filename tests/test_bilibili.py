"""
🎬 Bilibili 技能单元测试
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ========================================
# Fixtures
# ========================================

@pytest.fixture
def bili_skill():
    """创建带 BilibiliSkills 的实例"""
    from fuguang.core.skills.bilibili import BilibiliSkills

    class TestSkill(BilibiliSkills):
        pass

    return TestSkill()


# ========================================
# 时间解析测试
# ========================================

class TestTimeParser:
    """测试时间字符串解析"""

    def test_minutes_seconds(self, bili_skill):
        """13:26 → 806秒"""
        assert bili_skill._parse_time_to_seconds("13:26") == 806

    def test_hours_minutes_seconds(self, bili_skill):
        """1:02:30 → 3750秒"""
        assert bili_skill._parse_time_to_seconds("1:02:30") == 3750

    def test_pure_seconds(self, bili_skill):
        """806 → 806"""
        assert bili_skill._parse_time_to_seconds("806") == 806

    def test_empty_string(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("") == 0

    def test_zero(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("0:00") == 0

    def test_with_spaces(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("  13:26  ") == 806


# ========================================
# 搜索功能测试
# ========================================

class TestSearchBilibili:
    """测试B站搜索"""

    @patch("fuguang.core.skills.bilibili.search")
    def test_search_returns_results(self, mock_search, bili_skill):
        """搜索返回格式化结果"""
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [
                {
                    "title": "凡人修仙传 第156集",
                    "author": "B站番剧",
                    "play": 1234567,
                    "bvid": "BV1test123",
                    "duration": "24:00"
                }
            ]
        })

        result = bili_skill.search_bilibili("凡人修仙传")
        assert "凡人修仙传" in result
        assert "BV1test123" in result
        assert "123.5万" in result

    @patch("fuguang.core.skills.bilibili.search")
    def test_search_no_results(self, mock_search, bili_skill):
        """搜索无结果"""
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={"result": []})

        result = bili_skill.search_bilibili("不存在的视频xxxyyy")
        assert "未找到" in result

    @patch("fuguang.core.skills.bilibili.search")
    def test_search_strips_html(self, mock_search, bili_skill):
        """搜索结果去除HTML标签"""
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{
                "title": '<em class="keyword">凡人</em>修仙传',
                "author": "UP主",
                "play": 100,
                "bvid": "BV1test",
                "duration": "10:00"
            }]
        })

        result = bili_skill.search_bilibili("凡人")
        assert "<em" not in result
        assert "凡人修仙传" in result


# ========================================
# 播放功能测试
# ========================================

class TestPlayBilibili:
    """测试B站播放"""

    @patch("fuguang.core.skills.bilibili.webbrowser")
    def test_play_by_bvid(self, mock_wb, bili_skill):
        """通过BV号播放"""
        result = bili_skill.play_bilibili(bvid="BV1xx411c7mD")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1xx411c7mD")
        assert "✅" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    def test_play_by_bvid_with_time(self, mock_wb, bili_skill):
        """BV号 + 时间戳"""
        result = bili_skill.play_bilibili(bvid="BV1xx411c7mD", time="13:26")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1xx411c7mD?t=806")
        assert "13:26" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_by_keyword(self, mock_search, mock_wb, bili_skill):
        """通过关键词搜索并播放"""
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{
                "title": "怪物猎人荒野",
                "author": "GameUP",
                "bvid": "BV1game123",
                "play": 50000
            }]
        })

        result = bili_skill.play_bilibili(keyword="怪物猎人荒野")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1game123")
        assert "怪物猎人荒野" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_by_keyword_with_time(self, mock_search, mock_wb, bili_skill):
        """关键词 + 时间戳"""
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{
                "title": "凡人修仙传 156",
                "author": "番剧",
                "bvid": "BV1fanren",
                "play": 100000
            }]
        })

        result = bili_skill.play_bilibili(keyword="凡人修仙传 第156集", time="13:26")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1fanren?t=806")

    def test_play_no_args(self, bili_skill):
        """没有参数"""
        result = bili_skill.play_bilibili()
        assert "关键词" in result or "BV" in result
