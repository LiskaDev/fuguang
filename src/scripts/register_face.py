"""
人脸注册脚本 - 录入指挥官身份
运行此脚本来注册你的人脸，用于身份识别
"""
import cv2
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def capture_commander_face():
    """捕获指挥官照片并保存到人脸数据库"""
    # 1. 准备目录 (使用绝对路径)
    face_db_dir = PROJECT_ROOT / "data" / "face_db"
    face_db_dir.mkdir(parents=True, exist_ok=True)
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ 无法打开摄像头")
        return
    
    print("=" * 50)
    print("🎥 指挥官身份注册系统")
    print("=" * 50)
    print("请摘掉口罩，正对摄像头...")
    print("👉 按【S】键保存照片")
    print("👉 按【Q】key退出")
    print("=" * 50)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ 读取摄像头失败")
            break
        
        # 画辅助对准框
        height, width = frame.shape[:2]
        center_x, center_y = width // 2, height // 2
        
        # 绿色矩形框
        cv2.rectangle(
            frame, 
            (center_x - 150, center_y - 200), 
            (center_x + 150, center_y + 200), 
            (0, 255, 0), 2
        )
        
        # 标签文字
        cv2.putText(
            frame, "Commander", 
            (center_x - 70, center_y - 210), 
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2
        )
        
        # 操作提示
        cv2.putText(
            frame, "Press [S] to Save, [Q] to Quit", 
            (10, height - 20), 
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )
        
        cv2.imshow('Register Face - Commander', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s') or key == ord('S'):
            # 保存照片
            filename = face_db_dir / "commander.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"\n✅ 指挥官照片已保存至: {filename}")
            print("🎉 录入完成！鹰眼系统现在可以识别你了。")
            break
        elif key == ord('q') or key == ord('Q'):
            print("\n⚠️ 已取消注册")
            break
    
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    capture_commander_face()
