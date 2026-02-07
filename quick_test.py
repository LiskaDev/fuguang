"""YOLO-World 快速测试 - 记事本窗口识别"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fuguang.core.nervous_system import NervousSystem

print("=" * 60)
print("🧪 YOLO-World 快速测试")
print("=" * 60)
print("\n请确保记事本窗口已打开！\n")

# 初始化神经系统（会自动初始化 SkillManager）
print("📦 初始化扶光神经系统...")
nervous_system = NervousSystem()
skills = nervous_system.skills
print("✅ 初始化完成！\n")

# 测试案例
test_cases = [
    ("window", "识别记事本窗口"),
    ("close button", "识别关闭按钮"),
    ("text area", "识别文本编辑区"),
    ("menu bar", "识别菜单栏"),
]

results = []
for description, label in test_cases:
    print(f"【测试】{label}")
    print(f"描述词: '{description}'")
    
    result = skills.click_by_description(description, double_click=False)
    results.append((label, "✅" if "成功" in result or "找到" in result else "❌"))
    
    print(f"结果: {result}")
    print("-" * 60 + "\n")
    
    input("按回车继续下一个测试...")

# 总结
print("\n" + "=" * 60)
print("📊 测试总结")
print("=" * 60)
for label, status in results:
    print(f"{status} {label}")
