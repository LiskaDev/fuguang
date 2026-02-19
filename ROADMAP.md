# 🗺️ FUGUANG ROADMAP — AI 协作开发指南

> **本文档是给 AI 看的开发路线图。**
> 每个任务包含：背景、具体做法、涉及文件、验证方式。
> 使用时直接把相关章节粘贴给 AI，它就能开始干活。

---

## 📋 项目档案（AI 必读）

```
项目名称: 扶光 (Fuguang) — 桌面 AI 助手
语言: Python 3.11
环境: Conda (D:\conda\envs\fuguang)
入口: run.py (语音模式) / webui.py (Web模式)
核心: src/fuguang/core/
测试: pytest, 84 个测试, 全部通过
Git: GitHub private repo, main 分支
LLM: DeepSeek (对话) + GLM-4V (视觉)
```

### 架构速览

```
src/fuguang/core/
├── nervous_system.py   # 神经系统 — 主循环、按键监听、心跳
├── brain.py            # 大脑 — LLM 对话、Function Calling、记忆检索
├── skills/             # 技能包 — Mixin 多继承
│   ├── base.py         #   基础类 + __init__
│   ├── __init__.py     #   SkillManager 组合器 + execute_tool 路由
│   ├── vision.py       #   视觉 — GLM-4V 截屏/图片分析
│   ├── gui.py          #   GUI — UIA + OCR + 鼠标键盘
│   ├── browser.py      #   浏览器 — 搜索/阅读/深度浏览
│   ├── system.py       #   系统 — Shell/文件/提醒/音量
│   ├── memory.py       #   记忆 — ChromaDB 三集合
│   ├── email.py        #   邮件 — IMAP 监控 + SMTP 发送 + 附件
│   └── skill_mcp.py    #   MCP — GitHub/Obsidian 外部协议
├── memory.py           # 记忆库 — ChromaDB (对话/知识/配方)
├── ears.py             # 耳朵 — 麦克风 + ASR + 唤醒词
├── eyes.py             # 眼睛 — 截屏 + GLM-4V
├── mouth.py            # 嘴巴 — TTS + Unity 指令
└── config.py           # 配置 — 运行时参数
```

### 配置链路

```
.env → src/fuguang/config.py (GlobalConfig) → src/fuguang/core/config.py (CoreConfig)
```

新增配置项必须三个文件都加。

---

## 🏷️ 任务状态说明

- `[ ]` 未开始
- `[/]` 进行中
- `[x]` 已完成
- `[-]` 搁置/不做

---

## Phase 1: 基础设施升级（让项目可分享）

### 1.1 [ ] 一键安装脚本 (setup.bat / setup.py)

**背景**: 目前新用户需要手动装 Conda、创环境、装 PyTorch、配 .env，门槛太高。

**具体做法**:

1. 创建 `setup.bat`（Windows 批处理）:
   - 检测是否已安装 Conda，未安装则提示下载链接
   - 自动创建 `fuguang` 环境 + 安装 Python 3.11
   - 自动安装 PyTorch + CUDA（检测 GPU 型号选版本）
   - `pip install -r requirements.txt`
   - `playwright install chromium`
   - 交互式引导配置 `.env`（输入 DeepSeek API Key 等）

2. 创建 `setup.py`（Python 版，跨平台）:
   - 检测环境、安装依赖
   - 生成 `.env` 模板并引导填写
   - 验证配置是否正确（测试 API 连通性）

**涉及文件**:
- `[NEW] setup.bat` — Windows 一键安装
- `[NEW] setup.py` — Python 跨平台安装
- `[NEW] .env.example` — 环境变量模板（不含真实密钥）
- `[MODIFY] README.md` — 简化安装说明，指向 setup 脚本

**验证方式**:
- 删除 Conda 环境，从零运行 setup.bat，验证能否成功启动
- `.env.example` 包含所有必需配置项及注释

---

### 1.2 [ ] 渐进式功能模式（无 GPU 也能用）

**背景**: 不是所有人都有 NVIDIA GPU。应该支持"纯文字模式"（无视觉/无语音）。

**具体做法**:

1. `config.py` 新增 `RUN_MODE`:
   ```python
   # 运行模式
   RUN_MODE = os.getenv("RUN_MODE", "full")
   # "full"   = 语音 + 视觉 + GUI (需要 GPU)
   # "lite"   = 纯文字 + 工具调用 (无需 GPU)
   # "web"    = WebUI 模式 (无需音频设备)
   ```

2. `base.py` 的 `__init__` 根据模式跳过初始化:
   - `lite` 模式: 跳过 vision_client、ears、mouth 初始化
   - 保留: shell、文件、邮件、记忆、MCP

