import json
import logging
import time
import redis
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Redis配置
REDIS_HOST = "localhost"
REDIS_PORT = 6381
REDIS_PASSWORD = "Bfg@usr"
REDIS_DB = 3

class RedisQueueService:
    """Redis队列服务，用于管理视频处理任务"""
    
    # 队列和哈希表名称常量
    QUEUE_VIDEO_TASKS = "queue:video_tasks"        # 视频任务队列
    HASH_TASK_STATUS = "hash:task_status"          # 任务状态哈希表
    HASH_WORKER_STATUS = "hash:worker_status"      # 工作线程状态哈希表
    SET_ACTIVE_TASKS = "set:active_tasks"          # 活跃任务集合
    
    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=REDIS_DB):
        """
        初始化Redis队列服务
        
        参数:
        host: Redis主机
        port: Redis端口
        password: Redis密码
        db: Redis数据库
        """
        try:
            # 创建Redis连接
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                decode_responses=True  # 自动将字节解码为字符串
            )
            # 测试连接
            self.redis_client.ping()
            logger.info(f"Redis队列服务初始化完成，已连接到 {host}:{port}")
        except Exception as e:
            logger.error(f"Redis连接失败: {str(e)}")
            raise
    
    def enqueue_task(self, task_id: str, videos: List[Dict[str, Any]], config: Dict[str, Any]) -> bool:
        """
        将任务添加到队列
        
        参数:
        task_id: 任务ID
        videos: 视频列表
        config: 任务配置
        
        返回:
        是否成功添加
        """
        # 检查Redis客户端
        if not hasattr(self, 'redis_client') or self.redis_client is None:
            logger.error("Redis客户端未初始化")
            return False
            
        try:
            # 创建任务数据
            task_data = {
                "task_id": task_id,
                "videos": videos,
                "config": config,
                "submitted_at": datetime.now().isoformat()
            }
            
            # 保存任务状态
            task_status = {
                "status": "pending",
                "progress": 0,
                "total_videos": len(videos),
                "processed_videos": 0,
                "submitted_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # 将任务添加到Redis
            pipe = self.redis_client.pipeline()
            pipe.hset(
                self.HASH_TASK_STATUS, 
                task_id, 
                json.dumps(task_status)
            )
            pipe.lpush(
                self.QUEUE_VIDEO_TASKS, 
                json.dumps(task_data)
            )
            pipe.execute()
            
            logger.info(f"任务已添加到队列: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加任务到队列时出错: {str(e)}")
            return False
    
    def dequeue_task(self, timeout=5) -> Optional[Dict[str, Any]]:
        """
        从队列获取下一个任务
        
        参数:
        timeout: 等待超时时间(秒)
        
        返回:
        任务数据或None(如果队列为空)
        """
        try:
            # 从队列获取任务
            result = self.redis_client.brpop(self.QUEUE_VIDEO_TASKS, timeout)
            if not result:
                return None
            
            # 解析任务数据
            _, task_json = result
            task_data = json.loads(task_json)
            
            # 更新任务状态为处理中
            task_id = task_data["task_id"]
            self.update_task_status(task_id, "processing")
            
            # 将任务ID添加到活跃任务集合
            self.redis_client.sadd(self.SET_ACTIVE_TASKS, task_id)
            
            logger.info(f"从队列获取任务: {task_id}")
            return task_data
            
        except Exception as e:
            logger.error(f"从队列获取任务时出错: {str(e)}")
            return None
    
    def update_task_status(self, task_id: str, status: str, progress: int = None, error: str = None) -> bool:
        """
        更新任务状态
        
        参数:
        task_id: 任务ID
        status: 新状态
        progress: 进度百分比
        error: 错误信息
        
        返回:
        是否成功更新
        """
        try:
            # 获取当前任务状态
            status_json = self.redis_client.hget(self.HASH_TASK_STATUS, task_id)
            if not status_json:
                logger.warning(f"未找到任务状态: {task_id}")
                return False
            
            task_status = json.loads(status_json)
            
            # 更新状态
            task_status["status"] = status
            task_status["updated_at"] = datetime.now().isoformat()
            
            if progress is not None:
                task_status["progress"] = progress
            
            if error:
                task_status["error"] = error
            
            # 如果任务已完成或失败，从活跃任务集合中移除
            if status in ["completed", "failed", "canceled"]:
                self.redis_client.srem(self.SET_ACTIVE_TASKS, task_id)
            
            # 保存更新后的状态
            self.redis_client.hset(
                self.HASH_TASK_STATUS, 
                task_id, 
                json.dumps(task_status)
            )
            
            logger.info(f"更新任务状态: {task_id} -> {status}")
            return True
            
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
        video_id: 视频ID(仅用于已完成的视频)
        error: 错误信息
        
        返回:
        是否成功更新
        """
        try:
            # 获取当前任务状态
            status_json = self.redis_client.hget(self.HASH_TASK_STATUS, task_id)
            if not status_json:
                logger.warning(f"未找到任务状态: {task_id}")
                return False
            
            task_status = json.loads(status_json)
            
            # 确保视频数组存在
            if "videos" not in task_status:
                task_status["videos"] = []
            
            # 确保数组长度足够
            while len(task_status["videos"]) <= video_index:
                task_status["videos"].append({
                    "status": "pending",
                    "video_id": None,
                    "error": None
                })
            
            # 更新视频状态
            task_status["videos"][video_index]["status"] = status
            
            if video_id:
                task_status["videos"][video_index]["video_id"] = video_id
                
            if error:
                task_status["videos"][video_index]["error"] = error
            
            # 更新任务进度
            processed_count = 0
            error_count = 0
            for video in task_status["videos"]:
                if video["status"] in ["completed", "failed"]:
                    processed_count += 1
                if video["status"] == "failed":
                    error_count += 1
            
            task_status["processed_videos"] = processed_count
            task_status["failed_videos"] = error_count
            
            total_videos = task_status.get("total_videos", len(task_status["videos"]))
            if total_videos > 0:
                task_status["progress"] = int((processed_count / total_videos) * 100)
            
            # 如果所有视频都处理完成，更新任务状态
            if processed_count == total_videos:
                if error_count > 0:
                    task_status["status"] = "completed_with_errors"
                else:
                    task_status["status"] = "completed"
                
                # 从活跃任务集合中移除
                self.redis_client.srem(self.SET_ACTIVE_TASKS, task_id)
            
            # 保存更新后的状态
            self.redis_client.hset(
                self.HASH_TASK_STATUS, 
                task_id, 
                json.dumps(task_status)
            )
            
            logger.info(f"更新视频状态: {task_id}, 索引: {video_index} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"更新视频状态时出错: {str(e)}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        参数:
        task_id: 任务ID
        
        返回:
        任务状态或None(如果未找到)
        """
        try:
            status_json = self.redis_client.hget(self.HASH_TASK_STATUS, task_id)
            if not status_json:
                return None
            
            return json.loads(status_json)
            
        except Exception as e:
            logger.error(f"获取任务状态时出错: {str(e)}")
            return None
    
    def get_all_active_tasks(self) -> List[str]:
        """
        获取所有活跃任务的ID
        
        返回:
        活跃任务ID列表
        """
        try:
            return [task_id.decode() for task_id in self.redis_client.smembers(self.SET_ACTIVE_TASKS)]
            
        except Exception as e:
            logger.error(f"获取活跃任务时出错: {str(e)}")
            return []
    
    def register_worker(self, worker_id: str, status: str = "idle") -> bool:
        """
        注册工作线程
        
        参数:
        worker_id: 工作线程ID
        status: 初始状态
        
        返回:
        是否成功注册
        """
        try:
            worker_data = {
                "status": status,
                "registered_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "current_task": None
            }
            
            self.redis_client.hset(
                self.HASH_WORKER_STATUS, 
                worker_id, 
                json.dumps(worker_data)
            )
            
            logger.info(f"工作线程已注册: {worker_id}")
            return True
            
        except Exception as e:
            logger.error(f"注册工作线程时出错: {str(e)}")
            return False
    
    def update_worker_status(self, worker_id: str, status: str, current_task: str = None) -> bool:
        """
        更新工作线程状态
        
        参数:
        worker_id: 工作线程ID
        status: 新状态
        current_task: 当前处理的任务ID
        
        返回:
        是否成功更新
        """
        try:
            # 获取当前工作线程状态
            status_json = self.redis_client.hget(self.HASH_WORKER_STATUS, worker_id)
            if not status_json:
                # 如果不存在，先注册
                self.register_worker(worker_id, status)
                status_json = self.redis_client.hget(self.HASH_WORKER_STATUS, worker_id)
            
            worker_status = json.loads(status_json)
            
            # 更新状态
            worker_status["status"] = status
            worker_status["updated_at"] = datetime.now().isoformat()
            
            if current_task is not None:
                worker_status["current_task"] = current_task
            
            # 保存更新后的状态
            self.redis_client.hset(
                self.HASH_WORKER_STATUS, 
                worker_id, 
                json.dumps(worker_status)
            )
            
            logger.info(f"更新工作线程状态: {worker_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"更新工作线程状态时出错: {str(e)}")
            return False
    
    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        获取工作线程状态
        
        参数:
        worker_id: 工作线程ID
        
        返回:
        工作线程状态或None(如果未找到)
        """
        try:
            status_json = self.redis_client.hget(self.HASH_WORKER_STATUS, worker_id)
            if not status_json:
                return None
            
            return json.loads(status_json)
            
        except Exception as e:
            logger.error(f"获取工作线程状态时出错: {str(e)}")
            return None
    
    def get_all_workers(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有工作线程的状态
        
        返回:
        工作线程状态字典，键为工作线程ID
        """
        try:
            workers = {}
            for worker_id, status_json in self.redis_client.hgetall(self.HASH_WORKER_STATUS).items():
                workers[worker_id.decode()] = json.loads(status_json)
            
            return workers
            
        except Exception as e:
            logger.error(f"获取所有工作线程时出错: {str(e)}")
            return {}
    
    def get_queue_length(self) -> int:
        """
        获取任务队列长度
        
        返回:
        队列中的任务数量
        """
        try:
            return self.redis_client.llen(self.QUEUE_VIDEO_TASKS)
            
        except Exception as e:
            logger.error(f"获取队列长度时出错: {str(e)}")
            return 0
    
    def clear_queue(self) -> bool:
        """
        清空任务队列
        
        返回:
        是否成功清空
        """
        try:
            self.redis_client.delete(self.QUEUE_VIDEO_TASKS)
            logger.info("任务队列已清空")
            return True
            
        except Exception as e:
            logger.error(f"清空队列时出错: {str(e)}")
            return False 