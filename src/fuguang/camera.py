"""
扶光的眼睛 (Camera Module) v2.0 - 人脸检测 + 坐标追踪
功能：
  1. 检测用户是否在座位上
  2. 计算人脸坐标，用于注视追踪
"""
import cv2
import time
import threading
import logging

logger = logging.getLogger("Fuguang")


class Camera:
    """
    物理眼睛 - 摄像头人脸检测（单例模式）
    
    特性：
    - 单例模式：整个程序只有一个实例
    - 线程安全：使用锁保护摄像头访问
    - 坐标计算：支持注视追踪
    """
    
    _instance = None
    _init_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if not cls._instance:
            with cls._init_lock:
                if not cls._instance:
                    cls._instance = super(Camera, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, camera_index: int = 0):
        """初始化摄像头（只执行一次）"""
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self.camera_index = camera_index
        self.cap = None
        
        # 加载人脸识别模型
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(face_cascade_path)
        
        # 线程安全
        self._lock = threading.Lock()
        
        # 缓存机制
        self._cache_cooldown = 0.05  # 50ms
        self._last_read_time = 0
        self._cached_found = False
        self._cached_x = 0.0
        self._cached_y = 0.0
        
        # 用于 is_user_present 的冷却
        self._presence_cooldown = 2.0
        self._last_presence_time = 0
        self._cached_presence = False
        
        self._initialized = True
        logger.info("📷 摄像头模块初始化完成（单例模式）")
    
    def _open_camera(self) -> bool:
        """打开摄像头（延迟初始化）"""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning("⚠️ 无法打开摄像头")
                return False
        return True
    
    def get_face_position(self) -> tuple:
        """
        获取人脸的相对坐标（用于注视追踪）
        
        Returns:
            (found, x, y):
            - found: bool - 是否检测到人脸
            - x: float - -1.0 (左) ~ 1.0 (右)
            - y: float - -1.0 (下) ~ 1.0 (上)
        """
        with self._lock:
            # 缓存机制：防止读取太快
            current_time = time.time()
            if current_time - self._last_read_time < self._cache_cooldown:
                return self._cached_found, self._cached_x, self._cached_y
            
            self._last_read_time = current_time
            
            # 打开摄像头
            if not self._open_camera():
                return False, 0.0, 0.0
            
            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self._cached_found = False
                    return False, 0.0, 0.0
                
                # 转灰度图加速
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                
                if len(faces) > 0:
                    # 取第一张脸
                    (fx, fy, fw, fh) = faces[0]
                    height, width = frame.shape[:2]
                    
                    # 计算人脸中心点
                    face_center_x = fx + fw / 2
                    face_center_y = fy + fh / 2
                    
                    # 归一化 (-1 ~ 1)
                    norm_x = (face_center_x - width / 2) / (width / 2)
                    norm_y = (face_center_y - height / 2) / (height / 2)
                    
                    # 镜像修正：
                    # - X 取反：摄像头里的"右"是你的"左"
                    # - Y 取反：让抬头为正，低头为负
                    self._cached_found = True
                    self._cached_x = -norm_x
                    self._cached_y = -norm_y
                    
                    return True, self._cached_x, self._cached_y
                
                self._cached_found = False
                return False, 0.0, 0.0
                
            except Exception as e:
                logger.error(f"人脸坐标检测异常: {e}")
                return False, 0.0, 0.0
    
    def is_user_present(self) -> bool:
        """
        检测用户是否在座位上（用于主动对话触发）
        
        Returns:
            True: 检测到人脸
            False: 未检测到人脸
        """
        # 冷却机制：每 2 秒最多检测一次
        current_time = time.time()
        if current_time - self._last_presence_time < self._presence_cooldown:
            return self._cached_presence
        
        self._last_presence_time = current_time
        
        with self._lock:
            if not self._open_camera():
                return False
            
            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self._cached_presence = False
                    return False
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
                )
                
                self._cached_presence = len(faces) > 0
                
                if self._cached_presence:
                    logger.info(f"📸 视觉确认：检测到 {len(faces)} 张人脸，指挥官在座")
                
                # 检测完释放摄像头（节省资源，避免指示灯常亮）
                # 注意：如果 GazeTracker 在运行，这里不应该释放
                # 但单独调用 is_user_present 时可以释放
                
                return self._cached_presence
                
            except Exception as e:
                logger.error(f"用户在座检测异常: {e}")
                self._cached_presence = False
                return False
    
    def show_feed(self, duration: int = 10):
        """调试功能：显示摄像头检测状态（终端输出模式）"""
        if not self._open_camera():
            print("❌ 无法打开摄像头")
            return
        
        print(f"📷 摄像头调试开始，{duration}秒后自动结束...")
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                found, x, y = self.get_face_position()
                elapsed = int(time.time() - start_time)
                
                if found:
                    print(f"\r[{elapsed}s] ✅ 人脸坐标: X={x:+.2f}, Y={y:+.2f}   ", end="", flush=True)
                else:
                    print(f"\r[{elapsed}s] ❌ 未检测到人脸                    ", end="", flush=True)
                
                time.sleep(0.2)
        
        except KeyboardInterrupt:
            pass
        
        finally:
            print("\n📷 摄像头调试结束")
    
    def release(self):
        """释放摄像头资源"""
        with self._lock:
            if self.cap is not None and self.cap.isOpened():
                self.cap.release()
                self.cap = None
        logger.info("📷 摄像头模块已释放")


# 便捷方法
def get_camera() -> Camera:
    """获取摄像头单例"""
    return Camera()


def is_user_present() -> bool:
    """快捷方法：检测用户是否在座"""
    return get_camera().is_user_present()


# 测试入口
if __name__ == "__main__":
    print("📷 摄像头模块测试")
    cam = Camera()
    
    # 方式1：快速检测
    print(f"用户在座: {cam.is_user_present()}")
    
    # 方式2：坐标检测
    found, x, y = cam.get_face_position()
    print(f"人脸检测: found={found}, x={x:.2f}, y={y:.2f}")
    
    # 方式3：持续调试
    cam.show_feed(duration=10)
    
    cam.release()
