from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os


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
            你的工作是为视频制作团队提供明确的创意指导，确保最终的视频能够准确传达口播稿的信息和情感。
            1. 根据口播稿内容判断这是一篇讲什么汽车/主题的稿件
            2. 根据该车型及稿件内容生成高度定制和契合的视频需求清单，是得后续在向量知识库匹配时能更好匹配到合适的视频素材
            3. 向量知识库中有不同品牌的车型，你需要下达品牌清晰的视频清单指令,如本田ZRV，小米SU7，特斯拉Model3等""",
            verbose=True,
            allow_delegation=False,
            tools=[script_analysis_tool],
            llm=LLM(
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",  # Claude模型名称
                api_key=os.environ.get('OPENAI_API_KEY'),  # 代理API Key
                base_url=os.environ.get('OPENAI_BASE_URL'),  # 代理Base URL
                temperature=0.1,
                custom_llm_provider="openai" # 强制使用OpenAI API
            ),
            response_template="""
                请严格遵循以下格式输出json：
                {{ .Response }}
                {
                    "requirements": [
                        {
                            "segment": "口播稿的第1段文字",
                            "duration": "时长",
                            "visual_elements": ["场景类型", "情绪基调"],
                            "description": "描述"
                        }
                    ]
                }   
                """
        )
        
        return script_analysis_agent 