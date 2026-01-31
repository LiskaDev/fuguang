"""
扶光的注视追踪器 (Gaze Tracker)
功能：后台线程，持续检测人脸位置并发送给 Unity，实现眼神跟踪
"""
import time
import threading
import logging

logger = logging.getLogger("Fuguang")


class GazeTracker(threading.Thread):
    """
    注视追踪线程
    
    功能：
    - 后台持续检测人脸位置
    - 通过 UDP 发送 look:x,y 指令给 Unity
    - Unity 根据坐标控制角色头部/眼睛朝向
    """
    
    def __init__(self, camera, mouth, fps: float = 10):
        """
        初始化注视追踪器
        
        Args:
            camera: Camera 实例
            mouth: Mouth 实例（用于发送 UDP）
            fps: 检测频率（每秒次数），默认 10 FPS
        """
        super().__init__()
        self.camera = camera
        self.mouth = mouth
        self.interval = 1.0 / fps  # 检测间隔（秒）
        
        self._running = False
        self._enabled = True  # 是否启用注视追踪
        
        # 统计信息
        self._detect_count = 0
        self._found_count = 0
        
        self.daemon = True  # 守护线程，主程序退出时自动结束
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if value:
            logger.info("👀 注视追踪已启用")
        else:
            logger.info("👀 注视追踪已暂停")
    
    def run(self):
        """线程主循环"""
        self._running = True
        logger.info("👀 注视追踪器启动")
        
        while self._running:
            try:
                if self._enabled:
                    found, x, y = self.camera.get_face_position()
                    self._detect_count += 1
                    
                    if found:
                        self._found_count += 1
                        # 发送注视指令给 Unity
                        msg = f"look:{x:.2f},{y:.2f}"
                        self.mouth.send_to_unity(msg)
                        
                        # 调试日志（默认关闭，太吵）
                        # logger.debug(f"👀 注视: {msg}")
                
                time.sleep(self.interval)
                
            except Exception as e:
                logger.error(f"注视追踪异常: {e}")
                time.sleep(1)  # 出错后等待 1 秒再继续
    
    def stop(self):
        """停止追踪线程"""
        self._running = False
        logger.info(f"👀 注视追踪器停止 (检测:{self._detect_count}, 命中:{self._found_count})")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        hit_rate = (self._found_count / self._detect_count * 100) if self._detect_count > 0 else 0
        return {
            "detect_count": self._detect_count,
            "found_count": self._found_count,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# 测试入口
if __name__ == "__main__":
    print("👀 注视追踪器测试")
    
    # Mock 对象用于测试
    class MockCamera:
        def get_face_position(self):
            import random
            if random.random() > 0.3:
                return True, random.uniform(-0.5, 0.5), random.uniform(-0.3, 0.3)
            return False, 0, 0
    
    class MockMouth:
        def send_to_unity(self, msg):
            print(f"  → Unity: {msg}")
    
    tracker = GazeTracker(MockCamera(), MockMouth(), fps=2)
    tracker.start()
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        pass
    
    tracker.stop()
    print(f"统计: {tracker.get_stats()}")
