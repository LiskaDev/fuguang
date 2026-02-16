"""
简化版工具扫描器测试 - 只输出关键数据
"""
import os
import sys

# 设置环境变量禁止进度条
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'

# 重定向stderr来隐藏警告
import warnings
warnings.filterwarnings('ignore')

# 导入测试代码
from src.fuguang.core.tool_scanner import ToolScanner
from src.fuguang.core.skills import SkillManager

# 获取手动注册的工具schema（从类变量）
manual_tools = []
manual_tools.extend(SkillManager._BROWSER_TOOLS)
manual_tools.extend(SkillManager._GUI_TOOLS)
manual_tools.extend(SkillManager._MEMORY_TOOLS)
manual_tools.extend(SkillManager._SYSTEM_TOOLS)
manual_tools.extend(SkillManager._VISION_TOOLS)

manual_names = {tool['function']['name'] for tool in manual_tools}

# 扫描自动工具
scanner = ToolScanner()
scanned_tools = scanner.scan_class(SkillManager, scan_parents=True)
scanned_names = {tool['function']['name'] for tool in scanned_tools}

# 计算覆盖率
coverage = len(scanned_names) / len(manual_names) * 100 if manual_names else 0

# 输出结果
print(f"\n🤖 手动注册工具数: {len(manual_names)}")
print(f"🔧 自动扫描工具数: {len(scanned_names)}")
print(f"📈 覆盖率: {coverage:.1f}%")
print(f"\n新发现工具数: {len(scanned_names - manual_names)}")
print(f"未扫描到的工具数: {len(manual_names - scanned_names)}")
