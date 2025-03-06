import os
from openai import OpenAI
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import httpx

class TranscriptionInput(BaseModel):
    """语音转录工具的输入模式"""
    video_path: str = Field(..., description="视频文件的路径")
    language: str = Field("zh", description="视频主要语言，例如：zh, en, ja")

class TranscribeVideoTool(BaseTool):
    name: str = "TranscribeVideo"
    description: str = "使用OpenAI API进行语音转录，提取字幕文本"
    args_schema: Type[BaseModel] = TranscriptionInput
    
    def _run(self, video_path: str, language: str = "zh") -> dict:
        """
        使用OpenAI API进行语音转录
        
        参数:
        video_path: 视频文件路径
        language: 视频主要语言
        
        返回:
        转录结果，包含文本和时间戳
        """
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        try:
            # 设置 OpenAI API
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            
            base_url = os.environ.get('OPENAI_BASE_URL')
            if not base_url:
                raise ValueError("OPENAI_BASE_URL environment variable is not set")
            
            client = OpenAI(api_key=api_key, base_url=base_url,http_client=httpx.Client(
                proxies={
                    "http://": "http://172.22.93.27:1081",
                    "https://": "https://172.22.93.27:1081"
                })
            )
            
            # 打开音频文件
            with open(video_path, "rb") as audio_file:
                # 转录视频
                response = client.audio.transcriptions.create(
                    model="whisper",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json"
                )
            
            # 提取结果
            transcription = {
                "text": response.text,
                "segments": []
            }
            
            # 提取分段信息
            for segment in response.segments:
                transcription["segments"].append({
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                })
            
            return transcription
            
        except Exception as e:
            return f"Error transcribing video: {str(e)}" 