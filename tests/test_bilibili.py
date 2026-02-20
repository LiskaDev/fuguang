"""
🎬 Bilibili 技能单元测试
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture
def bili_skill():
    from fuguang.core.skills.bilibili import BilibiliSkills
    class TestSkill(BilibiliSkills):
        pass
    return TestSkill()


# ========================================
# 时间解析
# ========================================

class TestTimeParser:
    def test_minutes_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("13:26") == 806

    def test_hours_minutes_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("1:02:30") == 3750

    def test_pure_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("806") == 806

    def test_empty(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("") == 0

    def test_zero(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("0:00") == 0

    def test_spaces(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("  13:26  ") == 806


# ========================================
# 集数提取
# ========================================

class TestEpisodeExtraction:
    def test_chinese_format(self, bili_skill):
        """第156集"""
        assert bili_skill._extract_episode_number("凡人修仙传 第156集") == 156

    def test_chinese_hua(self, bili_skill):
        """第156话"""
        assert bili_skill._extract_episode_number("凡人修仙传 第156话") == 156

    def test_number_only(self, bili_skill):
        """156集"""
        assert bili_skill._extract_episode_number("凡人修仙传 156集") == 156

    def test_ep_format(self, bili_skill):
        """EP156"""
        assert bili_skill._extract_episode_number("凡人修仙传 EP156") == 156

    def test_no_episode(self, bili_skill):
        """无集数"""
        assert bili_skill._extract_episode_number("凡人修仙传") == 0

    def test_empty(self, bili_skill):
        assert bili_skill._extract_episode_number("") == 0


# ========================================
# HTML 清理
# ========================================

class TestCleanHtml:
    def test_removes_em(self, bili_skill):
        assert bili_skill._clean_html('<em class="keyword">凡人</em>修仙传') == "凡人修仙传"

    def test_empty(self, bili_skill):
        assert bili_skill._clean_html("") == ""


# ========================================
# 视频搜索
# ========================================

class TestSearchVideo:
    @patch("fuguang.core.skills.bilibili.search")
    def test_returns_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "Python教程", "author": "UP", "play": 1234567, "bvid": "BV1test123", "duration": "24:00"}]
        })
        result = bili_skill.search_bilibili("Python", search_type="video")
        assert "Python教程" in result
        assert "BV1test123" in result

    @patch("fuguang.core.skills.bilibili.search")
    def test_no_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={"result": []})
        result = bili_skill.search_bilibili("不存在xxx")
        assert "未找到" in result


# ========================================
# 番剧搜索
# ========================================

class TestSearchBangumi:
    @patch("fuguang.core.skills.bilibili.search")
    def test_returns_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "凡人修仙传", "season_id": 12345, "areas": "中国", "eps": [{"id": 1}], "desc": "修仙"}]
        })
        result = bili_skill.search_bilibili("凡人修仙传", search_type="bangumi")
        assert "凡人修仙传" in result
        assert "ss12345" in result


# ========================================
# 播放
# ========================================

class TestPlayBilibili:
    @patch("fuguang.core.skills.bilibili.webbrowser")
    def test_play_by_bvid(self, mock_wb, bili_skill):
        result = bili_skill.play_bilibili(bvid="BV1xx411c7mDx")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1xx411c7mDx")
        assert "✅" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    def test_play_by_bvid_with_time(self, mock_wb, bili_skill):
        result = bili_skill.play_bilibili(bvid="BV1xx411c7mDx", time="13:26")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1xx411c7mDx?t=806")

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_bangumi_first(self, mock_search, mock_wb, bili_skill):
        """播放时优先搜番剧"""
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "凡人修仙传", "season_id": 28747}]
        })
        result = bili_skill.play_bilibili(keyword="凡人修仙传")
        mock_wb.open.assert_called_once()
        assert "ss28747" in mock_wb.open.call_args[0][0]

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.bangumi")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_specific_episode(self, mock_search, mock_bangumi, mock_wb, bili_skill):
        """播放番剧指定集数"""
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "凡人修仙传", "season_id": 28747}]
        })

        # mock Bangumi.get_episodes
        mock_ep = MagicMock()
        mock_ep.get_epid.return_value = 999156
        mock_bangumi_inst = MagicMock()
        mock_bangumi_inst.get_episodes = AsyncMock(return_value=[MagicMock()] * 155 + [mock_ep])
        mock_bangumi.Bangumi.return_value = mock_bangumi_inst

        result = bili_skill.play_bilibili(keyword="凡人修仙传", episode=156)
        mock_wb.open.assert_called_once()
        opened_url = mock_wb.open.call_args[0][0]
        assert "ep999156" in opened_url
        assert "第 156 集" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.bangumi")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_episode_with_time(self, mock_search, mock_bangumi, mock_wb, bili_skill):
        """番剧指定集数 + 时间戳"""
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "凡人修仙传", "season_id": 28747}]
        })

        mock_ep = MagicMock()
        mock_ep.get_epid.return_value = 999156
        mock_bangumi_inst = MagicMock()
        mock_bangumi_inst.get_episodes = AsyncMock(return_value=[MagicMock()] * 155 + [mock_ep])
        mock_bangumi.Bangumi.return_value = mock_bangumi_inst

        result = bili_skill.play_bilibili(keyword="凡人修仙传 第156集", episode=156, time="13:26")
        opened_url = mock_wb.open.call_args[0][0]
        assert "ep999156" in opened_url
        assert "t=806" in opened_url

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.bangumi")
    @patch("fuguang.core.skills.bilibili.search")
    def test_auto_extract_episode(self, mock_search, mock_bangumi, mock_wb, bili_skill):
        """从关键词自动提取集数"""
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "凡人修仙传", "season_id": 28747}]
        })

        mock_ep = MagicMock()
        mock_ep.get_epid.return_value = 999003
        mock_bangumi_inst = MagicMock()
        mock_bangumi_inst.get_episodes = AsyncMock(return_value=[MagicMock()] * 2 + [mock_ep])
        mock_bangumi.Bangumi.return_value = mock_bangumi_inst

        # 关键词中包含 "第3集"，不传 episode 参数
        result = bili_skill.play_bilibili(keyword="凡人修仙传 第3集")
        opened_url = mock_wb.open.call_args[0][0]
        assert "ep999003" in opened_url

    def test_play_no_args(self, bili_skill):
        result = bili_skill.play_bilibili()
        assert "关键词" in result or "BV" in result
