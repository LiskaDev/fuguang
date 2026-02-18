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
        
        github_token = getattr(self.config, 'GITHUB_TOKEN', '')
        if not github_token:
            logger.info("ℹ️ [MCP] 未配置 GITHUB_TOKEN，跳过 GitHub MCP")
            return
        
        # 注册 GitHub MCP Server
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
    
    def _shutdown_mcp(self):
        """关闭所有 MCP 连接"""
        for name, client in getattr(self, '_mcp_clients', {}).items():
            try:
                client.disconnect()
            except Exception as e:
                logger.warning(f"⚠️ [MCP] 关闭 {name} 失败: {e}")
    
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
        
        logger.info(f"🧩 [MCP:{server_name}] 调用工具: {tool_name}({json.dumps(func_args, ensure_ascii=False)[:100]})")
        result = client.call_tool(tool_name, func_args)
        logger.info(f"✅ [MCP:{server_name}] {tool_name} 执行完成 ({len(result)} 字符)")
        return result