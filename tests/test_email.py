"""
test_email.py — 邮件功能测试
覆盖：邮件规则分类、缓存持久化、过滤规则管理、SMTP 发送(附件/AI身份)、
      AI 频率限制、附件解析、工具 Schema 完整性、HTML 解析。

所有测试 mock 了 IMAP/SMTP，不需要真实邮箱连接。
"""
import sys
import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ===========================
# Fixtures
# ===========================

@pytest.fixture
def email_worker():
    """创建一个不连接 IMAP 的 _EmailMonitorWorker 实例"""
    from fuguang.core.skills.email import _EmailMonitorWorker

    worker = _EmailMonitorWorker(
        qq_email="test@qq.com",
        auth_code="test-auth-code",
        check_interval=3600,
        llm_client=MagicMock(),
        on_notify_callback=MagicMock()
    )
    return worker


def _make_email_data(from_addr="someone@example.com", subject="测试", preview=""):
    """构造 _classify_rule_based 需要的 email_data dict"""
    return {
        'from': from_addr,
        'subject': subject,
        'preview': preview or subject,
        'body': preview or subject,
    }


# ===========================
# 邮件规则分类测试
# ===========================

class TestEmailClassification:
    """测试 _classify_rule_based（规则层，不调用 AI）"""

    def test_spam_by_domain(self, email_worker):
        """来自黑名单域名的邮件被标记为垃圾"""
        data = _make_email_data(from_addr="notification@taobao.com", subject="您的订单")
        assert email_worker._classify_rule_based(data) == 'spam'

    def test_spam_by_noreply(self, email_worker):
        """noreply 发件人被标记为垃圾"""
        data = _make_email_data(from_addr="noreply@example.com", subject="通知")
        assert email_worker._classify_rule_based(data) == 'spam'

    def test_spam_by_keywords(self, email_worker):
        """命中 2 个以上垃圾关键词 → spam"""
        data = _make_email_data(
            subject="限时优惠 免费领取",
            preview="点击领取优惠券 促销活动"
        )
        assert email_worker._classify_rule_based(data) == 'spam'

    def test_normal_email_unknown(self, email_worker):
        """普通邮件返回 unknown（交给 AI 判断）"""
        data = _make_email_data(
            from_addr="friend@gmail.com",
            subject="周末聚餐吗",
            preview="这周末一起吃饭？"
        )
        assert email_worker._classify_rule_based(data) == 'unknown'

    def test_vip_sender(self, email_worker):
        """VIP 发件人直接标为 important"""
        email_worker.user_vip_senders = ["boss@company.com"]
        data = _make_email_data(from_addr="boss@company.com", subject="普通标题")
        assert email_worker._classify_rule_based(data) == 'important'

    def test_important_keyword(self, email_worker):
        """重要关键词 → important"""
        data = _make_email_data(subject="紧急通知：会议时间变更", preview="请注意")
        result = email_worker._classify_rule_based(data)
        assert result in ('important', 'urgent')

    def test_ad_prefix_spam(self, email_worker):
        """以 AD/广告 开头的主题 → spam"""
        data = _make_email_data(subject="广告：超低价格", preview="快来抢购")
        assert email_worker._classify_rule_based(data) == 'spam'


# ===========================
# 缓存与持久化测试
# ===========================

class TestEmailCache:
    """测试缓存持久化"""

    def test_cache_save_and_load(self, email_worker, tmp_path):
        """缓存可以保存和加载"""
        cache_file = tmp_path / "test_cache.json"
        email_worker.set_cache_file(cache_file)

        email_worker._last_check_results = [
            {'id': '1', 'from': 'test@qq.com', 'subject': '测试', 'level': 'normal'}
        ]
        email_worker._last_check_time = datetime(2026, 2, 19, 12, 0, 0)
        email_worker._save_cache()

        assert cache_file.exists()

        # 清空再加载
        email_worker._last_check_results = []
        email_worker._last_check_time = None
        email_worker._load_cache()

        assert len(email_worker._last_check_results) == 1
        assert email_worker._last_check_results[0]['subject'] == '测试'

    def test_processed_ids_persistence(self, email_worker, tmp_path):
        """已处理邮件 ID 持久化"""
        ids_file = tmp_path / "processed_ids.json"
        email_worker.set_processed_file(ids_file)

        email_worker._processed_ids = {'id1', 'id2', 'id3'}
        email_worker._save_processed_ids()

        assert ids_file.exists()

        email_worker._processed_ids = set()
        email_worker._load_processed_ids()

        assert 'id1' in email_worker._processed_ids
        assert len(email_worker._processed_ids) == 3


