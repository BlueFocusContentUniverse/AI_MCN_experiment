# agents/executor_agent.py
from crewai import Agent
from tools.scene_detection import DetectScenesTool, ExtractSceneFramesTool
from tools.frame_analysis import AnalyzeFrameTool, BatchAnalyzeFramesTool

class ExecutorAgent:
    @staticmethod
    def create():
        """创建执行 Agent"""
        # 创建工具实例
        scene_detection_tool = DetectScenesTool()
        extract_frames_tool = ExtractSceneFramesTool()
        analyze_frame_tool = AnalyzeFrameTool()
        batch_analyze_frames_tool = BatchAnalyzeFramesTool()
        
        # 创建 Agent
        executor = Agent(
            role="Video Processing Specialist",
            goal="Process video content according to the director's specifications",
            backstory="""You are a skilled video processor with expertise in scene detection,
            frame extraction, and content analysis. You work closely with the director
            to transform their creative vision into concrete video segments and descriptions.""",
            verbose=True,
            allow_delegation=False,
            tools=[scene_detection_tool, extract_frames_tool, analyze_frame_tool, batch_analyze_frames_tool],
            llm_config={"model": "gemini-1.5-flash"}
        )
        
        return executor