
# =====================================================
# 🎮 Project Fuguang - IDE Entry Point
# =====================================================
# 【Usage】
# python run.py
# =====================================================

from .logger import setup_logger
from .core import NervousSystem

if __name__ == "__main__":
    setup_logger()  # 初始化日志（写入 logs/fuguang.log）
    app = NervousSystem()
    app.run()
