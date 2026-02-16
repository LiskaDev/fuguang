"""
工具自动扫描器 - v1.0
自动从Python类中扫描方法，生成OpenAI Function Calling需要的工具Schema

作者：扶光团队
版本：v1.0
创建日期：2026-02-16

功能：
- 自动扫描类的公开方法
- 从docstring提取描述
- 从类型注解推断参数类型
- 生成标准的工具Schema

好处：
✅ 新增工具：只需写函数+docstring，自动注册
✅ 修改工具：改函数就行，schema自动更新
✅ 删除工具：删函数就行，schema自动移除
✅ 减少90%重复代码
"""

import inspect
import logging
from typing import Any, Dict, List, get_type_hints

logger = logging.getLogger("Fuguang.ToolScanner")


class ToolScanner:
    """自动扫描Python类，生成工具Schema"""
    
    # 类型映射表：Python类型 → JSON Schema类型
    TYPE_MAPPING = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    
    def __init__(self):
        self.scanned_count = 0
        self.skipped_count = 0
        self.seen_methods = set()  # 跟踪已扫描的方法，避免重复
    
    def scan_class(self, cls: type, skip_private: bool = True, skip_magic: bool = True, scan_parents: bool = True) -> List[Dict]:
        """
        扫描一个类的所有方法，生成工具Schema列表
        
        Args:
            cls: 要扫描的类
            skip_private: 是否跳过私有方法（_开头）
            skip_magic: 是否跳过魔术方法（__开头__结尾）
            scan_parents: 是否递归扫描父类（适用于Mixin多继承）
        
        Returns:
            工具Schema列表，格式符合OpenAI Function Calling标准
        """
        tools = []
        self.scanned_count = 0
        self.skipped_count = 0
        self.seen_methods = set()
        
        logger.info(f"🔍 开始扫描类: {cls.__name__}")
        
        # 如果启用父类扫描，获取MRO（方法解析顺序）
        classes_to_scan = [cls]
        if scan_parents:
            # 获取所有父类（除了object）
            classes_to_scan = [c for c in cls.__mro__ if c != object]
            logger.info(f"   包含父类: {[c.__name__ for c in classes_to_scan[1:]]}")
        
        # 扫描所有相关类
        for current_class in classes_to_scan:
            for name, method in inspect.getmembers(current_class, inspect.isfunction):
                # 避免重复扫描（多继承可能导致同名方法）
                if name in self.seen_methods:
                    continue
                
                # 跳过私有方法
                if skip_private and name.startswith('_') and not name.startswith('__'):
                    self.skipped_count += 1
                    continue
                
                # 跳过魔术方法
                if skip_magic and name.startswith('__') and name.endswith('__'):
                    self.skipped_count += 1
                    continue
                
                # 读取docstring
                doc = inspect.getdoc(method)
                if not doc:
                    logger.debug(f"  ⚠️  {name} 缺少docstring，跳过")
                    self.skipped_count += 1
                    continue
                
                # 生成工具Schema
                try:
                    tool_schema = self._generate_schema(name, method, doc)
                    tools.append(tool_schema)
                    self.seen_methods.add(name)
                    self.scanned_count += 1
                    logger.debug(f"  ✅ {name}")
                except Exception as e:
                    logger.warning(f"  ❌ {name} 扫描失败: {e}")
                    self.skipped_count += 1
        
        logger.info(f"✅ 扫描完成: 成功 {self.scanned_count} 个，跳过 {self.skipped_count} 个")
        return tools
    
    def _generate_schema(self, func_name: str, method, docstring: str) -> Dict:
        """
        从单个方法生成工具Schema
        
        Args:
            func_name: 函数名
            method: 函数对象
            docstring: 函数文档字符串
        
        Returns:
            符合OpenAI标准的工具Schema字典
        """
        # 提取第一行作为简短描述
        lines = docstring.strip().split('\n')
        short_description = lines[0].strip()
        
        # 获取函数签名
        sig = inspect.signature(method)
        
        # 尝试获取类型注解
        try:
            type_hints = get_type_hints(method)
        except Exception as e:
            logger.debug(f"无法获取 {func_name} 的类型注解: {e}")
            type_hints = {}
        
        # 解析参数
        params = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            # 跳过self和cls
            if param_name in ['self', 'cls']:
                continue
            
            # 推断参数类型
            param_type = "string"  # 默认类型
            if param_name in type_hints:
                python_type = type_hints[param_name]
                # 处理泛型（如Optional[str]）
                if hasattr(python_type, '__origin__'):
                    python_type = python_type.__origin__
                param_type = self.TYPE_MAPPING.get(python_type, "string")
            elif param.annotation != inspect.Parameter.empty:
                param_type = self.TYPE_MAPPING.get(param.annotation, "string")
            
            # 从docstring提取参数描述（尝试查找Args部分）
            param_desc = self._extract_param_description(docstring, param_name)
            if not param_desc:
                param_desc = f"{param_name}参数"
            
            params[param_name] = {
                "type": param_type,
                "description": param_desc
            }
            
            # 判断是否必需（没有默认值的参数是必需的）
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        # 构建完整Schema
        tool_schema = {
            "type": "function",
            "function": {
                "name": func_name,
                "description": docstring,  # 完整docstring给AI参考
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": required
                }
            }
        }
        
        return tool_schema
    
    def _extract_param_description(self, docstring: str, param_name: str) -> str:
        """
        从docstring的Args部分提取参数描述
        
        格式示例：
        Args:
            file_path: 文件路径
            content: 文件内容
        """
        lines = docstring.split('\n')
        in_args_section = False
        
        for line in lines:
            stripped = line.strip()
            
            # 检测Args部分开始
            if stripped.lower() in ['args:', 'arguments:', 'parameters:']:
                in_args_section = True
                continue
            
            # 检测Args部分结束（遇到新的章节）
            if in_args_section and stripped and stripped.endswith(':') and not stripped.startswith(param_name):
                break
            
            # 在Args部分查找参数
            if in_args_section and param_name in stripped:
                # 格式：param_name: 描述 或 param_name (类型): 描述
                parts = stripped.split(':', 1)
                if len(parts) == 2:
                    desc = parts[1].strip()
                    # 移除可能的括号内容（如类型标注）
                    if '(' in parts[0]:
                        desc = parts[0].split('(')[0].strip() + ': ' + desc
                    return desc
        
        return ""
    
    def print_summary(self, tools: List[Dict]):
        """打印扫描结果摘要"""
        print("\n" + "="*60)
        print(f"🔧 工具自动扫描结果")
        print("="*60)
        print(f"✅ 成功扫描: {len(tools)} 个工具")
        print(f"⚠️  跳过: {self.skipped_count} 个方法")
        print("\n工具列表:")
        for i, tool in enumerate(tools, 1):
            func_info = tool['function']
            print(f"  {i}. {func_info['name']}")
            # 打印第一行描述
            desc = func_info['description'].split('\n')[0]
            print(f"     {desc[:70]}...")
        print("="*60 + "\n")


# 使用示例代码（供测试）
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 示例：扫描SkillManager
    print("🧪 工具扫描器测试\n")
    
    # 这里需要导入你的SkillManager类
    # from fuguang.core.skills import SkillManager
    # scanner = ToolScanner()
    # tools = scanner.scan_class(SkillManager)
    # scanner.print_summary(tools)
    
    print("ℹ️  提示：直接运行此文件仅供测试，实际使用请在brain.py中集成")
