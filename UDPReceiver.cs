using UnityEngine;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using TMPro;

public class UDPReceiver : MonoBehaviour
{
    public int port = 5005;
    public GameObject ballPrefab;
    public AvatarController myWife;

    // 🔥 用来控制头顶的气泡文字
    public TMP_Text bubbleText;

    // 🎭 用来控制身体动画
    public Animator anim;

    private UdpClient client;
    private Thread receiveThread;
    private bool isRunning = true;
    private ConcurrentQueue<string> messageQueue = new ConcurrentQueue<string>();
    private Vector3 currentVelocity = Vector3.zero;
    private float speed = 5.0f;

    void Start()
    {
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        print("Unity 监听启动, 端口: " + port);

        // 初始文字
        if (bubbleText != null) bubbleText.text = "等待指令...";

        // 🎭 获取 Animator (如果没有手动指定，自动从 myWife 获取)
        if (anim == null && myWife != null)
        {
            anim = myWife.GetComponent<Animator>();
        }
        
        if (anim == null)
        {
            Debug.LogWarning("⚠️ 未找到 Animator 组件，动画功能将不可用");
        }
    }

    private void ReceiveData()
    {
        try
        {
            client = new UdpClient(port);
            while (isRunning)
            {
                try
                {
                    IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);
                    byte[] data = client.Receive(ref anyIP);
                    string text = Encoding.UTF8.GetString(data);
                    messageQueue.Enqueue(text);
                }
                catch (System.Exception) { }
            }
        }
        catch (System.Exception) { }
    }

    void Update()
    {
        while (messageQueue.TryDequeue(out string message))
        {
            ProcessMessage(message);
        }

        if (myWife != null)
        {
            myWife.transform.Translate(currentVelocity * speed * Time.deltaTime);
            
            // 移动动画 (使用同一个 Animator)
            if (anim != null)
            {
                bool isWalking = currentVelocity != Vector3.zero;
                anim.SetBool("isMoving", isWalking);
            }
        }
    }

    void ProcessMessage(string message)
    {
        // 🔥 新增：脉冲处理
        if (message == "talk_word")
        {
            if (myWife != null) myWife.PulseMouth();
            return;
        }

        // 🎭 Animator 动画控制
        if (message == "wave")
        {
            if (anim != null) anim.SetTrigger("Trigger_Wave");
            if (bubbleText != null)
            {
                bubbleText.text = "👋 挥手中...";
                StopAllCoroutines();
                StartCoroutine(ClearText());
            }
            return;
        }

        // 原有的 talk_start/talk_end 等逻辑...
        if (message == "talk_start")
        {
            if (myWife != null) myWife.SetTalking(true);
            if (anim != null) anim.SetBool("IsTalking", true);
            return;
        }
        if (message == "talk_end")
        {
            if (myWife != null) myWife.SetTalking(false);
            if (anim != null) anim.SetBool("IsTalking", false);
            return;
        }

        // 🧠 思考动作控制
        if (message == "think_start")
        {
            if (anim != null) anim.SetBool("IsThinking", true);
            if (bubbleText != null)
            {
                bubbleText.text = "🤔 思考中...";
                StopAllCoroutines();
                StartCoroutine(ClearText());
            }
            return;
        }
        if (message == "think_end")
        {
            if (anim != null) anim.SetBool("IsThinking", false);
            return;
        }

        // 🔥 2. 字幕处理 (Python 发来的 say:内容)
        if (message.StartsWith("say:"))
        {
            // ... (这里是你之前写好的字幕代码，保持不变) ...
            if (bubbleText != null)
            {
                bubbleText.text = message.Substring(4);
                StopAllCoroutines();
                StartCoroutine(ClearText());
            }
            return;
        }

        // ... (下面的 Joy/Move 等逻辑保持不变) ...

        // 🔥 3. 其他状态显示 (去掉不兼容的 Emoji)
        if (bubbleText != null)
        {
            if (message == "Joy") bubbleText.text = "(开心)";
            else if (message == "Angry") bubbleText.text = "(生气)";
            else if (message == "Sorrow") bubbleText.text = "(悲伤)";
            else if (message.Contains("move")) bubbleText.text = "移动中...";

            // 刷新消失时间
            StopAllCoroutines();
            StartCoroutine(ClearText());
        }

        // --- 原有的移动和表情逻辑 (保持不变) ---
        if (message == "up" || message == "move_up") currentVelocity = Vector3.up;
        else if (message == "down" || message == "move_down") currentVelocity = Vector3.down;
        else if (message == "left" || message == "move_left") currentVelocity = Vector3.left;
        else if (message == "right" || message == "move_right") currentVelocity = Vector3.right;
        else if (message == "forward" || message == "move_forward") currentVelocity = Vector3.forward;
        else if (message == "back" || message == "move_back") currentVelocity = Vector3.back;
        else if (message == "stop") currentVelocity = Vector3.zero;

        else if (message == "create_ball")
        {
            if (ballPrefab != null)
            {
                for (int i = 0; i < 5; i++)
                {
                    Vector3 spawnPos = transform.position + new Vector3(Random.Range(-2f, 2f), 5, Random.Range(-2f, 2f));
                    Instantiate(ballPrefab, spawnPos, Quaternion.identity);
                }
            }
        }
        // 🔥 表情处理 - 添加调试日志
        else if (message == "Joy" || message == "Angry" || message == "Sorrow" || 
                 message == "Fun" || message == "Surprised" || message == "Neutral")
        {
            Debug.Log($"🎭 [UDPReceiver] 收到表情指令: {message}");
            if (myWife != null)
            {
                myWife.SetExpression(message);
                Debug.Log($"🎭 [UDPReceiver] 已调用 SetExpression({message})");
            }
            else
            {
                Debug.LogWarning("⚠️ myWife 为空，无法设置表情！");
            }
        }
        else if (myWife != null)
        {
            // 其他未知消息也尝试作为表情处理
            Debug.Log($"❓ [UDPReceiver] 收到未知消息: {message}，尝试作为表情处理");
            myWife.SetExpression(message);
        }
    }

    // 🧠 智能清空：根据文字长度动态调整显示时间
    System.Collections.IEnumerator ClearText()
    {
        // 1. 基础停留 1.5 秒 (给人眼反应的时间)
        float duration = 1.5f;

        if (bubbleText != null && bubbleText.text != null)
        {
            // 2. 动态时间：每个字给 0.3 秒
            duration += bubbleText.text.Length * 0.3f;
        }

        // 3. 🔥 强制上限
        // 意思是：不管 AI 说了多长的话，最长只显示 10 秒。
        // (10秒还没读完，说明这废话也没必要读了，不如清空屏幕看老婆)
        duration = Mathf.Min(duration, 10.0f); 

        // 开始倒计时
        yield return new WaitForSeconds(duration);
        
        // 时间到，清空
        if (bubbleText != null) bubbleText.text = "";
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (client != null) client.Close();
        if (receiveThread != null) receiveThread.Abort();
    }
}