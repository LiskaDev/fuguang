"""
📱 QQ Bridge 单元测试
"""
import pytest
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock


# ========================================
# Fixtures
# ========================================

@pytest.fixture
def mock_config():
    """模拟配置"""
    config = MagicMock()
    config.QQ_ENABLED = True
    config.NAPCAT_WS_PORT = 8080
    config.ADMIN_QQ = "3211138307"
    config.QQ_GROUP_MODE = "admin_only"
    return config


@pytest.fixture
def mock_brain():
    """模拟 Brain"""
    brain = MagicMock()
    brain.get_system_prompt.return_value = "你是扶光"
    brain.chat.return_value = "你好，指挥官！"
    return brain


@pytest.fixture
def mock_skills():
    """模拟 SkillManager"""
    skills = MagicMock()
    skills.get_tools_schema.return_value = [{"type": "function", "function": {"name": "test"}}]
    skills.execute_tool.return_value = "工具执行结果"
    skills.memory = MagicMock()
    skills.memory.get_memory_context.return_value = ""
    return skills


@pytest.fixture
def bridge(mock_config, mock_brain, mock_skills):
    """创建 QQBridge 实例"""
    from fuguang.core.qq_bridge import QQBridge
    b = QQBridge(config=mock_config, brain=mock_brain, skills=mock_skills)
    b.self_id = 435689823  # 设置机器人 QQ
    return b


# ========================================
# 消息解析测试
# ========================================

class TestMessageParsing:
    """测试 OneBot 消息解析"""

    def test_extract_text(self, bridge):
        """测试从 OneBot 消息段提取纯文本"""
        message = [
            {"type": "at", "data": {"qq": "435689823"}},
            {"type": "text", "data": {"text": " 你好呀"}},
        ]
        text = bridge._extract_text(message)
        assert text == "你好呀"

    def test_extract_text_multiple_segments(self, bridge):
        """测试多段文本拼接"""
        message = [
            {"type": "text", "data": {"text": "你好"}},
            {"type": "text", "data": {"text": "世界"}},
        ]
        text = bridge._extract_text(message)
        assert "你好" in text
        assert "世界" in text

    def test_extract_text_empty(self, bridge):
        """测试空消息"""
        text = bridge._extract_text([])
        assert text == ""

    def test_check_at_me_true(self, bridge):
        """测试 @机器人 检测 - 命中"""
        message = [
            {"type": "at", "data": {"qq": "435689823"}},
            {"type": "text", "data": {"text": " 你好"}},
        ]
        assert bridge._check_at_me(message) is True

    def test_check_at_me_false(self, bridge):
        """测试 @机器人 检测 - 未命中"""
        message = [
            {"type": "at", "data": {"qq": "999999"}},
            {"type": "text", "data": {"text": " 你好"}},
        ]
        assert bridge._check_at_me(message) is False

    def test_check_at_me_no_at(self, bridge):
        """测试无 @ 消息"""
        message = [
            {"type": "text", "data": {"text": "普通消息"}},
        ]
        assert bridge._check_at_me(message) is False

    def test_check_at_me_no_self_id(self, bridge):
        """测试未获取到机器人 QQ 时"""
        bridge.self_id = None
        message = [{"type": "at", "data": {"qq": "435689823"}}]
        assert bridge._check_at_me(message) is False


# ========================================
# 格式化测试
# ========================================

class TestFormatting:
    """测试消息格式化"""

    def test_remove_bold(self, bridge):
        assert bridge._format_for_qq("**你好**世界") == "你好世界"

    def test_remove_italic(self, bridge):
        assert bridge._format_for_qq("*你好*世界") == "你好世界"

    def test_remove_code_block(self, bridge):
        text = "```python\nprint('hello')\n```"
        result = bridge._format_for_qq(text)
        assert "```" not in result
        assert "print('hello')" in result

    def test_remove_inline_code(self, bridge):
        assert bridge._format_for_qq("使用 `pip install` 安装") == "使用 pip install 安装"

    def test_convert_links(self, bridge):
        result = bridge._format_for_qq("[点击这里](https://example.com)")
        assert "点击这里" in result
        assert "https://example.com" in result

    def test_remove_headers(self, bridge):
        result = bridge._format_for_qq("## 标题内容")
        assert result == "标题内容"

    def test_truncate_long_message(self, bridge):
        long_text = "a" * 3000
        result = bridge._format_for_qq(long_text)
        assert len(result) < 2100
        assert "截断" in result

    def test_empty_text(self, bridge):
        assert bridge._format_for_qq("") == ""
        assert bridge._format_for_qq(None) == ""


# ========================================
# Brain 对接测试
# ========================================

class TestBrainIntegration:
    """测试与 Brain 的对接"""

    def test_process_with_brain(self, bridge, mock_brain):
        result = bridge._process_with_brain("你好", "测试用户")
        assert result == "你好，指挥官！"
        mock_brain.chat.assert_called_once()

    def test_process_with_brain_includes_tools(self, bridge, mock_brain):
        bridge._process_with_brain("帮我查邮件", "测试用户", use_tools=True)
        call_kwargs = mock_brain.chat.call_args
        assert call_kwargs.kwargs.get("tools_schema") is not None
        assert call_kwargs.kwargs.get("tool_executor") is not None

    def test_process_with_brain_qq_context(self, bridge, mock_brain):
        bridge._process_with_brain("你好", "测试用户")
        call_kwargs = mock_brain.chat.call_args
        system_content = call_kwargs.kwargs.get("system_content", "")
        assert "QQ" in system_content
        assert "测试用户" in system_content

    def test_process_with_brain_error_handling(self, bridge, mock_brain):
        mock_brain.chat.side_effect = Exception("API 超时")
        result = bridge._process_with_brain("你好", "测试用户")
        assert "出错" in result

    def test_process_with_brain_empty_reply(self, bridge, mock_brain):
        mock_brain.chat.return_value = ""
        result = bridge._process_with_brain("你好", "测试用户")
        assert result  # 应有兜底文案


