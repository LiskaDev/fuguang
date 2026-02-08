# manage_memory.py - 记忆管理工具
"""
用法:
    python manage_memory.py list          # 列出所有记忆
    python manage_memory.py delete <id>   # 删除指定记忆
    python manage_memory.py clear         # 清空所有记忆!! 危险 !!
"""

import sys
sys.path.insert(0, 'src')

from fuguang.core.memory import MemoryBank

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
        
    cmd = sys.argv[1].lower()
    
    # 初始化记忆库
    memory = MemoryBank(persist_dir="data/memory_db")
    
    if cmd == "list":
        memories = memory.list_all_memories()
        if not memories:
            print("📭 记忆库是空的")
            return
            
        print(f"\n📚 共有 {len(memories)} 条记忆:\n")
        print("-" * 80)
        for i, mem in enumerate(memories, 1):
            print(f"{i}. [{mem['category']}] {mem['content'][:60]}...")
            print(f"   ID: {mem['id'][:16]}...  时间: {mem['timestamp']}")
            print("-" * 80)
            
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("❌ 请提供记忆 ID: python manage_memory.py delete <id>")
            return
        memory_id = sys.argv[2]
        result = memory.delete_memory(memory_id)
        print(result)
        
    elif cmd == "clear":
        confirm = input("⚠️ 确定要清空所有记忆吗? (输入 YES 确认): ")
        if confirm == "YES":
            result = memory.clear_all()
            print(result)
        else:
            print("已取消")
            
    elif cmd == "stats":
        stats = memory.get_stats()
        print(f"📊 记忆统计: {stats}")
        
    else:
        print(f"❌ 未知命令: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
