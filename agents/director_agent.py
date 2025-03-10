# agents/director_agent.py
from crewai import Agent, LLM
from tools.video_analysis import AnalyzeVideoQualityTool, GetVideoInfoTool
import os


class DirectorAgent:
    @staticmethod
    def create():
        """创建导演 Agent"""
        # 创建工具实例
        video_analysis_tool = AnalyzeVideoQualityTool()
        video_info_tool = GetVideoInfoTool()
        
        # 创建 Agent
        director = Agent(
            role="Film Director",
            goal="Analyze video content and provide high-level creative direction for video editing",
            backstory="""You are an experienced film director with a keen eye for visual aesthetics and storytelling.
            You can quickly identify the type and quality of a video, assess its technical aspects,
            and provide creative direction on how to effectively use the footage.""",
            verbose=True,
            allow_delegation=False,
            tools=[video_analysis_tool, video_info_tool],
            llm=LLM(
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.7,
                custom_llm_provider="openai"
            )
        )
        
        return director