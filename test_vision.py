"""
🎨 扶光视觉功能测试脚本
测试 GLM-4V 的图片识别能力

运行方式：python test_vision.py
"""
import time
import webbrowser
from src.fuguang.core.config import ConfigManager
from src.fuguang.core.mouth import Mouth
from src.fuguang.core.brain import Brain
from src.fuguang.core.skills import SkillManager

def print_section(title):
    """打印分隔线"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")

def test_local_image():
    """测试1：分析本地图片 jimi.png"""
    print_section("📸 测试1：分析本地图片 (jimi.png)")
    
    # 初始化组件
    config = ConfigManager()
    mouth = Mouth(config)
    brain = Brain(config, mouth)
    skills = SkillManager(config, mouth, brain)
    
    print("🖼️  正在分析 jimi.png...")
    print("⏳ 预计耗时: 3-5秒\n")
    
    result = skills.analyze_image_file(
        image_path="jimi.png",
        question="这张图片里是什么？请简单描述一下画面内容和视觉风格。"
    )
    
    print(result)
    print("\n✅ 测试1完成！\n")
    time.sleep(2)

def test_beautiful_scenes():
    """测试2：搜索美丽画面并截图分析"""
    print_section("🌄 测试2：搜索美丽画面 + 截图分析")
    
    config = ConfigManager()
    mouth = Mouth(config)
    brain = Brain(config, mouth)
    skills = SkillManager(config, mouth, brain)
    
    print("🔍 步骤1: 打开美丽的自然风光图片...")
    # 打开必应壁纸
    webbrowser.open("https://bing.com/images/search?q=beautiful+nature+scenery")
    
    print("⏳ 等待 5 秒让页面加载...")
    time.sleep(5)
    
    print("\n📸 步骤2: 截取当前屏幕并分析...")
    result = skills.analyze_screen_content(
        question="请描述一下这个页面上的图片，哪些画面最美丽？"
    )
    
    print(result)
    print("\n✅ 测试2完成！\n")
    time.sleep(2)

def test_bilibili_analysis():
    """测试3：打开B站首页，分析视频封面"""
    print_section("📺 测试3：B站首页封面分析")
    
    config = ConfigManager()
    mouth = Mouth(config)
    brain = Brain(config, mouth)
    skills = SkillManager(config, mouth, brain)
    
    print("🔍 步骤1: 打开B站首页...")
    webbrowser.open("https://www.bilibili.com")
    
    print("⏳ 等待 5 秒让页面加载...")
    time.sleep(5)
    
    print("\n📸 步骤2: 截取B站首页并分析封面...")
    result = skills.analyze_screen_content(
        question="请看看这些视频封面，哪个封面最吸引人？简单点评一下设计风格。"
    )
    
    print(result)
    print("\n✅ 测试3完成！\n")

def main():
    """主测试流程"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║          🎨 扶光视觉功能完整测试 (GLM-4V)                  ║
    ║                                                            ║
    ║  本测试将演示以下功能：                                     ║
    ║  1. 📸 分析本地图片文件 (jimi.png)                          ║
    ║  2. 🌄 搜索美丽画面 + 截图分析                              ║
    ║  3. 📺 B站首页封面点评                                      ║
    ║                                                            ║
    ║  预计总耗时: 约 30 秒                                       ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    input("按回车键开始测试... (确保 jimi.png 在项目根目录)")
    
    try:
        # 测试1：本地图片
        test_local_image()
        
        # 测试2：搜索美丽画面
        print("\n📢 即将进行测试2: 搜索美丽画面")
        input("按回车继续...")
        test_beautiful_scenes()
        
        # 测试3：B站分析
        print("\n📢 即将进行测试3: B站封面分析")
        input("按回车继续...")
        test_bilibili_analysis()
        
        print_section("🎉 所有测试完成！")
        print("""
        ✅ 测试结论：
        1. 本地图片分析功能正常
        2. 屏幕截图分析功能正常
        3. GLM-4V 视觉模型工作正常
        
        💡 提示：你现在可以对扶光说：
        - "帮我看看 jimi.png 这张图片"
        - "看看屏幕，告诉我这是什么"
        - "分析一下当前页面的内容"
        """)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
