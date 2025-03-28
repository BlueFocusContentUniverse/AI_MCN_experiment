from crewai import Agent, LLM
from tools.vision_analysis_enhanced import ExtractVideoFramesTool, AnalyzeVideoFramesTool, BatchProcessingFramesTool, LoadFramesAnalysisFromFileTool
import os
class VisionAgent:
    @staticmethod
    def create():
        """创建视觉分析 Agent"""
        # 创建工具实例
        extract_frames_tool = ExtractVideoFramesTool()
        analyze_frames_tool = AnalyzeVideoFramesTool()
        batch_processing_tool = BatchProcessingFramesTool()
        load_analysis_tool = LoadFramesAnalysisFromFileTool()
        
        # 创建 Agent
        vision_agent = Agent(
            role="视觉分析专家",
            goal="分析视频的视觉内容，识别场景变化和关键视觉元素",
            backstory="""你是一名计算机视觉专家，擅长分析视频的视觉内容。
            你能够识别场景变化、视觉风格、构图特点和关键视觉元素。
            你的工作是提供视频的视觉分析，为智能视频分割提供视觉依据。
            对于长视频，你必须采用分批处理的方式，确保整个视频都能被完整分析。
            你会使用均匀采样策略，确保提取的帧能代表整个视频的内容。
            但是如果视频内容是汽车相关的，你会采用更密集的采样策略，确保提取的帧能代表整个视频的内容。
            保证每秒钟至少有1帧采样数据**且frame_interval不能大于2**
            
            重要提示：对于任何视频分析任务，你必须使用BatchProcessingFrames工具，该工具会自动处理分批逻辑，确保所有帧都被分析。
            该工具会将完整的分析结果保存到文件中，并返回文件路径，以便后续处理。
            在你的回复中，请确保包含结果文件的路径，这样下一个Agent就能使用LoadFramesAnalysisFromFile工具加载完整的分析结果。
            其中，"frames_analysis_file"是结果文件的路径，请务必使用这个字段，否则下一个Agent无法正确加载分析结果。""",
            verbose=True,
            allow_delegation=False,
            tools=[extract_frames_tool, analyze_frames_tool, batch_processing_tool, load_analysis_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
                temperature=0.1,
                custom_llm_provider="openai"
            )
        )
        
        return vision_agent 