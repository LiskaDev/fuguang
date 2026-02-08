#!/usr/bin/env python
# manage_memory.py - 记忆管理工具 v2.0
"""
用法:
    python manage_memory.py stats              # 查看统计
    python manage_memory.py list               # 列出对话记忆
    python manage_memory.py list-knowledge     # 列出知识库
    python manage_memory.py delete <id>        # 删除对话记忆
    python manage_memory.py delete-knowledge <id>  # 删除知识库条目
    python manage_memory.py clear-memories     # 清空对话记忆
    python manage_memory.py clear-knowledge    # 清空知识库
    python manage_memory.py clear-all          # 清空所有 ⚠️危险
"""

import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fuguang.core.memory import MemoryBank

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1].lower()
    memory = MemoryBank(persist_dir="data/memory_db")
    
    if cmd == "stats":
        stats = memory.get_stats()
        print("\n📊 记忆库统计:")
        print(f"   对话记忆: {stats['memories_count']} 条")
        print(f"   知识库:   {stats['knowledge_count']} 条")
        print(f"   ─────────────────")
        print(f"   总计:     {stats['total']} 条")
        print(f"\n📍 存储位置: {os.path.abspath(memory.persist_dir)}")
    
    elif cmd == "list":
        memories = memory.list_all_memories(limit=50)
        if not memories:
            print("💭 对话记忆库是空的")
            return
        print(f"\n💭 对话记忆 ({len(memories)} 条):\n")
        for i, m in enumerate(memories, 1):
            print(f"{i}. [{m['category']}] {m['content'][:80]}...")
            print(f"   ID: {m['id']}")
            print(f"   时间: {m['timestamp']}\n")
    
    elif cmd == "list-knowledge":
        items = memory.list_all_knowledge(limit=50)
        if not items:
            print("📚 知识库是空的")
            return
        print(f"\n📚 知识库 ({len(items)} 条):\n")
        for i, m in enumerate(items, 1):
            source = m.get('source', 'unknown')
            print(f"{i}. [{source}] {m['content'][:80]}...")
            print(f"   ID: {m['id']}\n")
    
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("❌ 用法: python manage_memory.py delete <id>")
            return
        memory_id = sys.argv[2]
        result = memory.delete_memory(memory_id)
        print(result)
    
    elif cmd == "delete-knowledge":
        if len(sys.argv) < 3:
            print("❌ 用法: python manage_memory.py delete-knowledge <id>")
            return
        knowledge_id = sys.argv[2]
        result = memory.delete_knowledge(knowledge_id)
        print(result)
    
    elif cmd == "clear-memories":
        print("⚠️ 即将清空所有对话记忆！知识库不受影响。")
        confirm = input("输入 YES 确认: ")
        if confirm == "YES":
            result = memory.clear_memories()
            print(result)
        else:
            print("❌ 已取消")
    
    elif cmd == "clear-knowledge":
        print("⚠️ 即将清空所有知识库！对话记忆不受影响。")
        confirm = input("输入 YES 确认: ")
        if confirm == "YES":
            result = memory.clear_knowledge()
            print(result)
        else:
            print("❌ 已取消")
    
    elif cmd == "clear-all":
        print("⚠️⚠️⚠️ 即将清空所有记忆和知识库！这是不可逆操作！")
        confirm = input("输入 DELETE ALL 确认: ")
        if confirm == "DELETE ALL":
            result = memory.clear_all()
            print(result)
        else:
            print("❌ 已取消")
    
    else:
        print(f"❌ 未知命令: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
