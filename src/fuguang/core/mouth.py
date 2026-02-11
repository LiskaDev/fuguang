
import socket
import logging
from .config import ConfigManager
from .. import voice as fuguang_voice
from .. import heartbeat as fuguang_heartbeat

logger = logging.getLogger("Fuguang")

class Mouth:
    """
    表达与输出角色
    职责：语音合成、UDP通信、表情控制
    """

    def __init__(self, config: ConfigManager):
        self.config = config
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.unity_ip = config.UNITY_IP
        self.unity_port = config.UNITY_PORT
        
        # [新增] GUI 回调钩子 (由 NervousSystem 注入)
        self.on_speech_start = None   # (text: str) -> None
        self.on_speech_end = None     # () -> None

    def close(self):
        """[修复H-2] 关闭 UDP socket 释放资源"""
        try:
            self.udp_socket.close()
            logger.info("🔌 UDP socket 已关闭")
        except Exception as e:
            logger.warning(f"UDP socket 关闭异常: {e}")

    def send_to_unity(self, message: str):
        """发送消息到 Unity"""
        try:
            message = message.replace('\ufe0f', '')  # 移除 emoji 变体选择器
            self.udp_socket.sendto(message.encode('utf-8'), (self.unity_ip, self.unity_port))
        except Exception as e:
            logger.error(f"UDP 失败: {e}")

    def speak(self, text: str):
        """说话 - 语音合成 + Unity 同步"""
        fuguang_heartbeat.update_interaction()
        self.send_to_unity(f"say:{text}")
        
        # [GUI] 通知界面开始说话
        if self.on_speech_start:
            try:
                self.on_speech_start(text)
            except Exception as e:
                logger.warning(f"GUI 语音开始回调异常: {e}")

        try:
            self.send_to_unity("talk_start")
            fuguang_voice.speak(text)
            self.send_to_unity("talk_end")
        except Exception as e:
            logger.error(f"语音播放失败: {e}")
            self.send_to_unity("talk_end")
        finally:
            # [GUI] 通知界面说话结束
            if self.on_speech_end:
                try:
                    self.on_speech_end()
                except Exception as e:
                    logger.warning(f"GUI 语音结束回调异常: {e}")

    def start_thinking(self):
        """发送开始思考指令"""
        self.send_to_unity("think_start")

    def stop_thinking(self):
        """发送停止思考指令"""
        self.send_to_unity("think_end")

    def wave(self):
        """发送挥手指令"""
        self.send_to_unity("wave")
