"""
验证docstring改进效果 - 对比工具扫描前后的差异
"""
import os
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'

from src.fuguang.core.tool_scanner import ToolScanner
from src.fuguang.core.skills import SkillManager

print("\n" + "="*60)
print("🔍 工具扫描器覆盖率验证")
print("="*60 + "\n")

# 手动注册的工具（原始方式）
manual_tools = []
manual_tools.extend(SkillManager._BROWSER_TOOLS)
manual_tools.extend(SkillManager._GUI_TOOLS)
manual_tools.extend(SkillManager._MEMORY_TOOLS)
manual_tools.extend(SkillManager._SYSTEM_TOOLS)
manual_tools.extend(SkillManager._VISION_TOOLS)

manual_names = {tool['function']['name'] for tool in manual_tools}

# 自动扫描的工具（新方式）
scanner = ToolScanner()
scanned_tools = scanner.scan_class(SkillManager, scan_parents=True)
scanned_names = {tool['function']['name'] for tool in scanned_tools}

# 统计数据
total = len(manual_names)
scanned = len(scanned_names)
coverage = (scanned / total * 100) if total > 0 else 0

print(f"📊 统计数据：")
print(f"   手动注册工具数：{total}")
print(f"   自动扫描工具数：{scanned}")
print(f"   覆盖率：{coverage:.1f}%\n")

if coverage >= 85:
    print("✅ 优秀！覆盖率超过85%，工具扫描器已经可以实际使用")
elif coverage >= 70:
    print("⚠️ 良好，但还有提升空间")
else:
    print("❌ 覆盖率过低，需要添加更多docstring")

# 显示成功扫描的工具（有docstring的）
successful = manual_names & scanned_names
print(f"\n✨ 成功自动扫描的工具 ({len(successful)}个)：")
print("   " + ", ".join(sorted(list(successful)[:10])))
if len(successful) > 10:
    print(f"   ... 还有 {len(successful)-10} 个工具")

# 显示未扫描到的工具（缺少docstring的）
missing = manual_names - scanned_names
if missing:
    print(f"\n⚠️ 未扫描到的工具 ({len(missing)}个)：")
    print("   " + ", ".join(sorted(list(missing))))
    print("\n💡 提示：这些工具可能：")
    print("   1. 缺少docstring（最常见原因）")
    print("   2. 是动态生成的工具（如set_reminder）")
    print("   3. 在父类或Mixin中定义")

# 具体展示改进的模块
print("\n" + "-"*60)
print("📚 已完善docstring的模块：")
print("-"*60)

improved_modules = {
    "browser.py": ["search_web", "read_web_page", "open_website", "browse_website"],
    "system.py": ["execute_shell", "control_volume", "take_note", "write_code", "open_tool", "run_code"],
    "gui.py": ["click_screen_text", "list_ui_elements", "click_by_description"],
    "memory.py": ["save_to_long_term_memory", "ingest_knowledge_file", "forget_knowledge", "forget_memory", "list_learned_files"]
}

total_improved = 0
for module, methods in improved_modules.items():
    found_methods = [m for m in methods if m in scanned_names]
    total_improved += len(found_methods)
    status = "✅" if len(found_methods) == len(methods) else "⚠️"
    print(f"\n{status} {module}: {len(found_methods)}/{len(methods)} 个方法被成功扫描")
    for method in methods:
        icon = "✅" if method in scanned_names else "❌"
        print(f"     {icon} {method}")

print(f"\n📈 总计：{total_improved} 个方法现在有完整docstring并能被自动扫描")

print("\n" + "="*60)
print("🎉 验证完成！")
print("="*60 + "\n")
