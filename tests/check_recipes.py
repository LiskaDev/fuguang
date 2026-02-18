import sys
sys.path.insert(0, 'src')
from fuguang.core.memory import MemoryBank

m = MemoryBank(persist_dir='data/memory_db')
r = m.recipes.get()

print(f"共 {len(r['ids'])} 条配方：\n")
for i, (rid, doc, meta) in enumerate(zip(r['ids'], r['documents'], r['metadatas'])):
    source = meta.get('source', '')
    trigger = meta.get('trigger', '')[:50]
    solution = meta.get('solution', '')[:100]
    print(f"[{i}] source={source}")
    print(f"     trigger={trigger}")
    print(f"     solution={solution}")
    print()
