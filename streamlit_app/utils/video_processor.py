import sys
import os
import threading
import time
from typing import Dict, List, Any, Optional, Union, Callable
import logging
from bson import ObjectId

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 导入现有服务
from services.video_info_extractor import VideoInfoExtractor
from streamlit_app.services.mongo_service import TaskManagerService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoProcessorService:
    """视频处理服务"""
    
    def __init__(self):
        """初始化视频处理服务"""
        self.task_manager = TaskManagerService()
        self.active_tasks = {}  # 存储活跃的处理线程
    
    def start_processing(self, task_id: str) -> bool:
        """
        启动视频处理
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功启动
        """
        try:
            # 检查任务是否已存在
            if task_id in self.active_tasks:
                logger.warning(f"任务 {task_id} 已在处理中")
                return False
            
            # 获取任务信息
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.error(f"未找到任务: {task_id}")
                return False
            
            # 只有处于pending状态的任务可以启动
            if task["status"] != "pending":
                logger.warning(f"只能启动处于pending状态的任务，当前状态: {task['status']}")
                return False
            
            # 更新任务状态为processing
            self.task_manager.update_task_status(task_id, "processing", 0)
            
            # 启动处理线程
            thread = threading.Thread(
                target=self._process_task,
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
            
            logger.info(f"成功启动任务 {task_id} 的处理")
            return True
            
        except Exception as e:
            logger.error(f"启动视频处理时出错: {str(e)}")
            return False
    
    def _process_task(self, task_id: str, task: Dict[str, Any]) -> None:
        """
        处理任务中的所有视频
        
        参数:
        task_id: 任务ID
        task: 任务信息
        """
        try:
            videos = task["videos"]
            config = task["config"]
            
            # 创建VideoInfoExtractor
            output_dir = os.path.join("output", task_id)
            special_requirements = config.get("special_requirements", "")
            
            extractor = VideoInfoExtractor(
                output_dir=output_dir,
                skip_mongodb=False,
                special_requirements=special_requirements
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
                    
                    # 调用VideoInfoExtractor处理视频，并传递用户自定义元数据
                    video_info = extractor.extract_video_info(video_path, custom_metadata=custom_metadata)
                    
                    # 提取视频ID - 考虑多种情况
                    video_id = None
                    if video_info:
                        # 情况1: 直接包含_id字段
                        if "_id" in video_info:
                            video_id = video_info["_id"]
                        # 情况2: MongoDB可能返回特殊的_id对象
                        elif hasattr(video_info, "_id"):
                            video_id = video_info._id
                        # 情况3: MongoDB可能在其他结构中包含ID
                        elif "video_id" in video_info:
                            video_id = video_info["video_id"]
                        # 情况4: 日志中提取已保存的ID
                        # 这种情况通常不需要，保留作为后备方案
                    
                    # 确保ID为字符串
                    if video_id:
                        if isinstance(video_id, ObjectId):
                            video_id = str(video_id)
                        logger.info(f"视频处理成功: {video_path}, video_id: {video_id}")
                        self.task_manager.update_video_status(task_id, i, "completed", video_id)
                    else:
                        # 尝试查找刚刚插入的视频记录
                        try:
                            # 使用文件路径查找视频记录
                            found_video = extractor.mongodb_service.find_video_by_path(video_path)
                            if found_video and "_id" in found_video:
                                video_id = str(found_video["_id"])
                                logger.info(f"从数据库查找视频ID成功: {video_path}, video_id: {video_id}")
                                self.task_manager.update_video_status(task_id, i, "completed", video_id)
                            else:
                                logger.warning(f"无法查找刚插入的视频记录: {video_path}")
                                self.task_manager.update_video_status(
                                    task_id, i, "failed", 
                                    error="视频处理完成，但未返回有效ID且无法通过路径查找"
                                )
                        except Exception as lookup_err:
                            logger.error(f"查找视频记录时出错: {video_path}, 错误: {str(lookup_err)}")
                            self.task_manager.update_video_status(
                                task_id, i, "failed", 
                                error=f"视频处理完成，但查找ID时出错: {str(lookup_err)}"
                            )
                    
                except Exception as e:
                    logger.error(f"处理视频时出错: {video_path}, 错误: {str(e)}")
                    self.task_manager.update_video_status(task_id, i, "failed", error=str(e))
            
            # 处理完成后，从活跃任务中移除
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            
            logger.info(f"任务 {task_id} 处理完成")
            
        except Exception as e:
            logger.error(f"处理任务时出错: {task_id}, 错误: {str(e)}")
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
            # 检查任务是否存在
            if task_id not in self.active_tasks:
                logger.warning(f"任务 {task_id} 不在活跃任务列表中")
                return False
            
            # 设置取消标志
            self.active_tasks[task_id]["cancel_flag"].set()
            
            # 更新任务状态
            self.task_manager.update_task_status(task_id, "canceled")
            
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
        return list(self.active_tasks.keys())
    
    def is_task_active(self, task_id: str) -> bool:
        """
        检查任务是否活跃
        
        参数:
        task_id: 任务ID
        
        返回:
        是否活跃
        """
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
        return None
