import os
import sys
import json
import datetime
import threading
import time
from typing import Dict, Any, List, Optional
import uuid
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskManager:
    """任务管理器，负责创建、更新和查询任务"""
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """初始化任务管理器"""
        # 确保数据目录存在
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 任务文件路径
        self.tasks_file = os.path.join(self.data_dir, "tasks.json")
        
        # 初始化任务列表
        self.tasks = self._load_tasks()
        
        # 启动后台处理线程
        self.processor_running = False
        self.processor_thread = None
        # self._start_processor()
    
    def _load_tasks(self) -> List[Dict[str, Any]]:
        """加载任务列表"""
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
                logger.info(f"已加载 {len(tasks)} 个任务")
                return tasks
            except Exception as e:
                logger.error(f"加载任务时出错: {str(e)}")
                return []
        else:
            logger.info("任务文件不存在，创建新的任务列表")
            return []
    
    def _save_tasks(self) -> bool:
        """保存任务列表"""
        try:
            # 将任务对象转换为JSON可序列化格式
            serializable_tasks = []
            for task in self.tasks:
                serializable_task = task.copy()
                # 处理datetime对象
                if isinstance(serializable_task.get("created_at"), datetime.datetime):
                    serializable_task["created_at"] = serializable_task["created_at"].isoformat()
                if isinstance(serializable_task.get("updated_at"), datetime.datetime):
                    serializable_task["updated_at"] = serializable_task["updated_at"].isoformat()
                serializable_tasks.append(serializable_task)
            
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_tasks, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.tasks)} 个任务")
            return True
        except Exception as e:
            logger.error(f"保存任务时出错: {str(e)}")
            return False
    
    def create_task(self, task_id: str = None, task_type: str = "auto_video", 
                   params: Dict[str, Any] = None, priority: str = "normal") -> str:
        """
        创建新任务
        
        参数:
        task_id: 任务ID，如果不提供则自动生成
        task_type: 任务类型
        params: 任务参数
        priority: 任务优先级
        
        返回:
        任务ID
        """
        # 生成任务ID（如果未提供）
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # 创建任务对象
        now = datetime.datetime.now()
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "params": params or {},
            "status": "pending",
            "progress": 0,
            "priority": priority,
            "created_at": now,
            "updated_at": now
        }
        
        # 添加到任务列表
        with self._lock:
            self.tasks.append(task)
            self._save_tasks()
        
        logger.info(f"已创建任务: {task_id}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        
        参数:
        task_id: 任务ID
        
        返回:
        任务信息或None
        """
        with self._lock:
            for task in self.tasks:
                if task["task_id"] == task_id:
                    return task
        return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有任务
        
        返回:
        任务列表
        """
        with self._lock:
            return sorted(self.tasks, key=lambda x: x.get("created_at", datetime.datetime.min), reverse=True)
    
    def get_tasks_by_type(self, task_type: str) -> List[Dict[str, Any]]:
        """
        获取指定类型的任务
        
        参数:
        task_type: 任务类型
        
        返回:
        任务列表
        """
        with self._lock:
            return [task for task in self.tasks if task["task_type"] == task_type]
    
    def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        获取指定状态的任务
        
        参数:
        status: 任务状态
        
        返回:
        任务列表
        """
        with self._lock:
            return [task for task in self.tasks if task["status"] == status]
    
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
        with self._lock:
            for task in self.tasks:
                if task["task_id"] == task_id:
                    task["status"] = status
                    task["updated_at"] = datetime.datetime.now()
                    if progress is not None:
                        task["progress"] = progress
                    self._save_tasks()
                    logger.info(f"已更新任务状态: {task_id} -> {status}")
                    return True
        logger.warning(f"未找到任务: {task_id}")
        return False
    
    def update_task_progress(self, task_id: str, progress: int) -> bool:
        """
        更新任务进度
        
        参数:
        task_id: 任务ID
        progress: 进度百分比
        
        返回:
        是否成功
        """
        with self._lock:
            for task in self.tasks:
                if task["task_id"] == task_id:
                    task["progress"] = progress
                    task["updated_at"] = datetime.datetime.now()
                    self._save_tasks()
                    logger.info(f"已更新任务进度: {task_id} -> {progress}%")
                    return True
        logger.warning(f"未找到任务: {task_id}")
        return False
    
    def update_task_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        """
        更新任务结果
        
        参数:
        task_id: 任务ID
        result: 任务结果
        
        返回:
        是否成功
        """
        with self._lock:
            for task in self.tasks:
                if task["task_id"] == task_id:
                    task["result"] = result
                    task["status"] = "completed"
                    task["progress"] = 100
                    task["updated_at"] = datetime.datetime.now()
                    self._save_tasks()
                    logger.info(f"已更新任务结果: {task_id}")
                    return True
        logger.warning(f"未找到任务: {task_id}")
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        参数:
        task_id: 任务ID
        
        返回:
        是否成功
        """
        with self._lock:
            for i, task in enumerate(self.tasks):
                if task["task_id"] == task_id:
                    del self.tasks[i]
                    self._save_tasks()
                    logger.info(f"已删除任务: {task_id}")
                    return True
        logger.warning(f"未找到任务: {task_id}")
        return False
    
    def _start_processor(self):
        """启动任务处理线程"""
        if not self.processor_running:
            self.processor_running = True
            self.processor_thread = threading.Thread(target=self._processor_loop)
            self.processor_thread.daemon = True
            self.processor_thread.start()
            logger.info("任务处理线程已启动")
    
    def _processor_loop(self):
        """任务处理循环"""
        while self.processor_running:
            try:
                # 获取待处理任务
                with self._lock:
                    pending_tasks = [task for task in self.tasks if task["status"] == "pending"]
                    pending_tasks.sort(key=lambda t: self._get_priority_value(t["priority"]))
                
                if pending_tasks:
                    # 处理第一个任务
                    task = pending_tasks[0]
                    logger.info(f"开始处理任务: {task['task_id']}")
                    
                    # 更新任务状态为处理中
                    self.update_task_status(task["task_id"], "processing")
                    
                    try:
                        # 根据任务类型处理任务
                        if task["task_type"] == "auto_video":
                            # 这里应该调用视频处理服务
                            # 暂时跳过，仅作为示例
                            logger.info(f"模拟处理任务: {task['task_id']}")
                            
                            # 更新进度（模拟）
                            for progress in range(0, 101, 10):
                                self.update_task_progress(task["task_id"], progress)
                                time.sleep(1)  # 模拟处理时间
                            
                            # 更新结果
                            result = {
                                "success": True,
                                "message": "任务处理成功",
                                "final_video": "/path/to/video.mp4"  # 示例路径
                            }
                            self.update_task_result(task["task_id"], result)
                        
                        else:
                            logger.warning(f"未知的任务类型: {task['task_type']}")
                            self.update_task_status(task["task_id"], "failed")
                    
                    except Exception as e:
                        logger.error(f"处理任务时出错: {str(e)}")
                        # 更新任务状态为失败
                        self.update_task_status(task["task_id"], "failed")
                
                # 等待一段时间
                time.sleep(5)
            
            except Exception as e:
                logger.error(f"任务处理循环中出错: {str(e)}")
                time.sleep(10)  # 出错后等待更长时间
    
    def _get_priority_value(self, priority: str) -> int:
        """获取优先级数值"""
        if priority == "high":
            return 0
        elif priority == "normal":
            return 1
        else:  # low
            return 2
    
    def stop_processor(self):
        """停止任务处理线程"""
        if self.processor_running:
            self.processor_running = False
            if self.processor_thread:
                self.processor_thread.join(timeout=2)
            logger.info("任务处理线程已停止") 