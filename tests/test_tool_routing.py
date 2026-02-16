"""
test_tool_routing.py — 工具路由完整性测试
确保 SkillManager.execute_tool 能正确路由每一个工具名。
这是防回归的核心测试 — 上次 create_file_directly 和 send_hotkey 漏掉就是因为没有这个。
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# 所有应注册的工具名（这是「合同」，任何遗漏都会被捕获）
REQUIRED_TOOLS = [
    # Browser
    "search_web",
    "read_web_page",
    "open_website",
    "open_video",
    "browse_website",
    # Vision
    "analyze_screen_content",
    "analyze_image_file",
    "get_vision_history",
    # GUI
    "open_application",
    "click_screen_text",
    "type_text",
    "click_by_description",
    "list_ui_elements",
    "send_hotkey",                  # ← 之前漏掉的！
    # System
    "create_file_directly",         # ← 之前漏掉的！
    "execute_shell",
    "execute_shell_command",
    "launch_application",
    "list_installed_applications",
    "control_volume",
    "take_note",
    "write_code",
    "run_code",
    "open_tool",
    "set_reminder",
    "toggle_auto_execute",
    "transcribe_media_file",
    "listen_to_system_audio",
    # Memory
    "save_to_long_term_memory",
    "save_memory",
    "ingest_knowledge_file",
    "forget_knowledge",
    "forget_memory",
    "list_learned_files",
    "remember_recipe",
    "recall_recipe",
    "export_recipes_to_obsidian",
]


class TestToolRouting:
    """测试 execute_tool 路由表完整性"""

    def _get_route_source(self):
        """读取 __init__.py 源码，用于检查路由"""
        init_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "__init__.py"
        return init_file.read_text(encoding="utf-8")

    def test_all_tools_have_routes(self):
        """每个必需工具在 execute_tool 中都有路由"""
        source = self._get_route_source()
        missing = []
        for tool in REQUIRED_TOOLS:
            # 检查 func_name == "tool_name" 或 func_name == 'tool_name'
            if f'"{tool}"' not in source and f"'{tool}'" not in source:
                missing.append(tool)
        assert not missing, f"以下工具缺少路由: {missing}"

    def test_mcp_wildcard_route_exists(self):
        """MCP 工具有通配路由 startswith('mcp_')"""
        source = self._get_route_source()
        assert 'startswith("mcp_")' in source or "startswith('mcp_')" in source, \
            "缺少 MCP 通配路由 (mcp_* prefix)"

    def test_no_duplicate_routes(self):
        """没有重复的路由条目"""
        source = self._get_route_source()
        seen = {}
        for tool in REQUIRED_TOOLS:
            pattern = f'func_name == "{tool}"'
            count = source.count(pattern)
            if count == 0:
                pattern = f"func_name == '{tool}'"
                count = source.count(pattern)
            if count > 1:
                seen[tool] = count
        assert not seen, f"以下工具有重复路由: {seen}"


class TestToolSchema:
    """测试 get_tools_schema 返回的 Schema"""

    def _get_schema_source(self):
        """读取所有 Mixin 的 _*_TOOLS Schema 定义"""
        skills_dir = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills"
        all_source = ""
        for f in skills_dir.glob("*.py"):
            all_source += f.read_text(encoding="utf-8")
        return all_source

    def test_schema_files_have_tool_definitions(self):
        """各 Mixin 文件包含 Schema 定义"""
        skills_dir = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills"
        
        expected_schemas = {
            "vision.py": "_VISION_TOOLS",
            "gui.py": "_GUI_TOOLS",
            "browser.py": "_BROWSER_TOOLS",
            "system.py": "_SYSTEM_TOOLS",
            "memory.py": "_MEMORY_TOOLS",
        }
        
        for filename, schema_var in expected_schemas.items():
            filepath = skills_dir / filename
            assert filepath.exists(), f"缺少文件: {filename}"
            content = filepath.read_text(encoding="utf-8")
            assert schema_var in content, f"{filename} 中缺少 {schema_var} 定义"

    def test_create_file_directly_in_schema(self):
        """create_file_directly 出现在 Schema 中（防止再次遗漏）"""
        source = self._get_schema_source()
        assert "create_file_directly" in source, "create_file_directly 未在任何 Schema 中定义"

    def test_send_hotkey_in_schema(self):
        """send_hotkey 出现在 Schema 中（防止再次遗漏）"""
        source = self._get_schema_source()
        assert "send_hotkey" in source, "send_hotkey 未在任何 Schema 中定义"

    def test_mcp_obsidian_write_file_route(self):
        """mcp_obsidian_write_file 可通过 mcp_ 前缀路由"""
        # MCP 工具通过 startswith("mcp_") 统一路由，
        # 只需验证路由逻辑存在
        init_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "skills" / "__init__.py"
        source = init_file.read_text(encoding="utf-8")
        assert "mcp_" in source
        assert "execute_mcp_tool" in source
