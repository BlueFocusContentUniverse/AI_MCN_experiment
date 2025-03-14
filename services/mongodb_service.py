import os
from typing import Dict, Any, List, Optional, Union
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
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
        mongo_uri = os.environ.get('MONGODB_URI', "mongodb://localhost:27017/")
        if not mongo_uri:
            raise ValueError("MONGODB_URI environment variable is not set")
        
        logger.info(f"尝试连接到MongoDB: {mongo_uri}")
        
        # 创建MongoDB客户端，添加重试逻辑
        retry_count = 0
        while retry_count < max_retries:
            try:
                self.client = MongoClient(
                "mongodb://root:hdftk8l7@dbconn.sealosbja.site:38170/?directConnection=true",
                serverSelectionTimeoutMS=5000
            )
                # 测试连接
                self.client.admin.command('ping')
                logger.info("MongoDB连接成功")
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
        self.video_info: Collection = self.db['video_info']
        
        # 创建索引
        self._create_indexes()
    
    def _create_indexes(self):
        """创建必要的索引"""
        try:
            # 视频路径索引
            self.video_info.create_index("video_path", unique=True)
            
            # 内容标签索引
            self.video_info.create_index("content_tags")
            
            # 视觉特征索引
            self.video_info.create_index("visual_features.scene_type")
            
            # 品牌索引
            self.video_info.create_index("brand")
            
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
    
    def save_video_info(self, video_info: Dict[str, Any]) -> str:
        """
        保存视频信息到MongoDB
        
        参数:
        video_info: 视频信息字典
        
        返回:
        插入的文档ID
        """
        try:
            # 检查视频路径是否已存在
            existing_doc = self.video_info.find_one({"video_path": video_info["video_path"]})
            
            if existing_doc:
                # 如果已存在，则更新
                result = self.video_info.update_one(
                    {"_id": existing_doc["_id"]},
                    {"$set": video_info}
                )
                
                if result.modified_count == 1:
                    logger.info(f"更新文档成功: {existing_doc['_id']}")
                    return str(existing_doc["_id"])
                else:
                    logger.warning(f"未能更新文档: {existing_doc['_id']}")
                    return str(existing_doc["_id"])
            else:
                # 如果不存在，则插入
                # 首先确保数据可以被MongoDB序列化
                sanitized_info = self._sanitize_document(video_info)
                
                # 插入文档
                result = self.video_info.insert_one(sanitized_info)
                logger.info(f"插入文档成功: {result.inserted_id}")
                return str(result.inserted_id)
        except Exception as e:
            logger.error(f"保存到MongoDB时出错: {str(e)}")
            raise
    
    def update_video_embedding(self, video_id: str, embedding: List[float]) -> bool:
        """
        更新视频的嵌入向量
        
        参数:
        video_id: 视频ID
        embedding: 嵌入向量
        
        返回:
        更新是否成功
        """
        try:
            result = self.video_info.update_one(
                {"_id": video_id},
                {"$set": {"cinematography_embedding": embedding}}
            )
            
            if result.modified_count == 1:
                logger.info(f"更新视频嵌入向量成功: {video_id}")
                return True
            else:
                logger.warning(f"未能更新视频嵌入向量: {video_id}")
                return False
        except Exception as e:
            logger.error(f"更新视频嵌入向量时出错: {str(e)}")
            return False
    
    def find_video_by_path(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        根据视频路径查找视频信息
        
        参数:
        video_path: 视频文件路径
        
        返回:
        视频信息字典，如果未找到则返回None
        """
        result = self.video_info.find_one({"video_path": video_path})
        return result
    
    def search_videos_by_criteria(self, criteria: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        根据条件搜索视频
        
        参数:
        criteria: 搜索条件
        limit: 最大返回数量
        
        返回:
        符合条件的视频列表
        """
        results = self.video_info.find(criteria).limit(limit)
        return list(results)
    
    def vector_search(self, vector: List[float], pre_filter: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用向量相似度搜索视频
        
        参数:
        vector: 查询向量
        pre_filter: 预过滤条件
        limit: 最大返回数量
        
        返回:
        相似度最高的视频列表，每个视频包含similarity_score字段
        """
        try:
            # 构建查询条件
            query = {}
            if pre_filter:
                query.update(pre_filter)
            
            # 确保只查询有嵌入向量的文档
            query["cinematography_embedding"] = {"$exists": True}
            
            # 查询所有符合条件的视频
            videos = list(self.video_info.find(query))
            
            # 如果没有找到视频，返回空列表
            if not videos:
                logger.warning(f"未找到符合条件的视频: {pre_filter}")
                return []
            
            # 计算相似度
            results_with_scores = []
            for video in videos:
                if "cinematography_embedding" in video and video["cinematography_embedding"]:
                    # 计算余弦相似度
                    similarity = self._cosine_similarity(vector, video["cinematography_embedding"])
                    
                    # 添加相似度分数
                    video_copy = dict(video)
                    video_copy["similarity_score"] = similarity
                    results_with_scores.append(video_copy)
            
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