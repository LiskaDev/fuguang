"""
工具扫描器测试脚本
验证自动扫描功能是否正常工作
"""

import sys
import os

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fuguang.core.tool_scanner import ToolScanner
from fuguang.core.skills import SkillManager
from fuguang.core.config import ConfigManager
from fuguang.core.mouth import Mouth
from fuguang.core.brain import Brain

print("🧪 工具自动扫描测试\n")
print("="*60)

# 1. 初始化必要组件
print("\n📦 初始化组件...")
config = ConfigManager()
mouth = Mouth(config)
brain = Brain(config, mouth)

# 2. 创建SkillManager实例
print("📦 创建SkillManager...")
skills = SkillManager(config, mouth, brain)

# 3. 扫描工具
print("\n🔍 开始自动扫描...\n")
scanner = ToolScanner()
auto_tools = scanner.scan_class(type(skills))

# 4. 打印结果
scanner.print_summary(auto_tools)

# 5. 对比手动注册的工具
print("📊 对比分析：")
print("-"*60)

# 获取手动定义的工具（当前方式）
manual_tools = skills.get_tools_schema()

print(f"🤖 手动注册工具数: {len(manual_tools)}")
print(f"🔧 自动扫描工具数: {len(auto_tools)}")
print(f"📈 覆盖率: {len(auto_tools)/len(manual_tools)*100:.1f}%")

# 找出自动扫描发现的新工具（手动注册中没有的）
manual_names = {t['function']['name'] for t in manual_tools}
auto_names = {t['function']['name'] for t in auto_tools}

new_discovered = auto_names - manual_names
missing = manual_names - auto_names

if new_discovered:
    print(f"\n✨ 自动发现的新工具 ({len(new_discovered)}个):")
    for name in sorted(new_discovered):
        print(f"  + {name}")
else:
    print("\n✅ 没有发现新工具（所有工具都已手动注册）")

if missing:
    print(f"\n⚠️  手动注册但未被扫描到的工具 ({len(missing)}个):")
    for name in sorted(missing):
        print(f"  - {name}")
    print("\n💡 提示：这些工具可能是动态生成的（如set_reminder）")

print("\n" + "="*60)
print("🎉 测试完成！")
print("\n建议：")
print("  1. 如果自动扫描的工具数 >= 手动注册的90%，说明扫描器工作正常")
print("  2. 未来添加新工具时，只需写好docstring，无需手动注册Schema")
print("  3. 可以在brain.py中使用scanner.scan_class()替代手动定义")
