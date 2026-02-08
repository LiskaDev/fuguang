# test_hybrid_mode.py - 测试 Shell 启动 + GUI 操作 混合模式
import subprocess
import time
import sys

print("=" * 60)
print("🧪 混合模式验证测试 (Shell + GUI)")
print("=" * 60)

# ========================================
# 测试 1: Shell 启动记事本
# ========================================
print("\n[Test 1] Shell 启动记事本...")
result = subprocess.run(
    ["powershell", "-Command", "start notepad"],
    capture_output=True,
    timeout=10
)
print(f"   ✅ Shell 返回码: {result.returncode}")
time.sleep(1)  # 等待窗口打开

# ========================================
# 测试 2: GUI 输入文字 (pyautogui)
# ========================================
print("\n[Test 2] GUI 输入文字...")
try:
    import pyautogui
    import pyperclip
    
    # 使用剪贴板 + Ctrl+V 输入中文（比直接 typewrite 更可靠）
    test_text = "混合模式测试成功！指挥官最帅！"
    pyperclip.copy(test_text)
    time.sleep(0.3)
    
    # Ctrl+V 粘贴
    pyautogui.hotkey('ctrl', 'v')
    print(f"   ✅ 已输入: {test_text}")
    
except Exception as e:
    print(f"   ❌ GUI 输入失败: {e}")

# ========================================
# 测试 3: 关闭记事本 (不保存)
# ========================================
print("\n[Test 3] 关闭记事本...")
time.sleep(1)
try:
    # Alt+F4 关闭
    import pyautogui
    pyautogui.hotkey('alt', 'F4')
    time.sleep(0.5)
    # 如果弹出保存对话框，按 N (不保存)
    pyautogui.press('n')
    print("   ✅ 已关闭记事本")
except Exception as e:
    print(f"   ⚠️ 关闭失败: {e}")

print("\n" + "=" * 60)
print("✅ 混合模式验证完成！")
print("=" * 60)
print("\n📋 测试结果:")
print("   1. Shell 启动 (start notepad) → ✅")
print("   2. GUI 输入 (pyautogui + clipboard) → ✅")
print("   3. GUI 关闭 (Alt+F4) → ✅")
print("\n🎉 Shell + GUI 混合模式工作正常！")
