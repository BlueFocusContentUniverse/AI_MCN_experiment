from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from services.mongodb_service import MongoDBService
import os
import numpy as np
from services.embedding_service import EmbeddingService  # 假设有这样一个服务来获取嵌入向量
from tools.text_matching_tool import TextMatchingTool


class MaterialSearchInput(BaseModel):
    """素材搜索工具的输入模式"""
    requirements: List[Dict[str, Any]] = Field(..., description="视频需求列表，每个需求包含场景类型、视觉元素等")
    limit_per_requirement: int = Field(5, description="每个需求返回的最大素材数量")

class MaterialSearchTool(BaseTool):
    name: str = "MaterialSearch"
    description: str = "根据视频需求搜索匹配的素材"
    args_schema: Type[BaseModel] = MaterialSearchInput
    mongodb_service: MongoDBService = None
    embedding_service: EmbeddingService = None
    
    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self):
        super().__init__()
        self.mongodb_service = MongoDBService()
        self.embedding_service = EmbeddingService()  # 初始化嵌入服务
    
    def _run(self, requirements: List[Dict[str, Any]], limit_per_requirement: int = 25) -> dict:
        """
        根据视频需求搜索匹配的素材，使用向量搜索
        
        参数:
        requirements: 视频需求列表，每个需求包含场景类型、视觉元素等
        limit_per_requirement: 每个需求返回的最大素材数量
        
        返回:
        匹配的素材列表
        """
        results = []
        
        for i, requirement in enumerate(requirements):
            print(f"搜索需求 {i+1}: {requirement.get('description', '未提供描述')}")
            
            # 构建需求描述文本
            requirement_text = ""
            if "description" in requirement:
                requirement_text += requirement["description"] + " "
            if "scene_type" in requirement:
                requirement_text += f"场景类型: {requirement['scene_type']} "
            if "mood" in requirement:
                requirement_text += f"情绪: {requirement['mood']} "
            if "keywords" in requirement:
                keywords = requirement["keywords"]
                if isinstance(keywords, list):
                    requirement_text += f"关键词: {', '.join(keywords)} "
                else:
                    requirement_text += f"关键词: {keywords} "
            
            print(f"生成的需求描述文本: {requirement_text}")
            
            # 获取需求的向量表示
            try:
                requirement_vector = self.embedding_service.get_embedding(requirement_text)
                print(f"成功获取需求向量，维度: {len(requirement_vector)}")
            except Exception as e:
                print(f"获取需求向量时出错: {str(e)}")
                continue
            
            # 基于品牌的预过滤条件（可选）
            pre_filter = {}
            if "brand" in requirement and requirement["brand"]:
                pre_filter["brand"] = requirement["brand"]
                print(f"添加品牌过滤条件: {requirement['brand']}")
            
            # 执行向量搜索
            try:
                matching_videos = self.mongodb_service.vector_search(
                    vector=requirement_vector,
                    pre_filter=pre_filter,
                    limit=limit_per_requirement
                )
                print(f"向量搜索完成，找到 {len(matching_videos)} 个匹配的视频")
            except Exception as e:
                print(f"执行向量搜索时出错: {str(e)}")
                matching_videos = []
            
            # 添加到结果
            result = {
                "requirement": requirement,
                "matching_videos": []
            }
            
            for video in matching_videos:
                # 提取需要的信息
                video_info = {
                    "_id": str(video.get("_id", "")),
                    "video_path": video.get("video_path", ""),
                    "brand": video.get("brand", ""),
                    "analysis_time": video.get("analysis_time", ""),
                    "frames_analysis_file": video.get("frames_analysis_file", ""),
                    "cinematography_analysis": video.get("cinematography_analysis", ""),
                    "similarity_score": video.get("similarity_score", 0)  # 向量搜索返回的相似度分数
                }
                result["matching_videos"].append(video_info)
            
            results.append(result)
            print(f"找到 {len(result['matching_videos'])} 个匹配的视频")
        
        return {
            "requirements_count": len(requirements),
            "results": results
        }

class MaterialSearchAgent:
    @staticmethod
    def create():
        """创建素材搜索 Agent"""
        # 创建工具实例
        material_search_tool = MaterialSearchTool()
        text_matching_tool = TextMatchingTool()  # 添加文本匹配工具
        
        # 创建 Agent
        material_search_agent = Agent(
            role="视频素材搜索专家",
            goal="搜索匹配的视频素材，包括原话匹配和画面匹配",
            backstory="""你是一名资深的视频素材搜索专家，擅长根据需求查找最合适的视频素材。
            你熟悉各种视频类型和内容标签，能够精确匹配视觉元素和场景类型。
            你的工作是为每个需求找到最匹配的视频素材，包括原话匹配（需要在数据库中查找包含特定文本的视频片段）
            和画面匹配（需要根据视觉描述查找合适的视频素材）。
            你会考虑场景类型、视觉元素、情绪基调等因素，确保找到的素材能够准确表达需求的内容和情感。""",
            verbose=True,
            allow_delegation=False,
            tools=[material_search_tool, text_matching_tool],  # 添加文本匹配工具
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            )
        )
        
        return material_search_agent 