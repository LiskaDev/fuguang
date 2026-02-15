"""
GUISkills — 🖱️ 桌面控制类技能
操作鼠标、键盘、OCR 文字定位、pywinauto UIA 控件操作、YOLO 视觉点击
"""
import time, io, base64, os, logging, subprocess
import numpy as np, pyautogui
from PIL import Image
from .base import EASYOCR_AVAILABLE, PYGETWINDOW_AVAILABLE, PYWINAUTO_AVAILABLE, RAPIDOCR_AVAILABLE

logger = logging.getLogger("fuguang.skills")

# ---- Schema 定义 ----
_GUI_TOOLS_SCHEMA = [
    {"type":"function","function":{"name":"open_application","description":"【应用启动】打开常用应用程序（记事本、浏览器、计算器等）。使用场景: 用户说\"打开记事本\"等。","parameters":{"type":"object","properties":{"app_name":{"type":"string","description":"应用名称"},"args":{"type":"string","description":"可选参数"}},"required":["app_name"]}}},
    {"type":"function","function":{"name":"click_screen_text","description":"【GUI控制】智能寻找屏幕上的指定文字并模拟鼠标点击。优先用 Windows UIA 控件树精确匹配，失败后用 OCR 识别文字坐标。","parameters":{"type":"object","properties":{"target_text":{"type":"string","description":"要点击的文字内容"},"double_click":{"type":"boolean","description":"是否双击"},"window_title":{"type":"string","description":"可选：指定窗口标题"}},"required":["target_text"]}}},
    {"type":"function","function":{"name":"type_text","description":"【键盘输入】在当前光标位置输入文字。需要先点击输入框再调用此工具。","parameters":{"type":"object","properties":{"text":{"type":"string","description":"要输入的内容"},"press_enter":{"type":"boolean","description":"输入完是否按回车（默认True）"}},"required":["text"]}}},
    {"type":"function","function":{"name":"click_by_description","description":"【智能视觉点击】通过自然语言描述(英文)来寻找并点击屏幕上的UI元素（图标、按钮、图片等）。description参数必须用英文！","parameters":{"type":"object","properties":{"description":{"type":"string","description":"物体的英文描述（如 'red button', 'chrome icon'）"},"double_click":{"type":"boolean","description":"是否双击"}},"required":["description"]}}},
    {"type":"function","function":{"name":"list_ui_elements","description":"【UI探测器】列出指定窗口的所有可交互控件（按钮、菜单、输入框等）。用于了解界面结构，辅助精准点击。","parameters":{"type":"object","properties":{"window_title":{"type":"string","description":"窗口标题关键词（如'记事本'、'Chrome'）"}},"required":["window_title"]}}},
]


