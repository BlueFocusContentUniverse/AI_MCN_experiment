from crewai import Agent
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from services.mongodb_service import MongoDBService

class MaterialSearchInput(BaseModel):
    """素材搜索工具的输入模式"""
    requirements: List[Dict[str, Any]] = Field(..., description="视频需求列表，每个需求包含场景类型、视觉元素等")
    limit_per_requirement: int = Field(5, description="每个需求返回的最大素材数量")

class MaterialSearchTool(BaseTool):
    name: str = "MaterialSearch"
    description: str = "根据视频需求搜索匹配的素材"
    args_schema: Type[BaseModel] = MaterialSearchInput
    
    def __init__(self):
        super().__init__()
        self.mongodb_service = MongoDBService()
    
    def _run(self, requirements: List[Dict[str, Any]], limit_per_requirement: int = 5) -> dict:
        """
        根据视频需求搜索匹配的素材
        
        参数:
        requirements: 视频需求列表，每个需求包含场景类型、视觉元素等
        limit_per_requirement: 每个需求返回的最大素材数量
        
        返回:
        匹配的素材列表
        """
        results = []
        
        for i, requirement in enumerate(requirements):
            print(f"搜索需求 {i+1}: {requirement.get('description', '未提供描述')}")
            
            # 构建搜索条件
            search_criteria = {}
            
            # 添加场景类型条件
            if "scene_type" in requirement:
                search_criteria["visual_features.scene_type"] = requirement["scene_type"]
            
            # 添加内容标签条件
            if "tags" in requirement and requirement["tags"]:
                tags = requirement["tags"]
                if isinstance(tags, list):
                    # 如果有多个标签，至少匹配一个
                    search_criteria["content_tags"] = {"$in": tags}
                else:
                    search_criteria["content_tags"] = tags
            
            # 添加情绪条件
            if "mood" in requirement:
                search_criteria["multimodal_info.mood"] = requirement["mood"]
            
            # 搜索视频
            matching_videos = self.mongodb_service.search_videos_by_criteria(
                search_criteria, 
                limit=limit_per_requirement
            )
            
            # 添加到结果
            result = {
                "requirement": requirement,
                "matching_videos": []
            }
            
            for video in matching_videos:
                # 提取需要的信息
                video_info = {
                    "video_path": video.get("video_path", ""),
                    "video_filename": video.get("video_filename", ""),
                    "basic_info": video.get("basic_info", {}),
                    "content_summary": video.get("content_summary", {}),
                    "content_tags": video.get("content_tags", []),
                    "multimodal_info": video.get("multimodal_info", {})
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
            goal="根据视频需求搜索最匹配的素材",
            backstory="""你是一名专业的视频素材管理专家，擅长从海量素材库中找到最匹配需求的视频片段。
            你熟悉各种视频类型和风格，能够根据场景描述、视觉元素、情绪基调等要求，
            精准定位合适的素材。你的工作是为视频制作团队提供高质量的素材选择，
            确保最终的视频能够达到预期的视觉效果。特别是对于汽车相关视频，
            你能够找到最能展现车辆特点和魅力的素材。""",
            verbose=True,
            allow_delegation=False,
            tools=[material_search_tool],
            llm_config={"model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        )
        
        return material_search_agent 