"""
Standalone Web UI test — starts just the WebBridge with mock Brain/Skills
so we can test the frontend without needing the full NervousSystem.
"""
import sys
import os
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Set env vars
os.environ.setdefault("WEB_UI_ENABLED", "true")
os.environ.setdefault("WEB_UI_PASSWORD", "fuguang")
os.environ.setdefault("WEB_UI_PORT", "7860")
os.environ.setdefault("DATA_DIR", str(PROJECT_ROOT / "data"))


class MockConfig:
    WEB_UI_ENABLED = True
    WEB_UI_PORT = 7860
    WEB_UI_PASSWORD = "fuguang"
    WEB_UI_JWT_SECRET = "test_secret_key_1234567890"
    DATA_DIR = str(PROJECT_ROOT / "data")


class MockBrain:
    def get_system_prompt(self):
        return "你是扶光, AI 助手。"

    def chat(self, user_input, system_content=None, tools_schema=None, tool_executor=None):
        # Echo back with markdown to test rendering
        return (
            f"收到你的消息！这是测试回复。\n\n"
            f"## 你说的是\n\n"
            f"> {user_input}\n\n"
            f"### 代码示例\n\n"
            f"```python\n"
            f"print('Hello from 扶光!')\n"
            f"```\n\n"
            f"- 项目1\n"
            f"- 项目2\n"
            f"- **粗体** 和 *斜体*\n"
        )


class MockMemory:
    def get_memory_context(self, query, n_results=3):
        return ""


class MockSkills:
    memory = MockMemory()

    def get_tools_schema(self):
        return []

    def execute_tool(self, name, args):
        return f"Mock tool result for {name}"


if __name__ == "__main__":
    print("🚀 启动 Web UI 独立测试（Mock 模式）...")
    print("   密码: fuguang")
    print("   地址: http://localhost:7860")
    print("   按 Ctrl+C 退出")

    # Ensure data dir
    (PROJECT_ROOT / "data").mkdir(exist_ok=True)

    config = MockConfig()
    brain = MockBrain()
    skills = MockSkills()

    from fuguang.core.web_bridge import WebBridge

    wb = WebBridge(config, brain, skills)
    wb.start()

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wb.stop()
        print("\n👋 已停止")
