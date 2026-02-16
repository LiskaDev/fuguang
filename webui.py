"""
扶光AI助手 - Gradio Web UI
支持浏览器访问，展示对话记录和性能监控
"""
import gradio as gr
import pandas as pd
import os
import sys
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from src.fuguang.core.config import ConfigManager
from src.fuguang.core.mouth import Mouth
from src.fuguang.core.brain import Brain
from src.fuguang.core.eyes import Eyes
from src.fuguang.core.skills.base import SkillManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Fuguang.WebUI")

# 全局变量：扶光系统实例
fuguang_brain = None
fuguang_skills = None
fuguang_eyes = None

def initialize_fuguang():
    """初始化扶光系统（Web模式）"""
    global fuguang_brain, fuguang_skills, fuguang_eyes
    
    try:
        logger.info("🌌 初始化扶光AI助手（Web模式）...")
        
        # 初始化配置
        config = ConfigManager()
        
        # 初始化各个模块
        mouth = Mouth(config)
        fuguang_brain = Brain(config, mouth)
        fuguang_eyes = Eyes(config)
        fuguang_skills = SkillManager(config, mouth, fuguang_brain)
        
        logger.info("✅ 扶光系统初始化完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def chat_interface(message, history):
    """
    Gradio聊天接口
    
    Args:
        message: 用户输入
        history: 对话历史 [[user_msg, bot_msg], ...]
    
    Returns:
        AI回复
    """
    if not fuguang_brain or not fuguang_skills:
        return "❌ 系统未初始化，请重启服务"
    
    try:
        logger.info(f"👤 用户: {message}")
        
        # 收集实时感知数据
        perception_data = fuguang_eyes.get_perception_data()
        
        # 检索长期记忆
        memory_text = ""
        try:
            if hasattr(fuguang_skills, 'memory') and fuguang_skills.memory:
                memory_context = fuguang_skills.memory.get_memory_context(message, n_results=3)
                if memory_context:
                    memory_text = memory_context
                    logger.info(f"📖 [RAG] 已注入长期记忆")
            else:
                related_memories = fuguang_brain.memory_system.search_memory(message)
                if related_memories:
                    memory_text = "\n【相关长期记忆】\n" + "\n".join(related_memories)
                    logger.info(f"🧠 激活记忆: {related_memories}")
        except Exception as e:
            logger.warning(f"⚠️ 记忆检索失败: {e}")
        
        # 生成System Prompt
        system_content = fuguang_brain.get_system_prompt(dynamic_context=perception_data) + memory_text
        
        # 调用AI对话
        response = fuguang_brain.chat(
            user_input=message,
            system_content=system_content,
            tools_schema=fuguang_skills.get_all_tools(),
            tool_executor=fuguang_skills.execute_tool
        )
        
        # 清理回复中的表情标记（Web UI不需要）
        import re
        clean_response = re.sub(r'\[Joy\]|\[Angry\]|\[Sorrow\]|\[Fun\]|\[Surprised\]|\[Neutral\]', '', response)
        clean_response = re.sub(r'\[CMD:.*?\]', '', clean_response).strip()
        
        logger.info(f"🤖 扶光: {clean_response[:50]}...")
        
        return clean_response
        
    except Exception as e:
        logger.error(f"❌ 对话处理失败: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ 处理失败: {str(e)}"


def get_performance_stats():
    """获取性能统计数据"""
    if not fuguang_brain or not fuguang_brain.performance_log:
        return "📊 **性能统计报告**\n\n暂无数据，请先进行对话"
    
    try:
        # 转换为DataFrame
        df = pd.DataFrame(fuguang_brain.performance_log)
        
        # 计算统计
        avg_time = df['time'].mean()
        avg_steps = df['steps'].mean()
        total_tasks = len(df)
        
        # 找出最慢的3个任务
        slowest = df.nlargest(3, 'time')[['task', 'time', 'steps', 'timestamp']]
        
        # 找出最快的3个任务
        fastest = df.nsmallest(3, 'time')[['task', 'time', 'steps', 'timestamp']]
        
        # 生成报告
        report = f"""📊 **性能统计报告**

### 总体数据
- 📈 平均耗时: **{avg_time:.2f}秒**
- 🔧 平均工具调用: **{avg_steps:.1f}个**
- 📝 总任务数: **{total_tasks}**

### 🚀 最快的3个任务
{slowest.to_markdown(index=False) if not slowest.empty else "无数据"}

### 🐢 最慢的3个任务
{fastest.to_markdown(index=False) if not fastest.empty else "无数据"}

### 💡 优化建议
- ✅ 耗时<1秒：优秀（使用了create_file_directly、send_hotkey等极速工具）
- ⚠️ 耗时1-5秒：良好（可以进一步优化）
- ❌ 耗时>10秒：需要优化（检查是否用了慢速GUI操作）

**性能目标:** 90%的任务应在1秒内完成
"""
        
        return report
        
    except Exception as e:
        logger.error(f"❌ 性能统计失败: {e}")
        return f"❌ 统计失败: {str(e)}"


def create_gradio_app():
    """创建Gradio应用"""
    
    # 自定义CSS
    custom_css = """
    .gradio-container {
        font-family: 'Microsoft YaHei', sans-serif;
    }
    .performance-stats {
        font-size: 14px;
        line-height: 1.6;
    }
    """
    
    # 创建多Tab界面
    with gr.Blocks(
        title="扶光AI助手",
        theme=gr.themes.Soft(),
        css=custom_css
    ) as demo:
        
        gr.Markdown("""
        # 🌌 扶光AI助手 Web UI
        
        **智能桌面助手** - 支持文件操作、GUI自动化、网页浏览、性能自优化
        
        > 💡 提示：本系统具有性能自监控和自我学习能力，会自动优化执行效率
        """)
        
        with gr.Tab("💬 聊天对话"):
            chatbot = gr.ChatInterface(
                fn=chat_interface,
                chatbot=gr.Chatbot(
                    height=600,
                    show_label=False,
                    avatar_images=(None, "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f916.png")
                ),
                textbox=gr.Textbox(
                    placeholder="输入你的指令或问题...",
                    container=False,
                    scale=7
                ),
                examples=[
                    "在记事本写123，保存为test.txt",
                    "帮我搜索最新的AI新闻",
                    "打开浏览器访问百度",
                    "创建一个Python文件，内容是Hello World",
                    "设置提醒，明天早上9点开会",
                    "你能做什么？"
                ],
                retry_btn="🔄 重试",
                undo_btn="↶ 撤销",
                clear_btn="🗑️ 清空"
            )
        
        with gr.Tab("📊 性能监控"):
            gr.Markdown("### 实时性能数据")
            
            stats_output = gr.Markdown(
                value="点击「刷新数据」查看性能统计",
                elem_classes=["performance-stats"]
            )
            
            refresh_btn = gr.Button("🔄 刷新数据", variant="primary")
            refresh_btn.click(
                fn=get_performance_stats,
                outputs=stats_output
            )
            
            gr.Markdown("""
            ---
            
            ### 📈 性能监控说明
            
            本系统具有自动性能监控能力：
            
            - **⏱️ 耗时追踪**: 记录每次任务的执行时间
            - **🔧 工具统计**: 追踪工具调用次数和类型
            - **⚠️ 自动警告**: 耗时>10秒时自动触发性能警告
            - **🧠 自我学习**: 将性能教训永久保存到长期记忆
            
            **性能优化示例:**
            - 创建文件: 20秒 → 0.05秒 (提速 **400倍**)
            - 保存文件: 5秒 → 0.1秒 (提速 **50倍**)
            - 输入文本: 5秒 → 0.2秒 (提速 **25倍**)
            """)
        
        with gr.Tab("ℹ️ 关于"):
            gr.Markdown("""
            ## 扶光AI助手系统
            
            ### 🎯 核心功能
            
            - **💬 自然语言交互**: 支持中文对话，理解复杂指令
            - **🤖 桌面自动化**: 文件操作、GUI控制、应用启动
            - **🌐 网页浏览**: 智能搜索、网页内容提取
            - **🧠 长期记忆**: 基于ChromaDB的向量数据库
            - **⚡ 性能自优化**: 自动监控并改进执行效率
            
            ### 🚀 技术特性
            
            - **工具优先级系统**: 5级优先级，自动选择最优方案
            - **性能监控机制**: 耗时>10秒自动触发警告
            - **自我学习循环**: 失败经验自动记录到长期记忆
            - **多模态感知**: 视觉+文本实时感知
            
            ### 📚 技术栈
            
            - **AI模型**: DeepSeek-V3 (Function Calling)
            - **向量数据库**: ChromaDB
            - **自动化**: Pywinauto + RapidOCR + YOLO-World
            - **Web UI**: Gradio
            
            ---
            
            **版本**: v4.5.0  
            **作者**: 阿鑫  
            **项目地址**: [GitHub](https://github.com/LiskaDev/fuguang)
            """)
    
    return demo


def main():
    """主函数"""
    print("=" * 60)
    print("🌌 扶光AI助手 - Gradio Web UI")
    print("=" * 60)
    
    # 初始化系统
    if not initialize_fuguang():
        print("❌ 系统初始化失败，请检查配置")
        return
    
    print("\n✅ 系统启动成功！")
    print("\n📡 Web界面地址:")
    print("   - 本地访问: http://localhost:7860")
    print("   - 局域网访问: http://0.0.0.0:7860")
    print("\n💡 提示: 按 Ctrl+C 停止服务")
    print("=" * 60)
    
    # 创建并启动Gradio应用
    demo = create_gradio_app()
    
    try:
        demo.launch(
            server_name="0.0.0.0",  # 允许局域网访问
            server_port=7860,
            share=False,  # 改成True可生成公网链接（需要gradio账号）
            show_error=True,
            quiet=False
        )
    except KeyboardInterrupt:
        print("\n\n👋 再见！扶光系统已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
