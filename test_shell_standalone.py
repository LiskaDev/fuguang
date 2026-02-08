# test_shell_standalone.py - 独立测试 Shell 执行功能
import subprocess
import os
import platform

print("=" * 60)
print("⚡ God Mode Shell Execution Test (Standalone)")
print("=" * 60)

# === 模拟 execute_shell_command 逻辑 ===
def execute_shell_command(command, timeout=60):
    print(f"⚡ [Shell] 执行: {command}")
    
    # 黑名单
    forbidden_patterns = [
        "rm -rf", "rm -r /", "rmdir /s /q c:", 
        "del /s /q c:", "rd /s /q c:", "format ",
        "shutdown", "restart", "reboot", "poweroff",
    ]
    
    command_lower = command.lower()
    for pattern in forbidden_patterns:
        if pattern.lower() in command_lower:
            return f"❌ [安全拦截] 命令包含高危操作 '{pattern}'，已拒绝执行。"
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            timeout=timeout,
            cwd=os.path.expanduser("~")
        )
        
        try:
            stdout = result.stdout.decode('utf-8', errors='ignore').strip()
            stderr = result.stderr.decode('utf-8', errors='ignore').strip()
        except:
            stdout = result.stdout.decode('gbk', errors='ignore').strip()
            stderr = result.stderr.decode('gbk', errors='ignore').strip()
        
        output_parts = []
        if stdout:
            stdout_preview = stdout[:1500] + "...(已截断)" if len(stdout) > 1500 else stdout
            output_parts.append(f"【标准输出】:\n{stdout_preview}")
        if stderr:
            stderr_preview = stderr[:500] + "...(已截断)" if len(stderr) > 500 else stderr
            output_parts.append(f"【错误信息】:\n{stderr_preview}")
        
        output_msg = "\n\n".join(output_parts) if output_parts else ""
        
        if result.returncode == 0:
            return f"✅ 成功 (返回码: 0)\n\n{output_msg}" if output_msg else "✅ 成功，无输出"
        else:
            return f"❌ 失败 (返回码: {result.returncode})\n\n{output_msg}\n\n👉 请分析报错信息"
            
    except subprocess.TimeoutExpired:
        return f"❌ 超时 ({timeout}秒)"
    except Exception as e:
        return f"❌ 错误: {e}"

# === 测试 1: 成功执行 ===
print("\n[Test 1] 查看系统信息")
result = execute_shell_command("systeminfo | Select-String 'OS Name'")
print(result)

# === 测试 2: 查询 IP ===
print("\n" + "-" * 40)
print("[Test 2] 查询 IPv4 地址")
result = execute_shell_command("ipconfig | Select-String 'IPv4'")
print(result)

# === 测试 3: 安装不存在的库 (测试错误捕获) ===
print("\n" + "-" * 40)
print("[Test 3] 安装不存在的库 (错误测试)")
result = execute_shell_command("pip install non_existent_lib_xyz_123456")
print(result)

# === 测试 4: 黑名单拦截 ===
print("\n" + "-" * 40)
print("[Test 4] 黑名单拦截测试 (rm -rf)")
result = execute_shell_command("rm -rf /")
print(result)

# === 测试 5: 黑名单拦截 (shutdown) ===
print("\n" + "-" * 40)
print("[Test 5] 黑名单拦截测试 (shutdown)")
result = execute_shell_command("shutdown /s /t 0")
print(result)

# === 测试 6: 查看端口占用 ===
print("\n" + "-" * 40)
print("[Test 6] 查看 8080 端口占用")
result = execute_shell_command("netstat -ano | Select-String ':8080'")
print(result)

print("\n" + "=" * 60)
print("✅ 所有测试完成！")
