import os
import json
import openai
from typing import Type, List, Dict, Any, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class FusionInput(BaseModel):
    """融合分析工具的输入模式"""
    transcription: dict = Field(..., description="语音转录结果")
    frames_analysis: Optional[dict] = Field(None, description="视频帧分析结果")
    frames_analysis_file: Optional[str] = Field(None, description="视频帧分析结果文件路径")
    min_segment_duration: float = Field(5.0, description="最小分段时长（秒）")

class FusionTools:
    
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

class FuseAudioVideoAnalysisTool(BaseTool):
    name: str = "FuseAudioVideoAnalysis"
    description: str = "融合语音转录和视频帧分析结果，生成智能分割点"
    args_schema: Type[BaseModel] = FusionInput
    
    def _run(self, transcription: dict, frames_analysis: Optional[dict] = None, 
             frames_analysis_file: Optional[str] = None, min_segment_duration: float = 5.0) -> dict:
        """
        融合语音转录和视频帧分析结果，生成智能分割点
        
        参数:
        transcription: 语音转录结果
        frames_analysis: 视频帧分析结果
        frames_analysis_file: 视频帧分析结果文件路径
        min_segment_duration: 最小分段时长（秒）
        
        返回:
        分割点信息
        """
        try:
            client = FusionTools.setup_openai()
            
            # 准备转录数据
            transcription_text = transcription.get("text", "")
            transcription_segments = transcription.get("segments", [])
            
            # 准备帧分析数据
            if frames_analysis is None and frames_analysis_file:
                # 从文件加载分析结果
                if not os.path.exists(frames_analysis_file):
                    return f"Error: Analysis result file not found: {frames_analysis_file}"
                
                print(f"从文件加载视频帧分析结果: {frames_analysis_file}")
                with open(frames_analysis_file, 'r', encoding='utf-8') as f:
                    full_analysis = json.load(f)
                
                # 提取帧分析部分
                frames_analysis = full_analysis.get("frames_analysis", {})
            
            if not frames_analysis:
                return "Error: No frames analysis data provided"
            
            # 获取帧分析数据
            frames_data = frames_analysis.get("frames_analysis", [])
            
            # 构建提示
            prompt = f"""
            你是一名专业的视频编辑专家。请结合以下语音转录和视频帧分析结果，确定视频的最佳分割点。
            
            ## 语音转录全文:
            {transcription_text}
            
            ## 语音转录分段:
            {json.dumps(transcription_segments, indent=2, ensure_ascii=False)}
            
            ## 视频帧分析:
            {json.dumps(frames_data, indent=2, ensure_ascii=False)}
            
            请分析以上数据，找出视频的逻辑分割点。分割点应该考虑以下因素:
            1. 语音内容的主题变化
            2. 视觉场景的明显变化
            3. 自然的停顿点
            
            请返回JSON格式的分割点信息，格式如下:
            {{
                "segments": [
                    {{
                        "start": 开始时间（秒）,
                        "end": 结束时间（秒）,
                        "title": "分段标题",
                        "description": "分段内容描述"
                    }},
                    ...
                ]
            }}
            
            注意:
            - 每个分段至少应该有 {min_segment_duration} 秒长
            - 分段应该覆盖整个视频
            - 分段应该在语义和视觉上都是连贯的
            
            只返回JSON格式的结果，不要有其他解释。
            """
            
            # 获取分析结果
            response = client.chat.completions.create(
                model="anthropic.claude-3-5-sonnet-20241022-v2:0",  # 使用高级模型进行复杂分析
                messages=[
                    {"role": "system", "content": "你是一名专业的视频编辑专家，具备汽车类短视频的剪辑经验，擅长分析视频内容并确定最佳分割点。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=2000
            )
            
            # 解析结果
            result = json.loads(response.choices[0].message.content)
            
            return result
            
        except Exception as e:
            return f"Error fusing analysis: {str(e)}" 