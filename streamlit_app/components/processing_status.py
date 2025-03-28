import streamlit as st
import time
from services.video_processor_service import VideoProcessorService

def processing_status(processor: VideoProcessorService):
    """
    显示视频处理状态组件
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("系统状态")
    
    # 创建四列布局
    col1, col2, col3, col4 = st.columns(4)
    
    # 活跃工作线程数
    with col1:
        active_workers = processor.get_active_workers_count()
        total_workers = processor.max_workers
        st.metric(
            "活跃工作线程", 
            f"{active_workers}/{total_workers}",
            delta=active_workers - (total_workers // 2),
            delta_color="inverse"  # 负值为绿色，表示有空闲资源
        )
    
    # 活跃任务数
    with col2:
        active_tasks = processor.get_active_tasks_count()
        max_tasks = processor.max_concurrent_tasks
        st.metric(
            "当前处理任务", 
            f"{active_tasks}/{max_tasks}",
            delta=active_tasks - (max_tasks // 2),
            delta_color="inverse"  # 负值为绿色，表示有空闲资源
        )
    
    # 队列大小
    with col3:
        queue_size = processor.get_queue_size()
        st.metric(
            "待处理视频", 
            queue_size,
            delta=None
        )
    
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

def worker_status_table(processor: VideoProcessorService):
    """
    显示工作线程状态表格
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("工作线程状态")
    
    # 获取所有工作线程状态
    workers_status = []
    for i in range(processor.max_workers):
        status = "忙碌" if processor.worker_status[i] else "空闲"
        workers_status.append({
            "ID": f"worker_{i}",
            "状态": status,
            "更新时间": time.strftime("%H:%M:%S")
        })
    
    # 显示表格
    st.table(workers_status)

def task_queue_preview(processor: VideoProcessorService):
    """
    显示任务队列预览
    
    参数:
    processor: 视频处理服务实例
    """
    st.subheader("任务队列预览")
    
    # 获取队列大小
    queue_size = processor.get_queue_size()
    
    if queue_size == 0:
        st.info("当前没有待处理的视频")
        return
    
    # 显示队列信息
    st.write(f"当前有 {queue_size} 个视频在队列中等待处理")
    
    # 可以在这里添加队列中待处理视频的预览信息
    # 由于队列对象不支持非破坏性查看，这里只能显示数量
    
    # 添加一个进度条，表示队列处理进度
    st.progress(min(1.0, queue_size / 10))  # 假设队列最大容量为10 