# ===========================
# 过滤规则管理测试
# ===========================

class TestFilterConfig:
    """测试用户自定义过滤规则"""

    def test_add_vip_sender(self, email_worker, tmp_path):
        """添加 VIP 发件人"""
        config_file = tmp_path / "filter_config.json"
        email_worker.set_filter_config_file(config_file)

        result = email_worker.add_filter_rule('vip', 'boss@qq.com')
        assert 'boss@qq.com' in email_worker.user_vip_senders
        assert '✅' in result

    def test_add_spam_keyword(self, email_worker, tmp_path):
        """添加垃圾关键词"""
        config_file = tmp_path / "filter_config.json"
        email_worker.set_filter_config_file(config_file)

        email_worker.add_filter_rule('spam_keyword', '赌博')
        assert '赌博' in email_worker.user_spam_keywords

        # 分类需要 2 个以上垃圾关键词命中，用自定义 + 内置关键词
        data = _make_email_data(subject="赌博网站推荐", preview="免费赌博优惠")
        result = email_worker._classify_rule_based(data)
        assert result == 'spam'

    def test_remove_rule(self, email_worker, tmp_path):
        """删除过滤规则"""
        config_file = tmp_path / "filter_config.json"
        email_worker.set_filter_config_file(config_file)

        email_worker.add_filter_rule('vip', 'someone@qq.com')
        assert 'someone@qq.com' in email_worker.user_vip_senders

        email_worker.remove_filter_rule('vip', 'someone@qq.com')
        assert 'someone@qq.com' not in email_worker.user_vip_senders

    def test_list_rules(self, email_worker, tmp_path):
        """列出所有规则"""
        config_file = tmp_path / "filter_config.json"
        email_worker.set_filter_config_file(config_file)

        email_worker.add_filter_rule('vip', 'vip@qq.com')
        result = email_worker.list_filter_rules()
        assert 'vip@qq.com' in result


# ===========================
# AI 邮箱频率限制测试
# ===========================

class TestAIRateLimit:
    """测试 AI 邮箱每月 2 封限制"""

    def test_rate_limit_allows_first_send(self, email_worker):
        """第一封允许发送"""
        email_worker._ai_send_log = []
        result = email_worker._check_ai_rate_limit()
        assert result is None  # None = 未超限

    def test_rate_limit_allows_second_send(self, email_worker):
        """第二封允许发送"""
        email_worker._ai_send_log = [
            datetime.now().isoformat()
        ]
        result = email_worker._check_ai_rate_limit()
        assert result is None

    def test_rate_limit_blocks_third_send(self, email_worker):
        """第三封被阻止"""
        now = datetime.now()
        email_worker._ai_send_log = [
            (now - timedelta(days=1)).isoformat(),
            now.isoformat()
        ]
        result = email_worker._check_ai_rate_limit()
        assert result is not None
        assert '月上限' in result

    def test_rate_limit_resets_next_month(self, email_worker):
        """上个月的发送不影响本月"""
        last_month = datetime.now().replace(day=1) - timedelta(days=1)
        email_worker._ai_send_log = [
            (last_month - timedelta(days=1)).isoformat(),
            last_month.isoformat()
        ]
        result = email_worker._check_ai_rate_limit()
        assert result is None

    def test_ai_send_log_persistence(self, email_worker, tmp_path):
        """AI 发送记录可以持久化"""
        log_file = tmp_path / "ai_send_log.json"

        email_worker._ai_send_log = [datetime.now().isoformat()]
        email_worker._ai_send_log_file = log_file
        email_worker._save_ai_send_log()

        assert log_file.exists()

        # 清空再加载
        email_worker._ai_send_log = []
        email_worker.set_ai_send_log_file(log_file)
        assert len(email_worker._ai_send_log) == 1


