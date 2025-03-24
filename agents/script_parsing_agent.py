from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
import re
import json

class ScriptParsingInput(BaseModel):
    """脚本解析工具的输入模式"""
    script: str = Field(..., description="需要解析的脚本文本")

class ScriptParsingTool(BaseTool):
    name: str = "ScriptParsing"
    description: str = "解析脚本，区分需要原话匹配的部分和需要画面匹配的部分"
    args_schema: Type[BaseModel] = ScriptParsingInput
    
    def _run(self, script: str) -> dict:
        """
        解析脚本，区分需要原话匹配的部分和需要画面匹配的部分
        
        参数:
        script: 需要解析的脚本文本
        
        返回:
        解析后的脚本结构
        """
        return {
            "script": script,
            "message": """请解析这个脚本，区分需要原话匹配的部分和需要画面匹配的部分。

原话匹配部分通常是引用的说话内容，需要在数据库中查找原始视频片段。
画面匹配部分是对画面的描述，需要根据描述查找合适的视频素材。

请输出结构化的解析结果，包含每个片段的类型、内容、时间信息等。"""
        }

class ScriptParsingAgent:
    @staticmethod
    def create():
        """创建脚本解析 Agent"""
        # 创建工具实例
        script_parsing_tool = ScriptParsingTool()
        
        # 创建 Agent
        script_parsing_agent = Agent(
            role="脚本解析专家",
            goal="解析脚本，区分需要原话匹配的部分和需要画面匹配的部分",
            backstory="""你是一名专业的视频脚本解析专家，擅长分析视频脚本的结构和内容。
            你的任务是解析脚本，准确区分需要原话匹配的部分（通常是引用的说话内容）和需要画面匹配的部分（通常是对画面的描述）。
            你需要输出结构化的解析结果，以便后续系统能够根据不同类型的内容查找合适的视频素材。""",
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
                            "type": "quote", // 原话匹配类型为"quote"，画面匹配类型为"visual"
                            "content": "需要匹配的内容",
                            "start_time": 10, // 开始时间（秒）
                            "end_time": 15, // 结束时间（秒）
                            "description": "额外描述信息"
                        }
                    ]
                }
                """
        )
        
        return script_parsing_agent 