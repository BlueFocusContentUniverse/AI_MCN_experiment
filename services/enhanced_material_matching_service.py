import os
import json
import logging
from typing import Dict, Any, List, Optional, Union, Tuple
import time
import re
import copy

from bson import ObjectId
import numpy as np

from services.mongodb_service import MongoDBService
from services.embedding_service import EmbeddingService
from services.vector_search_service import VectorSearchService
from services.material_matching_service import MaterialMatchingService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedMaterialMatchingService:
    """增强的素材匹配服务，支持多策略搜索和基于IR的精细匹配"""
    
    def __init__(self):
        """初始化增强的素材匹配服务"""
        self.mongodb_service = MongoDBService()
        self.embedding_service = EmbeddingService()
        self.vector_search_service = VectorSearchService(self.mongodb_service)
        self.material_matching_service = MaterialMatchingService()  # 使用现有服务作为基础
        
        # 初始化缓存
        self._library_summary = None
        self._library_stats = None
        self._summary_timestamp = None
        
        logger.info("已初始化 MongoDB, Embedding, 和 Vector Search 服务")
        
    def _get_search_strategy(self, segment_requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        安全获取搜索策略，处理可能的字符串类型
        
        参数:
        segment_requirement: 视频片段需求
        
        返回:
        处理后的搜索策略字典
        """
        search_strategy = segment_requirement.get("material_search_strategy", {})
        
        # 检查search_strategy是否为字符串，如果是则转换为字典
        if isinstance(search_strategy, str):
            logger.warning(f"material_search_strategy是字符串而不是字典: '{search_strategy}'。将使用默认字典并设置search_type={search_strategy}")
            search_type = search_strategy  # 保存字符串值作为搜索类型
            search_strategy = {"search_type": search_type}  # 创建一个包含该值的字典
        
        return search_strategy

    def search_materials_for_segment(self, segment_requirement: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        为视频片段搜索匹配的素材
        
        参数:
        segment_requirement: IR中的视频片段需求，包含material_search_strategy
        limit: 最大返回结果数
        
        返回:
        匹配的素材列表
        """
        logger.info(f"为片段 {segment_requirement.get('id', 'unknown')} 搜索素材")
        
        # 提取搜索策略
        search_strategy = self._get_search_strategy(segment_requirement)
        search_type = search_strategy.get("search_type", "vector")
        
        # 根据不同搜索类型执行搜索
        if search_type == "vector":
            materials = self._vector_search(segment_requirement, limit)
        elif search_type == "keyword":
            materials = self._keyword_search(segment_requirement, limit)
        elif search_type == "hybrid":
            materials = self._hybrid_search(segment_requirement, limit)
        else:
            logger.warning(f"未知的搜索类型: {search_type}，使用向量搜索作为默认方法")
            materials = self._vector_search(segment_requirement, limit)
        
        # 应用额外过滤
        materials = self._apply_filters(materials, segment_requirement)
        
        # 对结果进行排序
        materials = self._rank_materials(materials, segment_requirement)
        
        logger.info(f"找到 {len(materials)} 个匹配的素材")
        return materials
    
    def _build_search_query(self, segment_requirement: Dict[str, Any]) -> str:
        """
        构建搜索查询文本 - 简化版本，只包含品牌和型号
        
        参数:
        segment_requirement: 视频片段需求
        
        返回:
        搜索查询文本
        """
        # 构建查询文本
        query_parts = []
        
        # 品牌和车型（从搜索策略中提取）
        search_strategy = self._get_search_strategy(segment_requirement)
        priority_brands = search_strategy.get("priority_brands", [])
        priority_models = search_strategy.get("priority_models", [])
        
        if priority_brands:
            query_parts.append(f"品牌: {', '.join(priority_brands)}")
        
        if priority_models:
            query_parts.append(f"车型: {', '.join(priority_models)}")
        
        # 组合查询文本
        query = " ".join(query_parts)
        logger.info(f"构建的搜索查询: {query}")
        
        return query
    
    def _vector_search(self, segment_requirement: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        基于向量相似度的素材搜索
        
        参数:
        segment_requirement: 视频片段需求
        limit: 最大结果数量
        
        返回:
        匹配的素材列表
        """
        logger.info("执行向量搜索")
        
        # 构建搜索查询文本
        query_text = self._build_search_query(segment_requirement)
        
        # 生成查询向量
        try:
            query_vector = self.embedding_service.get_embedding(query_text)
            logger.info(f"生成查询向量，维度: {len(query_vector)}")
        except Exception as e:
            logger.error(f"生成查询向量时出错: {e}")
            return []
        
        # 构建预过滤条件
        pre_filter = self._build_pre_filter(segment_requirement)
        
        # 执行向量搜索
        try:
            search_strategy = self._get_search_strategy(segment_requirement)
            minimum_match_score = search_strategy.get("minimum_match_score", 0.7)
            
            # 步骤1: 先搜索匹配的视频
            logger.info("步骤1: 搜索匹配的视频...")
            matching_videos = self.vector_search_service.search_similar_vectors(
                query_vector=query_vector,
                limit=limit * 2,  # 增加结果数量以便后续过滤
                collection_name='videos',  # 假设集合名为 'videos'
                vector_field='fusion_vector', # 指定向量字段
                pre_filter=pre_filter # 传递预过滤条件
            )
            
            if not matching_videos:
                logger.warning("没有找到匹配的视频，尝试关键词搜索")
                return self._keyword_search(segment_requirement, limit)
            
            # 提取匹配视频的ID
            video_ids = []
            video_map = {}  # 存储视频信息，用于后续获取路径等信息
            
            for video in matching_videos:
                if "_id" in video:
                    video_id = str(video["_id"])
                    video_ids.append(video_id)
                    video_map[video_id] = video
            
            logger.info(f"找到 {len(video_ids)} 个匹配的视频ID")
            
            # 步骤2: 根据视频ID搜索匹配的段落
            logger.info("步骤2: 搜索匹配的视频段落...")
            
            # 段落过滤条件
            segment_filter = {"video_id": {"$in": video_ids}}
            
            # 添加镜头类型过滤条件
            visual_requirements = segment_requirement.get("visual_requirements", {})
            shot_type = visual_requirements.get("shot_type", "")
            if shot_type:
                segment_filter["shot_type"] = shot_type
            
            # 搜索段落
            try:
                # 使用visual_vector进行段落级别的向量搜索
                matching_segments = self.vector_search_service.search_similar_vectors(
                    query_vector=query_vector,
                    limit=limit * 3,  # 获取更多结果，以便后续过滤
                    collection_name='video_segments',  # 视频分段集合
                    vector_field='visual_vector',  # 段落的视觉向量
                    pre_filter=segment_filter  # 仅搜索匹配视频的段落
                )
                
                logger.info(f"找到 {len(matching_segments)} 个匹配的视频段落")
                
                # 转换段落结果为素材格式，并添加来自原始视频的相关信息
                materials = []
                
                for segment in matching_segments:
                    if segment.get("similarity_score", 0) < minimum_match_score:
                        continue
                    
                    # 获取段落对应的视频ID和相关信息
                    segment_video_id = segment.get("video_id", "")
                    if segment_video_id in video_map:
                        video_data = video_map[segment_video_id]
                        
                        # 创建素材对象
                        material = {
                            "_id": str(segment.get("_id", "")),
                            "video_id": segment_video_id,
                            "video_path": video_data.get("file_info", {}).get("path", ""),
                            "title": video_data.get("title", "未知视频"),
                            "duration": segment.get("duration", video_data.get("duration", 0)),
                            "start_time": segment.get("start_time", 0),
                            "end_time": segment.get("end_time", 0),
                            "shot_type": segment.get("shot_type", ""),
                            "shot_description": segment.get("shot_description", ""),
                            "brand": video_data.get("metadata", {}).get("brand", ""),
                            "similarity_score": segment.get("similarity_score", 0.5),
                            "content_tags": segment.get("content_tags", [])
                        }
                        
                        materials.append(material)
                
                # 如果没有找到足够的段落，回退到直接使用视频
                if not materials:
                    logger.warning("没有找到匹配的视频段落，回退到视频级别匹配")
                    
                    # 将匹配的视频直接转换为素材格式
                    for video in matching_videos:
                        if video.get("similarity_score", 0) >= minimum_match_score:
                            material = {
                                "_id": str(video.get("_id", "")),
                                "video_id": str(video.get("_id", "")),
                                "video_path": video.get("file_info", {}).get("path", ""),
                                "title": video.get("title", "未知视频"),
                                "duration": video.get("duration", 0),
                                "start_time": 0,
                                "end_time": video.get("duration", 0),
                                "brand": video.get("metadata", {}).get("brand", ""),
                                "similarity_score": video.get("similarity_score", 0.5),
                                "content_tags": video.get("content_tags", [])
                            }
                            materials.append(material)
                
                return materials[:limit]  # 确保不超过原始限制
                
            except Exception as e:
                logger.error(f"搜索段落时出错: {e}")
                
                # 如果段落搜索失败，回退到直接使用视频
                logger.warning("段落搜索失败，回退到视频级别匹配")
                materials = []
                
                for video in matching_videos:
                    if video.get("similarity_score", 0) >= minimum_match_score:
                        material = {
                            "_id": str(video.get("_id", "")),
                            "video_id": str(video.get("_id", "")),
                            "video_path": video.get("file_info", {}).get("path", ""),
                            "title": video.get("title", "未知视频"),
                            "duration": video.get("duration", 0),
                            "start_time": 0,
                            "end_time": video.get("duration", 0),
                            "brand": video.get("metadata", {}).get("brand", ""),
                            "similarity_score": video.get("similarity_score", 0.5),
                            "content_tags": video.get("content_tags", [])
                        }
                        materials.append(material)
                
                return materials[:limit]
            
        except Exception as e:
            logger.error(f"执行向量搜索时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 出错时尝试关键词搜索作为备选方案
            logger.info("向量搜索失败，尝试使用关键词搜索作为备选")
            return self._keyword_search(segment_requirement, limit)
    
    def _keyword_search(self, segment_requirement: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        基于关键词和标签的素材搜索
        
        参数:
        segment_requirement: 视频片段需求
        limit: 最大结果数量
        
        返回:
        匹配的素材列表
        """
        logger.info("执行关键词搜索")
        
        # 构建视频过滤条件
        video_filter = self._build_pre_filter(segment_requirement)
        
        # 获取所有需要匹配的标签
        visual_requirements = segment_requirement.get("visual_requirements", {})
        search_strategy = self._get_search_strategy(segment_requirement)
        
        required_tags = []
        
        # 从视觉需求中提取标签
        scene_type = visual_requirements.get("scene_type")
        if scene_type:
            required_tags.append(scene_type)
        
        required_elements = visual_requirements.get("required_elements", [])
        required_tags.extend(required_elements)
        
        # 从搜索策略中提取优先标签
        priority_tags = search_strategy.get("priority_tags", [])
        required_tags.extend(priority_tags)
        
        # 去重
        required_tags = list(set(required_tags))
        
        # 步骤1: 先搜索匹配的视频
        logger.info("步骤1: 基于关键词搜索匹配的视频...")
        
        # 如果有标签，添加到过滤条件
        if required_tags:
            video_filter["content_tags"] = {"$in": required_tags}
        
        try:
            # 执行视频查询
            matching_videos = list(self.mongodb_service.videos.find(
                video_filter,
                limit=20  # 获取更多视频以便后续筛选段落
            ))
            
            # 转换ObjectId为字符串
            for video in matching_videos:
                if "_id" in video and isinstance(video["_id"], ObjectId):
                    video["_id"] = str(video["_id"])
            
            logger.info(f"关键词搜索找到 {len(matching_videos)} 个匹配的视频")
            
            if not matching_videos:
                logger.warning("没有找到匹配的视频")
                return []
            
            # 提取视频ID
            video_ids = [video["_id"] for video in matching_videos if "_id" in video]
            video_map = {video["_id"]: video for video in matching_videos if "_id" in video}
            
            # 步骤2: 搜索匹配的视频段落
            logger.info("步骤2: 搜索匹配的视频段落...")
            
            # 段落过滤条件
            segment_filter = {"video_id": {"$in": video_ids}}
            
            # 添加镜头类型过滤条件
            shot_type = visual_requirements.get("shot_type", "")
            if shot_type:
                segment_filter["shot_type"] = shot_type
                
            # 如果有标签，添加到段落过滤条件
            if required_tags:
                segment_filter["content_tags"] = {"$in": required_tags}
                
            try:
                # 查询段落
                matching_segments = list(self.mongodb_service.video_segments.find(
                    segment_filter,
                    limit=limit * 3  # 获取更多结果以便后续过滤
                ))
                
                # 转换ObjectId为字符串
                for segment in matching_segments:
                    if "_id" in segment and isinstance(segment["_id"], ObjectId):
                        segment["_id"] = str(segment["_id"])
                
                logger.info(f"找到 {len(matching_segments)} 个匹配的视频段落")
                
                # 转换段落结果为素材格式，并添加来自原始视频的相关信息
                materials = []
                
                for segment in matching_segments:
                    # 获取段落对应的视频ID和相关信息
                    segment_video_id = segment.get("video_id", "")
                    if segment_video_id in video_map:
                        video_data = video_map[segment_video_id]
                        
                        # 创建素材对象
                        material = {
                            "_id": str(segment.get("_id", "")),
                            "video_id": segment_video_id,
                            "video_path": video_data.get("file_info", {}).get("path", ""),
                            "title": video_data.get("title", "未知视频"),
                            "duration": segment.get("duration", video_data.get("duration", 0)),
                            "start_time": segment.get("start_time", 0),
                            "end_time": segment.get("end_time", 0),
                            "shot_type": segment.get("shot_type", ""),
                            "shot_description": segment.get("shot_description", ""),
                            "brand": video_data.get("metadata", {}).get("brand", ""),
                            "similarity_score": 0.7,  # 使用固定相似度分数，因为这是关键词匹配
                            "content_tags": segment.get("content_tags", [])
                        }
                        
                        materials.append(material)
                
                # 如果没有找到足够的段落，回退到直接使用视频
                if not materials:
                    logger.warning("没有找到匹配的视频段落，回退到视频级别匹配")
                    
                    # 将匹配的视频直接转换为素材格式
                    for video in matching_videos:
                        material = {
                            "_id": str(video.get("_id", "")),
                            "video_id": str(video.get("_id", "")),
                            "video_path": video.get("file_info", {}).get("path", ""),
                            "title": video.get("title", "未知视频"),
                            "duration": video.get("duration", 0),
                            "start_time": 0,
                            "end_time": video.get("duration", 0),
                            "brand": video.get("metadata", {}).get("brand", ""),
                            "similarity_score": 0.7,  # 使用固定相似度分数
                            "content_tags": video.get("content_tags", [])
                        }
                        materials.append(material)
                
                return materials[:limit]  # 确保不超过原始限制
                
            except Exception as e:
                logger.error(f"搜索段落时出错: {e}")
                
                # 如果段落搜索失败，回退到直接使用视频
                logger.warning("段落搜索失败，回退到视频级别匹配")
                materials = []
                
                for video in matching_videos:
                    material = {
                        "_id": str(video.get("_id", "")),
                        "video_id": str(video.get("_id", "")),
                        "video_path": video.get("file_info", {}).get("path", ""),
                        "title": video.get("title", "未知视频"),
                        "duration": video.get("duration", 0),
                        "start_time": 0,
                        "end_time": video.get("duration", 0),
                        "brand": video.get("metadata", {}).get("brand", ""),
                        "similarity_score": 0.7,  # 使用固定相似度分数
                        "content_tags": video.get("content_tags", [])
                    }
                    materials.append(material)
                
                return materials[:limit]
            
        except Exception as e:
            logger.error(f"执行关键词搜索时出错: {e}")
            return []
    
    def _hybrid_search(self, segment_requirement: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        混合搜索策略，结合向量和关键词搜索
        
        参数:
        segment_requirement: 视频片段需求
        limit: 最大结果数量
        
        返回:
        匹配的素材列表
        """
        logger.info("执行混合搜索")
        
        # 执行向量搜索
        vector_results = self._vector_search(segment_requirement, limit)
        
        # 如果向量搜索结果足够，直接返回
        if len(vector_results) >= limit:
            logger.info(f"向量搜索结果充足，返回前 {limit} 个结果")
            return vector_results[:limit]
        
        # 执行关键词搜索，但排除已有的视频ID
        existing_video_ids = [result.get("video_id", "") for result in vector_results if "video_id" in result]
        
        # 更新搜索策略以进行关键词搜索
        modified_requirement = copy.deepcopy(segment_requirement)
        modified_search_strategy = self._get_search_strategy(modified_requirement)
        modified_search_strategy["search_type"] = "keyword"
        modified_requirement["material_search_strategy"] = modified_search_strategy
        
        # 执行关键词搜索
        keyword_results = self._keyword_search(modified_requirement, limit)
        
        # 合并结果（向量搜索结果优先）
        merged_results = list(vector_results)
        
        # 添加关键词搜索结果（如果不在已有结果中）
        for material in keyword_results:
            if "video_id" in material and material["video_id"] not in existing_video_ids:
                merged_results.append(material)
                existing_video_ids.append(material["video_id"])
                
                if len(merged_results) >= limit:
                    break
        
        logger.info(f"混合搜索完成，最终找到 {len(merged_results)} 个匹配的段落/视频")
        return merged_results[:limit]
    
    def _build_pre_filter(self, segment_requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建预过滤条件 - 简化版本，只包含品牌和型号过滤
        
        参数:
        segment_requirement: 视频片段需求
        
        返回:
        过滤条件字典
        """
        # 初始化过滤条件
        filter_conditions = {}
        
        # 获取搜索策略
        search_strategy = self._get_search_strategy(segment_requirement)
        
        # 优先品牌和车型
        priority_brands = search_strategy.get("priority_brands", [])
        priority_models = search_strategy.get("priority_models", [])
        
        # 如果指定了品牌，添加品牌过滤
        if priority_brands:
            if len(priority_brands) == 1:
                filter_conditions["brand"] = priority_brands[0]
            else:
                filter_conditions["brand"] = {"$in": priority_brands}
        
        # 如果指定了车型，添加车型过滤
        if priority_models:
            if len(priority_models) == 1:
                filter_conditions["model"] = priority_models[0]
            else:
                filter_conditions["model"] = {"$in": priority_models}
        
        return filter_conditions
    
    def _apply_filters(self, materials: List[Dict[str, Any]], segment_requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        应用额外的过滤条件
        
        参数:
        materials: 待过滤的素材列表
        segment_requirement: 视频片段需求
        
        返回:
        过滤后的素材列表
        """
        if not materials:
            return []
        
        filtered_materials = []
        
        # 获取搜索策略和分段过滤器
        search_strategy = self._get_search_strategy(segment_requirement)
        segment_filters = search_strategy.get("segment_filters", {})
        
        # 最小时长过滤
        min_duration = segment_filters.get("min_duration", 0)
        
        # 最大时长过滤（如果有）
        max_duration = segment_filters.get("max_duration")
        
        # 应用过滤
        for material in materials:
            duration = material.get("duration", 0)
            
            # 跳过短于最小时长的材料
            if min_duration > 0 and duration < min_duration:
                continue
            
            # 跳过长于最大时长的材料（如果指定了最大时长）
            if max_duration is not None and duration > max_duration:
                continue
            
            # 通过所有过滤的材料添加到结果中
            filtered_materials.append(material)
        
        return filtered_materials
    
    def _rank_materials(self, materials: List[Dict[str, Any]], segment_requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        对匹配的素材进行排序
        
        参数:
        materials: 匹配的素材列表
        segment_requirement: 视频片段需求
        
        返回:
        排序后的素材列表
        """
        if not materials:
            return []
        
        # 获取权重设置
        search_strategy = self._get_search_strategy(segment_requirement)
        weight_settings = search_strategy.get("weight_settings", {})
        
        # 默认权重
        visual_similarity_weight = weight_settings.get("visual_similarity", 0.7)
        contextual_relevance_weight = weight_settings.get("contextual_relevance", 0.2)
        technical_quality_weight = weight_settings.get("technical_quality", 0.1)
        
        # 计算每个素材的综合分数
        for material in materials:
            # 如果已有相似度分数，使用该分数作为基础
            base_score = material.get("similarity_score", 0.5)
            
            # 计算视觉相似度分数（基于已有的相似度分数）
            visual_score = base_score
            
            # 计算上下文相关性分数（基于标签匹配）
            contextual_score = self._calculate_contextual_relevance(material, segment_requirement)
            
            # 计算技术质量分数（基于分辨率、稳定性等）
            technical_score = self._calculate_technical_quality(material)
            
            # 计算加权总分
            total_score = (
                visual_similarity_weight * visual_score +
                contextual_relevance_weight * contextual_score +
                technical_quality_weight * technical_score
            )
            
            # 将分数保存到素材中
            material["ranking_score"] = total_score
            material["score_components"] = {
                "visual_score": visual_score,
                "contextual_score": contextual_score,
                "technical_score": technical_score
            }
        
        # 按分数降序排序
        ranked_materials = sorted(materials, key=lambda x: x.get("ranking_score", 0), reverse=True)
        
        return ranked_materials
    
    def _calculate_contextual_relevance(self, material: Dict[str, Any], segment_requirement: Dict[str, Any]) -> float:
        """
        计算素材与片段需求的上下文相关性
        
        参数:
        material: 素材信息
        segment_requirement: 视频片段需求
        
        返回:
        上下文相关性分数 (0-1)
        """
        # 从素材和需求中提取相关信息
        visual_requirements = segment_requirement.get("visual_requirements", {})
        search_strategy = self._get_search_strategy(segment_requirement)
        
        # 标签匹配分数
        material_tags = material.get("content_tags", [])
        
        # 从视觉需求中提取必要元素
        required_elements = visual_requirements.get("required_elements", [])
        
        # 从搜索策略中提取优先标签
        priority_tags = search_strategy.get("priority_tags", [])
        
        # 合并标签集合
        target_tags = set(required_elements + priority_tags)
        
        # 如果目标标签为空，返回默认分数0.5
        if not target_tags:
            return 0.5
        
        # 计算匹配的标签数量
        matching_tags = [tag for tag in target_tags if tag in material_tags]
        
        # 计算分数
        relevance_score = len(matching_tags) / len(target_tags)
        
        return relevance_score
    
    def _calculate_technical_quality(self, material: Dict[str, Any]) -> float:
        """
        计算素材的技术质量分数
        
        参数:
        material: 素材
        
        返回:
        质量分数 (0.0-1.0)
        """
        # 默认质量分数
        default_score = 0.7
        
        # 如果素材中没有足够的技术信息，返回默认分数
        if "cinematography_analysis" not in material:
            return default_score
        
        cinematography = material.get("cinematography_analysis", {})
        overall_analysis = cinematography.get("overall_analysis", {})
        
        # 如果没有整体分析，返回默认分数
        if not overall_analysis:
            return default_score
        
        # 基于各种技术指标计算分数
        # 这里只是示例，实际实现可能更复杂
        
        # 默认基础分数
        quality_score = default_score
        
        # 提高分数的因素
        positive_factors = [
            "高清晰度", "稳定", "流畅", "高品质", "专业", "细节丰富"
        ]
        
        # 降低分数的因素
        negative_factors = [
            "模糊", "抖动", "不稳定", "质量低", "噪点多"
        ]
        
        # 检查各种因素
        visual_style = overall_analysis.get("visual_style", "")
        editing_rhythm = overall_analysis.get("editing_rhythm", "")
        
        # 将字符串转换为列表（如果是字符串）
        if isinstance(visual_style, str):
            visual_style_list = [s.strip() for s in visual_style.split(",")]
        else:
            visual_style_list = visual_style
            
        if isinstance(editing_rhythm, str):
            editing_rhythm_list = [r.strip() for r in editing_rhythm.split(",")]
        else:
            editing_rhythm_list = editing_rhythm
        
        # 检查是否有正面因素
        for factor in positive_factors:
            if any(factor in s for s in visual_style_list) or any(factor in r for r in editing_rhythm_list):
                quality_score += 0.05  # 每有一个正面因素，增加0.05分
        
        # 检查是否有负面因素
        for factor in negative_factors:
            if any(factor in s for s in visual_style_list) or any(factor in r for r in editing_rhythm_list):
                quality_score -= 0.1  # 每有一个负面因素，减少0.1分
        
        # 确保分数在0.0-1.0范围内
        quality_score = max(0.0, min(1.0, quality_score))
        
        return quality_score 