import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import logging

# 导入现有的MongoDB服务以重用连接
from services.mongodb_service import MongoDBService
from streamlit_app.config import MONGODB_URI, MONGODB_DB, TASK_COLLECTION

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskManagerService:
    """视频分析任务管理服务"""
    
    def __init__(self):
        """初始化任务管理服务"""
        try:
            # 尝试复用现有的MongoDB连接
            self.mongodb_service = MongoDBService()
            self.db = self.mongodb_service.db
            self.task_collection = self.db[TASK_COLLECTION]
            logger.info("任务管理服务初始化成功")
        except Exception as e:
            logger.error(f"初始化任务管理服务时出错: {str(e)}")
            raise
    
    def create_task(self, task_name: str, videos: List[Dict[str, str]], config: Dict[str, Any]) -> str:
        """
        创建新任务
        
        参数:
        task_name: 任务名称
        videos: 视频列表，每个视频包含file_name和file_path
        config: 任务配置
        
        返回:
        任务ID
        """
        try:
            # 创建任务文档
            task = {
                "task_name": task_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "status": "pending",
                "progress": 0,
                "total_videos": len(videos),
                "processed_videos": 0,
                "failed_videos": 0,
                "config": config,
                "videos": []
            }
            
            # 添加视频信息
            for video in videos:
                task["videos"].append({
                    "file_name": video["file_name"],
                    "file_path": video["file_path"],
                    "status": "pending",
                    "video_id": None,
                    "error": None
                })
            
            # 插入任务文档
            result = self.task_collection.insert_one(task)
            task_id = str(result.inserted_id)
            
            logger.info(f"创建任务成功: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"创建任务时出错: {str(e)}")
            raise
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        
        参数:
        task_id: 任务ID
        
        返回:
        任务信息或None
        """
        try:
            # 转换为ObjectId
            object_id = ObjectId(task_id)
            
            # 查询任务
            task = self.task_collection.find_one({"_id": object_id})
            
            if task:
                # 添加ID字段为字符串
                task["_id"] = str(task["_id"])
                return task
            else:
                logger.warning(f"未找到任务: {task_id}")
                return None
            
        except Exception as e:
            logger.error(f"获取任务时出错: {str(e)}")
            return None
    
    def get_tasks(self, status: str = None, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """
        获取任务列表
        
        参数:
        status: 任务状态筛选
        limit: 最大返回数
        skip: 跳过的记录数
        
        返回:
        任务列表
        """
        try:
            # 创建筛选条件
            filters = {}
            if status:
                filters["status"] = status
            
            # 查询任务
            cursor = self.task_collection.find(filters).sort("created_at", DESCENDING).skip(skip).limit(limit)
            tasks = []
            
            # 处理结果
            for task in cursor:
                # 添加ID字段为字符串
                task["_id"] = str(task["_id"])
                tasks.append(task)
            
            return tasks
            
        except Exception as e:
            logger.error(f"获取任务列表时出错: {str(e)}")
            return []
    
    def update_task_status(self, task_id: str, status: str, progress: int = None) -> bool:
        """
        更新任务状态
        
        参数:
        task_id: 任务ID
        status: 新状态
        progress: 进度百分比
        
        返回:
        是否成功
        """
        try:
            # 转换为ObjectId
            object_id = ObjectId(task_id)
            
            # 创建更新文档
            update = {
                "status": status,
                "updated_at": datetime.now().isoformat()
            }
            
            if progress is not None:
                update["progress"] = progress
            
            # 如果状态为completed，检查是否有失败的视频
            if status == "completed":
                task = self.get_task(task_id)
                if task and task.get("failed_videos", 0) > 0:
                    update["status"] = "completed_with_errors"
            
            # 更新任务
            result = self.task_collection.update_one(
                {"_id": object_id},
                {"$set": update}
            )
            
            if result.modified_count == 1:
                logger.info(f"更新任务状态成功: {task_id} -> {status}")
                return True
            else:
                logger.warning(f"未能更新任务状态: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"更新任务状态时出错: {str(e)}")
            return False
    
    def update_video_status(self, task_id: str, video_index: int, status: str, video_id: str = None, error: str = None) -> bool:
        """
        更新视频状态
        
        参数:
        task_id: 任务ID
        video_index: 视频索引
        status: 新状态
        video_id: 视频ID，仅在状态为completed时需要
        error: 错误信息，仅在状态为failed时需要
        
        返回:
        是否成功
        """
        try:
            # 转换为ObjectId
            object_id = ObjectId(task_id)
            
            # 创建视频更新文档
            video_update = {
                f"videos.{video_index}.status": status
            }
            
            if video_id:
                video_update[f"videos.{video_index}.video_id"] = video_id
            
            if error:
                video_update[f"videos.{video_index}.error"] = error
            
            # 更新任务中的视频状态
            result = self.task_collection.update_one(
                {"_id": object_id},
                {"$set": video_update}
            )
            
            if result.modified_count != 1:
                logger.warning(f"未能更新视频状态: {task_id}, 索引: {video_index}")
                return False
            
            # 更新任务统计信息
            task = self.get_task(task_id)
            if not task:
                logger.warning(f"未找到任务: {task_id}")
                return False
            
            # 计算已处理和失败的视频数量
            processed = 0
            failed = 0
            for video in task["videos"]:
                if video["status"] in ["completed", "failed"]:
                    processed += 1
                if video["status"] == "failed":
                    failed += 1
            
            # 计算进度百分比
            total = len(task["videos"])
            progress = int((processed / total) * 100) if total > 0 else 0
            
            # 更新任务统计信息
            update = {
                "processed_videos": processed,
                "failed_videos": failed,
                "progress": progress,
                "updated_at": datetime.now().isoformat()
            }
            
            # 如果所有视频都已处理，更新任务状态
            if processed == total:
                if failed > 0:
                    update["status"] = "completed_with_errors"
                else:
                    update["status"] = "completed"
            
            result = self.task_collection.update_one(
                {"_id": object_id},
                {"$set": update}
            )
            
            if result.modified_count == 1:
                logger.info(f"更新任务统计信息成功: {task_id}, 进度: {progress}%")
                return True
            else:
                logger.warning(f"未能更新任务统计信息: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"更新视频状态时出错: {str(e)}")
            return False
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功
        """
        try:
            return self.update_task_status(task_id, "canceled")
            
        except Exception as e:
            logger.error(f"取消任务时出错: {str(e)}")
            return False
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功
        """
        try:
            # 转换为ObjectId
            object_id = ObjectId(task_id)
            
            # 删除任务
            result = self.task_collection.delete_one({"_id": object_id})
            
            if result.deleted_count == 1:
                logger.info(f"删除任务成功: {task_id}")
                return True
            else:
                logger.warning(f"未能删除任务: {task_id}")
                return False
            
        except Exception as e:
            logger.error(f"删除任务时出错: {str(e)}")
            return False
    
    def get_brands(self) -> List[str]:
        """
        获取所有品牌列表
        
        返回:
        品牌列表
        """
        try:
            # 从视频集合中获取品牌
            brands = set()
            
            # 从任务配置中获取品牌
            tasks = self.task_collection.find({}, {"config.brand": 1})
            for task in tasks:
                brand = task.get("config", {}).get("brand")
                if brand:
                    brands.add(brand)
            
            # 从videos集合中获取品牌
            videos_collection = self.db.get_collection("videos")
            if videos_collection is not None:
                videos = videos_collection.find({}, {"metadata.brand": 1})
                for video in videos:
                    brand = video.get("metadata", {}).get("brand")
                    if brand:
                        brands.add(brand)
            
            # 从其他可能的集合中查找品牌信息
            possible_collections = ["video_metadata", "brands", "products"]
            for collection_name in possible_collections:
                if collection_name in self.db.list_collection_names():
                    try:
                        collection = self.db.get_collection(collection_name)
                        if collection is not None:
                            # 尝试不同的字段名
                            for field in ["brand", "name", "brand_name"]:
                                results = collection.distinct(field)
                                for brand in results:
                                    if isinstance(brand, str) and brand:
                                        brands.add(brand)
                    except Exception as inner_e:
                        logger.warning(f"从集合 {collection_name} 获取品牌时出错: {str(inner_e)}")
            
            # 如果没有找到品牌，添加一些默认品牌作为备选
            if not brands:
                default_brands = ["宝马", "奔驰", "奥迪", "大众", "丰田", "本田", "日产", "福特"]
                logger.info("未在数据库中找到品牌，使用默认品牌列表")
                brands.update(default_brands)
            
            return sorted(list(brands))
            
        except Exception as e:
            logger.error(f"获取品牌列表时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def count_tasks(self, status: str = None) -> int:
        """
        获取任务数量
        
        参数:
        status: 任务状态筛选
        
        返回:
        任务数量
        """
        try:
            # 创建筛选条件
            filters = {}
            if status:
                filters["status"] = status
            
            # 计算任务数量
            count = self.task_collection.count_documents(filters)
            return count
            
        except Exception as e:
            logger.error(f"计算任务数量时出错: {str(e)}")
            return 0
    
    def get_video_results(self, filters: Dict[str, Any] = None, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        """
        获取视频解析结果
        
        参数:
        filters: 筛选条件，包含brand、model、date_from、date_to等
        limit: 最大返回数
        skip: 跳过的记录数
        
        返回:
        视频列表
        """
        try:
            logger.info(f"获取视频结果，筛选条件: {filters}")
            
            # 初始化查询条件
            query = {}
            
            # 处理筛选条件
            if filters:
                # 品牌筛选
                if "brand" in filters and filters["brand"]:
                    query["metadata.brand"] = filters["brand"]
                
                # 型号筛选
                if "model" in filters and filters["model"]:
                    query["metadata.model"] = filters["model"]
                
                # 日期范围筛选 - 这里的问题是metadata.upload_date可能是ISO字符串格式而不是日期对象
                if "date_from" in filters or "date_to" in filters:
                    # 检查实际使用的日期字段
                    field_options = [
                        "metadata.upload_date",
                        "created_at", 
                        "file_info.created_at",
                        "metadata.created_at"
                    ]
                    
                    # 首先检查第一个视频记录，看看使用了哪个日期字段
                    date_field = "metadata.upload_date"  # 默认字段
                    try:
                        if "videos" in self.db.list_collection_names():
                            sample = self.db.videos.find_one({})
                            if sample:
                                # 检查哪个字段存在
                                for option in field_options:
                                    parts = option.split('.')
                                    obj = sample
                                    exists = True
                                    for part in parts:
                                        if part in obj:
                                            obj = obj[part]
                                        else:
                                            exists = False
                                            break
                                    if exists:
                                        date_field = option
                                        logger.info(f"找到日期字段: {date_field}")
                                        break
                    except Exception as e:
                        logger.warning(f"检查日期字段时出错: {str(e)}")
                    
                    # 构建日期查询
                    date_query = {}
                    
                    if "date_from" in filters and filters["date_from"]:
                        date_from = filters["date_from"]
                        date_query["$gte"] = date_from
                        
                    if "date_to" in filters and filters["date_to"]:
                        date_to = filters["date_to"]
                        date_query["$lte"] = date_to
                    
                    if date_query:
                        query[date_field] = date_query
                        
                        # 针对ISO字符串格式的日期添加额外的查询条件
                        if isinstance(date_from, datetime) or isinstance(date_to, datetime):
                            # 也尝试匹配ISO字符串格式的日期
                            str_query = {}
                            if "date_from" in filters and filters["date_from"]:
                                str_query["$gte"] = filters["date_from"].isoformat()
                            if "date_to" in filters and filters["date_to"]:
                                str_query["$lte"] = filters["date_to"].isoformat()
                            
                            # 添加为OR条件
                            if "$or" not in query:
                                query["$or"] = []
                            
                            query["$or"].append({date_field: str_query})
                            # 移除原来的条件以避免冲突
                            del query[date_field]
            
            logger.info(f"最终查询条件: {query}")
            
            # 检查videos集合是否存在
            if "videos" not in self.db.list_collection_names():
                logger.warning("videos集合不存在")
                return []
            
            # 查询视频
            videos = []
            cursor = self.db.videos.find(query).skip(skip).limit(limit)
            
            # 转换ObjectId为字符串
            for video in cursor:
                video["_id"] = str(video["_id"])
                videos.append(video)
            
            logger.info(f"找到 {len(videos)} 个视频")
            return videos
            
        except Exception as e:
            logger.error(f"获取视频结果时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return [] 