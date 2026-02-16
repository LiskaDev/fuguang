"""检查自我学习功能是否保存了教训"""
import chromadb

# 连接数据库
client = chromadb.PersistentClient(path='data/memory_db')

# 列出所有集合
print("📚 数据库集合列表:")
collections = client.list_collections()
for c in collections:
    print(f"  - {c.name} (共 {c.count()} 条)")

# 查看对话记忆
print("\n🧠 检查对话记忆集合 (fuguang_memories):")
memories = client.get_collection('fuguang_memories')

# 获取所有记忆
all_results = memories.get(limit=100)
total = len(all_results['ids'])
print(f"   总数: {total} 条")

# 查找性能相关的教训（包含"create_file"、"记事本"、"优化"等关键词）
print("\n🔍 搜索性能优化相关的教训:")
keywords = ["create_file", "记事本", "优化", "快速", "直接", "不要", "应该"]
found = False
for i, doc in enumerate(all_results['documents']):
    if any(kw in doc for kw in keywords):
        print(f"   [{i+1}] {doc}")
        found = True

if not found:
    print("   ❌ 未找到性能学习记录")
    
# 显示最近5条记忆
print("\n📝 最近5条记忆:")
for i, doc in enumerate(all_results['documents'][-5:]):
    print(f"   {i+1}. {doc[:80]}...")

print("\n" + "="*60)
print("诊断建议:")
if not found:
    print("❌ 自我学习功能未触发，可能原因：")
    print("   1. 测试任务耗时 < 10秒")
    print("   2. 调用工具数 < 3个")
    print("   3. 后台线程未完成就重启了程序")
    print("\n💡 建议测试：'打开记事本，写入ABC，换行，写入DEF，换行，写入GHI，保存为test.txt'")
    print("   这会触发多个工具调用，耗时>10秒")
