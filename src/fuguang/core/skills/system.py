"""
SystemSkills — 🐚 系统命令类技能
Shell 执行、文件操作、应用启动、音量控制、提醒、笔记、代码生成/执行
"""
import subprocess, os, time, datetime, logging, json
import psutil, keyboard

from .base import WHISPER_AVAILABLE

logger = logging.getLogger("fuguang.skills")

_SYSTEM_TOOLS_SCHEMA = [
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

    def execute_shell(self, command: str, background: bool = False) -> str:
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
            except: pass
            return f"✅ 已记录到桌面: {filename.name}"
        except Exception as e:
            return f"记录失败: {str(e)}"

    def write_code(self, filename: str, code_content: str) -> str:
        if not filename.endswith(".py"): filename += ".py"
        full_path = self.config.GENERATED_DIR / filename
        try:
            with open(full_path, "w", encoding="utf-8") as f: f.write(code_content)
            self.mouth.speak(f"代码已生成：{filename}，正在为你打开。")
            try:
                result = subprocess.run(["code", str(full_path)], capture_output=True, timeout=5)
                if result.returncode != 0: raise Exception()
            except:
                try: os.startfile(str(full_path))
                except: pass
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
            try: os.system(cmd); return True
            except: return False
        return False

    def open_tool(self, tool_name: str) -> str:
        if self.open_app(tool_name): return "✅ 已打开"
        self.mouth.speak(f"正在打开{tool_name}...")
        try: os.system(f"start {tool_name}"); return f"✅ 尝试启动: {tool_name}"
        except Exception as e: return f"❌ 打开失败: {str(e)}"

    def set_reminder(self, content: str, target_time: str, auto_action: dict = None) -> str:
        try:
            datetime.datetime.strptime(target_time, "%Y-%m-%d %H:%M:%S")
            reminder_task = {"time": target_time, "content": content}
            if auto_action and isinstance(auto_action, dict):
                reminder_task["auto_action"] = auto_action
                action_desc = f"（到时将自动执行: {auto_action.get('tool_name', '未知操作')}）"
                self.mouth.speak(f"好的，已设置提醒，会在 {target_time} 叫你，并自动帮你执行。")
            else:
                action_desc = ""
                self.mouth.speak(f"好的，已设置提醒，会在 {target_time} 叫你。")
            self.reminders.append(reminder_task)
            self._save_reminders_to_disk()
            self.take_note(f"设定提醒 {target_time}: {content}{action_desc}", category="待办")
            return f"✅ 已设定提醒: {target_time} {content}{action_desc}"
        except ValueError:
            return f"❌ 时间格式错误"

    def check_reminders(self):
        current_time = datetime.datetime.now()
        active_reminders = []; is_changed = False
        for task in self.reminders:
            task_time = datetime.datetime.strptime(task["time"], "%Y-%m-%d %H:%M:%S")
            if current_time >= task_time:
                self.mouth.send_to_unity("Surprised")
                self.mouth.speak(f"指挥官，{task['content']}")
                self._show_toast("Fuguang IDE 提醒", task['content'])
                if "auto_action" in task and task["auto_action"]:
                    action = task["auto_action"]
                    try:
                        result = self.execute_tool(action.get("tool_name", ""), action.get("arguments", {}))
                        self.mouth.speak("已自动帮你执行~")
                    except Exception as e:
                        self.mouth.speak("自动操作出了点问题...")
                is_changed = True
            else:
                active_reminders.append(task)
        if is_changed:
            self.reminders = active_reminders
            self._save_reminders_to_disk()

    def run_code(self, filename: str) -> str:
        import sys as _sys
        if not filename.endswith(".py"): filename += ".py"
        file_path = self.config.GENERATED_DIR / filename
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
            except: pass
            user_confirm = input("是否允许运行? [y/n]: ").strip().lower()
            if user_confirm != 'y': return "❌ 指挥官拒绝了代码执行请求。"
        try:
            with open(file_path, 'r', encoding='utf-8') as f: code_content = f.read()
            is_interactive = 'input(' in code_content
        except: is_interactive = False
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
        logger.info(f"👂 [系统听觉] 正在通过 WASAPI 监听扬声器 {duration} 秒...")
        try:
            speaker = sc.default_speaker(); loopback = sc.get_microphone(id=str(speaker.id), include_loopback=True)
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
            start_menu_paths = [
                Path(os.getenv('APPDATA')) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.getenv('ProgramData')) / "Microsoft/Windows/Start Menu/Programs",
            ]
            desktop = Path(os.path.expanduser("~/Desktop"))
            all_sc = []
            for base in start_menu_paths + [desktop]:
                if not base.exists(): continue
                for s in base.rglob("*.lnk"): all_sc.append(s)
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
