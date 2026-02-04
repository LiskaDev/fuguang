
# 🌌 Fuguang IDE (扶光系统)

这里是扶光系统的核心工程目录。本项目采用 **OOP (面向对象)** 架构，模仿生物体器官进行分层设计。

## 🏥 核心架构说明 (System Architecture)

所有的核心逻辑都位于 `src/fuguang/core/` 目录下。任何 AI 或开发者在修改代码前，请先阅读下表：

| 文件路径 (`src/fuguang/core/`) | 对应器官 | 职责描述 (Responsibility) | 常见修改场景 |
| :--- | :--- | :--- | :--- |
| **`nervous_system.py`** | **神经系统** | **总指挥**。负责主循环、按键监听 (PTT)、协调各器官工作。 | 修改按键逻辑、调整交互流程、修改心跳机制。 |
| **`brain.py`** | **大脑** | **思考与记忆**。负责调用 LLM API、管理对话历史 (Context)、加载 System Prompt。 | 修改 System Prompt、更换 AI 模型、调整记忆长度。 |
| **`skills.py`** | **手/技能** | **执行**。负责所有 Function Calling 工具（搜索、打开App、写文件）。 | **这是最常修改的文件**。增加新功能（如关机、查天气）都在这里。 |
| **`ears.py`** | **耳朵** | **听觉**。负责麦克风录音、ASR 语音识别、唤醒词检测。 | 调整麦克风灵敏度、修改唤醒词、更换语音识别服务。 |
| **`mouth.py`** | **嘴巴** | **表达**。负责 TTS 语音合成、发送表情/动作指令给 Unity。 | 更换 TTS 音色、对接新的 Unity 动画事件。 |
| **`config.py`** | **管家** | **配置**。负责管理 API Key、路径常量、全局参数。 | 更新 API Key、修改文件保存路径、修改 IP 端口。 |

---

## 📏 开发规范 (Development Rules)

1.  **每次编辑后必须测试**：修改任何 `.py` 文件后，运行 `python run.py` 确认无报错再提交。
2.  **配置文件分工**：
    - API 密钥 → 编辑 **`.env`** 文件
    - 功能开关 → 编辑 **`src/fuguang/config.py`**
    - 新增配置项 → 两个 config.py 都要加（外层定义，内层复制）
3.  **IDE 模式 (`ide.py`)**：由 AI 辅助维护。核心逻辑复用 `core/` 下的代码。
4.  **Study 模式 (`fuguang_study.py`)**：用户的试验田。目前为独立单体脚本。
5.  **核心修改**：如果修改了 `core/` 下的代码，会同时影响到所有引用它的入口。

---

## � 概念文档 (Concepts)

如果你对以下概念感到困惑，请阅读对应文档：

| 文档 | 内容 |
| :--- | :--- |
| **[Function Calling vs Skill vs MCP](docs/concepts_comparison.md)** | 三种 AI 扩展能力的直观对比，包含扶光实际代码示例 |

---

## ⚠️ 常见坑点 (Common Pitfalls)

> 以下是开发过程中遇到的典型问题，**AI 助手和开发者必读**！

### 坑点 #1：路径计算层级错误

**问题表现**：`system_prompt.txt` 无法加载，AI 人设丢失，回复变成默认机械风格。

**根本原因**：`core/config.py` 中的 `PROJECT_ROOT` 路径计算错误。

```python
# ❌ 错误写法（少算了一级）
self.PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # 指向 src/

# ✅ 正确写法
self.PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # 指向 fuguang/
```

**路径追踪**：
```
__file__ = src/fuguang/core/config.py
parent   = core/
parent^2 = fuguang/
parent^3 = src/         ← 错误！
parent^4 = fuguang/     ← 正确！（项目根目录）
```

**预防措施**：修改任何 `Path(__file__)` 路径时，务必在控制台打印验证。

### 坑点 #2：两个 config.py 文件

**问题表现**：新增配置项后，运行时读不到值。

**根本原因**：项目有两个 config.py，新增配置时两个都要加。

| 文件 | 作用 |
| :--- | :--- |
| `src/fuguang/config.py` | 定义默认值（静态类属性） |
| `src/fuguang/core/config.py` | 运行时使用（复制外层值 + 额外属性） |

**正确做法**：
```python
# 1. 先在 src/fuguang/config.py 添加
class ConfigManager:
    MY_NEW_CONFIG = True

# 2. 再在 src/fuguang/core/config.py 的 __init__ 添加
self.MY_NEW_CONFIG = GlobalConfig.MY_NEW_CONFIG
```

### 坑点 #3：安全检查遗漏

**问题表现**：锁定状态下，陌生人说话扶光还是会响应。

**根本原因**：只在一处检查了 `security_mode_active`。

**正确做法**：PTT 模式和语音唤醒模式**都要检查**：
```python
if self.security_mode_active:
    time.sleep(0.1)
    continue  # 跳过语音处理
```

---

