"""
🔧 终极配方修复脚本
删除所有错误的 Obsidian 配方，写入唯一正确版本
"""
import sys
sys.path.insert(0, 'src')
from fuguang.core.memory import MemoryBank

m = MemoryBank(persist_dir='data/memory_db')

# ============================================================
# 需要删除的错误配方 ID（根据你的输出）
# ============================================================
DELETE_INDEXES = [10, 12, 15, 16, 20, 21, 22]  # 所有 Obsidian 相关的错误配方

r = m.recipes.get()
all_ids = r['ids']
all_metas = r['metadatas']

ids_to_delete = []
for i in DELETE_INDEXES:
    if i < len(all_ids):
        ids_to_delete.append(all_ids[i])
        trigger = all_metas[i].get('trigger', '')[:50]
        print(f"🗑️  删除 [{i}]: {trigger}")

# 额外：扫描所有配方，凡是 solution 里包含 Notes/ 或 list_allowed 的全删
for i, (rid, meta) in enumerate(zip(all_ids, all_metas)):
    solution = meta.get('solution', '')
    if rid not in ids_to_delete:
        if ('Notes/' in solution or 
            'list_allowed_directories' in solution) and \
           meta.get('source') != 'manual_fix':
            ids_to_delete.append(rid)
            print(f"🗑️  额外删除 [{i}]: {meta.get('trigger','')[:50]}")

if ids_to_delete:
    m.recipes.delete(ids=ids_to_delete)
    print(f"\n✅ 共删除 {len(ids_to_delete)} 条错误配方\n")

# ============================================================
# 写入唯一正确的 Obsidian 配方
# ============================================================
print("📝 写入正确配方...\n")

correct_recipes = [
    {
        "trigger": "Obsidian写笔记,黑曜石写笔记,黑药石写笔记,黑钥匙写笔记,写到Obsidian,记笔记,日记",
        "solution": (
            "直接调用一次 mcp_obsidian_write_file 完成，路径：FUGUANG/文件名.md。"
            "绝对禁止调用 list_allowed_directories、list_directory、create_directory。"
            "第一次就用 FUGUANG/文件名.md，写入失败也不改策略，检查文件名是否含非法字符。"
            "Notes/ 路径是错的，不要用。"
        ),
        "importance": 5
    },
]

for recipe in correct_recipes:
    result = m.add_recipe(
        trigger=recipe['trigger'],
        solution=recipe['solution'],
        metadata={"source": "manual_fix", "importance": recipe['importance']}
    )
    print(f"✅ 写入: {recipe['trigger'][:50]}")
    print(f"   {recipe['solution'][:80]}...")

# ============================================================
# 验证结果
# ============================================================
print("\n=== 当前所有配方 ===\n")
r = m.recipes.get()
for i, (rid, meta) in enumerate(zip(r['ids'], r['metadatas'])):
    src = meta.get('source', '')
    trigger = meta.get('trigger', '')[:55]
    solution = meta.get('solution', '')[:70]
    icon = "🛡️" if src == "manual_fix" else "📚"
    print(f"{icon} [{i}] {trigger}")
    print(f"      {solution}")
    print()

print("=" * 50)
print("✅ 完成！重启扶光测试。")
print("预期：写笔记只需 1 步，路径 FUGUANG/文件名.md")
