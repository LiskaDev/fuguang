using UnityEngine;
using VRM; // 🔥 必须引用 VRM 命名空间
using System.Collections;

public class AvatarController : MonoBehaviour
{
    private VRMBlendShapeProxy proxy;
    private Animator animator; // 🆕 引用Animator

    [Header("口型参数")]
    [Range(1, 100)] public float talkSpeed = 25f;
    [Range(0.1f, 1f)] public float mouthOpenStrength = 0.6f;

    [Header("Animator嘴型参数")]
    [Range(5f, 50f)] public float animatorTalkSpeed = 15f;
    [Range(0.1f, 0.8f)] public float animatorMouthOpen = 0.4f;

    [Header("表情过渡参数")]
    [Range(0.05f, 1f)] public float expressionTransitionTime = 0.2f;  // 🆕 表情过渡时间

    private bool isTalking = false;
    private float targetPulse = 0f;

    // 🆕 当前表情状态
    private BlendShapePreset currentExpression = BlendShapePreset.Neutral;
    private Coroutine expressionCoroutine = null;

    void Start()
    {
        proxy = GetComponent<VRMBlendShapeProxy>();
        animator = GetComponent<Animator>();
        
        if (proxy == null)
        {
            Debug.LogError("❌ 找不到 VRMBlendShapeProxy！请确保脚本挂在 VRM 模型根部！");
        }
        
        if (animator == null)
        {
            Debug.LogWarning("⚠️ 未找到 Animator 组件！Animator驱动的嘴型将不可用。");
        }
    }

