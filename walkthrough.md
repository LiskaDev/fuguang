# 扶光 (Fuguang) 项目架构总结

## 一句话概括

**AI 桌面宠物助手** — 悬浮球形态，Lottie 矢量表情，语音对话，接入 60+ 工具，支持 QQ 桥接和 Web UI。当前版本 v6.7。

---

## 目录结构

```
fuguang/
├── config/
│   ├── system_prompt.txt    # AI 人设 + 核心规则 (~25KB)
│   └── soul.md              # 扶光的自述文件（AI可自行更新）
├── src/fuguang/
│   ├── core/                # 🧠 核心逻辑层
│   │   ├── nervous_system.py   # 总控制器（主循环、状态机、信号分发）~50KB
│   │   ├── brain.py            # AI 大脑（LLM对话、Function Calling、潜意识记忆、性能学习）~28KB
│   │   ├── mouth.py            # 输出（TTS语音 + Unity UDP + VTS嘴巴回调注入）
│   │   ├── ears.py             # 输入（语音识别入口）
│   │   ├── eyes.py             # 视觉（截屏分析 + 剪贴板感知）
│   │   ├── memory.py           # 长期记忆（ChromaDB 三集合 RAG）~35KB
│   │   ├── chat_store.py       # 对话历史持久化（SQLite）
│   │   ├── qq_bridge.py        # QQ消息桥接（NapCat WebSocket）~27KB
│   │   ├── web_bridge.py       # Web UI 后端（FastAPI + WebSocket）~28KB
│   │   ├── vtube_bridge.py     # VTube Studio 集成（WebSocket、表情、嘴巴、自然运动）~25KB
│   │   ├── tool_scanner.py     # 工具自动扫描（docstring → Schema）
│   │   ├── config.py           # 配置管理（核心层）
│   │   └── skills/             # 11个技能Mixin（见下方）
│   ├── gui/                 # 🎨 GUI 层（PyQt6）
│   │   ├── app.py              # 主应用（信号中心、工作线程、回调注入）
│   │   ├── ball.py             # 悬浮球（Lottie表情、拖拽、状态机）~21KB
│   │   ├── hud.py              # HUD气泡（Markdown渲染、字幕显示）~18KB
│   │   ├── lottie_player.html  # Lottie动画播放器（WebView加载）
│   │   └── emotions/           # 62个Lottie JSON表情文件
│   ├── config.py            # 配置管理（包级别）
│   ├── voice.py             # TTS核心（CosyVoice2 PCM流式 + pyaudio + RMS嘴巴 + edge-tts降级）
│   ├── ali_ear.py / heartbeat.py / camera.py
├── tests/                   # 13个测试文件
├── data/                    # 运行时数据（web_chat.db / memory_db/ / vts_token.txt）
├── 启动扶光GUI.bat / 启动扶光.bat
└── .env                     # API密钥和配置
```

---

## 核心信号流

```
用户说话/点击悬浮球
    → Ears (ASR) 或 GUI 点击
    → NervousSystem._process_input()
        → 本地快捷？（音量/时间/状态）→ 直接响应
        → 否 → _handle_ai_response()
            → Memory (RAG检索) → 注入记忆上下文
            → Eyes (感知) → 注入窗口/剪贴板
            → Brain.chat() (Function Calling 循环, 最多15轮, 当前 stream=False)
            → _process_response()
                → 提取 [Joy]/[Sorrow] 等表情标签
                → VTS trigger_expression() + GUI set_expression()
                → 清洁文本 → mouth.speak() → HUD字幕 → TTS播放
                → 说完 → HUD清空 → IDLE → 8秒后开始随机轮播表情
```

---

## VTube Studio 集成 (v6.7)

| 组件 | 功能 |
|------|------|
| [vtube_bridge.py](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/core/vtube_bridge.py) | WebSocket 连接 VTS，认证+token持久化，7个自定义参数（AI* 开头） |
| `NaturalMotion` | 随机头部/眼球/眨眼运动，`_keep_alive`循环每帧注入 |
| `set_mouth_open(value)` | 直接设 `_mouth_value`，`_speaking`自动跟随 |
| `trigger_expression(emotion)` | 表情标签→VTS热键，自动切换/防叠加 |

**嘴巴同步链路**：
```
voice.py on_mouth_update回调 → mouth.py注入 → vtube_bridge.set_mouth_open(rms)
                                                → _keep_alive → InjectParam MouthOpen
```

---

## TTS 系统 (当前状态)

**优先级**：CosyVoice2 PCM 流式 → edge-tts + pygame 降级

| 路径 | 引擎 | 播放 | 嘴巴驱动 |
|------|------|------|----------|
| 主路径 | SiliconFlow CosyVoice2 | pyaudio 实时 PCM | RMS 音量（smoothed = 0.4*prev + 0.6*current） |
| 降级 | edge-tts | pygame mp3 | 固定 0.8 |

**关键参数**（`voice.py` 顶部）：
- `RMS_MAX = 5000.0`（归一化上限）
- `RMS_SMOOTH_FACTOR = 0.6`（平滑系数）
- `PCM_SAMPLE_RATE = 24000`
- `PCM_CHUNK_SIZE = 4096`

**Azure TTS** 已尝试但回退，key 保留在 .env（以后可能再用）。两个 config.py 里的 Azure 配置已回退。

---

## 技能系统（11 个 Mixin 多继承）

