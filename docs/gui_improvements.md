# 🎯 GUI 控制功能改进说明

## 你提出的三个问题

### ❌ **问题1：缺乏主动性**
**现象**：必须手动打开记事本，AI 才能点击"文件"菜单  
**问题本质**：AI 只能"点击已有的"，不会"先创造条件"

### ❌ **问题2：多窗口歧义**
**现象**：VSCode 有"文件"，记事本也有"文件"，OCR 不知道点哪个  
**问题本质**：纯文字匹配缺乏"窗口上下文"理解

### ❌ **问题3：终端干扰**
**现象**：B站输入框的提示文字也显示在终端里，OCR 点错了  
**问题本质**：全屏扫描无法区分"目标窗口"和"干扰窗口"

---

## ✅ 我的改进方案

### 🚀 **改进1：应用启动工具**

**新增工具**：`open_application(app_name, args)`

```python
# 支持的应用
notepad      # 记事本
chrome       # Chrome浏览器
edge         # Edge浏览器
calc         # 计算器
explorer     # 文件管理器
cmd          # 命令行
paint        # 画图
...更多
```

**AI 调用示例**：
```
用户："打开记事本并点击文件菜单"
AI 理解：
  1. open_application("notepad")
  2. click_screen_text("文件", window_title="记事本")
```

**效果**：  
✅ AI 可以自己打开应用，不需要用户手动操作  
✅ 串联操作更流畅（打开 → 操作 → 关闭）

---

### 🪟 **改进2：窗口感知过滤**

**改进点**：`click_screen_text` 添加 `window_title` 参数

```python
# 旧版（全屏查找）
click_screen_text("文件")  # 可能点错

# 新版（窗口过滤）
click_screen_text("文件", window_title="记事本")  # 只点记事本的
```

**技术方案**：
1. 使用 `pygetwindow` 库获取窗口信息
2. 获取窗口的 (left, top, width, height)
3. OCR 扫描后，过滤掉窗口范围之外的坐标

**效果**：  
✅ 解决多窗口歧义（VSCode + 记事本同时打开）  
✅ 过滤终端干扰（演示脚本的输出不会被点击）

---

### 🎯 **改进3：智能候选排序**

**问题场景**：
- 记事本菜单栏有"文件"
- 记事本文本框里也输入了"文件"
- OCR 找到 2 个匹配，该点哪个？

**排序策略**：
```python
candidates.sort(key=lambda c: (
    -c['in_window'],      # 1️⃣ 窗口内优先（如果指定了窗口）
    -c['confidence'],     # 2️⃣ 置信度高优先（OCR 识别清晰度）
    c['y']                # 3️⃣ Y坐标小优先（菜单通常在屏幕上方）
))
```

**效果**：  
✅ 优先点击窗口内的（跨窗口安全）  
✅ 优先点击清晰的（避免误识别）  
✅ 优先点击上方的（菜单栏位置）

---

## 📝 实际使用示例

### **场景1：打开记事本并保存文件**

**用户说**：  
"帮我打开记事本，输入'你好世界'，然后另存为"

**AI 理解并执行**：
```python
1. open_application("notepad")
2. type_text("你好世界", press_enter=False)
3. click_screen_text("文件", window_title="记事本")
4. click_screen_text("另存为")
```

---

### **场景2：B站发弹幕（解决终端干扰）**

**用户说**：  
"打开B站视频，发送弹幕'666'"

**AI 理解并执行**：
```python
1. open_application("edge", "https://www.bilibili.com/video/xxx")
2. click_screen_text("发个友善的弹幕", window_title="Bilibili")  # 只点浏览器窗口
3. type_text("666")
4. click_screen_text("发送", window_title="Bilibili")
```

**关键改进**：
- ✅ 终端里显示的"发个友善的弹幕"会被过滤掉
- ✅ 只点击浏览器窗口范围内的输入框

---

### **场景3：多窗口操作（VSCode + 记事本）**

**用户说**：  
"打开记事本和VSCode，分别点击它们的文件菜单"

