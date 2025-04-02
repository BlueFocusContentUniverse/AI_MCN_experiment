import os
import logging
import json
import time
import threading
import queue
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from services.video_info_extractor import VideoInfoExtractor
from streamlit_app.services.mongo_service import TaskManagerService
from services.redis_queue_service import RedisQueueService, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoProcessorService:
    """视频处理服务，支持并发处理任务"""
    
    def __init__(self, max_workers=4, host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, db=REDIS_DB):
        """
        初始化视频处理服务
        
        参数:
        max_workers: 最大工作线程数，默认为4
        host: Redis主机
        port: Redis端口
        password: Redis密码
        db: Redis数据库
        """
        self.max_workers = max_workers
        self.task_manager = TaskManagerService()
        
        # 初始化Redis服务
        try:
            self.redis_service = RedisQueueService(host, port, password, db)
            logger.info(f"Redis服务初始化完成，连接到 {host}:{port}")
        except Exception as e:
            logger.error(f"Redis服务初始化失败: {str(e)}")
            logger.warning("系统将在没有Redis的情况下运行，部分功能可能不可用")
            self.redis_service = None
        
        # 初始化工作线程池和任务队列
        self.workers = []
        self.worker_status = [False] * max_workers  # 记录每个工作线程的状态，False表示空闲
        self.video_queue = queue.Queue()  # 本地视频处理队列
        
        # 线程同步锁
        self.lock = threading.Lock()
        
        # 当前处理的任务数量
        self.active_tasks_count = 0
        self.max_concurrent_tasks = max_workers  # 最大并发任务数应该与工作线程数一致，保证资源最佳利用
        
        # 性能统计数据
        self.stats = {
            "processed_videos": 0,
            "successful_videos": 0,
            "failed_videos": 0,
            "total_processing_time": 0,
            "start_time": time.time()
        }
        
        # 初始化工作线程
        self._init_workers()
        
        # 启动调度器线程
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        logger.info(f"视频处理服务初始化完成，最大工作线程数: {self.max_workers}")
    
    def _init_workers(self):
        """初始化工作线程池"""
        for i in range(self.max_workers):
            worker_thread = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                daemon=True
            )
            worker_thread.start()
            self.workers.append(worker_thread)
            
            # 在Redis中注册工作线程
            self.redis_service.register_worker(f"worker_{i}", "idle")
            
            logger.info(f"工作线程 {i} 已启动")
    
    def _scheduler_loop(self):
        """调度器主循环，负责从MongoDB获取待处理任务"""
        last_check_time = 0  # 上次检查MongoDB的时间
        check_interval = 5   # 检查间隔时间，秒
        
        while True:
            try:
                current_time = time.time()
                
                # 检查是否有空闲的工作线程
                with self.lock:
                    idle_workers_count = self.worker_status.count(False)
                    current_tasks_count = self.active_tasks_count
                    queue_size = self.video_queue.qsize()
                
                # 当有空闲工作线程，但队列为空，且当前任务数小于最大并发任务数时，获取新任务
                if idle_workers_count > 0 and queue_size == 0 and current_tasks_count < self.max_concurrent_tasks:
                    # 限制查询频率，避免频繁请求数据库
                    if current_time - last_check_time >= check_interval:
                        last_check_time = current_time
                        
                        # 获取一个待处理的任务
                        pending_tasks = self.task_manager.get_tasks(status="pending", limit=3)  # 获取多个任务，以便排序
                        
                        if pending_tasks:
                            # 按照优先级和创建时间排序
                            # TODO: 添加实际的优先级排序逻辑
                            # 这里先简单按照创建时间排序
                            pending_tasks.sort(key=lambda task: task.get("created_at", ""), reverse=True)
                            
                            # 获取最优先的任务
                            task = pending_tasks[0]
                            task_id = task["_id"]
                            
                            # 更新任务状态为处理中
                            self.task_manager.update_task_status(task_id, "processing")
                            
                            # 将任务添加到Redis队列
                            videos = task.get("videos", [])
                            config = task.get("config", {})
                            
                            # 更新活跃任务计数
                            with self.lock:
                                self.active_tasks_count += 1
                            
                            # 将任务中的每个视频添加到处理队列
                            for idx, video in enumerate(videos):
                                video_info = {
                                    "task_id": task_id,
                                    "video_index": idx,
                                    "file_path": video["file_path"],
                                    "file_name": video["file_name"],
                                    "config": config
                                }
                                self.video_queue.put(video_info)
                                logger.info(f"添加视频到处理队列: {video['file_name']}")
                            
                            # 更新检查时间，避免立即获取下一个任务
                            last_check_time = time.time()
                
                # 避免CPU空转
                sleep_time = min(1.0, max(0.1, check_interval - (current_time - last_check_time)))
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"调度器出错: {str(e)}")
                time.sleep(5)  # 错误后等待一段时间再继续
    
    def _worker_loop(self, worker_id: int):
        """
        工作线程主循环
        
        参数:
        worker_id: 工作线程ID
        """
        # 创建独立的VideoInfoExtractor实例
        extractor = VideoInfoExtractor(
            output_dir=f"./output/worker_{worker_id}"
        )
        
        worker_id_str = f"worker_{worker_id}"
        
        # 统计信息
        processed_count = 0  # 处理过的视频数量
        success_count = 0    # 成功处理的视频数量
        failed_count = 0     # 失败的视频数量
        
        while True:
            try:
                # 标记为空闲
                with self.lock:
                    self.worker_status[worker_id] = False
                
                # 更新Redis中的工作线程状态
                try:
                    self.redis_service.update_worker_status(worker_id_str, "idle")
                except Exception as e:
                    logger.warning(f"更新Redis中的工作线程状态失败: {str(e)}")
                
                # 从队列获取视频信息，最多等待5秒
                try:
                    video_info = self.video_queue.get(timeout=5)
                except queue.Empty:
                    # 没有待处理的视频，继续下一次循环
                    time.sleep(1)  # 避免CPU空转
                    continue
                
                # 标记为忙碌
                with self.lock:
                    self.worker_status[worker_id] = True
                
                # 更新Redis中的工作线程状态
                try:
                    self.redis_service.update_worker_status(
                        worker_id_str, 
                        "busy", 
                        video_info["task_id"]
                    )
                except Exception as e:
                    logger.warning(f"更新Redis中的工作线程状态失败: {str(e)}")
                
                # 提取视频信息
                task_id = video_info["task_id"]
                video_index = video_info["video_index"]
                file_path = video_info["file_path"]
                file_name = video_info.get("file_name", os.path.basename(file_path))
                
                # 验证文件是否存在
                if not os.path.exists(file_path):
                    logger.error(f"视频文件不存在: {file_path}")
                    self.task_manager.update_video_status(
                        task_id, 
                        video_index, 
                        "failed", 
                        error=f"文件不存在: {file_path}"
                    )
                    self.video_queue.task_done()
                    continue
                
                # 更新统计信息
                processed_count += 1
                
                logger.info(f"工作线程 {worker_id} 开始处理视频: {file_name} (总处理数: {processed_count})")
                start_time = time.time()
                
                try:
                    # 更新视频状态为处理中
                    self.task_manager.update_video_status(
                        task_id, 
                        video_index, 
                        "processing"
                    )
                    
                    # 提取视频信息
                    result = extractor.extract_video_info(
                        file_path,
                        custom_metadata=video_info.get("config", {})
                    )
                    
                    # 获取视频ID
                    video_id = None
                    if "_id" in result:
                        video_id = str(result["_id"])
                    
                    # 更新视频状态为已完成
                    self.task_manager.update_video_status(
                        task_id, 
                        video_index, 
                        "completed", 
                        video_id=video_id
                    )
                    
                    # 更新统计信息
                    success_count += 1
                    processing_time = time.time() - start_time
                    
                    # 更新全局统计信息
                    with self.lock:
                        self.stats["processed_videos"] += 1
                        self.stats["successful_videos"] += 1
                        self.stats["total_processing_time"] += processing_time
                    
                    logger.info(f"工作线程 {worker_id} 完成视频处理: {file_name}, 耗时: {processing_time:.2f}秒 (成功: {success_count}, 失败: {failed_count})")
                    
                except Exception as e:
                    logger.error(f"处理视频时出错: {file_name}, 错误: {str(e)}")
                    
                    # 更新视频状态为失败
                    self.task_manager.update_video_status(
                        task_id, 
                        video_index, 
                        "failed", 
                        error=str(e)
                    )
                    
                    # 更新统计信息
                    failed_count += 1
                    
                    # 更新全局统计信息
                    with self.lock:
                        self.stats["processed_videos"] += 1
                        self.stats["failed_videos"] += 1
                
                # 完成任务，标记队列项目为已处理
                self.video_queue.task_done()
                
                # 检查这个任务是否已经全部完成
                try:
                    task = self.task_manager.get_task(task_id)
                    if task:
                        total_videos = len(task.get("videos", []))
                        processed_videos = task.get("processed_videos", 0)
                        
                        if processed_videos >= total_videos:
                            # 任务已完成，减少活跃任务计数
                            with self.lock:
                                self.active_tasks_count = max(0, self.active_tasks_count - 1)
                            
                            logger.info(f"任务 {task_id} 全部视频处理完成，当前活跃任务数: {self.active_tasks_count}")
                except Exception as e:
                    logger.error(f"检查任务完成状态时出错: {str(e)}")
                
            except Exception as e:
                logger.error(f"工作线程 {worker_id} 出错: {str(e)}")
                time.sleep(1)  # 错误后等待一段时间再继续
    
    def start_processing(self, task_id: str) -> bool:
        """
        开始处理指定任务
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功启动处理
        """
        try:
            # 获取任务信息
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.error(f"未找到任务: {task_id}")
                return False
            
            # 检查任务状态
            if task.get("status") != "pending":
                logger.warning(f"任务状态不是pending，无法启动: {task_id}, 当前状态: {task.get('status')}")
                return False
            
            # 更新任务状态为处理中
            self.task_manager.update_task_status(task_id, "processing")
            
            # 将任务添加到Redis队列
            videos = task.get("videos", [])
            config = task.get("config", {})
            
            # 检查当前活跃任务数
            with self.lock:
                if self.active_tasks_count >= self.max_concurrent_tasks:
                    logger.warning(f"当前活跃任务数已达上限({self.max_concurrent_tasks})，任务 {task_id} 将排队等待")
                    return True
                
                # 更新活跃任务计数
                self.active_tasks_count += 1
            
            # 将任务中的每个视频添加到处理队列
            for idx, video in enumerate(videos):
                video_info = {
                    "task_id": task_id,
                    "video_index": idx,
                    "file_path": video["file_path"],
                    "file_name": video["file_name"],
                    "config": config
                }
                self.video_queue.put(video_info)
                logger.info(f"添加视频到处理队列: {video['file_name']}")
            
            return True
            
        except Exception as e:
            logger.error(f"启动任务处理时出错: {str(e)}")
            return False
    
    def is_task_active(self, task_id: str) -> bool:
        """
        检查任务是否正在处理中
        
        参数:
        task_id: 任务ID
        
        返回:
        是否正在处理
        """
        # 获取任务状态
        task = self.task_manager.get_task(task_id)
        if not task:
            return False
        
        return task.get("status") == "processing"
    
    def cancel_processing(self, task_id: str) -> bool:
        """
        取消任务处理
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功取消
        """
        try:
            # 获取任务信息
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.error(f"未找到任务: {task_id}")
                return False
            
            # 只有当任务状态为processing或pending时才能取消
            if task.get("status") not in ["processing", "pending"]:
                logger.warning(f"任务状态不能取消: {task_id}, 当前状态: {task.get('status')}")
                return False
            
            # 更新任务状态为取消
            self.task_manager.cancel_task(task_id)
            
            # 如果任务正在处理中，减少活跃任务计数
            if task.get("status") == "processing":
                with self.lock:
                    self.active_tasks_count = max(0, self.active_tasks_count - 1)
            
            return True
            
        except Exception as e:
            logger.error(f"取消任务处理时出错: {str(e)}")
            return False
    
    def get_active_workers_count(self) -> int:
        """获取当前活跃的工作线程数"""
        with self.lock:
            return self.worker_status.count(True)
    
    def get_queue_size(self) -> int:
        """获取当前队列中的视频数量"""
        return self.video_queue.qsize()
    
    def get_active_tasks_count(self) -> int:
        """获取当前活跃的任务数量"""
        with self.lock:
            return self.active_tasks_count
    
    def get_worker_status_list(self) -> List[bool]:
        """获取工作线程状态列表"""
        return self.worker_status
    
    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        runtime = time.time() - self.stats["start_time"]
        
        # 计算每分钟处理的视频数
        processed_per_minute = 0
        if runtime > 0:
            processed_per_minute = (self.stats["processed_videos"] / runtime) * 60
            
        # 计算成功率
        success_rate = 0
        if self.stats["processed_videos"] > 0:
            success_rate = (self.stats["successful_videos"] / self.stats["processed_videos"]) * 100
            
        # 返回统计信息
        return {
            "processed_videos": self.stats["processed_videos"],
            "successful_videos": self.stats["successful_videos"],
            "failed_videos": self.stats["failed_videos"],
            "success_rate": success_rate,
            "processed_per_minute": processed_per_minute,
            "runtime_seconds": runtime,
            "runtime_formatted": self._format_time(runtime),
            "active_workers": self.get_active_workers_count(),
            "total_workers": self.max_workers,
            "active_tasks": self.active_tasks_count,
            "queue_size": self.video_queue.qsize(),
            "redis_available": self.redis_service is not None
        }
        
    def _format_time(self, seconds: float) -> str:
        """将秒数格式化为时:分:秒"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" 