"""
扶光的眼睛 (Camera Module) - 人脸检测
功能：通过摄像头检测用户是否在座位上
"""
import cv2
import time
import logging

logger = logging.getLogger("Fuguang")


class Camera:
    """
    物理眼睛 - 摄像头人脸检测
    
    用途：在主动对话前检测用户是否在座位上，避免对着空气说话
    """
    
    def __init__(self, camera_index: int = 0):
        """
        初始化摄像头
        
        Args:
            camera_index: 摄像头索引，0 通常是默认摄像头
        """
        self.camera_index = camera_index
        self.cap = None  # 延迟初始化，不占用资源
        
        # 加载人脸识别模型（Haar 级联分类器）
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(face_cascade_path)
        
        # 冷却机制
        self.last_check_time = 0
        self.last_result = False
        self.check_cooldown = 2.0  # 每 2 秒最多检测一次
        
        logger.info("📷 摄像头模块初始化完成")
    
    def _open_camera(self) -> bool:
        """打开摄像头（延迟初始化）"""
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.warning("⚠️ 无法打开摄像头")
                return False
        return True
    
    def is_user_present(self) -> bool:
        """
        检测摄像头画面中是否有人
        
        Returns:
            True: 检测到人脸
            False: 未检测到人脸或摄像头不可用
        """
        # 冷却机制：防止 CPU 占用过高
        current_time = time.time()
        if current_time - self.last_check_time < self.check_cooldown:
            return self.last_result
        
        self.last_check_time = current_time
        
        # 打开摄像头
        if not self._open_camera():
            return False
        
        try:
            # 读取一帧
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.last_result = False
                return False
            
            # 转灰度图（加速检测）
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 检测人脸
            # scaleFactor: 每次图像缩小的比例
            # minNeighbors: 每个候选矩形需要多少个邻居来保留
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(30, 30)
            )
            
            self.last_result = len(faces) > 0
            
            if self.last_result:
                logger.info(f"📸 视觉确认：检测到 {len(faces)} 张人脸，指挥官在座")
            
            # 释放摄像头（节省资源，避免指示灯常亮）
            self._release_camera()
            
            return self.last_result
            
        except Exception as e:
            logger.error(f"人脸检测异常: {e}")
            self.last_result = False
            return False
    
    def _release_camera(self):
        """释放摄像头资源"""
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None
    
    def show_feed(self, duration: int = 10):
        """
        调试功能：显示摄像头画面并在人脸上画框
        
        Args:
            duration: 显示持续时间（秒）
        """
        if not self._open_camera():
            print("❌ 无法打开摄像头")
            return
        
        # 尝试使用 GUI 模式
        gui_available = True
        try:
            # 测试是否支持 GUI
            cv2.namedWindow("test", cv2.WINDOW_NORMAL)
            cv2.destroyWindow("test")
        except cv2.error:
            gui_available = False
            print("⚠️ 当前 OpenCV 不支持 GUI 窗口，将使用终端输出模式")
        
        print(f"📷 摄像头调试开始，{duration}秒后自动结束...")
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                # 转灰度检测人脸
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                
                if gui_available:
                    # GUI 模式：显示窗口
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    status = f"Faces: {len(faces)}"
                    cv2.putText(frame, status, (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    cv2.imshow("Fuguang Camera Debug", frame)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                else:
                    # 终端模式：每秒打印一次状态
                    elapsed = int(time.time() - start_time)
                    if elapsed % 1 == 0:  # 每秒输出一次
                        status = "✅ 检测到人脸" if len(faces) > 0 else "❌ 未检测到人脸"
                        print(f"\r[{elapsed}s] {status} (人脸数: {len(faces)})", end="", flush=True)
                    time.sleep(0.5)
        
        except Exception as e:
            print(f"\n⚠️ 调试出错: {e}")
        
        finally:
            if gui_available:
                try:
                    cv2.destroyAllWindows()
                except:
                    pass
            self._release_camera()
            print("\n📷 摄像头调试结束")
    
    def release(self):
        """释放所有资源"""
        self._release_camera()
        logger.info("📷 摄像头模块已释放")


# 全局单例（延迟初始化）
_camera_instance = None


def get_camera() -> Camera:
    """获取摄像头单例"""
    global _camera_instance
    if _camera_instance is None:
        _camera_instance = Camera()
    return _camera_instance


def is_user_present() -> bool:
    """快捷方法：检测用户是否在座"""
    return get_camera().is_user_present()


# 测试入口
if __name__ == "__main__":
    print("📷 摄像头模块测试")
    cam = Camera()
    
    # 方式1：快速检测
    print(f"用户在座: {cam.is_user_present()}")
    
    # 方式2：调试窗口
    cam.show_feed(duration=10)
    
    cam.release()