    void Update()
    {
        if (proxy == null) return;

        // 🆕 从 Animator 读取 IsTalking 状态
        bool isAnimatorTalking = false;
        if (animator != null)
        {
            isAnimatorTalking = animator.GetBool("IsTalking");
        }

        bool shouldTalk = isTalking || isAnimatorTalking;

        if (shouldTalk)
        {
            // 1. 🆕 Animator驱动的正弦波基础律动
            float sineWave = 0f;
            if (isAnimatorTalking)
            {
                sineWave = (Mathf.Sin(Time.time * animatorTalkSpeed) + 1f) * 0.5f * animatorMouthOpen;
            }
            
            // 2. UDP脉冲
            float udpNoise = 0f;
            if (isTalking)
            {
                udpNoise = Mathf.PerlinNoise(Time.time * talkSpeed, 0) * (mouthOpenStrength * 0.3f);
            }
            
            // 3. 脉冲衰减
            targetPulse = Mathf.Lerp(targetPulse, 0, Time.deltaTime * 15f);

            // 4. 混合三种嘴型
            float finalOpen = Mathf.Max(sineWave, udpNoise, targetPulse);
            finalOpen = Mathf.Clamp(finalOpen, 0f, 1f);

            // 5. 应用给 VRM 的 "A" (张嘴) 通道
            proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.A), finalOpen);
        }
        else
        {
            // 缓慢闭嘴
            float currentVal = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.A));
            float closeVal = Mathf.Lerp(currentVal, 0, Time.deltaTime * 10f);
            proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.A), closeVal);
        }
    }

    // --- 供 UDPReceiver 调用 ---

    public void SetTalking(bool talking)
    {
        isTalking = talking;
        if (!talking)
        {
            targetPulse = 0;
        }
    }

    public void PulseMouth()
    {
        if (isTalking)
        {
            targetPulse = mouthOpenStrength;
        }
    }

    // ... 省略前面代码

    private void ResetFacialExpressions()
    {
        if (proxy == null) return;

        // 立即重置所有表情
        proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Joy), 0);
        proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Angry), 0);
        proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Sorrow), 0);
        proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Fun), 0);
        // proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Surprised), 0); // 移除或注释掉此行
    }

    /// <summary>
    /// 设置表情（带平滑过渡）
    /// </summary>
    public void SetExpression(string expressionName)
    {
        Debug.Log($"🎭 [AvatarController] SetExpression 被调用: {expressionName}, 当前表情: {currentExpression}");
        
        if (proxy == null)
        {
            Debug.LogWarning("⚠️ proxy 为空，无法设置表情！");
            return;
        }

        BlendShapePreset targetPreset = BlendShapePreset.Neutral;
        
        switch (expressionName)
        {
            case "Joy": targetPreset = BlendShapePreset.Joy; break;
            case "Angry": targetPreset = BlendShapePreset.Angry; break;
            case "Sorrow": targetPreset = BlendShapePreset.Sorrow; break;
            case "Fun": targetPreset = BlendShapePreset.Fun; break;
            case "Surprised": targetPreset = BlendShapePreset.Fun; break;
            case "Neutral": targetPreset = BlendShapePreset.Neutral; break;
            default: 
                Debug.LogWarning("未知表情: " + expressionName); 
                return;
        }

        // 如果已经是当前表情，跳过
        if (targetPreset == currentExpression)
        {
            Debug.Log($"🎭 [AvatarController] 表情相同，跳过: {targetPreset}");
            return;
        }

        Debug.Log($"🎭 [AvatarController] 开始过渡到表情: {targetPreset}");

        // 停止之前的过渡协程
        if (expressionCoroutine != null)
        {
            StopCoroutine(expressionCoroutine);
        }

        // 启动新的过渡协程
        expressionCoroutine = StartCoroutine(TransitionToExpression(targetPreset));
    }

    // ... 省略中间代码

    private IEnumerator TransitionToExpression(BlendShapePreset targetPreset)
    {
        float elapsed = 0f;

        // 记录起始状态（当前所有表情的权重）
        float startJoy = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Joy));
        float startAngry = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Angry));
        float startSorrow = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Sorrow));
        float startFun = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Fun));
        // float startSurprised = proxy.GetValue(BlendShapeKey.CreateFromPreset(BlendShapePreset.Surprised)); // 移除或注释掉此行

        // 目标状态（只有目标表情为1，其他为0）
        float targetValue = (targetPreset == BlendShapePreset.Neutral) ? 0f : 1f;

        while (elapsed < expressionTransitionTime)
        {
            elapsed += Time.deltaTime;
            float t = elapsed / expressionTransitionTime;

            // 平滑插值（使用 SmoothStep 让过渡更自然）
            float smoothT = Mathf.SmoothStep(0, 1, t);

            // 所有表情逐渐归零
            proxy.ImmediatelySetValue(
                BlendShapeKey.CreateFromPreset(BlendShapePreset.Joy),
                Mathf.Lerp(startJoy, targetPreset == BlendShapePreset.Joy ? targetValue : 0, smoothT)
            );
            proxy.ImmediatelySetValue(
                BlendShapeKey.CreateFromPreset(BlendShapePreset.Angry),
                Mathf.Lerp(startAngry, targetPreset == BlendShapePreset.Angry ? targetValue : 0, smoothT)
            );
            proxy.ImmediatelySetValue(
                BlendShapeKey.CreateFromPreset(BlendShapePreset.Sorrow),
                Mathf.Lerp(startSorrow, targetPreset == BlendShapePreset.Sorrow ? targetValue : 0, smoothT)
            );
            proxy.ImmediatelySetValue(
                BlendShapeKey.CreateFromPreset(BlendShapePreset.Fun),
                Mathf.Lerp(startFun, targetPreset == BlendShapePreset.Fun ? targetValue : 0, smoothT)
            );

            // Surprised 和 Fun 共用同一个 BlendShape（根据你的原代码）
            // 如果你的模型有独立的 Surprised，取消注释下面这行：
            // proxy.ImmediatelySetValue(
            //     BlendShapeKey.CreateFromPreset(BlendShapePreset.Surprised), 
            //     Mathf.Lerp(startSurprised, targetPreset == BlendShapePreset.Surprised ? targetValue : 0, smoothT)
            // );

            yield return null;
        }

        // 确保最终值精确
        ResetFacialExpressions();
        if (targetPreset != BlendShapePreset.Neutral)
        {
            proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(targetPreset), 1.0f);
        }

        currentExpression = targetPreset;
        expressionCoroutine = null;
    }

    /// <summary>
    /// 🆕 立即设置表情（无过渡，用于紧急情况）
    /// </summary>
    public void SetExpressionImmediate(string expressionName)
    {
        if (proxy == null) return;

        // 停止过渡协程
        if (expressionCoroutine != null)
        {
            StopCoroutine(expressionCoroutine);
            expressionCoroutine = null;
        }

        ResetFacialExpressions();

        BlendShapePreset preset = BlendShapePreset.Neutral;
        
        switch (expressionName)
        {
            case "Joy": preset = BlendShapePreset.Joy; break;
            case "Angry": preset = BlendShapePreset.Angry; break;
            case "Sorrow": preset = BlendShapePreset.Sorrow; break;
            case "Fun": preset = BlendShapePreset.Fun; break;
            case "Surprised": preset = BlendShapePreset.Fun; break;
            case "Neutral": preset = BlendShapePreset.Neutral; break;
            default: Debug.LogWarning("未知表情: " + expressionName); return;
        }

        if (preset != BlendShapePreset.Neutral)
        {
            proxy.ImmediatelySetValue(BlendShapeKey.CreateFromPreset(preset), 1.0f);
        }

        currentExpression = preset;
    }
}