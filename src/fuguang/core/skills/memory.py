"""
MemorySkills — 🧠 记忆类技能
长期记忆（向量数据库）、知识吞噬、记忆管理
"""
import logging

logger = logging.getLogger("fuguang.skills")

_MEMORY_TOOLS_SCHEMA = [
    {"type":"function","function":{"name":"save_memory","description":"将用户的重要信息存入长期记忆。","parameters":{"type":"object","properties":{"content":{"type":"string","description":"要记忆的内容"},"importance":{"type":"integer","description":"重要程度(1-5)"}},"required":["content"]}}},
    {"type":"function","function":{"name":"save_to_long_term_memory","description":"【长期记忆】将重要信息永久保存到向量数据库。你应该主动判断何时调用此工具。","parameters":{"type":"object","properties":{"content":{"type":"string","description":"要记住的内容"},"category":{"type":"string","description":"分类","enum":["preference","fact","task","event","general"]}},"required":["content"]}}},
    {"type":"function","function":{"name":"ingest_knowledge_file","description":"【知识库】读取本地文件并学习其内容。支持 PDF, Word, TXT, Markdown, Python, JSON等。","parameters":{"type":"object","properties":{"file_path":{"type":"string","description":"文件的绝对路径"}},"required":["file_path"]}}},
    {"type":"function","function":{"name":"forget_knowledge","description":"【删除知识】从知识库中删除来自特定文件的所有内容。","parameters":{"type":"object","properties":{"source_name":{"type":"string","description":"要删除的文件名"}},"required":["source_name"]}}},
    {"type":"function","function":{"name":"forget_memory","description":"【遗忘记忆】从对话记忆中删除包含特定关键词的记忆。","parameters":{"type":"object","properties":{"keyword":{"type":"string","description":"要匹配的关键词"}},"required":["keyword"]}}},
    {"type":"function","function":{"name":"list_learned_files","description":"【查看知识库】列出已学习的所有文件及其碎片数量。","parameters":{"type":"object","properties":{}}}},
]


class MemorySkills:
    """记忆类技能 Mixin"""
    _MEMORY_TOOLS = _MEMORY_TOOLS_SCHEMA

    def save_to_long_term_memory(self, content: str, category: str = "general") -> str:
        """
        【长期记忆】将重要信息永久保存到ChromaDB向量数据库。
        
        功能：AI主动判断重要信息并永久记忆，支持向量检索
        分类：preference(偏好) / fact(事实) / task(任务教训) / event(事件) / general(通用)
        
        Args:
            content: 要记住的内容
            category: 记忆分类（默认general）
            
        Returns:
            保存结果
        """
        if not self.memory:
            return "❌ 长期记忆系统未初始化，无法保存"
        logger.info(f"🧠 [记忆] AI 请求保存: '{content[:50]}...' (分类: {category})")
        try:
            result = self.memory.add_memory(content, category=category)
            self.mouth.speak("好的，我记住了")
            return result
        except Exception as e:
            return f"❌ 保存失败: {str(e)}"

    def ingest_knowledge_file(self, file_path: str) -> str:
        """
        【知识吞噬】读取本地文件并学习其内容，支持多种格式。
        
        支持格式：PDF, Word, TXT, Markdown, Python, JSON等
        处理流程：文档分块 → 向量嵌入 → 存储到ChromaDB
        
        Args:
            file_path: 文件的绝对路径
            
        Returns:
            学习结果（成功碎片数）
        """
        if not self.eater:
            return "❌ 知识吞噬系统未初始化"
        logger.info(f"📚 [知识库] AI 请求吞噬文件: {file_path}")
        self.mouth.speak("好的，让我来学习这个文件...")
        try:
            result = self.eater.ingest_file(file_path)
            if result.startswith("✅"):
                self.mouth.speak("学习完成，我已经记住了文件内容")
            return result
        except Exception as e:
            return f"❌ 吞噬失败: {str(e)}"

    def forget_knowledge(self, source_name: str) -> str:
        """
        【删除知识】从知识库中删除来自特定文件的所有内容。
        
        功能：按来源批量删除向量记录
        应用：文件已过期、信息错误、清理空间
        
        Args:
            source_name: 要删除的文件名（需完全匹配）
            
        Returns:
            删除结果（删除数量）
        """
        if not self.memory:
            return "❌ 记忆系统未初始化"
        logger.info(f"🗑️ [知识库] AI 请求删除来自 '{source_name}' 的知识")
        self.mouth.speak(f"好的，让我忘掉{source_name}的内容...")
        return self.memory.delete_knowledge_by_source(source_name)

    def forget_memory(self, keyword: str) -> str:
        """
        【遗忘记忆】从对话记忆中删除包含特定关键词的记忆。
        
        功能：按内容关键词模糊匹配删除
        应用：用户要求遗忘某事、删除隐私信息
        
        Args:
            keyword: 要匹配的关键词（支持部分匹配）
            
        Returns:
            删除结果（删除数量）
        """
        if not self.memory:
            return "❌ 记忆系统未初始化"
        logger.info(f"🗑️ [对话记忆] AI 请求遗忘包含 '{keyword}' 的记忆")
        self.mouth.speak(f"好的，让我忘掉关于{keyword}的事情...")
        return self.memory.forget_memory_by_content(keyword)

    def list_learned_files(self) -> str:
        """
        【查看知识库】列出已学习的所有文件及其碎片数量。
        
        功能：统计知识库内容，查看已吞噬的文件列表
        显示：文件名 + 碎片数 + 总体统计
        
        Returns:
            文件列表和统计信息
        """
        if not self.memory:
            return "❌ 记忆系统未初始化"
        sources = self.memory.list_knowledge_sources()
        if not sources:
            return "📚 知识库是空的，我还没有学习过任何文件"
        lines = ["📚 我已学习的文件："]
        for s in sources:
            lines.append(f"  • {s['source']} ({s['chunk_count']} 个碎片)")
        stats = self.memory.get_stats()
        lines.append(f"\n📊 统计：知识库 {stats['knowledge_count']} 条 | 对话记忆 {stats['memories_count']} 条")
        return "\n".join(lines)
