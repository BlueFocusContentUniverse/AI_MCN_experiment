from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
import json
import datetime

class RequirementParsingInput(BaseModel):
    """需求解析工具的输入模式"""
    user_requirement: str = Field(..., description="用户输入的自然语言需求描述")
    brands: List[str] = Field(None, description="可选的品牌列表")
    models: List[str] = Field(None, description="可选的车型列表")
    target_platforms: List[str] = Field(None, description="目标平台")
    target_duration: float = Field(None, description="目标视频时长（秒）")

class RequirementParsingTool(BaseTool):
    name: str = "RequirementParsing"
    description: str = "分析用户的自然语言需求，转换为标准中间表示(IR)格式"
    args_schema: Type[BaseModel] = RequirementParsingInput
    
    def _run(self, user_requirement: str, brands: List[str] = None, models: List[str] = None, 
             target_platforms: List[str] = None, target_duration: float = None) -> dict:
        """
        分析用户需求，生成标准IR
        
        参数:
        user_requirement: 用户输入的自然语言需求描述
        brands: 可选的品牌列表
        models: 可选的车型列表
        target_platforms: 目标平台
        target_duration: 目标视频时长（秒）
        
        返回:
        标准IR格式的需求表示
        """
        # 这里将使用Agent的LLM能力，所以只需返回输入参数
        return {
            "user_requirement": user_requirement,
            "brands": brands or [],
            "models": models or [],
            "target_platforms": target_platforms or ["微信", "抖音"],
            "target_duration": target_duration or 60.0,
            "message": "请分析这个用户需求，生成标准化的中间表示(IR)格式"
        }

class RequirementParsingAgent:
    @staticmethod
    def create():
        """创建需求解析 Agent"""
        # 创建工具实例
        requirement_parsing_tool = RequirementParsingTool()
        
        # 创建 Agent
        requirement_parsing_agent = Agent(
            role="视频需求分析专家",
            goal="分析用户需求，生成标准化视频制作指令",
            backstory="""你是一名资深的视频需求分析专家，擅长将用户的自然语言需求转化为精确的视频制作指令。
            你熟悉短视频制作的各个方面，包括镜头语言、剪辑风格、音频处理和后期制作。
            你能够理解用户的意图，即使在需求不完整或模糊的情况下，也能根据上下文和最佳实践补充必要的细节。
            你的任务是将各种形式的用户需求转化为标准化的中间表示格式，以便后续系统组件能够准确执行。
            
            你特别擅长分析以下方面：
            1. 视频整体结构（开场、主体、结尾等）
            2. 音频需求（配音、背景音乐、原声、音效等）
            3. 视觉风格要求（色调、镜头类型、节奏等）
            4. 场景转换和情感表达
            5. 品牌和产品特性展示方式
            
            对于不明确的要求，你会根据汽车视频制作的最佳实践做出合理推断，确保生成的指令全面且可执行。""",
            verbose=True,
            allow_delegation=False,
            tools=[requirement_parsing_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            ),
            response_template="""
                请将用户的自然语言需求分析并转换为标准化的中间表示(IR)格式。要考虑视频整体结构、音频需求、视觉风格、场景转换和品牌展示方式。
                {{ .Response }}
                
                确保返回的是完整有效的JSON对象，包含以下主要部分：
                - metadata（元数据，包含项目基本信息）
                - audio_design（音频设计，包含口播、背景音乐、音效等）
                - visual_structure（视觉结构，包含视频分段、镜头要求等）
                - post_processing（后期处理，包含字幕、滤镜、标志等）
                - export_settings（导出设置，包含格式、质量等）
                
                如果用户没有明确指定的部分，请根据视频制作的最佳实践补充合理的默认值。
                """
        )
        
        return requirement_parsing_agent 