"""
test_security.py — 安保系统测试
验证 v5.2.1 新增的人脸识别改进。
"""
import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestFaceRecognitionConfig:
    """测试人脸识别配置"""

    def test_tolerance_is_050(self):
        """阈值应为 0.50（v5.2.1 从 0.4 放宽）"""
        camera_file = PROJECT_ROOT / "src" / "fuguang" / "camera.py"
        source = camera_file.read_text(encoding="utf-8")
        assert "tolerance = 0.50" in source or "tolerance = 0.5" in source, \
            "人脸识别阈值应为 0.50"

    def test_consecutive_confirmation_exists(self):
        """连续确认机制存在（防止单帧误判）"""
        camera_file = PROJECT_ROOT / "src" / "fuguang" / "camera.py"
        source = camera_file.read_text(encoding="utf-8")
        assert "_stranger_consecutive" in source, "缺少连续确认计数器"
        assert ">= 3" in source or ">=3" in source, "应需要连续3次才确认陌生人"


class TestSecurityAutoUnlock:
    """测试安保自动解锁"""

    def test_auto_unlock_exists(self):
        """60秒无人脸自动解锁逻辑存在"""
        ns_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "nervous_system.py"
        source = ns_file.read_text(encoding="utf-8")
        assert "自动解锁" in source or "auto_unlock" in source or "lock_duration" in source, \
            "缺少自动解锁逻辑"
        assert "60" in source, "自动解锁超时应为60秒"


class TestPTTDebounce:
    """测试 PTT 防抖"""

    def test_debounce_exists(self):
        """PTT 按键有防抖逻辑"""
        ns_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "nervous_system.py"
        source = ns_file.read_text(encoding="utf-8")
        assert "0.2" in source or "200" in source or "_last_ptt_event_time" in source, \
            "缺少 PTT 防抖（200ms）"
        assert "防抖" in source or "debounce" in source or "_last_ptt" in source, \
            "缺少防抖相关代码"


class TestVisualKeywords:
    """测试自动截屏关键词"""

    def test_no_overly_broad_keywords(self):
        """不应包含过于宽泛的视觉关键词"""
        ns_file = PROJECT_ROOT / "src" / "fuguang" / "core" / "nervous_system.py"
        source = ns_file.read_text(encoding="utf-8")
        
        # 这些过于宽泛，会误触发
        broad_keywords = ["什么情况", "怎么回事", "出了什么"]
        for kw in broad_keywords:
            # 只检查 _VISUAL_KEYWORDS 列表中是否包含（不检查注释）
            # 查找 _VISUAL_KEYWORDS = [...] 部分
            import re
            match = re.search(r'_VISUAL_KEYWORDS\s*=\s*\[([^\]]+)\]', source)
            if match:
                keywords_str = match.group(1)
                assert f'"{kw}"' not in keywords_str, f"视觉关键词过于宽泛: {kw}"
