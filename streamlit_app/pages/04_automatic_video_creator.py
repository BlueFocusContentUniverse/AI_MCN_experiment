import os
import sys
import streamlit as st
import json
import datetime
import uuid
import logging
from typing import Dict, Any, List

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 导入相关服务
try:
    from agents.requirement_parsing_agent import RequirementParsingAgent
    from tools.ir_template_tool import IRTemplateTool
    from streamlit_app.services.task_manager import TaskManager
    from streamlit_app.services.mongo_service import TaskManagerService
except ImportError as e:
    st.error(f"导入模块时出错: {str(e)}")
    st.info("请确保已安装所需的依赖并且路径配置正确")

# 页面配置
st.set_page_config(
    page_title="自动视频创作",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 页面样式
st.markdown("""
<style>
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}
.stExpander {
    border: 1px solid #f0f0f0;
    border-radius: 0.5rem;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background-color: #f0f0f0;
    border-radius: 4px 4px 0px 0px;
    padding: 8px 16px;
    height: 40px;
}
.stTabs [aria-selected="true"] {
    background-color: #ffaa00 !important;
    color: white !important;
}
</style>
""", unsafe_allow_html=True)

# 获取可用品牌列表
def get_available_brands() -> List[str]:
    """获取系统中可用的品牌列表"""
    try:
        logger.info("正在获取品牌列表")
        # 从数据库获取品牌列表
        task_manager = TaskManagerService()
        brands = task_manager.get_brands()
        
        if not brands:
            logger.warning("无法从数据库获取品牌列表，使用默认值")
            # 仅当数据库没有返回品牌时使用默认值
            return ["奔驰", "宝马", "奥迪", "保时捷", "特斯拉", "比亚迪", "小鹏", "理想", "蔚来"]
        
        logger.info(f"从数据库成功获取到 {len(brands)} 个品牌")
        return brands
    except Exception as e:
        logger.error(f"获取品牌列表时出错: {str(e)}")
        st.error(f"获取品牌列表时出错: {str(e)}")
        return []

# 获取可用车型列表
def get_available_models() -> List[str]:
    """获取系统中可用的车型列表"""
    try:
        logger.info("正在获取车型列表")
        # 从数据库获取车型列表
        task_manager = TaskManagerService()
        
        # 尝试从videos集合中获取不同的车型
        models = []
        if hasattr(task_manager, 'db'):
            videos_collection = task_manager.db.get_collection("videos")
            if videos_collection is not None:
                # 使用distinct查询不同的车型
                models = videos_collection.distinct("metadata.model")
                # 过滤掉空值和非字符串值
                models = [model for model in models if model and isinstance(model, str)]
                logger.info(f"从videos集合获取到 {len(models)} 个车型")
        
        # 如果数据库中没有找到车型，也尝试从任务配置中获取
        if not models:
            logger.info("从任务配置中查找车型")
            tasks = task_manager.get_tasks(limit=100)
            for task in tasks:
                model = task.get("config", {}).get("model")
                if model and isinstance(model, str) and model not in models:
                    models.append(model)
            logger.info(f"从任务配置中获取到 {len(models)} 个车型")
        
        if not models:
            logger.warning("无法从数据库获取车型列表，使用默认值")
            # 仅当数据库没有返回车型时使用默认值
            return ["S级", "E级", "C级", "X5", "X3", "A6", "A4", "Taycan", "Model S", "Model 3", "汉", "唐", "P7", "L9", "ET7"]
        
        return sorted(models)
    except Exception as e:
        logger.error(f"获取车型列表时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"获取车型列表时出错: {str(e)}")
        return []

# 提交任务
def submit_task(params: Dict[str, Any]) -> str:
    """
    提交视频创建任务
    
    参数:
    params: 任务参数
    
    返回:
    任务ID
    """
    try:
        # 获取任务管理器
        task_manager = TaskManagerService()
        
        # 创建空的视频列表，不再使用占位符
        # 后端系统将负责根据IR要求匹配合适的素材
        videos = []
        
        # 提交任务
        task_id = task_manager.create_task(
            task_name=params.get("user_requirement", "自动视频创作任务")[:50],
            videos=videos,  # 空列表，后端会处理素材匹配
            config=params
        )
        
        # 记录日志
        logger.info(f"成功提交任务: {task_id}, 参数: {params}")
        
        return task_id
    except Exception as e:
        logger.error(f"提交任务时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"提交任务时出错: {str(e)}")
        return ""

# 生成IR预览
def generate_ir_preview(user_requirement: str, brands: List[str], models: List[str], 
                      target_platforms: List[str], target_duration: float, 
                      visual_style: str = None) -> Dict[str, Any]:
    """
    生成IR预览
    
    参数:
    user_requirement: 用户需求
    brands: 品牌列表
    models: 车型列表
    target_platforms: 目标平台
    target_duration: 目标时长
    visual_style: 视觉风格偏好
    
    返回:
    IR预览数据
    """
    try:
        logger.info("开始生成IR预览...")
        # 创建需求解析Agent
        agent = RequirementParsingAgent.create()
        
        # 准备参数，添加视觉风格
        params = {
            "user_requirement": user_requirement,
            "brands": brands,
            "models": models,
            "target_platforms": target_platforms,
            "target_duration": target_duration
        }
        
        if visual_style:
            params["visual_style"] = visual_style
            
        # 创建Task
        from crewai import Task
        
        # 构建丰富的需求解析提示
        requirement_parsing_prompt = f"""
        分析以下用户需求，生成标准化的中间表示(IR)格式：
        
        用户需求: {user_requirement}
        品牌: {', '.join(brands) if brands else '未指定'}
        车型: {', '.join(models) if models else '未指定'}
        目标平台: {', '.join(target_platforms) if target_platforms else '未指定'}
        目标时长: {target_duration} 秒
        {'视觉风格: ' + visual_style if visual_style else ''}
        
        请确保IR结果包含详细的镜头语言规范，包括但不限于：
        1. 拍摄视角 (第一人称/第三人称/俯视/仰视等)
        2. 镜头类型 (特写/中景/远景/全景等)
        3. 镜头运动 (平移/推进/拉远/跟踪等)
        4. 色彩风格和光线特点
        5. 情感表达和节奏控制
        
        为每个视频段落设计最合适的镜头语言，确保它们能够有效地表达品牌特性和产品优势。
        """
        
        parse_task = Task(
            description=requirement_parsing_prompt,
            agent=agent,
            expected_output="完整的标准化IR JSON"
        )
        
        # 执行任务
        from crewai import Crew, Process
        crew = Crew(
            agents=[agent],
            tasks=[parse_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 尝试使用Agent解析需求
        try:
            result = crew.kickoff()
            # 尝试从结果中提取JSON
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', result)
            if json_match:
                json_str = json_match.group(1)
                ir_data = json.loads(json_str)
                logger.info("成功从Agent结果中提取IR数据")
            else:
                # 尝试直接解析
                try:
                    ir_data = json.loads(result)
                    logger.info("直接解析Agent结果为JSON")
                except:
                    # 失败时使用模板
                    logger.warning("无法解析Agent结果，使用模板生成IR")
                    ir_data = IRTemplateTool.generate_template(
                        brands=brands, 
                        models=models, 
                        target_duration=target_duration
                    )
        except Exception as e:
            logger.error(f"Agent解析失败: {str(e)}")
            # 使用模板工具创建示例IR
            ir_data = IRTemplateTool.generate_template(
                brands=brands, 
                models=models, 
                target_duration=target_duration
            )
        
        # 确保IR数据包含镜头语言信息
        if "visual_structure" in ir_data and "segments" in ir_data["visual_structure"]:
            for segment in ir_data["visual_structure"]["segments"]:
                if "visual_requirements" not in segment:
                    segment["visual_requirements"] = {}
                
                # 确保包含镜头语言字段
                if "cinematic_language" not in segment:
                    segment["cinematic_language"] = {}
                    
                # 从segment的其他信息推断镜头语言
                segment_type = segment.get("type", "")
                if "opening" in segment_type and "cinematic_language" not in segment:
                    segment["cinematic_language"] = {
                        "shot_size": "全景",
                        "perspective": "第三人称",
                        "camera_movement": "稳定推进",
                        "color_grading": "鲜明对比",
                        "lighting": "明亮自然"
                    }
                elif "feature" in segment_type and "cinematic_language" not in segment:
                    segment["cinematic_language"] = {
                        "shot_size": "特写",
                        "perspective": "第三人称",
                        "camera_movement": "缓慢平移",
                        "color_grading": "高饱和度",
                        "lighting": "重点照明"
                    }
                elif "driving" in segment_type and "cinematic_language" not in segment:
                    segment["cinematic_language"] = {
                        "shot_size": "中景",
                        "perspective": "驾驶视角",
                        "camera_movement": "跟踪",
                        "color_grading": "对比鲜明",
                        "lighting": "自然光"
                    }
                elif "emotion" in segment_type and "cinematic_language" not in segment:
                    segment["cinematic_language"] = {
                        "shot_size": "特写",
                        "perspective": "第三人称",
                        "camera_movement": "稳定",
                        "color_grading": "柔和暖色",
                        "lighting": "侧光"
                    }
                elif "ending" in segment_type and "cinematic_language" not in segment:
                    segment["cinematic_language"] = {
                        "shot_size": "全景",
                        "perspective": "第三人称",
                        "camera_movement": "拉远",
                        "color_grading": "品牌色调",
                        "lighting": "明亮"
                    }
        
        return ir_data
    except Exception as e:
        logger.error(f"生成IR预览时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"生成IR预览时出错: {str(e)}")
        return {}

# 主页面
def main():
    st.title("🎬 自动视频创作")
    
    # 创建标签页
    tab1, tab2 = st.tabs(["创建新任务", "查看已提交任务"])
    
    # 第一个标签页：创建新任务
    with tab1:
        st.header("创建新的视频任务")
        
        # 自然语言需求输入
        user_requirement = st.text_area(
            "请输入您的视频需求描述",
            height=150,
            help="描述您想要的视频效果，包括内容、风格、时长等",
            placeholder="例如：制作一个奔驰C级的30秒宣传片，强调豪华内饰和驾驶体验，使用专业男声配音，适合在朋友圈分享"
        )
        
        # 品牌和车型选择
        col1, col2 = st.columns(2)
        with col1:
            brands = st.multiselect("品牌", get_available_brands(), help="选择相关的汽车品牌")
        with col2:
            models = st.multiselect("车型", get_available_models(), help="选择相关的汽车型号")
        
        # 高级选项（可折叠）
        with st.expander("高级选项"):
            # 平台选择
            target_platforms = st.multiselect(
                "目标平台",
                ["抖音", "微信", "B站", "YouTube"],
                default=["微信"],
                help="选择视频将发布的平台，会影响视频比例和风格"
            )
            
            # 时长选择
            target_duration = st.slider(
                "目标时长（秒）",
                min_value=10,
                max_value=300,
                value=60,
                step=5,
                help="设置视频的目标时长"
            )
            
            # 视觉风格选择
            col1, col2 = st.columns(2)
            with col1:
                visual_style = st.selectbox(
                    "视觉风格",
                    [
                        "默认",
                        "动感型（动态镜头、快速剪辑）", 
                        "展示型（特写镜头、精细展示）", 
                        "情感型（柔和光线、渐变过渡）", 
                        "科技型（锐利对比、几何构图）",
                        "豪华型（优雅构图、华丽色调）"
                    ],
                    index=0,
                    help="选择视频的整体视觉风格，影响镜头语言和剪辑风格"
                )
                
                # 将"默认"转换为None
                if visual_style == "默认":
                    visual_style = None
                
            with col2:
                # 镜头风格偏好
                shot_preference = st.multiselect(
                    "镜头偏好",
                    ["特写", "中景", "远景", "全景", "跟踪", "环绕", "空中俯瞰", "低角度"],
                    help="选择偏好的镜头类型，系统会尽量匹配包含这些镜头类型的素材"
                )
            
            # 其他选项
            col1, col2 = st.columns(2)
            with col1:
                enable_subtitles = st.checkbox("添加字幕", value=True)
            with col2:
                enable_logo = st.checkbox("添加品牌标志", value=True)
            
            # 任务优先级
            priority = st.radio(
                "任务优先级",
                ["low", "normal", "high"],
                index=1,
                horizontal=True,
                help="设置任务处理的优先级"
            )
        
        # 预览按钮
        if st.button("生成预览", type="secondary"):
            if not user_requirement:
                st.warning("请输入需求描述")
            else:
                with st.spinner("正在生成预览..."):
                    # 生成IR预览
                    ir_preview = generate_ir_preview(
                        user_requirement=user_requirement,
                        brands=brands,
                        models=models,
                        target_platforms=target_platforms,
                        target_duration=target_duration,
                        visual_style=visual_style
                    )
                    
                    # 显示IR预览
                    if ir_preview:
                        st.session_state["ir_preview"] = ir_preview
                        st.success("预览生成成功")
                        
                        # 显示IR摘要
                        with st.expander("需求解析结果", expanded=True):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.subheader("基本信息")
                                st.write(f"项目：{ir_preview['metadata']['title']}")
                                st.write(f"目标时长：{ir_preview['metadata']['target_duration']}秒")
                                st.write(f"目标平台：{', '.join(ir_preview['metadata']['target_platforms'])}")
                                
                                st.subheader("音频设计")
                                if ir_preview['audio_design']['voiceover']['enabled']:
                                    st.write("✅ 口播已启用")
                                    segments = ir_preview['audio_design']['voiceover']['segments']
                                    st.write(f"口播段落数量：{len(segments)}")
                                else:
                                    st.write("❌ 口播未启用")
                                
                                if ir_preview['audio_design']['background_music']['enabled']:
                                    st.write("✅ 背景音乐已启用")
                                else:
                                    st.write("❌ 背景音乐未启用")
                            
                            with col2:
                                st.subheader("视频结构")
                                segments = ir_preview['visual_structure']['segments']
                                st.write(f"片段数量：{len(segments)}")
                                
                                for i, segment in enumerate(segments):
                                    st.markdown(f"**片段 {i+1}**：{segment['type']}")
                                    st.write(f"时长：{segment['duration']}秒")
                                    st.write(f"场景：{segment['visual_requirements']['scene_type']}")
                        
                        # 显示JSON预览
                        with st.expander("查看完整JSON"):
                            st.json(ir_preview)
                    else:
                        st.error("生成预览失败")
        
        # 提交按钮
        if st.button("提交任务", type="primary"):
            if not user_requirement:
                st.warning("请输入需求描述")
            else:
                with st.spinner("正在提交任务..."):
                    # 收集参数
                    params = {
                        "user_requirement": user_requirement,
                        "brands": brands,
                        "models": models,
                        "target_platforms": target_platforms,
                        "target_duration": target_duration,
                        "enable_subtitles": enable_subtitles,
                        "enable_logo": enable_logo,
                        "priority": priority,
                        "submitted_at": datetime.datetime.now().isoformat()
                    }
                    
                    # 添加视觉风格和镜头偏好
                    if visual_style:
                        params["visual_style"] = visual_style
                    
                    if shot_preference:
                        params["shot_preference"] = shot_preference
                    
                    # 如果已有IR预览，添加到参数
                    if "ir_preview" in st.session_state:
                        params["ir_preview"] = st.session_state["ir_preview"]
                    
                    # 提交任务
                    task_id = submit_task(params)
                    
                    if task_id:
                        st.success(f"任务已提交，任务ID: {task_id}")
                        st.info("您可以在'查看已提交任务'标签页查看任务进度")
                    else:
                        st.error("任务提交失败")
    
    # 第二个标签页：查看已提交任务
    with tab2:
        st.header("已提交的任务")
        
        # 刷新按钮
        if st.button("刷新任务列表"):
            st.experimental_rerun()
        
        # 显示任务列表
        try:
            task_manager = TaskManagerService()
            tasks = task_manager.get_tasks(limit=20)  # 获取更多任务
            
            if not tasks:
                st.info("暂无任务")
            else:
                # 准备表格数据
                table_data = []
                for task in tasks:
                    # 检查是否为自动视频创作任务（通过配置判断）
                    if task.get("config", {}).get("user_requirement"):
                        table_data.append({
                            "任务ID": task["_id"],
                            "任务名称": task.get("task_name", "未命名任务"),
                            "提交时间": task.get("created_at", ""),
                            "状态": task.get("status", "未知"),
                            "进度": f"{task.get('progress', 0)}%",
                            "品牌": ", ".join(task.get("config", {}).get("brands", [])),
                            "视频数量": str(len(task.get("videos", [])))
                        })
                
                # 显示表格
                if table_data:
                    selected_task = st.selectbox(
                        "选择一个任务查看详情",
                        options=[task["任务ID"] for task in table_data],
                        format_func=lambda x: f"{next((task['任务名称'] for task in table_data if task['任务ID'] == x), '')} ({next((task['提交时间'] for task in table_data if task['任务ID'] == x), '')})"
                    )
                    
                    if selected_task:
                        # 获取选中的任务
                        task_info = task_manager.get_task(selected_task)
                        
                        if task_info:
                            # 显示任务详情
                            st.subheader("任务详情")
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write("**状态**", task_info.get("status", "未知"))
                            with col2:
                                st.write("**进度**", f"{task_info.get('progress', 0)}%")
                            with col3:
                                st.write("**提交时间**", task_info.get("created_at", ""))
                            
                            # 显示需求
                            st.subheader("需求描述")
                            st.write(task_info.get("config", {}).get("user_requirement", ""))
                            
                            # 显示参数
                            with st.expander("任务参数"):
                                config = task_info.get("config", {})
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write("**品牌**", ", ".join(config.get("brands", [])))
                                    st.write("**车型**", ", ".join(config.get("models", [])))
                                with col2:
                                    st.write("**目标平台**", ", ".join(config.get("target_platforms", [])))
                                    st.write("**目标时长**", f"{config.get('target_duration', 60)}秒")
                            
                            # 视频列表
                            videos = task_info.get("videos", [])
                            if videos:
                                st.subheader("视频列表")
                                for i, video in enumerate(videos):
                                    st.write(f"**视频 {i+1}**: {video.get('file_name', '未命名')} - {video.get('status', '未知')}")
                                    if video.get("video_id"):
                                        st.write(f"视频ID: {video.get('video_id')}")
                                    if video.get("error"):
                                        st.error(f"错误: {video.get('error')}")
                            
                            # 任务操作按钮
                            col1, col2 = st.columns(2)
                            with col1:
                                if task_info.get("status") in ["pending", "processing"]:
                                    if st.button("取消任务", key=f"cancel_{selected_task}"):
                                        task_manager.update_task_status(selected_task, "canceled")
                                        st.success("任务已取消")
                                        st.experimental_rerun()
                            
                            with col2:
                                if st.button("删除任务", key=f"delete_{selected_task}"):
                                    task_manager.delete_task(selected_task)
                                    st.success("任务已删除")
                                    st.experimental_rerun()
                else:
                    st.info("暂无自动视频创作任务")
                    
        except Exception as e:
            logger.error(f"获取任务列表时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            st.error(f"获取任务列表时出错: {str(e)}")

# 运行主函数
if __name__ == "__main__":
    main() 