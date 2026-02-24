import json
import os
import sys
import time
import datetime
import logging
import httpx
import threading
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIStatusError
from .config import ConfigManager
from .mouth import Mouth
from .memory import MemoryBank  # [Migration] Use new ChromaDB memory

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

        # [Migration] 长期记忆系统 (ChromaDB)
        self.memory_system = MemoryBank(
            persist_dir=str(self.config.PROJECT_ROOT / "data" / "memory_db"),
            obsidian_vault_path=getattr(self.config, 'OBSIDIAN_VAULT_PATH', '')
        )

        # 短期对话历史
        self.chat_history = []

        # 状态
        self.IS_CREATION_MODE = False

        # 🔒 线程安全锁（修复风险1：ChromaDB 多线程写入可能锁死）
        # 所有后台线程写入 memory_system 前必须先获取此锁
        self._memory_lock = threading.Lock()

        # 🔥 性能监控系统
        self.performance_log = []  # 记录每次任务的性能数据
        self.system_hints = []     # 存储给AI的系统提示（如性能警告）

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
            # 使用 str.replace 而非 str.format，避免 system_prompt.txt 中的
            # JSON 示例（如 {"name": "RedSphere"}）触发 KeyError
            prompt = template.replace("{current_time}", current_time)
            prompt = prompt.replace("{current_date}", current_date)
            prompt = prompt.replace("{mode_status}", mode_status)
            prompt = prompt.replace("{history_summary}", f"【用户档案】{user_profile}\n【上次话题摘要】{summary}")
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
    def chat(self, user_input: str, system_content: str, tools_schema: list, tool_executor, progress_callback=None, cancel_event=None) -> str:
        """
        核心对话方法：支持 Function Calling (工具调用)
        
        Args:
            user_input: 用户输入
            system_content: 完整的 System Prompt（包含记忆）
            tools_schema: 工具定义列表
            tool_executor: 工具执行函数 (func_name, func_args) -> result
            progress_callback: 可选的进度回调 (dict) -> None，用于实时通知调用状态
            cancel_event: 可选的 threading.Event，外部设置后中断执行
            
        Returns:
            AI 的最终回复文本
        """
        def _notify(msg_type: str, **kwargs):
            if progress_callback:
                try:
                    progress_callback({"type": msg_type, **kwargs})
                except Exception:
                    pass
        
        def _is_cancelled():
            return cancel_event is not None and cancel_event.is_set()

        # 🔥 性能监控：记录开始时间
        start_time = time.time()
        tool_calls_list = []   # 记录本次调用的所有工具
        consecutive_errors = 0 # 修复风险3：连续错误计数器

        # 修复风险4：system_hints 移到 user_message 前面而非 system_prompt 末尾
        # 原因：DeepSeek 对 system_prompt 首尾敏感，警告放末尾会冲淡人设
        # 现在警告以 [System Note] 形式贴在用户消息最前面，权重更高
        hints_prefix = ""
        if self.system_hints:
            hints_text = "\n".join(self.system_hints)
            hints_prefix = f"[System Note]\n{hints_text}\n[/System Note]\n\n"
            self.system_hints.clear()

        # 修复风险1：配方召回不涉及写操作，不需要加锁
        recipe_reminder = self.memory_system.recall_recipe(user_input, n_results=4)
        if recipe_reminder:
            user_input_with_context = (
                f"{hints_prefix}"
                f"【⚡ 执行前必读配方 - 强制规范】\n{recipe_reminder}\n\n"
                f"---\n用户指令：{user_input}"
            )
        else:
            user_input_with_context = f"{hints_prefix}{user_input}" if hints_prefix else user_input

        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": user_input_with_context})

        # 修复风险3：max_iterations 保持15，但加连续错误截断
        max_iterations = 15
        iteration = 0
        ai_reply = ""
        
        while iteration < max_iterations:
            # 🛑 检查取消标志
            if _is_cancelled():
                logger.info("🛑 用户取消了当前操作")
                ai_reply = "好的指挥官，已停止当前操作。有什么需要可以随时告诉我~ [OK]"
                break
            
            iteration += 1
            logger.info(f"🤖 AI思考轮次: {iteration}")
            _notify("thinking", iteration=iteration)
            
            # 调用 DeepSeek（带重试 + 降级）
            response = None
            for attempt in range(3):  # 最多重试 3 次
                try:
                    response = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=messages,
                        tools=tools_schema,
                        tool_choice="auto",
                        stream=False,
                        temperature=0.8,
                        max_tokens=8192
                    )
                    break  # 成功，跳出重试循环
                except (APITimeoutError, APIConnectionError) as e:
                    wait = 2 ** attempt  # 1s, 2s, 4s 指数退避
                    logger.warning(f"⚠️ API 网络错误 (第{attempt+1}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                except RateLimitError as e:
                    wait = 5 * (attempt + 1)  # 5s, 10s, 15s
                    logger.warning(f"⚠️ API 限流 (第{attempt+1}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                except APIStatusError as e:
                    logger.error(f"❌ API 状态错误: {e.status_code} {e.message}")
                    break  # 服务端错误不重试
                except Exception as e:
                    logger.error(f"❌ API 未知错误: {e}")
                    break
            
            if response is None:
                ai_reply = "指挥官，我的网络好像不太稳定，连接不上服务器…等一下再试试？[Sorrow]"
                break
            
            message = response.choices[0].message
            
            # 检查是否需要调用工具
            if message.tool_calls:
                logger.info(f"🔧 AI请求使用工具: {len(message.tool_calls)} 个")
                _notify("tool_start", count=len(message.tool_calls))
                
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
                        # 多层修复策略
                        func_args = None
                        raw = tool_call.function.arguments or ""
                        
                        # 策略1: 给裸字标识符加引号
                        try:
                            import re
                            fixed = re.sub(
                                r':\s*([A-Za-z_][A-Za-z0-9_]*)\s*([,}\]])',
                                lambda m: ': "' + m.group(1) + '"' + m.group(2)
                                    if m.group(1) not in ('true', 'false', 'null')
                                    else m.group(0),
                                raw
                            )
                            func_args = json.loads(fixed)
                            logger.warning(f"⚠️ 工具参数 JSON 已自动修复（裸标识符）: {func_name}")
                        except Exception:
                            pass
                        
                        # 策略1.5: 对 create_file_directly 直接正则提取（不依赖 JSON 解析）
                        if func_args is None and func_name == "create_file_directly":
                            try:
                                import re as _re
                                fp_match = _re.search(r'"file_path"\s*:\s*"([^"]+)"', raw)
                                ct_match = _re.search(r'"content"\s*:\s*"', raw)
                                if fp_match and ct_match:
                                    file_path = fp_match.group(1)
                                    # content 从匹配结束位置取到字符串末尾
                                    content_start = ct_match.end()
                                    content_raw = raw[content_start:]
                                    # 去掉尾部可能的 "} 或未闭合的部分
                                    content_raw = content_raw.rstrip()
                                    if content_raw.endswith('"}'):
                                        content_raw = content_raw[:-2]
                                    elif content_raw.endswith('"'):
                                        content_raw = content_raw[:-1]
                                    # 反转义 JSON 字符串中的转义字符
                                    content_text = content_raw.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
                                    func_args = {"file_path": file_path, "content": content_text}
                                    logger.warning(f"⚠️ 工具参数 JSON 已自动修复（正则提取）: {func_name}")
                            except Exception:
                                pass
                        
                        # 策略2: 截断修复（改进版：字符串感知的括号计数）
                        if func_args is None:
                            try:
                                repair = raw.rstrip()
                                # 字符串感知：遍历时跟踪是否在引号内
                                in_str = False
                                open_braces = 0
                                open_brackets = 0
                                for i, ch in enumerate(repair):
                                    if ch == '"' and (i == 0 or repair[i-1] != '\\'):
                                        in_str = not in_str
                                    elif not in_str:
                                        if ch == '{': open_braces += 1
                                        elif ch == '}': open_braces -= 1
                                        elif ch == '[': open_brackets += 1
                                        elif ch == ']': open_brackets -= 1
                                # 补全
                                if in_str:
                                    repair += '"'
                                repair += '}' * max(0, open_braces)
                                repair += ']' * max(0, open_brackets)
                                func_args = json.loads(repair)
                                logger.warning(f"⚠️ 工具参数 JSON 已自动修复（截断补全）: {func_name}")
                            except Exception:
                                pass
                        
                        # 所有策略失败
                        if func_args is None:
                            logger.error(f"工具参数解析失败: {func_name}, 原始参数: {raw[:500]}..., 错误: {e}")
                            # 给 AI 清晰的错误回馈，避免重试死循环
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": (
                                    f"❌ JSON 参数解析失败（可能是内容太长被截断）。"
                                    f"请不要重试相同内容！建议对用户说明情况，或将内容拆分为更小的部分。"
                                )
                            })
                            consecutive_errors += 1
                            if consecutive_errors >= 2:
                                ai_reply = "指挥官，文件内容太长导致工具调用失败了，我重新换个方式试试或者你来配合一下？[Worry]"
                                break
                            continue
                    
                    # 修复风险3+日志增强：显示工具参数，方便调试路径问题
                    logger.info(f"📞 调用工具: {func_name} | 参数: {json.dumps(func_args, ensure_ascii=False)[:200]}")
                    _notify("tool_call", tool=func_name)
                    
                    # 🛑 工具执行前再次检查取消
                    if _is_cancelled():
                        logger.info("🛑 用户在工具调用前取消了操作")
                        ai_reply = "好的指挥官，已停止当前操作。有什么需要可以随时告诉我~ [OK]"
                        break
                    
                    tool_calls_list.append(func_name)

                    # 工具执行（带连续错误截断）
                    try:
                        result = tool_executor(func_name, func_args)
                        consecutive_errors = 0  # 成功则重置计数器
                    except Exception as e:
                        consecutive_errors += 1
                        logger.error(f"❌ 工具执行失败: {func_name} → {e} （连续失败 {consecutive_errors} 次）")
                        result = f"工具执行失败: {e}"
                        # 修复风险3：连续 3 次工具报错，截断并请求人工介入
                        if consecutive_errors >= 3:
                            logger.error("🚨 连续 3 次工具失败，强制截断，请人工介入！")
                            ai_reply = "指挥官，我连续遇到了 3 次工具报错，可能是环境问题，需要你来看一下～[Worry]"
                            break
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                
                # 修复风险3：连续错误截断后退出主循环
                if consecutive_errors >= 3:
                    break
                # 🛑 取消后退出主循环
                if _is_cancelled():
                    break

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
        # [优化] 降低触发阈值：5秒 + 2个工具，更容易触发学习
        if elapsed_time > 5 and tool_count > 2:
            warning = f"""⚠️ 性能警告：上一个任务耗时 {elapsed_time:.1f}秒，调用了 {tool_count} 个工具。

请反思：
- 是否有更快的方法？（如用 create_file_directly 代替打开记事本）
- 是否可以用快捷键代替点击菜单？（如 Ctrl+S 保存）
- 是否可以合并多个操作为一个工具调用？

记住：用户要的是结果，不是过程。优先使用【工具优先级1-2】的方法。

最近调用的工具：{', '.join(tool_calls_list[-5:])}"""
            self.system_hints.append(warning)  # 下次对话时自动注入
            logger.warning(f"🐢 性能警告已生成，将在下次对话时提醒AI优化")
            
            # 🔥 自动学习：把性能教训保存到长期记忆（永久记住）
            self.learn_from_performance(user_input, tool_calls_list, elapsed_time)
        
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
                
                # 5. 去重检查：如果已有高度相似的记忆，跳过存储
                try:
                    existing = self.memory_system.search_memory(content, n_results=1, threshold=0.5)
                    if existing:
                        logger.debug(f"🧠 [潜意识] 记忆已存在，跳过: '{content[:30]}' (相似: {existing[0].get('content', '')[:30]})")
                        return
                except Exception:
                    pass  # 去重失败不影响存储
                
                # 6. 存入长期记忆（加锁防止多线程写入冲突）
                with self._memory_lock:
                    self.memory_system.add_memory(content, category="fact", metadata={"importance": importance})
                logger.info(f"🧠 [潜意识] 已自动归档记忆：{content} (重要度: {importance})")
                
            except json.JSONDecodeError as e:
                logger.debug(f"潜意识记忆解析失败: {e}")
            except Exception as e:
                logger.warning(f"潜意识记忆提取失败: {e}")
        
        # 启动后台线程，不阻塞主对话
        thread = threading.Thread(target=_background_task, daemon=True)
        thread.start()

    # 任务步数基准范围 (min_steps, max_steps)
    # 修复风险2：改为范围而非固定值，避免复杂任务被误判为冗余
    # 超过 max_steps 才触发反思
    TASK_BASELINES = {
        "obsidian": (1, 2),   # 写笔记：1步最优，2步可接受
        "黑曜石":   (1, 2),
        "黑药石":   (1, 2),
        "黑钥匙":   (1, 2),
        "github搜索": (1, 2), # 单纯搜索：1-2步
        "github":   (1, 4),   # 复杂GitHub操作（搜索+读+创建Issue）：最多4步
        "创建文件": (1, 1),
        "写文件":   (1, 1),
        "保存文件": (1, 1),
    }

    def _get_task_baseline(self, user_task: str) -> tuple:
        """
        根据任务描述获取步数基准范围 (min, max)
        超过 max 才触发反思，避免复杂任务被误判
        """
        task_lower = user_task.lower()
        # 优先匹配更具体的关键词（github搜索 > github）
        sorted_keys = sorted(self.TASK_BASELINES.keys(), key=len, reverse=True)
        for keyword in sorted_keys:
            if keyword in task_lower:
                return self.TASK_BASELINES[keyword]
        return (1, 4)  # 未知任务默认 1-4 步都可接受

    def learn_from_performance(self, user_task: str, tools_used: list, elapsed_time: float):
        """
        🔥 从操作中自动学习，存入配方前先验证是否走了弯路
        v2.1 新增：
        - 验证环节：存配方前先问 AI 有没有多余步骤
        - 基准检查：超过历史最优步数 1.5 倍也触发反思
        - 防止学错：成功但低效的方法不会被存为正确配方
        """
        def _background_task():
            try:
                tool_count = len(tools_used)
                tools_str = ' -> '.join(tools_used)

                # Step 1: 验证环节 - 存配方前先问 AI 有没有走弯路
                verify_prompt = f"""你刚才完成了一个任务，请做【执行质量审查】。

【任务】：{user_task}
【耗时】：{elapsed_time:.1f}秒
【工具调用顺序】：{tools_str}
【总步数】：{tool_count}步

请判断这次执行是否走了弯路：

【审查重点】
1. 有没有本可以不用但用了的工具？
   例如：已知路径还去调用 list_directory 或 list_allowed_directories
   例如：同一工具连续调用多次（write_file 调用 3 次）
   例如：第一次用错路径失败，第二次才用对（说明配方路径有误）
2. 最优方案应该几步？（Obsidian写笔记=1步，GitHub搜索=1步）

严格按以下 JSON 格式输出，不要废话：
{{"has_redundancy": true或false, "redundant_steps": ["多余步骤1"], "optimal_steps": 最优步数, "root_cause": "根本原因一句话", "correct_solution": "正确做法一句话含具体工具名和路径"}}

如果执行完全最优，输出：{{"has_redundancy": false}}"""

                verify_resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": verify_prompt}],
                    max_tokens=300,
                    temperature=0.1
                )
                verify_result = verify_resp.choices[0].message.content.strip()
                clean_verify = verify_result.replace("```json", "").replace("```", "").strip()
                verify_data = json.loads(clean_verify)

                has_redundancy = verify_data.get("has_redundancy", False)
                redundant_steps = verify_data.get("redundant_steps", [])
                optimal_steps = verify_data.get("optimal_steps", tool_count)
                root_cause = verify_data.get("root_cause", "")
                correct_solution = verify_data.get("correct_solution", "")

                if has_redundancy:
                    logger.warning(f"⚠️ [质量审查] 发现冗余！实际{tool_count}步 vs 最优{optimal_steps}步 | {root_cause}")
                else:
                    logger.info(f"✅ [质量审查] 执行合格（{tool_count}步）")

                # Step 2: 基准检查 - 超过 max_steps 才触发反思
                # 修复风险2：使用范围(min,max)而非固定值，避免复杂任务被误判
                baseline_min, baseline_max = self._get_task_baseline(user_task)
                if tool_count > baseline_max and not has_redundancy:
                    has_redundancy = True
                    root_cause = root_cause or f"步数({tool_count})超过可接受上限({baseline_max}步)"
                    logger.warning(f"⚠️ [基准检查] 步数超标：{tool_count}步 > 上限{baseline_max}步")
                elif tool_count <= baseline_max:
                    logger.info(f"✅ [基准检查] 步数合格（{tool_count}步，上限{baseline_max}步）")

                # Step 3: 根据验证结果生成配方内容
                if has_redundancy and correct_solution:
                    # 有冗余：存正确做法 + 禁止项
                    lesson = f"{correct_solution} 【禁止】{', '.join(redundant_steps[:2])} 【原因】{root_cause}"
                    logger.info(f"📚 [学习] 发现弯路，存入纠正配方：{lesson[:80]}")
                else:
                    # 无冗余：生成常规最佳实践
                    learning_prompt = f"""分析以下操作，提取最佳实践。

【任务】：{user_task}
【耗时】：{elapsed_time:.1f}秒
【工具链】：{tools_str}

提炼下次同类任务的最优做法，一句话。
格式：{{"lesson": "当用户说...时，直接用...，注意..."}}
如果已是最优，输出 None"""

                    learn_resp = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": learning_prompt}],
                        max_tokens=150,
                        temperature=0.2
                    )
                    learn_result = learn_resp.choices[0].message.content.strip()

                    if "None" in learn_result or "{" not in learn_result:
                        logger.info("✅ [学习] 本次执行已是最优，无需存配方")
                        return

                    clean_learn = learn_result.replace("```json", "").replace("```", "").strip()
                    lesson_item = json.loads(clean_learn)
                    lesson = lesson_item.get("lesson", "")
                    if not lesson:
                        return

                # Step 4: 提取语义化 trigger，避免语音识别错误
                trigger_prompt = f"""从以下内容提取触发场景关键词（3-5个中文词，逗号分隔）：
任务：{user_task}
教训：{lesson}
直接输出关键词，不要其他内容："""

                trigger_resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": trigger_prompt}],
                    max_tokens=30,
                    temperature=0.1
                )
                semantic_trigger = trigger_resp.choices[0].message.content.strip()

                # 存入配方（加锁防止与潜意识线程冲突）
                with self._memory_lock:
                    self.memory_system.add_recipe(
                        trigger=semantic_trigger,
                        solution=lesson,
                        metadata={
                            "source": "auto_learn",
                            "elapsed": elapsed_time,
                            "tools": ",".join(tools_used),
                            "optimal_steps": optimal_steps,
                            "actual_steps": tool_count,
                            "had_redundancy": has_redundancy,
                            "original_task": user_task[:100]
                        }
                    )
                logger.info(f"📚 [性能学习] 已存入配方：{lesson[:80]}")

            except json.JSONDecodeError as e:
                logger.debug(f"性能教训解析失败: {e}")
            except Exception as e:
                logger.warning(f"性能学习失败: {e}")

        thread = threading.Thread(target=_background_task, daemon=True)
        thread.start()