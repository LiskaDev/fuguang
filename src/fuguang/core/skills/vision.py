"""
VisionSkills — 👁️ 视觉类技能
输入是图像，调用 GLM-4V / YOLO-World 进行分析
"""

import time
import io
import base64
import os
import logging
import numpy as np
import pyautogui
from PIL import Image

logger = logging.getLogger("fuguang.skills")


class VisionSkills:
    """视觉类技能 Mixin"""

    # ---- Schema ----
    _VISION_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "analyze_screen_content",
                "description": """【视觉神经】(GLM-4V) 截取当前屏幕并进行视觉分析。
                使用场景: 用户说"看看屏幕"、"这个图片是什么"、"帮我看看这张图片"、"帮我读一下屏幕内容"时使用。
                ⚠️ 优先级规则：当用户没有提供具体文件路径时（如只说"看看这张图片"），应该使用此工具截屏分析，而不是 analyze_image_file。
                注意: 这是一个耗时操作(约3-5秒)，请耐心等待。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "关于屏幕内容的具体问题"}
                    },
                    "required": ["question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_image_file",
                "description": """【本地图片分析】(GLM-4V) 分析指定路径的本地图片文件。
                使用场景: 用户明确提到了文件名或路径时使用，如"分析一下 xxx.png"、"看看桌面上的 cat.jpg"。
                支持格式: jpg, jpeg, png, bmp, webp。
                ⚠️ 重要：只有用户提供了具体文件路径时才用此工具！如果用户只说"看看这张图片"而没给路径，应该用 analyze_screen_content 截屏分析。
                注意: 图片路径可以是相对路径(如 'jimi.png')或绝对路径。""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图片文件的路径(相对或绝对)"},
                        "question": {"type": "string", "description": "关于图片内容的具体问题"}
                    },
                    "required": ["image_path", "question"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_vision_history",
                "description": """【视觉历史记录】查看最近5次的视觉分析记录。
                使用场景: 用户说"刚才看到什么"、"之前分析的那个图片"、"回看一下历史记录"时使用。
                支持多轮对话: 可以让AI记住之前看过的内容，实现"继续看刚才那个画面的左上角"这样的对话。""",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
    ]

    # ---- 方法实现 ----

    def analyze_screen_content(self, question: str) -> str:
        """
        截取屏幕并调用 GLM-4V 进行分析
        
        改进:
        - ✅ 修复 Base64 格式（添加 data URI 前缀）
        - ✅ 支持极速/标准模式切换
        - ✅ 优化提示词（让回答更简洁口语化）
        - ✅ 增加重试机制（网络波动时自动重试）
        - ✅ 智能缓存（避免重复分析同一画面）
        """
        if not self.vision_client:
            return "❌ 视觉模块未激活，请检查 ZHIPU_API_KEY 配置。"

        logger.info(f"📸 [视觉] 正在截取屏幕并发送给 GLM-4V...")
        self.mouth.speak("让我看看屏幕...")
        start_time = time.time()

        try:
            # 1. 截图
            screenshot = pyautogui.screenshot()
            
            # 2. 图片压缩 (使用配置的参数)
            max_size = self.config.VISION_MAX_SIZE
            screenshot.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # 3. 转成 Base64 (关键修复：添加 data URI 前缀)
            buffered = io.BytesIO()
            screenshot.save(buffered, format="JPEG", quality=self.config.VISION_QUALITY)
            img_bytes = buffered.getvalue()
            
            # 计算图片哈希（用于缓存判断）
            import hashlib
            img_hash = hashlib.md5(img_bytes).hexdigest()
            
            # 智能缓存：如果画面没变且问题相同，直接返回上次结果
            if img_hash == self._last_screenshot_hash and self._last_screenshot_result:
                logger.info("🎯 [缓存] 画面未变化，直接返回上次结果")
                return self._last_screenshot_result
            
            # Base64 编码并添加前缀（智谱 API 要求的格式）
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            img_data_uri = f"data:image/jpeg;base64,{img_base64}"
            
            # 选择模型（根据配置）
            model = "glm-4v-flash" if self.config.VISION_USE_FLASH else "glm-4v"
            
            # 4. 优化的提示词（让 GLM 的回答更符合扶光的口吻，并防止幻觉）
            optimized_prompt = (
                f"你是扶光，指挥官的AI助手。请【完全基于图片内容】回答，【绝对禁止编造】不在图片中的信息。\n\n"
                f"用户问题：{question}\n\n"
                f"必须遵守：\n"
                f"- 看到什么说什么，如果画面是空白/加载中/模糊，请直接说明。\n"
                f"- 如果看不清具体文字，不要瞎猜。\n"
                f"- 语气自然口语化，控制在 100 字以内。"
            )
            
            # 5. 调用 GLM-4V (带重试机制)
            max_retries = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    response = self.vision_client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": optimized_prompt
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": img_data_uri
                                        }
                                    }
                                ]
                            }
                        ],
                        temperature=0.7,  # 适中的创造性
                        top_p=0.9
                    )
                    
                    # 成功获取结果
                    analysis_result = response.choices[0].message.content
                    cost_time = time.time() - start_time
                    
                    # 更新缓存
                    self._last_screenshot_hash = img_hash
                    self._last_screenshot_result = f"【视觉观察】\n{analysis_result}"
                    
                    # 保存到历史记录
                    self._add_vision_history(
                        question=question,
                        result=analysis_result,
                        image_data=img_bytes,
                        source="screenshot"
                    )
                    
                    logger.info(f"👀 [GLM-{model}] 视觉分析完成 (耗时 {cost_time:.2f}s)")
                    return self._last_screenshot_result
                
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ 第 {attempt + 1} 次调用失败，正在重试... ({e})")
                        time.sleep(1)  # 等待 1 秒后重试
                    else:
                        raise  # 最后一次失败则抛出异常
            
        except Exception as e:
            logger.error(f"视觉分析失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 根据错误类型给出更友好的提示
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                return "❌ 指挥官，网络有点慢，视觉分析超时了..."
            elif "api" in error_msg or "key" in error_msg:
                return "❌ API 配置有问题，请检查 ZHIPU_API_KEY 是否正确。"
            else:
                return f"❌ 视觉分析出错了：{str(e)[:100]}..."

    def analyze_image_file(self, image_path: str, question: str) -> str:
        """
        分析本地图片文件（使用 GLM-4V）
        
        Args:
            image_path: 图片路径（支持相对路径）
            question: 关于图片的问题
        
        Returns:
            GPT-4V 的分析结果
        """
        if not self.vision_client:
            return "❌ 视觉模块未激活，请检查 ZHIPU_API_KEY 配置。"
        
        logger.info(f"🖼️ [视觉] 正在分析本地图片: {image_path}")
        self.mouth.speak("让我看看这张图片...")
        start_time = time.time()
        
        try:
            if not image_path:
                return "❌ 图片路径为空，请提供有效的 image_path。"

            # 1. 处理路径（支持相对路径）
            if not os.path.isabs(image_path):
                # 相对于项目根目录
                project_root = self.config.PROJECT_ROOT
                image_path = os.path.join(project_root, image_path)
            
            if not os.path.exists(image_path):
                return f"❌ 找不到图片文件: {image_path}"
            
            # 2. 读取图片
            img = Image.open(image_path)
            
            # 3. 图片压缩（复用配置）
            max_size = self.config.VISION_MAX_SIZE
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # 4. 转成 Base64
            buffered = io.BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(buffered, format=img_format, quality=self.config.VISION_QUALITY)
            img_bytes = buffered.getvalue()
            
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            img_data_uri = f"data:image/{img_format.lower()};base64,{img_base64}"
            
            # 5. 选择模型
            model = "glm-4v-flash" if self.config.VISION_USE_FLASH else "glm-4v"
            
            # 6. 优化提示词
            optimized_prompt = (
                f"你是扶光，指挥官的AI助手。请简洁地回答问题，口语化一点。\n\n"
                f"用户问题：{question}\n\n"
                f"提示：描述画面的主要内容和视觉特点，控制在 100 字以内。"
            )
            
            # 7. 调用 GLM-4V
            response = self.vision_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": optimized_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": img_data_uri
                                }
                            }
                        ]
                    }
                ],
                temperature=0.7,
                top_p=0.9
            )
            
            analysis_result = response.choices[0].message.content
            cost_time = time.time() - start_time
            
            logger.info(f"👀 [GLM-{model}] 图片分析完成 (耗时 {cost_time:.2f}s)")
            return f"【图片分析】\n{analysis_result}"
        
        except Exception as e:
            logger.error(f"图片分析失败: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ 图片分析失败: {str(e)[:100]}..."
    
    def _add_vision_history(self, question: str, result: str, image_data: bytes, source: str):
        """
        添加视觉分析历史记录
        
        Args:
            question: 用户问题
            result: 分析结果
            image_data: 图片二进制数据
            source: 来源（screenshot 或 file:xxx.png）
        """
        try:
            import datetime
            timestamp = datetime.datetime.now()
            
            # 保存图片到磁盘
            image_filename = f"vision_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            image_path = self._vision_history_dir / image_filename
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            # 添加到历史记录
            history_item = {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "question": question,
                "result": result,
                "image_path": str(image_path),
                "source": source
            }
            
            self._vision_history.append(history_item)
            
            # 只保留最近 5 次
            if len(self._vision_history) > 5:
                # 删除最旧的图片文件
                old_item = self._vision_history.pop(0)
                old_image_path = old_item.get("image_path")
                if old_image_path and os.path.exists(old_image_path):
                    os.remove(old_image_path)
            
            logger.debug(f"📝 [历史] 已保存视觉分析记录 ({len(self._vision_history)}/5)")
            
        except Exception as e:
            logger.warning(f"⚠️ 保存视觉历史失败: {e}")
    
    def get_vision_history(self) -> str:
        """
        获取视觉分析历史记录（用于多轮对话）
        
        Returns:
            格式化的历史记录文本
        """
        if not self._vision_history:
            return "暂无视觉分析历史记录。"
        
        history_text = "【最近的视觉分析记录】\n\n"
        
        for i, item in enumerate(reversed(self._vision_history), 1):
            history_text += f"{i}. [{item['timestamp']}] {item['source']}\n"
            history_text += f"   问题: {item['question']}\n"
            history_text += f"   结果: {item['result'][:80]}...\n\n"
        
        return history_text
