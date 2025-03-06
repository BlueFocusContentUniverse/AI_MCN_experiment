# tools/video_analysis.py
import os
import cv2
import tempfile
import base64
import openai
from PIL import Image
import io
import numpy as np
from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class VideoPathInput(BaseModel):
    """视频路径输入模式"""
    video_path: str = Field(..., description="视频文件的路径")

class VideoAnalysisTools:
    
    @staticmethod
    def setup_openai():
        """设置 OpenAI API"""
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        base_url = os.environ.get('OPENAI_BASE_URL')
        if not base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        return openai.Client(api_key=api_key, base_url=base_url)
    
    @staticmethod
    def encode_image(image_path):
        """将图像编码为 base64 字符串"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    @staticmethod
    def analyze_frames_with_openai(frame_paths):
        """使用 OpenAI 分析视频帧"""
        try:
            client = VideoAnalysisTools.setup_openai()
            
            # 准备图像数据
            image_contents = []
            for frame_path in frame_paths:
                base64_image = VideoAnalysisTools.encode_image(frame_path)
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })
            
            # 构建提示
            prompt = """
            Please analyze these frames from a video and provide the following information:
            1. Video type (e.g., vlog, tutorial, documentary, review, etc.)
            2. Video quality (e.g., high-definition, low quality, professional, amateur)
            3. Content description (what's shown in the frames)
            4. Visual aesthetics (composition, lighting, colors)
            5. Overall quality score (1-10) with justification
            
            Format the response as structured information that can be easily parsed.
            """
            
            # 构建消息内容
            message_content = [{"type": "text", "text": prompt}]
            message_content.extend(image_contents)
            
            # 获取分析结果
            response = client.chat.completions.create(
                model="gemini-1.5-flash",  # 使用支持视觉的模型
                messages=[
                    {"role": "system", "content": "You are a professional video analyst."},
                    {"role": "user", "content": message_content}
                ],
                max_tokens=1500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Error analyzing frames with OpenAI: {str(e)}"

class GetVideoInfoTool(BaseTool):
    name: str = "GetVideoInfo"
    description: str = "提取视频的基本信息，包括分辨率、时长等"
    args_schema: Type[BaseModel] = VideoPathInput
    
    def _run(self, video_path: str) -> dict:
        """获取视频的基本信息"""
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return f"Error: Could not open video file: {video_path}"
            
            # 获取视频基本信息
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            # 提取视频的代表性帧用于分析
            frame_positions = [0.05,0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.65, 0.7, 0.8,  0.9]  # 在视频的不同位置取帧
            sample_frames = []
            
            for pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * pos))
                ret, frame = cap.read()
                if ret:
                    sample_frames.append(frame)

            cap.release()
            
            # 准备视频基本信息
            video_info = {
                "filename": os.path.basename(video_path),
                "resolution": f"{width}x{height}",
                "duration": f"{duration:.2f} seconds",
                "frame_count": frame_count,
                "fps": fps,
            }
            
            # 使用临时文件保存样本帧
            temp_frames = []
            for i, frame in enumerate(sample_frames):
                temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                cv2.imwrite(temp_file.name, frame)
                temp_frames.append(temp_file.name)
            
            # 分析样本帧
            frame_analysis = VideoAnalysisTools.analyze_frames_with_openai(temp_frames)
            
            # 清理临时文件
            for temp_file in temp_frames:
                os.unlink(temp_file)
            
            # 合并信息
            result = {
                "video_info": video_info,
                "frame_analysis": frame_analysis
            }
            
            return result
        
        except Exception as e:
            return f"Error analyzing video: {str(e)}"

class AnalyzeVideoQualityTool(BaseTool):
    name: str = "AnalyzeVideoQuality"
    description: str = "使用 OpenAI 视觉能力分析视频质量"
    args_schema: Type[BaseModel] = VideoPathInput
    
    def _run(self, video_path: str) -> dict:
        """使用 OpenAI 分析视频质量"""
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        try:
            # 创建视频基本信息工具实例
            video_info_tool = GetVideoInfoTool()
            
            # 分析视频
            analysis_result = video_info_tool._run(video_path)
            
            return analysis_result
        except Exception as e:
            return f"Error analyzing video quality: {str(e)}"