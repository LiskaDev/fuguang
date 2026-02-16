# 文件名：ali_ear_v2.py
# 作用：阿里云实时识别（生产模式）

import json
import time
import os
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
try:
    import nls
except ImportError:
    print("❌ 请先安装: pip install alibabacloud_nls_python_sdk")
    exit(1)

# =====================================================
# 配置
# =====================================================
ACCESS_KEY_ID = os.getenv("ALI_ACCESS_KEY_ID")
ACCESS_KEY_SECRET = os.getenv("ALI_ACCESS_KEY_SECRET")
APPKEY = os.getenv("ALI_APPKEY")
REGION_ID = os.getenv("ALI_REGION_ID", "cn-shanghai")

if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET or not APPKEY:
    raise RuntimeError("Missing Aliyun credentials. Set ALI_ACCESS_KEY_ID, ALI_ACCESS_KEY_SECRET, ALI_APPKEY.")

# =====================================================
# Token 缓存（避免重复获取）
# =====================================================
_token_cache = {
    "token": None,
    "expire_time": 0  # 过期时间戳
}

def get_token():
    """获取Token（带缓存机制）"""
    import time
    
    # 检查缓存是否有效（提前5分钟刷新，避免临界点失败）
    if _token_cache["token"] and time.time() < _token_cache["expire_time"] - 300:
        return _token_cache["token"]
    
    # 缓存失效，重新获取
    try:
        client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION_ID)
        request = CommonRequest()
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')
        response = client.do_action_with_exception(request)
        response_json = json.loads(response)
        
        token = response_json.get('Token', {}).get('Id')
        if token:
            # 缓存Token，设置24小时过期（86400秒）
            _token_cache["token"] = token
            _token_cache["expire_time"] = time.time() + 86400
            print("✅ Token已刷新并缓存（有效期24小时）")
        
        return token
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in ['connection', 'timeout', 'refused', 'unreachable', 'network', 'getaddrinfo']):
            print(f"❌ Token 网络错误 (可能断网): {e}")
            return "__NETWORK_ERROR__"
        print(f"❌ Token 错误: {e}")
        return None

# =====================================================
# 识别结果存储
# =====================================================
class RecognitionResult:
    def __init__(self):
        self.text = ""
        self.finished = False
        self.error = None

result_holder = RecognitionResult()

# =====================================================
# 回调函数（精简版）
# =====================================================
def on_start(message, *args):
    pass

def on_sentence_end(message, *args):
    """句子结束 - 提取识别结果"""
    global result_holder
    try:
        msg_dict = json.loads(message) if isinstance(message, str) else message
        result = msg_dict.get('payload', {}).get('result', '')
        if result:
            result_holder.text += result
    except Exception as e:
        # 消息格式错误或网络中断，忽略
        pass

def on_completed(message, *args):
    result_holder.finished = True

def on_error(message, *args):
    result_holder.error = str(message)
    result_holder.finished = True

def on_close(*args):
    pass

# =====================================================
# 核心识别函数（精简版）
# =====================================================
def listen_ali(audio_data):
    global result_holder
    result_holder = RecognitionResult()
    
    # 先快速检查网络连通性（解决Token缓存后NLS静默超时的问题）
    try:
        import socket
        sock = socket.create_connection(("223.5.5.5", 53), timeout=2)  # 阿里DNS
        sock.close()
    except (socket.timeout, OSError, ConnectionError):
        print("⚠️ 网络连接中断，无法进行语音识别")
        return "[NETWORK_ERROR]"
    
    token = get_token()
    if token == "__NETWORK_ERROR__":
        print("❌ 网络连接失败，无法进行语音识别")
        return "[NETWORK_ERROR]"
    if not token:
        return ""
    
    try:
        transcriber = nls.NlsSpeechTranscriber(
            token=token,
            appkey=APPKEY,
            on_start=on_start,
            on_sentence_end=on_sentence_end,
            on_completed=on_completed,
            on_error=on_error,
            on_close=on_close
        )
        
        transcriber.start(
            aformat="pcm",
            sample_rate=16000,
            enable_intermediate_result=False,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True
        )
        
        time.sleep(0.3)
        
        # 发送音频
        chunk_size = 3200
        for i in range(0, len(audio_data), chunk_size):
            transcriber.send_audio(audio_data[i:i + chunk_size])
            time.sleep(0.01)
        
        transcriber.stop()
        
        # 等待结果
        start_time = time.time()
        while not result_holder.finished and (time.time() - start_time) < 10:
            time.sleep(0.1)
        
        if result_holder.text:
            print(f"✅ 识别: {result_holder.text}")
            return result_holder.text.strip()
        else:
            # 检查是否有NLS SDK报告的错误（如断网时连接失败）
            if result_holder.error:
                err = str(result_holder.error).lower()
                print(f"⚠️ NLS错误: {result_holder.error}")
                if any(kw in err for kw in ['connect', 'timeout', 'network', 'refused', 'eof', 'ssl', 'socket', 'name resolution']):
                    return "[NETWORK_ERROR]"
            return ""
        
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in ['connection', 'timeout', 'refused', 'unreachable', 'network']):
            print(f"❌ 识别失败 (网络问题): {e}")
            return "[NETWORK_ERROR]"
        print(f"❌ 识别失败: {e}")
        return ""