from crewai import Agent
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from tools.vision_analysis_enhanced import LoadFramesAnalysisFromFileTool

class EditingPlanInput(BaseModel):
    """剪辑规划工具的输入模式"""
    script_segments: List[Dict[str, Any]] = Field(..., description="口播稿分段，每个分段包含文本和时长")
    available_materials: List[Dict[str, Any]] = Field(..., description="可用的视频素材列表")

class EditingPlanTool(BaseTool):
    name: str = "EditingPlan"
    description: str = "规划视频剪辑，为每个口播分段选择合适的视频素材"
    args_schema: Type[BaseModel] = EditingPlanInput
    
    def _run(self, script_segments: List[Dict[str, Any]], available_materials: List[Dict[str, Any]]) -> dict:
        """
        规划视频剪辑，为每个口播分段选择合适的视频素材
        
        参数:
        script_segments: 口播稿分段，每个分段包含文本和时长
        available_materials: 可用的视频素材列表
        
        返回:
        剪辑规划，包括每个分段使用的素材和时间点
        """
        # 这里将使用Agent的LLM能力，所以只需返回输入参数
        return {
            "script_segments": script_segments,
            "available_materials": available_materials,
            "message": "请为每个口播分段选择最合适的视频素材，并规划剪辑点，确保视觉内容与口播内容协调一致"
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
            goal="规划视频剪辑，为每个口播分段选择合适的视频素材",
            backstory="""你是一名资深的视频剪辑师和创意总监，擅长规划视频剪辑流程。
            你熟悉各种剪辑技巧和视觉语言，能够将口播内容与视觉素材完美结合。
            你的工作是为每个口播分段选择最合适的视频素材，并规划精确的剪辑点，
            确保最终的视频在视听上协调一致，能够有效传达信息和情感。
            特别是对于汽车相关视频，你能够选择最能展现车辆特点和魅力的素材，
            并使用专业的剪辑手法增强视觉冲击力。""",
            verbose=True,
            allow_delegation=False,
            tools=[editing_plan_tool, load_analysis_tool],
            llm_config={"model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        )
        
        return editing_planning_agent 