class GUISkills:
    """桌面 GUI 控制 Mixin"""
    _GUI_TOOLS = _GUI_TOOLS_SCHEMA

    def open_application(self, app_name: str, args: str = None) -> str:
        logger.info(f"🚀 [GUI] 正在打开应用: {app_name}")
        self.mouth.speak(f"正在打开 {app_name}...")
        try:
            app_map = {"notepad":"notepad.exe","记事本":"notepad.exe","chrome":"chrome.exe","谷歌浏览器":"chrome.exe","edge":"msedge.exe","浏览器":"msedge.exe","calc":"calc.exe","计算器":"calc.exe","explorer":"explorer.exe","文件管理器":"explorer.exe","资源管理器":"explorer.exe","cmd":"cmd.exe","命令提示符":"cmd.exe","terminal":"wt.exe","终端":"wt.exe","paint":"mspaint.exe","画图":"mspaint.exe","word":"winword.exe","excel":"excel.exe","powershell":"powershell.exe"}
            app_key = app_name.lower().strip()
            executable = app_map.get(app_key)
            if not executable:
                executable = app_name if app_name.endswith(".exe") else f"{app_name}.exe"
            cmd = f"{executable} {args}" if args else executable
            subprocess.Popen(cmd, shell=True)
            time.sleep(1.5)
            self.mouth.speak(f"已打开 {app_name}")
            return f"✅ 已打开 {app_name}"
        except Exception as e:
            logger.error(f"打开应用失败: {e}")
            return f"❌ 打开 {app_name} 失败: {str(e)}"

    # ========================
    # 🖱️ 核心点击方法（UIA 优先 → OCR 回退 → GLM 兜底）
    # ========================

    def click_screen_text(self, target_text: str, double_click: bool = False, window_title: str = None) -> str:
        if not self.config.ENABLE_GUI_CONTROL:
            return "❌ GUI 控制功能未启用，请在配置中开启 ENABLE_GUI_CONTROL。"
        logger.info(f"🖱️ [GUI] 正在寻找屏幕上的文字: '{target_text}'" + (f" (窗口: {window_title})" if window_title else ""))
        self.mouth.speak(f"正在寻找 {target_text}...")

        # === 第一优先级: pywinauto UIA 控件树精确匹配 ===
        if PYWINAUTO_AVAILABLE:
            result = self._click_with_uia(target_text, double_click, window_title)
            if result:
                return result
            logger.info("⚠️ UIA 未匹配到控件，回退到 OCR")

        # === 第二优先级: OCR 文字识别定位 ===
        if getattr(self, '_ocr_reader', None):
            result = self._click_with_ocr(target_text, double_click, window_title)
            if result:
                return result
            logger.warning(f"⚠️ OCR 未找到 '{target_text}'")

        # === 第三优先级: GLM-4V 视觉辅助 ===
        if self.config.GUI_USE_GLM_FALLBACK and self.vision_client:
            result = self._click_with_glm(target_text, double_click)
            if result:
                return result

        return f"❌ 未在屏幕上找到文字 '{target_text}'（UIA+OCR+GLM 均未命中）"

    def _click_with_uia(self, target_text: str, double_click: bool = False, window_title: str = None) -> str:
        """[新增] 使用 pywinauto UIA 后端定位并点击控件"""
        try:
            from pywinauto import Desktop
            from difflib import SequenceMatcher

            desktop = Desktop(backend='uia')

            # 获取目标窗口
            if window_title:
                windows = desktop.windows()
                target_win = None
                for w in windows:
                    try:
                        title = w.window_text()
                        if window_title.lower() in title.lower():
                            target_win = w
                            break
                    except Exception:
                        continue
                if not target_win:
                    logger.debug(f"UIA: 未找到窗口 '{window_title}'")
                    return None
            else:
                # 使用前台窗口
                import pywinauto
                target_win = pywinauto.application.Application(backend='uia').connect(active_only=True).active()

            # 遍历控件树，寻找匹配的控件
            target_lower = target_text.lower().strip()
            best_match = None
            best_score = 0

            try:
                # 获取所有可见子控件
                descendants = target_win.descendants()
                for ctrl in descendants:
                    try:
                        ctrl_name = ctrl.window_text().strip()
                        if not ctrl_name:
                            continue

                        ctrl_lower = ctrl_name.lower()

                        # 精确匹配
                        if ctrl_lower == target_lower:
                            score = 1.0
                        # 包含匹配
                        elif target_lower in ctrl_lower:
                            score = 0.85
                        elif ctrl_lower in target_lower:
                            score = 0.7
                        # 模糊匹配
                        else:
                            score = SequenceMatcher(None, target_lower, ctrl_lower).ratio()

                        if score > best_score and score >= 0.6:
                            best_score = score
                            best_match = ctrl
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"UIA: 遍历控件失败: {e}")
                return None

            if best_match and best_score >= 0.6:
                try:
                    ctrl_name = best_match.window_text()
                    ctrl_type = best_match.friendly_class_name()
                    logger.info(f"✅ [UIA] 找到控件: '{ctrl_name}' (类型: {ctrl_type}, 匹配度: {best_score:.0%})")

                    if double_click:
                        best_match.click_input(double=True)
                        action = "双击"
                    else:
                        best_match.click_input()
                        action = "点击"

                    self.mouth.speak(f"已{action} {target_text}")
                    return f"✅ [UIA] 已{action}控件 '{ctrl_name}' (类型: {ctrl_type})"
                except Exception as e:
                    logger.warning(f"UIA: 点击控件失败: {e}")
                    return None

            return None

        except Exception as e:
            logger.debug(f"UIA 整体异常: {e}")
            return None

    # ========================
    # 📋 UI 元素探测器
    # ========================

    def list_ui_elements(self, window_title: str) -> str:
        """[新增] 列出指定窗口的所有可交互控件"""
        if not PYWINAUTO_AVAILABLE:
            return "❌ pywinauto 未安装，请运行: pip install pywinauto"

        try:
            from pywinauto import Desktop

            desktop = Desktop(backend='uia')
            windows = desktop.windows()

            target_win = None
            for w in windows:
                try:
                    title = w.window_text()
                    if window_title.lower() in title.lower():
                        target_win = w
                        break
                except Exception:
                    continue

            if not target_win:
                available = []
                for w in windows[:10]:
                    try:
                        t = w.window_text()
                        if t.strip():
                            available.append(t[:40])
                    except:
                        pass
                return f"❌ 未找到包含 '{window_title}' 的窗口。当前可见窗口:\n" + "\n".join(f"  - {t}" for t in available)

            # 收集可交互控件
            elements = []
            clickable_types = {'Button', 'MenuItem', 'TabItem', 'ListItem',
                             'TreeItem', 'Hyperlink', 'CheckBox', 'RadioButton',
                             'ComboBox', 'Edit', 'Menu', 'ToolBar'}

            try:
                for ctrl in target_win.descendants():
                    try:
                        name = ctrl.window_text().strip()
                        ctrl_type = ctrl.friendly_class_name()

                        if not name and ctrl_type not in {'Edit', 'ComboBox'}:
                            continue

                        if ctrl_type in clickable_types:
                            display_name = name if name else f"[{ctrl_type}]"
                            elements.append(f"  [{ctrl_type}] {display_name}")
                    except Exception:
                        continue
            except Exception as e:
                return f"❌ 读取控件失败: {e}"

            if not elements:
                return f"⚠️ 窗口 '{target_win.window_text()}' 中未发现可交互控件"

            # 限制输出长度
            max_show = 50
            result = f"📋 窗口 '{target_win.window_text()[:40]}' 的可交互控件 ({len(elements)} 个):\n"
            result += "\n".join(elements[:max_show])
            if len(elements) > max_show:
                result += f"\n  ... 还有 {len(elements) - max_show} 个控件"
            result += "\n\n💡 提示: 使用 click_screen_text(target_text='控件名称') 可以精准点击上述控件。"
            return result

        except Exception as e:
            logger.error(f"UI 探测异常: {e}")
            return f"❌ UI 探测失败: {str(e)}"

    # ========================
    # 📝 OCR 点击（回退方案）
    # ========================

    def _click_with_ocr(self, target_text, double_click, window_title=None):
        try:
            target_window = None
            if window_title and PYGETWINDOW_AVAILABLE:
                try:
                    import pygetwindow as gw
                    window_aliases = {"记事本":["记事本","notepad"],"浏览器":["chrome","edge","firefox","browser","bilibili","百度","google"],"计算器":["计算器","calculator"],"资源管理器":["资源管理器","explorer","文件"],"画图":["画图","paint"]}
                    search_keywords = [window_title.lower()]
                    for key, aliases in window_aliases.items():
                        if window_title in aliases or key == window_title:
                            search_keywords.extend(aliases); break
                    for win in gw.getAllWindows():
                        for keyword in search_keywords:
                            if keyword in win.title.lower():
                                target_window = win
                                if win.isMinimized:
                                    try: win.restore(); time.sleep(0.5)
                                    except: pass
                                elif not win.isActive:
                                    try: win.activate(); time.sleep(0.3)
                                    except: pass
                                break
                        if target_window: break
                except Exception as e:
                    logger.warning(f"⚠️ 窗口查找失败: {e}")

            if target_window: time.sleep(0.2)
            screenshot = pyautogui.screenshot()
            screenshot_array = np.array(screenshot)

            if not getattr(self, '_ocr_reader', None):
                return None  # OCR 未初始化

            # 调用 OCR 引擎（RapidOCR vs EasyOCR 格式不同）
            ocr_results = []
            if getattr(self, '_ocr_engine', None) == 'rapid':
                result, _ = self._ocr_reader(screenshot_array)
                if result:
                    for item in result:
                        bbox, text, confidence = item[0], item[1], item[2]
                        # RapidOCR bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                        ocr_results.append((bbox, text, confidence))
            else:
                # EasyOCR
                raw = self._ocr_reader.readtext(screenshot_array)
                for bbox, text, confidence in raw:
                    ocr_results.append((bbox, text, confidence))

            candidates = []
            target_lower = target_text.lower().strip()

            for bbox, text, confidence in ocr_results:
                detected_lower = text.strip().lower()
                match_score = 0
                if detected_lower == target_lower: match_score = 100
                elif target_lower in detected_lower:
                    ratio = len(text.strip()) / len(target_text)
                    match_score = (80 if ratio <= 2.0 else 30) / ratio
                elif detected_lower in target_lower: match_score = 60
                if match_score == 0: continue

                tl, tr, br, bl = bbox
                if match_score < 100 and target_lower in detected_lower:
                    idx = detected_lower.index(target_lower)
                    r = idx / len(text.strip()) if len(text.strip()) > 0 else 0
                    w = tr[0] - tl[0]
                    cx = int(tl[0] + w * r + w * (len(target_text) / len(text.strip())) / 2)
                    cy = int((tl[1] + bl[1]) / 2)
                else:
                    cx = int((tl[0] + br[0]) / 2); cy = int((tl[1] + br[1]) / 2)

                in_window = False
                if target_window:
                    if (target_window.left <= cx <= target_window.left + target_window.width and
                        target_window.top <= cy <= target_window.top + target_window.height):
                        in_window = True
                    else: continue
                candidates.append({'text': text.strip(), 'x': cx, 'y': cy, 'confidence': confidence, 'match_score': match_score, 'in_window': in_window or (target_window is None)})

            if not candidates: return None
            candidates.sort(key=lambda c: (-c['match_score'], -c['in_window'], -c['confidence'], c['y']))
            best = candidates[0]
            pyautogui.moveTo(best['x'], best['y'], duration=self.config.GUI_CLICK_DELAY)
            time.sleep(0.1)
            if double_click: pyautogui.doubleClick(); action = "双击"
            else: pyautogui.click(); action = "点击"
            self.mouth.speak(f"已{action} {target_text}")
            return f"✅ [OCR] 已{action}屏幕上的 '{best['text']}' (坐标: {best['x']}, {best['y']})"
        except Exception as e:
            logger.error(f"OCR 点击失败: {e}")
            return None

    def _click_with_glm(self, target_text, double_click):
        try:
            screenshot = pyautogui.screenshot()
            screenshot.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            buf = io.BytesIO(); screenshot.save(buf, format="JPEG", quality=85)
            img_uri = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
            response = self.vision_client.chat.completions.create(
                model="glm-4v-flash",
                messages=[{"role":"user","content":[{"type":"text","text":f"请在截图中找到'{target_text}'的位置"},{"type":"image_url","image_url":{"url":img_uri}}]}],
                temperature=0.3)
            desc = response.choices[0].message.content
            return f"ℹ️ GLM-4V 提示：{desc}\n（暂不支持自动点击，请手动操作）"
        except Exception as e:
            logger.error(f"GLM-4V 辅助定位失败: {e}"); return None

    # ========================
    # ⌨️ 键盘输入
    # ========================

    def type_text(self, text: str, press_enter: bool = True) -> str:
        if not self.config.ENABLE_GUI_CONTROL: return "❌ GUI 控制功能未启用。"
        logger.info(f"⌨️ [GUI] 正在输入文字: {text[:20]}...")
        self.mouth.speak("正在输入...")
        try:
            import pyperclip; pyperclip.copy(text); pyautogui.hotkey('ctrl', 'v')
            if press_enter: time.sleep(0.1); pyautogui.press('enter')
            action = "已发送" if press_enter else "已输入"
            self.mouth.speak(f"{action}"); return f"✅ {action}: {text}"
        except Exception as e:
            return f"❌ 输入失败: {str(e)}"

    # ========================
    # 👁️ 视觉点击（YOLO-World / UIA 混合）
    # ========================

    def click_by_description(self, description: str, double_click: bool = False) -> str:
        if not self.config.ENABLE_GUI_CONTROL: return "❌ GUI 控制功能未启用。"

        logger.info(f"👁️ [视觉] 正在寻找: '{description}'")
        self.mouth.speak(f"正在寻找 {description}")

        # 优先尝试 UIA（如果描述是中文或明确的控件名）
        if PYWINAUTO_AVAILABLE:
            result = self._click_with_uia(description, double_click)
            if result:
                return result

        # 回退到 YOLO-World
        if not self.yolo_world:
            return f"❌ 未找到 '{description}'。YOLO-World 模型未加载且 UIA 未匹配到控件。"

        try:
            self.yolo_world.set_classes([description])
            screenshot_array = np.array(pyautogui.screenshot())
            results = self.yolo_world.predict(screenshot_array, conf=0.1, verbose=False)
            if len(results[0].boxes) > 0:
                boxes = results[0].boxes; confs = boxes.conf.cpu().numpy()
                best_idx = confs.argmax(); coords = boxes[best_idx].xyxy[0].tolist(); conf = confs[best_idx]
                cx, cy = int((coords[0]+coords[2])/2), int((coords[1]+coords[3])/2)
                pyautogui.moveTo(cx, cy, duration=0.3); time.sleep(0.1)
                if double_click: pyautogui.doubleClick(); act = "双击"
                else: pyautogui.click(); act = "点击"
                self.mouth.speak(f"已{act}")
                return f"✅ [YOLO] 已{act} '{description}' (坐标: {cx}, {cy}, 置信度: {conf:.2%})"
            else:
                self.mouth.speak("没有找到目标")
                return f"❌ 在屏幕上没有找到 '{description}'。建议用英文描述。"
        except Exception as e:
            logger.error(f"视觉识别失败: {e}"); return f"❌ 视觉识别失败: {str(e)}"

