
# 🌌 Fuguang (扶光系统)

AI 桌面宠物助手 — 悬浮球形态，Lottie 矢量表情，语音对话，接入多种 MCP 工具。

> **当前版本**：v6.7 | **详细更新记录**：[CHANGELOG.md](CHANGELOG.md)

---

## ✨ 核心能力

| 模块 | 能力 |
|------|------|
| 🎭 **表情系统** | 59 个 Lottie 矢量表情，15 组分组随机，IDLE 时自动轮播 |
| 🗣️ **语音对话** | 阿里云语音识别 + TTS，按住说话 / 打字输入双模式 |
| 🧠 **AI 大脑** | DeepSeek 驱动，长期记忆（RAG 向量检索），配方记忆系统 |
| 🔧 **MCP 工具** | GitHub / Obsidian / Unity (60+ 工具) / Browser (Playwright) |
| 🎭 **VTube Studio** | WebSocket 桥接，Live2D 表情切换 + 嘴巴张合 + 自然运动（摇头/眼球/眨眼） |
| 🎨 **更多集成** | Figma API / Everything 文件搜索 / 邮件监控 / QQ 桥接 |
| 🖥️ **多端访问** | 桌面 GUI (PyQt6) + Web UI + QQ 消息 |

---

## 🏗️ 架构概览

```
src/fuguang/
├── core/                    🧠 核心逻辑层
│   ├── nervous_system.py       总控制器（主循环、AI对话、工具调用）
│   ├── brain.py                AI 大脑（prompt加载、对话管理）
│   ├── mouth.py                输出（TTS + Unity UDP）
│   ├── ears.py                 输入（语音识别）
│   ├── eyes.py                 视觉（截屏分析）
│   ├── memory.py               长期记忆（RAG）
│   ├── chat_store.py           对话历史持久化
│   ├── qq_bridge.py            QQ 消息桥接
│   ├── web_bridge.py           Web UI 后端
│   ├── vtube_bridge.py         VTube Studio 桥接（Live2D 外观）
│   ├── browser.py              浏览器 MCP
│   ├── tool_scanner.py         MCP 工具扫描注册
│   └── skills/                 技能模块（Figma/Everything/...）
├── gui/                     🎨 GUI 层（PyQt6）
│   ├── app.py                  主应用（信号中心、工作线程）
│   ├── ball.py                 悬浮球（Lottie表情、状态机）
│   ├── hud.py                  HUD气泡（Markdown字幕）
│   ├── lottie_player.html      Lottie 播放器
│   └── emotions/               62 个 Lottie JSON 表情文件
├── voice.py                 TTS 语音合成
├── ali_ear.py               阿里云语音识别
├── heartbeat.py             心跳 / 活跃度管理
└── config.py                配置管理

config/
├── system_prompt.txt        AI 人设 + 核心规则
└── soul.md                  扶光的自述（AI可更新）
```

设计理念：**仿生架构** — 每个模块对应一个"器官"（大脑/嘴巴/耳朵/眼睛），NervousSystem 是"神经系统"总控。

---

## 🚀 快速开始

### 环境准备

```bash
# 1. 创建 conda 环境
conda create -n fuguang python=3.11
conda activate fuguang

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 等
```

### 启动

```bash
# GUI 模式（悬浮球）
双击 启动扶光GUI.bat
# 或手动：set PYTHONPATH=src && python -m fuguang.gui.app

# 命令行模式（无GUI）
双击 启动扶光.bat
# 或手动：set PYTHONPATH=src && python -m fuguang.gui.app --no-gui
```

---

## 🎭 表情系统

15 个表情标签，每个对应 3-5 个 Lottie 动画变体，切换时随机抽取：

| 标签 | 变体数 | 示例 |
|------|--------|------|
| Joy | 4 | joy / grin / laughing / rofl |
| Fun | 5 | fun / wink / zany / yum / imp_smile |
| Love | 4 | love / heart_eyes / kissing_heart / heart_face |
| Shy | 4 | shy / blush / warm_smile / hand_over_mouth |
| Angry | 5 | angry / triumph / unamused / rage / imp_frown |
| Sorrow | 4 | sorrow / loudly_crying / sad / concerned |
| ... | ... | _共 15 组 59 个表情_ |

**IDLE 轮播**：闲置 8 秒后，每 5-8 秒从全部 15 组里随机切换一个表情。

---

## 📋 信号流

```
用户说话 → ears → nervous_system → brain（AI推理）
    → _process_response()
        → 表情标签 [Joy] → ball.set_expression() → 随机抽 emoji
        → 清洁文本 → mouth.speak()
            → HUD 显示字幕 → TTS 播放 → HUD 自动隐藏
            → 状态 → IDLE → idle_timer 启动
```

---

## 🎭 VTube Studio 集成

通过 WebSocket 连接 VTube Studio API，控制 Live2D 模型的表情和动作。

| 功能 | 说明 |
|------|------|
| 表情切换 | AI 生成的表情标签 (Joy/Angry/...) → VTS 热键，自动 toggle off 上一个 |
| 嘴巴张合 | TTS 说话时 MouthOpen=0.8，结束后主动发 0.0 |
| 自然运动 | 随机摇头/眼球转动/眨眼（10fps 持续注入） |
| 认证 | Token 自动持久化到 `data/vts_token.txt`，首次连接需 VTS 弹窗授权 |
| 降级 | VTS 未运行时静默降级，不影响扶光正常运行 |

配置（`.env`）：
```bash
VTS_ENABLED=true
VTS_PORT=8001
```

---

## ⚠️ 已知注意事项

- **两个 config.py**：`src/fuguang/config.py`（包级别）和 `src/fuguang/core/config.py`（核心层），历史原因并存
- **system_prompt.txt**：变量替换用 `str.replace()`，不能用 `str.format()`（模板里有 JSON `{}`）
- **环境**：conda `fuguang`，`PYTHONPATH=src`

---

## 📜 更新记录

详见 [CHANGELOG.md](CHANGELOG.md)。