import json
import os
import time
import logging
import jieba  # 需要安装: pip install jieba (用于提取关键词)
from datetime import datetime
from .config import LONG_TERM_MEMORY_FILE

# [修复C-3] 添加缺失的 logger 定义
logger = logging.getLogger("Fuguang")

# MEMORY_DB defined in config

# 停用词列表（过滤无意义的词）
STOP_WORDS = set([
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
    '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
    '看', '好', '自己', '这', '那', '里', '啊', '吧', '呢', '吗'
])

class MemorySystem:
    def __init__(self):
        self.memories = self._load_db()

    def _load_db(self):
        """加载记忆数据库"""
        if not LONG_TERM_MEMORY_FILE.exists():
            return []
        try:
            with open(LONG_TERM_MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"记忆文件读取失败: {e}")
            return []

    def _save_db(self):
        """保存记忆数据库"""
        with open(LONG_TERM_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=4)

    def add_memory(self, content, importance=1):
        """
        写入一条长期记忆（带去重和停用词过滤）
        content: 记忆内容 (如 "指挥官说他最喜欢风骚律师")
        importance: 重要程度 (1-5, 5为最高级，永不删除)
        """
        # 🔥 去重检查：避免重复记忆
        for mem in self.memories:
            if mem["content"] == content:
                print(f"⚠️ [海马体] 记忆已存在，跳过: {content}")
                return
        
        # 1. 自动提取关键词（过滤停用词）
        raw_keywords = jieba.cut(content)
        keywords = [w for w in raw_keywords if w not in STOP_WORDS and len(w) > 1]
        
        # 2. 构建记忆原子 (Memory Atom)
        memory_atom = {
            "id": int(time.time()),          # 唯一ID
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # 时间戳
            "content": content,              # 记忆正文
            "keywords": keywords,            # 用于检索的标签（已过滤）
            "importance": importance         # 权重
        }
        
        self.memories.append(memory_atom)
        self._save_db()
        print(f"🧠 [海马体] 已固化记忆: {content} (关键词: {keywords})")

    def search_memory(self, query_text):
        """
        检索记忆 (RAG 的雏形)
        原理：看 query_text 里有多少词命中记忆的 keywords
        升级：加入 importance 权重 + 子串匹配，提高召回率
        """
        query_words = list(jieba.cut(query_text))
        results = []

        for mem in self.memories:
            mem_keywords = mem.get("keywords", [])
            if not mem_keywords:
                continue
            
            # 计算匹配度（两种匹配方式）
            match_score = 0
            for query_word in query_words:
                if len(query_word) < 2:  # 跳过单字词
                    continue
                for keyword in mem_keywords:
                    # 方式1: 精确匹配
                    if query_word == keyword:
                        match_score += 2
                    # 方式2: 子串包含（'驾照' in '考驾照' 或反向）
                    elif query_word in keyword or keyword in query_word:
                        match_score += 1
            
            if match_score > 0:
                # 重要度作为权重因子 (1-5 → 1.0-2.0)
                importance = mem.get("importance", 1)
                weighted_score = match_score * (1 + importance * 0.2)
                results.append((weighted_score, mem["content"]))

        # 按加权分数降序排列，取前 3 条
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:3]]

# =======================
# 🧪 测试区 (Unit Test)
# =======================
if __name__ == "__main__":
    brain = MemorySystem()
    
    # 1. 模拟写入记忆 (假设这是几天前发生的)
    print("--- 正在写入记忆 ---")
    brain.add_memory("阿鑫最喜欢的剧是风骚律师", importance=5)
    brain.add_memory("阿鑫不喜欢吃蔬菜", importance=3)
    brain.add_memory("阿鑫正在开发Project Fuguang项目", importance=4)
    
    # 2. 模拟检索
    print("\n--- 正在回忆 ---")
    query = "我喜欢哪部剧？"
    print(f"用户问: {query}")
    recalled = brain.search_memory(query)
    print(f"扶光想起: {recalled}")
    
    query2 = "我不想吃什么？"
    print(f"\n用户问: {query2}")
    recalled2 = brain.search_memory(query2)
    print(f"扶光想起: {recalled2}")