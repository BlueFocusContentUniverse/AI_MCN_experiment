from crewai import Agent, LLM
from tools.vision_analysis_enhanced import LoadFramesAnalysisFromFileTool
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from langchain.chat_models import ChatOpenAI
import os


class CinematographyInput(BaseModel):
    """电影摄影分析工具的输入模式"""
    frames_analysis_file: str = Field(..., description="视频帧分析结果文件路径")

class CinematographyAnalysisTool(BaseTool):
    name: str = "CinematographyAnalysis"
    description: str = "分析视频的运镜、色调、节奏等动态特征"
    args_schema: Type[BaseModel] = CinematographyInput
    
    def _run(self, frames_analysis_file: str) -> dict:
        """
        分析视频的运镜、色调、节奏等动态特征
        
        参数:
        frames_analysis_file: 视频帧分析结果文件路径
        
        返回:
        视频动态特征分析结果
        """
        # 使用LoadFramesAnalysisFromFileTool加载帧分析结果
        load_tool = LoadFramesAnalysisFromFileTool()
        frames_analysis = load_tool._run(frames_analysis_file)
        
        if isinstance(frames_analysis, str) and frames_analysis.startswith("Error"):
            return frames_analysis
        
        # 构建提示，请求LLM分析动态特征
        # 这里将使用Agent的LLM能力，所以只需返回帧分析结果
        return {
            "frames_analysis": frames_analysis,
            "message": "请分析这些帧的动态特征，包括运镜变化、色调、节奏感等"
        }

class CinematographyAgent:
    @staticmethod
    def create():
        """创建电影摄影分析 Agent"""
        # 创建工具实例
        cinematography_tool = CinematographyAnalysisTool()
        load_analysis_tool = LoadFramesAnalysisFromFileTool()
        
        # 创建 Agent
        cinematography_agent = Agent(
            role="电影摄影专家",
            goal="分析视频的运镜、色调、节奏等动态特征",
            backstory="""你是一名资深的电影摄影师和视觉艺术家，擅长分析视频的视觉语言和动态特征。
            你能够识别不同的运镜技巧（如推、拉、摇、移等），分析色彩搭配和色调变化，
            感知视频的节奏感和情绪变化。你的工作是从静态帧分析中提取动态信息，
            为视频内容提供更深层次的理解。

            首先，你需要判断素材类型：
            1. 如果是画面丰富的素材（如汽车展示、风景、产品展示等）：
               特别是对于汽车相关视频，你能够精准描述车辆展示的动态效果、速度感的表现以及视觉冲击力。
               请在输出中对于运镜、分镜、色彩、节奏等进行总结，并给出每个镜头的开始时间、结束时间、镜头类型、镜头描述、
               镜头画面描述、镜头色彩描述、镜头节奏描述、镜头情绪描述。
               由于是汽车相关的视频，你的分析需要从汽车的角度出发，重点分析汽车相关的场景和内容，
               也需要包含汽车的外观、内饰、动力、性能等。（如果有的话）
            
            2. 如果是人物采访类素材：
               你需要重点关注语音信息和语义完整性，按照语音内容进行切分。
               对于采访内容，应保持语义的完整性，确保每个切分点都是在语义自然结束的地方。
               请在输出中给出每个语义段落的开始时间、结束时间、主要内容概述、说话人情绪、
               背景画面描述（如有变化）。
               切分时应优先考虑语音内容的连贯性，而非画面变化。
            
            通用要求：
            - 需要包含一定细节，同时需要严格参照帧的时间戳
            - 每段视频素材不能低于2秒，否则会被剪辑师删除
            - 如果两个片段属于同一个场景或同一个语义单元，那么需要合并成一段视频，不要切割
            - 请严格参照解析结果中的时间戳给出分割点信息，因为分割点不准确会直接导致最后的效果大打折扣
            - 你的分析将作为下一个Agent进行剪辑的重要参考""",
            verbose=True,
            allow_delegation=False,
            tools=[cinematography_tool, load_analysis_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.7,
                custom_llm_provider="openai"
            )
        )
        
        return cinematography_agent 