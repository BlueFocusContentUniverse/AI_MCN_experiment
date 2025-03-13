from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from services.mongodb_service import MongoDBService
import os
import numpy as np
from services.embedding_service import EmbeddingService  # 假设有这样一个服务来获取嵌入向量


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
        
        # 创建 Agent
        material_search_agent = Agent(
            role="视频素材专家",
            goal="根据视频需求搜索最匹配的素材，按要求输出为json格式以便下一个Agent可以拿到结果并处理",
            backstory="""你是一名专业的视频素材管理专家，擅长从海量素材库中找到最匹配需求的视频片段。
            你熟悉各种视频类型和风格，能够根据场景描述、视觉元素、情绪基调等要求，
            精准定位合适的素材。你的工作是为视频制作团队提供高质量的素材选择，
            确保最终的视频能够达到预期的视觉效果。特别是对于汽车相关视频，
            你能够找到最能展现车辆特点和魅力的素材。
            注意，在寻找素材时务必确保视频素材和需求高度匹配，**根据视频名称可判断该视频所属汽车品牌**，**汽车品牌和视频需求中的品牌必须匹配，如本田ZRV，小米SU7，特斯拉Model3等**，否则不返回结果
            输出为json格式以便下一个Agent可以拿到结果并处理，json内禁止出现换行符！""",
            verbose=True,
            allow_delegation=False,
            tools=[material_search_tool],
            llm=LLM(
                model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            )
        )
        
        return material_search_agent 