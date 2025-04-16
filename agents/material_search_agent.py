from crewai import Agent, LLM
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
from services.mongodb_service import MongoDBService
import os
import json
import numpy as np
from bson import ObjectId
import time
import openai
from services.embedding_service import EmbeddingService
from services.material_matching_service import MaterialMatchingService
from tools.text_matching_tool import TextMatchingTool
from services.vector_search_service import VectorSearchService


class MaterialSearchInput(BaseModel):
    """素材搜索工具的输入模式"""
    requirements: List[Dict[str, Any]] = Field(..., description="视频需求列表，每个需求包含场景类型、视觉元素等")
    limit_per_requirement: int = Field(5, description="每个需求返回的最大素材数量")

class ScriptToVideoInput(BaseModel):
    """脚本到视频匹配工具的输入模式"""
    script: str = Field(..., description="视频脚本文本")
    brand: str = Field(None, description="可选的品牌名称过滤")

class MaterialSearchTool(BaseTool):
    name: str = "MaterialSearch"
    description: str = "根据视频需求搜索匹配的素材"
    args_schema: Type[BaseModel] = MaterialSearchInput
    mongodb_service: MongoDBService = None
    embedding_service: EmbeddingService = None
    vector_search_service: VectorSearchService = None
    db_id_type: str = "unknown"  # 数据库中存储的ID类型
    
    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self):
        super().__init__()
        self.mongodb_service = MongoDBService()
        self.embedding_service = EmbeddingService()
        self.vector_search_service = VectorSearchService(self.mongodb_service)
        # 检测数据库中的ID类型
        self._detect_db_id_type()
    
    def _detect_db_id_type(self):
        """检测数据库中的ID类型"""
        try:
            # 尝试获取一个视频片段
            sample_segment = self.mongodb_service.db.video_segments.find_one({}, {"video_id": 1})
            if sample_segment:
                video_id = sample_segment.get("video_id")
                if isinstance(video_id, str):
                    self.db_id_type = "string"
                    print("检测到数据库中的video_id类型为字符串")
                elif isinstance(video_id, ObjectId):
                    self.db_id_type = "objectid"
                    print("检测到数据库中的video_id类型为ObjectId")
                else:
                    self.db_id_type = "unknown"
                    print(f"检测到数据库中的video_id类型为: {type(video_id)}")
        except Exception as e:
            print(f"检测数据库ID类型时出错: {str(e)}")
    
    def _convert_id_for_query(self, id_value):
        """
        根据数据库中的ID类型转换ID
        
        参数:
        id_value: 要转换的ID值
        
        返回:
        转换后的ID值，适合数据库查询
        """
        if id_value is None:
            return None
            
        # 如果已知数据库使用字符串类型
        if self.db_id_type == "string":
            return str(id_value)
        # 如果已知数据库使用ObjectId类型
        elif self.db_id_type == "objectid":
            try:
                if isinstance(id_value, ObjectId):
                    return id_value
                else:
                    return ObjectId(str(id_value))
            except:
                print(f"无法将ID '{id_value}' 转换为ObjectId，使用原始值")
                return id_value
        # 如果类型未知，返回多种类型
        else:
            try:
                if isinstance(id_value, ObjectId):
                    return id_value
                else:
                    # 尝试转换为ObjectId
                    try:
                        return ObjectId(str(id_value))
                    except:
                        # 否则返回字符串
                        return str(id_value)
            except:
                return str(id_value)
    
    def _run(self, requirements: List[Dict[str, Any]], limit_per_requirement: int = 25) -> dict:
        """
        根据视频需求搜索匹配的素材，使用向量搜索
        
        参数:
        requirements: 视频需求列表，每个需求包含场景类型、视觉元素等
        limit_per_requirement: 每个需求返回的最大素材数量
        
        返回:
        匹配的素材列表
        """
        # 打印调试信息
        print("="*50)
        print(f"调用MaterialSearchTool.run方法搜索素材")
        
        # 确保 requirements 是列表类型
        if not isinstance(requirements, list):
            print("收到单个需求对象，转换为列表")
            requirements = [requirements]
            
        print(f"收到 {len(requirements)} 个需求项")
        print(f"每个需求返回最多 {limit_per_requirement} 个素材")
        print("="*50)
        
        results = []
        
        for i, requirement in enumerate(requirements):
            print(f"搜索需求 {i+1}: {requirement.get('description', '未提供描述')}")
            
            # 构建需求描述文本
            requirement_text = self._build_requirement_text(requirement)
            print(f"生成的需求描述文本: {requirement_text}")
            
            # 获取需求的向量表示
            try:
                requirement_vector = self.embedding_service.get_embedding(requirement_text)
                print(f"成功获取需求向量，维度: {len(requirement_vector)}")
            except Exception as e:
                print(f"获取需求向量时出错: {str(e)}，将使用文本搜索作为备选")
                requirement_vector = None
            
            # 基于品牌的预过滤条件
            pre_filter = {}
            if "brand" in requirement and requirement["brand"]:
                pre_filter["metadata.brand"] = {"$regex": requirement["brand"], "$options": "i"}
                print(f"添加品牌过滤条件: {requirement['brand']}")
            
            # 候选片段列表
            candidate_segments = []
            
            # 执行向量搜索 - 先搜索视频集合
            if requirement_vector is not None:
                try:
                    matching_videos = self.vector_search_service.search_similar_vectors(
                        query_vector=requirement_vector,
                        limit=2, # 限制为少数候选视频
                        collection_name='videos',
                        vector_field='embeddings.fusion_vector', # 修改为新的向量字段路径
                        pre_filter=pre_filter
                    )
                    print(f"向量搜索完成，找到 {len(matching_videos)} 个匹配的视频")
                    
                    # 提取视频ID列表
                    video_ids = []
                    for video in matching_videos:
                        if "_id" in video:
                            try:
                                # 转换ID，适应数据库中的类型
                                converted_id = self._convert_id_for_query(video["_id"])
                                video_ids.append(converted_id)
                                print(f"添加转换后的video_id: {type(converted_id).__name__}类型, 值={converted_id}")
                            except Exception as e:
                                print(f"转换video_id时出错: {str(e)}")
                                # 尝试添加字符串形式作为后备
                                try:
                                    video_ids.append(str(video["_id"]))
                                    print(f"无法转换ID，使用字符串形式: {str(video['_id'])}")
                                except:
                                    pass
                    
                    # 查询这些视频的所有片段
                    if video_ids:
                        try:
                            # 构建查询条件
                            query = {"video_id": {"$in": video_ids}}
                            print(f"使用查询: video_id $in [{video_ids[0]}, ...] (共{len(video_ids)}个ID)")
                            
                            # 执行查询
                            segments = list(self.mongodb_service.db.video_segments.find(
                                query,
                                {
                                    "_id": 1, "video_id": 1, "start_time": 1, "end_time": 1,
                                    "shot_type": 1, "shot_description": 1, "duration": 1,
                                    "emotional_tags": 1, "feature_tags": 1, "visual_elements": 1,
                                    "cinematic_language": 1, "searchable_text": 1
                                }
                            ).limit(50))  # 每个需求最多获取50个候选片段
                            
                            print(f"查询得到 {len(segments)} 个片段")
                        except Exception as e:
                            print(f"查询video_segments时出错: {str(e)}")
                            segments = []
                        
                        # 为每个片段增加视频信息
                        for segment in segments:
                            # 提取片段的video_id，无论是字符串还是ObjectId
                            segment_video_id = segment.get("video_id", "")
                            segment_video_id_str = str(segment_video_id)
                            
                            # 匹配对应的视频信息
                            video_info = None
                            for video in matching_videos:
                                video_id = video.get("_id", "")
                                video_id_str = str(video_id)
                                
                                # 比较字符串形式的ID
                                if video_id_str == segment_video_id_str:
                                    video_info = video
                                    print(f"匹配到视频: segment_id={segment.get('_id', '')}, video_id={video_id_str}")
                                    break
                            
                            if video_info:
                                segment["video_title"] = video_info.get("title", "未知视频")
                                segment["video_brand"] = video_info.get("metadata", {}).get("brand", "")
                                segment["video_type"] = video_info.get("metadata", {}).get("video_type", "")
                                segment["video_path"] = video_info.get("file_info", {}).get("path", "")
                                segment["vector_score"] = video_info.get("vector_score", 0)
                            else:
                                print(f"警告: 未找到匹配视频信息: segment_id={segment.get('_id', '')}, video_id={segment_video_id_str}")
                                # 添加基本信息以避免后续处理出错
                                segment["video_title"] = "未知视频"
                                segment["video_brand"] = ""
                                segment["video_type"] = ""
                                segment["video_path"] = f"unknown_video_{segment_video_id_str}.mp4"
                                segment["vector_score"] = 0.1
                            
                            candidate_segments.append(segment)
                
                except Exception as e:
                    print(f"执行向量搜索时出错: {str(e)}")
            
            # 如果没有候选片段，使用文本搜索作为备选
            if not candidate_segments:
                print("没有找到匹配的片段，使用文本搜索作为备选...")
                try:
                    text_results = self.mongodb_service.text_search(requirement_text, 20)
                    print(f"文本搜索找到 {len(text_results)} 个结果")
                    
                    for segment in text_results:
                        try:
                            # 提取片段的video_id，无论是字符串还是ObjectId
                            segment_video_id = segment.get("video_id", "")
                            segment_video_id_str = str(segment_video_id)
                            
                            # 转换ID以适应数据库查询
                            query_id = self._convert_id_for_query(segment_video_id)
                            
                            # 查询视频信息
                            video = self.mongodb_service.db.videos.find_one({"_id": query_id})
                            
                            if video:
                                print(f"文本搜索: 使用转换后的ID({type(query_id).__name__})匹配到视频: {query_id}")
                                segment["video_title"] = video.get("title", "未知视频")
                                segment["video_brand"] = video.get("metadata", {}).get("brand", "")
                                segment["video_type"] = video.get("metadata", {}).get("video_type", "")
                                segment["video_path"] = video.get("file_info", {}).get("path", "")
                                segment["vector_score"] = 0.5  # 默认分数
                            else:
                                print(f"警告: 文本搜索未找到匹配视频: segment_id={segment.get('_id', '')}, video_id={segment_video_id_str}")
                                # 添加基本信息以避免后续处理出错
                                segment["video_title"] = "未知视频"
                                segment["video_brand"] = ""
                                segment["video_type"] = ""
                                segment["video_path"] = f"unknown_video_{segment_video_id_str}.mp4"
                                segment["vector_score"] = 0.3
                            
                            candidate_segments.append(segment)
                        except Exception as e:
                            print(f"处理文本搜索结果时出错: {str(e)}")
                except Exception as e:
                    print(f"文本搜索出错: {str(e)}")
            
            # 如果向量搜索和文本搜索都失败，尝试直接查询视频片段
            if not candidate_segments:
                print("尝试直接查询视频片段...")
                try:
                    # 构建基本查询条件
                    query = {}
                    
                    # 添加场景类型过滤（如果有）
                    if "scene_type" in requirement:
                        query["shot_type"] = {"$regex": requirement["scene_type"], "$options": "i"}
                    
                    # 添加情感过滤（如果有）
                    if "emotion" in requirement:
                        query["emotional_tags"] = {"$regex": requirement["emotion"], "$options": "i"}
                    
                    # 限制返回数量
                    segments = list(self.mongodb_service.db.video_segments.find(query).limit(20))
                    print(f"直接查询找到 {len(segments)} 个片段")
                    
                    # 为片段添加视频信息
                    for segment in segments:
                        try:
                            # 提取片段的video_id，无论是字符串还是ObjectId
                            segment_video_id = segment.get("video_id", "")
                            segment_video_id_str = str(segment_video_id)
                            
                            # 转换ID以适应数据库查询
                            query_id = self._convert_id_for_query(segment_video_id)
                            
                            # 查询视频信息
                            video = self.mongodb_service.db.videos.find_one({"_id": query_id})
                            
                            if video:
                                print(f"直接查询: 使用转换后的ID({type(query_id).__name__})匹配到视频: {query_id}")
                                segment["video_title"] = video.get("title", "未知视频")
                                segment["video_brand"] = video.get("metadata", {}).get("brand", "")
                                segment["video_type"] = video.get("metadata", {}).get("video_type", "")
                                segment["video_path"] = video.get("file_info", {}).get("path", "")
                                segment["vector_score"] = 0.3  # 直接查询结果分数较低
                            else:
                                print(f"警告: 直接查询未找到匹配视频: segment_id={segment.get('_id', '')}, video_id={segment_video_id_str}")
                                # 添加基本信息以避免后续处理出错
                                segment["video_title"] = "未知视频"
                                segment["video_brand"] = ""
                                segment["video_type"] = ""
                                segment["video_path"] = f"unknown_video_{segment_video_id_str}.mp4"
                                segment["vector_score"] = 0.2
                            
                            candidate_segments.append(segment)
                        except Exception as e:
                            print(f"处理直接查询结果时出错: {str(e)}")
                except Exception as e:
                    print(f"直接查询出错: {str(e)}")
                
            # 如果数据库查询失败，返回示例素材（仅用于调试）
            if not candidate_segments and os.environ.get('ENABLE_MOCK_DATA', 'false').lower() == 'true':
                print("使用示例数据作为最后的备选...")
                for i in range(3):
                    candidate_segments.append({
                        "_id": f"mock_segment_{i}",
                        "video_id": f"mock_video_{i}",
                        "video_title": f"示例视频 {i}",
                        "video_brand": "示例品牌",
                        "video_path": f"/path/to/example/video_{i}.mp4",
                        "start_time": 0,
                        "end_time": 10,
                        "duration": 10,
                        "shot_type": requirement.get("scene_type", "未知"),
                        "shot_description": f"示例场景描述 {i}",
                        "vector_score": 0.1  # 示例数据分数最低
                    })
            
            # 使用Agent进行智能匹配
            matched_segments = self._match_segments_by_agent(requirement, candidate_segments, limit_per_requirement)
            
            # 构建结果
            result_videos = self._format_matched_results(matched_segments)
            results.append({
                "requirement": requirement,
                "matching_videos": result_videos
            })
            
            print(f"找到 {len(result_videos)} 个匹配的视频")
            
            # 如果没有找到匹配的视频，添加一个明确的消息
            if not result_videos:
                print("警告: 未找到匹配的视频素材")
        
        print("素材搜索完成，返回结果")
        final_result = {
            "requirements_count": len(requirements),
            "results": results
        }
        
        # 打印每个需求的匹配结果计数，便于调试
        print("\n" + "="*50)
        print("搜索结果摘要:")
        for i, result in enumerate(results):
            req_desc = result["requirement"].get("description", "未提供描述")
            if len(req_desc) > 50:
                req_desc = req_desc[:50] + "..."
            videos_count = len(result["matching_videos"])
            print(f"需求 {i+1}: {videos_count} 个匹配视频 - {req_desc}")
        print("="*50 + "\n")
        
        return final_result
        
    def _build_requirement_text(self, requirement: Dict[str, Any]) -> str:
        """构建需求描述文本"""
        requirement_text = ""
        
        if "description" in requirement:
            requirement_text += requirement["description"] + " "
        
        if "text" in requirement:
            requirement_text += requirement["text"] + " "
            
        if "scene_type" in requirement:
            requirement_text += f"场景类型: {requirement['scene_type']} "
        
        if "emotion" in requirement:
            requirement_text += f"情绪: {requirement['emotion']} "
        
        if "visual_elements" in requirement:
            elements = requirement["visual_elements"]
            if isinstance(elements, list):
                requirement_text += f"视觉元素: {', '.join(elements)} "
            else:
                requirement_text += f"视觉元素: {elements} "
        
        if "keywords" in requirement:
            keywords = requirement["keywords"]
            if isinstance(keywords, list):
                requirement_text += f"关键词: {', '.join(keywords)} "
            else:
                requirement_text += f"关键词: {keywords} "
                
        return requirement_text
        
    def _match_segments_by_agent(self, requirement: Dict[str, Any], candidate_segments: List[Dict[str, Any]], 
                                limit: int = 5) -> List[Dict[str, Any]]:
        """使用Agent匹配最合适的片段"""
        # 如果没有候选片段，返回空列表
        if not candidate_segments:
            print("_match_segments_by_agent: 没有候选片段，返回空列表")
            return []
        
        # 添加调试信息
        print(f"_match_segments_by_agent: 开始处理 {len(candidate_segments)} 个候选片段")
        
        # 如果候选片段数量不超过限制，直接返回所有片段
        if len(candidate_segments) <= limit:
            print(f"_match_segments_by_agent: 候选片段数量({len(candidate_segments)})不超过限制({limit})，直接返回所有片段")
            return candidate_segments
        
        try:
            # 准备提供给Agent的上下文
            segments_context = []
            for idx, segment in enumerate(candidate_segments):
                # 简化片段信息，避免上下文过长
                simplified_segment = {
                    "index": idx + 1,  # 提供索引供Agent引用
                    "video_title": segment.get("video_title", "未知视频"),
                    "video_brand": segment.get("video_brand", ""),
                    "video_path": segment.get("video_path", ""),
                    "segment_id": str(segment.get("_id", "")),
                    "video_id": str(segment.get("video_id", "")),
                    "start_time": segment.get("start_time", 0),
                    "end_time": segment.get("end_time", 0),
                    "duration": segment.get("duration", 0),
                    "shot_type": segment.get("shot_type", ""),
                    "shot_description": segment.get("shot_description", ""),
                    "similarity_score": segment.get("vector_score", 0)
                }
                
                # 添加情感标签
                if "emotional_tags" in segment:
                    tags = segment["emotional_tags"]
                    if isinstance(tags, list) and tags:
                        simplified_segment["emotional_tags"] = ", ".join(tags)
                    elif isinstance(tags, str):
                        simplified_segment["emotional_tags"] = tags
                
                # 添加特征标签
                if "feature_tags" in segment:
                    tags = segment["feature_tags"]
                    if isinstance(tags, list) and tags:
                        simplified_segment["feature_tags"] = ", ".join(tags)
                    elif isinstance(tags, str):
                        simplified_segment["feature_tags"] = tags
                
                # 添加视觉元素
                if "visual_elements" in segment:
                    visual_elements = segment["visual_elements"]
                    simplified_segment["visual_elements"] = self._simplify_visual_elements(visual_elements)
                
                segments_context.append(simplified_segment)
            
            # 根据相似度分数进行初步排序
            segments_sorted = sorted(segments_context, key=lambda x: x.get("similarity_score", 0), reverse=True)
            
            # 取前limit个作为结果
            selected_segments = segments_sorted[:limit]
            print(f"_match_segments_by_agent: 按相似度排序，返回前 {len(selected_segments)} 个结果")
            
            # 找回原始片段对象
            results = []
            for selected in selected_segments:
                idx = selected.get("index", 0) - 1
                if 0 <= idx < len(candidate_segments):
                    # 添加匹配原因
                    match_reason = f"相似度分数: {selected.get('similarity_score', 0):.2f}, 镜头类型: {selected.get('shot_type', '')}"
                    candidate_segments[idx]["match_reason"] = match_reason
                    results.append(candidate_segments[idx])
            
            return results
            
        except Exception as e:
            print(f"_match_segments_by_agent 出错: {str(e)}")
            # 发生错误时，返回按相似度排序的前limit个结果
            sorted_segments = sorted(candidate_segments, 
                                    key=lambda x: x.get("vector_score", 0), 
                                    reverse=True)
            return sorted_segments[:limit]
    
    def _format_matched_results(self, matched_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化匹配结果，确保返回一致的结构"""
        formatted_results = []
        
        for segment in matched_segments:
            # 复制基本信息
            formatted_segment = {
                "segment_id": str(segment.get("_id", "")),
                "video_id": str(segment.get("video_id", "")),
                "video_title": segment.get("video_title", "未知视频"),
                "video_path": segment.get("video_path", ""),
                "start_time": segment.get("start_time", 0),
                "end_time": segment.get("end_time", 0),
                "duration": segment.get("duration", 0),
                "shot_type": segment.get("shot_type", ""),
                "shot_description": segment.get("shot_description", ""),
                "match_reason": segment.get("match_reason", "")
            }
            
            # 提取并添加情感标签
            if "emotional_tags" in segment:
                if isinstance(segment["emotional_tags"], list):
                    formatted_segment["emotional_tags"] = segment["emotional_tags"]
                elif isinstance(segment["emotional_tags"], str):
                    formatted_segment["emotional_tags"] = [tag.strip() for tag in segment["emotional_tags"].split(",")]
                else:
                    formatted_segment["emotional_tags"] = []
            else:
                formatted_segment["emotional_tags"] = []
            
            # 添加视觉元素
            if "visual_elements" in segment:
                formatted_segment["visual_elements"] = segment["visual_elements"]
            
            formatted_results.append(formatted_segment)
        
        return formatted_results
    
    def _simplify_visual_elements(self, visual_elements: Any) -> Any:
        """处理不同类型的视觉元素数据，返回简化后的表示"""
        if isinstance(visual_elements, dict):
            # 返回字典的简化版本
            return {
                "main_subject": visual_elements.get("main_subject", ""),
                "background": visual_elements.get("background", ""),
                "lighting": visual_elements.get("lighting", ""),
                "color": visual_elements.get("color", ""),
                "emotion": visual_elements.get("emotion", "")
            }
        elif isinstance(visual_elements, str):
            return visual_elements
        elif isinstance(visual_elements, list):
            return ", ".join(visual_elements)
        else:
            return str(visual_elements)

class ScriptToVideoTool(BaseTool):
    name: str = "ScriptToVideo"
    description: str = "根据脚本找到匹配的视频素材"
    args_schema: Type[BaseModel] = ScriptToVideoInput
    material_matching_service: MaterialMatchingService = None
    mongodb_service: MongoDBService = None
    
    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self):
        super().__init__()
        self.material_matching_service = MaterialMatchingService()
        self.mongodb_service = MongoDBService()
    
    def _run(self, script: str, brand: str = None) -> dict:
        """
        根据脚本找到匹配的视频素材
        
        参数:
        script: 脚本文本
        brand: 可选的品牌名称过滤
        
        返回:
        匹配的素材列表
        """
        try:
            print(f"处理脚本匹配请求，脚本长度: {len(script)} 字符")
            if brand:
                print(f"品牌过滤: {brand}")
            
            # 分析脚本
            script_analysis = self.material_matching_service.analyze_script(script)
            
            # 获取视频片段信息作为上下文
            segments_context = self._get_video_segments_context(script_analysis, brand)
            
            # 使用Agent进行智能匹配
            match_results = self._match_by_agent(script_analysis, segments_context)
            
            # 简化结果中的向量数据
            self._simplify_vector_data(match_results)
            
            return match_results
            
        except Exception as e:
            error_message = f"脚本到视频匹配出错: {str(e)}"
            print(error_message)
            return {
                "error": error_message,
                "success": False
            }
    
    def _get_video_segments_context(self, script_analysis: Dict[str, Any], brand: str = None) -> Dict[str, List[Dict[str, Any]]]:
        """获取视频片段上下文信息"""
        # 初始化结果
        segments_by_scene = {}
        
        try:
            # 获取场景列表
            scenes = script_analysis.get("scenes", [])
            
            # 为每个场景获取候选片段
            for scene in scenes:
                scene_id = scene.get("id", "")
                if not scene_id:
                    continue
                    
                # 构建基础过滤条件
                filters = {}
                if brand:
                    # 先获取符合品牌的视频ID
                    brand_videos = list(self.mongodb_service.db.videos.find(
                        {"metadata.brand": {"$regex": brand, "$options": "i"}},
                        {"_id": 1}
                    ))
                    brand_video_ids = [v["_id"] for v in brand_videos]
                    if brand_video_ids:
                        filters["video_id"] = {"$in": brand_video_ids}
                
                # 尝试使用向量搜索
                candidate_segments = []
                
                # 如果场景有向量表示且向量搜索可用，使用向量搜索
                if "vector" in scene and scene["vector"] and hasattr(self.material_matching_service, "vector_search_service"):
                    try:
                        candidates = self.material_matching_service.vector_search_service.search_similar_vectors(
                            query_vector=scene["vector"],
                            collection_name="video_segments",
                            vector_field="embeddings.fusion_vector",
                            pre_filter=filters,
                            limit=20  # 每个场景获取20个候选
                        )
                        candidate_segments.extend(candidates)
                    except Exception as e:
                        print(f"场景 {scene_id} 向量搜索出错: {str(e)}")
                
                # 如果向量搜索无结果或出错，使用文本搜索
                if not candidate_segments:
                    description = scene.get("description", "")
                    shot_type = scene.get("shot_type_preference", "")
                    emotion = scene.get("emotion", "")
                    
                    # 构建搜索文本
                    search_text = f"{description} {shot_type} {emotion}"
                    
                    # 使用文本搜索
                    text_results = self.mongodb_service.text_search(search_text, 20)
                    
                    # 应用过滤器
                    if filters and "video_id" in filters:
                        text_results = [r for r in text_results if r.get("video_id") in filters["video_id"]]
                    
                    candidate_segments.extend(text_results)
                
                # 为每个候选添加视频信息
                enriched_segments = []
                for segment in candidate_segments:
                    video_id = segment.get("video_id")
                    if video_id:
                        video = self.mongodb_service.db.videos.find_one({"_id": video_id})
                        if video:
                            segment_copy = dict(segment)
                            segment_copy["video_title"] = video.get("title", "未知视频")
                            segment_copy["video_brand"] = video.get("metadata", {}).get("brand", "")
                            segment_copy["video_path"] = video.get("file_info", {}).get("path", "")
                            enriched_segments.append(segment_copy)
                
                # 存储该场景的候选片段
                segments_by_scene[scene_id] = enriched_segments
            
            return segments_by_scene
            
        except Exception as e:
            print(f"获取视频片段上下文时出错: {str(e)}")
            return {}
    
    def _match_by_agent(self, script_analysis: Dict[str, Any], 
                      segments_context: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """使用Agent进行智能匹配"""
        try:
            # 提取脚本信息
            title = script_analysis.get("title", "未命名脚本")
            brand = script_analysis.get("brand", "")
            scenes = script_analysis.get("scenes", [])
            
            # 准备结果结构
            shotlist = {
                "title": title,
                "brand": brand,
                "tonality": script_analysis.get("tonality", ""),
                "pace": script_analysis.get("pace", ""),
                "total_scenes": len(scenes),
                "scenes": []
            }
            
            # 总时长计数
            total_duration = 0
            
            # 为每个场景选择最佳匹配
            for i, scene in enumerate(scenes):
                scene_id = scene.get("id", "")
                scene_number = i + 1
                
                # 获取该场景的候选片段
                candidates = segments_context.get(scene_id, [])
                if not candidates:
                    # 无候选片段，添加占位信息
                    shotlist["scenes"].append({
                        "scene_number": scene_number,
                        "scene_id": scene_id,
                        "scene_description": scene.get("description", ""),
                        "status": "未找到匹配片段",
                        "requirements": {
                            "shot_type": scene.get("shot_type_preference", ""),
                            "emotion": scene.get("emotion", ""),
                            "key_elements": scene.get("key_elements", [])
                        }
                    })
                    continue
                
                # 简化候选片段信息，避免上下文太长
                simplified_candidates = []
                for idx, segment in enumerate(candidates):
                    simplified_segment = {
                        "index": idx + 1,
                        "video_title": segment.get("video_title", "未知视频"),
                        "video_brand": segment.get("video_brand", ""),
                        "video_path": segment.get("video_path", ""),
                        "segment_id": str(segment.get("_id", "")),
                        "start_time": segment.get("start_time", 0),
                        "end_time": segment.get("end_time", 0),
                        "duration": segment.get("duration", 0),
                        "shot_type": segment.get("shot_type", ""),
                        "description": segment.get("shot_description", "")
                    }
                    
                    # 添加情感和视觉元素（如果有）
                    if "emotional_tags" in segment:
                        simplified_segment["emotional_tags"] = segment["emotional_tags"]
                    if "visual_elements" in segment:
                        simplified_segment["visual_elements"] = self._simplify_visual_elements(segment["visual_elements"])
                    
                    simplified_candidates.append(simplified_segment)
                
                # 构建Agent提示
                prompt = f"""
作为视频剪辑专家，你需要从候选片段中为场景"{scene.get('description', '')}"选择最佳匹配片段。

场景要求:
- 描述: {scene.get('description', '无描述')}
- 镜头类型: {scene.get('shot_type_preference', '无镜头类型偏好')}
- 情感基调: {scene.get('emotion', '无情感基调')}
- 关键元素: {', '.join(scene.get('key_elements', []))}
- 功能: {scene.get('function', '无指定功能')}

候选片段信息:
{json.dumps(simplified_candidates[:10], ensure_ascii=False, indent=2)}

{f"注：候选片段共{len(simplified_candidates)}个，已显示前10个。" if len(simplified_candidates) > 10 else ""}

请选择1个最佳匹配的片段，以及最多2个备选片段。对于每个选择，请说明选择理由。

返回格式:
{{
  "selections": [
    {{
      "index": 候选片段的索引,
      "reason": "选择理由..."
    }}
  ]
}}
"""
                
                # 调用LLM获取匹配结果
                try:
                    match_response = self._call_llm_for_scene_matching(prompt)
                    selected_indices = self._extract_selected_indices(match_response)
                    
                    # 获取选择的片段
                    selected_segments = []
                    for idx in selected_indices:
                        if 0 <= idx < len(candidates):
                            selected_segments.append(candidates[idx])
                    
                    if selected_segments:
                        # 获取最佳匹配（第一个）
                        best_match = selected_segments[0]
                        alternatives = selected_segments[1:3] if len(selected_segments) > 1 else []
                        
                        # 获取选择理由
                        match_reason = self._extract_match_reason(match_response, 0)
                        
                        # 计算片段时长
                        clip_duration = best_match.get("duration", 0)
                        if not clip_duration and "start_time" in best_match and "end_time" in best_match:
                            clip_duration = best_match["end_time"] - best_match["start_time"]
                        
                        total_duration += clip_duration
                        
                        # 添加到分镜表
                        scene_entry = {
                            "scene_number": scene_number,
                            "scene_id": scene_id,
                            "scene_description": scene.get("description", ""),
                            "selected_clip": {
                                "video_id": str(best_match.get("video_id", "")),
                                "segment_id": str(best_match.get("_id", "")),
                                "start_time": best_match.get("start_time", 0),
                                "end_time": best_match.get("end_time", 0),
                                "duration": clip_duration,
                                "shot_type": best_match.get("shot_type", ""),
                                "shot_description": best_match.get("shot_description", ""),
                                "match_reason": match_reason
                            },
                            "alternatives": []
                        }
                        
                        # 添加备选片段
                        for i, alt in enumerate(alternatives):
                            alt_duration = alt.get("duration", 0)
                            if not alt_duration and "start_time" in alt and "end_time" in alt:
                                alt_duration = alt["end_time"] - alt["start_time"]
                                
                            alt_reason = self._extract_match_reason(match_response, i+1)
                                
                            scene_entry["alternatives"].append({
                                "video_id": str(alt.get("video_id", "")),
                                "segment_id": str(alt.get("_id", "")),
                                "start_time": alt.get("start_time", 0),
                                "end_time": alt.get("end_time", 0),
                                "duration": alt_duration,
                                "shot_type": alt.get("shot_type", ""),
                                "match_reason": alt_reason
                            })
                        
                        shotlist["scenes"].append(scene_entry)
                    else:
                        # 未能选择匹配片段
                        shotlist["scenes"].append({
                            "scene_number": scene_number,
                            "scene_id": scene_id,
                            "scene_description": scene.get("description", ""),
                            "status": "未能选择匹配片段",
                            "requirements": {
                                "shot_type": scene.get("shot_type_preference", ""),
                                "emotion": scene.get("emotion", ""),
                                "key_elements": scene.get("key_elements", [])
                            }
                        })
                except Exception as e:
                    print(f"场景 {scene_id} 的LLM匹配出错: {str(e)}")
                    # 出错时使用简单方法选择
                    self._fallback_scene_matching(scene, candidates, shotlist, scene_number)
            
            # 添加总时长
            shotlist["total_duration"] = round(total_duration, 1)
            
            # 构建完整结果
            return {
                "script_analysis": script_analysis,
                "shotlist": shotlist,
                "process_info": {
                    "scenes_count": len(scenes),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            }
        
        except Exception as e:
            print(f"Agent匹配过程出错: {str(e)}")
            return {
                "error": f"匹配过程出错: {str(e)}",
                "script_analysis": script_analysis,
                "shotlist": {"scenes": [], "total_scenes": 0}
            }
    
    def _call_llm_for_scene_matching(self, prompt: str) -> Dict[str, Any]:
        """调用LLM进行场景匹配"""
        try:
            response = openai.chat.completions.create(
                model="gemini-1.5-pro",
                messages=[
                    {"role": "system", "content": "你是一位专业的视频剪辑师，擅长为场景选择最合适的视频片段。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # 解析响应
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            print(f"调用LLM进行场景匹配时出错: {str(e)}")
            # 返回空结果
            return {"selections": []}
    
    def _extract_selected_indices(self, response: Dict[str, Any]) -> List[int]:
        """从LLM响应中提取选择的索引"""
        try:
            if "selections" in response and isinstance(response["selections"], list):
                indices = []
                for selection in response["selections"]:
                    if "index" in selection:
                        # 转为0-based索引
                        idx = int(selection["index"]) - 1
                        indices.append(idx)
                return indices
            elif "selected_indices" in response:
                # 转为0-based索引
                return [int(idx) - 1 for idx in response["selected_indices"]]
            else:
                # 尝试从其他字段中提取
                for key, value in response.items():
                    if isinstance(value, list) and all(isinstance(item, int) or 
                                                     (isinstance(item, dict) and "index" in item)
                                                     for item in value):
                        if all(isinstance(item, int) for item in value):
                            return [int(idx) - 1 for idx in value]
                        else:
                            return [int(item["index"]) - 1 for item in value if "index" in item]
            
            return []
        except Exception as e:
            print(f"提取索引时出错: {str(e)}")
            return []
    
    def _extract_match_reason(self, response: Dict[str, Any], index: int) -> str:
        """从匹配结果中提取选择理由"""
        try:
            if "selections" in response and isinstance(response["selections"], list):
                if 0 <= index < len(response["selections"]):
                    selection = response["selections"][index]
                    if "reason" in selection:
                        return selection["reason"]
            elif "reasons" in response and isinstance(response["reasons"], list):
                if 0 <= index < len(response["reasons"]):
                    return response["reasons"][index]
            
            return "最佳匹配" if index == 0 else "备选匹配"
        except Exception:
            return "最佳匹配" if index == 0 else "备选匹配"
    
    def _fallback_scene_matching(self, scene: Dict[str, Any], candidates: List[Dict[str, Any]], 
                              shotlist: Dict[str, Any], scene_number: int) -> None:
        """备用匹配方法，当LLM匹配失败时使用"""
        if not candidates:
            return
            
        # 按相似度分数排序
        sorted_candidates = sorted(candidates, key=lambda x: x.get("vector_score", 0), reverse=True)
        
        # 选择排名最高的片段
        best_match = sorted_candidates[0]
        alternatives = sorted_candidates[1:3] if len(sorted_candidates) > 1 else []
        
        # 计算片段时长
        clip_duration = best_match.get("duration", 0)
        if not clip_duration and "start_time" in best_match and "end_time" in best_match:
            clip_duration = best_match["end_time"] - best_match["start_time"]
        
        # 添加到分镜表
        scene_entry = {
            "scene_number": scene_number,
            "scene_id": scene.get("id", f"场景{scene_number}"),
            "scene_description": scene.get("description", ""),
            "selected_clip": {
                "video_id": str(best_match.get("video_id", "")),
                "segment_id": str(best_match.get("_id", "")),
                "start_time": best_match.get("start_time", 0),
                "end_time": best_match.get("end_time", 0),
                "duration": clip_duration,
                "shot_type": best_match.get("shot_type", ""),
                "shot_description": best_match.get("shot_description", ""),
                "match_reason": "基于向量相似度自动选择"
            },
            "alternatives": []
        }
        
        # 添加备选片段
        for alt in alternatives:
            alt_duration = alt.get("duration", 0)
            if not alt_duration and "start_time" in alt and "end_time" in alt:
                alt_duration = alt["end_time"] - alt["start_time"]
                
            scene_entry["alternatives"].append({
                "video_id": str(alt.get("video_id", "")),
                "segment_id": str(alt.get("_id", "")),
                "start_time": alt.get("start_time", 0),
                "end_time": alt.get("end_time", 0),
                "duration": alt_duration,
                "shot_type": alt.get("shot_type", ""),
                "match_reason": "备选匹配"
            })
        
        shotlist["scenes"].append(scene_entry)
    
    def _simplify_vector_data(self, result: Dict[str, Any]) -> None:
        """简化结果中的向量数据以减小响应大小"""
        if "script_analysis" in result:
            script_analysis = result["script_analysis"]
            scenes = script_analysis.get("scenes", [])
            for scene in scenes:
                if "vector" in scene:
                    # 移除向量数据，只保留向量大小信息
                    vector_length = len(scene["vector"]) if isinstance(scene["vector"], list) else 0
                    scene["vector"] = f"[向量数据，维度: {vector_length}]"
        
        if "shotlist" in result:
            shotlist = result["shotlist"]
            scenes = shotlist.get("scenes", [])
            for scene in scenes:
                if "selected_clip" in scene:
                    clip = scene["selected_clip"]
                    if "embeddings" in clip:
                        clip["embeddings"] = "[嵌入向量数据已省略]"
                
                if "alternatives" in scene:
                    for alt in scene["alternatives"]:
                        if "embeddings" in alt:
                            alt["embeddings"] = "[嵌入向量数据已省略]"
    
    def _simplify_visual_elements(self, visual_elements: Any) -> Any:
        """简化视觉元素信息，处理各种类型"""
        if not visual_elements:
            return {}
            
        if isinstance(visual_elements, dict):
            return {
                "main_subject": visual_elements.get("main_subject", ""),
                "background": visual_elements.get("background", ""),
                "lighting": visual_elements.get("lighting", ""),
                "color": visual_elements.get("color", ""),
                "emotion": visual_elements.get("emotion", "")
            }
        elif isinstance(visual_elements, str):
            return visual_elements
        elif isinstance(visual_elements, list):
            return ", ".join(visual_elements)
        else:
            return str(visual_elements)

class MaterialSearchAgent:
    @staticmethod
    def create():
        """创建素材搜索 Agent"""
        # 创建工具实例
        material_search_tool = MaterialSearchTool()
        text_matching_tool = TextMatchingTool()
        script_to_video_tool = ScriptToVideoTool()  # 添加脚本到视频匹配工具
        
        # 创建 Agent
        material_search_agent = Agent(
            role="视频素材搜索与脚本匹配专家",
            goal="准确理解需求并使用MaterialSearch工具搜索匹配的视频素材，为每个需求找到最合适的视频片段",
            backstory="""你是一名资深的视频素材搜索与脚本匹配专家，擅长根据需求和脚本查找最合适的视频素材。
            你熟悉各种视频类型和内容标签，能够精确匹配视觉元素和场景类型。
            你擅长分析脚本，理解每个场景的核心需求和情感基调，并为其找到最匹配的视频片段。
            你会考虑场景类型、视觉元素、情绪基调、功能需求等多维度因素，确保找到的素材能够准确表达脚本的内容和情感。
            
            你有以下专业技能：
            1. 基于简单需求描述的素材搜索，适合单个场景或元素的匹配
            2. 基于完整脚本的多场景素材匹配，适合构建完整的视频故事板
            
            重要提示：当使用MaterialSearch工具时，你需要注意以下几点：
            1. requirements参数必须传递完整的需求列表，而不是单个需求对象
            2. 只需调用一次MaterialSearch工具，传入完整的需求列表，工具会自动处理所有需求
            3. 请按照以下格式调用工具：MaterialSearch(requirements=需求列表)
            4. 可以根据需要设置limit_per_requirement参数，默认为5
            """,
            verbose=True,
            allow_delegation=False,
            tools=[material_search_tool, text_matching_tool, script_to_video_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            )
        )
        
        return material_search_agent 