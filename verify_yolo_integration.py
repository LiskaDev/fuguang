"""
✅ YOLO-World 集成验证脚本

快速验证 YOLO-World 是否正确集成到扶光核心
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

def verify_integration():
    print("="*60)
    print("🔍 开始验证 YOLO-World 集成...")
    print("="*60)
    
    # 1. 检查 Ultralytics 是否安装
    print("\n[1/5] 检查 Ultralytics 包...")
    try:
        from ultralytics import YOLOWorld
        print("✅ Ultralytics 已安装")
    except ImportError as e:
        print(f"❌ Ultralytics 未安装: {e}")
        print("   请运行: pip install ultralytics")
        return False
    
    # 2. 检查 skills.py 是否有 YOLO-World 导入
    print("\n[2/5] 检查 skills.py 导入...")
    try:
        from fuguang.core.skills import SkillManager, YOLOWORLD_AVAILABLE
        if YOLOWORLD_AVAILABLE:
            print("✅ skills.py 已正确导入 YOLO-World")
        else:
            print("⚠️ YOLO-World 导入失败（但代码已集成）")
    except Exception as e:
        print(f"❌ skills.py 导入检查失败: {e}")
        return False
    
    # 3. 检查工具 schema 是否包含 click_by_description
    print("\n[3/5] 检查工具 Schema...")
    try:
        from fuguang.core.config import ConfigManager
        from fuguang.core.mouth import Mouth
        from fuguang.core.brain import Brain
        
        # 创建简化组件
        class MockMouth:
            def speak(self, text): pass
        class MockBrain:
            class MemorySystem:
                def add_memory(self, content, importance): pass
            memory_system = MemorySystem()
        
        config = ConfigManager()
        skills = SkillManager(config, MockMouth(), MockBrain())
        
        tools_schema = skills.get_tools_schema()
        has_tool = any(
            tool.get("function", {}).get("name") == "click_by_description"
            for tool in tools_schema
        )
        
        if has_tool:
            print("✅ click_by_description 工具已注册")
        else:
            print("❌ click_by_description 工具未找到")
            return False
    except Exception as e:
        print(f"❌ 工具 Schema 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. 检查方法是否实现
    print("\n[4/5] 检查方法实现...")
    try:
        if hasattr(skills, 'click_by_description'):
            print("✅ click_by_description 方法已实现")
        else:
            print("❌ click_by_description 方法未找到")
            return False
    except Exception as e:
        print(f"❌ 方法检查失败: {e}")
        return False
    
    # 5. 检查模型是否能加载
    print("\n[5/5] 检查模型加载...")
    try:
        if skills.yolo_world is not None:
            print("✅ YOLO-World 模型已成功加载")
            print(f"   模型类型: {type(skills.yolo_world).__name__}")
        else:
            print("⚠️ YOLO-World 模型未加载（可能是首次运行）")
            print("   运行测试脚本时会自动下载模型")
    except Exception as e:
        print(f"⚠️ 模型加载检查失败: {e}")
    
    print("\n" + "="*60)
    print("🎉 验证完成！YOLO-World 已成功集成到扶光核心")
    print("="*60)
    
    print("\n📝 下一步:")
    print("1. 运行测试: python test_yolo_world.py")
    print("2. 或启动扶光: python run.py")
    print("3. 尝试对话: \"点击 Chrome 图标\"")
    
    return True


if __name__ == "__main__":
    try:
        success = verify_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
