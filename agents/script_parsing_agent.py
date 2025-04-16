from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
import re
import json

class ScriptParsingInput(BaseModel):
    """脚本解析工具的输入模式"""
    script: Any = Field(..., description="需要解析的脚本文本")
    target_duration: Any = Field(default=60.0, description="目标视频总时长（秒）")
    
    @property
    def script_value(self) -> str:
        """获取脚本文本，无论是直接提供的字符串还是嵌套在字典中"""
        if isinstance(self.script, dict) and "description" in self.script:
            return self.script["description"]
        return self.script
    
    @property
    def duration_value(self) -> float:
        """获取时长值，无论是直接提供的数值还是嵌套在字典中"""
        if isinstance(self.target_duration, dict) and "description" in self.target_duration:
            try:
                return float(self.target_duration["description"])
            except (ValueError, TypeError):
                return 60.0
        
        try:
            return float(self.target_duration) if self.target_duration is not None else 60.0
        except (ValueError, TypeError):
            return 60.0

class ScriptParsingTool(BaseTool):
    name: str = "ScriptParsing"
    description: str = "解析视频脚本，识别场景并分配时长和视觉需求"
    args_schema: Type[BaseModel] = ScriptParsingInput
    
    def _prepare_parameters(self, **kwargs):
        """
        重写参数准备方法，以处理CrewAI传递的参数格式
        
        参数:
        kwargs: 传入的关键字参数
        
        返回:
        处理后的参数字典
        """
        params = {}
        
        # 处理script参数
        script = kwargs.get("script")
        if isinstance(script, dict) and "description" in script:
            params["script"] = script["description"]
        else:
            params["script"] = script
            
        # 处理target_duration参数
        target_duration = kwargs.get("target_duration", 60.0)
        if isinstance(target_duration, dict) and "description" in target_duration:
            try:
                params["target_duration"] = float(target_duration["description"])
            except (ValueError, TypeError):
                params["target_duration"] = 60.0  # 默认值
        else:
            try:
                params["target_duration"] = float(target_duration) if target_duration is not None else 60.0
            except (ValueError, TypeError):
                params["target_duration"] = 60.0
                
        return params
    
    def _run(self, **kwargs) -> dict:
        """
        解析视频脚本，识别场景并分配时长和视觉需求
        
        参数:
        kwargs: 包含script和target_duration的关键字参数字典
        
        返回:
        解析后的脚本结构
        """
        # 从kwargs中提取script参数
        script = kwargs.get("script", "")
        if isinstance(script, dict) and "description" in script:
            script = script["description"]
        
        # 从kwargs中提取target_duration参数    
        target_duration = kwargs.get("target_duration", 60.0)
        if isinstance(target_duration, dict) and "description" in target_duration:
            try:
                target_duration = float(target_duration["description"])
            except (ValueError, TypeError):
                target_duration = 60.0
        else:
            try:
                target_duration = float(target_duration) if target_duration is not None else 60.0
            except (ValueError, TypeError):
                target_duration = 60.0
        
        return {
            "script": script,
            "target_duration": target_duration,
            "message": """解析这个视频脚本，识别其中的独立场景并为每个场景分配合理的时长和视觉需求。

对于每个场景，请提供：
1. 场景编号和简短描述
2. 场景所需视觉元素和关键内容
3. 场景时长建议（秒）
4. 场景情感基调和视觉风格
5. 场景类型（如产品展示、场景氛围、人物介绍等）

请确保所有场景时长总和接近目标视频时长。如果脚本中已包含时间标记，请尊重这些标记；如果没有，请根据内容重要性和描述长度合理分配时间。

输出结果将用于后续自动视频素材匹配和剪辑。"""
        }

class ScriptParsingAgent:
    @staticmethod
    def create():
        """创建脚本解析 Agent"""
        # 创建工具实例
        script_parsing_tool = ScriptParsingTool()
        
        # 创建 Agent
        script_parsing_agent = Agent(
            role="视频脚本解析专家",
            goal="解析视频脚本，识别场景并分配时长和视觉需求",
            backstory="""你是一名专业的视频脚本解析专家，擅长分析视频脚本的结构和内容。
            你的任务是将脚本分解为独立场景，并为每个场景分配合理的时长和视觉需求。
            你需要识别每个场景的关键视觉元素、情感基调和场景类型，以便后续系统能够匹配到合适的视频素材。
            你对视频制作有深入了解，明白如何将文字脚本转化为视频场景，保持视觉连贯性和叙事流畅。""",
            verbose=True,
            allow_delegation=False,
            tools=[script_parsing_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            ),
            response_template="""
                请严格遵循以下格式输出json：
                {{ .Response }}
                {
                    "segments": [
                        {
                            "segment_id": 1,
                            "content": "场景描述内容",
                            "text": "场景内容文本",
                            "description": "详细场景描述",
                            "visual_elements": ["需要的视觉元素1", "视觉元素2"],
                            "start_time": 0, 
                            "end_time": 10, 
                            "duration": 10,
                            "emotion": "场景情感基调",
                            "scene_type": "场景类型（产品展示/功能演示/场景氛围等）"
                        }
                    ],
                    "total_duration": 60
                }
                """
        )
        
        return script_parsing_agent 