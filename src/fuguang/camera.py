"""
扶光的眼睛 (Camera Module) v4.5 - 双引擎分离模式
功能：
  1. OpenCV 负责每帧坐标追踪（极速丝滑）
  2. face_recognition 负责身份识别（每 2 秒一次，不阻塞追踪）
"""
import cv2
import face_recognition
import time
import threading
import logging
from pathlib import Path

logger = logging.getLogger("Fuguang")

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Camera:
    """
    物理眼睛 - 双引擎分离模式（单例模式）
    
    引擎分工：
    - OpenCV Haar: 每帧坐标追踪（快）
    - face_recognition: 每 2 秒身份识别（准）
    
    两个引擎独立运行，互不阻塞。
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
        
        # 线程安全
        self._lock = threading.Lock()
        
        # === 引擎 1：OpenCV（极速坐标追踪）===
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        # === 引擎 2：face_recognition（身份识别）===
        self.commander_encoding = None
        self.face_db_path = PROJECT_ROOT / "data" / "face_db" / "commander.jpg"
        self._load_commander_face()
        
        # ===== 身份识别配置（从 config 读取，支持热调整）=====
        try:
            from .config import ConfigManager
            self.identity_check_interval = ConfigManager.IDENTITY_CHECK_INTERVAL
        except (ImportError, AttributeError):
            self.identity_check_interval = 2.0  # 默认值
        self._last_identity_check_time = 0
        self._cached_identity = "Unknown"
        
        # 坐标平滑（防抖动）
        self._last_x = 0.0
        self._last_y = 0.0
        self._smooth_alpha = 0.7
        
        # 用于 is_user_present 的冷却
        self._presence_cooldown = 2.0
        self._last_presence_time = 0
        self._cached_presence = False
        
        self._initialized = True
        logger.info("📷 摄像头模块 v4.5 初始化完成（双引擎分离模式）")
    
    def _load_commander_face(self):
        """加载指挥官的人脸特征底片"""
        if self.face_db_path.exists():
            try:
                image = face_recognition.load_image_file(str(self.face_db_path))
                encodings = face_recognition.face_encodings(image)
                
                if len(encodings) > 0:
                    self.commander_encoding = encodings[0]
                    logger.info("👁️ 鹰眼系统就绪：双引擎分离模式 (OpenCV + face_recognition)")
                else:
                    logger.warning("⚠️ 指挥官照片中未检测到人脸")
            except Exception as e:
                logger.error(f"❌ 加载指挥官档案失败: {e}")
        else:
            logger.warning(f"⚠️ 未找到指挥官照片: {self.face_db_path}")
    
    def _open_camera(self) -> bool:
        """打开摄像头（延迟初始化）"""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning("⚠️ 无法打开摄像头")
                return False
        return True
    
    def get_face_info(self) -> tuple:
        """
        获取人脸信息（坐标 + 身份）
        
        - 坐标：每帧用 OpenCV 计算（丝滑）
        - 身份：每 2 秒用 face_recognition 计算（精准）
        
        Returns:
            (found, x, y, identity)
        """
        with self._lock:
            if not self._open_camera():
                return False, 0.0, 0.0, "Unknown"
            
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return False, 0.0, 0.0, "Unknown"
            
            height, width = frame.shape[:2]
            current_time = time.time()
            
            # === 引擎 1：OpenCV 快速追踪（每帧执行）===
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
            
            if len(faces) == 0:
                return False, 0.0, 0.0, self._cached_identity
            
            # 取最大的一张脸
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            
            # 计算归一化坐标
            cx = x + w / 2
            cy = y + h / 2
            
            # 坐标平滑（防抖动）
            cx = cx * self._smooth_alpha + self._last_x * (1 - self._smooth_alpha)
            cy = cy * self._smooth_alpha + self._last_y * (1 - self._smooth_alpha)
            self._last_x, self._last_y = cx, cy
            
            # 归一化到 -1 ~ 1（镜像修正）
            norm_x = -((cx - width / 2) / (width / 2))
            norm_y = -((cy - height / 2) / (height / 2))
            
            # === 引擎 2：face_recognition 身份识别（每 2 秒执行）===
            if current_time - self._last_identity_check_time >= self.identity_check_interval:
                self._last_identity_check_time = current_time
                
                if self.commander_encoding is not None:
                    # 只裁剪人脸区域，加速识别
                    pad = 30
                    face_roi = frame[
                        max(0, y - pad):min(height, y + h + pad),
                        max(0, x - pad):min(width, x + w + pad)
                    ]
                    
                    if face_roi.size > 0:
                        rgb_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
                        
                        try:
                            face_encodings = face_recognition.face_encodings(rgb_face)
                            
                            if len(face_encodings) > 0:
                                # 计算人脸距离（越小越相似）
                                face_distances = face_recognition.face_distance(
                                    [self.commander_encoding], face_encodings[0]
                                )
                                distance = face_distances[0]
                                
                                # tolerance=0.4 更严格（默认0.6太宽松）
                                # 距离 < 0.4 认为是同一人
                                tolerance = 0.4
                                
                                if distance < tolerance:
                                    self._cached_identity = "Commander"
                                    logger.debug(f"✅ 身份匹配: distance={distance:.3f} < {tolerance}")
                                else:
                                    self._cached_identity = "Stranger"
                                    logger.warning(f"🚨 陌生人: distance={distance:.3f} >= {tolerance}")
                            # 如果没算出特征，保持上次身份不变
                        except Exception as e:
                            logger.debug(f"身份识别异常: {e}")
            
            return True, norm_x, norm_y, self._cached_identity
    
    def get_face_position(self) -> tuple:
        """获取人脸坐标（兼容旧接口）"""
        found, x, y, _ = self.get_face_info()
        return found, x, y
    
    def is_user_present(self) -> bool:
        """检测用户是否在座位上"""
        current_time = time.time()
        if current_time - self._last_presence_time < self._presence_cooldown:
            return self._cached_presence
        
        self._last_presence_time = current_time
        found, _, _, _ = self.get_face_info()
        self._cached_presence = found
        return found
    
    def get_identity(self) -> str:
        """获取当前用户身份（缓存值）"""
        return self._cached_identity
    
    def show_feed(self, duration: int = 10):
        """调试功能：显示摄像头检测状态"""
        if not self._open_camera():
            print("❌ 无法打开摄像头")
            return
        
        print(f"📷 摄像头调试开始，{duration}秒后自动结束...")
        print(f"   坐标追踪: OpenCV (每帧)")
        print(f"   身份识别: face_recognition (每 {self.identity_check_interval}秒)")
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                found, x, y, identity = self.get_face_info()
                elapsed = int(time.time() - start_time)
                
                if found:
                    print(f"\r[{elapsed}s] ✅ X={x:+.2f}, Y={y:+.2f}, ID={identity}   ", end="", flush=True)
                else:
                    print(f"\r[{elapsed}s] ❌ 未检测到人脸                    ", end="", flush=True)
                
                time.sleep(0.05)  # 20 FPS 输出
        
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
    print("📷 摄像头模块 v4.5 测试（双引擎分离模式）")
    print("=" * 50)
    print("特点：坐标每帧更新（丝滑），身份每 2 秒更新（精准）")
    print("=" * 50)
    cam = Camera()
    
    cam.show_feed(duration=15)
    
    cam.release()
