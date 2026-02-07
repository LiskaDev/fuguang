
import sys
import os
import time

# Add src to path
sys.path.insert(0, 'src')

# Import core modules
from fuguang.core.config import ConfigManager
from fuguang.core.mouth import Mouth
from fuguang.core.brain import Brain
from fuguang.core.skills import SkillManager

# Mock Mouth
class MockMouth:
    def speak(self, text):
        print(f"🔊 [Mouth]: {text}")

def run_test():
    print("🚀 Starting Vision Trinity Test (OCR + YOLO + GLM)...")
    
    # Initialize Core
    config = ConfigManager()
    mouth = MockMouth()
    brain = Brain(config, mouth)
    skills = SkillManager(config, mouth, brain)
    
    # Get components
    sys_prompt = brain.get_system_prompt()
    tools_schema = skills.get_tools_schema()
    tool_executor = skills.execute_tool
    
    print("\n" + "="*50)
    print("🧪 Test 1: Open App & Type (Base Interaction)")
    prompt1 = "请打开记事本，然后输入 'Hello Vision Trinity!'"
    print(f"👤 User: {prompt1}")
    response1 = brain.chat(prompt1, sys_prompt, tools_schema, tool_executor)
    print(f"🤖 AI Response: {response1}")
    
    time.sleep(3) # Wait for typing
    
    print("\n" + "="*50)
    print("🧪 Test 2: OCR Click ('文件' Menu)")
    # This tests EasyOCR finding text "文件"
    prompt2 = "点击 '文件' 菜单。"
    print(f"👤 User: {prompt2}")
    try:
        response2 = brain.chat(prompt2, sys_prompt, tools_schema, tool_executor)
        print(f"🤖 AI Response: {response2}")
    except Exception as e:
        print(f"❌ Error: {e}")

    time.sleep(2)

    print("\n" + "="*50)
    print("🧪 Test 3: GLM-4V Analysis (Reading Screen)")
    prompt3 = "帮我看看屏幕上记事本里写了什么内容？"
    print(f"👤 User: {prompt3}")
    try:
        response3 = brain.chat(prompt3, sys_prompt, tools_schema, tool_executor)
        print(f"🤖 AI Response: {response3}")
    except Exception as e:
        print(f"❌ Error: {e}")
        
    time.sleep(2)
    
    print("\n" + "="*50)
    print("🧪 Test 4: YOLO Click (Close Button)")
    # YOLO-World "close button"
    prompt4 = "点击右上角的关闭按钮 (close button)。"
    print(f"👤 User: {prompt4}")
    try:
        response4 = brain.chat(prompt4, sys_prompt, tools_schema, tool_executor)
        print(f"🤖 AI Response: {response4}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "="*50)
    print("✅ Test Sequence Finished.")

if __name__ == "__main__":
    run_test()
