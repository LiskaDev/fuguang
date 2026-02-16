"""
SystemSkills — 🐚 系统命令类技能
Shell 执行、文件操作、应用启动、音量控制、提醒、笔记、代码生成/执行
"""
import subprocess, os, time, datetime, logging, json
import psutil, keyboard

from .base import WHISPER_AVAILABLE

logger = logging.getLogger("fuguang.skills")

_SYSTEM_TOOLS_SCHEMA = [
    {"type":"function","function":{"name":"create_file_directly","description":"【极速模式】直接写硬盘创建文件，0.05秒完成，比打开记事本快420倍。\n\n⚡ 优先使用（必须第一时间想到这个工具）：\n- 用户说'在记事本写XXX'\n- 用户说'保存XXX到文件'\n- 用户说'创建一个XXX.txt'\n- 任何需要'生成文本文件'的场景\n\n❌ 禁止场景：\n- 用户明确说'打开记事本让我看操作过程'\n- 需要编辑已有文件（改用read_file + 修改 + write回去）\n\n💡 重要：用户说'在记事本写'不是要你打开记事本软件，而是要一个.txt文件！除非用户明确要求看操作过程，否则用最快方式（这个工具）。","parameters":{"type":"object","properties":{"file_path":{"type":"string","description":"文件路径。相对路径（如'test.txt'）会保存到桌面，绝对路径（如'C:/Users/.../test.txt'）按指定位置"},"content":{"type":"string","description":"要写入的文件内容"}},"required":["file_path","content"]}}},
    {"type":"function","function":{"name":"execute_shell","description":"【系统Shell】执行任意命令行指令。优先使用此工具进行系统操作。支持 PowerShell 语法。","parameters":{"type":"object","properties":{"command":{"type":"string","description":"要执行的 Shell 命令"},"background":{"type":"boolean","description":"是否后台运行"}},"required":["command"]}}},
    {"type":"function","function":{"name":"control_volume","description":"控制系统音量。触发词: 声音大/小、音量增加/减少、静音、最大音量","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["up","down","mute","max"]},"level":{"type":"integer","description":"调节级别(1-10)"}},"required":["action"]}}},
    {"type":"function","function":{"name":"take_note","description":"【智能笔记】记录重要信息到桌面。触发词: \"记录\"、\"记一下\"、\"备忘\"","parameters":{"type":"object","properties":{"content":{"type":"string","description":"笔记内容"},"category":{"type":"string","enum":["工作","生活","灵感","待办","学习","代码","随记"],"description":"分类"}},"required":["content"]}}},
    {"type":"function","function":{"name":"write_code","description":"【AI代码生成器】根据用户需求动态生成Python代码。保存到 generated/ 文件夹并用VSCode打开。","parameters":{"type":"object","properties":{"filename":{"type":"string","description":"文件名"},"code_content":{"type":"string","description":"完整的Python代码"}},"required":["filename","code_content"]}}},
    {"type":"function","function":{"name":"open_tool","description":"打开Windows内置工具。支持: 记事本/计算器/画图/任务管理器等","parameters":{"type":"object","properties":{"tool_name":{"type":"string","description":"工具名称(中文)"}},"required":["tool_name"]}}},
    {"type":"function","function":{"name":"run_code","description":"【代码执行器】运行 generated/ 目录下的 Python 脚本。","parameters":{"type":"object","properties":{"filename":{"type":"string","description":"要运行的文件名"}},"required":["filename"]}}},
    {"type":"function","function":{"name":"transcribe_media_file","description":"使用 Whisper 模型将本地的视频或音频文件转写为文字。支持格式：mp4, mp3, wav, m4a 等。","parameters":{"type":"object","properties":{"file_path":{"type":"string","description":"文件的绝对路径"}},"required":["file_path"]}}},
    {"type":"function","function":{"name":"listen_to_system_audio","description":"监听电脑系统内部发出的声音（视频会议、网页视频等）并转写为文字。","parameters":{"type":"object","properties":{"duration":{"type":"integer","description":"监听时长（秒），建议 15-60 秒"}},"required":["duration"]}}},
    {"type":"function","function":{"name":"launch_application","description":"【一键启动】快速启动应用程序、游戏、软件。智能匹配: 同音字/简称/拼音/模糊匹配。比execute_shell_command快10倍。","parameters":{"type":"object","properties":{"app_name":{"type":"string","description":"应用程序名称"}},"required":["app_name"]}}},
    {"type":"function","function":{"name":"execute_shell_command","description":"【高危权限】在系统终端执行 Shell 命令。带黑名单保护、超时机制。⚠️ 不要用此工具启动应用程序！","parameters":{"type":"object","properties":{"command":{"type":"string","description":"要执行的命令"},"timeout":{"type":"integer","description":"超时时间(秒)，默认60"}},"required":["command"]}}},
    {"type":"function","function":{"name":"toggle_auto_execute","description":"切换自主执行模式。当指挥官说'全交给你了'时开启；说'需要我确认'时关闭。","parameters":{"type":"object","properties":{"enable":{"type":"boolean","description":"true=开启自主模式，false=关闭"}},"required":["enable"]}}},
    {"type":"function","function":{"name":"list_installed_applications","description":"列出已安装的应用程序和游戏。","parameters":{"type":"object","properties":{}}}},
]


class SystemSkills:
    """系统命令类技能 Mixin"""
    _SYSTEM_TOOLS = _SYSTEM_TOOLS_SCHEMA

    def create_file_directly(self, file_path: str, content: str) -> str:
        """
        【极速模式】直接创建文件，0.05秒完成
        
        Args:
            file_path: 文件路径，支持相对路径（自动保存到桌面）
            content: 文件内容
        """
        logger.info(f"📄 [极速文件] 正在创建: {file_path}")
        try:
            # 如果是相对路径，保存到桌面
            if ":" not in file_path:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                file_path = os.path.join(desktop, file_path)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self.mouth.speak(f"文件已创建")
            return f"✅ 文件已创建: {file_path}"
        except Exception as e:
            logger.error(f"创建文件失败: {e}")
            return f"❌ 创建失败: {str(e)}"

    def execute_shell(self, command: str, background: bool = False) -> str:
        """
        【系统Shell】执行任意PowerShell命令，支持后台运行。
        
        功能：直接调用PowerShell执行命令，可选择后台模式（不等待结果）
        注意：高级功能，使用前确保命令安全
        
        Args:
            command: PowerShell命令字符串
            background: 是否后台运行（True=不等待结果）
            
        Returns:
            执行结果或错误信息
        """
        logger.info(f"🐚 执行Shell指令: {command} (后台={background})")
        self.mouth.speak("正在执行指令..." if self.auto_execute else "正在执行终端指令...")
        try:
            cmd_args = ["powershell", "-Command", command]
            if background:
                subprocess.Popen(cmd_args, creationflags=subprocess.CREATE_NO_WINDOW)
                return f"✅ 指令已在后台启动: {command}"
            else:
                result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
                output = result.stdout.strip(); error = result.stderr.strip()
                if result.returncode == 0:
                    return f"✅ 执行成功:\n{output[:1000]}"
                else:
                    return f"❌ 执行出错:\n{error}\n(Output: {output})"
        except Exception as e:
            return f"❌ Shell 执行失败: {str(e)}"

    def control_volume(self, action: str, level: int = None) -> str:
        """
        【音量控制】调节系统音量，支持增大/减小/静音/最大。
        
        Args:
            action: 操作类型 - "up"（增大）, "down"（减小）, "mute"（静音）, "max"（最大）
            level: 调节级数（1-10），默认1格
            
        Returns:
            操作结果
        """
        logger.info(f"🔊 音量控制: {action}, 级别: {level}")
        try:
            if level is None: level = 1
            if action == "up":
                for _ in range(level): keyboard.press_and_release('volume up'); time.sleep(0.1)
                self.mouth.speak(f"音量已增大{level}格"); return f"✅ 音量已增大 {level} 格"
            elif action == "down":
                for _ in range(level): keyboard.press_and_release('volume down'); time.sleep(0.1)
                self.mouth.speak(f"音量已减小{level}格"); return f"✅ 音量已减小 {level} 格"
            elif action == "mute":
                keyboard.press_and_release('volume mute'); self.mouth.speak("已切换静音状态"); return "✅ 已切换静音状态"
            elif action == "max":
                for _ in range(50): keyboard.press_and_release('volume up'); time.sleep(0.05)
                self.mouth.speak("音量已最大"); return "✅ 音量已调到最大"
            return f"❌ 未知操作: {action}"
        except Exception as e:
            return f"❌ 控制失败: {str(e)}"

    def take_note(self, content: str, category: str = "随记") -> str:
        """
        【快速记录】将内容保存到桌面Markdown笔记本，按月份归档。
        
        特点：自动按月分类、表格式排版、分类图标、自动打开文件
        
        Args:
            content: 要记录的内容
            category: 分类（工作/生活/灵感/待办/学习/代码/随记）
            
        Returns:
            保存结果和文件名
        """
        icons = {"工作":"💼","生活":"🏠","灵感":"💡","待办":"📌","学习":"📚","代码":"💻","随记":"📝"}
        icon = icons.get(category, "📝")
        month_str = datetime.datetime.now().strftime("%Y-%m")
        filename = self.config.NOTES_DIR / f"Fuguang_Notes_{month_str}.md"
        timestamp = datetime.datetime.now().strftime("%m-%d %H:%M")
        is_new_file = not filename.exists()
        try:
            with open(filename, "a", encoding="utf-8") as f:
                if is_new_file:
                    f.write(f"# 📅 {month_str} 扶光笔记本\n\n| 时间 | 分类 | 内容 |\n|:---:|:---:|---|\n")
                clean_content = content.replace("\n", " ").replace("|", "/")
                f.write(f"| {timestamp} | {icon} {category} | {clean_content} |\n")
            self.mouth.speak(f"已记录到桌面笔记本，分类是{category}。")
            try: os.startfile(str(filename))
            except Exception as e: logger.debug(f"打开笔记文件失败: {e}")
            return f"✅ 已记录到桌面: {filename.name}"
        except Exception as e:
            return f"记录失败: {str(e)}"

    def write_code(self, filename: str, code_content: str) -> str:
        """
        【代码生成】将AI生成的代码保存到generated/目录，并自动用VS Code打开。
        
        功能：保存Python代码到项目的generated目录，尝试用VS Code打开
        
        Args:
            filename: 文件名（英文，如snake_game.py，不写.py会自动添加）
            code_content: 完整的Python代码内容
            
        Returns:
            生成结果和文件路径
        """
        if not filename.endswith(".py"): filename += ".py"
        # [修复] 防止路径穿越（如 ../malicious.py）
        full_path = (self.config.GENERATED_DIR / filename).resolve()
        if not full_path.is_relative_to(self.config.GENERATED_DIR.resolve()):
            return f"❌ 非法文件名: {filename}（禁止路径穿越）"
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f: f.write(code_content)
            self.mouth.speak(f"代码已生成：{filename}，正在为你打开。")
            try:
                result = subprocess.run(["code", str(full_path)], capture_output=True, timeout=5)
                if result.returncode != 0: raise Exception()
            except Exception:
                try: os.startfile(str(full_path))
                except Exception as e: logger.debug(f"startfile 失败: {e}")
            return f"✅ 代码已生成: generated/{filename}"
        except Exception as e:
            return f"代码生成失败: {str(e)}"

    def find_app_by_alias(self, text: str) -> tuple:
        text_lower = text.lower()
        for app_name, config in self.APP_REGISTRY.items():
            for alias in config["aliases"]:
                if alias.lower() in text_lower:
                    return app_name, config["cmd"]
        return None, None

    def open_app(self, text: str) -> bool:
        app_name, cmd = self.find_app_by_alias(text)
        if app_name:
            self.mouth.speak(f"正在打开{app_name}...")
            try:
                # [修复] 使用 subprocess 替代 os.system，避免 shell 注入
                subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
            except Exception as e:
                logger.warning(f"打开应用失败: {app_name} -> {e}")
                return False
        return False

    def open_tool(self, tool_name: str) -> str:
        """
        【快速启动】打开Windows内置工具或应用程序。
        
        支持：记事本、计算器、画图、任务管理器等常用工具
        
        Args:
            tool_name: 工具名称（支持中文，如"记事本"、"计算器"）
            
        Returns:
            启动结果
        """
        if self.open_app(tool_name): return "✅ 已打开"
        self.mouth.speak(f"正在打开{tool_name}...")
        try:
            # [修复] 使用 subprocess.Popen 替代 os.system，并过滤危险字符
            # 只允许字母、数字、中文、空格、点和连字符
            import re
            if re.search(r'[;&|<>$`"\\]', tool_name):
                return f"❌ 工具名称包含非法字符: {tool_name}"
            subprocess.Popen(["cmd", "/c", "start", "", tool_name], creationflags=subprocess.CREATE_NO_WINDOW)
            return f"✅ 尝试启动: {tool_name}"
        except Exception as e:
            return f"❌ 打开失败: {str(e)}"

    def set_reminder(self, content: str, target_time: str, auto_action: dict = None) -> str:
        try:
            datetime.datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S")
            reminder_task = {"time": target_time, "content": content}
            if auto_action and isinstance(auto_action, dict):
                reminder_task["auto_action"] = auto_action
                action_desc = f"（到时将自动执行: {auto_action.get('tool_name', '未知操作')}）"
            else:
                action_desc = ""
            self.reminders.append(reminder_task)
            self._save_reminders_to_disk()
            # 不调用 mouth.speak —— 让 AI 的自然语言回复作为唯一确认
            # 不调用 take_note —— 避免副作用产生额外 TTS
            return f"✅ 已设定提醒: {target_time} {content}{action_desc}"
        except ValueError:
            return f"❌ 时间格式错误"

    def check_reminders(self):
        current_time = datetime.datetime.now()
        active_reminders = []; is_changed = False
        for task in list(self.reminders):  # [修复] 遍历副本，防止迭代中修改
            # [修复] 容错：跳过损坏的提醒数据
            try:
                task_time_str = task.get("time") if isinstance(task, dict) else None
                if not task_time_str:
                    logger.warning(f"⚠️ 跳过无效提醒数据（缺少time字段）: {task}")
                    is_changed = True
                    continue
                task_time = datetime.datetime.strptime(task_time_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, AttributeError) as e:
                logger.warning(f"⚠️ 跳过损坏的提醒数据: {task} ({e})")
                is_changed = True
                continue
            if current_time >= task_time:
                self.mouth.send_to_unity("Surprised")
                self._show_toast("Fuguang IDE 提醒", task['content'])
                # [修复#9] auto_action 执行
                if "auto_action" in task and task["auto_action"]:
                    action = task["auto_action"]
                    tool_name = action.get("tool_name", "")
                    arguments = action.get("arguments", {})
                    logger.info(f"⏰ [提醒] 正在自动执行: {tool_name}({arguments})")
                    try:
                        result = self.execute_tool(tool_name, arguments)
                        logger.info(f"✅ [提醒] 自动执行完成: {result[:100] if result else 'OK'}")
                        self.mouth.speak(f"指挥官，已帮你{task['content']}")
                    except Exception as e:
                        logger.error(f"❌ [提醒] 自动执行失败: {tool_name} -> {e}")
                        self.mouth.speak(f"指挥官，{task['content']}，但自动执行出了点问题")
                else:
                    self.mouth.speak(f"指挥官，{task['content']}")
                is_changed = True
            else:
                active_reminders.append(task)
        if is_changed:
            self.reminders = active_reminders
            self._save_reminders_to_disk()

    def run_code(self, filename: str) -> str:
        """
        【代码执行器】运行generated/目录下的Python脚本，带安全确认。
        
        安全机制：非自主模式下需要用户确认，交互式代码会在新窗口运行
        
        Args:
            filename: 文件名（在generated/目录下，如snake_game.py）
            
        Returns:
            执行结果或输出内容
        """
        import sys as _sys
        if not filename.endswith(".py"): filename += ".py"
        # [修复] 防止路径穿越（如 ../../system32/xxx.py）
        file_path = (self.config.GENERATED_DIR / filename).resolve()
        if not file_path.is_relative_to(self.config.GENERATED_DIR.resolve()):
            return f"❌ 非法文件名: {filename}（禁止路径穿越）"
        if not file_path.exists():
            return f"❌ 找不到文件: {filename}，请先使用 write_code 生成代码。"
        if self.auto_execute:
            pass
        elif not _sys.stdin or not _sys.stdin.isatty():
            pass
        else:
            print(f"\n{'='*50}\n🚨 [安全警告] AI 请求运行代码\n{'='*50}\n📂 文件: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f: preview = f.read()[:500]
                print(preview)
            except Exception as e:
                logger.debug(f"预览代码读取失败: {e}")
            user_confirm = input("是否允许运行? [y/n]: ").strip().lower()
            if user_confirm != 'y': return "❌ 指挥官拒绝了代码执行请求。"
        try:
            with open(file_path, 'r', encoding='utf-8') as f: code_content = f.read()
            is_interactive = 'input(' in code_content
        except Exception as e:
            logger.debug(f"读取代码文件失败: {e}")
            is_interactive = False
        if is_interactive:
            self.mouth.speak(f"交互式程序，给你打开新窗口运行~")
            subprocess.Popen(f'start cmd /k "chcp 65001 >nul && "{_sys.executable}" "{file_path}""', shell=True, cwd=str(self.config.GENERATED_DIR))
            return f"✅ 已在新终端窗口启动 {filename}"
        self.mouth.speak("正在执行代码...")
        try:
            result = subprocess.run([_sys.executable, str(file_path)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, cwd=str(self.config.GENERATED_DIR), env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            if result.returncode == 0:
                resp = f"✅ 代码执行成功！"
                if result.stdout: resp += f"\n📤 输出结果:\n{result.stdout[:500]}"
                return resp
            else:
                return f"❌ 代码执行出错:\n{result.stderr[:500]}"
        except subprocess.TimeoutExpired:
            return "⏰ 代码执行超时（超过60秒），已强制终止。"
        except Exception as e:
            return f"❌ 运行失败: {str(e)}"

    def transcribe_media_file(self, file_path: str) -> str:
        if not WHISPER_AVAILABLE: return "❌ Whisper 未安装"
        from pathlib import Path
        path = Path(file_path)
        if not path.is_absolute(): path = self.config.PROJECT_ROOT / file_path
        if not path.exists(): return f"❌ 找不到文件: {file_path}"
        try:
            if self.whisper_model is None:
                import whisper; self.whisper_model = whisper.load_model("small")
            result = self.whisper_model.transcribe(str(path), fp16=True)
            text = result["text"].strip(); lang = result.get("language", "unknown")
            if not text: return "⚠️ 文件中没有检测到语音内容"
            if len(text) > 3000: return f"【文件转写内容】(语言: {lang})\n{text[:3000]}...\n\n(已截断，共 {len(text)} 字)"
            return f"【文件转写内容】(语言: {lang})\n{text}"
        except Exception as e:
            return f"❌ 转写失败: {str(e)}"

    def listen_to_system_audio(self, duration: int = 30) -> str:
        import soundcard as sc, soundfile as sf, tempfile
        # [修复] 限制最大录制时长，防止内存占用过大
        if duration > 120:
            return "❌ 录制时长过长，请设置 120 秒以内"
        if duration < 1:
            return "❌ 录制时长至少 1 秒"
        logger.info(f"👂 [系统听觉] 正在通过 WASAPI 监听扬声器 {duration} 秒...")
        try:
            speaker = sc.default_speaker()
            # [修复] 检查默认扬声器是否存在
            if not speaker:
                return "❌ 未检测到默认扬声器，请检查音频设备"
            loopback = sc.get_microphone(id=str(speaker.id), include_loopback=True)
            SR = 44100
            with loopback.recorder(samplerate=SR) as mic: data = mic.record(numframes=SR * duration)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp: temp_path = tmp.name
            sf.write(temp_path, data, SR)
            if not WHISPER_AVAILABLE: os.remove(temp_path); return "❌ Whisper 未安装"
            if self.whisper_model is None:
                import whisper; self.whisper_model = whisper.load_model("small")
            result = self.whisper_model.transcribe(temp_path, fp16=True)
            os.remove(temp_path)
            text = result["text"].strip(); lang = result.get("language", "unknown")
            if not text: return "⚠️ 系统音频中没有检测到语音内容"
            if len(text) > 3000: return f"【系统音频监听结果】(语言: {lang})\n{text[:3000]}...\n\n(已截断)"
            return f"【系统音频监听结果】(语言: {lang})\n{text}"
        except Exception as e:
            return f"❌ 系统内录失败: {str(e)}"

    def list_installed_applications(self) -> str:
        from pathlib import Path
        try:
            start_menu_paths = [
                Path(os.getenv('APPDATA')) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.getenv('ProgramData')) / "Microsoft/Windows/Start Menu/Programs",
            ]
            desktop_path = Path(os.path.expanduser("~/Desktop"))
            all_apps = []; seen = set()
            for base in start_menu_paths + [desktop_path]:
                if not base.exists(): continue
                for s in base.rglob("*.lnk"):
                    name = s.stem
                    if any(kw in name.lower() for kw in ['uninstall','卸载','readme','help']): continue
                    if name not in seen: seen.add(name); all_apps.append({"name":name,"path":str(s)})
            all_apps.sort(key=lambda x: x['name'])
            names = [a['name'] for a in all_apps]
            result = f"✅ 找到 {len(names)} 个已安装的应用：\n\n"
            result += "\n".join(f"  - {n}" for n in names[:50])
            if len(names) > 50: result += f"\n\n... 还有 {len(names)-50} 个应用"
            return result
        except Exception as e:
            return f"❌ 扫描应用列表失败: {str(e)}"

    def launch_application(self, app_name: str) -> str:
        from pathlib import Path; from difflib import SequenceMatcher
        def calc_sim(s1, s2): return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
        def pinyin_sim(s1, s2):
            try:
                from pypinyin import lazy_pinyin
                p1, p2 = ''.join(lazy_pinyin(s1)), ''.join(lazy_pinyin(s2))
                full = SequenceMatcher(None, p1.lower(), p2.lower()).ratio()
                shorter, longer = (p1, p2) if len(p1) < len(p2) else (p2, p1)
                if shorter.lower() in longer.lower(): return max(full, 0.85)
                return full
            except ImportError: return calc_sim(s1, s2)
        try:
            # [修复#11] 缓存快捷方式列表，避免每次都扫描文件系统（32秒→即时）
            _CACHE_TTL = 600  # 缓存10分钟
            now = time.time()
            if not hasattr(self, '_shortcut_cache') or not self._shortcut_cache or \
               now - getattr(self, '_shortcut_cache_time', 0) > _CACHE_TTL:
                start_menu_paths = [
                    Path(os.getenv('APPDATA')) / "Microsoft/Windows/Start Menu/Programs",
                    Path(os.getenv('ProgramData')) / "Microsoft/Windows/Start Menu/Programs",
                ]
                desktop = Path(os.path.expanduser("~/Desktop"))
                all_sc = []
                for base in start_menu_paths + [desktop]:
                    if not base.exists(): continue
                    for s in base.rglob("*.lnk"): all_sc.append(s)
                self._shortcut_cache = all_sc
                self._shortcut_cache_time = now
                logger.info(f"📂 [缓存] 已扫描 {len(all_sc)} 个快捷方式并缓存")
            else:
                all_sc = self._shortcut_cache
                logger.debug(f"📂 [缓存] 使用缓存的 {len(all_sc)} 个快捷方式")

            matched = []
            for sc in all_sc:
                name = sc.stem; score = 0
                if app_name.lower() == name.lower(): score = 1.0
                elif app_name.lower() in name.lower() or name.lower() in app_name.lower(): score = 0.8
                else:
                    ps = pinyin_sim(app_name, name)
                    if ps > 0.7: score = ps * 0.9
                    else:
                        cs = calc_sim(app_name, name)
                        if cs > 0.6: score = cs * 0.7
                if score > 0.6: matched.append((sc, score))
            matched.sort(key=lambda x: x[1], reverse=True)
            found = [m[0] for m in matched]
            if found:
                best = found[0]
                ps_script = f"$shell = New-Object -ComObject WScript.Shell\n$shortcut = $shell.CreateShortcut('{best}')\nStart-Process -FilePath $shortcut.TargetPath -WorkingDirectory $shortcut.WorkingDirectory"
                r = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=10, encoding='utf-8', errors='ignore')
                if r.returncode == 0: return f"✅ 已启动 {best.stem}"
            r = subprocess.run(["cmd", "/c", "start", "", app_name], capture_output=True, text=True, timeout=5, encoding='utf-8', errors='ignore')
            if r.returncode == 0: return f"✅ 已启动 {app_name}"
            suggestions = [s.stem for s in found[:3]] if found else []
            if suggestions: return f"❌ 未找到「{app_name}」，您是否想启动：{', '.join(suggestions)}？"
            return f"❌ 未找到「{app_name}」"
        except subprocess.TimeoutExpired:
            return f"❌ 启动 {app_name} 超时"
        except Exception as e:
            return f"❌ 启动失败: {str(e)}"

    def execute_shell_command(self, command: str, timeout: int = 60) -> str:
        logger.info(f"⚡ [Shell] AI 申请执行: {command}")
        command_lower = command.lower()
        forbidden = ["format ", "mkfs", "dd if=", "> /dev/sda", "clear-disk", "format-volume", "shutdown", "restart", "reboot", "poweroff", "reg delete hklm", "reg delete hkcr", ":(){ :|:& };:", "%0|%0", "c:\\windows", "c:\\program files", "system32"]
        for p in forbidden:
            if p.lower() in command_lower:
                return f"❌ [安全拦截] 命令包含高危操作 '{p}'，已拒绝执行。"
        delete_kw = ["remove-item", "del ", "rm ", "rd ", "rmdir", "rm -r", "rm -f"]
        if any(kw in command_lower for kw in delete_kw):
            danger = ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "system32", "syswow64", "$env:windir", "$env:systemroot", "\\appdata\\roaming\\microsoft", "/etc", "/usr", "/bin", "/sbin", "/boot", "/var"]
            if any(dp in command_lower for dp in danger):
                return "❌ [安全拦截] 禁止删除系统关键目录！"
        try:
            result = subprocess.run(["powershell", "-Command", command], capture_output=True, timeout=timeout, cwd=str(self.config.PROJECT_ROOT))
            try:
                stdout = result.stdout.decode('utf-8', errors='ignore').strip()
                stderr = result.stderr.decode('utf-8', errors='ignore').strip()
            except:
                stdout = result.stdout.decode('gbk', errors='ignore').strip()
                stderr = result.stderr.decode('gbk', errors='ignore').strip()
            parts = []
            if stdout: parts.append(f"【标准输出】:\n{stdout[:2000]}{'...(已截断)' if len(stdout)>2000 else ''}")
            if stderr: parts.append(f"【错误信息】:\n{stderr[:1000]}{'...(已截断)' if len(stderr)>1000 else ''}")
            out = "\n\n".join(parts)
            if result.returncode == 0:
                return f"✅ 命令执行成功 (返回码: 0)\n\n{out}" if out else "✅ 命令执行成功，无文本输出。"
            else:
                return f"❌ 命令执行失败 (返回码: {result.returncode})\n\n{out}\n\n👉 请分析报错信息。"
        except subprocess.TimeoutExpired:
            return f"❌ 命令执行超时 ({timeout}秒)，已强制终止。"
        except Exception as e:
            return f"❌ Shell 执行错误: {str(e)}"

    def toggle_auto_execute(self, enable: bool = True) -> str:
        self.auto_execute = enable
        if enable:
            self.mouth.speak("收到，指挥官。自主执行模式已开启。")
            return "✅ 自主执行模式已开启。"
        else:
            self.mouth.speak("好的指挥官，已切换回安全模式。")
            return "✅ 已切换回安全模式。"

    def get_time(self) -> str:
        return f"现在是 {datetime.datetime.now().strftime('%H点%M分')}。"

    def get_date(self) -> str:
        return f"今天是 {datetime.datetime.now().strftime('%Y年%m月%d日')}。"

    def check_battery(self) -> str:
        b = psutil.sensors_battery()
        return f"电量 {b.percent}%" if b else "无电池信息"

    def check_status(self) -> str:
        return f"CPU {psutil.cpu_percent()}%"
