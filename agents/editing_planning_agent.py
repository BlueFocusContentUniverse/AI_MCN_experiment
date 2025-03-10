from crewai import Agent, LLM
from typing import Type, List, Dict, Any, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
from tools.vision_analysis_enhanced import LoadFramesAnalysisFromFileTool


class EditingPlanInput(BaseModel):
    """剪辑规划工具的输入模式"""
    script_segments: List[Dict[str, Any]] = Field(..., description="口播稿分段，每个分段包含文本和时长")
    available_materials: Union[List[Dict[str, Any]], Dict[str, Any]] = Field(..., description="可用的视频素材列表或包含素材的字典")

class EditingPlanTool(BaseTool):
    name: str = "EditingPlan"
    description: str = "规划视频剪辑，为每个口播分段选择合适的视频素材"
    args_schema: Type[BaseModel] = EditingPlanInput
    
    def _run(self, script_segments: List[Dict[str, Any]], available_materials: Union[List[Dict[str, Any]], Dict[str, Any]]) -> dict:
        """
        规划视频剪辑，为每个口播分段选择合适的视频素材
        
        参数:
        script_segments: 口播稿分段，每个分段包含文本和时长
        available_materials: 可用的视频素材列表或包含素材的字典
        
        返回:
        剪辑规划，包括每个分段使用的素材和时间点
        """
        # 提取素材中的视频信息
        video_materials = []
        
        # 处理不同格式的素材数据
        if isinstance(available_materials, list):
            # 如果是列表，直接处理
            for material in available_materials:
                if isinstance(material, dict) and "video_path" in material:
                    video_materials.append({
                        "video_path": material.get("video_path", ""),
                        "frames_analysis_file": material.get("frames_analysis_file", ""),
                        "similarity_score": material.get("similarity_score", 0),
                        "requirement": material.get("requirement", "")
                    })
        elif isinstance(available_materials, dict):
            # 如果是字典，尝试提取视频信息
            if "results" in available_materials:
                for result in available_materials.get("results", []):
                    for video in result.get("matching_videos", []):
                        video_materials.append({
                            "video_path": video.get("video_path", ""),
                            "frames_analysis_file": video.get("frames_analysis_file", ""),
                            "similarity_score": video.get("similarity_score", 0),
                            "requirement": result.get("requirement", {}).get("description", "")
                        })
            elif "matching_videos" in available_materials:
                for video in available_materials.get("matching_videos", []):
                    video_materials.append({
                        "video_path": video.get("video_path", ""),
                        "frames_analysis_file": video.get("frames_analysis_file", ""),
                        "similarity_score": video.get("similarity_score", 0)
                    })
        
        # 如果没有提取到视频素材，打印警告
        if not video_materials:
            print(f"警告: 无法从available_materials提取视频素材。类型: {type(available_materials)}")
            # 如果是简单的视频列表（只包含video_path和frames_analysis_file），直接使用
            if isinstance(available_materials, list) and all(isinstance(item, dict) and "video_path" in item for item in available_materials):
                video_materials = available_materials
        
        # 修改返回格式，确保包含segments键和frames_analysis_file信息
        return {
            "segments": [],  # 初始化空的segments列表，将由Agent填充
            "script_segments": script_segments,
            "available_materials": video_materials,
            "message": """请为每个口播分段选择最合适的视频素材，并规划剪辑点。

步骤：
1. 使用LoadFramesAnalysisFromFile工具加载每个素材的帧分析信息
2. 基于帧分析信息选择最合适的视频片段
3. 为每个音频分段指定一个视频片段，包括:
   - video_path: 视频文件路径
   - start_time: 开始时间（秒）
   - end_time: 结束时间（秒）
   - reason: 选择该片段的理由

请确保你的回答包含一个完整的segments列表，每个segment对应一个音频分段。"""
        }

class EditingPlanningAgent:
    @staticmethod
    def create():
        """创建剪辑规划 Agent"""
        # 创建工具实例
        editing_plan_tool = EditingPlanTool()
        load_analysis_tool = LoadFramesAnalysisFromFileTool()
        
        # 创建 Agent
        editing_planning_agent = Agent(
            role="视频剪辑规划专家",
            goal="规划视频剪辑，为每个口播分段选择合适的视频素材（每段口播需要多段素材(每条素材2-10秒）进行组合剪辑呈现效果，适用于短视频平台的快节奏）",
            backstory="""你是一名资深的视频剪辑师和创意总监，擅长规划视频剪辑流程。
            你熟悉各种剪辑技巧和视觉语言，能够将口播内容与视觉素材完美结合。
            你的工作是为每个口播分段选择最合适的视频素材，并规划精确的剪辑点，
            确保最终的视频在视听上协调一致，能够有效传达信息和情感。
            特别是对于汽车相关视频，你能够选择最能展现车辆特点和魅力的素材，
            并使用专业的剪辑手法增强视觉冲击力。
            画面之间需要在镜头运镜、画面、色彩、节奏、内容上进行衔接，确保视频的连贯性和流畅性。不要给用户带来不好的观感。
            注意根据视频节奏和剪辑需求，**每段口播需要多段素材(每条素材2-10秒）进行组合剪辑呈现效果，适用于短视频平台**""",
            use_system_prompt=False,
            verbose=True,
            allow_delegation=False,
            tools=[editing_plan_tool, load_analysis_tool],
            llm=LLM(
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai",
                timeout=180
            )
        )
        
        return editing_planning_agent 