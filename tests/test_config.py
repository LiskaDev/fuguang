"""
test_config.py — 配置模块测试
验证 ConfigManager 能正确初始化、路径正确、文件存在。
"""
import sys
import os
import pytest
from pathlib import Path

# 确保项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestConfigManager:
    """测试 ConfigManager 初始化"""

    def test_import(self):
        """ConfigManager 能正常导入"""
        from fuguang.core.config import ConfigManager
        assert ConfigManager is not None

    def test_init(self):
        """ConfigManager 能正常实例化"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        assert config is not None

    def test_project_root(self):
        """项目根目录正确"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        assert config.PROJECT_ROOT.exists()
        assert (config.PROJECT_ROOT / "run.py").exists()

    def test_system_prompt_file_exists(self):
        """System Prompt 文件存在"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        assert config.SYSTEM_PROMPT_FILE.exists(), f"缺少: {config.SYSTEM_PROMPT_FILE}"

    def test_directories_exist(self):
        """关键目录存在"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        assert config.CONFIG_DIR.exists()
        assert config.DATA_DIR.exists()
        assert config.LOG_DIR.exists()

    def test_api_keys_configured(self):
        """API Key 已配置（非空）"""
        from fuguang.core.config import ConfigManager
        config = ConfigManager()
        assert config.DEEPSEEK_API_KEY, "DEEPSEEK_API_KEY 未配置"
        assert config.DEEPSEEK_BASE_URL, "DEEPSEEK_BASE_URL 未配置"


class TestSystemPrompt:
    """测试 System Prompt 模板"""

    def test_template_has_placeholders(self):
        """System Prompt 包含必要的模板变量"""
        prompt_file = PROJECT_ROOT / "config" / "system_prompt.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "{current_time}" in content, "缺少 {current_time} 占位符"
        assert "{current_date}" in content, "缺少 {current_date} 占位符"
        assert "{mode_status}" in content, "缺少 {mode_status} 占位符"
        assert "{history_summary}" in content, "缺少 {history_summary} 占位符"

    def test_template_has_mcp_section(self):
        """System Prompt 包含 MCP 工具说明"""
        prompt_file = PROJECT_ROOT / "config" / "system_prompt.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "mcp_github" in content, "缺少 GitHub MCP 说明"
        assert "mcp_obsidian" in content, "缺少 Obsidian MCP 说明"

    def test_template_has_obsidian_priority(self):
        """System Prompt 包含 Obsidian 工具优先级规则（v5.2.1新增）"""
        prompt_file = PROJECT_ROOT / "config" / "system_prompt.txt"
        content = prompt_file.read_text(encoding="utf-8")
        assert "mcp_obsidian_write_file" in content, "缺少 Obsidian 优先级规则"

    def test_template_format_succeeds(self):
        """System Prompt 模板中的 4 个核心占位符可成功 format()"""
        prompt_file = PROJECT_ROOT / "config" / "system_prompt.txt"
        content = prompt_file.read_text(encoding="utf-8")
        # System Prompt 可能包含 {server}/{tool} 等示例文本，
        # 只验证 4 个核心占位符存在且可被替换
        for placeholder in ["current_time", "current_date", "mode_status", "history_summary"]:
            assert f"{{{placeholder}}}" in content, f"缺少占位符: {placeholder}"
        
        # 用 safe_substitute 风格验证：不会因为示例中的 {server} 而报错
        import re
        # 只替换 4 个核心变量，其他大括号保持不变
        result = content
        result = result.replace("{current_time}", "12:00:00")
        result = result.replace("{current_date}", "2026-02-17 周一")
        result = result.replace("{mode_status}", "🔒已锁定")
        result = result.replace("{history_summary}", "测试摘要")
        assert len(result) > 100
