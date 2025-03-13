import streamlit as st
import os
import sys
import json
import tempfile
import io
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from contextlib import redirect_stdout, redirect_stderr

# 导入服务
from services.video_info_extractor import VideoInfoExtractor
from services.video_production_service import VideoProductionService
from agents.script_analysis_agent import ScriptAnalysisAgent
from agents.material_search_agent import MaterialSearchAgent
from agents.editing_planning_agent import EditingPlanningAgent
from agents.vision_agent import VisionAgent
from agents.cinematography_agent import CinematographyAgent
from crewai import Crew, Task, Process

# 设置页面配置
st.set_page_config(
    page_title="智能视频处理系统",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 创建临时目录
@st.cache_resource
def get_temp_dir():
    temp_dir = tempfile.mkdtemp()
    return temp_dir

# 加载示例脚本
@st.cache_data
def load_example_script():
    example_script_path = "./debug_script.txt"
    try:
        with open(example_script_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        example_script = """很多人以为自动驾驶就是简单的识别前方道路,但理想汽车的双系统架构,已经做到了像人脑一样思考。
就像我们开车时,大脑会同时处理"看到了什么"和"该怎么做"。理想汽车的端到端系统负责即时反应,VLM 视觉语言模型则像人类大脑一样进行深度思考。
举个例子,当遇到施工路段时,端到端系统能快速识别出路障,而 VLM 系统则会像人类一样分析:"这是临时施工,需要减速并保持安全距离,观察施工人员指挥"。
这就是为什么理想汽车能在复杂路况下做出更智能的决策,因为它不仅能看,还能思考。就像一个经验丰富的老司机,走过的路多了,碰到任何情况都能从容应对。
我觉得这套双系统的设计,让自动驾驶离真正的"智能"更进一步。对于未来的出行方式,你们觉得 AI 能完全取代人类驾驶吗?欢迎在评论区留下你的想法。"""
        os.makedirs(os.path.dirname(example_script_path) or '.', exist_ok=True)
        with open(example_script_path, 'w', encoding='utf-8') as f:
            f.write(example_script)
        return example_script

# 初始化会话状态
if 'task_type' not in st.session_state:
    st.session_state.task_type = None
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'result' not in st.session_state:
    st.session_state.result = None
if 'error' not in st.session_state:
    st.session_state.error = None

# 页面标题
st.title("🎬 智能视频处理系统")
st.markdown("---")

# 任务选择
task_options = ["选择任务类型", "视频生产", "视频解析"]
selected_task = st.selectbox("请选择要执行的任务:", task_options)

if selected_task != "选择任务类型":
    st.session_state.task_type = selected_task

# 根据任务类型显示不同的输入界面
if st.session_state.task_type == "视频生产":
    st.subheader("📝 视频生产")
    
    # 加载示例脚本
    example_script = load_example_script()
    
    # 文本输入区域
    script = st.text_area("请输入口播稿:", value=example_script, height=200)
    
    # 输出目录
    output_dir = get_temp_dir()
    
    # 创建占位符用于实时更新
    progress_placeholder = st.empty()
    output_placeholder = st.empty()
    
    # 执行按钮
    if st.button("开始生产视频", type="primary", disabled=st.session_state.processing):
        if not script.strip():
            st.error("请输入口播稿内容")
        else:
            # 重置状态
            st.session_state.processing = True
            st.session_state.result = None
            st.session_state.error = None
            
            try:
                # 显示进度条
                progress_bar = progress_placeholder.progress(0)
                
                # 1. 脚本分析阶段
                script_analysis_agent = ScriptAnalysisAgent.create()
                analyze_script_task = Task(
                    description=f"分析口播稿，生成视频需求清单：\n\n{script}\n\n目标视频时长：60秒\n视频风格：汽车广告",
                    agent=script_analysis_agent,
                    expected_output="详细的视频需求清单，包括每个段落需要的视觉元素、场景类型、情绪基调等"
                )
                
                script_analysis_crew = Crew(
                    agents=[script_analysis_agent],
                    tasks=[analyze_script_task],
                    verbose=True,
                    process=Process.sequential
                )
                
                # 执行分析并直接显示结果
                result_analysis = script_analysis_crew.kickoff()
                
                # 显示 Agent 名字和思考过程
                output_placeholder.markdown(f"""
                ### 🤖 Agent 名字：{script_analysis_agent.role}
                **思考过程：**  
                {result_analysis}
                """)
                
                # 更新进度
                progress_bar.progress(25)
                
                # 提取 requirements
                try:
                    requirements_data = json.loads(result_analysis.raw)
                except:
                    requirements_data = {"requirements": []}
                
                # 2. 素材搜索阶段
                material_search_agent = MaterialSearchAgent.create()
                search_materials_task = Task(
                    description=f"根据视频需求搜索匹配的素材：\n\n{json.dumps(requirements_data, ensure_ascii=False)}",
                    agent=material_search_agent,
                    expected_output="匹配的视频素材列表"
                )
                
                material_search_crew = Crew(
                    agents=[material_search_agent],
                    tasks=[search_materials_task],
                    verbose=True,
                    process=Process.sequential
                )
                
                # 执行搜索并直接显示结果
                result_materials = material_search_crew.kickoff()
                
                # 显示 Agent 名字和思考过程
                output_placeholder.markdown(f"""
                ### 🤖 Agent 名字：{material_search_agent.role}
                **思考过程：**  
                {result_materials}
                """)
                
                # 更新进度
                progress_bar.progress(50)
                
                # 提取 materials
                try:
                    materials_data = json.loads(result_materials.raw)
                except:
                    materials_data = {"results": []}
                
                # 3. 音频生成
                producer = VideoProductionService(output_dir=output_dir)
                audio_segments = producer._generate_audio_segments(script)
                
                # 4. 编辑规划阶段
                editing_planning_agent = EditingPlanningAgent.create()
                plan_editing_task = Task(
                    description=f"规划视频剪辑：\n\n音频分段信息：{json.dumps(audio_segments, ensure_ascii=False)}\n\n可用素材：{json.dumps(materials_data, ensure_ascii=False)}",
                    agent=editing_planning_agent,
                    expected_output="详细的剪辑规划，包括每个分段使用的素材和时间点"
                )
                
                editing_planning_crew = Crew(
                    agents=[editing_planning_agent],
                    tasks=[plan_editing_task],
                    verbose=True,
                    process=Process.sequential
                )
                
                # 执行规划并直接显示结果
                result_editing = editing_planning_crew.kickoff()
                
                # 显示 Agent 名字和思考过程
                output_placeholder.markdown(f"""
                ### 🤖 Agent 名字：{editing_planning_agent.role}
                **思考过程：**  
                {result_editing}
                """)
                
                # 更新进度
                progress_bar.progress(75)
                
                # 提取编辑计划
                try:
                    editing_plan_data = json.loads(result_editing.raw)
                except:
                    editing_plan_data = {"segments": []}
                
                # 5. 执行剪辑
                complete_plan = {
                    "segments": editing_plan_data.get("segments", []),
                    "audio_segments": audio_segments
                }
                
                # 执行剪辑
                timestamp = int(time.time())
                project_name = f"video_{timestamp}"
                final_video = producer._execute_editing(complete_plan, project_name)
                
                # 构建结果
                result = {
                    "project_name": project_name,
                    "script": script,
                    "audio_info": {
                        "segments": audio_segments
                    },
                    "requirements": {
                        "data": requirements_data
                    },
                    "materials": {
                        "data": materials_data
                    },
                    "editing_plan": {
                        "data": editing_plan_data
                    },
                    "final_video": final_video
                }
                
                st.session_state.result = result
                
                # 更新进度
                progress_bar.progress(100)
                
            except Exception as e:
                st.session_state.error = str(e)
                st.error(f"处理出错: {str(e)}")
            
            finally:
                st.session_state.processing = False
                st.rerun()

elif st.session_state.task_type == "视频解析":
    st.subheader("🔍 视频解析")
    
    # 文件上传
    uploaded_file = st.file_uploader("请上传视频文件:", type=["mp4", "avi", "mov", "mkv"])
    
    # 输出目录
    output_dir = get_temp_dir()
    
    # 创建占位符用于实时更新
    progress_placeholder = st.empty()
    output_placeholder = st.empty()
    
    # 执行按钮
    if st.button("开始解析视频", type="primary", disabled=st.session_state.processing):
        if uploaded_file is None:
            st.error("请上传视频文件")
        else:
            # 重置状态
            st.session_state.processing = True
            st.session_state.result = None
            st.session_state.error = None
            
            try:
                # 显示进度条
                progress_bar = progress_placeholder.progress(0)
                
                # 保存上传的文件
                temp_video_path = os.path.join(output_dir, uploaded_file.name)
                with open(temp_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # 1. 视觉分析阶段
                vision_agent = VisionAgent.create()
                analyze_frames_task = Task(
                    description=f"从视频 {temp_video_path} 中提取关键帧，并分析视觉内容",
                    agent=vision_agent,
                    expected_output="包含分析摘要和结果文件路径的JSON对象"
                )
                
                vision_crew = Crew(
                    agents=[vision_agent],
                    tasks=[analyze_frames_task],
                    verbose=True,
                    process=Process.sequential
                )
                
                # 执行视觉分析并直接显示结果
                result_vision = vision_crew.kickoff(inputs={"video_path": temp_video_path})
                
                # 显示 Agent 名字和思考过程
                output_placeholder.markdown(f"""
                ### 🤖 Agent 名字：{vision_agent.role}
                **思考过程：**  
                {result_vision}
                """)
                
                # 更新进度
                progress_bar.progress(50)
                
                # 2. 电影摄影分析阶段
                cinematography_agent = CinematographyAgent.create()
                frames_analysis_file = result_vision.json_dict.get("frames_analysis_file", "")
                
                cinematography_task = Task(
                    description=f"分析视频 {temp_video_path} 的运镜、色调、节奏等动态特征",
                    agent=cinematography_agent,
                    expected_output="包含运镜、色调、节奏等动态特征分析的JSON对象"
                )
                
                cinematography_crew = Crew(
                    agents=[cinematography_agent],
                    tasks=[cinematography_task],
                    verbose=True,
                    process=Process.sequential
                )
                
                # 执行动态分析并直接显示结果
                result_cinematography = cinematography_crew.kickoff(
                    inputs={"frames_analysis_file": frames_analysis_file}
                )
                
                # 显示 Agent 名字和思考过程
                output_placeholder.markdown(f"""
                ### 🤖 Agent 名字：{cinematography_agent.role}
                **思考过程：**  
                {result_cinematography}
                """)
                
                # 更新进度
                progress_bar.progress(100)
                
                # 创建解析器
                extractor = VideoInfoExtractor(output_dir=output_dir, skip_mongodb=False)
                
                # 整合信息
                result = extractor._integrate_information(
                    video_path=temp_video_path,
                    transcription={"text": ""},  # 简化处理
                    vision_result=result_vision,
                    cinematography_result=result_cinematography,
                    frames_analysis_file=frames_analysis_file
                )
                
                st.session_state.result = result
                
            except Exception as e:
                st.session_state.error = str(e)
                st.error(f"处理出错: {str(e)}")
            
            finally:
                st.session_state.processing = False
                st.rerun()

# 显示结果
if st.session_state.result is not None:
    st.markdown("---")
    st.subheader("📊 处理结果")
    
    if st.session_state.task_type == "视频生产":
        # 显示视频生产结果
        result = st.session_state.result
        
        # 显示最终视频
        if "final_video" in result and os.path.exists(result["final_video"]):
            st.success(f"视频生产成功: {result['final_video']}")
            st.video(result["final_video"])
        else:
            st.warning("未找到生成的视频文件")
        
        # 显示详细信息
        with st.expander("详细信息", expanded=False):
            # 项目信息
            st.markdown("### 项目信息")
            st.text(f"项目名称: {result.get('project_name', '未知')}")
            st.text(f"目标时长: 60 秒")
            st.text(f"视频风格: 汽车广告")
            
            # 音频信息
            if "audio_info" in result and "segments" in result["audio_info"]:
                st.markdown("### 音频分段")
                for i, segment in enumerate(result["audio_info"]["segments"]):
                    st.markdown(f"**分段 {i+1}**")
                    st.text(f"文本: {segment.get('text', '未知')}")
                    st.text(f"时长: {segment.get('duration', '未知')} 秒")
                    if "audio_file" in segment and os.path.exists(segment["audio_file"]):
                        st.audio(segment["audio_file"])
            
            # 编辑计划
            if "editing_plan" in result and "data" in result["editing_plan"] and "segments" in result["editing_plan"]["data"]:
                st.markdown("### 编辑计划")
                for i, segment in enumerate(result["editing_plan"]["data"]["segments"]):
                    st.markdown(f"**片段 {i+1}**")
                    st.text(f"分段ID: {segment.get('segment_id', '未知')}")
                    st.text(f"视频路径: {segment.get('video_path', '未知')}")
                    st.text(f"开始时间: {segment.get('start_time', '未知')} 秒")
                    st.text(f"结束时间: {segment.get('end_time', '未知')} 秒")
                    st.text(f"选择原因: {segment.get('reason', '未知')}")
    
    elif st.session_state.task_type == "视频解析":
        # 显示视频解析结果
        result = st.session_state.result
        
        # 显示基本信息
        st.markdown("### 基本信息")
        st.text(f"视频路径: {result.get('video_path', '未知')}")
        st.text(f"分析时间: {result.get('analysis_time', '未知')}")
        
        # 显示转录信息
        if "transcription" in result and "text" in result["transcription"]:
            with st.expander("语音转录", expanded=False):
                st.markdown("### 语音转录")
                st.text(result["transcription"]["text"])
                
                # 显示分段信息
                if "segments" in result["transcription"]:
                    st.markdown("#### 分段信息")
                    for i, segment in enumerate(result["transcription"]["segments"]):
                        st.text(f"[{segment.get('start', '?')} - {segment.get('end', '?')}] {segment.get('text', '')}")
        
        # 显示视觉分析
        if "vision_analysis" in result:
            with st.expander("视觉分析", expanded=False):
                st.markdown("### 视觉分析")
                
                # 显示帧分析文件路径
                if "frames_analysis_file" in result:
                    st.text(f"帧分析文件: {result['frames_analysis_file']}")
                
                # 显示视觉分析摘要
                vision_analysis = result["vision_analysis"]
                if isinstance(vision_analysis, dict):
                    for key, value in vision_analysis.items():
                        if key != "frames_results" and key != "raw_output":  # 排除大型数据
                            st.markdown(f"#### {key}")
                            st.write(value)
        
        # 显示电影摄影分析
        if "cinematography_analysis" in result:
            with st.expander("电影摄影分析", expanded=False):
                st.markdown("### 电影摄影分析")
                
                cinematography_analysis = result["cinematography_analysis"]
                if isinstance(cinematography_analysis, dict):
                    for key, value in cinematography_analysis.items():
                        if key != "raw_output" and key != "raw_json":  # 排除大型数据
                            st.markdown(f"#### {key}")
                            st.write(value)

# 显示错误信息
if st.session_state.error is not None:
    st.error(f"处理过程中出错: {st.session_state.error}")

# 页脚
st.markdown("---") 