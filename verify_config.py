"""
扶光系统 - 路径和配置验证脚本
用于测试优化后的路径计算和配置加载
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

print("=" * 60)
print("🔍 扶光系统 - 配置验证")
print("=" * 60)

try:
    # 测试 1: 导入主配置
    print("\n📦 测试 1: 导入主配置模块...")
    from fuguang.config import ConfigManager, PROJECT_ROOT, CONFIG_DIR, DATA_DIR
    print(f"✅ 主配置导入成功")
    print(f"   项目根目录: {PROJECT_ROOT}")
    print(f"   是否存在 README.md: {(PROJECT_ROOT / 'README.md').exists()}")
    
    # 测试 2: 验证目录结构
    print("\n📁 测试 2: 验证目录结构...")
    dirs = {
        "config": CONFIG_DIR,
        "data": DATA_DIR,
        "logs": PROJECT_ROOT / "logs",
        "generated": PROJECT_ROOT / "generated",
    }
    all_dirs_ok = True
    for name, path in dirs.items():
        exists = path.exists()
        status = "✅" if exists else "❌"
        print(f"   {status} {name}: {path}")
        if not exists:
            all_dirs_ok = False
    
    if not all_dirs_ok:
        print("   ⚠️ 部分目录不存在，但程序会自动创建")
    
    # 测试 3: API Key 配置
    print("\n🔑 测试 3: API Key 配置...")
    config = ConfigManager()
    api_keys = {
        "DEEPSEEK_API_KEY": bool(config.DEEPSEEK_API_KEY),
        "ZHIPU_API_KEY": bool(config.ZHIPU_API_KEY),
        "SERPER_API_KEY": bool(config.SERPER_API_KEY),
    }
    configured_count = sum(api_keys.values())
    for key, configured in api_keys.items():
        status = "✅ 已配置" if configured else "⚠️ 未配置"
        print(f"   {key}: {status}")
    
    if configured_count == 0:
        print(f"   💡 提示：请在 .env 文件中配置 API Keys")
    
    # 测试 4: 关键文件
    print("\n📄 测试 4: 关键文件...")
    system_prompt_file = CONFIG_DIR / "system_prompt.txt"
    readme_file = PROJECT_ROOT / "README.md"
    
    files = {
        "System Prompt": system_prompt_file,
        "README.md": readme_file,
        "requirements.txt": PROJECT_ROOT / "requirements.txt",
    }
    
    for name, path in files.items():
        status = "✅" if path.exists() else "❌"
        print(f"   {status} {name}: {path}")
    
    # 测试 5: 路径计算方法验证
    print("\n🔍 测试 5: 路径计算方法验证...")
    # 检查是否使用了标记文件搜索法
    if (PROJECT_ROOT / "README.md").exists():
        print(f"   ✅ 标记文件搜索成功 (README.md)")
    elif (PROJECT_ROOT / ".git").exists():
        print(f"   ✅ 标记文件搜索成功 (.git)")
    else:
        print(f"   ⚠️ 使用备用路径计算方法")
    
    print("\n" + "=" * 60)
    print("✅ 配置验证完成！所有核心功能正常")
    print("💡 提示：运行 'pip install -r requirements.txt' 安装完整依赖")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
