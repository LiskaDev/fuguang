# memory.py - 向量数据库长期记忆系统 (海马体)
"""
基于 ChromaDB 的 RAG (检索增强生成) 记忆系统

功能：
- 向量化存储用户偏好、重要信息、历史对话
- 语义检索相关记忆
- 持久化到本地硬盘
"""

import chromadb
from chromadb.utils import embedding_functions
import os
import uuid
import datetime
import logging

logger = logging.getLogger("Fuguang")


class MemoryBank:
    """扶光的海马体 - 长期记忆管理器"""
    
    def __init__(self, persist_dir: str = "data/memory_db"):
        """
        初始化向量数据库
        
        Args:
            persist_dir: 持久化存储目录
        """
        # 1. 确保目录存在
        if not os.path.exists(persist_dir):
            os.makedirs(persist_dir)
            
        logger.info(f"🧠 [记忆] 正在加载 ChromaDB 向量数据库 ({persist_dir})...")
        
        # 2. 初始化持久化客户端
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # 3. 使用多语言嵌入模型 (支持中文！)
        # 首次运行会下载 ~400MB 模型
        try:
            self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"  # 多语言版本，中文友好
            )
            logger.info("✅ [记忆] 多语言嵌入模型加载成功")
        except Exception as e:
            # 备用：使用默认嵌入函数
            logger.warning(f"⚠️ 多语言模型加载失败: {e}，使用默认嵌入")
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # 4. 获取或创建记忆集合
        self.collection = self.client.get_or_create_collection(
            name="fuguang_long_term_memory",
            embedding_function=self.embedding_fn,
            metadata={"description": "扶光的长期记忆库"}
        )
        
        memory_count = self.collection.count()
        logger.info(f"✅ [记忆] 海马体加载完成，已有 {memory_count} 条记忆")

    def add_memory(self, content: str, category: str = "general", metadata: dict = None) -> str:
        """
        存入一条记忆
        
        Args:
            content: 要记住的内容
            category: 分类 (preference/fact/event/task/general)
            metadata: 附加元数据
            
        Returns:
            确认消息
        """
        if not content or not content.strip():
            return "❌ 无法存储空内容"
            
        if metadata is None:
            metadata = {}
            
        # 添加时间戳和分类
        metadata.update({
            "category": category,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "user_chat"
        })
        
        # 生成唯一 ID
        mem_id = str(uuid.uuid4())
        
        self.collection.add(
            documents=[content.strip()],
            metadatas=[metadata],
            ids=[mem_id]
        )
        
        logger.info(f"💾 [记忆] 已永久存储: '{content[:50]}...' (分类: {category})")
        return f"✅ 已记住: {content}"

    def search_memory(self, query: str, n_results: int = 3, threshold: float = 1.2) -> list:
        """
        语义检索相关记忆
        
        Args:
            query: 查询内容
            n_results: 返回结果数量
            threshold: 距离阈值 (越小越相似，建议 0.8-1.5)
            
        Returns:
            相关记忆列表
        """
        if not query or not query.strip():
            return []
            
        # 如果记忆库是空的，直接返回
        if self.collection.count() == 0:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=min(n_results, self.collection.count())  # 不能超过总数
        )
        
        # 提取结果
        documents = results.get('documents', [[]])[0]
        distances = results.get('distances', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        
        # 过滤：只保留相似度高的 (距离小于阈值)
        valid_memories = []
        for i in range(len(documents)):
            if distances[i] < threshold:
                memory_info = {
                    "content": documents[i],
                    "distance": round(distances[i], 3),
                    "category": metadatas[i].get("category", "unknown"),
                    "timestamp": metadatas[i].get("timestamp", "unknown")
                }
                valid_memories.append(memory_info)
                logger.debug(f"   📎 记忆: '{documents[i][:30]}...' (距离: {distances[i]:.3f})")
        
        if valid_memories:
            logger.info(f"⚡ [回忆] 联想起 {len(valid_memories)} 条相关记忆")
            
        return valid_memories

    def get_memory_context(self, query: str, n_results: int = 3) -> str:
        """
        获取格式化的记忆上下文 (用于注入 Prompt)
        
        Args:
            query: 查询内容
            n_results: 返回结果数量
            
        Returns:
            格式化的记忆文本块
        """
        memories = self.search_memory(query, n_results)
        
        if not memories:
            return ""
            
        # 格式化为文本块
        memory_lines = []
        for mem in memories:
            memory_lines.append(f"- [{mem['category']}] {mem['content']}")
            
        memory_block = "\n".join(memory_lines)
        
        return f"""
【相关历史记忆】:
{memory_block}
(请参考这些记忆来辅助回答，但不要机械复述)
"""

    def get_stats(self) -> dict:
        """获取记忆库统计信息"""
        return {
            "total_memories": self.collection.count(),
            "collection_name": self.collection.name
        }

    def list_all_memories(self, limit: int = 50) -> list:
        """
        列出所有记忆（用于调试和管理）
        
        Returns:
            记忆列表 [{id, content, category, timestamp}]
        """
        if self.collection.count() == 0:
            return []
            
        results = self.collection.get(limit=limit)
        
        memories = []
        for i in range(len(results['ids'])):
            memories.append({
                "id": results['ids'][i],
                "content": results['documents'][i],
                "category": results['metadatas'][i].get('category', 'unknown'),
                "timestamp": results['metadatas'][i].get('timestamp', 'unknown')
            })
        
        return memories

    def delete_memory(self, memory_id: str) -> str:
        """
        删除指定记忆
        
        Args:
            memory_id: 记忆的 UUID
            
        Returns:
            确认消息
        """
        try:
            self.collection.delete(ids=[memory_id])
            logger.info(f"🗑️ [记忆] 已删除记忆: {memory_id}")
            return f"✅ 已删除记忆 {memory_id[:8]}..."
        except Exception as e:
            logger.error(f"❌ 删除失败: {e}")
            return f"❌ 删除失败: {str(e)}"

    def update_memory(self, memory_id: str, new_content: str) -> str:
        """
        更新指定记忆的内容
        
        Args:
            memory_id: 记忆的 UUID
            new_content: 新内容
            
        Returns:
            确认消息
        """
        try:
            # ChromaDB 的 update 是覆盖操作
            self.collection.update(
                ids=[memory_id],
                documents=[new_content]
            )
            logger.info(f"📝 [记忆] 已更新记忆: {memory_id}")
            return f"✅ 已更新记忆 {memory_id[:8]}..."
        except Exception as e:
            logger.error(f"❌ 更新失败: {e}")
            return f"❌ 更新失败: {str(e)}"

    def clear_all(self) -> str:
        """清空所有记忆 (危险操作)"""
        count = self.collection.count()
        if count > 0:
            # 获取所有 ID 并删除
            all_ids = self.collection.get()['ids']
            self.collection.delete(ids=all_ids)
            logger.warning(f"🗑️ [记忆] 已清空 {count} 条记忆")
            return f"已清空 {count} 条记忆"
        return "记忆库已经是空的"
