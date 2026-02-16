"""
test_brain.py — Brain 模块测试
验证 System Prompt 生成、对话历史修剪等核心逻辑。
"""
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestBrainSystemPrompt:
    """测试 Brain.get_system_prompt()"""

    def test_get_system_prompt_basic(self, tmp_path):
        """get_system_prompt 能正常返回"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        # 确保 MEMORY_FILE 指向一个有效的 JSON 文件
        mem_file = tmp_path / "memory.json"
        mem_file.write_text('{"user_profile": {}, "short_term_summary": "test"}', encoding="utf-8")
        config.MEMORY_FILE = mem_file
        
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        prompt = brain.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "沈扶光" in prompt

    def test_get_system_prompt_with_context(self, tmp_path):
        """带感知数据时，prompt 包含感知信息"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        mem_file = tmp_path / "memory.json"
        mem_file.write_text('{"user_profile": {}, "short_term_summary": "test"}', encoding="utf-8")
        config.MEMORY_FILE = mem_file
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        prompt = brain.get_system_prompt(dynamic_context={
            "app": "Visual Studio Code",
            "clipboard": "test code"
        })
        assert "Visual Studio Code" in prompt
        assert "test code" in prompt

    def test_get_system_prompt_contains_time(self, tmp_path):
        """prompt 包含当前时间"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        mem_file = tmp_path / "memory.json"
        mem_file.write_text('{"user_profile": {}, "short_term_summary": "test"}', encoding="utf-8")
        config.MEMORY_FILE = mem_file
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        prompt = brain.get_system_prompt()
        # 应包含时间格式 HH:MM:SS
        import re
        assert re.search(r'\d{2}:\d{2}:\d{2}', prompt), "prompt 中没有时间"


class TestBrainHistory:
    """测试对话历史管理"""

    def test_trim_history_under_limit(self):
        """历史未超限时不修剪"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        brain.chat_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
        brain.trim_history()
        assert len(brain.chat_history) == 2

    def test_trim_history_over_limit(self):
        """历史超限时会修剪"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        # 填入超过 MAX_HISTORY*2 的消息
        for i in range(50):
            brain.chat_history.append({"role": "user", "content": f"msg {i}"})
            brain.chat_history.append({"role": "assistant", "content": f"reply {i}"})
        
        original_len = len(brain.chat_history)
        brain.trim_history()
        assert len(brain.chat_history) < original_len
        assert len(brain.chat_history) <= brain.MAX_HISTORY * 2


class TestBrainMemory:
    """测试短期记忆存取"""

    def test_load_memory_missing_file(self, tmp_path):
        """文件不存在时返回默认值"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        config.MEMORY_FILE = tmp_path / "nonexistent.json"
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        mem = brain.load_memory()
        assert isinstance(mem, dict)
        assert "user_profile" in mem

    def test_save_and_load_memory(self, tmp_path):
        """保存和读取记忆"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        config.MEMORY_FILE = tmp_path / "test_mem.json"
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            from fuguang.core.brain import Brain
            brain = Brain(config, mouth)
        
        test_data = {"user_profile": {"name": "测试"}, "short_term_summary": "ok"}
        brain.save_memory(test_data)
        
        loaded = brain.load_memory()
        assert loaded["user_profile"]["name"] == "测试"
        assert loaded["short_term_summary"] == "ok"


class TestBrainResilience:
    """测试 Brain.chat() 的健壮性"""

    def test_api_retry_on_timeout(self):
        """API 超时时自动重试，最终降级回复"""
        from fuguang.core.config import ConfigManager
        from fuguang.core.brain import Brain, APITimeoutError
        config = ConfigManager()
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            brain = Brain(config, mouth)
        
        # Mock client 总是超时
        brain.client = MagicMock()
        brain.client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
        
        result = brain.chat(
            user_input="你好",
            system_content="你是扶光",
            tools_schema=[],
            tool_executor=lambda name, args: "ok"
        )
        assert "网络" in result or "服务器" in result or "不稳定" in result

    def test_tool_executor_exception_handled(self):
        """工具执行异常时不会让整个对话崩溃"""
        from fuguang.core.config import ConfigManager
        from fuguang.core.brain import Brain
        config = ConfigManager()
        mouth = MagicMock()
        
        with patch("fuguang.core.brain.MemoryBank"):
            brain = Brain(config, mouth)
        
        # Mock: 第一次调用返回工具调用，第二次返回文本
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "broken_tool"
        mock_tool_call.function.arguments = '{"x": 1}'
        
        msg_with_tool = MagicMock()
        msg_with_tool.tool_calls = [mock_tool_call]
        msg_with_tool.content = None
        
        msg_final = MagicMock()
        msg_final.tool_calls = None
        msg_final.content = "好的，工具出了点问题 [Neutral]"
        
        brain.client = MagicMock()
        resp1 = MagicMock()
        resp1.choices = [MagicMock(message=msg_with_tool)]
        resp2 = MagicMock()
        resp2.choices = [MagicMock(message=msg_final)]
        brain.client.chat.completions.create.side_effect = [resp1, resp2]
        
        def exploding_executor(name, args):
            raise RuntimeError("工具爆炸了!")
        
        result = brain.chat(
            user_input="测试",
            system_content="你是扶光",
            tools_schema=[],
            tool_executor=exploding_executor
        )
        # 不应该崩溃，应该拿到最终回复
        assert isinstance(result, str)
        assert len(result) > 0