3. `requirements.txt` 拆分:
   - `requirements-base.txt` — 核心依赖（openai、chromadb、schedule等）
   - `requirements-full.txt` — 完整依赖（torch、pyaudio、pywinauto等）

**涉及文件**:
- `[MODIFY] src/fuguang/config.py` — 新增 RUN_MODE
- `[MODIFY] src/fuguang/core/config.py` — 传递 RUN_MODE
- `[MODIFY] src/fuguang/core/skills/base.py` — 条件初始化
- `[MODIFY] src/fuguang/core/nervous_system.py` — lite 模式跳过语音循环
- `[NEW] requirements-base.txt`
- `[NEW] requirements-full.txt`

**验证方式**:
```bash
# 在无 GPU 机器上测试
RUN_MODE=lite python run.py
# 应该能正常启动，支持文字对话和工具调用
```

---

## Phase 2: 核心架构升级

### 2.1 [ ] 多模型支持（LLM 抽象层）

**背景**: 目前 `brain.py` 直接调用 DeepSeek API。如果 DeepSeek 挂了或用户想用其他模型，无法切换。OpenClaw 和 Open-Interpreter 都支持模型无关。

**具体做法**:

1. 新建 `src/fuguang/core/llm_provider.py`:
   ```python
   class LLMProvider:
       """LLM 抽象层 — 统一接口"""
       def chat(self, messages, tools=None, temperature=0.7) -> dict:
           raise NotImplementedError
       
   class DeepSeekProvider(LLMProvider):
       """DeepSeek API"""
       ...
   
   class OpenAIProvider(LLMProvider):
       """OpenAI GPT-4o / GPT-4"""
       ...
   
   class OllamaProvider(LLMProvider):
       """本地 Ollama (Llama3/Qwen2 等)"""
       ...
   
   class AutoFallbackProvider(LLMProvider):
       """自动降级: 主模型超时 → 备用模型"""
       def __init__(self, primary: LLMProvider, fallback: LLMProvider):
           ...
   ```

2. `.env` 新增:
   ```env
   # LLM 提供商 (deepseek / openai / ollama)
   LLM_PROVIDER=deepseek
   LLM_FALLBACK_PROVIDER=ollama
   
   # OpenAI (可选)
   OPENAI_API_KEY=
   OPENAI_MODEL=gpt-4o
   
   # Ollama (可选, 本地模型)
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:14b
   ```

3. `brain.py` 改用 `LLMProvider` 接口，不直接 import openai:
   ```python
   # 之前
   self.client = OpenAI(api_key=..., base_url=...)
   response = self.client.chat.completions.create(...)
   
   # 之后
   self.llm = create_provider(config)  # 根据配置创建对应 Provider
   response = self.llm.chat(messages, tools=tools)
   ```

**涉及文件**:
- `[NEW] src/fuguang/core/llm_provider.py` — LLM 抽象层
- `[MODIFY] src/fuguang/core/brain.py` — 改用 Provider 接口
- `[MODIFY] .env` — 新增 LLM 配置
- `[MODIFY] src/fuguang/config.py` + `core/config.py` — 新增配置项
- `[NEW] tests/test_llm_provider.py` — Provider 单元测试

**验证方式**:
```bash
# 测试 DeepSeek
LLM_PROVIDER=deepseek python -c "from fuguang.core.llm_provider import create_provider; ..."

# 测试 Ollama 本地
LLM_PROVIDER=ollama python -c "..."

# 测试自动降级
LLM_PROVIDER=deepseek LLM_FALLBACK_PROVIDER=ollama python run.py
# 断网后应自动切换到 Ollama
```

---

### 2.2 [ ] 持久化调度系统（关机任务不丢）

**背景**: 当前 `set_reminder` 存在内存中，重启扶光后所有定时任务丢失。用户无法可靠地设置未来的定时邮件、生日提醒等。

**具体做法**:

1. 新建 `data/schedules.json` 持久化文件:
   ```json
   [
     {
       "id": "uuid",
       "type": "reminder",
       "trigger_time": "2026-02-29T00:00:00",
       "action": "send_email",
       "params": {"to": "bear@qq.com", "subject": "生日快乐", "content": "..."},
       "status": "pending",
       "created_at": "2026-02-19T23:00:00"
     }
   ]
   ```

2. 修改 `system.py` 的 `set_reminder`:
   - 新建提醒时写入 `schedules.json`
   - 启动时加载所有 pending 任务
   - 到期执行后标记 `completed`
   - 过期未执行的任务标记 `missed`，下次启动时通知用户

3. 新增 `list_schedules` / `cancel_schedule` 工具

**涉及文件**:
- `[MODIFY] src/fuguang/core/skills/system.py` — 持久化 set_reminder
- `[MODIFY] src/fuguang/core/skills/base.py` — 启动时加载 schedules
- `[MODIFY] src/fuguang/core/skills/__init__.py` — 新增路由
- `[NEW] tests/test_scheduler.py`

