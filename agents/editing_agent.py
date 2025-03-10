from crewai import Agent, LLM
from tools.video_editing import SplitVideoBySegmentsTool
import os


class EditingAgent:
    @staticmethod
    def create():
        """创建视频编辑 Agent"""
        # 创建工具实例
        split_video_tool = SplitVideoBySegmentsTool()
        
        # 创建 Agent
        editing_agent = Agent(
            role="视频编辑专家",
            goal="根据分析结果切割视频，生成高质量的视频片段",
            backstory="""你是一名专业的视频编辑师，擅长视频剪辑和后期处理。
            你能够根据分析结果精确切割视频，确保每个片段都是完整且连贯的。
            你的工作是将智能分析转化为实际的视频片段。""",
            verbose=True,
            allow_delegation=False,
            tools=[split_video_tool],
            llm=LLM(
                model="gemini-1.5-flash",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.7,
                custom_llm_provider="openai"
            )
        )
        
        return editing_agent 