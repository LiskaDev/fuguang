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
        """测试去除 Markdown 加粗"""
        assert bridge._format_for_qq("**你好**世界") == "你好世界"

    def test_remove_italic(self, bridge):
        """测试去除 Markdown 斜体"""
        assert bridge._format_for_qq("*你好*世界") == "你好世界"

    def test_remove_code_block(self, bridge):
        """测试去除代码块"""
        text = "```python\nprint('hello')\n```"
        result = bridge._format_for_qq(text)
        assert "```" not in result
        assert "print('hello')" in result

    def test_remove_inline_code(self, bridge):
        """测试去除行内代码"""
        assert bridge._format_for_qq("使用 `pip install` 安装") == "使用 pip install 安装"

    def test_convert_links(self, bridge):
        """测试 Markdown 链接转换"""
        result = bridge._format_for_qq("[点击这里](https://example.com)")
        assert "点击这里" in result
        assert "https://example.com" in result

    def test_remove_headers(self, bridge):
        """测试去除标题标记"""
        result = bridge._format_for_qq("## 标题内容")
        assert result == "标题内容"

    def test_truncate_long_message(self, bridge):
        """测试长消息截断"""
        long_text = "a" * 3000
        result = bridge._format_for_qq(long_text)
        assert len(result) < 2100
        assert "截断" in result

    def test_empty_text(self, bridge):
        """测试空文本"""
        assert bridge._format_for_qq("") == ""
        assert bridge._format_for_qq(None) == ""


# ========================================
# Brain 对接测试
# ========================================

class TestBrainIntegration:
    """测试与 Brain 的对接"""

    def test_process_with_brain(self, bridge, mock_brain):
        """测试正常消息处理"""
        result = bridge._process_with_brain("你好", "测试用户")
        assert result == "你好，指挥官！"
        mock_brain.chat.assert_called_once()

    def test_process_with_brain_includes_tools(self, bridge, mock_brain):
        """测试消息处理包含工具调用"""
        bridge._process_with_brain("帮我查邮件", "测试用户")
        call_kwargs = mock_brain.chat.call_args
        assert call_kwargs.kwargs.get("tools_schema") is not None
        assert call_kwargs.kwargs.get("tool_executor") is not None

    def test_process_with_brain_qq_context(self, bridge, mock_brain):
        """测试 QQ 上下文注入"""
        bridge._process_with_brain("你好", "测试用户")
        call_kwargs = mock_brain.chat.call_args
        system_content = call_kwargs.kwargs.get("system_content", "")
        assert "QQ" in system_content
        assert "测试用户" in system_content

    def test_process_with_brain_error_handling(self, bridge, mock_brain):
        """测试 Brain 异常处理"""
        mock_brain.chat.side_effect = Exception("API 超时")
        result = bridge._process_with_brain("你好", "测试用户")
        assert "出错" in result

    def test_process_with_brain_empty_reply(self, bridge, mock_brain):
        """测试 Brain 返回空"""
        mock_brain.chat.return_value = ""
        result = bridge._process_with_brain("你好", "测试用户")
        assert result  # 应有兜底文案


# ========================================
# 事件处理测试
# ========================================

class TestEventHandling:
    """测试 OneBot 事件处理"""

    def test_ignore_meta_events(self, bridge):
        """测试忽略元事件"""
        ws = AsyncMock()
        data = {"post_type": "meta_event", "meta_event_type": "heartbeat"}
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_ignore_self_messages(self, bridge):
        """测试忽略自己的消息"""
        ws = AsyncMock()
        data = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 435689823,
            "self_id": 435689823,
            "message_id": 1,
            "message": [{"type": "text", "data": {"text": "test"}}],
            "sender": {"nickname": "扶光"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_group_msg_without_at_ignored(self, bridge):
        """测试群消息不@不回复"""
        ws = AsyncMock()
        data = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 608939370,
            "user_id": 3211138307,
            "message_id": 2,
            "message": [{"type": "text", "data": {"text": "普通消息"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_not_called()

    def test_private_msg_processed(self, bridge, mock_brain):
        """测试私聊消息正常处理"""
        ws = AsyncMock()
        data = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 3211138307,
            "message_id": 3,
            "message": [{"type": "text", "data": {"text": "你好"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["action"] == "send_private_msg"
        assert sent["params"]["user_id"] == 3211138307

    def test_group_msg_with_at_processed(self, bridge, mock_brain):
        """测试群消息@机器人正常处理"""
        ws = AsyncMock()
        data = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 608939370,
            "user_id": 3211138307,
            "message_id": 4,
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
        assert sent["params"]["group_id"] == 608939370

    def test_message_dedup(self, bridge):
        """测试消息去重"""
        ws = AsyncMock()
        data = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 3211138307,
            "message_id": 100,
            "message": [{"type": "text", "data": {"text": "重复消息"}}],
            "sender": {"nickname": "ALan"},
        }
        asyncio.run(bridge._handle_event(ws, data))
        asyncio.run(bridge._handle_event(ws, data))  # 重复
        assert ws.send.call_count == 1  # 只处理一次

    def test_self_id_detection(self, bridge):
        """测试从事件中获取机器人 QQ"""
        bridge.self_id = None
        ws = AsyncMock()
        data = {
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "self_id": 435689823,
        }
        asyncio.run(bridge._handle_event(ws, data))
        assert bridge.self_id == 435689823


# ========================================
# 初始化和配置测试
# ========================================

class TestInitialization:
    """测试初始化"""

    def test_bridge_creation(self, mock_config, mock_brain, mock_skills):
        """测试 QQBridge 正常创建"""
        from fuguang.core.qq_bridge import QQBridge
        bridge = QQBridge(config=mock_config, brain=mock_brain, skills=mock_skills)
        assert bridge.ws_url == "ws://127.0.0.1:8080"
        assert bridge._running is False

    def test_bridge_start_stop(self, bridge):
        """测试启动和停止"""
        # Mock websockets 避免实际连接
        with patch("fuguang.core.qq_bridge.QQBridge._run_loop"):
            bridge.start()
            assert bridge._running is True
            bridge.stop()
            assert bridge._running is False
