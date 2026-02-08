# memory.py - 向量数据库双集合记忆系统 (海马体 v2.0)
"""
基于 ChromaDB 的 RAG (检索增强生成) 记忆系统

v2.0 新特性：
- 分离集合：对话记忆 vs 知识库
- 独立管理：可以清空知识库而不影响对话记忆
- 联合检索：RAG 时同时搜索两个集合

存储位置：[项目目录]/data/memory_db/
    ├── chroma.sqlite3          # ChromaDB 主数据库
    ├── [collection_uuid]/      # fuguang_memories (对话记忆)
    └── [collection_uuid]/      # fuguang_knowledge (知识库)
"""

import chromadb
from chromadb.utils import embedding_functions
import os
import uuid
import datetime
import logging
from typing import Optional, List, Dict

logger = logging.getLogger("Fuguang")


class MemoryBank:
    """扶光的海马体 v2.0 - 双集合长期记忆管理器"""
    
    # 集合名称常量
    COLLECTION_MEMORIES = "fuguang_memories"   # 对话记忆
    COLLECTION_KNOWLEDGE = "fuguang_knowledge"  # 知识库
    
    def __init__(self, persist_dir: str = "data/memory_db"):
        """
        初始化向量数据库（双集合）
        
        Args:
            persist_dir: 持久化存储目录
        """
        self.persist_dir = persist_dir
        
        # 1. 确保目录存在
        if not os.path.exists(persist_dir):
            os.makedirs(persist_dir)
            
        logger.info(f"🧠 [记忆] 正在加载 ChromaDB 向量数据库 ({persist_dir})...")
        
        # 2. 初始化持久化客户端
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # 3. 使用多语言嵌入模型 (支持中文！)
        try:
            self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("✅ [记忆] 多语言嵌入模型加载成功")
        except Exception as e:
            logger.warning(f"⚠️ 多语言模型加载失败: {e}，使用默认嵌入")
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # 4. 创建/获取两个独立集合
        # 对话记忆集合
        self.memories = self.client.get_or_create_collection(
            name=self.COLLECTION_MEMORIES,
            embedding_function=self.embedding_fn,
            metadata={"description": "对话记忆：用户偏好、重要信息、历史对话"}
        )
        
        # 知识库集合
        self.knowledge = self.client.get_or_create_collection(
            name=self.COLLECTION_KNOWLEDGE,
            embedding_function=self.embedding_fn,
            metadata={"description": "知识库：PDF/Word/代码等文档内容"}
        )
        
        # 兼容性：保留 collection 属性指向记忆集合
        self.collection = self.memories
        
        mem_count = self.memories.count()
        know_count = self.knowledge.count()
        logger.info(f"✅ [记忆] 双集合加载完成: 对话记忆 {mem_count} 条 | 知识库 {know_count} 条")

    # ========================
    # 对话记忆 (Memories)
    # ========================
    
    def add_memory(self, content: str, category: str = "general", metadata: dict = None) -> str:
        """
        存入一条对话记忆
        
        Args:
            content: 要记住的内容
            category: 分类 (preference/fact/event/task/general/knowledge)
            metadata: 附加元数据
            
        Returns:
            确认消息
        """
        if not content or not content.strip():
            return "❌ 无法存储空内容"
            
        if metadata is None:
            metadata = {}
        
        # 根据 category 决定存入哪个集合
        if category == "knowledge":
            return self._add_to_knowledge(content, metadata)
            
        # 添加时间戳和分类
        metadata.update({
            "category": category,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": metadata.get("source", "user_chat")
        })
        
        mem_id = str(uuid.uuid4())
        
        self.memories.add(
            documents=[content.strip()],
            metadatas=[metadata],
            ids=[mem_id]
        )
        
        logger.info(f"💾 [对话记忆] 已存储: '{content[:50]}...' (分类: {category})")
        return f"✅ 已记住: {content}"
    
    def _add_to_knowledge(self, content: str, metadata: dict) -> str:
        """存入知识库集合"""
        metadata.update({
            "category": "knowledge",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        
        mem_id = str(uuid.uuid4())
        
        self.knowledge.add(
            documents=[content.strip()],
            metadatas=[metadata],
            ids=[mem_id]
        )
        
        logger.debug(f"📚 [知识库] 已存储: '{content[:30]}...'")
        return f"✅ 已存入知识库"

    def search_memory(self, query: str, n_results: int = 3, threshold: float = 1.2) -> list:
        """
        语义检索对话记忆
        """
        return self._search_collection(self.memories, query, n_results, threshold)
    
    def search_knowledge(self, query: str, n_results: int = 3, threshold: float = 1.2) -> list:
        """
        语义检索知识库
        """
        return self._search_collection(self.knowledge, query, n_results, threshold)
    
    def search_all(self, query: str, n_results: int = 5, threshold: float = 1.2) -> list:
        """
        同时检索对话记忆和知识库，返回合并结果（按相似度排序）
        """
        memories = self._search_collection(self.memories, query, n_results, threshold)
        knowledge = self._search_collection(self.knowledge, query, n_results, threshold)
        
        # 合并并按距离排序
        combined = memories + knowledge
        combined.sort(key=lambda x: x['distance'])
        
        return combined[:n_results]
    
    def _search_collection(self, collection, query: str, n_results: int, threshold: float) -> list:
        """通用检索方法"""
        if not query or not query.strip():
            return []
            
        if collection.count() == 0:
            return []
            
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count())
        )
        
        documents = results.get('documents', [[]])[0]
        distances = results.get('distances', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        
        valid_results = []
        for i in range(len(documents)):
            if distances[i] < threshold:
                valid_results.append({
                    "content": documents[i],
                    "distance": round(distances[i], 3),
                    "category": metadatas[i].get("category", "unknown"),
                    "timestamp": metadatas[i].get("timestamp", "unknown"),
                    "source": metadatas[i].get("source", "unknown")
                })
        
        return valid_results

    def get_memory_context(self, query: str, n_results: int = 5) -> str:
        """
        获取格式化的记忆上下文 (用于注入 Prompt)
        同时搜索对话记忆和知识库
        """
        results = self.search_all(query, n_results)
        
        if not results:
            return ""
            
        memory_lines = []
        for mem in results:
            memory_lines.append(f"- [{mem['category']}] {mem['content']}")
            
        memory_block = "\n".join(memory_lines)
        
        return f"""
【相关历史记忆】:
{memory_block}
(请参考这些记忆来辅助回答，但不要机械复述)
"""

    # ========================
    # 统计与管理
    # ========================

    def get_stats(self) -> dict:
        """获取记忆库统计信息"""
        return {
            "memories_count": self.memories.count(),
            "knowledge_count": self.knowledge.count(),
            "total": self.memories.count() + self.knowledge.count()
        }

    def list_all_memories(self, limit: int = 50) -> list:
        """列出所有对话记忆"""
        return self._list_collection(self.memories, limit)
    
    def list_all_knowledge(self, limit: int = 50) -> list:
        """列出所有知识库条目"""
        return self._list_collection(self.knowledge, limit)
    
    def _list_collection(self, collection, limit: int) -> list:
        """通用列表方法"""
        if collection.count() == 0:
            return []
            
        results = collection.get(limit=limit)
        
        items = []
        for i in range(len(results['ids'])):
            items.append({
                "id": results['ids'][i],
                "content": results['documents'][i],
                "category": results['metadatas'][i].get('category', 'unknown'),
                "timestamp": results['metadatas'][i].get('timestamp', 'unknown'),
                "source": results['metadatas'][i].get('source', 'unknown')
            })
        
        return items

    def delete_memory(self, memory_id: str) -> str:
        """删除对话记忆"""
        try:
            self.memories.delete(ids=[memory_id])
            logger.info(f"🗑️ [对话记忆] 已删除: {memory_id}")
            return f"✅ 已删除记忆 {memory_id[:8]}..."
        except Exception as e:
            logger.error(f"❌ 删除失败: {e}")
            return f"❌ 删除失败: {str(e)}"
    
    def delete_knowledge(self, knowledge_id: str) -> str:
        """删除知识库条目"""
        try:
            self.knowledge.delete(ids=[knowledge_id])
            logger.info(f"🗑️ [知识库] 已删除: {knowledge_id}")
            return f"✅ 已删除知识条目 {knowledge_id[:8]}..."
        except Exception as e:
            logger.error(f"❌ 删除失败: {e}")
            return f"❌ 删除失败: {str(e)}"

    def update_memory(self, memory_id: str, new_content: str) -> str:
        """更新对话记忆"""
        try:
            self.memories.update(ids=[memory_id], documents=[new_content])
            logger.info(f"📝 [对话记忆] 已更新: {memory_id}")
            return f"✅ 已更新记忆 {memory_id[:8]}..."
        except Exception as e:
            logger.error(f"❌ 更新失败: {e}")
            return f"❌ 更新失败: {str(e)}"

    def clear_memories(self) -> str:
        """清空所有对话记忆（保留知识库）"""
        count = self.memories.count()
        if count > 0:
            all_ids = self.memories.get()['ids']
            self.memories.delete(ids=all_ids)
            logger.warning(f"🗑️ [对话记忆] 已清空 {count} 条")
            return f"已清空 {count} 条对话记忆"
        return "对话记忆库已经是空的"
    
    def clear_knowledge(self) -> str:
        """清空所有知识库（保留对话记忆）"""
        count = self.knowledge.count()
        if count > 0:
            all_ids = self.knowledge.get()['ids']
            self.knowledge.delete(ids=all_ids)
            logger.warning(f"🗑️ [知识库] 已清空 {count} 条")
            return f"已清空 {count} 条知识库条目"
        return "知识库已经是空的"

    def clear_all(self) -> str:
        """清空所有记忆和知识库（危险操作）"""
        mem_result = self.clear_memories()
        know_result = self.clear_knowledge()
        return f"{mem_result}\n{know_result}"

    # ========================
    # 按来源管理知识库
    # ========================
    
    def list_knowledge_sources(self) -> list:
        """列出知识库中所有的来源文件"""
        if self.knowledge.count() == 0:
            return []
        
        results = self.knowledge.get()
        sources = {}
        
        for i in range(len(results['ids'])):
            source = results['metadatas'][i].get('source', 'unknown')
            if source not in sources:
                sources[source] = 0
            sources[source] += 1
        
        return [{"source": s, "chunk_count": c} for s, c in sorted(sources.items())]
    
    def delete_knowledge_by_source(self, source_name: str) -> str:
        """
        删除来自特定文件的所有知识
        
        Args:
            source_name: 文件名（如 "张鑫5稿.docx"）
            
        Returns:
            删除结果
        """
        if self.knowledge.count() == 0:
            return "❌ 知识库是空的"
        
        # 获取所有条目
        results = self.knowledge.get()
        
        # 找到匹配的 ID
        ids_to_delete = []
        for i in range(len(results['ids'])):
            source = results['metadatas'][i].get('source', '')
            # 支持部分匹配
            if source_name.lower() in source.lower():
                ids_to_delete.append(results['ids'][i])
        
        if not ids_to_delete:
            return f"❌ 未找到来自 '{source_name}' 的知识"
        
        # 删除
        self.knowledge.delete(ids=ids_to_delete)
        logger.info(f"🗑️ [知识库] 已删除来自 '{source_name}' 的 {len(ids_to_delete)} 条记录")
        
        return f"✅ 已删除来自 '{source_name}' 的 {len(ids_to_delete)} 条知识碎片"
    
    def forget_memory_by_content(self, keyword: str) -> str:
        """
        删除包含特定关键词的对话记忆
        
        Args:
            keyword: 要匹配的关键词
            
        Returns:
            删除结果
        """
        if self.memories.count() == 0:
            return "❌ 对话记忆是空的"
        
        results = self.memories.get()
        
        ids_to_delete = []
        for i in range(len(results['ids'])):
            content = results['documents'][i]
            if keyword.lower() in content.lower():
                ids_to_delete.append(results['ids'][i])
        
        if not ids_to_delete:
            return f"❌ 未找到包含 '{keyword}' 的记忆"
        
        self.memories.delete(ids=ids_to_delete)
        logger.info(f"🗑️ [对话记忆] 已删除包含 '{keyword}' 的 {len(ids_to_delete)} 条记录")
        
        return f"✅ 已遗忘 {len(ids_to_delete)} 条包含 '{keyword}' 的记忆"
