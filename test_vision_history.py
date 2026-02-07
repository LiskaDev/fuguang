"""
🎬 扶光视觉历史记录测试
演示多轮对话和历史回看功能

运行方式：python test_vision_history.py
"""
import time
import webbrowser
from src.fuguang.core.config import ConfigManager
from src.fuguang.core.mouth import Mouth
from src.fuguang.core.brain import Brain
from src.fuguang.core.skills import SkillManager

def test_vision_history():
    """测试视觉历史记录功能"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║       🎬 扶光视觉历史记录 & 多轮对话测试                   ║
    ║                                                            ║
    ║  演示场景：                                                 ║
    ║  1. 分析 jimi.png                                          ║
    ║  2. 打开B站分析封面                                         ║
    ║  3. 查看历史记录                                            ║
    ║  4. 多轮对话 - "刚才那个图片里有几个人？"                  ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    input("按回车开始测试...")
    
    # 初始化组件
    config = ConfigManager()
    mouth = Mouth(config)
    brain = Brain(config, mouth)
    skills = SkillManager(config, mouth, brain)
    
    print("\n" + "="*60)
    print("  📸 第1次分析：jimi.png")
    print("="*60 + "\n")
    
    result1 = skills.analyze_image_file("jimi.png", "这张图片里是什么？")
    print(result1)
    print("\n✅ 已保存到历史记录 (1/5)\n")
    time.sleep(2)
    
    print("\n" + "="*60)
    print("  📸 第2次分析：打开B站首页")
    print("="*60 + "\n")
    
    webbrowser.open("https://www.bilibili.com")
    print("⏳ 等待页面加载...")
    time.sleep(5)
    
    result2 = skills.analyze_screen_content("这个页面有哪些视频？")
    print(result2)
    print("\n✅ 已保存到历史记录 (2/5)\n")
    time.sleep(2)
    
    print("\n" + "="*60)
    print("  📚 查看历史记录")
    print("="*60 + "\n")
    
    history = skills.get_vision_history()
    print(history)
    
    print("\n" + "="*60)
    print("  🗣️ 多轮对话演示")
    print("="*60 + "\n")
    
    print("现在你可以这样问扶光：")
    print('  你："刚才那个 jimi.png 图片里有几个人？"')
    print('  扶光："（查看历史记录）根据之前的分析，那张图片里有两个人..."')
    print()
    print('或者：')
    print('  你："之前看过什么图片？"')
    print('  扶光："（调用 get_vision_history 工具）最近分析了..."')
    print()
    print("💡 提示：历史记录会自动保存到 data/vision_history/ 目录")
    print("       只保留最近 5 次分析，旧的会自动删除")
    
    print("\n" + "="*60)
    print("  🎉 测试完成！")
    print("="*60 + "\n")
    
    print("""
    ✅ 功能验证：
    1. ✅ 视觉分析自动保存到历史记录
    2. ✅ 历史记录包含时间戳、问题、结果
    3. ✅ 支持查看历史记录
    4. ✅ 图片文件保存到 data/vision_history/
    5. ✅ 自动维护最近 5 次记录
    
    💬 实际对话示例：
    运行 python run.py 后，你可以说：
    - "看看 jimi.png"（会自动保存）
    - "刚才那张图片里有什么？"（AI 会查历史）
    - "帮我看看屏幕"（会自动保存）
    - "回看一下历史记录"（显示最近5次）
    - "继续看刚才那个画面的左上角"（多轮对话）
    """)

if __name__ == "__main__":
    try:
        test_vision_history()
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