# ===========================
# SMTP 发送测试 (Mock)
# ===========================

class TestSendEmail:
    """测试邮件发送（SMTP 完全 Mock）"""

    @patch('smtplib.SMTP_SSL')
    def test_send_reply_success(self, mock_smtp_class, email_worker):
        """成功发送邮件"""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = email_worker.send_reply(
            to_addr="someone@qq.com",
            subject="测试",
            body="你好"
        )
        assert result is True

    @patch('smtplib.SMTP_SSL')
    def test_send_new_email_with_result(self, mock_smtp_class, email_worker):
        """send_new_email 返回结果消息"""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = email_worker.send_new_email(
            to_addr="test@qq.com",
            subject="标题",
            body="正文"
        )
        assert '✅' in result

    @patch('smtplib.SMTP_SSL')
    def test_send_with_attachment(self, mock_smtp_class, email_worker, tmp_path):
        """发送带附件的邮件"""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        test_file = tmp_path / "测试文档.txt"
        test_file.write_text("这是测试内容", encoding='utf-8')

        result = email_worker.send_reply(
            to_addr="someone@qq.com",
            subject="带附件",
            body="请查收",
            attachment_path=str(test_file)
        )
        assert result is True

    @patch('smtplib.SMTP_SSL')
    def test_send_new_email_with_attachment_result(self, mock_smtp_class, email_worker, tmp_path):
        """send_new_email 带附件返回成功消息含附件信息"""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        test_file = tmp_path / "报告.pdf"
        test_file.write_bytes(b"fake pdf content")

        result = email_worker.send_new_email(
            to_addr="test@qq.com",
            subject="报告",
            body="请查收",
            attachment_path=str(test_file)
        )
        assert '✅' in result
        assert '📎' in result
        assert '报告.pdf' in result

    def test_send_attachment_not_exists(self, email_worker):
        """附件文件不存在 → 失败"""
        result = email_worker.send_reply(
            to_addr="someone@qq.com",
            subject="附件",
            body="文件",
            attachment_path="C:\\不存在的路径\\fake.txt"
        )
        assert result is False

    @patch('smtplib.SMTP_SSL')
    def test_send_as_ai_success(self, mock_smtp_class, email_worker):
        """AI 身份发送成功"""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        email_worker.ai_qq_email = "ai@qq.com"
        email_worker.ai_auth_code = "ai-auth"
        email_worker._ai_send_log = []

        result = email_worker.send_as_ai(
            to_addr="user@qq.com",
            subject="来自扶光",
            body="你好指挥官"
        )
        assert '✅' in result
        assert len(email_worker._ai_send_log) == 1

    def test_send_as_ai_no_config(self, email_worker):
        """AI 邮箱未配置 → 失败"""
        email_worker.ai_qq_email = ''
        email_worker.ai_auth_code = ''
        result = email_worker.send_as_ai("user@qq.com", "标题", "正文")
        assert '❌' in result

    def test_send_as_ai_rate_limited(self, email_worker):
        """AI 发送超过月限制 → 被阻止"""
        email_worker.ai_qq_email = "ai@qq.com"
        email_worker.ai_auth_code = "ai-auth"
        now = datetime.now()
        email_worker._ai_send_log = [
            (now - timedelta(days=1)).isoformat(),
            now.isoformat()
        ]
        result = email_worker.send_as_ai("user@qq.com", "标题", "正文")
        assert '月上限' in result


# ===========================
# 附件内容解析测试
# ===========================