# ========================================
# 事件处理测试
# ========================================

class TestEventHandling:
    """测试 OneBot 事件处理"""

    def test_ignore_meta_events(self, bridge):
        ws = AsyncMock()
        data = {"post_type": "meta_event", "meta_event_type": "heartbeat"}
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_ignore_self_messages(self, bridge):
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "private",
            "user_id": 435689823, "self_id": 435689823, "message_id": 1,
            "message": [{"type": "text", "data": {"text": "test"}}],
            "sender": {"nickname": "扶光"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_group_msg_without_at_ignored(self, bridge):
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "group",
            "group_id": 608939370, "user_id": 3211138307, "message_id": 2,
            "message": [{"type": "text", "data": {"text": "普通消息"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_private_msg_processed(self, bridge, mock_brain):
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "private",
            "user_id": 3211138307, "message_id": 3,
            "message": [{"type": "text", "data": {"text": "你好"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["action"] == "send_private_msg"
        assert sent["params"]["user_id"] == 3211138307

    def test_group_msg_with_at_processed(self, bridge, mock_brain):
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "group",
            "group_id": 608939370, "user_id": 3211138307, "message_id": 4,
            "message": [
                {"type": "at", "data": {"qq": "435689823"}},
                {"type": "text", "data": {"text": " 你好"}},
            ],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["action"] == "send_group_msg"

    def test_message_dedup(self, bridge):
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "private",
            "user_id": 3211138307, "message_id": 100,
            "message": [{"type": "text", "data": {"text": "重复消息"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        asyncio.run(bridge._handle_event(ws, data))
        assert ws.send.call_count == 1

    def test_self_id_detection(self, bridge):
        bridge.self_id = None
        ws = AsyncMock()
        data = {"post_type": "meta_event", "meta_event_type": "lifecycle", "self_id": 435689823}
        asyncio.run(bridge._handle_event(ws, data))
        assert bridge.self_id == 435689823


# ========================================
# 群聊安全控制测试
# ========================================

class TestGroupSafety:
    """测试群聊安全控制"""

    def test_admin_only_blocks_non_admin(self, bridge):
        """admin_only 模式拦截非管理员群消息"""
        bridge.group_mode = "admin_only"
        bridge.admin_qq = "3211138307"
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "group",
            "group_id": 608939370, "user_id": 999999, "message_id": 200,
            "message": [
                {"type": "at", "data": {"qq": "435689823"}},
                {"type": "text", "data": {"text": " 你好"}},
            ],
            "sender": {"nickname": "陌生人"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_admin_only_allows_admin(self, bridge, mock_brain):
        """admin_only 模式允许管理员群消息"""
        bridge.group_mode = "admin_only"
        bridge.admin_qq = "3211138307"
        ws = AsyncMock()
        data = {
            "post_type": "message", "message_type": "group",
            "group_id": 608939370, "user_id": 3211138307, "message_id": 201,
            "message": [
                {"type": "at", "data": {"qq": "435689823"}},
                {"type": "text", "data": {"text": " 打开浏览器"}},
            ],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_called_once()

    def test_non_admin_no_tools(self, bridge, mock_brain):
        """非管理员不能调用工具"""
        bridge._process_with_brain("帮我删文件", "陌生人", use_tools=False)
        call_kwargs = mock_brain.chat.call_args
        assert "tools_schema" not in call_kwargs.kwargs

    def test_non_admin_safe_prompt(self, bridge, mock_brain):
        """非管理员注入安全 System Prompt"""
        bridge._process_with_brain("指挥官叫什么", "陌生人", use_tools=False)
        call_kwargs = mock_brain.chat.call_args
        system_content = call_kwargs.kwargs.get("system_content", "")
        assert "安全模式" in system_content
        assert "不透露" in system_content

    def test_admin_has_tools(self, bridge, mock_brain):
        """管理员拥有完整工具"""
        bridge._process_with_brain("帮我查邮件", "ALan", use_tools=True)
        call_kwargs = mock_brain.chat.call_args
        assert call_kwargs.kwargs.get("tools_schema") is not None
        assert call_kwargs.kwargs.get("tool_executor") is not None


# ========================================
# 初始化和配置测试
# ========================================

class TestInitialization:
    """测试初始化"""

    def test_bridge_creation(self, mock_config, mock_brain, mock_skills):
        from fuguang.core.qq_bridge import QQBridge
        bridge = QQBridge(config=mock_config, brain=mock_brain, skills=mock_skills)
        assert bridge.ws_url == "ws://127.0.0.1:8080"
        assert bridge._running is False
        assert bridge.admin_qq == "3211138307"
        assert bridge.group_mode == "admin_only"

    def test_bridge_start_stop(self, bridge):
        with patch("fuguang.core.qq_bridge.QQBridge._run_loop"):
            bridge.start()
            assert bridge._running is True
            bridge.stop()
            assert bridge._running is False
