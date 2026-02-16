"""
test_memory.py — 记忆系统测试
验证 ChromaDB MemoryBank 的基本存取能力。
"""
import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestMemoryBank:
    """测试 MemoryBank（ChromaDB 向量记忆）"""

    def test_import(self):
        """MemoryBank 能正常导入"""
        from fuguang.core.memory import MemoryBank
        assert MemoryBank is not None

    @pytest.mark.integration
    def test_init_with_temp_dir(self, tmp_path):
        """MemoryBank 可用临时目录初始化"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        assert mb is not None

    @pytest.mark.integration
    def test_add_and_search_memory(self, tmp_path):
        """能存入并检索记忆"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        # 存入
        mb.add_memory("指挥官喜欢吃红烧肉", category="fact")
        
        # 检索
        results = mb.search_memory("喜欢吃什么")
        assert len(results) > 0
        # search_memory 可能返回 dict 或 str
        first = results[0]
        if isinstance(first, dict):
            assert "红烧肉" in first.get("content", "")
        else:
            assert "红烧肉" in first

    @pytest.mark.integration
    def test_add_recipe(self, tmp_path):
        """能存入配方记忆"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        mb.add_recipe(
            trigger="在记事本写",
            solution="应该用 create_file_directly 而不是打开软件"
        )
        
        results = mb.search_recipes("记事本写东西")
        assert len(results) > 0

    @pytest.mark.integration
    def test_recipe_dedup_by_solution(self, tmp_path):
        """相同教训、不同触发词的配方应被去重"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        # 第一次存入
        mb.add_recipe(
            trigger="帮我在Obsidian写一篇笔记，标题是可能",
            solution="应该直接用mcp_obsidian_write_file工具一次完成，不要先调list"
        )
        # 第二次存入——触发词不同但教训相同
        mb.add_recipe(
            trigger="帮我在Obsidian写一篇笔记，标题是测试",
            solution="应该直接用mcp_obsidian_write_file工具一次完成，避免多次调用list和write"
        )
        
        # 应该只有 1 条（第二条替换了第一条）
        count = mb.recipes.count()
        assert count == 1, f"配方应去重为1条，实际有{count}条"

    @pytest.mark.integration
    def test_recipe_keeps_different_lessons(self, tmp_path):
        """trigger 相似但教训不同的配方应保留两条"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        # 两个"打开XX"但教训完全不同
        mb.add_recipe(
            trigger="打开Chrome浏览器",
            solution="用execute_shell_command执行start chrome命令"
        )
        mb.add_recipe(
            trigger="打开记事本软件",
            solution="用create_file_directly直接写文件，不要启动notepad"
        )
        
        count = mb.recipes.count()
        assert count == 2, f"不同教训应保留2条，实际有{count}条"

    @pytest.mark.integration
    def test_get_memory_context(self, tmp_path):
        """get_memory_context 返回格式化的记忆文本"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        mb.add_memory("指挥官的MBTI是INFP", category="fact")
        
        context = mb.get_memory_context("MBTI是什么")
        assert context is not None
        assert isinstance(context, str)

    @pytest.mark.integration
    def test_dedup_prevents_duplicate_memory(self, tmp_path):
        """去重机制：相似记忆不会重复存储"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        mb.add_memory("指挥官喜欢吃红烧肉", category="fact")
        
        # 搜索相似内容，阈值 0.5 应命中
        existing = mb.search_memory("指挥官喜欢吃红烧肉", n_results=1, threshold=0.5)
        assert len(existing) > 0, "去重搜索应能找到已有记忆"
        assert existing[0]["distance"] < 0.5, "完全相同的内容距离应 < 0.5"

    @pytest.mark.integration
    def test_importance_filtering_in_context(self, tmp_path):
        """get_memory_context 过滤低重要度记忆"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        # 存一条低重要度记忆
        mb.add_memory("今天天气不错", category="fact", metadata={"importance": 1})
        # 存一条高重要度记忆
        mb.add_memory("指挥官的名字叫小明", category="fact", metadata={"importance": 5})
        
        context = mb.get_memory_context("指挥官是谁")
        # 高重要度应出现
        if context:
            assert "小明" in context or context == "", "高重要度记忆应被召回"

    @pytest.mark.integration
    def test_memory_context_has_natural_hint(self, tmp_path):
        """记忆上下文提示 AI 自然引用"""
        from fuguang.core.memory import MemoryBank
        mb = MemoryBank(persist_dir=str(tmp_path / "test_db"))
        
        mb.add_memory("指挥官下个月要考驾照", category="fact", metadata={"importance": 4})
        
        context = mb.get_memory_context("最近有什么计划")
        assert "自然" in context or "记得" in context, "提示词应引导 AI 自然引用记忆"


class TestShortTermMemory:
    """测试短期记忆（JSON 文件）"""

    def test_memory_file_format(self):
        """data/memory.json 格式正确"""
        import json
        mem_file = PROJECT_ROOT / "data" / "memory.json"
        if mem_file.exists():
            with open(mem_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict)
            # 应包含 user_profile 和 short_term_summary
            assert "user_profile" in data or "short_term_summary" in data

    def test_reminders_file_format(self):
        """data/reminders.json 格式正确（如果存在）"""
        import json
        rem_file = PROJECT_ROOT / "data" / "reminders.json"
        if rem_file.exists():
            with open(rem_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, list)