**验证方式**:
```
1. 设置一个 5 分钟后的提醒
2. 关闭 run.py
3. 重新启动 run.py
4. 验证提醒仍然存在并按时触发
```

---

## Phase 3: 体验增强

### 3.1 [ ] WebUI 增强 — 远程控制 + 移动端适配

**背景**: 当前 WebUI 只是本地聊天界面。应该支持手机浏览器远程控制。

**具体做法**:

1. `webui.py` 启用局域网访问:
   ```python
   demo.launch(server_name="0.0.0.0", server_port=7860)
   ```

2. 新增移动端 CSS 适配（Gradio 自带响应式，但需微调）

3. 新增功能面板:
   - 📧 邮件快捷操作（查邮件/发邮件）
   - ⏰ 定时任务管理（查看/取消）
   - 📊 系统状态（记忆/MCP/邮件）

4. 可选: 添加简单的 PIN 码认证

**涉及文件**:
- `[MODIFY] webui.py` — 远程访问 + 功能面板 + PIN 认证

**验证方式**:
- 手机连同一 WiFi，访问 `http://<电脑IP>:7860`
- 在手机上发消息、查邮件

---

### 3.2 [ ] 每日成长日报（自动邮件推送）

**背景**: 利用已有的 `notify_commander` + 邮件系统，每天自动发一封"今日总结"。

**具体做法**:

1. 在 `nervous_system.py` 心跳循环中加入每日检查:
   ```python
   # 每天 22:00 触发
   if now.hour == 22 and not self._daily_report_sent_today:
       self._send_daily_report()
       self._daily_report_sent_today = True
   ```

2. `_send_daily_report()` 收集:
   - 今日对话次数
   - 工具调用统计（哪些工具用了几次）
   - 新学到的配方
   - 邮件处理统计
   - 用 LLM 生成一段简短的人格化总结

3. 通过 `notify_commander` 发送

**涉及文件**:
- `[MODIFY] src/fuguang/core/nervous_system.py` — 每日触发逻辑
- `[MODIFY] src/fuguang/core/brain.py` — 暴露今日统计数据

**验证方式**:
- 手动触发 `_send_daily_report()`，验证收到邮件
- 验证邮件内容包含当天统计

---

### 3.3 [ ] 英文 README + 项目包装

**背景**: 开源项目想获得关注，GitHub 上的国际开发者只看英文。

**具体做法**:

1. 新建 `README_EN.md`，翻译核心内容（不需要全部翻译）:
   - 项目介绍 + 架构图
   - Quick Start（5 步跑起来）
   - 功能截图 / GIF 演示
   - Architecture 表格

2. `README.md` 顶部加语言切换:
   ```markdown
   [🇨🇳 中文](README.md) | [🇬🇧 English](README_EN.md)
   ```

3. 可选: 录制一个 2 分钟演示视频（语音对话 → 执行任务 → 邮件发送）

**涉及文件**:
- `[NEW] README_EN.md`
- `[MODIFY] README.md` — 加语言切换链接

---

## Phase 4: 高级功能（长期方向）

### 4.1 [ ] 微信/QQ 消息入口

**背景**: OpenClaw 的杀手锏是 WhatsApp 入口。中国用户最常用微信/QQ。

**具体做法**: 使用 `itchat`（微信）或 `nonebot2`（QQ Bot）接入。

**注意**: 微信限制严格，QQ Bot 需要申请。这是长期方向。

### 4.2 [ ] 语音克隆 / 自定义 TTS 音色

**背景**: 让扶光真正有"独特的声音"。

**具体做法**: 接入 GPT-SoVITS 或 Fish-Speech 开源项目。

### 4.3 [ ] 本地小模型加速

**背景**: 邮件分类、垃圾过滤等简单任务不需要调 API，本地小模型更快更省钱。

**具体做法**: 用 Ollama 跑 Qwen2.5-7B 处理低级任务，复杂任务仍用 DeepSeek。

---

## 开发规范（AI 必读）

1. **配置三文件同步**: `.env` → `config.py` → `core/config.py`
2. **每次改动必须测试**: `python -m pytest tests/ --tb=short` 全部通过
3. **Git 提交格式**: `feat: 中文描述` / `fix: 中文描述` / `test: 中文描述`
4. **新增工具必须**:
   - 在对应 Mixin 的 `_XXX_TOOLS` 添加 Schema
   - 在 `__init__.py` 的 `execute_tool` 添加路由
   - 在 `tests/test_tool_routing.py` 的 `REQUIRED_TOOLS` 添加工具名
5. **代码风格**: 中文注释、docstring 标准格式、logger 而非 print
6. **Conda 环境**: `D:\conda\envs\fuguang\python.exe`
