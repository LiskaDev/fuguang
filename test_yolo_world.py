"""
🧪 YOLO-World 视觉识别功能测试脚本

测试扶光的新能力：通过自然语言描述识别并点击 UI 元素

安装依赖:
    pip install ultralytics

测试前准备:
1. 确保屏幕上有要测试的元素（如打开浏览器显示图标）
2. 调整好窗口位置，确保目标可见
3. 测试时不要移动鼠标（观察AI自动操作）
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from fuguang.core.config import ConfigManager
from fuguang.core.mouth import Mouth
from fuguang.core.brain import Brain
from fuguang.core.skills import SkillManager

def test_visual_recognition():
    """测试 YOLO-World 视觉识别功能"""
    
    print("""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║         🧪 YOLO-World 视觉识别功能测试                        ║
║                                                                ║
║  测试内容:                                                     ║
║  1. ✅ 模型加载验证                                           ║
║  2. ✅ 图标识别（Chrome/微信/VSCode）                        ║
║  3. ✅ 按钮识别（红色按钮/关闭按钮）                         ║
║  4. ✅ 输入框识别（搜索框）                                  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # 初始化组件
    print("\n📦 初始化组件...")
    config = ConfigManager()
    config.ENABLE_GUI_CONTROL = True  # 启用 GUI 控制
    
    # 创建简化的 Mouth 和 Brain（仅测试用）
    class MockMouth:
        def speak(self, text):
            print(f"🔊 语音: {text}")
    
    class MockBrain:
        class MemorySystem:
            def add_memory(self, content, importance):
                pass
        memory_system = MemorySystem()
    
    mouth = MockMouth()
    brain = MockBrain()
    
    # 初始化 SkillManager（会自动加载 YOLO-World）
    print("🚀 加载 YOLO-World 模型...")
    skills = SkillManager(config, mouth, brain)
    
    if not skills.yolo_world:
        print("❌ YOLO-World 模型加载失败！")
        print("   请运行: pip install ultralytics")
        return
    
    print("✅ YOLO-World 模型加载成功！\n")
    
    # 测试用例
    test_cases = [
        {
            "name": "桌面图标识别",
            "description": "chrome icon",
            "hint": "请确保桌面上有 Chrome 图标可见",
            "double_click": False
        },
        {
            "name": "按钮识别（通用）",
            "description": "close button",
            "hint": "请打开一个窗口（如记事本），确保右上角关闭按钮可见",
            "double_click": False
        },
        {
            "name": "搜索框识别",
            "description": "search box",
            "hint": "请打开浏览器或文件管理器，确保搜索框可见",
            "double_click": False
        },
        {
            "name": "红色元素识别",
            "description": "red icon",
            "hint": "请确保屏幕上有红色图标或按钮可见",
            "double_click": False
        }
    ]
    
    print("="*60)
    print("开始测试用例执行\n")
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n【测试 {i}/{len(test_cases)}】{test_case['name']}")
        print(f"描述词: {test_case['description']}")
        print(f"提示: {test_case['hint']}")
        
        # 等待用户确认
        input("\n按回车开始测试（或输入 's' 跳过）> ")
        
        # 执行测试
        print(f"\n🔍 正在识别: {test_case['description']}...")
        result = skills.click_by_description(
            test_case['description'],
            test_case['double_click']
        )
        
        # 记录结果
        success = "✅" in result
        results.append({
            "test": test_case['name'],
            "success": success,
            "result": result
        })
        
        print(f"\n结果: {result}")
        print("-"*60)
    
    # 总结报告
    print("\n" + "="*60)
    print("📊 测试总结报告\n")
    
    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)
    
    print(f"总测试数: {total_count}")
    print(f"成功: {success_count}")
    print(f"失败: {total_count - success_count}")
    print(f"成功率: {success_count/total_count*100:.1f}%\n")
    
    print("详细结果:")
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['test']}")
        if not r['success']:
            print(f"   原因: {r['result']}")
    
    print("\n" + "="*60)
    
    if success_count == total_count:
        print("🎉 所有测试通过！扶光现在拥有真正的视觉能力了！")
    elif success_count > 0:
        print("⚠️ 部分测试通过。建议:")
        print("   1. 确保目标元素在屏幕上清晰可见")
        print("   2. 尝试调整描述词（更具体或更通用）")
        print("   3. 检查光照条件（避免反光或过暗）")
    else:
        print("❌ 所有测试失败。可能原因:")
        print("   1. YOLO-World 模型未正确加载")
        print("   2. 目标元素不在屏幕上")
        print("   3. 描述词不准确")


def interactive_test():
    """交互式测试：用户自定义描述词"""
    
    print("\n" + "="*60)
    print("🎮 进入交互式测试模式")
    print("="*60)
    
    # 初始化组件
    config = ConfigManager()
    config.ENABLE_GUI_CONTROL = True
    
    class MockMouth:
        def speak(self, text):
            print(f"🔊 语音: {text}")
    
    class MockBrain:
        class MemorySystem:
            def add_memory(self, content, importance):
                pass
        memory_system = MemorySystem()
    
    mouth = MockMouth()
    brain = MockBrain()
    skills = SkillManager(config, mouth, brain)
    
    if not skills.yolo_world:
        print("❌ YOLO-World 模型未加载，无法进行测试")
        return
    
    print("\n提示:")
    print("- 输入英文描述词（如 'red button', 'chrome icon'）")
    print("- 输入 'quit' 或 'q' 退出")
    print("- 输入 'help' 查看常用描述词示例\n")
    
    while True:
        description = input("\n👉 请输入描述词: ").strip()
        
        if description.lower() in ['quit', 'q', 'exit']:
            print("👋 再见！")
            break
        
        if description.lower() == 'help':
            print("\n常用描述词示例:")
            print("  图标类: chrome icon, wechat icon, vscode icon")
            print("  按钮类: close button, minimize button, play button")
            print("  输入框: search box, text input, input field")
            print("  颜色类: red button, blue icon, green circle")
            print("  组合: red close button, large play button")
            continue
        
        if not description:
            print("⚠️ 请输入有效的描述词")
            continue
        
        # 执行识别
        result = skills.click_by_description(description, double_click=False)
        print(f"\n结果: {result}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="YOLO-World 视觉识别功能测试")
    parser.add_argument(
        '--mode',
        choices=['auto', 'interactive'],
        default='auto',
        help="测试模式: auto=自动测试套件, interactive=交互式测试"
    )
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'auto':
            test_visual_recognition()
        else:
            interactive_test()
    
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试已中断")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
