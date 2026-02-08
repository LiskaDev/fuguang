# test_shell_god_mode.py - 测试上帝模式 Shell 执行
import sys
sys.path.insert(0, 'src')
from fuguang.core.skills import SkillManager

class MockMouth:
    def speak(self, text): print(f"[TTS] {text}")

print("=" * 60)
print("⚡ God Mode Shell Execution Test")
print("=" * 60)

# 初始化
skill = SkillManager(MockMouth())

# === 测试 1: 成功执行 ===
print("\n[Test 1] 查看当前目录")
result = skill.execute_shell_command("dir")
print(result[:500] + "..." if len(result) > 500 else result)

# === 测试 2: 查询 IP ===
print("\n" + "-" * 40)
print("[Test 2] 查询网络信息")
result = skill.execute_shell_command("ipconfig | Select-String 'IPv4'")
print(result)

# === 测试 3: 安装不存在的库 (测试错误捕获) ===
print("\n" + "-" * 40)
print("[Test 3] 安装不存在的库 (错误测试)")
result = skill.execute_shell_command("pip install non_existent_lib_123456")
print(result)

# === 测试 4: 黑名单拦截 ===
print("\n" + "-" * 40)
print("[Test 4] 黑名单拦截测试")
result = skill.execute_shell_command("rm -rf /")
print(result)

# === 测试 5: 另一个黑名单 ===
print("\n" + "-" * 40)
print("[Test 5] 黑名单拦截测试 2 (shutdown)")
result = skill.execute_shell_command("shutdown /s /t 0")
print(result)

print("\n" + "=" * 60)
print("✅ 测试完成！")
