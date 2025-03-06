from crewai import Agent
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class ScriptInput(BaseModel):
    """脚本分析工具的输入模式"""
    script: str = Field(..., description="口播稿文本")
    target_duration: float = Field(60.0, description="目标视频时长（秒）")
    style: str = Field("汽车广告", description="视频风格")

class ScriptAnalysisTool(BaseTool):
    name: str = "ScriptAnalysis"
    description: str = "分析口播稿，生成视频需求清单"
    args_schema: Type[BaseModel] = ScriptInput
    
    def _run(self, script: str, target_duration: float = 60.0, style: str = "汽车广告") -> dict:
        """
        分析口播稿，生成视频需求清单
        
        参数:
        script: 口播稿文本
        target_duration: 目标视频时长（秒）
        style: 视频风格
        
        返回:
        视频需求清单
        """
        # 这里将使用Agent的LLM能力，所以只需返回输入参数
        return {
            "script": script,
            "target_duration": target_duration,
            "style": style,
            "message": "请分析这个口播稿，生成视频需求清单，包括每个段落需要的视觉元素、场景类型、情绪基调等"
        }

class ScriptAnalysisAgent:
    @staticmethod
    def create():
        """创建脚本分析 Agent"""
        # 创建工具实例
        script_analysis_tool = ScriptAnalysisTool()
        
        # 创建 Agent
        script_analysis_agent = Agent(
            role="视频脚本专家",
            goal="分析口播稿，生成视频需求清单",
            backstory="""你是一名资深的视频脚本专家和创意总监，擅长将文字转化为视觉语言。
            你熟悉各种视频类型的创作规律，特别是汽车广告和宣传片的制作要求。
            你能够分析口播稿的结构和内容，提取关键信息，并将其转化为具体的视频需求清单。
            你的工作是为视频制作团队提供明确的创意指导，确保最终的视频能够准确传达口播稿的信息和情感。""",
            verbose=True,
            allow_delegation=False,
            tools=[script_analysis_tool],
            llm_config={"model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        )
        
        return script_analysis_agent 