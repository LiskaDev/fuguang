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
        
        # [修复C-4] 状态共享（用于回头杀/害羞机制）- 线程锁保护
        self._state_lock = threading.Lock()
        self._has_face = False           # 当前是否检测到人脸
        self._face_enter_time = 0        # 人脑首次出现的时间戳
        self._last_face_seen_time = 0    # 上次看到人脸的时间戳
        
        self.daemon = True  # 守护线程，主程序退出时自动结束

    # [修复C-4] 线程安全属性访问器
    @property
    def has_face(self) -> bool:
        with self._state_lock:
            return self._has_face
    
    @has_face.setter
    def has_face(self, value: bool):
        with self._state_lock:
            self._has_face = value
    
    @property
    def face_enter_time(self):
        with self._state_lock:
            return self._face_enter_time
    
    @face_enter_time.setter
    def face_enter_time(self, value):
        with self._state_lock:
            self._face_enter_time = value
    
    @property
    def last_face_seen_time(self):
        with self._state_lock:
            return self._last_face_seen_time
    
    @last_face_seen_time.setter
    def last_face_seen_time(self, value):
        with self._state_lock:
            self._last_face_seen_time = value
    
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
                current_time = time.time()
                
                if self._enabled:
                    found, x, y = self.camera.get_face_position()
                    self._detect_count += 1
                    
                    if found:
                        self._found_count += 1
                        
                        # [新增] 状态更新：从无人变有人
                        if not self.has_face:
                            self.face_enter_time = current_time
                            logger.info("👀 检测到用户出现")
                        
                        self.has_face = True
                        self.last_face_seen_time = current_time
                        
                        # 发送注视指令给 Unity
                        msg = f"look:{x:.2f},{y:.2f}"
                        self.mouth.send_to_unity(msg)
                    else:
                        # [新增] 缓冲 2 秒，防止眨眼/光线导致的误判
                        if self.has_face and (current_time - self.last_face_seen_time > 2.0):
                            self.has_face = False
                            logger.info("👀 用户已离开")
                
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
