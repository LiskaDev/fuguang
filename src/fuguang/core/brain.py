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
        
        # 🔥 性能监控系统
        self.performance_log = []  # 记录每次任务的性能数据
        self.system_hints = []  # 存储给AI的系统提示（如性能警告）
        
        # v2.1 新增：启动时预埋关键配方（importance=5，不会被自动学习覆盖）
        self._ensure_critical_recipes()

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
            prompt = template
            prompt = prompt.replace("{current_time}", current_time)
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
            system_content += f"\n\n{hints_text}\n"
            self.system_hints.clear()  # 清空提示，只显示一次
        
        # v2.1 新增：把配方单独强化注入到 user_input 前面
        # 原来配方混在 system_prompt 里容易被淹没
        # 现在把配方作为独立的"任务前检查"注入到用户消息前
        recipe_reminder = self.memory_system.recall_recipe(user_input, n_results=4)
        if recipe_reminder:
            user_input_with_recipe = f"""【⚡ 执行前必读配方 - 这是强制规范，不是建议】
{recipe_reminder}

---
用户指令：{user_input}"""
        else:
            user_input_with_recipe = user_input
        
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": user_input_with_recipe})
        
        # [调整] 增加思考轮次上限，以支持复杂的连续任务 (如: 打开网页 -> 截图 -> 分析 -> 总结)
        max_iterations = 15
        iteration = 0
        ai_reply = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"🤖 AI思考轮次: {iteration}")
            
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
                        max_tokens=4096
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
                    
                    logger.info(f"📞 调用工具: {func_name} | 参数: {json.dumps(func_args, ensure_ascii=False)[:300]}")
                    tool_calls_list.append(func_name)  # 🔥 记录工具调用
                    
                    # 工具执行超时保护（30秒）
                    try:
                        result = tool_executor(func_name, func_args)
                    except Exception as e:
                        logger.error(f"❌ 工具执行失败: {func_name} → {e}")
                        result = f"工具执行失败: {e}"
                    
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
        
        # 🔥 性能警告：如果太慢或调用太多工具，下次强制执行优化规则
        if elapsed_time > 5 and tool_count > 2:
            # v2.1 修复：从"建议"改为"强制规则"
            # 原来的措辞是"请反思"，AI 可以忽略
            # 现在改为"禁止/必须"，强制约束行为
            warning = f"""【🚨 强制执行规则 - 上次任务违规】
上次任务耗时 {elapsed_time:.1f}秒，调用了 {tool_count} 个工具（超标）。
违规工具链：{' → '.join(tool_calls_list[-8:])}

本次任务【禁止】重复以下行为：
❌ 禁止连续调用超过 2 次相同工具（如重复 write_file / list_directory）
❌ 禁止在写文件前先 list_directory 探索路径（直接使用已知路径）
❌ 禁止多次尝试写同一个文件（一次写对）

本次任务【必须】遵守：
✅ Obsidian 写文件：直接用 mcp_obsidian_write_file，路径格式 "Notes/文件名.md"
✅ GitHub 搜索：一次性搜索完所有结果，禁止循环调用 search_repositories
✅ 创建文件：用 create_file_directly，禁止打开记事本

违反以上规则视为执行失败。"""
            self.system_hints.append(warning)
            logger.warning(f"🚨 强制规则已生成，下次对话强制注入")
            
            # 🔥 自动学习：把性能教训保存到长期记忆（永久记住）
            self.learn_from_performance(user_input, tool_calls_list, elapsed_time)
        
        # 更新对话历史（保存原始输入，不含配方前缀，避免污染历史）
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
                
                # 6. 存入长期记忆
                self.memory_system.add_memory(content, category="fact", metadata={"importance": importance})
                logger.info(f"🧠 [潜意识] 已自动归档记忆：{content} (重要度: {importance})")
                
            except json.JSONDecodeError as e:
                logger.debug(f"潜意识记忆解析失败: {e}")
            except Exception as e:
                logger.warning(f"潜意识记忆提取失败: {e}")
        
        # 启动后台线程，不阻塞主对话
        thread = threading.Thread(target=_background_task, daemon=True)
        thread.start()

    def learn_from_performance(self, user_task: str, tools_used: list, elapsed_time: float):
        """
        🔥 从慢操作中自动学习，把教训永久保存到长期记忆
        
        Args:
            user_task: 用户的任务描述
            tools_used: 调用的工具列表
            elapsed_time: 耗时（秒）
        """
        def _background_task():
            try:
                # 1. 让AI分析这次慢操作，提取教训
                learning_prompt = f"""分析以下慢操作，提取【性能优化教训】。

【任务】：{user_task}
【耗时】：{elapsed_time:.1f}秒
【调用的工具】：{', '.join(tools_used)}

【分析规则】
1. 🔍 **成败检查**：如果最后一步是失败的（报错、异常），请不要提取教训，或者提取“避坑指南”。
2. ⚡ **GUI优化**：如果由于 GUI 点击变慢，是否有键盘快捷键替代？
3. 🛠️ **工具链优化**：如果多次调用同一工具（如 write_file），是否可以合并？
4. 📂 **路径修正**：如果涉及文件操作，是否需要指定特殊路径（如 Obsidian 的 Notes/ 目录）？

【输出格式】
严格按照以下JSON格式输出：
{{"lesson": "当用户说【关键词】时，应该使用【具体方案】，注意【避坑点】"}}

【示例】
{{"lesson": "当用户说'在Obsidian写笔记'时，应该直接用mcp_obsidian_write_file，但必须确保文件路径包含'Notes/'前缀（如Notes/xx.md），否则会权限报错"}}
{{"lesson": "当用户说'保存'时，直接发送快捷键ctrl+s，不要用鼠标点击菜单"}}

如果这次操作已经是最优方案，或者因不可抗力失败，输出 None
"""
                
                # 2. 调用LLM分析
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": learning_prompt}],
                    max_tokens=200,
                    temperature=0.2  # 低温度，更精确
                )
                result = response.choices[0].message.content.strip()
                
                # 3. 检查是否有教训
                if "None" in result or "none" in result or "{" not in result:
                    return  # 已经是最优方案
                
                # 4. 解析JSON
                clean_json = result.replace("```json", "").replace("```", "").strip()
                lesson_item = json.loads(clean_json)
                
                lesson = lesson_item.get("lesson", "")
                if not lesson:
                    return
                
                # 5. 保存到 recipes 配方记忆（而非通用记忆池）
                # v2.1 修复：trigger 不再用原始语音识别文本
                # 原因：语音识别常出错（"get hardly" = "GitHub"），导致配方无法被匹配
                # 改为：让 LLM 从 lesson 里提取语义化的触发关键词
                trigger_prompt = f"""从以下性能优化教训中，提取【触发场景关键词】，用于下次匹配识别。

教训内容：{lesson}

要求：
- 输出3-5个中文关键词，用逗号分隔
- 关键词要语义化（不是原始语音），能代表这类任务
- 例如："GitHub搜索,找项目,写到Obsidian"

直接输出关键词，不要其他内容："""
                
                try:
                    trigger_resp = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": trigger_prompt}],
                        max_tokens=50,
                        temperature=0.1
                    )
                    semantic_trigger = trigger_resp.choices[0].message.content.strip()
                except Exception:
                    semantic_trigger = user_task  # 提取失败则退回原始文本
                
                self.memory_system.add_recipe(
                    trigger=semantic_trigger,
                    solution=lesson,
                    metadata={"source": "auto_learn", "elapsed": elapsed_time, "tools": ",".join(tools_used), "original_task": user_task[:100]}
                )
                logger.info(f"📚 [性能学习] 已存入配方记忆：{lesson}")
                
            except json.JSONDecodeError as e:
                logger.debug(f"性能教训解析失败: {e}")
            except Exception as e:
                logger.warning(f"性能学习失败: {e}")
        
        # 后台线程运行，不阻塞对话
        thread = threading.Thread(target=_background_task, daemon=True)
        thread.start()

    def _ensure_critical_recipes(self):
        """
        v2.1 新增：启动时预埋关键配方
        这些是经过实战验证的最优方案，importance=5 不会被自动学习覆盖
        解决"每次都学但每次都忘"的根本问题
        """
        critical_recipes = [
            {
                "trigger": "Obsidian写文件,写到黑曜石,保存到笔记,记录到Obsidian",
                "solution": "直接调用 mcp_obsidian_write_file，路径格式：'Notes/文件名.md'。禁止先调用 list_directory 或 list_allowed_directories 探索路径。一次写入，禁止重复调用 write_file。",
                "importance": 5
            },
            {
                "trigger": "GitHub搜索,找项目,search repositories,在GitHub上找",
                "solution": "调用一次 mcp_github_search_repositories，带上 language 和 sort 参数一次性获取所有结果。禁止循环多次调用 search_repositories。",
                "importance": 5
            },
            {
                "trigger": "创建文件,写文件,保存文件",
                "solution": "使用 create_file_directly，禁止打开记事本或任何 GUI 应用。create_file_directly 速度是打开记事本的 600 倍。",
                "importance": 5
            },
        ]
        
        for recipe in critical_recipes:
            # 检查是否已存在（避免重复写入）
            existing = self.memory_system.search_recipes(recipe["trigger"].split(",")[0], n_results=1, threshold=0.5)
            if not existing:
                self.memory_system.add_recipe(
                    trigger=recipe["trigger"],
                    solution=recipe["solution"],
                    metadata={"source": "manual_fix", "importance": recipe["importance"]}
                )
                logger.info(f"🛡️ [关键配方] 已预埋: {recipe['trigger'][:30]}")