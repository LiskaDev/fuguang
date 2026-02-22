"""
MCPSkills — 🧩 MCP (Model Context Protocol) 客户端
通过标准协议接入外部工具服务器（GitHub、Obsidian、文件系统等）

架构说明：
- MCP Server 是独立的 Node.js 进程，提供工具能力
- 本模块作为 MCP Client，通过 stdio JSON-RPC 与 Server 通信
- 自动发现 Server 暴露的工具 → 转换为 OpenAI Function Calling Schema → 桥接到扶光技能体系

当前接入：
- @modelcontextprotocol/server-github (GitHub 操作)
- @modelcontextprotocol/server-filesystem (Obsidian 读写)
"""
import asyncio
import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("fuguang.skills")

# MCP SDK 导入
try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("⚠️ MCP SDK 未安装 (pip install mcp)，MCP 扩展功能将不可用")

# Streamable HTTP 传输（用于 Unity MCP 直连）
try:
    from mcp.client.streamable_http import streamablehttp_client
    MCP_HTTP_AVAILABLE = True
except ImportError:
    MCP_HTTP_AVAILABLE = False


class MCPClient:
    """
    MCP 客户端 — 管理与 MCP Server 的连接和工具调用
    
    生命周期：
    1. connect() — 启动 Server 子进程，建立 stdio 通信
    2. discover_tools() — 获取 Server 暴露的工具列表
    3. call_tool() — 执行指定工具
    4. disconnect() — 关闭连接，终止子进程
    """
    
    def __init__(self, server_name: str, command: str, args: list, env: dict = None):
        """
        Args:
            server_name: 服务器名称（如 "github"）
            command: 启动命令（如 "npx"）
            args: 命令参数（如 ["-y", "@modelcontextprotocol/server-github"]）
            env: 环境变量（如 {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}）
        """
        self.server_name = server_name
        self.command = command
        self.args = args
        self.env = env or {}
        
        self._session: Optional[ClientSession] = None
        self._tools: list = []
        self._tools_schema: list = []  # OpenAI Function Calling 格式
        self._connected = False
        
        # 异步事件循环（在独立线程中运行）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        # 用于保持连接活跃
        self._shutdown_flag = False
    
    def connect(self) -> bool:
        """启动 MCP Server 并建立连接（同步入口）"""
        if not MCP_AVAILABLE:
            logger.error("❌ MCP SDK 未安装，无法连接")
            return False
        
        try:
            # 创建独立的事件循环线程
            self._loop = asyncio.new_event_loop()
            
            # 在独立线程中启动异步连接
            connect_ready = threading.Event()
            connect_result = {"success": False, "error": None}
            
            def _run_loop():
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(self._async_connect(connect_ready, connect_result))
                    # 连接建立后，保持事件循环运行以处理后续的工具调用
                    self._loop.run_forever()
                except Exception as e:
                    connect_result["error"] = str(e)
                    connect_ready.set()
            
            self._thread = threading.Thread(target=_run_loop, daemon=True, name=f"mcp-{self.server_name}")
            self._thread.start()
            
            # 等待连接完成（最多 30 秒）
            if not connect_ready.wait(timeout=30):
                logger.error(f"❌ [MCP:{self.server_name}] 连接超时 (30s)")
                return False
            
            if connect_result["error"]:
                logger.error(f"❌ [MCP:{self.server_name}] 连接失败: {connect_result['error']}")
                return False
            
            self._connected = connect_result["success"]
            return self._connected
            
        except Exception as e:
            logger.error(f"❌ [MCP:{self.server_name}] 启动失败: {e}")
            return False
    
    async def _async_connect(self, ready_event: threading.Event, result: dict):
        """异步连接实现"""
        try:
            # 合并环境变量
            full_env = {**os.environ, **self.env}
            
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=full_env,
            )
            
            # 进入 stdio_client 上下文
            self._stdio_cm = stdio_client(server_params)
            streams = await self._stdio_cm.__aenter__()
            read_stream, write_stream = streams
            
            # 进入 ClientSession 上下文
            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()
            
            # 初始化协议握手
            await self._session.initialize()
            
            # 发现工具
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools
            self._tools_schema = self._convert_to_openai_schema()
            
            tool_names = [t.name for t in self._tools]
            logger.info(f"✅ [MCP:{self.server_name}] 已连接，发现 {len(self._tools)} 个工具: {tool_names}")
            
            result["success"] = True
            ready_event.set()
            
            # 注意：不在这里等待清理信号
            # run_forever() 会在 _run_loop 中保持事件循环活跃
            # 上下文管理器由 self._stdio_cm / self._session_cm 保持引用
            
        except Exception as e:
            result["error"] = str(e)
            ready_event.set()
    
    def _convert_to_openai_schema(self) -> list:
        """将 MCP 工具 Schema 转换为 OpenAI Function Calling 格式"""
        schema_list = []
        for tool in self._tools:
            # MCP inputSchema → OpenAI parameters
            parameters = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}
            
            # 添加 MCP 前缀防止命名冲突（如 mcp_github_search_repositories）
            func_name = f"mcp_{self.server_name}_{tool.name}"
            
            schema_list.append({
                "type": "function",
                "function": {
                    "name": func_name,
                    "description": f"[MCP:{self.server_name}] {tool.description or tool.name}",
                    "parameters": parameters,
                }
            })
        return schema_list
    
    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        调用 MCP 工具（同步入口，带自动重连）
        
        Args:
            tool_name: 原始工具名（不含 mcp_ 前缀）
            arguments: 工具参数字典
            
        Returns:
            工具执行结果字符串
        """
        if not self._connected or not self._session:
            # 尝试自动重连
            logger.warning(f"⚠️ [MCP:{self.server_name}] 连接丢失，尝试自动重连...")
            if not self._reconnect():
                return f"❌ MCP Server [{self.server_name}] 未连接且重连失败"
        
        try:
            # 在 MCP 事件循环中执行异步调用
            future = asyncio.run_coroutine_threadsafe(
                self._async_call_tool(tool_name, arguments),
                self._loop
            )
            result = future.result(timeout=30)
            return result
        except TimeoutError:
            return f"❌ MCP 工具调用超时 (30s): {tool_name}"
        except Exception as e:
            error_msg = str(e)
            # 连接断开类错误 → 重连后重试一次
            if any(kw in error_msg.lower() for kw in ['closed', 'broken', 'eof', 'connection', 'transport']):
                logger.warning(f"⚠️ [MCP:{self.server_name}] 通信异常，尝试重连: {error_msg[:80]}")
                if self._reconnect():
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self._async_call_tool(tool_name, arguments),
                            self._loop
                        )
                        return future.result(timeout=30)
                    except Exception as retry_e:
                        return f"❌ MCP 重连后仍失败: {retry_e}"
            return f"❌ MCP 工具调用失败: {e}"
    
    def _reconnect(self) -> bool:
        """断开旧连接并重新建立"""
        try:
            self.disconnect()
        except Exception:
            pass
        logger.info(f"🔄 [MCP:{self.server_name}] 正在重连...")
        return self.connect()
    
    async def _async_call_tool(self, tool_name: str, arguments: dict) -> str:
        """异步工具调用实现"""
        result = await self._session.call_tool(tool_name, arguments)
        
        # 拼接所有 content 块
        parts = []
        for content in result.content:
            if hasattr(content, 'text'):
                parts.append(content.text)
            elif hasattr(content, 'data'):
                parts.append(f"[Binary data: {len(content.data)} bytes]")
            else:
                parts.append(str(content))
        
        output = "\n".join(parts)
        
        # 截断过长的输出（防止 token 爆炸）
        if len(output) > 4000:
            output = output[:4000] + f"\n... (已截断，总长 {len(output)} 字符)"
        
        return output
    
    def disconnect(self):
        """断开连接，终止 Server 子进程"""
        self._shutdown_flag = True
        
        # 在事件循环中执行异步清理
        if self._loop and self._loop.is_running():
            async def _cleanup():
                try:
                    if hasattr(self, '_session_cm'):
                        await self._session_cm.__aexit__(None, None, None)
                    if hasattr(self, '_stdio_cm'):
                        await self._stdio_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._loop.stop()
            
            asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._session = None
        logger.info(f"🔌 [MCP:{self.server_name}] 已断开连接")
    
    @property
    def tools_schema(self) -> list:
        """获取 OpenAI Function Calling 格式的工具 Schema"""
        return self._tools_schema
    
    @property
    def is_connected(self) -> bool:
        return self._connected


class MCPHttpClient:
    """
    MCP HTTP 客户端 — 通过 streamablehttp 协议直连 MCP Server
    
    用于 Unity MCP Plugin 等原生 HTTP MCP 服务的连接。
    不需要启动子进程，直接通过 HTTP 连接到已运行的 MCP 服务器。
    """
    
    def __init__(self, server_name: str, url: str):
        self.server_name = server_name
        self.url = url
        
        self._session: Optional[ClientSession] = None
        self._tools: list = []
        self._tools_schema: list = []
        self._connected = False
        
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
    
    def connect(self) -> bool:
        """连接到 HTTP MCP Server（同步入口）"""
        if not MCP_AVAILABLE or not MCP_HTTP_AVAILABLE:
            logger.error("❌ MCP SDK 或 streamablehttp 不可用")
            return False
        
        try:
            self._loop = asyncio.new_event_loop()
            connect_ready = threading.Event()
            connect_result = {"success": False, "error": None}
            
            def _run_loop():
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(self._async_connect(connect_ready, connect_result))
                    self._loop.run_forever()
                except Exception as e:
                    connect_result["error"] = str(e)
                    connect_ready.set()
            
            self._thread = threading.Thread(target=_run_loop, daemon=True, name=f"mcp-http-{self.server_name}")
            self._thread.start()
            
            if not connect_ready.wait(timeout=30):
                logger.error(f"❌ [MCP:{self.server_name}] HTTP 连接超时 (30s)")
                return False
            
            if connect_result["error"]:
                logger.error(f"❌ [MCP:{self.server_name}] HTTP 连接失败: {connect_result['error']}")
                return False
            
            self._connected = connect_result["success"]
            return self._connected
        except Exception as e:
            logger.error(f"❌ [MCP:{self.server_name}] HTTP 启动失败: {e}")
            return False
    
    async def _async_connect(self, ready_event: threading.Event, result: dict):
        """异步 HTTP 连接实现"""
        try:
            self._http_cm = streamablehttp_client(self.url)
            streams = await self._http_cm.__aenter__()
            read_stream, write_stream = streams[0], streams[1]
            
            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()
            
            await self._session.initialize()
            
            tools_result = await self._session.list_tools()
            self._tools = tools_result.tools
            self._tools_schema = self._convert_to_openai_schema()
            
            tool_names = [t.name for t in self._tools]
            logger.info(f"✅ [MCP:{self.server_name}] HTTP 已连接，发现 {len(self._tools)} 个工具")
            
            result["success"] = True
            ready_event.set()
        except Exception as e:
            result["error"] = str(e)
            ready_event.set()
    
    def _convert_to_openai_schema(self) -> list:
        """将 MCP 工具 Schema 转换为 OpenAI Function Calling 格式"""
        schema_list = []
        for tool in self._tools:
            parameters = tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}}
            func_name = f"mcp_{self.server_name}_{tool.name}"
            schema_list.append({
                "type": "function",
                "function": {
                    "name": func_name,
                    "description": f"[MCP:{self.server_name}] {tool.description or tool.name}",
                    "parameters": parameters,
                }
            })
        return schema_list
    
    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具（同步入口）"""
        if not self._connected or not self._session:
            logger.warning(f"⚠️ [MCP:{self.server_name}] HTTP 连接丢失，尝试重连...")
            if not self._reconnect():
                return f"❌ MCP Server [{self.server_name}] 未连接且重连失败"
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_call_tool(tool_name, arguments),
                self._loop
            )
            result = future.result(timeout=60)  # Unity 工具可能较慢
            return result
        except TimeoutError:
            return f"❌ MCP 工具调用超时 (60s): {tool_name}"
        except Exception as e:
            error_msg = str(e)
            if any(kw in error_msg.lower() for kw in ['closed', 'broken', 'eof', 'connection', 'transport']):
                logger.warning(f"⚠️ [MCP:{self.server_name}] 通信异常，尝试重连")
                if self._reconnect():
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self._async_call_tool(tool_name, arguments),
                            self._loop
                        )
                        return future.result(timeout=60)
                    except Exception as retry_e:
                        return f"❌ MCP 重连后仍失败: {retry_e}"
            return f"❌ MCP 工具调用失败: {e}"
    
    def _reconnect(self) -> bool:
        try:
            self.disconnect()
        except Exception:
            pass
        logger.info(f"🔄 [MCP:{self.server_name}] HTTP 重连中...")
        return self.connect()
    
    async def _async_call_tool(self, tool_name: str, arguments: dict) -> str:
        """异步工具调用实现"""
        result = await self._session.call_tool(tool_name, arguments)
        
        parts = []
        for content in result.content:
            if hasattr(content, 'text'):
                parts.append(content.text)
            elif hasattr(content, 'data'):
                parts.append(f"[Binary data: {len(content.data)} bytes]")
            else:
                parts.append(str(content))
        
        output = "\n".join(parts)
        if len(output) > 8000:  # Unity 工具可能返回较多数据
            output = output[:8000] + f"\n... (已截断，总长 {len(output)} 字符)"
        return output
    
    def disconnect(self):
        """断开 HTTP 连接"""
        if self._loop and self._loop.is_running():
            async def _cleanup():
                try:
                    if hasattr(self, '_session_cm'):
                        await self._session_cm.__aexit__(None, None, None)
                    if hasattr(self, '_http_cm'):
                        await self._http_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._loop.stop()
            asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._connected = False
        self._session = None
        logger.info(f"🔌 [MCP:{self.server_name}] HTTP 已断开")
    
    @property
    def tools_schema(self) -> list:
        return self._tools_schema
    
    @property
    def is_connected(self) -> bool:
        return self._connected


