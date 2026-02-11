
import speech_recognition as sr
from pypinyin import lazy_pinyin
from .. import ali_ear

class Ears:
    """
    感知与输入角色
    职责：麦克风管理、语音识别、唤醒词检测
    """

    WAKE_WORDS = ["扶光", "阿光", "老婆", "宝贝"]

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 3000
        self.recognizer.dynamic_energy_threshold = True

    def check_wake_word_pinyin(self, text: str) -> tuple:
        """
        拼音唤醒词检测
        返回: (是否唤醒, 匹配的唤醒词, 清理后的文本)
        """
        user_pinyin = lazy_pinyin(text)
        for word in self.WAKE_WORDS:
            word_pinyin = lazy_pinyin(word)
            n = len(word_pinyin)
            for i in range(len(user_pinyin) - n + 1):
                if user_pinyin[i:i + n] == word_pinyin:
                    # [修复H-7] 使用拼音匹配位置 i 而非固定取 len(word) 字符
                    clean_text = (text[:i] + text[i + n:]).strip()
                    clean_text = clean_text.lstrip("，。！？、")
                    return True, word, clean_text
        return False, "", text

    def listen_ali(self, audio_data: bytes) -> str:
        """阿里云语音识别"""
        return ali_ear.listen_ali(audio_data)

    def get_microphone(self, sample_rate: int = 16000):
        """获取麦克风上下文"""
        return sr.Microphone(sample_rate=sample_rate)
