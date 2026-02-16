
import json
import os
import sys
import time
import datetime
import logging
import httpx
import threading
from openai import OpenAI
from .config import ConfigManager
from .mouth import Mouth
from .. import memory as fuguang_memory

logger = logging.getLogger("Fuguang")

class Brain:
    """
    思考与记忆角色
    职责：AI 客户端、聊天历史、记忆、System Prompt
    """

    MAX_HISTORY = 20
    QUICK_LOCAL_TRIGGERS = ["几点", "时间", "几号", "日期", "电量", "状态"]

    def __init__(self, config: ConfigManager, mouth: Mouth):
        self.config = config
        self.mouth = mouth

        # AI 客户端
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0)
        )

        # 长期记忆系统
        self.memory_system = fuguang_memory.MemorySystem()

        # 短期对话历史
        self.chat_history = []

        # 状态
        self.IS_CREATION_MODE = False
        
        # 🔥 性能监控系统
        self.performance_log = []  # 记录每次任务的性能数据
        self.system_hints = []  # 存储给AI的系统提示（如性能警告）

    def load_memory(self) -> dict:
        """加载短期记忆"""
        if not self.config.MEMORY_FILE.exists():
            return {"user_profile": {}, "short_term_summary": "暂无记录"}
        try:
            with open(self.config.MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"user_profile": {}, "short_term_summary": "文件损坏"}

    def save_memory(self, memory_data: dict):
        """保存短期记忆"""
        try:
            with open(self.config.MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=4)
            logger.info("💾 记忆已保存")
        except Exception as e:
            logger.error(f"记忆保存失败: {e}")

    def get_system_prompt(self, dynamic_context: dict = None) -> str:
        """
        生成动态 System Prompt
        
        Args:
            dynamic_context: 实时感知数据，包含:
                - app: 当前活动窗口标题
                - clipboard: 剪贴板内容
                - user_present: 用户是否在座（可选）
        """
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.datetime.now().weekday()]
        current_date = f"{datetime.datetime.now().strftime('%Y-%m-%d')} {weekday}"
        mode_status = "🔓已解锁" if self.IS_CREATION_MODE else "🔒已锁定"

        memory = self.load_memory()
        user_profile = json.dumps(memory.get("user_profile", {}), ensure_ascii=False)
        summary = memory.get("short_term_summary", "暂无")

        # 构建感知信息（如果提供了）
        perception_section = ""
        if dynamic_context:
            app_name = dynamic_context.get("app", "未知")
            clipboard = dynamic_context.get("clipboard", "无")
            user_present = dynamic_context.get("user_present", None)
            visual_status = ""
            if user_present is not None:
                visual_status = "指挥官在座位上" if user_present else "座位无人"
            
            perception_section = f"""

【实时感知状态】
- 用户正在操作: {app_name}
- 剪贴板内容: {clipboard}
{f'- 视觉状态: {visual_status}' if visual_status else ''}
（当用户问"这个"、"这段代码"、"帮我看看"时，指的就是剪贴板内容；当用户问"我在干嘛"时请根据当前窗口回答）
"""

        try:
            with open(self.config.SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                template = f.read()
            prompt = template.format(
                current_time=current_time,
                current_date=current_date,
                mode_status=mode_status,
                history_summary=f"【用户档案】{user_profile}\n【上次话题摘要】{summary}"
            )
            # 追加感知信息
            return prompt + perception_section
        except Exception:
            return f"你是沈扶光，说话简洁。[Neutral]{perception_section}"

    def trim_history(self):
        """修剪对话历史，防止过长"""
        if len(self.chat_history) <= self.MAX_HISTORY * 2:
            return

        target_len = self.MAX_HISTORY * 2 - 10
        start_idx = max(0, len(self.chat_history) - target_len)  # [修复L-5] 防止负索引
        for i in range(start_idx, len(self.chat_history)):
            if i >= 0 and self.chat_history[i]["role"] == "user":
                self.chat_history = self.chat_history[i:]
                return

        self.chat_history = self.chat_history[-(self.MAX_HISTORY * 2):]

    def should_auto_respond(self, text: str) -> bool:
        """判断是否应该自动响应本地指令"""
        return any(trigger in text for trigger in self.QUICK_LOCAL_TRIGGERS)

    def summarize_and_exit(self):
        """整理记忆并退出"""
        logger.info("正在整理今日记忆...")
        self.mouth.speak("指挥官，正在同步记忆数据...")

        if len(self.chat_history) < 2:
            self.mouth.speak("晚安。")
            sys.exit(0)  # [修复H-1] 使用 sys.exit 替代 os._exit，允许 finally/atexit 清理

        conversation_text = ""
        for msg in self.chat_history:
            role = "阿鑫" if msg["role"] == "user" else "扶光"
            conversation_text += f"{role}: {msg['content']}\n"

        try:
            summary_prompt = [
                {"role": "system", "content": "请简要总结以下对话中的关键信息。100字以内。"},
                {"role": "user", "content": conversation_text}
            ]
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=summary_prompt,
                max_tokens=200,
                temperature=0.5
            )
            new_summary = response.choices[0].message.content
            logger.info(f"📝 今日日记: {new_summary}")

            mem = self.load_memory()
            old = mem.get("short_term_summary", "")
            mem["short_term_summary"] = f"{new_summary} | (旧: {old[:50]}...)"
            self.save_memory(mem)

        except Exception as e:
            logger.error(f"总结失败: {e}")

        self.mouth.speak("记忆同步完成，晚安。")
        time.sleep(1)
        sys.exit(0)  # [修复H-1] 使用 sys.exit 替代 os._exit

    # ========================
    # 🧠 核心对话方法 (Function Calling)
    # ========================
    def chat(self, user_input: str, system_content: str, tools_schema: list, tool_executor) -> str:
        """
        核心对话方法：支持 Function Calling (工具调用)
        
        Args:
            user_input: 用户输入
            system_content: 完整的 System Prompt（包含记忆）
            tools_schema: 工具定义列表
            tool_executor: 工具执行函数 (func_name, func_args) -> result
            
        Returns:
            AI 的最终回复文本
        """
        # 🔥 性能监控：记录开始时间
        start_time = time.time()
        tool_calls_list = []  # 记录本次调用的所有工具
        
        # 注入系统提示（如性能警告）
        if self.system_hints:
            hints_text = "\n".join(self.system_hints)
            system_content += f"\n\n【⚠️ 系统提示】\n{hints_text}\n"
            self.system_hints.clear()  # 清空提示，只显示一次
        
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": user_input})
        
        # [调整] 增加思考轮次上限，以支持复杂的连续任务 (如: 打开网页 -> 截图 -> 分析 -> 总结)
        max_iterations = 15
        iteration = 0
        ai_reply = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"🤖 AI思考轮次: {iteration}")
            
            # 调用 DeepSeek
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                stream=False,
                temperature=0.8,
                max_tokens=4096
            )
            
            message = response.choices[0].message
            
            # 检查是否需要调用工具
            if message.tool_calls:
                logger.info(f"🔧 AI请求使用工具: {len(message.tool_calls)} 个")
                
                # 把 AI 的工具调用意图加入对话历史
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in message.tool_calls
                    ]
                })
                
                # 执行每个工具调用
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    
                    # [修复C-2] 防止 API 返回畸形 JSON 导致崩溃
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"工具参数解析失败: {func_name}, 原始参数: {tool_call.function.arguments}, 错误: {e}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"参数解析错误: {e}"
                        })
                        continue
                    
                    logger.info(f"📞 调用工具: {func_name}")
                    tool_calls_list.append(func_name)  # 🔥 记录工具调用
                    result = tool_executor(func_name, func_args)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                
                # 继续下一轮，让 AI 根据工具结果生成回复
                continue
            
            else:
                # 没有工具调用，直接获取回复
                ai_reply = message.content
                break
        
        else:
            # 超过最大迭代次数
            ai_reply = "指挥官，这个问题有点复杂，我需要更多时间思考..."
        
        # 🔥 性能监控：记录结束时间和统计数据
        elapsed_time = time.time() - start_time
        tool_count = len(tool_calls_list)
        
        # 记录到性能日志（保留最近20条）
        self.performance_log.append({
            "task": user_input[:50],  # 截取前50字符
            "time": round(elapsed_time, 2),
            "steps": tool_count,
            "tools_used": tool_calls_list,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        })
        if len(self.performance_log) > 20:
            self.performance_log.pop(0)  # 移除最旧的记录
        
        logger.info(f"⏱️ [性能] 本次任务耗时: {elapsed_time:.2f}秒，调用工具: {tool_count}个")
        
        # 🔥 性能警告：如果太慢或调用太多工具，给AI发送优化建议
        if elapsed_time > 10 and tool_count > 3:
            warning = f"""⚠️ 性能警告：上一个任务耗时 {elapsed_time:.1f}秒，调用了 {tool_count} 个工具。

请反思：
- 是否有更快的方法？（如用 create_file_directly 代替打开记事本）
- 是否可以用快捷键代替点击菜单？（如 Ctrl+S 保存）
- 是否可以合并多个操作为一个工具调用？

记住：用户要的是结果，不是过程。优先使用【工具优先级1-2】的方法。

最近调用的工具：{', '.join(tool_calls_list[-5:])}"""
            self.system_hints.append(warning)  # 下次对话时自动注入
            logger.warning(f"🐢 性能警告已生成，将在下次对话时提醒AI优化")
        
        # 更新对话历史
        self.chat_history.append({"role": "user", "content": user_input})
        self.chat_history.append({"role": "assistant", "content": ai_reply})
        self.trim_history()
        
        # 保存交互时间
        current_mem = self.load_memory()
        current_mem["last_interaction"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save_memory(current_mem)
        
        # 潜意识记忆：后台分析对话
        self.analyze_and_store_memory(user_input, ai_reply)
        
        return ai_reply

    # ========================
    # 🧠 潜意识记忆系统 (Subconscious Memory)
    # ========================
    def analyze_and_store_memory(self, user_text: str, ai_reply: str):
        """
        让 AI 反思刚才的对话，提取有价值的记忆。
        在后台线程运行，不卡住对话。
        """
        def _background_task():
            # 1. 构造专门用来提取记忆的 Prompt
            reflection_prompt = f"""请分析以下对话，提取关于用户的【长期事实】或【重要偏好】。

用户说：{user_text}
AI回复：{ai_reply}

【提取规则】
- 只提取可以长期记住的事实（如：用户的计划、偏好、厌恶、习惯、人际关系等）
- 不要提取临时性信息（如：今天天气、正在做的事）
- 如果没有值得记忆的信息，请直接输出 None

【输出要求】
如果有值得记忆的信息，严格按照以下 JSON 格式输出（不要Markdown，不要废话）：
{{"content": "陈述句格式的事实", "importance": 1到5的整数}}

importance 等级说明：
- 5: 核心身份/永久偏好（如：名字、MBTI、绝对禁忌）
- 4: 重要计划/关系（如：考驾照、女朋友叫什么）
- 3: 一般偏好（如：喜欢吃甜食）
- 2: 临时状态（如：最近在学Python）
- 1: 琐碎信息

示例输出：
{{"content": "指挥官打算下个月考驾照", "importance": 4}}
"""
            
            try:
                # 2. 调用 LLM（非流式，解析 JSON）
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": reflection_prompt}],
                    max_tokens=150,
                    temperature=0.3  # 低温度，更稳定
                )
                result = response.choices[0].message.content.strip()
                
                # 3. 检查是否有值得记忆的内容
                if "None" in result or "none" in result or "{" not in result:
                    return  # 没什么好记的
                
                # 4. 解析 JSON
                # 清洗可能的 Markdown 包裹
                clean_json = result.replace("```json", "").replace("```", "").strip()
                memory_item = json.loads(clean_json)
                
                content = memory_item.get("content", "")
                importance = memory_item.get("importance", 3)
                
                if not content:
                    return
                
                # 5. 存入长期记忆
                self.memory_system.add_memory(content, importance)
                logger.info(f"🧠 [潜意识] 已自动归档记忆：{content} (重要度: {importance})")
                
            except json.JSONDecodeError as e:
                logger.debug(f"潜意识记忆解析失败: {e}")
            except Exception as e:
                logger.warning(f"潜意识记忆提取失败: {e}")
        
        # 启动后台线程，不阻塞主对话
        thread = threading.Thread(target=_background_task, daemon=True)
        thread.start()
