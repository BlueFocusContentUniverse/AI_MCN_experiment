import streamlit as st
import time
import logging

# 配置日志
logger = logging.getLogger(__name__)

def processing_status(processor):
    """
    显示视频处理状态组件
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("系统状态")
    
    try:
        # 创建四列布局
        col1, col2, col3, col4 = st.columns(4)
        
        # 活跃工作线程数
        with col1:
            try:
                active_workers = processor.get_active_workers_count()
                total_workers = processor.max_workers
                st.metric(
                    "活跃工作线程", 
                    f"{active_workers}/{total_workers}",
                    delta=active_workers - (total_workers // 2),
                    delta_color="inverse"  # 负值为绿色，表示有空闲资源
                )
            except Exception as e:
                logger.error(f"获取工作线程状态时出错: {str(e)}")
                st.metric("活跃工作线程", "N/A")
        
        # 活跃任务数
        with col2:
            try:
                active_tasks = processor.get_active_tasks_count()
                # 如果属性不存在，使用默认值1
                max_tasks = getattr(processor, "max_concurrent_tasks", 1)
                st.metric(
                    "当前处理任务", 
                    f"{active_tasks}/{max_tasks}",
                    delta=active_tasks - (max_tasks // 2),
                    delta_color="inverse"  # 负值为绿色，表示有空闲资源
                )
            except Exception as e:
                logger.error(f"获取活跃任务状态时出错: {str(e)}")
                st.metric("当前处理任务", "N/A")
        
        # 队列大小
        with col3:
            try:
                queue_size = processor.get_queue_size()
                st.metric(
                    "待处理视频", 
                    queue_size,
                    delta=None
                )
            except Exception as e:
                logger.error(f"获取队列大小时出错: {str(e)}")
                st.metric("待处理视频", "N/A")
        
        # 处理速度（仅模拟，实际应从统计数据计算）
        with col4:
            # 这里模拟每秒处理的视频数量，实际应该基于历史数据计算
            processing_rate = "~1-2 视频/分钟"
            st.metric(
                "处理速度", 
                processing_rate,
                delta=None
            )
        
        # 添加一个刷新按钮
        if st.button("刷新状态", key="refresh_status"):
            st.rerun()
    
    except Exception as e:
        st.error(f"显示处理状态时出错: {str(e)}")
        logger.error(f"显示处理状态时出错: {str(e)}")

def worker_status_table(processor):
    """
    显示工作线程状态表格
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("工作线程状态")
    
    try:
        # 获取所有工作线程状态
        workers_status = []
        
        # 获取工作线程状态列表，如果不存在则使用空列表
        try:
            # 尝试使用.worker_status属性
            worker_status_list = processor.worker_status if hasattr(processor, "worker_status") else []
        except Exception as e:
            logger.error(f"使用worker_status属性时出错: {str(e)}")
            worker_status_list = []
        
        if not worker_status_list and hasattr(processor, "active_tasks"):
            # 如果没有worker_status但有active_tasks，则使用active_tasks模拟状态
            if processor.active_tasks:
                worker_status_list = [True]  # 有活跃任务，则工作线程忙碌
            else:
                worker_status_list = [False]  # 没有活跃任务，则工作线程空闲
        
        # 如果还是空的，使用活跃工作线程数创建状态列表
        if not worker_status_list:
            try:
                active_count = processor.get_active_workers_count()
                total_count = getattr(processor, "max_workers", 1)
                worker_status_list = [i < active_count for i in range(total_count)]
            except Exception as e:
                logger.error(f"使用活跃工作线程数创建状态列表时出错: {str(e)}")
                worker_status_list = [False]
        
        for i, is_busy in enumerate(worker_status_list):
            status = "忙碌" if is_busy else "空闲"
            workers_status.append({
                "ID": f"worker_{i}",
                "状态": status,
                "更新时间": time.strftime("%H:%M:%S")
            })
        
        if not workers_status:
            st.info("无法获取工作线程状态")
            return
            
        # 显示表格
        st.table(workers_status)
    
    except Exception as e:
        st.error(f"显示工作线程状态时出错: {str(e)}")
        logger.error(f"显示工作线程状态时出错: {str(e)}")

def task_queue_preview(processor):
    """
    显示任务队列预览
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("任务队列预览")
    
    try:
        # 获取队列大小
        queue_size = 0
        try:
            queue_size = processor.get_queue_size()
        except Exception as e:
            logger.error(f"获取队列大小时出错: {str(e)}")
        
        if queue_size == 0:
            st.info("当前没有待处理的视频")
            return
        
        # 显示队列信息
        st.write(f"当前有 {queue_size} 个视频在队列中等待处理")
        
        # 可以在这里添加队列中待处理视频的预览信息
        # 由于队列对象不支持非破坏性查看，这里只能显示数量
        
        # 添加一个进度条，表示队列处理进度
        st.progress(min(1.0, queue_size / 10))  # 假设队列最大容量为10 
    except Exception as e:
        st.error(f"显示任务队列时出错: {str(e)}")
        logger.error(f"显示任务队列时出错: {str(e)}") 