```python
class SkillManager(
    BaseSkillMixin,       # 共享初始化
    VisionSkills,         # GLM-4V 截屏/图片分析
    GUISkills,            # UIA + OCR 桌面控制 (27KB)
    BrowserSkills,        # 搜索/阅读/Playwright 无头浏览器 (26KB)
    SystemSkills,         # Shell/文件/提醒/音量 (33KB)
    MemorySkills,         # ChromaDB 三集合操作
    MCPSkills,            # GitHub/Obsidian/Unity MCP (44KB)
    EmailSkills,          # IMAP监控 + SMTP发送 + 附件 (95KB!)
    BilibiliSkills,       # B站搜索/播放
    FileGeneratorSkills,  # CSV/XLSX/DOCX/PDF 生成
    FigmaSkills,          # Figma API
    EverythingSkills,     # 本地文件极速搜索
)
```

[execute_tool()](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/core/skills/__init__.py#118-368) 是统一路由入口（379行 if-elif）。MCP 工具名以 `mcp_` 前缀自动路由。

---

## 记忆系统（ChromaDB 三集合）

| 集合 | 用途 | 写入方式 |
|------|------|----------|
| `fuguang_memories` | 对话记忆（事实/偏好） | 潜意识自动提取（后台LLM分析） |
| `fuguang_knowledge` | 知识库（文件内容） | 用户拖拽文件到悬浮球 |
| `fuguang_recipes` | 技能配方（肌肉记忆） | 慢操作自动学习 + 手动存储 |

---

## 表情系统

| 概念 | 说明 |
|------|------|
| `EXPRESSION_EMOJI_MAP` | 15个标签 → 每个标签3-5个Lottie文件名列表（共59个） |
| [set_expression()](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/gui/ball.py#368-380) | `random.choice()` 从组内随机抽一个播放 |
| `_expression_override` | AI指定表情后锁定，防止SPEAKING状态覆盖 |
| [_idle_timer](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/gui/ball.py#348-353) | IDLE 8秒后开始，每5-8秒随机切换 |
| 渲染方式 | QWebEngineView + dotlottie-player，CSS scaleY() 压扁弹开过渡 |

---

## 已知坑点

| # | 坑 | 说明 |
|---|------|------|
| 1 | 两个 config.py | [src/fuguang/config.py](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/config.py)（默认值）+ [core/config.py](file:///c:/Users/ALan/Desktop/fuguang/src/fuguang/core/config.py)（运行时），新增配置两个都要加 |
| 2 | 配置三文件同步 | [.env](file:///c:/Users/ALan/Desktop/fuguang/.env) → config.py → core/config.py，漏一个就读不到 |
| 3 | system_prompt.txt | 变量替换用 `str.replace()` 链式调用，**禁止改回 `str.format()`**（模板里有 JSON `{}` 会炸） |
| 4 | .env 修改 | **只追加/单行替换，禁止整体重写**（之前因此丢过 API key） |
| 5 | email.py 95KB | 单文件过大，IMAP+SMTP+附件+AI邮箱+过滤全在一个文件 |
| 6 | execute_tool 路由 | 379行 if-elif，无注册表模式 |

---

## 环境

- **Python**: conda 环境 `fuguang`（`D:\conda\envs\fuguang`），Python 3.11
- **框架**: PyQt6 + QWebEngineView
- **AI后端**: DeepSeek（对话）+ GLM-4V（视觉），配置在 `.env`
- **TTS**: SiliconFlow CosyVoice2 PCM + pyaudio，edge-tts 降级
- **VTS**: VTube Studio WebSocket API（ws://localhost:8001）
- **已安装**: pyaudio, numpy, azure-cognitiveservices-speech（备用）
- **PYTHONPATH**: `src`
- **入口**: `启动扶光GUI.bat` → `python -m fuguang.gui.app`

---

## 待执行任务：DeepSeek 流式响应

> 实现计划在 `implementation_plan.md`，已审批通过。

**目标**：将 `brain.chat()` 从 `stream=False` 改为 `stream=True`，分句流式送 TTS，首句延迟从 5-10秒降到 1-2秒。

**方案**：全程 `stream=True` + 双模式处理：
- content delta → 分句缓冲（`。！？…\n` 断句）→ `on_sentence(text, expression)` 回调
- tool_calls delta → 按 index 累积 → 执行工具 → continue 下一轮

**⚠️ 关键线程问题**：
`on_sentence` 回调里调 `mouth.speak()` 是阻塞的（有 `_speak_lock`），**不能在 stream 迭代线程里直接调用**，否则 TTS 播放会卡住 chunk 接收。**必须用队列 + 独立消费线程**：
```
stream 迭代线程 → sentence_queue.put(sentence)  → 不阻塞
TTS 播放线程   → sentence_queue.get() → mouth.speak()  → 阻塞等播完
```

**改动范围**：只改 `brain.py` 和 `nervous_system.py`，其他文件不动。
- `_process_response()` 保留（QQ/Web 端还在用）
- `voice.py` / `mouth.py` / `vtube_bridge.py` 不改

---

## 开新对话快速上下文

**项目**：扶光 AI 桌面宠物（`c:\Users\ALan\Desktop\fuguang`），v6.7

**架构**：仿生器官（NervousSystem 总控 + Brain/Ears/Eyes/Mouth），11个 Skill Mixin 组合 60+ 工具

**核心文件**：
- 主控：`core/nervous_system.py` → AI对话：`core/brain.py` → TTS：`voice.py` + `core/mouth.py`
- VTS：`core/vtube_bridge.py`（WebSocket 嘴巴/表情/自然运动）
- GUI：`gui/app.py`（信号中心）→ `gui/ball.py`（悬浮球/表情）→ `gui/hud.py`（字幕）
- 配置：`config/system_prompt.txt`（人设）+ `.env`（API keys）

**关键机制**：表情分组随机 → IDLE轮播 → HUD自动隐藏 → 配方强制注入 → 潜意识自动记忆 → VTS嘴巴RMS驱动

**已知坑**：两个 config.py 配置三文件同步 + .env 禁止整体重写
