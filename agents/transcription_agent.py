from crewai import Agent
from tools.transcription import TranscribeVideoTool

class TranscriptionAgent:
    @staticmethod
    def create():
        """创建语音转录 Agent"""
        # 创建工具实例
        transcribe_video_tool = TranscribeVideoTool()
        
        # 创建 Agent
        transcription_agent = Agent(
            role="语音转录专家",
            goal="将视频音频转换为文本，提取字幕信息",
            backstory="""你是一名语音识别专家，擅长将视频中的语音内容转换为高质量的文本。
            你能够准确识别不同语言、口音和说话风格，并提供带有时间戳的字幕。
            你的工作是为视频分析提供语音内容的文本基础。""",
            verbose=True,
            allow_delegation=False,
            tools=[transcribe_video_tool],
            llm_config={"model": "gemini-1.5-flash"}
        )
        
        return transcription_agent 