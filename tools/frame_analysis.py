# tools/frame_analysis.py
import os
import base64
import openai
from PIL import Image
import io
from typing import Optional, Type, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class FrameAnalysisInput(BaseModel):
    """帧分析工具的输入模式"""
    frame_path: str = Field(..., description="帧图像的文件路径")
    context: Optional[str] = Field(None, description="可选的额外上下文信息，例如场景号、时间点等")

class BatchFrameAnalysisInput(BaseModel):
    """批量帧分析工具的输入模式"""
    frame_paths: List[str] = Field(..., description="帧图像路径列表")
    scene_info: Optional[dict] = Field(None, description="可选的场景信息")

class FrameAnalysisTools:
    
    @staticmethod
    def setup_openai():
        """设置 OpenAI API"""
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        base_url = os.environ.get('OPENAI_BASE_URL')
        if not base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        return openai.Client(api_key=api_key, base_url=base_url,)
    
    @staticmethod
    def encode_image(image_path):
        """将图像编码为 base64 字符串"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

class AnalyzeFrameTool(BaseTool):
    name: str = "AnalyzeFrame"
    description: str = "使用 Gemini 视觉能力分析视频帧"
    args_schema: Type[BaseModel] = FrameAnalysisInput
    
    def _run(self, frame_path: str, context: Optional[str] = None) -> dict:
        """
        使用 Gemini 模型分析一个视频帧
        
        参数:
        frame_path: 帧图像路径
        context: 可选的额外上下文信息，例如场景号、时间点等
        
        返回:
        帧分析结果
        """
        if not os.path.exists(frame_path):
            return f"Error: Frame file not found: {frame_path}"
        
        try:
            client = FrameAnalysisTools.setup_openai()
            
            # 编码图像
            base64_image = FrameAnalysisTools.encode_image(frame_path)
            
            # 构建提示
            prompt = """
            Please analyze this frame from a video and provide the following information:
            1. What is happening in this frame? Describe the scene, subjects, and actions.
            2. Visual aesthetics assessment (composition, lighting, colors)
            3. How might this frame be used in video editing?
            4. Any notable elements that make this frame particularly useful or not useful?
            
            If you have additional context about this frame, include that in your analysis.
            Context information: {context}
            
            Format your response as structured information that can be easily parsed.
            """
            
            # 填充上下文
            prompt = prompt.format(context=context if context else "No additional context provided")
            
            # 获取分析结果
            response = client.chat.completions.create(
                model="gemini-1.5-pro",  # 使用支持视觉的模型
                messages=[
                    {"role": "system", "content": "You are a professional video frame analyzer."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=1000
            )
            
            return {
                "frame_path": frame_path,
                "analysis": response.choices[0].message.content
            }
            
        except Exception as e:
            return f"Error analyzing frame: {str(e)}"

class BatchAnalyzeFramesTool(BaseTool):
    name: str = "BatchAnalyzeFrames"
    description: str = "使用 Gemini 视觉能力批量分析多个视频帧"
    args_schema: Type[BaseModel] = BatchFrameAnalysisInput
    
    def _run(self, frame_paths: List[str], scene_info: Optional[dict] = None) -> list:
        """
        使用 Gemini 模型批量分析多个视频帧
        
        参数:
        frame_paths: 帧图像路径列表
        scene_info: 可选的场景信息
        
        返回:
        多个帧的分析结果
        """
        results = []
        
        # 创建单帧分析工具实例
        analyze_frame_tool = AnalyzeFrameTool()
        
        for i, frame_path in enumerate(frame_paths):
            # 准备上下文信息
            context = None
            if scene_info and i < len(scene_info.get('scenes', [])):
                scene = scene_info['scenes'][i]
                context = f"Scene {scene.get('scene_number', i+1)}, starts at {scene.get('start_time', 'unknown')}, duration: {scene.get('duration', 'unknown')} seconds"
            
            # 分析帧
            result = analyze_frame_tool._run(frame_path, context)
            results.append(result)
        
        return results