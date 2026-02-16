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
    COLLECTION_RECIPES = "fuguang_recipes"      # 技能配方（肌肉记忆）
    
    def __init__(self, persist_dir: str = "data/memory_db", obsidian_vault_path: str = ""):
        """
        初始化向量数据库（双集合）
        
        Args:
            persist_dir: 持久化存储目录
            obsidian_vault_path: Obsidian Vault 根目录（为空则不同步）
        """
        self.persist_dir = persist_dir
        self.obsidian_vault_path = obsidian_vault_path
        
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
        
        # 4. 创建/获取三个独立集合（带损坏自动修复）
        self.memories = self._safe_get_collection(self.COLLECTION_MEMORIES, "对话记忆：用户偏好、重要信息、历史对话")
        self.knowledge = self._safe_get_collection(self.COLLECTION_KNOWLEDGE, "知识库：PDF/Word/代码等文档内容")
        self.recipes = self._safe_get_collection(self.COLLECTION_RECIPES, "技能配方：成功工作流、工具链、最佳实践")
        
        # 兼容性：保留 collection 属性指向记忆集合
        self.collection = self.memories
        
        mem_count = self.memories.count()
        know_count = self.knowledge.count()
        recipe_count = self.recipes.count()
        logger.info(f"✅ [记忆] 三集合加载完成: 对话记忆 {mem_count} 条 | 知识库 {know_count} 条 | 技能配方 {recipe_count} 条")

    def _safe_get_collection(self, name: str, description: str):
        """安全获取集合，HNSW索引损坏时自动重建"""
        try:
            collection = self.client.get_or_create_collection(
                name=name,
                embedding_function=self.embedding_fn,
                metadata={"description": description}
            )
            # 尝试访问一下，触发索引加载
            collection.count()
            return collection
        except Exception as e:
            error_msg = str(e)
            if "hnsw" in error_msg.lower() or "Nothing found on disk" in error_msg:
                logger.warning(f"⚠️ [记忆] {name} 索引损坏，正在自动重建...")
                try:
                    self.client.delete_collection(name)
                except Exception:
                    pass
                collection = self.client.get_or_create_collection(
                    name=name,
                    embedding_function=self.embedding_fn,
                    metadata={"description": description}
                )
                logger.info(f"✅ [记忆] {name} 已重建（之前的数据已丢失）")
                return collection
            else:
                raise

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
    
    def search_recipes(self, query: str, n_results: int = 3, threshold: float = 1.2) -> list:
        """
        语义检索技能配方
        """
        return self._search_collection(self.recipes, query, n_results, threshold)
    
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

    # ========================
    # 技能配方 (Recipes) — 肌肉记忆
    # ========================
    
    def add_recipe(self, trigger: str, solution: str, metadata: dict = None) -> str:
        """
        存入一条技能配方（最佳实践/工作流经验）
        带去重机制：如果已存在高度相似的配方，会替换旧版而非重复追加。
        
        Args:
            trigger: 触发场景描述（用户会怎么说）
            solution: 最佳方案描述（应该怎么做）
            metadata: 附加信息（来源、工具链等）
            
        Returns:
            确认消息
        """
        if not trigger or not solution:
            return "❌ 触发场景和解决方案不能为空"
        
        if metadata is None:
            metadata = {}
        
        # 将触发词和方案合并为文档（方便向量检索）
        document = f"当用户说'{trigger}'时，{solution}"
        
        # === 去重检测 ===
        # 查找是否已有高度相似的配方（距离 < 0.5 视为"同一类经验"）
        DEDUP_THRESHOLD = 0.5
        existing = self.search_recipes(trigger, n_results=1, threshold=DEDUP_THRESHOLD)
        
        replaced_id = None
        if existing:
            old = existing[0]
            old_id = old.get('id', '')
            old_trigger = old.get('metadata', {}).get('trigger', '')
            logger.info(f"🔄 [配方] 发现相似配方(距离={old['distance']:.3f}): '{old_trigger[:30]}' → 用新版替换")
            # 删除旧配方
            try:
                self.recipes.delete(ids=[old_id])
                replaced_id = old_id
            except Exception as e:
                logger.warning(f"⚠️ [配方] 删除旧配方失败: {e}")
        
        metadata.update({
            "trigger": trigger[:200],
            "solution": solution[:500],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": metadata.get("source", "auto_learn")
        })
        
        recipe_id = f"recipe_{uuid.uuid4().hex[:12]}"
        
        self.recipes.add(
            documents=[document],
            metadatas=[metadata],
            ids=[recipe_id]
        )
        
        if replaced_id:
            logger.info(f"🔄 [配方] 已进化: '{trigger[:30]}' (替换了 {replaced_id[:20]})")
            action = "进化"
        else:
            logger.info(f"🍳 [配方] 已习得: '{trigger[:30]}' → '{solution[:50]}'")
            action = "习得"
        
        # 同步到 Obsidian 成长日记
        self._sync_recipe_to_obsidian(trigger, solution, metadata)
        
        return f"✅ 已{action}技能配方: {trigger}"
    
    def recall_recipe(self, query: str, n_results: int = 2) -> str:
        """
        回忆相关的技能配方，返回格式化文本（直接注入 Prompt）
        
        Args:
            query: 当前任务/用户输入
            n_results: 最多返回几条
            
        Returns:
            格式化的配方提示文本，无匹配时返回空字符串
        """
        results = self.search_recipes(query, n_results=n_results, threshold=1.0)
        
        if not results:
            return ""
        
        lines = []
        for r in results:
            lines.append(f"- {r['content']}")
        
        return "\n".join(lines)
    
    # ========================
    # Obsidian 成长日记同步
    # ========================
    
    def _get_obsidian_diary_dir(self) -> Optional[str]:
        """获取 Obsidian 成长日记目录，不存在则创建"""
        if not self.obsidian_vault_path:
            return None
        diary_dir = os.path.join(self.obsidian_vault_path, "扶光成长日记")
        if not os.path.exists(diary_dir):
            try:
                os.makedirs(diary_dir)
                logger.info(f"📓 [Obsidian] 已创建成长日记目录: {diary_dir}")
            except OSError as e:
                logger.error(f"❌ [Obsidian] 创建目录失败: {e}")
                return None
        return diary_dir

    def _sync_recipe_to_obsidian(self, trigger: str, solution: str, metadata: dict):
        """将单条配方追加到当天的 Obsidian 日记"""
        diary_dir = self._get_obsidian_diary_dir()
        if not diary_dir:
            return
        
        today = datetime.datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        time_str = today.strftime("%H:%M:%S")
        filepath = os.path.join(diary_dir, f"{date_str}.md")
        
        source = metadata.get("source", "unknown") if metadata else "unknown"
        
        # 构建 Markdown 条目
        entry = (
            f"\n## ⚡ {trigger}\n\n"
            f"- **时间**: {time_str}\n"
            f"- **来源**: `{source}`\n\n"
            f"> {solution}\n\n"
            f"---\n"
        )
        
        try:
            is_new = not os.path.exists(filepath)
            with open(filepath, "a", encoding="utf-8") as f:
                if is_new:
                    # 新文件加 YAML front-matter + 标题
                    f.write(
                        f"---\ntags:\n  - 扶光\n  - 配方记忆\ndate: {date_str}\n---\n\n"
                        f"# 🌟 扶光成长日记 — {date_str}\n\n"
                        f"> 今天扶光学到的新技能和最佳实践。\n\n---\n"
                    )
                f.write(entry)
            logger.info(f"📓 [Obsidian] 已同步配方到 {date_str}.md")
        except Exception as e:
            logger.error(f"❌ [Obsidian] 写入失败: {e}")

    def export_all_recipes_to_obsidian(self) -> str:
        """
        将所有配方一次性导出到 Obsidian，生成索引页 + 按日期归档。
        用于首次开启 Obsidian 同步时补全历史数据。
        
        Returns:
            导出结果消息
        """
        diary_dir = self._get_obsidian_diary_dir()
        if not diary_dir:
            return "❌ 未配置 Obsidian Vault 路径"
        
        recipe_count = self.recipes.count()
        if recipe_count == 0:
            return "📭 配方库是空的，没有需要导出的内容"
        
        # 获取所有配方
        results = self.recipes.get(limit=recipe_count)
        
        # 按日期分组
        date_groups: Dict[str, list] = {}
        for i in range(len(results['ids'])):
            meta = results['metadatas'][i]
            ts = meta.get('timestamp', '')
            date_key = ts[:10] if len(ts) >= 10 else "未知日期"
            
            if date_key not in date_groups:
                date_groups[date_key] = []
            date_groups[date_key].append({
                "trigger": meta.get("trigger", ""),
                "solution": meta.get("solution", ""),
                "source": meta.get("source", "unknown"),
                "time": ts[11:] if len(ts) > 11 else ""
            })
        
        # 写入每日文件
        exported = 0
        for date_str, recipes in sorted(date_groups.items()):
            filepath = os.path.join(diary_dir, f"{date_str}.md")
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(
                        f"---\ntags:\n  - 扶光\n  - 配方记忆\ndate: {date_str}\n---\n\n"
                        f"# 🌟 扶光成长日记 — {date_str}\n\n"
                        f"> 今天扶光学到的新技能和最佳实践。\n\n---\n"
                    )
                    for r in recipes:
                        f.write(
                            f"\n## ⚡ {r['trigger']}\n\n"
                            f"- **时间**: {r['time'] or '未知'}\n"
                            f"- **来源**: `{r['source']}`\n\n"
                            f"> {r['solution']}\n\n"
                            f"---\n"
                        )
                exported += len(recipes)
            except Exception as e:
                logger.error(f"❌ [Obsidian] 导出 {date_str}.md 失败: {e}")
        
        # 生成索引页
        index_path = os.path.join(diary_dir, "README.md")
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(
                    "---\ntags:\n  - 扶光\n  - 配方记忆\n---\n\n"
                    "# 📚 扶光成长日记\n\n"
                    "> 扶光通过实践自动习得的技能配方，按日期归档。\n\n"
                )
                for date_str in sorted(date_groups.keys(), reverse=True):
                    count = len(date_groups[date_str])
                    f.write(f"- [[{date_str}]] — {count} 条配方\n")
                f.write(f"\n---\n\n*共 {exported} 条配方，{len(date_groups)} 天记录*\n")
        except Exception as e:
            logger.error(f"❌ [Obsidian] 索引页写入失败: {e}")
        
        msg = f"✅ 已导出 {exported} 条配方到 Obsidian ({len(date_groups)} 天)"
        logger.info(f"📓 [Obsidian] {msg}")
        return msg

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
        ids = results.get('ids', [[]])[0]
        
        valid_results = []
        for i in range(len(documents)):
            if distances[i] < threshold:
                valid_results.append({
                    "id": ids[i],
                    "content": documents[i],
                    "distance": round(distances[i], 3),
                    "metadata": metadatas[i],
                    "category": metadatas[i].get("category", "unknown"),
                    "timestamp": metadatas[i].get("timestamp", "unknown"),
                    "source": metadatas[i].get("source", "unknown")
                })
        
        return valid_results

    def get_memory_context(self, query: str, n_results: int = 5) -> str:
        """
        获取格式化的记忆上下文 (用于注入 Prompt)
        智能路由：同时搜索对话记忆、知识库、技能配方
        v5.3: 增加重要度过滤，低价值记忆不污染上下文
        """
        results = self.search_all(query, n_results)
        
        # 同时检索技能配方（独立搜索，不混入通用结果排序）
        recipe_text = self.recall_recipe(query, n_results=2)
        
        # 过滤低重要度记忆（importance < 2 的琐碎信息不注入）
        if results:
            results = [
                mem for mem in results
                if mem.get('metadata', {}).get('importance', 3) >= 2
            ]
        
        if not results and not recipe_text:
            return ""
        
        sections = []
        
        # 技能配方优先展示（最高优先级，影响 AI 工具选择）
        if recipe_text:
            sections.append(f"【⚡ 最佳实践（务必优先遵循）】:\n{recipe_text}")
        
        # 通用记忆/知识（标注重要度，帮助 AI 判断权重）
        if results:
            memory_lines = []
            for mem in results:
                imp = mem.get('metadata', {}).get('importance', '')
                imp_tag = f"★{imp}" if imp else ""
                memory_lines.append(f"- [{mem['category']}{imp_tag}] {mem['content']}")
            sections.append(f"【相关历史记忆】:\n" + "\n".join(memory_lines))
        
        context = "\n\n".join(sections)
        return f"\n{context}\n(你记得这些！自然地引用，比如'对了你之前说过…'、'我记得你…'，不要生硬地列出来)\n"

    # ========================
    # 统计与管理
    # ========================

    def get_stats(self) -> dict:
        """获取记忆库统计信息"""
        mem = self.memories.count()
        know = self.knowledge.count()
        rec = self.recipes.count()
        return {
            "memories_count": mem,
            "knowledge_count": know,
            "recipes_count": rec,
            "total": mem + know + rec
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