**AI 理解并执行**：
```python
1. open_application("notepad")
2. open_application("code")  # VSCode
3. click_screen_text("文件", window_title="记事本")  # 只点记事本的
4. click_screen_text("文件", window_title="Visual Studio Code")  # 只点VSCode的
```

---

## 🛠️ 技术细节

### **依赖库**
```bash
pip install easyocr        # OCR 文字识别
pip install pygetwindow    # 窗口管理（新增）
pip install pyautogui      # 鼠标键盘控制
```

### **窗口过滤算法**
```python
# 1. 查找目标窗口
windows = gw.getAllWindows()
for win in windows:
    if "记事本" in win.title and win.visible:
        target_window = win
        break

# 2. 过滤 OCR 结果
for detection in ocr_results:
    center_x, center_y = calculate_center(detection.bbox)
    
    # 只保留窗口范围内的
    if (target_window.left <= center_x <= target_window.left + target_window.width and
        target_window.top <= center_y <= target_window.top + target_window.height):
        candidates.append(detection)
```

---

## 🔧 配置说明

### **config.py 配置项**
```python
# GUI 控制总开关
ENABLE_GUI_CONTROL = True

# 鼠标移动延迟（模拟人类）
GUI_CLICK_DELAY = 0.5  # 秒

# OCR 失败时是否使用 GLM-4V 辅助
GUI_USE_GLM_FALLBACK = True
```

---

## 💡 使用建议

### **什么时候需要指定 window_title？**

**必须指定**：
- ✅ 多个窗口有相同文字（如多个"文件"菜单）
- ✅ 演示脚本运行时（避免终端干扰）
- ✅ 浏览器操作（区分多个标签页）

**可以不指定**：
- ✅ 只有一个窗口的场景
- ✅ 目标文字非常独特（如"立即登录"）
- ✅ OCR 误点的风险很低

### **AI 如何智能判断？**

DeepSeek 可以根据用户意图自动添加参数：

| 用户说的话 | AI 理解 | 是否加参数 |
|:---|:---|:---|
| "点击文件菜单" | 全屏查找 | ❌ 不加 |
| "点击记事本的文件菜单" | 指定记事本窗口 | ✅ 加 `window_title="记事本"` |
| "在B站输入框输入666" | 指定B站窗口 | ✅ 加 `window_title="Bilibili"` |
| "打开记事本点文件" | 先打开再点击 | ✅ 先调用 `open_application` |

---

## ⚠️ 已知限制

### **窗口标题匹配**
- 记事本标题可能是 "无标题 - 记事本" 或 "test.txt - 记事本"
- 解决：使用模糊匹配 `"记事本" in window.title`

### **窗口最小化**
- 如果窗口被最小化，pygetwindow 仍能找到但 visible=False
- 解决：自动过滤 `if win.visible`

### **多显示器**
- 坐标可能超出主屏幕，pyautogui 可能点错
- 解决：暂不支持多显示器，建议在主屏幕操作

---

## 🎉 改进总结

| 改进项 | 解决的问题 | 技术方案 |
|:---|:---|:---|
| **应用启动** | 缺乏主动性 | `open_application` 工具 |
| **窗口过滤** | 多窗口歧义 | `pygetwindow` + 坐标过滤 |
| **智能排序** | 终端干扰 | 候选排序算法 |

---

## 🔮 未来可能的改进

1. **窗口自动激活**：点击前先激活目标窗口（`win.activate()`）
2. **OCR 缓存**：相同画面不重复扫描（MD5 判断）
3. **区域限制**：只扫描窗口范围内（提升速度）
4. **图标识别**：支持点击纯图标（使用 OpenCV 模板匹配）
5. **多显示器支持**：识别窗口所在屏幕

---

## 📊 测试结果

✅ **应用启动**：成功打开记事本、浏览器、计算器  
✅ **窗口过滤**：成功区分 VSCode 和记事本的"文件"菜单  
✅ **智能排序**：优先点击菜单栏，而非文本框内的文字  
✅ **终端隔离**：演示脚本的输出不再干扰点击  

---

**改进后的 GUI 控制能力更加智能、准确、可靠！** 🎉