class TestAttachmentParsing:
    """测试 _parse_file_content"""

    def test_parse_txt_file(self, email_worker, tmp_path):
        """解析文本文件"""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello, World!", encoding='utf-8')

        content = email_worker._parse_file_content(txt_file)
        assert "Hello, World!" in content

    def test_parse_csv_file(self, email_worker, tmp_path):
        """解析 CSV 文件"""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25", encoding='utf-8')

        content = email_worker._parse_file_content(csv_file)
        assert "Alice" in content
        assert "Bob" in content

    def test_parse_json_file(self, email_worker, tmp_path):
        """解析 JSON 文件"""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}', encoding='utf-8')

        content = email_worker._parse_file_content(json_file)
        assert "key" in content

    def test_long_txt_truncated(self, email_worker, tmp_path):
        """超长文本被截断"""
        long_file = tmp_path / "long.txt"
        long_file.write_text("x" * 10000, encoding='utf-8')

        content = email_worker._parse_file_content(long_file)
        assert len(content) < 10000
        assert "截取" in content

    def test_unsupported_format(self, email_worker, tmp_path):
        """不支持的格式返回提示"""
        bin_file = tmp_path / "data.exe"
        bin_file.write_bytes(b'\x00\x01\x02')

        content = email_worker._parse_file_content(bin_file)
        assert "不支持" in content or ".exe" in content

    def test_image_file(self, email_worker, tmp_path):
        """图片文件返回提示"""
        img_file = tmp_path / "photo.jpg"
        img_file.write_bytes(b'\xff\xd8\xff')

        content = email_worker._parse_file_content(img_file)
        assert "图片" in content


# ===========================
# 工具 Schema 完整性测试
# ===========================

class TestEmailToolSchema:
    """测试邮件工具 Schema 定义"""

    def test_email_tools_schema_exists(self):
        """_EMAIL_TOOLS Schema 存在"""
        email_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "email.py"
        source = email_file.read_text(encoding='utf-8')
        assert "_EMAIL_TOOLS" in source

    def test_all_email_tools_in_schema(self):
        """所有邮件工具都有 Schema 定义"""
        email_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "email.py"
        source = email_file.read_text(encoding='utf-8')

        expected_tools = [
            "check_email",
            "read_email",
            "search_email",
            "config_email_filter",
            "reply_email",
            "send_email",
            "download_attachment",
        ]
        for tool in expected_tools:
            assert f'"{tool}"' in source, f"邮件工具 Schema 中缺少 {tool}"

    def test_ai_tools_schema_exists(self):
        """_EMAIL_AI_TOOLS Schema 含 notify_commander"""
        email_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "email.py"
        source = email_file.read_text(encoding='utf-8')
        assert "_EMAIL_AI_TOOLS" in source
        assert '"notify_commander"' in source

    def test_send_email_has_attachment_param(self):
        """send_email 工具有 attachment 参数"""
        email_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "email.py"
        source = email_file.read_text(encoding='utf-8')
        assert '"attachment"' in source

    def test_email_tools_have_routes(self):
        """邮件工具在 __init__.py 有路由"""
        init_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "__init__.py"
        source = init_file.read_text(encoding='utf-8')

        email_routes = [
            "check_email",
            "read_email",
            "search_email",
            "config_email_filter",
            "reply_email",
            "send_email",
            "download_attachment",
            "notify_commander",
        ]
        for tool in email_routes:
            assert f'"{tool}"' in source, f"路由中缺少 {tool}"


# ===========================
# HTML 解析测试
# ===========================

class TestHTMLParsing:
    """测试 _html_to_text 静态方法"""

    def test_html_to_text_basic(self):
        """基础 HTML → 纯文本"""
        from fuguang.core.skills.email import _EmailMonitorWorker
        html = "<html><body><p>你好世界</p></body></html>"
        text = _EmailMonitorWorker._html_to_text(html)
        assert "你好世界" in text

    def test_html_to_text_strips_scripts(self):
        """去除 script 标签"""
        from fuguang.core.skills.email import _EmailMonitorWorker
        html = "<html><body><script>alert('xss')</script><p>正文</p></body></html>"
        text = _EmailMonitorWorker._html_to_text(html)
        assert "alert" not in text
        assert "正文" in text

    def test_html_to_text_handles_links(self):
        """处理超链接"""
        from fuguang.core.skills.email import _EmailMonitorWorker
        html = '<html><body><a href="https://example.com">点击这里</a></body></html>'
        text = _EmailMonitorWorker._html_to_text(html)
        assert "点击这里" in text

    def test_html_to_text_strips_style(self):
        """去除 style 标签内容"""
        from fuguang.core.skills.email import _EmailMonitorWorker
        html = "<html><head><style>body{color:red}</style></head><body><p>内容</p></body></html>"
        text = _EmailMonitorWorker._html_to_text(html)
        assert "color" not in text
        assert "内容" in text
