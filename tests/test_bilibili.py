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
    def test_minutes_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("13:26") == 806

    def test_hours_minutes_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("1:02:30") == 3750

    def test_pure_seconds(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("806") == 806

    def test_empty_string(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("") == 0

    def test_zero(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("0:00") == 0

    def test_with_spaces(self, bili_skill):
        assert bili_skill._parse_time_to_seconds("  13:26  ") == 806


# ========================================
# HTML 清理测试
# ========================================

class TestCleanHtml:
    def test_removes_em_tags(self, bili_skill):
        assert bili_skill._clean_html('<em class="keyword">凡人</em>修仙传') == "凡人修仙传"

    def test_empty_string(self, bili_skill):
        assert bili_skill._clean_html("") == ""

    def test_no_tags(self, bili_skill):
        assert bili_skill._clean_html("普通文本") == "普通文本"


# ========================================
# 视频搜索测试
# ========================================

class TestSearchVideo:
    @patch("fuguang.core.skills.bilibili.search")
    def test_search_video_returns_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{
                "title": "Python入门教程",
                "author": "码农UP",
                "play": 1234567,
                "bvid": "BV1test123",
                "duration": "24:00"
            }]
        })
        result = bili_skill.search_bilibili("Python教程", search_type="video")
        assert "Python入门教程" in result
        assert "BV1test123" in result
        assert "123.5万" in result

    @patch("fuguang.core.skills.bilibili.search")
    def test_search_video_no_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={"result": []})
        result = bili_skill.search_bilibili("不存在xxx")
        assert "未找到" in result


# ========================================
# 番剧搜索测试
# ========================================

class TestSearchBangumi:
    @patch("fuguang.core.skills.bilibili.search")
    def test_search_bangumi_returns_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{
                "title": "凡人修仙传",
                "season_id": 12345,
                "media_id": 67890,
                "areas": "中国",
                "styles": "玄幻",
                "eps": [{"id": 1}, {"id": 2}],
                "cv": "未知",
                "desc": "一个小村少年的修仙之路"
            }]
        })
        result = bili_skill.search_bilibili("凡人修仙传", search_type="bangumi")
        assert "凡人修仙传" in result
        assert "番剧" in result
        assert "ss12345" in result

    @patch("fuguang.core.skills.bilibili.search")
    def test_search_bangumi_no_results(self, mock_search, bili_skill):
        mock_search.SearchObjectType.BANGUMI = "bangumi"
        mock_search.search_by_type = AsyncMock(return_value={"result": []})
        result = bili_skill.search_bilibili("不存在的番剧", search_type="bangumi")
        assert "未找到" in result


# ========================================
# 播放测试
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
        assert "13:26" in result

    @patch("fuguang.core.skills.bilibili.webbrowser")
    @patch("fuguang.core.skills.bilibili.search")
    def test_play_by_keyword(self, mock_search, mock_wb, bili_skill):
        mock_search.SearchObjectType.VIDEO = "video"
        mock_search.search_by_type = AsyncMock(return_value={
            "result": [{"title": "怪物猎人荒野", "author": "GameUP", "bvid": "BV1game12345x"}]
        })
        result = bili_skill.play_bilibili(keyword="怪物猎人荒野")
        mock_wb.open.assert_called_once_with("https://www.bilibili.com/video/BV1game12345x")
        assert "怪物猎人荒野" in result

    def test_play_no_args(self, bili_skill):
        result = bili_skill.play_bilibili()
        assert "关键词" in result or "BV" in result


# ========================================
# 字幕提取测试
# ========================================

class TestGetSubtitle:
    @patch("fuguang.core.skills.bilibili.httpx")
    @patch("fuguang.core.skills.bilibili.video")
    def test_get_subtitle_success(self, mock_video_mod, mock_httpx, bili_skill):
        """成功提取字幕"""
        mock_v = MagicMock()
        mock_video_mod.Video.return_value = mock_v

        # mock get_info
        mock_v.get_info = AsyncMock(return_value={
            "title": "测试视频",
            "pages": [{"cid": 12345, "part": "第一P"}]
        })

        # mock get_subtitle
        mock_v.get_subtitle = AsyncMock(return_value={
            "subtitles": [{
                "lan": "zh-CN",
                "lan_doc": "中文",
                "subtitle_url": "//example.com/sub.json"
            }]
        })

        # mock httpx response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "body": [
                {"content": "大家好"},
                {"content": "今天讲Python"},
                {"content": "谢谢观看"}
            ]
        }
        mock_httpx.get.return_value = mock_resp

        result = bili_skill.get_bilibili_subtitle(bvid="BV17x411w7KCx")
        assert "测试视频" in result
        assert "大家好" in result
        assert "Python" in result
        assert "3 句" in result

    @patch("fuguang.core.skills.bilibili.video")
    def test_get_subtitle_no_subtitles(self, mock_video_mod, bili_skill):
        """视频没有字幕"""
        mock_v = MagicMock()
        mock_video_mod.Video.return_value = mock_v

        mock_v.get_info = AsyncMock(return_value={
            "title": "无字幕视频",
            "pages": [{"cid": 12345, "part": ""}]
        })
        mock_v.get_subtitle = AsyncMock(return_value={"subtitles": []})

        result = bili_skill.get_bilibili_subtitle(bvid="BV17x411w7KCx")
        assert "没有可用字幕" in result

    @patch("fuguang.core.skills.bilibili.video")
    def test_get_subtitle_error(self, mock_video_mod, bili_skill):
        """错误处理"""
        mock_v = MagicMock()
        mock_video_mod.Video.return_value = mock_v
        mock_v.get_info = AsyncMock(side_effect=Exception("网络错误"))

        result = bili_skill.get_bilibili_subtitle(bvid="BV17x411w7KCx")
        assert "出错" in result
