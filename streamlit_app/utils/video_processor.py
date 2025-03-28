import sys
import os
import threading
import time
from typing import Dict, List, Any, Optional, Union, Callable
import logging
from bson import ObjectId
import datetime

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 导入现有服务
from services.video_info_extractor import VideoInfoExtractor
from streamlit_app.services.mongo_service import TaskManagerService
from services.redis_queue_service import RedisQueueService, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB
from services.video_processor_service import VideoProcessorService as GlobalVideoProcessorService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoProcessorService:
    """视频处理服务"""
    
    def __init__(self):
        """初始化视频处理服务"""
        self.task_manager = TaskManagerService()
        
        # 初始化Redis服务
        try:
            self.redis_service = RedisQueueService()
            logger.info("初始化Redis服务成功")
        except Exception as e:
            logger.error(f"初始化Redis服务失败: {str(e)}")
            self.redis_service = None
        
        # 全局处理服务实例 (单例模式)
        self.global_processor = None
        try:
            self.global_processor = GlobalVideoProcessorService(max_workers=4)
            logger.info("已连接到全局视频处理服务")
        except Exception as e:
            logger.error(f"连接全局视频处理服务失败: {str(e)}")
        
        # 向全局处理器传入状态监控回调函数
        self.active_tasks = {}  # 仍然保留这个字典以兼容现有代码
    
    def start_processing(self, task_id: str) -> bool:
        """
        启动视频处理
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功启动
        """
        try:
            # 获取任务信息
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.error(f"未找到任务: {task_id}")
                return False
            
            # 只有处于pending状态的任务可以启动
            if task["status"] != "pending":
                logger.warning(f"只能启动处于pending状态的任务，当前状态: {task['status']}")
                return False
            
            # 尝试使用全局处理服务
            if self.global_processor is not None:
                logger.info(f"使用全局处理服务启动任务 {task_id}")
                try:
                    success = self.global_processor.start_processing(task_id)
                    if success:
                        return True
                    else:
                        logger.warning(f"全局处理服务启动任务 {task_id} 失败，尝试使用Redis队列服务")
                except Exception as e:
                    logger.error(f"全局处理服务启动任务时出错: {str(e)}")
            else:
                logger.warning("全局处理服务不可用，尝试使用Redis队列服务")
            
            # 如果没有全局处理服务或启动失败，则使用Redis队列服务
            videos = task["videos"]
            config = task["config"]
            
            # 检查Redis服务是否可用
            if self.redis_service is None:
                logger.error("Redis服务不可用，无法启动任务")
                # 创建本地线程处理，防止任务无法开始
                self._create_fallback_thread(task_id, task)
                # 仍然返回True，因为我们使用了备用方法
                return True
            
            # 将任务添加到Redis队列
            success = self.redis_service.enqueue_task(task_id, videos, config)
            
            if success:
                # 更新任务状态为processing
                self.task_manager.update_task_status(task_id, "processing", 0)
                
                # 记录活跃任务，使用字典模拟线程
                self.active_tasks[task_id] = {
                    "thread": None,  # 不再使用线程
                    "start_time": time.time(),
                    "cancel_flag": threading.Event()
                }
                
                logger.info(f"成功将任务 {task_id} 添加到处理队列")
                return True
            else:
                logger.error(f"将任务 {task_id} 添加到处理队列失败，使用备用线程处理")
                # 创建本地线程处理，防止任务无法开始
                self._create_fallback_thread(task_id, task)
                return True
            
        except Exception as e:
            logger.error(f"启动视频处理时出错: {str(e)}")
            return False
    
    def _create_fallback_thread(self, task_id: str, task: Dict[str, Any]):
        """创建备用处理线程，当Redis和全局服务都不可用时使用"""
        logger.info(f"创建备用处理线程处理任务: {task_id}")
        
        # 更新任务状态为processing
        self.task_manager.update_task_status(task_id, "processing", 0)
        
        # 启动处理线程
        thread = threading.Thread(
            target=self._process_task_fallback,
            args=(task_id, task),
            daemon=True
        )
        thread.start()
        
        # 记录活跃任务
        self.active_tasks[task_id] = {
            "thread": thread,
            "start_time": time.time(),
            "cancel_flag": threading.Event()
        }
        
        logger.info(f"成功启动备用线程处理任务 {task_id}")
        
    def _process_task_fallback(self, task_id: str, task: Dict[str, Any]):
        """备用的任务处理方法，直接在线程中处理视频"""
        try:
            videos = task["videos"]
            config = task.get("config", {})
            
            # 创建VideoInfoExtractor
            output_dir = os.path.join("output", task_id)
            
            extractor = VideoInfoExtractor(
                output_dir=output_dir
            )
            
            # 处理每个视频
            for i, video in enumerate(videos):
                # 检查是否取消
                if task_id in self.active_tasks and self.active_tasks[task_id]["cancel_flag"].is_set():
                    logger.info(f"任务 {task_id} 已取消")
                    break
                
                try:
                    # 更新视频状态为processing
                    self.task_manager.update_video_status(task_id, i, "processing")
                    
                    # 处理视频
                    video_path = video["file_path"]
                    logger.info(f"开始处理视频: {video_path}")
                    
                    # 准备用户自定义的元数据
                    custom_metadata = {
                        "brand": config.get("brand", ""),
                        "model": config.get("model", "")
                    }
                    
                    # 提取视频信息
                    result = extractor.extract_video_info(
                        video_path,
                        custom_metadata=custom_metadata
                    )
                    
                    # 获取视频ID
                    video_id = None
                    if "_id" in result:
                        video_id = str(result["_id"])
                    
                    # 更新视频状态为已完成
                    self.task_manager.update_video_status(
                        task_id, 
                        i, 
                        "completed", 
                        video_id=video_id
                    )
                    
                    logger.info(f"备用线程完成视频处理: {video_path}")
                    
                except Exception as e:
                    logger.error(f"备用线程处理视频时出错: {str(e)}")
                    
                    # 更新视频状态为失败
                    self.task_manager.update_video_status(
                        task_id, 
                        i, 
                        "failed", 
                        error=str(e)
                    )
            
            # 处理完成后，从活跃任务中移除
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            
            logger.info(f"备用线程完成任务 {task_id} 的处理")
            
        except Exception as e:
            logger.error(f"备用线程处理任务时出错: {task_id}, 错误: {str(e)}")
            self.task_manager.update_task_status(task_id, "failed")
            
            # 从活跃任务中移除
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
    
    def cancel_processing(self, task_id: str) -> bool:
        """
        取消视频处理
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功取消
        """
        try:
            # 尝试使用全局处理服务取消
            if self.global_processor and self.global_processor.is_task_active(task_id):
                logger.info(f"使用全局处理服务取消任务 {task_id}")
                return self.global_processor.cancel_processing(task_id)
            
            # 否则使用Redis服务更新任务状态
            self.redis_service.update_task_status(task_id, "canceled")
            
            # 更新任务状态在MongoDB中
            self.task_manager.update_task_status(task_id, "canceled")
            
            # 从活跃任务中移除
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["cancel_flag"].set()
                del self.active_tasks[task_id]
            
            logger.info(f"已发送取消请求给任务 {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消视频处理时出错: {str(e)}")
            return False
    
    def get_active_tasks(self) -> List[str]:
        """
        获取活跃任务列表
        
        返回:
        活跃任务ID列表
        """
        # 优先使用全局处理服务
        if self.global_processor:
            # 转为列表，使用len()函数时不会出错
            tasks_count = self.global_processor.get_active_tasks_count()
            logger.info(f"全局处理服务当前有 {tasks_count} 个活跃任务")
            
            # 从Redis获取活跃任务
            redis_tasks = self.redis_service.get_all_active_tasks()
            logger.info(f"Redis队列服务当前有 {len(redis_tasks)} 个活跃任务")
            
            # 合并两个列表
            return list(self.active_tasks.keys()) + redis_tasks
        
        # 如果没有全局处理服务，则使用本地活跃任务列表和Redis活跃任务
        redis_tasks = self.redis_service.get_all_active_tasks()
        return list(self.active_tasks.keys()) + redis_tasks
    
    def is_task_active(self, task_id: str) -> bool:
        """
        检查任务是否活跃
        
        参数:
        task_id: 任务ID
        
        返回:
        是否活跃
        """
        # 优先检查全局处理服务
        if self.global_processor and self.global_processor.is_task_active(task_id):
            return True
        
        # 检查Redis活跃任务
        if task_id in self.redis_service.get_all_active_tasks():
            return True
        
        # 最后检查本地活跃任务
        return task_id in self.active_tasks
    
    def get_task_runtime(self, task_id: str) -> Optional[float]:
        """
        获取任务运行时间
        
        参数:
        task_id: 任务ID
        
        返回:
        运行时间（秒），如果任务不存在则返回None
        """
        if task_id in self.active_tasks:
            return time.time() - self.active_tasks[task_id]["start_time"]
        
        # 尝试从Redis获取任务状态
        task_status = self.redis_service.get_task_status(task_id)
        if task_status:
            # 从updated_at和submitted_at计算运行时间
            try:
                submitted_at = datetime.datetime.fromisoformat(task_status.get("submitted_at", ""))
                return time.time() - submitted_at.timestamp()
            except:
                pass
        
        return None