class MCPSkills:
    """
    MCP 扩展技能 Mixin
    
    在 BaseSkillMixin.__init__ 之后自动初始化 MCP 服务器连接，
    动态发现工具并注册到扶光技能体系。
    """
    _MCP_TOOLS = []  # 动态填充
    
    def _init_mcp(self):
        """
        初始化所有配置的 MCP Servers
        在 BaseSkillMixin.__init__ 末尾调用
        """
        self._mcp_clients: dict[str, MCPClient] = {}
        
        if not MCP_AVAILABLE:
            logger.info("ℹ️ [MCP] SDK 未安装，跳过 MCP 初始化")
            return
        
        # 注册 GitHub MCP Server
        github_token = getattr(self.config, 'GITHUB_TOKEN', '')
        if github_token:
            github_client = MCPClient(
                server_name="github",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-github"],
                env={"GITHUB_PERSONAL_ACCESS_TOKEN": github_token}
            )
            
            logger.info("🔌 [MCP] 正在连接 GitHub Server...")
            if github_client.connect():
                self._mcp_clients["github"] = github_client
                # 动态注入工具 Schema
                MCPSkills._MCP_TOOLS = list(github_client.tools_schema)
                logger.info(f"✅ [MCP] GitHub 已就绪，{len(github_client.tools_schema)} 个工具已注册")
            else:
                logger.warning("⚠️ [MCP] GitHub Server 连接失败（系统仍可正常运行）")
        else:
            logger.info("ℹ️ [MCP] 未配置 GITHUB_TOKEN，跳过 GitHub MCP")
        
        # 注册 Obsidian MCP Server（通过 FileSystem）
        obsidian_vault = getattr(self.config, 'OBSIDIAN_VAULT_PATH', '')
        if obsidian_vault and os.path.isdir(obsidian_vault):
            obsidian_client = MCPClient(
                server_name="obsidian",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", obsidian_vault],
                env={}
            )
            
            logger.info(f"🔌 [MCP] 正在连接 Obsidian FileSystem Server ({obsidian_vault})...")
            if obsidian_client.connect():
                self._mcp_clients["obsidian"] = obsidian_client
                MCPSkills._MCP_TOOLS.extend(obsidian_client.tools_schema)
                logger.info(f"✅ [MCP] Obsidian 已就绪，{len(obsidian_client.tools_schema)} 个工具已注册")
            else:
                logger.warning("⚠️ [MCP] Obsidian FileSystem Server 连接失败")
        elif obsidian_vault:
            logger.warning(f"⚠️ [MCP] Obsidian Vault 路径不存在: {obsidian_vault}")
        
        # 注册 Unity MCP Server (AI Game Developer) — 通过 HTTP 直连 Unity 插件
        unity_port = getattr(self.config, 'UNITY_MCP_PORT', 0)
        if unity_port and MCP_HTTP_AVAILABLE:
            unity_url = f"http://localhost:{unity_port}/mcp"
            unity_client = MCPHttpClient(
                server_name="ai-game-developer",
                url=unity_url
            )
            
            print(f"🔌 [MCP] 正在连接 Unity MCP (HTTP: {unity_url})...")
            logger.info(f"🔌 [MCP] 正在连接 Unity MCP (HTTP: {unity_url})...")
            if unity_client.connect():
                self._mcp_clients["ai-game-developer"] = unity_client
                MCPSkills._MCP_TOOLS.extend(unity_client.tools_schema)
                print(f"✅ [MCP] Unity 已就绪，{len(unity_client.tools_schema)} 个工具已注册")
                logger.info(f"✅ [MCP] Unity 已就绪，{len(unity_client.tools_schema)} 个工具已注册")
            else:
                print("⚠️ [MCP] Unity MCP 连接失败（请确认 Unity Editor 已打开且 MCP 插件正在运行）")
                logger.warning("⚠️ [MCP] Unity MCP 连接失败（请确认 Unity Editor 已打开且 MCP 插件正在运行）")
        elif unity_port and not MCP_HTTP_AVAILABLE:
            print("⚠️ [MCP] streamablehttp 模块不可用，无法连接 Unity MCP")
            logger.warning("⚠️ [MCP] streamablehttp 模块不可用，无法连接 Unity MCP")
        else:
            print(f"ℹ️ [MCP] 未配置 UNITY_MCP_PORT (值={unity_port})，跳过 Unity MCP")
            logger.info("ℹ️ [MCP] 未配置 UNITY_MCP_PORT，跳过 Unity MCP")
    
    def _shutdown_mcp(self):
        """关闭所有 MCP 连接"""
        for name, client in getattr(self, '_mcp_clients', {}).items():
            try:
                client.disconnect()
            except Exception as e:
                logger.warning(f"⚠️ [MCP] 关闭 {name} 失败: {e}")
    
    def _autocorrect_unity_params(self, tool_name: str, func_args: dict) -> dict:
        """
        自动修正 DeepSeek 常见的 Unity MCP 参数错误。
        
        DeepSeek 经常犯的错误：
        1. assets-modify: 用 fields 设置 _Color，应该用 props
        2. assets-modify: 用 "color" 作为属性名，应该是 "_Color"
        3. gameobject-component-modify: 用 fields 设置 material，应该用 props
        4. assets-modify: color 值缺少 alpha ("a") 分量
        """
        args = json.loads(json.dumps(func_args))  # 深拷贝
        
        # === 修正 assets-modify（材质颜色设置）===
        if tool_name == "assets-modify" and "content" in args:
            content = args["content"]
            
            # 修正1: fields 中有 color/_Color 相关项 → 移到 props
            if "fields" in content and isinstance(content["fields"], list):
                color_items = []
                remaining = []
                for field in content["fields"]:
                    fname = field.get("name", "").lower()
                    ftype = field.get("typeName", "").lower()
                    if fname in ("color", "_color") or "color" in ftype:
                        # 修正属性名
                        field["name"] = "_Color"
                        if "typeName" not in field or "color" not in field["typeName"].lower():
                            field["typeName"] = "UnityEngine.Color"
                        # 确保有 alpha
                        if "value" in field and isinstance(field["value"], dict):
                            field["value"].setdefault("a", 1.0)
                        color_items.append(field)
                    else:
                        remaining.append(field)
                
                if color_items:
                    # 将颜色项移到 props
                    if "props" not in content:
                        content["props"] = []
                    content["props"].extend(color_items)
                    content["fields"] = remaining
                    if not content["fields"]:
                        del content["fields"]
                    logger.info(f"🔧 [自动修正] 将 _Color 从 fields 移到 props")
            
            # 修正2: props 中有 "color" 而非 "_Color"
            if "props" in content and isinstance(content["props"], list):
                for prop in content["props"]:
                    pname = prop.get("name", "")
                    if pname.lower() == "color" and pname != "_Color":
                        prop["name"] = "_Color"
                        logger.info(f"🔧 [自动修正] 属性名 '{pname}' → '_Color'")
                    if prop.get("name") == "_Color":
                        if "typeName" not in prop:
                            prop["typeName"] = "UnityEngine.Color"
                        if "value" in prop and isinstance(prop["value"], dict):
                            prop["value"].setdefault("a", 1.0)
        
        # === 修正 gameobject-component-modify（材质赋值）===
        if tool_name == "gameobject-component-modify" and "componentDiff" in args:
            diff = args["componentDiff"]
            
            # 修正3: fields 中有 material → 移到 props
            if "fields" in diff and isinstance(diff["fields"], (list, dict)):
                fields_list = diff["fields"] if isinstance(diff["fields"], list) else [diff["fields"]]
                mat_items = []
                remaining = []
                for field in fields_list:
                    if isinstance(field, dict):
                        fname = field.get("name", "").lower()
                        if fname in ("material", "sharedmaterial", "m_materials"):
                            if fname == "m_materials":
                                field["name"] = "sharedMaterial"
                            mat_items.append(field)
                        else:
                            remaining.append(field)
                    else:
                        remaining.append(field)
                
                if mat_items:
                    if "props" not in diff:
                        diff["props"] = []
                    diff["props"].extend(mat_items)
                    diff["fields"] = remaining
                    if not diff["fields"]:
                        del diff["fields"]
                    logger.info(f"🔧 [自动修正] 将 material 从 fields 移到 props")
        
        return args
    
    def execute_mcp_tool(self, func_name: str, func_args: dict) -> str:
        """
        执行 MCP 工具调用
        
        func_name 格式: mcp_{server}_{tool_name}
        例: mcp_github_search_repositories → server="github", tool="search_repositories"
        
        Args:
            func_name: 带前缀的工具名
            func_args: 工具参数
            
        Returns:
            执行结果字符串
        """
        # 解析 server 名和工具名
        # mcp_github_search_repositories → ["mcp", "github", "search_repositories"]
        parts = func_name.split("_", 2)  # 最多分3段
        if len(parts) < 3:
            return f"❌ 无效的 MCP 工具名格式: {func_name}"
        
        server_name = parts[1]
        tool_name = parts[2]
        
        client = getattr(self, '_mcp_clients', {}).get(server_name)
        if not client or not client.is_connected:
            return f"❌ MCP Server [{server_name}] 未连接"
        
        # 🔧 Unity MCP 参数自动修正
        if server_name == "ai-game-developer":
            func_args = self._autocorrect_unity_params(tool_name, func_args)
        
        logger.info(f"🧩 [MCP:{server_name}] 调用工具: {tool_name}({json.dumps(func_args, ensure_ascii=False)[:200]})")
        result = client.call_tool(tool_name, func_args)
        logger.info(f"✅ [MCP:{server_name}] {tool_name} 执行完成 ({len(result)} 字符)")
        return result
    
    # ========================
    # 🎮 Unity 便捷工具
    # ========================
    
    # 颜色名称到 RGBA 的映射
    _COLOR_MAP = {
        "red": {"r": 1, "g": 0, "b": 0, "a": 1}, "红": {"r": 1, "g": 0, "b": 0, "a": 1}, "红色": {"r": 1, "g": 0, "b": 0, "a": 1},
        "green": {"r": 0, "g": 1, "b": 0, "a": 1}, "绿": {"r": 0, "g": 1, "b": 0, "a": 1}, "绿色": {"r": 0, "g": 1, "b": 0, "a": 1},
        "blue": {"r": 0, "g": 0, "b": 1, "a": 1}, "蓝": {"r": 0, "g": 0, "b": 1, "a": 1}, "蓝色": {"r": 0, "g": 0, "b": 1, "a": 1},
        "yellow": {"r": 1, "g": 1, "b": 0, "a": 1}, "黄": {"r": 1, "g": 1, "b": 0, "a": 1}, "黄色": {"r": 1, "g": 1, "b": 0, "a": 1},
        "white": {"r": 1, "g": 1, "b": 1, "a": 1}, "白": {"r": 1, "g": 1, "b": 1, "a": 1}, "白色": {"r": 1, "g": 1, "b": 1, "a": 1},
        "black": {"r": 0, "g": 0, "b": 0, "a": 1}, "黑": {"r": 0, "g": 0, "b": 0, "a": 1}, "黑色": {"r": 0, "g": 0, "b": 0, "a": 1},
        "orange": {"r": 1, "g": 0.65, "b": 0, "a": 1}, "橙": {"r": 1, "g": 0.65, "b": 0, "a": 1}, "橙色": {"r": 1, "g": 0.65, "b": 0, "a": 1},
        "purple": {"r": 0.5, "g": 0, "b": 0.5, "a": 1}, "紫": {"r": 0.5, "g": 0, "b": 0.5, "a": 1}, "紫色": {"r": 0.5, "g": 0, "b": 0.5, "a": 1},
        "pink": {"r": 1, "g": 0.75, "b": 0.8, "a": 1}, "粉": {"r": 1, "g": 0.75, "b": 0.8, "a": 1}, "粉色": {"r": 1, "g": 0.75, "b": 0.8, "a": 1},
        "cyan": {"r": 0, "g": 1, "b": 1, "a": 1}, "青色": {"r": 0, "g": 1, "b": 1, "a": 1},
        "gray": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}, "灰": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1}, "灰色": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1},
        "brown": {"r": 0.6, "g": 0.3, "b": 0, "a": 1}, "棕": {"r": 0.6, "g": 0.3, "b": 0, "a": 1}, "棕色": {"r": 0.6, "g": 0.3, "b": 0, "a": 1},
        "gold": {"r": 1, "g": 0.84, "b": 0, "a": 1}, "金": {"r": 1, "g": 0.84, "b": 0, "a": 1}, "金色": {"r": 1, "g": 0.84, "b": 0, "a": 1},
    }
    
    # 形状中文映射
    _SHAPE_MAP = {
        "cube": "Cube", "立方体": "Cube", "方块": "Cube", "正方体": "Cube", "盒子": "Cube",
        "sphere": "Sphere", "球": "Sphere", "球体": "Sphere",
        "cylinder": "Cylinder", "圆柱": "Cylinder", "圆柱体": "Cylinder",
        "capsule": "Capsule", "胶囊": "Capsule", "胶囊体": "Capsule",
        "plane": "Plane", "平面": "Plane", "地面": "Plane",
        "quad": "Quad", "面片": "Quad",
    }
    
    _UNITY_CONVENIENCE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "unity_create_object",
                "description": "在 Unity 中一键创建带颜色的物体。这是创建彩色 Unity 物体最简单的方式，一次调用即可完成所有步骤。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "物体名称，如 'RedCube'、'球体1'"
                        },
                        "shape": {
                            "type": "string",
                            "description": "形状：Cube/Sphere/Cylinder/Capsule/Plane/Quad（也支持中文：立方体/球体/圆柱体/胶囊体/平面/面片）",
                            "enum": ["Cube", "Sphere", "Cylinder", "Capsule", "Plane", "Quad",
                                     "立方体", "方块", "正方体", "球体", "球", "圆柱体", "圆柱",
                                     "胶囊体", "胶囊", "平面", "面片"]
                        },
                        "color": {
                            "type": "string",
                            "description": "颜色名称：red/green/blue/yellow/white/black/orange/purple/pink/cyan/gray/brown/gold（也支持中文：红色/绿色/蓝色/黄色等）"
                        },
                        "position": {
                            "type": "object",
                            "description": "可选，位置坐标",
                            "properties": {
                                "x": {"type": "number", "default": 0},
                                "y": {"type": "number", "default": 0},
                                "z": {"type": "number", "default": 0}
                            }
                        }
                    },
                    "required": ["name", "shape", "color"]
                }
            }
        }
    ]
    
    def unity_create_object(self, name: str, shape: str, color: str, position: dict = None) -> str:
        """
        一键创建带颜色的 Unity 物体。
        内部自动完成：创建物体 → 创建材质 → 设颜色 → 赋材质
        """
        # 检查 Unity MCP 是否连接
        client = getattr(self, '_mcp_clients', {}).get("ai-game-developer")
        if not client or not client.is_connected:
            return "❌ Unity MCP 未连接，请确保 Unity Editor 已打开"
        
        # 解析形状
        primitive_type = self._SHAPE_MAP.get(shape.lower(), shape)
        if primitive_type not in ("Cube", "Sphere", "Cylinder", "Capsule", "Plane", "Quad"):
            return f"❌ 不支持的形状: {shape}，支持: Cube/Sphere/Cylinder/Capsule/Plane/Quad"
        
        # 解析颜色
        color_rgba = self._COLOR_MAP.get(color.lower())
        if not color_rgba:
            return f"❌ 不支持的颜色: {color}，支持: red/green/blue/yellow/orange/purple/pink/cyan/gray/brown/gold/white/black"
        
        results = []
        
        # 步骤1：创建物体
        try:
            create_args = {"name": name, "primitiveType": primitive_type}
            if position:
                create_args["position"] = position
            r1 = client.call_tool("gameobject-create", create_args)
            results.append(f"✅ 创建了 {primitive_type}: {name}")
            logger.info(f"🎮 [Unity] 创建物体: {name} ({primitive_type})")
        except Exception as e:
            return f"❌ 创建物体失败: {e}"
        
        # 步骤2：创建材质
        mat_name = f"{name}Material"
        mat_path = f"Assets/Materials/{mat_name}.mat"
        try:
            r2 = client.call_tool("assets-material-create", {
                "assetPath": mat_path,
                "shaderName": "Standard"
            })
            results.append(f"✅ 创建了材质: {mat_path}")
        except Exception as e:
            results.append(f"⚠️ 创建材质失败: {e}（物体已创建但无颜色）")
            return "\n".join(results)
        
        # 步骤3：修改材质颜色（使用 props，不是 fields！）
        try:
            r3 = client.call_tool("assets-modify", {
                "assetRef": {"path": mat_path},
                "content": {
                    "props": [
                        {
                            "name": "_Color",
                            "typeName": "UnityEngine.Color",
                            "value": color_rgba
                        }
                    ]
                }
            })
            results.append(f"✅ 设置颜色: {color} → {color_rgba}")
        except Exception as e:
            results.append(f"⚠️ 设置颜色失败: {e}（尝试赋材质）")
        
        # 步骤4：将材质赋给物体的 MeshRenderer
        try:
            r4 = client.call_tool("gameobject-component-modify", {
                "gameObjectRef": {"name": name},
                "componentRef": {"typeName": "UnityEngine.MeshRenderer"},
                "componentDiff": {
                    "props": [
                        {
                            "name": "material",
                            "typeName": "UnityEngine.Material",
                            "value": {"path": mat_path}
                        }
                    ]
                }
            })
            results.append(f"✅ 材质已赋给 {name}")
        except Exception as e:
            # 尝试备用方案：用 sharedMaterial
            try:
                r4b = client.call_tool("gameobject-component-modify", {
                    "gameObjectRef": {"name": name},
                    "componentRef": {"typeName": "UnityEngine.MeshRenderer"},
                    "componentDiff": {
                        "props": [
                            {
                                "name": "sharedMaterial",
                                "typeName": "UnityEngine.Material",
                                "value": {"path": mat_path}
                            }
                        ]
                    }
                })
                results.append(f"✅ 材质已赋给 {name} (via sharedMaterial)")
            except Exception as e2:
                # 最后备用：用 fields m_Materials
                try:
                    r4c = client.call_tool("gameobject-component-modify", {
                        "gameObjectRef": {"name": name},
                        "componentRef": {"typeName": "UnityEngine.MeshRenderer"},
                        "componentDiff": {
                            "fields": {
                                "m_Materials": [{"path": mat_path}]
                            }
                        }
                    })
                    results.append(f"✅ 材质已赋给 {name} (via m_Materials)")
                except Exception as e3:
                    results.append(f"⚠️ 赋材质失败: {e3}（请手动拖拽材质 {mat_path} 到物体上）")
        
        return "\n".join(results)