## 🔧 常用命令 (Common Commands)

```powershell
# 激活虚拟环境
& c:/Users/ALan/Desktop/fuguang/.venv/Scripts/Activate.ps1

# 运行扶光
python run.py

# 测试摄像头模块
python src/fuguang/camera.py

# 注册人脸
python src/scripts/register_face.py
```

---

## 📋 日志查看 (Logging)

| 日志类型 | 位置 | 说明 |
| :--- | :--- | :--- |
| **控制台日志** | 运行时终端窗口 | 实时查看，包含所有 `logger.info()` 输出 |
| **文件日志** | `logs/fuguang_study.log` | Study 模式的持久化日志 |
| **文件日志** | `logs/fuguang.log` | IDE 模式的持久化日志（如已配置） |

**关键日志标识**：
- `📜 System Prompt` - 人设加载状态
- `🧠 激活记忆` - 长期记忆检索
- `🔧 AI请求使用工具` - Function Calling 触发
- `⏰ 触发提醒` - 定时任务执行

---

## 📝 更新日志 (Changelog)

**规则**：每次增加新功能、修复 Bug 或调整架构后，**必须**在此处记录修改内容。

### v1.5.0 - 身份识别与安保系统 (2026-02-04)
- **[新增]** 人脸注册脚本（`src/scripts/register_face.py`）：录入指挥官人脸，保存到 `data/face_db/`。
- **[升级]** 摄像头模块 v4.5：双引擎分离模式（OpenCV 每帧追踪 + face_recognition 每2秒识别）。
- **[新增]** 安保协议：陌生人触发警报 + 系统锁定，拒绝一切语音指令，指挥官回归后自动解锁。
- **[新增]** 周期性警告：锁定期间每10秒刷新愤怒表情。
- **[修复]** `CAMERA_ENABLED = False` 现在正确禁用所有摄像头功能。
- **[优化]** API 密钥从硬编码迁移到 `.env` 文件，提高安全性。
- **[新增]** 配置项 `IDENTITY_CHECK_INTERVAL`：可调整身份识别频率。
- **[新增]** 坐标平滑：防止注视追踪微小抖动。

### v1.4.0 - 注视追踪 & 情感交互 & 数字感知 (2026-02-02)
- **[新增]** 数字感知模块（`core/eyes.py`）：获取当前窗口标题和剪贴板内容，注入 AI 上下文。
- **[新增]** 注视追踪功能（`gaze_tracker.py`）：角色眼神实时跟随用户，通过 `look:x,y` 发送坐标给 Unity。
- **[新增]** 回头杀机制：离开超过 5 分钟后回来，扶光会惊喜迎接。
- **[新增]** 害羞机制：盯着看超过 10 秒，扶光会撒娇吐槽。
- **[升级]** 摄像头模块 v2.0：单例模式、线程安全、坐标计算、缓存机制。
- **[配置]** 新增 `GAZE_TRACKING_ENABLED` 和 `GAZE_TRACKING_FPS` 开关。

### v1.3.1 - 路径修复 & 心跳升级 & 摄像头 (2026-01-31)
- **[修复]** 修复 `core/config.py` 中 `PROJECT_ROOT` 路径计算错误（`parent^3` → `parent^4`）。
- **[升级]** 心跳系统 v2.0：用 AI 动态生成主动对话内容。
- **[新增]** 摄像头人脸检测：主动对话前检测用户是否在座。
- **[优化]** 添加 System Prompt 加载日志。

### v1.3.0 - 语音打断 & 代码生成优化 (2026-01-28)
- **[新增]** 语音打断功能：按住 **右Ctrl键** 可立即停止扶光说话，方便用户插话。
- **[修复]** 修复复杂代码生成失败问题（如贪吃蛇游戏）。`max_tokens` 从 800 提升至 4096。
- **[优化]** 改进异常提示，区分超时/token超限/其他错误，不再统一显示"连接受到干扰"。

### v1.2.0 - 智能提醒升级 (2026-01-28)
- **[修复]** 修复了 `set_reminder` 时间计算错误问题。将工具定义改为动态生成，每次调用时注入当前时间，避免 AI 使用错误时间。
- **[升级]** `set_reminder` 新增 **行动触发模式**。支持 `auto_action` 参数，可在提醒触发时自动执行操作（如"3分钟后打开B站"）。
- **[优化]** 优化了 `content` 参数描述，避免 AI 填写占位符。

### v1.1.0 - OOP 架构重构 (2026-01-28)
- **[重构]** 完成了从单体脚本到 OOP 架构的物理拆分，核心代码迁移至 `src/fuguang/core/`。
- **[优化]** 统一了 `ide.py` 的入口逻辑，仅保留启动代码。

### v1.0.0 - 初始版本
- **[功能]** 实现了基础的 PTT 语音对话、唤醒词检测、Unity 联动。
- **[功能]** 集成了 DeepSeek API 和 阿里云 ASR/TTS。
