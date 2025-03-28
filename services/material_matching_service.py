import os
import json
import logging
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime
import time
import re

import openai
from bson import ObjectId
import numpy as np

from services.mongodb_service import MongoDBService
from services.embedding_service import EmbeddingService
from services.vector_search_service import VectorSearchService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MaterialMatchingService:
    """视频素材智能匹配服务，基于LLM、向量检索和多维度匹配"""
    
    def __init__(self):
        """初始化素材匹配服务"""
        self.mongodb_service = MongoDBService()
        self.embedding_service = EmbeddingService()
        self.vector_search_service = VectorSearchService(self.mongodb_service)
        
        # 加载LSH索引
        try:
            self._init_vector_indices()
        except Exception as e:
            logger.warning(f"初始化向量索引时出错: {str(e)}")
        
        # 初始化缓存
        self._library_summary = None
        self._library_stats = None
        self._summary_timestamp = None
        
        # 从环境变量获取OpenAI API密钥
        openai.api_key = os.environ.get('OPENAI_API_KEY')
        if not openai.api_key:
            logger.warning("未设置OPENAI_API_KEY环境变量，LLM分析功能将不可用")
    
    def _init_vector_indices(self):
        """初始化向量索引"""
        # 初始化视频片段的LSH索引
        self.vector_search_service.build_lsh_index("video_segments", "embeddings.fusion_vector")
        self.vector_search_service.build_lsh_index("video_segments", "embeddings.text_vector")
        self.vector_search_service.build_lsh_index("video_segments", "embeddings.visual_vector")
    
    def get_library_summary(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取视频库摘要信息，用于LLM了解可用的视频素材
        
        参数:
        force_refresh: 是否强制刷新缓存
        
        返回:
        视频库摘要信息
        """
        # 检查缓存是否有效
        cache_valid = (
            self._library_summary is not None and
            self._summary_timestamp is not None and
            (datetime.now() - self._summary_timestamp).total_seconds() < 3600 and
            not force_refresh
        )
        
        if not cache_valid:
            logger.info("生成视频库摘要...")
            
            try:
                db = self.mongodb_service.db
                
                # 从videos集合获取数据
                brands = list(db.videos.distinct("metadata.brand"))
                video_types = list(db.videos.distinct("metadata.video_type"))
                
                # 从video_segments集合获取数据
                shot_types = list(db.video_segments.distinct("shot_type"))
                perspectives = list(filter(None, db.video_segments.distinct("cinematic_language.perspective")))
                emotions = list(filter(None, db.video_segments.distinct("visual_elements.emotion")))
                
                # 过滤掉None和空字符串
                brands = [b for b in brands if b]
                video_types = [t for t in video_types if t]
                shot_types = [s for s in shot_types if s]
                perspectives = [p for p in perspectives if p]
                emotions = [e for e in emotions if e]
                
                # 统计数量
                total_videos = db.videos.count_documents({})
                total_segments = db.video_segments.count_documents({})
                
                # 构建摘要
                self._library_summary = {
                    "total_videos": total_videos,
                    "total_segments": total_segments,
                    "brands": sorted(brands),
                    "video_types": sorted(video_types),
                    "shot_types": sorted(shot_types),
                    "perspectives": sorted(perspectives),
                    "emotions": sorted(emotions),
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # 生成库统计信息
                self._library_stats = self._calculate_library_stats()
                
                # 更新时间戳
                self._summary_timestamp = datetime.now()
                
                logger.info(f"视频库摘要生成完成，共{total_videos}个视频，{total_segments}个片段")
            
            except Exception as e:
                logger.error(f"生成视频库摘要时出错: {str(e)}")
                # 如果生成失败但有缓存，继续使用缓存
                if self._library_summary is None:
                    self._library_summary = {
                        "error": f"生成摘要时出错: {str(e)}",
                        "total_videos": 0,
                        "total_segments": 0,
                        "brands": [],
                        "video_types": [],
                        "shot_types": [],
                        "perspectives": [],
                        "emotions": [],
                        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
        
        return self._library_summary
    
    def _calculate_library_stats(self) -> Dict[str, Any]:
        """
        计算视频库的统计信息
        
        返回:
        统计信息字典
        """
        try:
            db = self.mongodb_service.db
            
            # 按品牌统计视频数量
            brand_stats = list(db.videos.aggregate([
                {"$group": {"_id": "$metadata.brand", "count": {"$sum": 1}}},
                {"$match": {"_id": {"$ne": None}}},
                {"$sort": {"count": -1}}
            ]))
            
            # 按镜头类型统计片段数量
            shot_type_stats = list(db.video_segments.aggregate([
                {"$group": {"_id": "$shot_type", "count": {"$sum": 1}}},
                {"$match": {"_id": {"$ne": None}}},
                {"$sort": {"count": -1}}
            ]))
            
            # 按情感统计片段数量
            emotion_stats = list(db.video_segments.aggregate([
                {"$group": {"_id": "$visual_elements.emotion", "count": {"$sum": 1}}},
                {"$match": {"_id": {"$ne": None}}},
                {"$sort": {"count": -1}}
            ]))
            
            return {
                "brands": {item["_id"]: item["count"] for item in brand_stats if item["_id"]},
                "shot_types": {item["_id"]: item["count"] for item in shot_type_stats if item["_id"]},
                "emotions": {item["_id"]: item["count"] for item in emotion_stats if item["_id"]}
            }
        
        except Exception as e:
            logger.error(f"计算库统计信息时出错: {str(e)}")
            return {"error": str(e)}
    
    def analyze_script(self, script: str) -> Dict[str, Any]:
        """
        使用LLM分析脚本，识别场景和匹配需求
        
        参数:
        script: 脚本文本
        
        返回:
        脚本分析结果
        """
        if not openai.api_key:
            raise ValueError("未设置OpenAI API密钥，无法使用LLM分析功能")
            
        # 获取视频库摘要
        summary = self.get_library_summary()
        
        # 构建提示，注入视频库信息
        prompt = f"""
分析以下视频脚本，提取详细的场景结构和每个场景的特征需求，以便后续匹配最合适的视频素材。

可用的视频库信息:
- 可用品牌: {summary['brands'][:10] if len(summary['brands']) > 10 else summary['brands']}
- 可用视频类型: {summary['video_types']}
- 可用镜头类型: {summary['shot_types'][:10] if len(summary['shot_types']) > 10 else summary['shot_types']}
- 可用视角类型: {summary['perspectives']}
- 可用情感类型: {summary['emotions'][:10] if len(summary['emotions']) > 10 else summary['emotions']}
- 共有 {summary['total_videos']} 个视频，{summary['total_segments']} 个视频片段

脚本内容:
{script}

请详细分析每个场景，提取以下信息：
1. 场景编号和描述
2. 可能的品牌和产品名称（必须从可用品牌列表中选择，如果没有匹配的则保留空字符串）
3. 镜头类型需求（特写、远景、跟踪等）（必须尽量匹配可用镜头类型）
4. 情感基调需求（必须尽量匹配可用情感类型）
5. 场景时间要求（如有）
6. 场景的核心主题或功能展示
7. 视觉元素和对象
8. 动作描述和要求
9. 可选的色彩和构图要求

请以JSON格式返回，结构如下:
{{
  "title": "脚本标题",
  "brand": "相关品牌名称（从可用品牌列表中选择）",
  "tonality": "整体基调（从可用情感类型列表中选择）",
  "pace": "节奏需求（快节奏/中等/舒缓）",
  "color_preference": "主色调偏好（如有）",
  "scenes": [
    {{
      "id": "场景1",
      "description": "详细场景描述",
      "shot_type_preference": "镜头类型偏好（从可用镜头类型中选择）",
      "key_elements": ["需要出现的关键元素"],
      "emotion": "场景情感基调（从可用情感类型中选择）",
      "time_requirement": {{
        "min_duration": 2,
        "max_duration": 5
      }},
      "visual_objects": ["需要出现的视觉对象"],
      "actions": ["需要展示的动作"],
      "function": "场景功能（产品展示/功能演示/场景氛围/情感表达/动作展示）"
    }}
  ]
}}

仅返回JSON格式结果，不要其他解释。确保选择的品牌、镜头类型和情感类型尽可能从提供的可用选项中选择，如果没有匹配的选项则使用空字符串。
"""
        
        try:
            # 调用OpenAI GPT模型
            response = openai.chat.completions.create(
                model="gpt-4o",  # 使用最新可用的模型
                messages=[
                    {"role": "system", "content": "你是一位专业的视频创意分析师，擅长解析脚本并提取视觉关键元素，具有深厚的影视制作知识"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # 解析返回的JSON
            result_text = response.choices[0].message.content
            script_analysis = json.loads(result_text)
            
            # 为每个场景生成向量
            script_analysis = self._generate_scene_vectors(script_analysis)
            
            logger.info(f"脚本分析完成，识别到{len(script_analysis.get('scenes', []))}个场景")
            return script_analysis
            
        except Exception as e:
            logger.error(f"LLM分析脚本时出错: {str(e)}")
            raise ValueError(f"分析脚本失败: {str(e)}")
    
    def _generate_scene_vectors(self, script_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """为每个场景生成向量表示"""
        if 'scenes' not in script_analysis:
            return script_analysis
            
        for scene in script_analysis['scenes']:
            # 构建场景描述的完整文本，用于生成向量
            scene_text = f"{scene.get('description', '')} {scene.get('shot_type_preference', '')} {scene.get('emotion', '')}"
            
            # 添加关键元素
            if 'key_elements' in scene and isinstance(scene['key_elements'], list):
                scene_text += " " + " ".join(scene['key_elements'])
                
            # 添加视觉对象
            if 'visual_objects' in scene and isinstance(scene['visual_objects'], list):
                scene_text += " " + " ".join(scene['visual_objects'])
                
            # 添加动作
            if 'actions' in scene and isinstance(scene['actions'], list):
                scene_text += " " + " ".join(scene['actions'])
                
            # 生成向量
            try:
                vector = self.embedding_service.get_embedding(scene_text)
                scene['vector'] = vector
            except Exception as e:
                logger.error(f"生成场景向量时出错: {str(e)}")
                # 确保即使向量生成失败，也有向量字段（空向量）
                scene['vector'] = [0] * 1536
                
        return script_analysis
    
    def match_script_to_video(self, script: str) -> Dict[str, Any]:
        """
        执行完整的脚本到视频匹配流程
        
        参数:
        script: 脚本文本
        
        返回:
        完整的匹配结果
        """
        try:
            start_time = time.time()
            
            # 1. 分析脚本
            script_analysis = self.analyze_script(script)
            
            # 2. 处理场景匹配
            scenes = script_analysis.get("scenes", [])
            if not scenes:
                raise ValueError("脚本分析未返回有效场景")
            
            # 3. 初筛符合品牌和内容需求的视频
            filtered_video_ids = self._filter_videos_by_requirements(script_analysis)
            logger.info(f"初筛出 {len(filtered_video_ids)} 个符合品牌和内容需求的视频")
            
            matching_results = []
            
            # 4. 为每个场景找到匹配的视频片段
            for i, scene in enumerate(scenes):
                logger.info(f"处理场景 {i+1}/{len(scenes)}: {scene.get('id', f'场景{i+1}')}")
                
                # 查找匹配片段
                matches = self._find_matching_segments_for_scene(
                    scene=scene,
                    filtered_video_ids=filtered_video_ids
                )
                
                # 添加到结果
                matching_results.append({
                    "scene": scene,
                    "matches": matches
                })
            
            # 5. 生成最终的分镜表
            shotlist = self._generate_shotlist(matching_results, script_analysis)
            
            # 计算耗时
            elapsed_time = time.time() - start_time
            
            # 6. 构建并返回完整结果
            result = {
                "script_analysis": script_analysis,
                "shotlist": shotlist,
                "library_stats": {
                    "total_videos": self.get_library_summary()["total_videos"],
                    "total_segments": self.get_library_summary()["total_segments"],
                },
                "process_info": {
                    "scenes_count": len(scenes),
                    "processing_time": round(elapsed_time, 2),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"执行脚本到视频匹配时出错: {str(e)}")
            raise ValueError(f"匹配失败: {str(e)}")
    
    def _filter_videos_by_requirements(self, script_analysis: Dict[str, Any]) -> List[str]:
        """
        根据脚本需求过滤视频
        
        参数:
        script_analysis: 脚本分析结果
        
        返回:
        符合要求的视频ID列表
        """
        try:
            # 构建过滤条件
            filter_conditions = {}
            
            # 品牌过滤
            brand = script_analysis.get("brand")
            if brand:
                filter_conditions["metadata.brand"] = {"$regex": brand, "$options": "i"}
            
            # 从所有场景中提取可能的内容标签
            content_tags = set()
            for scene in script_analysis.get("scenes", []):
                # 添加镜头类型
                if scene.get("shot_type_preference"):
                    content_tags.add(scene["shot_type_preference"])
                
                # 添加关键元素
                if "key_elements" in scene and isinstance(scene["key_elements"], list):
                    content_tags.update(scene["key_elements"])
                
                # 添加功能标签
                if scene.get("function"):
                    content_tags.add(scene["function"])
            
            # 添加内容标签过滤（如果有足够的标签）
            if content_tags:
                # 只要求匹配任意一个标签
                filter_conditions["metadata.tags"] = {"$in": list(content_tags)}
            
            # 查询符合条件的视频
            videos = list(self.mongodb_service.db.videos.find(
                filter_conditions,
                {"_id": 1}  # 只返回ID字段
            ))
            
            # 提取ID
            video_ids = [str(video["_id"]) for video in videos]
            
            # 如果没有匹配的视频，返回所有视频ID
            if not video_ids:
                logger.warning("没有视频符合过滤条件，返回所有视频")
                all_videos = list(self.mongodb_service.db.videos.find({}, {"_id": 1}))
                video_ids = [str(video["_id"]) for video in all_videos]
            
            return video_ids
        
        except Exception as e:
            logger.error(f"过滤视频时出错: {str(e)}")
            # 如果出错，返回空列表
            return []
    
    def _find_matching_segments_for_scene(self, scene: Dict[str, Any], filtered_video_ids: List[str]) -> List[Dict[str, Any]]:
        """
        为场景查找匹配的视频片段
        
        参数:
        scene: 场景信息
        filtered_video_ids: 预过滤的视频ID列表
        
        返回:
        匹配的视频片段列表
        """
        try:
            # 构建查询条件
            filters = {}
            
            # 添加视频ID过滤
            if filtered_video_ids:
                # 转换为ObjectId
                try:
                    object_ids = [ObjectId(vid) for vid in filtered_video_ids]
                    filters["video_id"] = {"$in": object_ids}
                except Exception as e:
                    logger.error(f"转换视频ID时出错: {str(e)}")
            
            # 添加镜头类型过滤
            if scene.get("shot_type_preference"):
                filters["shot_type"] = {"$regex": scene["shot_type_preference"], "$options": "i"}
            
            # 添加情感过滤
            if scene.get("emotion"):
                filters["emotional_tags"] = {"$regex": scene["emotion"], "$options": "i"}
            
            # 添加功能过滤
            if scene.get("function"):
                filters["shot_metadata.function"] = {"$regex": scene["function"], "$options": "i"}
            
            # 添加时间要求（如果有）
            if "time_requirement" in scene:
                min_duration = scene["time_requirement"].get("min_duration", 0)
                max_duration = scene["time_requirement"].get("max_duration", 100)
                
                # 只选择时长在范围内的片段
                filters["duration"] = {"$gte": min_duration, "$lte": max_duration}
            
            # 检查场景是否有向量表示
            if "vector" not in scene or not scene["vector"]:
                logger.warning(f"场景 {scene.get('id', '未知')} 没有向量表示，降级到文本搜索")
                # 降级到文本搜索
                description = scene.get("description", "")
                return self.mongodb_service.text_search(description, 5)
            
            try:
                # 使用应用层向量搜索服务
                logger.info("使用应用层向量搜索服务搜索匹配片段")
                
                # 确保LSH索引已构建
                self.vector_search_service.build_lsh_index("video_segments", "embeddings.text_vector")
                self.vector_search_service.build_lsh_index("video_segments", "embeddings.fusion_vector")
                
                # 多阶段搜索：先尝试使用文本向量
                results = self.vector_search_service.search_similar_vectors(
                    query_vector=scene["vector"],
                    collection_name="video_segments",
                    vector_field="embeddings.text_vector",
                    pre_filter=filters,
                    limit=10
                )
                
                # 如果结果为空，尝试使用融合向量
                if not results:
                    logger.info("文本向量搜索无结果，尝试使用融合向量")
                    results = self.vector_search_service.search_similar_vectors(
                        query_vector=scene["vector"],
                        collection_name="video_segments",
                        vector_field="embeddings.fusion_vector",
                        pre_filter=filters,
                        limit=10
                    )
                
                # 如果仍无结果，放宽条件
                if not results:
                    logger.warning(f"场景 {scene.get('id', '未知')} 向量搜索无结果，放宽条件")
                    # 移除部分过滤条件，只保留视频ID过滤
                    min_filters = {}
                    if "video_id" in filters:
                        min_filters["video_id"] = filters["video_id"]
                    
                    # 尝试提高搜索数量限制，有可能相关结果被排在后面
                    results = self.vector_search_service.search_similar_vectors(
                        query_vector=scene["vector"],
                        collection_name="video_segments",
                        vector_field="embeddings.fusion_vector",
                        pre_filter=min_filters,
                        limit=20  # 增加搜索范围
                    )
                
                # 如果仍然没有结果，降级到文本搜索
                if not results:
                    logger.warning(f"场景 {scene.get('id', '未知')} 放宽条件后仍无结果，降级到文本搜索")
                    description = scene.get("description", "")
                    return self.mongodb_service.text_search(description, 5)
                
                # 添加视频信息
                results_with_video_info = []
                for result in results:
                    try:
                        # 查询视频信息
                        video = self.mongodb_service.db.videos.find_one({"_id": result["video_id"]})
                        if video:
                            result["video_info"] = {
                                "title": video.get("title", "未知视频"),
                                "brand": video.get("metadata", {}).get("brand", ""),
                                "video_type": video.get("metadata", {}).get("video_type", "")
                            }
                        # 如果没有vector_score，添加一个默认值以避免后续处理出错
                        if "vector_score" not in result:
                            result["vector_score"] = 0.5
                        results_with_video_info.append(result)
                    except Exception as e:
                        logger.error(f"附加视频信息时出错: {str(e)}")
                        # 即使出错也添加原始结果
                        if "vector_score" not in result:
                            result["vector_score"] = 0.5
                        results_with_video_info.append(result)
                
                # 进行多维度评分
                scored_results = self._score_segments_for_scene(results_with_video_info, scene)
                
                # 按最终得分排序
                scored_results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
                
                # 打印向量搜索服务缓存统计
                cache_stats = self.vector_search_service.get_cache_stats()
                logger.info(f"向量搜索服务缓存统计: 命中率 {cache_stats['hit_rate']:.2f}, 查询总数: {cache_stats['query_count']}")
                
                # 限制返回数量
                return scored_results[:5]
                
            except Exception as e:
                logger.error(f"应用层向量搜索出错: {str(e)}")
                # 降级到文本搜索
                logger.warning(f"向量搜索失败，降级到文本搜索")
                description = scene.get("description", "")
                return self.mongodb_service.text_search(description, 5)
            
        except Exception as e:
            logger.error(f"为场景查找匹配片段时出错: {str(e)}")
            return []
    
    def _score_segments_for_scene(self, segments: List[Dict[str, Any]], scene: Dict[str, Any]) -> List[Dict[str, Any]]:
        """对片段进行多维度评分"""
        scored_segments = []
        
        for segment in segments:
            # 基础向量相似度分数（如果有）
            base_score = segment.get("vector_score", 0.5)
            
            # 初始化各维度分数
            scores = {
                "vector_score": base_score * 0.5,  # 向量相似度基础权重
                "shot_type_score": 0,
                "emotion_score": 0,
                "function_score": 0,
                "content_score": 0,
                "duration_score": 0
            }
            
            # 镜头类型匹配评分
            shot_type_preference = scene.get("shot_type_preference", "").lower()
            if shot_type_preference and segment.get("shot_type"):
                if shot_type_preference in segment["shot_type"].lower():
                    scores["shot_type_score"] = 0.15
            
            # 情感标签匹配评分
            scene_emotion = scene.get("emotion", "").lower()
            if scene_emotion and "emotional_tags" in segment:
                emotional_tags = [tag.lower() for tag in segment["emotional_tags"]]
                if scene_emotion in emotional_tags:
                    scores["emotion_score"] = 0.15
                elif any(scene_emotion in tag for tag in emotional_tags):
                    scores["emotion_score"] = 0.1
            
            # 功能匹配评分
            scene_function = scene.get("function", "").lower()
            if scene_function and "shot_metadata" in segment and "function" in segment["shot_metadata"]:
                if scene_function.lower() in segment["shot_metadata"]["function"].lower():
                    scores["function_score"] = 0.1
            
            # 内容匹配评分（关键元素和视觉对象）
            content_match_count = 0
            
            # 关键元素匹配
            if "key_elements" in scene and isinstance(scene["key_elements"], list):
                for element in scene["key_elements"]:
                    if element.lower() in segment.get("searchable_text", "").lower():
                        content_match_count += 1
            
            # 视觉对象匹配
            if "visual_objects" in scene and isinstance(scene["visual_objects"], list) and "shot_metadata" in segment and "objects" in segment["shot_metadata"]:
                segment_objects = [obj.lower() for obj in segment["shot_metadata"]["objects"]]
                for obj in scene["visual_objects"]:
                    if obj.lower() in segment_objects or any(obj.lower() in seg_obj for seg_obj in segment_objects):
                        content_match_count += 1
            
            # 根据匹配数量计算内容得分
            if content_match_count > 0:
                scores["content_score"] = min(0.15, 0.05 * content_match_count)
            
            # 时长匹配评分
            if "time_requirement" in scene and "duration" in segment:
                min_duration = scene["time_requirement"].get("min_duration", 0)
                max_duration = scene["time_requirement"].get("max_duration", 100)
                duration = segment["duration"]
                
                # 如果时长在理想范围内，给满分
                if min_duration <= duration <= max_duration:
                    scores["duration_score"] = 0.1
                # 如果稍微超出范围，给部分分数
                elif (min_duration - 1 <= duration <= max_duration + 1):
                    scores["duration_score"] = 0.05
            else:
                # 如果没有时长要求，默认给一些分数
                scores["duration_score"] = 0.05
            
            # 计算最终得分
            final_score = sum(scores.values())
            
            # 生成匹配原因
            match_reasons = self._generate_match_reasons(segment, scene, scores)
            
            # 更新片段
            segment_copy = dict(segment)
            segment_copy["final_score"] = final_score
            segment_copy["score_details"] = scores
            segment_copy["match_reasons"] = match_reasons
            
            scored_segments.append(segment_copy)
        
        return scored_segments
    
    def _generate_match_reasons(self, segment: Dict[str, Any], scene: Dict[str, Any], scores: Dict[str, float]) -> List[str]:
        """生成匹配原因列表"""
        reasons = []
        
        # 向量相似度匹配
        if scores["vector_score"] > 0:
            similarity_percent = min(round(scores["vector_score"] * 200, 1), 100)  # 转为0-100%的百分比
            reasons.append(f"场景描述相似度: {similarity_percent}%")
        
        # 镜头类型匹配
        if scores["shot_type_score"] > 0:
            reasons.append(f"镜头类型匹配: {segment.get('shot_type', '')}")
        
        # 情感标签匹配
        if scores["emotion_score"] > 0:
            emotional_tags = segment.get("emotional_tags", [])
            matching_tag = next((tag for tag in emotional_tags if scene.get("emotion", "").lower() in tag.lower()), None)
            if matching_tag:
                reasons.append(f"情感基调匹配: {matching_tag}")
        
        # 功能匹配
        if scores["function_score"] > 0:
            function = segment.get("shot_metadata", {}).get("function", "")
            reasons.append(f"功能匹配: {function}")
        
        # 内容匹配
        if scores["content_score"] > 0:
            # 找出匹配的关键元素
            matched_elements = []
            if "key_elements" in scene and isinstance(scene["key_elements"], list):
                for element in scene["key_elements"]:
                    if element.lower() in segment.get("searchable_text", "").lower():
                        matched_elements.append(element)
            
            if matched_elements:
                reasons.append(f"包含关键元素: {', '.join(matched_elements[:3])}")
            
            # 找出匹配的视觉对象
            matched_objects = []
            if "visual_objects" in scene and isinstance(scene["visual_objects"], list) and "shot_metadata" in segment and "objects" in segment["shot_metadata"]:
                segment_objects = [obj.lower() for obj in segment["shot_metadata"]["objects"]]
                for obj in scene["visual_objects"]:
                    if obj.lower() in segment_objects or any(obj.lower() in seg_obj for seg_obj in segment_objects):
                        matched_objects.append(obj)
            
            if matched_objects:
                reasons.append(f"包含视觉对象: {', '.join(matched_objects[:3])}")
        
        # 时长匹配
        if scores["duration_score"] > 0.05:  # 只有高分才提及
            reasons.append(f"片段时长合适: {segment.get('duration', 0):.1f}秒")
        
        return reasons
    
    def _generate_shotlist(self, matching_results: List[Dict[str, Any]], script_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成最终分镜表
        
        参数:
        matching_results: 匹配结果列表
        script_analysis: 脚本分析结果
        
        返回:
        分镜表
        """
        shotlist_scenes = []
        total_duration = 0
        
        for i, result in enumerate(matching_results):
            scene = result["scene"]
            matches = result["matches"]
            
            if not matches:
                # 如果没有匹配结果，添加占位信息
                shotlist_scenes.append({
                    "scene_number": i + 1,
                    "scene_id": scene.get("id", f"场景{i+1}"),
                    "scene_description": scene["description"],
                    "status": "未找到匹配片段",
                    "requirements": {
                        "shot_type": scene.get("shot_type_preference", ""),
                        "emotion": scene.get("emotion", ""),
                        "key_elements": scene.get("key_elements", [])
                    }
                })
                continue
            
            # 获取最佳匹配
            best_match = matches[0]
            alternatives = matches[1:3] if len(matches) > 1 else []
            
            # 计算段落时长
            clip_duration = best_match.get("end_time", 0) - best_match.get("start_time", 0)
            total_duration += clip_duration
            
            # 添加到分镜表
            shotlist_scenes.append({
                "scene_number": i + 1,
                "scene_id": scene.get("id", f"场景{i+1}"),
                "scene_description": scene["description"],
                "selected_clip": {
                    "video_id": str(best_match["video_id"]),
                    "segment_id": str(best_match["_id"]) if "_id" in best_match else "",
                    "start_time": best_match["start_time"],
                    "end_time": best_match["end_time"],
                    "duration": round(clip_duration, 2),
                    "shot_type": best_match.get("shot_type", ""),
                    "shot_description": best_match.get("shot_description", ""),
                    "similarity_score": round(best_match.get("final_score", 0), 2),
                    "match_reasons": best_match.get("match_reasons", [])
                },
                "alternatives": [
                    {
                        "video_id": str(alt["video_id"]),
                        "segment_id": str(alt["_id"]) if "_id" in alt else "",
                        "start_time": alt["start_time"],
                        "end_time": alt["end_time"],
                        "duration": round(alt["end_time"] - alt["start_time"], 2),
                        "shot_type": alt.get("shot_type", ""),
                        "similarity_score": round(alt.get("final_score", 0), 2)
                    } for alt in alternatives
                ]
            })
        
        # 构建完整分镜表
        return {
            "title": script_analysis.get("title", "未命名脚本"),
            "brand": script_analysis.get("brand", ""),
            "tonality": script_analysis.get("tonality", ""),
            "pace": script_analysis.get("pace", ""),
            "total_scenes": len(shotlist_scenes),
            "total_duration": round(total_duration, 1),
            "scenes": shotlist_scenes
        } 