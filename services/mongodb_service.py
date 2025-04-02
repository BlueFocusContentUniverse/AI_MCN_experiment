import os
from typing import Dict, Any, List, Optional, Union, Tuple
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import OperationFailure, ConnectionFailure
from bson import ObjectId
from datetime import datetime
import time
import logging
import numpy as np

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MongoDBService:
    """MongoDB数据存储服务"""
    
    def __init__(self, max_retries=3):
        """初始化MongoDB连接"""
        # 从环境变量获取MongoDB连接信息
        username = os.environ.get("MONGODB_USERNAME")
        password = os.environ.get("MONGODB_PASSWORD")
        mongo_uri = "mongodb://username:password@localhost:27018/?directConnection=true"
        if not mongo_uri:
            raise ValueError("MONGODB_URI environment variable is not set")
        
        # 检查URI中是否包含用户名和密码
        has_credentials = "@" in mongo_uri and not ("username:password@" in mongo_uri)
        if not has_credentials:
            logger.warning("警告: MongoDB URI 可能使用默认的用户名和密码")
        
        logger.info(f"尝试连接到MongoDB: {mongo_uri}")
        
        # 创建MongoDB客户端，添加重试逻辑
        retry_count = 0
        while retry_count < max_retries:
            try:
                # 解析URL中的端口号以便进行验证
                parsed_uri = mongo_uri.split('@')
                server_part = parsed_uri[-1].split('/')[0]
                host_port = server_part.split('?')[0]
                expected_port = "27017"  # 默认端口
                if ":" in host_port:
                    expected_port = host_port.split(':')[-1]
                
                # 确保使用正确的端口和连接参数
                self.client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=5000,
                    directConnection=True,
                    socketTimeoutMS=20000,
                    connectTimeoutMS=20000
                )
                # 测试连接
                self.client.admin.command('ping')
                
                # 验证连接的端口
                actual_port = str(self.client.PORT)
                if actual_port != expected_port:
                    logger.warning(f"警告: 连接成功但使用的端口与指定的不同 (指定: {expected_port}, 实际: {actual_port})")
                
                logger.info(f"MongoDB连接成功，服务器: {self.client.HOST}:{self.client.PORT}")
                break
            except Exception as e:
                retry_count += 1
                logger.warning(f"MongoDB连接失败 (尝试 {retry_count}/{max_retries}): {str(e)}")
                if retry_count >= max_retries:
                    raise
                time.sleep(2)  # 等待2秒后重试
        
        # 获取数据库
        db_name = os.environ.get('MONGODB_DB', 'test_mcn')
        logger.info(f"使用数据库: {db_name}")
        self.db: Database = self.client[db_name]
        
        # 获取集合
        self.videos: Collection = self.db['videos']        # 视频基本信息和整体分析
        self.video_segments: Collection = self.db['video_segments']  # 视频分段详细信息
        
        # 创建索引 - 捕获可能的认证错误
        try:
            self._create_indexes()
        except OperationFailure as e:
            if "requires authentication" in str(e) or "not authorized" in str(e):
                logger.error(f"创建索引时认证失败: {str(e)}")
                raise ValueError(f"MongoDB认证失败，请检查用户名、密码和权限: {str(e)}")
            else:
                logger.error(f"创建索引时发生错误: {str(e)}")
                raise
    
    def _create_indexes(self):
        """创建必要的索引"""
        try:
            # videos集合的索引
            self.videos.create_index("file_info.path", unique=True)
            self.videos.create_index("metadata.video_type")
            self.videos.create_index("metadata.upload_date")
            self.videos.create_index("metadata.tags")
            self.videos.create_index("metadata.brand")
            
            # video_segments集合的索引
            self.video_segments.create_index("video_id")
            self.video_segments.create_index("start_time")
            self.video_segments.create_index("shot_type")
            self.video_segments.create_index("time_bucket")  # 添加时间分桶索引
            self.video_segments.create_index("duration")  # 添加时长索引
            self.video_segments.create_index("emotional_tags")  # 添加情感标签索引
            self.video_segments.create_index("feature_tags")  # 添加功能标签索引
            self.video_segments.create_index({
                "video_id": 1,
                "cinematic_language.perspective": 1,
                "cinematic_language.shot_size": 1
            })
            
            # 创建复合索引
            self.video_segments.create_index([
                ("shot_type", 1),
                ("emotional_tags", 1),
                ("time_bucket", 1)
            ])
            
            # 为视频片段创建文本索引
            self.video_segments.create_index([("searchable_text", "text")])
            
            # 注释: 向量索引功能已移除，需要MongoDB 7.0+版本和Atlas集群支持
            # 我们使用应用层向量搜索服务代替MongoDB原生向量搜索
            
            logger.info("MongoDB索引创建成功")
        except Exception as e:
            logger.error(f"创建索引时出错: {str(e)}")
            # 继续执行，不要因为索引创建失败而中断程序
    
    def _sanitize_document(self, doc: Any) -> Any:
        """
        清理文档，确保可以被MongoDB序列化
        
        参数:
        doc: 需要清理的文档或文档的一部分
        
        返回:
        清理后的文档
        """
        if isinstance(doc, dict):
            # 处理字典
            sanitized_doc = {}
            for key, value in doc.items():
                # 跳过以$或.开头的键，MongoDB不允许这些键
                if key.startswith('$') or '.' in key:
                    continue
                
                # 递归清理值
                sanitized_value = self._sanitize_document(value)
                sanitized_doc[key] = sanitized_value
            
            return sanitized_doc
        elif isinstance(doc, list):
            # 处理列表
            return [self._sanitize_document(item) for item in doc]
        elif isinstance(doc, (str, int, float, bool, type(None))):
            # 基本类型直接返回
            return doc
        elif hasattr(doc, 'isoformat'):
            # 处理日期时间类型
            return doc.isoformat()
        else:
            # 其他类型转换为字符串
            try:
                return str(doc)
            except:
                return None
            
    def _create_empty_embeddings(self) -> Dict[str, List[float]]:
        """创建空的嵌入向量，为将来的向量检索做准备"""
        return {
            "visual_vector": [0] * 1536,
            "text_vector": [0] * 1536,
            "audio_vector": [0] * 1536,
            "fusion_vector": [0] * 1536  # 添加融合向量字段
        }
        
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词，用于文本搜索"""
        if not text:
            return []
            
        # 简单分词并过滤长度小于2的词
        words = text.split()
        return [word for word in words if len(word) > 2]
    
    def save_video_info(self, video_info: Dict[str, Any]) -> str:
        """
        将视频分析结果保存到MongoDB的videos和video_segments两个集合
        
        参数:
        video_info: 视频信息字典
        
        返回:
        插入的videos文档ID
        """
        try:
            # 开始一个会话，以便在事务中执行
            with self.client.start_session() as session:
                # 提取片段和事件数据
                segments = self._get_segments(video_info)
                key_events = self._get_key_events(video_info)
                
                # 计算片段摘要数据
                segments_summary = self._create_segments_summary(segments)
                
                # 准备视频主文档
                video_doc = {
                    "title": self._extract_title(video_info.get("video_path", "")),
                    "file_info": {
                        "path": video_info.get("video_path", ""),
                        "duration": self._calculate_duration(video_info),
                        "resolution": "1920x1080",  # 默认值，实际应从视频文件中提取
                        "format": "MP4",            # 默认值
                        "size_mb": 0                # 默认值
                    },
                    "metadata": {
                        "upload_date": datetime.now(),
                        "video_type": self._get_from_nested_dict(video_info, ["cinematography_analysis", "metadata", "video_type"], "未知"),
                        "analysis_version": self._get_from_nested_dict(video_info, ["cinematography_analysis", "metadata", "analysis_version"], "1.0"),
                        "tags": self._extract_tags(video_info),
                        "processed": True,
                        "brand": video_info.get("brand", "未知"),
                        "model": video_info.get("model", "")  # 从video_info中获取用户提供的型号
                    },
                    "content_overview": self._get_from_nested_dict(video_info, ["cinematography_analysis", "content_overview"], {}),
                    "theme_analysis": self._get_from_nested_dict(video_info, ["cinematography_analysis", "theme_analysis"], {}),
                    "emphasis_analysis": self._get_from_nested_dict(video_info, ["cinematography_analysis", "emphasis_analysis"], {}),
                    "overall_analysis": self._get_from_nested_dict(video_info, ["cinematography_analysis", "overall_analysis"], {}),
                    "segments_summary": segments_summary,  # 添加片段摘要数据
                    "stats": {
                        "segment_count": len(segments),
                        "key_events_count": len(key_events),
                        "total_duration": self._calculate_duration(video_info)
                    },
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
                
                # 添加嵌入向量到视频文档
                if "embeddings" in video_info and isinstance(video_info["embeddings"], dict):
                    video_doc["embeddings"] = video_info["embeddings"]
                    logger.info(f"添加视频级嵌入向量到视频文档")
                else:
                    video_doc["embeddings"] = self._create_empty_embeddings()
                    logger.info(f"使用空向量作为视频级嵌入向量")
                
                # 检查视频是否已存在
                existing_video = self.videos.find_one({"file_info.path": video_info.get("video_path", "")})
                
                if existing_video:
                    # 如果存在，则更新
                    video_id = existing_video["_id"]
                    self.videos.update_one(
                        {"_id": video_id},
                        {"$set": video_doc}
                    )
                    logger.info(f"更新视频文档: {video_id}")
                    
                    # 删除旧的片段
                    self.video_segments.delete_many({"video_id": video_id})
                    logger.info(f"删除视频 {video_id} 的旧片段")
                else:
                    # 插入新的视频文档
                    sanitized_video_doc = self._sanitize_document(video_doc)
                    result = self.videos.insert_one(sanitized_video_doc)
                    video_id = result.inserted_id
                    logger.info(f"插入新视频文档: {video_id}")
                
                # 准备并插入片段文档
                segment_docs = []
                
                for segment in segments:
                    # 找出属于这个片段的关键事件
                    segment_events = []
                    for event in key_events:
                        event_time = event.get("timestamp", 0)
                        if event_time >= segment.get("start_time", 0) and event_time <= segment.get("end_time", 0):
                            segment_events.append(event)
                    
                    # 提取对象和动作标签
                    extracted_objects, extracted_actions = self._extract_objects_and_actions(segment)
                    
                    # 准备搜索关键词
                    searchable_text = " ".join([
                        segment.get("shot_description", ""),
                        self._dict_to_str(segment.get("visual_elements", {})),
                        self._dict_to_str(segment.get("audio_analysis", {}))
                    ])
                    
                    # 创建片段文档
                    segment_doc = {
                        "video_id": video_id,
                        "start_time": segment.get("start_time", 0),
                        "end_time": segment.get("end_time", 0),
                        "duration": segment.get("end_time", 0) - segment.get("start_time", 0),
                        "time_bucket": self._get_time_bucket(segment.get("start_time", 0)),
                        "shot_type": segment.get("shot_type", ""),
                        "shot_description": segment.get("shot_description", ""),
                        "shot_metadata": {
                            "type": segment.get("shot_type", ""),
                            "objects": extracted_objects,
                            "actions": extracted_actions,
                            "function": self._determine_shot_function(segment)
                        },
                        "visual_elements": segment.get("visual_elements", {}),
                        "cinematic_language": segment.get("cinematic_language", {}),
                        "narrative_structure": segment.get("narrative_structure", ""),
                        "audio_analysis": segment.get("audio_analysis", {}),
                        "subject_focus": segment.get("subject_focus", {}),
                        "key_events": segment_events,
                        "feature_tags": self._extract_feature_tags(segment),
                        "emotional_tags": self._extract_emotional_tags(segment),
                        "searchable_text": searchable_text,
                        "thumbnail_url": f"/thumbnails/{video_id}_{segment.get('start_time', 0)}.jpg",
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    }
                    
                    # 添加嵌入向量
                    # 首先检查片段是否有自己的嵌入向量
                    if "embeddings" in segment and isinstance(segment["embeddings"], dict):
                        segment_doc["embeddings"] = segment["embeddings"]
                    # 否则，使用视频级的嵌入向量（适用于所有片段共享相同嵌入向量的情况）
                    elif "embeddings" in video_info and isinstance(video_info["embeddings"], dict):
                        segment_doc["embeddings"] = video_info["embeddings"]
                        logger.debug(f"使用视频级嵌入向量作为片段 {segment.get('start_time')} 的嵌入向量")
                    # 如果都没有，使用空向量
                    else:
                        segment_doc["embeddings"] = self._create_empty_embeddings()
                        logger.debug(f"使用空向量作为片段 {segment.get('start_time')} 的嵌入向量")
                    
                    segment_docs.append(self._sanitize_document(segment_doc))
                
                # 批量插入片段文档
                if segment_docs:
                    self.video_segments.insert_many(segment_docs)
                    logger.info(f"插入{len(segment_docs)}个片段文档")
                
                # 记录嵌入向量信息
                if "embeddings" in video_info and isinstance(video_info["embeddings"], dict):
                    vectors_info = ', '.join([f"{k}: {'有效' if v and len(v) > 0 else '空'}" 
                                           for k, v in video_info["embeddings"].items()])
                    logger.info(f"嵌入向量信息: {vectors_info}")
                
                return str(video_id)
                
        except Exception as e:
            logger.error(f"保存视频信息到MongoDB时出错: {str(e)}")
            raise
    
    def _extract_title(self, file_path: str) -> str:
        """从文件路径中提取视频标题"""
        if not file_path:
            return "未知视频"
        
        # 提取文件名，不包含扩展名
        file_name = os.path.basename(file_path)
        title = os.path.splitext(file_name)[0]
        
        # 替换下划线和连字符为空格
        title = title.replace('_', ' ').replace('-', ' ')
        
        return title
    
    def _calculate_duration(self, video_info: Dict[str, Any]) -> float:
        """计算视频总时长"""
        segments = self._get_segments(video_info)
        if not segments:
            return 0.0
            
        # 使用最后一个片段的结束时间作为总时长
        max_end_time = 0.0
        for segment in segments:
            end_time = segment.get("end_time", 0.0)
            if end_time > max_end_time:
                max_end_time = end_time
                
        return max_end_time
    
    def _get_segments(self, video_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从视频信息中获取片段列表"""
        if "cinematography_analysis" in video_info and "segments" in video_info["cinematography_analysis"]:
            return video_info["cinematography_analysis"]["segments"]
        return []
    
    def _get_key_events(self, video_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从视频信息中获取关键事件列表"""
        if "cinematography_analysis" in video_info and "key_events" in video_info["cinematography_analysis"]:
            return video_info["cinematography_analysis"]["key_events"]
        return []
    
    def _extract_tags(self, video_info: Dict[str, Any]) -> List[str]:
        """从视频信息中提取标签"""
        tags = set()
        
        # 从视觉分析中提取标签
        if "vision_analysis" in video_info:
            vision = video_info["vision_analysis"]
            for key in ["scene_types", "objects", "car_features"]:
                if key in vision and isinstance(vision[key], list):
                    tags.update(vision[key])
        
        # 从电影摄影分析中提取标签
        if "cinematography_analysis" in video_info:
            cinema = video_info["cinematography_analysis"]
            # 从emphasis_analysis中提取
            if "emphasis_analysis" in cinema and "repeated_elements" in cinema["emphasis_analysis"]:
                tags.update(cinema["emphasis_analysis"]["repeated_elements"])
            
            # 从overall_analysis中提取
            if "overall_analysis" in cinema:
                overall = cinema["overall_analysis"]
                for key in ["visual_style", "narrative_approach", "color_palette"]:
                    if key in overall and overall[key]:
                        tags.add(overall[key])
        
        return list(tags)
    
    def _get_from_nested_dict(self, d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
        """从嵌套字典中安全地获取值"""
        current = d
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def _dict_to_str(self, d: Dict[str, Any]) -> str:
        """将字典转换为空格分隔的字符串，用于全文搜索"""
        result = []
        
        def _extract_values(obj, result_list):
            if isinstance(obj, dict):
                for val in obj.values():
                    _extract_values(val, result_list)
            elif isinstance(obj, list):
                for item in obj:
                    _extract_values(item, result_list)
            elif isinstance(obj, str):
                result_list.append(obj)
            elif obj is not None:
                result_list.append(str(obj))
        
        _extract_values(d, result)
        return " ".join(result)
    
    def find_video_by_path(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        根据视频路径查找视频信息
        
        参数:
        video_path: 视频文件路径
        
        返回:
        视频信息字典，如果未找到则返回None
        """
        video = self.videos.find_one({"file_info.path": video_path})
        if not video:
            return None
            
        # 查询该视频的所有片段
        segments = list(self.video_segments.find({"video_id": video["_id"]}).sort("start_time", 1))
        
        # 构建完整的视频信息
        video_info = dict(video)
        
        # 构建 cinematography_analysis 结构，以兼容旧代码
        cinematography_analysis = {
            "metadata": video_info.get("metadata", {}),
            "content_overview": video_info.get("content_overview", {}),
            "theme_analysis": video_info.get("theme_analysis", {}),
            "emphasis_analysis": video_info.get("emphasis_analysis", {}),
            "overall_analysis": video_info.get("overall_analysis", {}),
            "segments": segments,
            "key_events": self._extract_all_events(segments)
        }
        
        video_info["video_path"] = video_info.get("file_info", {}).get("path", "")
        video_info["cinematography_analysis"] = cinematography_analysis
        
        return video_info
    
    def _extract_all_events(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从所有片段中提取所有关键事件"""
        events = []
        for segment in segments:
            if "key_events" in segment and isinstance(segment["key_events"], list):
                events.extend(segment["key_events"])
        
        # 按时间戳排序
        return sorted(events, key=lambda x: x.get("timestamp", 0))
    
    def update_segment_embedding(self, segment_id: str, embedding_type: str, embedding: List[float]) -> bool:
        """
        更新视频片段的嵌入向量
        
        参数:
        segment_id: 片段ID
        embedding_type: 嵌入向量类型 (visual_vector, text_vector, audio_vector)
        embedding: 嵌入向量
        
        返回:
        更新是否成功
        """
        try:
            embedding_key = f"embeddings.{embedding_type}"
            result = self.video_segments.update_one(
                {"_id": ObjectId(segment_id)},
                {"$set": {embedding_key: embedding}}
            )
            
            if result.modified_count == 1:
                logger.info(f"更新片段嵌入向量成功: {segment_id}, 类型: {embedding_type}")
                return True
            else:
                logger.warning(f"未能更新片段嵌入向量: {segment_id}")
                return False
        except Exception as e:
            logger.error(f"更新片段嵌入向量时出错: {str(e)}")
            return False
    
    def vector_search(self, embedding_type: str, vector: List[float], pre_filter: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用向量相似度搜索视频片段
        
        注意: 此方法已被应用层向量搜索服务(VectorSearchService)替代，
        保留此方法仅作为备份或在应用层服务不可用时使用。
        推荐使用 VectorSearchService.search_similar_vectors 方法。
        
        参数:
        embedding_type: 嵌入向量类型 (visual_vector, text_vector, audio_vector)
        vector: 查询向量
        pre_filter: 预过滤条件
        limit: 最大返回数量
        
        返回:
        相似度最高的视频片段列表，每个片段包含similarity_score字段
        """
        logger.warning("正在使用弃用的vector_search方法，建议使用VectorSearchService.search_similar_vectors")
        try:
            # 构建查询条件
            query = {}
            if pre_filter:
                query.update(pre_filter)
            
            # 确保只查询有嵌入向量的文档
            embedding_key = f"embeddings.{embedding_type}"
            query[embedding_key] = {"$exists": True}
            
            # 查询所有符合条件的片段
            segments = list(self.video_segments.find(query))
            
            # 如果没有找到片段，返回空列表
            if not segments:
                logger.warning(f"未找到符合条件的视频片段: {pre_filter}")
                return []
            
            # 计算相似度
            results_with_scores = []
            for segment in segments:
                if "embeddings" in segment and embedding_type in segment["embeddings"]:
                    # 计算余弦相似度
                    segment_vector = segment["embeddings"][embedding_type]
                    similarity = self._cosine_similarity(vector, segment_vector)
                    
                    # 添加相似度分数
                    segment_copy = dict(segment)
                    segment_copy["similarity_score"] = similarity
                    results_with_scores.append(segment_copy)
            
            # 按相似度降序排序
            results_with_scores.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # 限制返回数量
            return results_with_scores[:limit]
        except Exception as e:
            logger.error(f"向量搜索时出错: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        参数:
        vec1: 第一个向量
        vec2: 第二个向量
        
        返回:
        余弦相似度，范围为[-1, 1]
        """
        # 转换为numpy数组
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        # 计算余弦相似度
        dot_product = np.dot(vec1_np, vec2_np)
        norm_vec1 = np.linalg.norm(vec1_np)
        norm_vec2 = np.linalg.norm(vec2_np)
        
        # 避免除以零
        if norm_vec1 == 0 or norm_vec2 == 0:
            return 0.0
        
        similarity = dot_product / (norm_vec1 * norm_vec2)
        return float(similarity)
    
    def close(self):
        """关闭MongoDB连接"""
        if self.client:
            self.client.close()
    
    def text_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用文本搜索查找视频片段
        
        参数:
        query: 搜索查询
        limit: 最大返回结果数
        
        返回:
        匹配的片段列表
        """
        try:
            # 执行文本搜索
            results = list(self.video_segments.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit))
            
            # 添加视频信息
            for result in results:
                video = self.videos.find_one({"_id": result["video_id"]})
                if video:
                    result["video_info"] = {
                        "title": video.get("title", "未知视频"),
                        "brand": video.get("metadata", {}).get("brand", ""),
                        "video_type": video.get("metadata", {}).get("video_type", "")
                    }
            
            return results
        except Exception as e:
            logger.error(f"执行文本搜索时出错: {str(e)}")
            return []
            
    def update_embeddings(self, embedding_service, video_id: str = None) -> bool:
        """
        更新视频和片段的嵌入向量
        
        参数:
        embedding_service: 嵌入服务实例
        video_id: 需要更新的视频ID，如果为None则更新所有视频
        
        返回:
        是否成功更新
        """
        try:
            # 过滤条件
            filter_query = {}
            if video_id:
                try:
                    # 转换为ObjectId
                    object_id = ObjectId(video_id)
                    filter_query = {"_id": object_id}
                except Exception as e:
                    logger.error(f"转换视频ID为ObjectId时出错: {str(e)}")
                    return False
            
            # 查询需要更新的视频
            videos = list(self.videos.find(filter_query))
            if not videos:
                logger.warning(f"未找到需要更新的视频: {filter_query}")
                return False
            
            logger.info(f"开始更新 {len(videos)} 个视频的嵌入向量")
            
            # 遍历视频
            for video in videos:
                video_id = video["_id"]
                logger.info(f"处理视频 {video_id}")
                
                # 获取视频类型用于权重分配
                video_type = self._determine_video_type(video)
                logger.info(f"识别到视频类型: {video_type}")
                
                # 获取与视频类型相对应的权重
                weights = self._get_weights_by_video_type(video_type)
                
                # 查询视频的所有片段
                segments = list(self.video_segments.find({"video_id": video_id}))
                logger.info(f"找到 {len(segments)} 个片段")
                
                # 更新片段向量
                updated_segments = []
                for segment in segments:
                    # 确定片段类型，可能与整体视频类型不同
                    segment_type = self._determine_segment_type(segment)
                    segment_weights = self._get_weights_by_video_type(segment_type)
                    
                    # 更新片段向量
                    updated_segment = embedding_service.update_segment_vectors(segment, segment_weights)
                    updated_segments.append(updated_segment)
                    
                    # 更新数据库中的片段
                    self.video_segments.update_one(
                        {"_id": segment["_id"]},
                        {"$set": {"embeddings": updated_segment["embeddings"]}}
                    )
                
                # 更新视频向量
                updated_video = embedding_service.update_video_vectors(video, updated_segments, weights)
                
                # 更新数据库中的视频
                self.videos.update_one(
                    {"_id": video_id},
                    {"$set": {"embeddings": updated_video["embeddings"]}}
                )
                
                logger.info(f"视频 {video_id} 的嵌入向量更新完成")
            
            logger.info("所有嵌入向量更新完成")
            return True
            
        except Exception as e:
            logger.error(f"更新嵌入向量时出错: {str(e)}")
            return False
    
    def _determine_video_type(self, video: Dict[str, Any]) -> str:
        """
        确定视频类型，用于权重分配
        
        参数:
        video: 视频文档
        
        返回:
        视频类型: "画面丰富型" 或 "人物访谈型"
        """
        # 检查元数据中是否已明确指定视频类型
        video_type = video.get("metadata", {}).get("video_type", "")
        if video_type:
            if "人物访谈" in video_type or "访谈" in video_type or "采访" in video_type:
                return "人物访谈型"
            elif "画面丰富" in video_type:
                return "画面丰富型"
        
        # 检查overall_analysis中的信息
        overall_analysis = video.get("overall_analysis", {})
        narrative = overall_analysis.get("narrative_approach", "")
        if "信息传达" in narrative or "证言" in narrative:
            return "人物访谈型"
        
        # 检查content_overview中的信息
        content = video.get("content_overview", {}).get("main_content", "")
        if "访谈" in content or "采访" in content or "讲解" in content:
            return "人物访谈型"
        
        # 默认为画面丰富型
        return "画面丰富型"
    
    def _determine_segment_type(self, segment: Dict[str, Any]) -> str:
        """
        确定片段类型，用于权重分配
        
        参数:
        segment: 片段文档
        
        返回:
        片段类型: "画面丰富型" 或 "人物访谈型"
        """
        # 检查shot_type
        shot_type = segment.get("shot_type", "").lower()
        description = segment.get("shot_description", "").lower()
        
        # 检查是否是人物相关镜头
        if ("人物" in description or "采访" in description or "讲话" in description or 
            "对话" in description or "特写" in shot_type and "人" in description):
            return "人物访谈型"
        
        # 检查情感标签
        emotional_tags = segment.get("emotional_tags", [])
        person_emotions = ["专注", "思考", "讲解", "严肃", "专业"]
        if any(emotion in emotional_tags for emotion in person_emotions):
            return "人物访谈型"
        
        # 检查音频分析
        audio = segment.get("audio_analysis", {})
        speech_content = audio.get("speech_content", "")
        if speech_content and len(speech_content) > 100:  # 长对话内容
            return "人物访谈型"
        
        # 检查功能
        function = segment.get("shot_metadata", {}).get("function", "")
        if "信息传达" in function or "讲解" in function:
            return "人物访谈型"
        
        # 默认为画面丰富型
        return "画面丰富型"
    
    def _get_weights_by_video_type(self, video_type: str) -> Dict[str, float]:
        """
        根据视频类型获取适当的向量权重
        
        参数:
        video_type: 视频类型
        
        返回:
        权重字典
        """
        if video_type == "画面丰富型":
            return {
                "visual_vector": 0.8,
                "text_vector": 0.1,
                "audio_vector": 0.1
            }
        elif video_type == "人物访谈型":
            return {
                "text_vector": 0.7,
                "audio_vector": 0.2,
                "visual_vector": 0.1
            }
        else:
            # 默认平衡权重
            return {
                "text_vector": 0.4,
                "visual_vector": 0.3,
                "audio_vector": 0.3
            }
    
    def search_segments_by_criteria(self, criteria: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        根据条件搜索视频片段
        
        参数:
        criteria: 搜索条件
        limit: 最大返回数量
        
        返回:
        符合条件的视频片段列表
        """
        results = self.video_segments.find(criteria).limit(limit)
        return list(results)
    
    def get_video_segments(self, video_id: str) -> List[Dict[str, Any]]:
        """
        获取特定视频的所有片段，按时间排序
        
        参数:
        video_id: 视频ID
        
        返回:
        视频片段列表
        """
        segments = self.video_segments.find({"video_id": ObjectId(video_id)}).sort("start_time", 1)
        return list(segments)
    
    def search_segments_by_type(self, shot_type: str, perspective: str) -> List[Dict[str, Any]]:
        """
        根据拍摄类型和视角搜索片段
        
        参数:
        shot_type: 拍摄类型
        perspective: 视角
        
        返回:
        符合条件的视频片段列表
        """
        segments = self.video_segments.find({
            "shot_type": shot_type,
            "cinematic_language.perspective": perspective
        })
        return list(segments)
    
    def _ensure_absolute_path(self, path: str) -> str:
        """确保路径是绝对路径"""
        if not path:
            return path
        if os.path.isabs(path):
            return path
        # 假设有一个基础目录
        base_dir = os.environ.get('VIDEO_BASE_DIR', '/path/to/videos')
        return os.path.join(base_dir, path)
    
    def _extract_objects_and_actions(self, segment: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """从片段中提取物体和动作标签"""
        objects = []
        actions = []
        
        # 从shot_description中尝试提取对象和动作
        description = segment.get("shot_description", "")
        if description:
            # 简单的对象提取（名词可能是对象）
            # 这里只是简单实现，实际应用可能需要更复杂的NLP处理
            words = description.split()
            for word in words:
                if len(word) > 3:  # 简单过滤，长度大于3的词可能是物体
                    objects.append(word)
        
        # 从visual_elements中提取信息
        if "composition" in segment.get("visual_elements", {}):
            comp = segment["visual_elements"]["composition"]
            if comp:
                words = comp.split()
                for word in words:
                    if len(word) > 3:
                        objects.append(word)
        
        # 从subject_focus中提取信息
        subject = segment.get("subject_focus", {}).get("subject", "")
        if subject:
            objects.append(subject)
        
        # 去重并限制列表长度
        objects = list(set(objects))[:10]  # 最多保留10个物体
        actions = list(set(actions))[:5]   # 最多保留5个动作
        
        return objects, actions
    
    def _determine_shot_function(self, segment: Dict[str, Any]) -> str:
        """确定镜头功能"""
        # 从描述和其他字段推断镜头功能
        shot_type = segment.get("shot_type", "").lower()
        description = segment.get("shot_description", "").lower()
        
        # 功能映射字典
        function_keywords = {
            "产品展示": ["展示", "特写", "产品", "外观", "设计"],
            "功能演示": ["功能", "演示", "操作", "使用", "效果"],
            "场景氛围": ["场景", "环境", "氛围", "周围", "背景"],
            "情感表达": ["情感", "表情", "反应", "感受"],
            "动作展示": ["动作", "行动", "移动", "驾驶", "操作"]
        }
        
        # 分数计算
        function_scores = {function: 0 for function in function_keywords}
        
        for function, keywords in function_keywords.items():
            for keyword in keywords:
                if keyword in shot_type or keyword in description:
                    function_scores[function] += 1
        
        # 返回得分最高的功能，如果都是0则返回"未知"
        max_function = max(function_scores.items(), key=lambda x: x[1])
        if max_function[1] > 0:
            return max_function[0]
        else:
            return "未知"
    
    def _get_time_bucket(self, start_time: float) -> str:
        """获取时间分桶，将时间划分为5秒区间"""
        bucket_size = 5  # 5秒一个桶
        bucket_start = int(start_time / bucket_size) * bucket_size
        bucket_end = bucket_start + bucket_size
        return f"{bucket_start}-{bucket_end}s"
    
    def _create_segments_summary(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建片段摘要数据"""
        if not segments:
            return {
                "total_segments": 0,
                "time_ranges": [],
                "dominant_emotions": [],
                "shot_types": []
            }
        
        # 收集时间范围
        time_ranges = []
        for segment in segments:
            start_time = segment.get("start_time", 0)
            end_time = segment.get("end_time", 0)
            if start_time is not None and end_time is not None:
                time_ranges.append([start_time, end_time])
        
        # 收集情感标签
        emotions = []
        for segment in segments:
            emotion = segment.get("visual_elements", {}).get("emotion", "")
            if emotion:
                emotions.extend(emotion.split('、'))
                emotions.extend(emotion.split(','))
                emotions.extend(emotion.split('，'))
        
        # 收集镜头类型
        shot_types = [segment.get("shot_type", "") for segment in segments if segment.get("shot_type")]
        
        # 统计出现频率
        emotion_counts = {}
        for emotion in emotions:
            emotion = emotion.strip()
            if emotion:
                emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
        
        shot_type_counts = {}
        for shot_type in shot_types:
            shot_type = shot_type.strip()
            if shot_type:
                shot_type_counts[shot_type] = shot_type_counts.get(shot_type, 0) + 1
        
        # 获取主要情感（出现次数最多的前5个）
        dominant_emotions = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)
        dominant_emotions = [emotion for emotion, count in dominant_emotions[:5]]
        
        # 获取主要镜头类型（出现次数最多的前5个）
        dominant_shot_types = sorted(shot_type_counts.items(), key=lambda x: x[1], reverse=True)
        dominant_shot_types = [shot_type for shot_type, count in dominant_shot_types[:5]]
        
        return {
            "total_segments": len(segments),
            "time_ranges": time_ranges,
            "dominant_emotions": dominant_emotions,
            "shot_types": dominant_shot_types
        }
    
    def _extract_feature_tags(self, segment: Dict[str, Any]) -> List[str]:
        """从片段中提取功能标签"""
        tags = []
        
        # 从shot_description中提取关键词
        description = segment.get("shot_description", "")
        if description:
            # 查找产品功能相关词汇
            feature_keywords = ["展示", "功能", "性能", "特性", "效果", "质量", "设计", "外观", "内饰"]
            for keyword in feature_keywords:
                if keyword in description:
                    tags.append(keyword)
        
        # 从subject_focus中提取
        subject = segment.get("subject_focus", {}).get("subject", "")
        if subject:
            tags.append(subject)
        
        # 去重
        return list(set(tags))
    
    def _extract_emotional_tags(self, segment: Dict[str, Any]) -> List[str]:
        """从片段中提取情感标签"""
        tags = []
        
        # 从visual_elements中提取情感
        emotion = segment.get("visual_elements", {}).get("emotion", "")
        if emotion:
            # 拆分情感标签（可能有多个情感用顿号或逗号分隔）
            emotions = emotion.split('、')
            emotions.extend(emotion.split(','))
            emotions.extend(emotion.split('，'))
            
            # 清理并添加到标签
            for e in emotions:
                e = e.strip()
                if e:
                    tags.append(e)
        
        # 去重
        return list(set(tags))

if __name__ == "__main__":
    """
    测试MongoDB连接和基本功能
    
    使用方法:
    1. 设置环境变量 MONGODB_URI 和 MONGODB_DB (可选)
    2. 运行此文件: python mongodb_service.py
    """
    try:
        # 获取和显示配置的MongoDB URI
        mongo_uri = os.environ.get('MONGODB_URI', "mongodb://username:password@localhost:27018/?directConnection=true&connect=direct")
        
        # 隐藏URI中的密码用于显示
        display_uri = mongo_uri
        if "@" in mongo_uri:
            parts = mongo_uri.split("@")
            auth_part = parts[0]
            if ":" in auth_part:
                username = auth_part.split(":")[0].replace("mongodb://", "")
                display_uri = f"mongodb://{username}:******@{parts[1]}"
        
        print(f"配置的MongoDB URI: {display_uri}")
        
        # 检查认证信息
        if "username:password@" in mongo_uri:
            print("警告: 使用默认用户名和密码！请设置正确的MongoDB认证信息")
        
        # 解析端口信息
        try:
            parsed_uri = mongo_uri.split('@')
            server_part = parsed_uri[-1].split('/')[0]
            host_port = server_part.split('?')[0]
            if ":" in host_port:
                host, port = host_port.split(':')
                print(f"配置的连接信息 - 主机: {host}, 端口: {port}")
            else:
                print(f"配置的连接信息 - 主机: {host_port}, 端口: 默认(27017)")
        except Exception as e:
            print(f"解析URI时出错: {str(e)}")
        
        # 尝试创建服务实例
        print("\n正在测试MongoDB连接...")
        mongo_service = MongoDBService()
        
        # 显示实际连接信息
        print(f"\n实际连接信息:")
        print(f"- 主机: {mongo_service.client.HOST}")
        print(f"- 端口: {mongo_service.client.PORT}")
        print(f"- 连接选项: {mongo_service.client.options}")
        
        try:
            # 测试认证 - 尝试列出所有数据库
            print("\n测试认证和权限...")
            dbs = mongo_service.client.list_database_names()
            print(f"认证成功! 可访问的数据库: {', '.join(dbs)}")
            
            # 获取数据库信息
            db_stats = mongo_service.db.command("dbStats")
            print(f"\n数据库统计信息:")
            print(f"- 数据库名称: {mongo_service.db.name}")
            print(f"- 集合数量: {db_stats.get('collections', 0)}")
            print(f"- 文档总数: {db_stats.get('objects', 0)}")
            print(f"- 数据库大小: {db_stats.get('dataSize', 0) / (1024 * 1024):.2f} MB")
            
            # 获取集合计数
            videos_count = mongo_service.videos.count_documents({})
            segments_count = mongo_service.video_segments.count_documents({})
            print(f"\n集合统计信息:")
            print(f"- videos集合: {videos_count} 条记录")
            print(f"- video_segments集合: {segments_count} 条记录")
            
            if videos_count > 0:
                # 获取最新的视频记录
                latest_video = mongo_service.videos.find_one(
                    sort=[("created_at", -1)]
                )
                if latest_video:
                    print(f"\n最新视频记录:")
                    print(f"- 标题: {latest_video.get('title', '未知')}")
                    print(f"- 文件路径: {latest_video.get('file_info', {}).get('path', '未知')}")
                    print(f"- 创建时间: {latest_video.get('created_at', '未知')}")
        
        except OperationFailure as e:
            print(f"\n认证或权限错误: {str(e)}")
            print("\n可能的解决方案:")
            print("1. 检查MongoDB URI中的用户名和密码是否正确")
            print("2. 确保该用户有对应数据库的读写权限")
            print("3. 在MongoDB中运行: db.createUser({user:'用户名',pwd:'密码',roles:[{role:'readWrite',db:'数据库名'}]})")
        
        # 关闭连接
        mongo_service.close()
        print("\nMongoDB连接测试完成!\n")
        
    except ConnectionFailure as e:
        print(f"\n连接失败: {str(e)}")
        print("\n可能的解决方案:")
        print("1. 确保MongoDB服务正在运行")
        print("2. 检查主机名和端口是否正确")
        print("3. 检查网络配置和防火墙设置")
    except ValueError as e:
        print(f"\n配置错误: {str(e)}")
    except Exception as e:
        print(f"\n测试MongoDB连接时出错: {str(e)}")
        import traceback
        print(traceback.format_exc()) 