import os
import streamlit as st
import sys
import datetime
import time

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from streamlit_app.config import APP_NAME, REFRESH_INTERVAL
from streamlit_app.services.mongo_service import TaskManagerService
from streamlit_app.utils.video_processor import VideoProcessorService
from streamlit_app.components.task_card import task_card, compact_task_card
from streamlit_app.components.status_badge import status_badge, inline_status_badge

# 设置页面配置
st.set_page_config(
    page_title=f"任务监控 - {APP_NAME}",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 添加自定义样式
st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3, h4, h5, h6 {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .stButton>button {
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# 初始化服务
task_manager = TaskManagerService()
video_processor = VideoProcessorService()

# 自定义排序函数，将ISO格式字符串转换为datetime进行比较
def get_created_time(task):
    try:
        created_at = task.get("created_at", "")
        if isinstance(created_at, datetime.datetime):
            return created_at
        else:
            return datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    except:
        # 如果解析失败，返回一个非常早的日期
        return datetime.datetime(1970, 1, 1)

def handle_cancel_task(task_id):
    """处理取消任务事件"""
    try:
        # 取消任务
        if video_processor.is_task_active(task_id):
            video_processor.cancel_processing(task_id)
        else:
            task_manager.cancel_task(task_id)
        
        st.success(f"已取消任务 {task_id}")
        
        # 重新加载页面数据
        st.rerun()
        
    except Exception as e:
        st.error(f"取消任务时出错: {str(e)}")

def handle_restart_task(task_id):
    """处理重启任务事件"""
    try:
        # 重启任务
        video_processor.start_processing(task_id)
        
        st.success(f"已重启任务 {task_id}")
        
        # 重新加载页面数据
        st.rerun()
        
    except Exception as e:
        st.error(f"重启任务时出错: {str(e)}")

def handle_delete_task(task_id):
    """处理删除任务事件"""
    try:
        # 删除任务
        task_manager.delete_task(task_id)
        
        st.success(f"已删除任务 {task_id}")
        
        # 重新加载页面数据
        st.rerun()
        
    except Exception as e:
        st.error(f"删除任务时出错: {str(e)}")

def task_detail(task_id):
    """显示任务详情"""
    try:
        # 获取任务信息
        task = task_manager.get_task(task_id)
        
        if not task:
            st.error(f"未找到任务: {task_id}")
            return
        
        # 显示任务卡片
        task_card(task, on_cancel=handle_cancel_task, on_restart=handle_restart_task)
        
        # 添加删除按钮
        if st.button("删除任务", key=f"delete_{task_id}"):
            handle_delete_task(task_id)
        
    except Exception as e:
        st.error(f"显示任务详情时出错: {str(e)}")

def show_active_tasks():
    """显示活跃任务"""
    try:
        # 获取处理中的任务
        processing_tasks = task_manager.get_tasks(status="processing")
        
        if not processing_tasks:
            st.info("当前没有正在处理的任务")
            return
        
        # 显示每个活跃任务
        for task in processing_tasks:
            task_card(task, on_cancel=handle_cancel_task)
            
    except Exception as e:
        st.error(f"显示活跃任务时出错: {str(e)}")

def show_pending_tasks():
    """显示等待中的任务"""
    try:
        # 获取等待中的任务
        pending_tasks = task_manager.get_tasks(status="pending")
        
        if not pending_tasks:
            st.info("当前没有等待中的任务")
            return
        
        # 显示任务表头
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        
        with col1:
            st.markdown("**任务名称**")
        
        with col2:
            st.markdown("**创建时间**")
        
        with col3:
            st.markdown("**状态**")
        
        with col4:
            st.markdown("**进度**")
        
        with col5:
            st.markdown("**视频数**")
        
        st.markdown("---")
        
        # 显示每个任务
        for task in pending_tasks:
            compact_task_card(task)
            
            col1, col2 = st.columns([5, 1])
            
            with col2:
                if st.button("开始处理", key=f"start_{task['_id']}"):
                    video_processor.start_processing(task["_id"])
                    st.rerun()
        
    except Exception as e:
        st.error(f"显示等待中的任务时出错: {str(e)}")

def show_completed_tasks():
    """显示已完成的任务"""
    try:
        # 获取已完成的任务
        completed_tasks = task_manager.get_tasks(status="completed")
        completed_with_errors_tasks = task_manager.get_tasks(status="completed_with_errors")
        
        # 合并列表
        all_completed_tasks = completed_tasks + completed_with_errors_tasks
        
        if not all_completed_tasks:
            st.info("当前没有已完成的任务")
            return
        
        # 使用相同的排序函数
        all_completed_tasks.sort(key=get_created_time, reverse=True)
        
        # 显示任务表头
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        
        with col1:
            st.markdown("**任务名称**")
        
        with col2:
            st.markdown("**创建时间**")
        
        with col3:
            st.markdown("**状态**")
        
        with col4:
            st.markdown("**进度**")
        
        with col5:
            st.markdown("**视频数**")
        
        st.markdown("---")
        
        # 显示每个任务
        for task in all_completed_tasks:
            compact_task_card(task)
        
    except Exception as e:
        st.error(f"显示已完成任务时出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def show_failed_tasks():
    """显示失败的任务"""
    try:
        # 获取失败或取消的任务
        failed_tasks = task_manager.get_tasks(status="failed")
        canceled_tasks = task_manager.get_tasks(status="canceled")
        
        # 合并列表
        all_failed_tasks = failed_tasks + canceled_tasks
        
        if not all_failed_tasks:
            st.info("当前没有失败或取消的任务")
            return
        
        # 使用相同的排序函数
        all_failed_tasks.sort(key=get_created_time, reverse=True)
        
        # 显示任务表头
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        
        with col1:
            st.markdown("**任务名称**")
        
        with col2:
            st.markdown("**创建时间**")
        
        with col3:
            st.markdown("**状态**")
        
        with col4:
            st.markdown("**进度**")
        
        with col5:
            st.markdown("**视频数**")
        
        st.markdown("---")
        
        # 显示每个任务
        for task in all_failed_tasks:
            compact_task_card(task)
            
            col1, col2 = st.columns([5, 1])
            
            with col2:
                if st.button("重新启动", key=f"restart_{task['_id']}"):
                    handle_restart_task(task["_id"])
        
    except Exception as e:
        st.error(f"显示失败任务时出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def render_task_tabs():
    """渲染任务选项卡"""
    tab1, tab2, tab3, tab4 = st.tabs(["处理中", "等待中", "已完成", "失败/取消"])
    
    with tab1:
        show_active_tasks()
    
    with tab2:
        show_pending_tasks()
    
    with tab3:
        show_completed_tasks()
    
    with tab4:
        show_failed_tasks()

def main():
    # 显示页面标题
    st.title("🔍 任务监控")
    
    # 获取URL参数
    query_params = st.experimental_get_query_params()
    task_id = query_params.get("task_id", [""])[0]
    
    # 存储选中的任务ID
    if "selected_task_id" not in st.session_state:
        st.session_state.selected_task_id = task_id
    
    # 如果URL中有任务ID参数
    if task_id:
        # 如果不是当前选中的任务，更新选中的任务ID
        if st.session_state.selected_task_id != task_id:
            st.session_state.selected_task_id = task_id
    
    # 如果有选中的任务，显示任务详情
    if st.session_state.selected_task_id:
        st.markdown("---")
        st.subheader("任务详情")
        task_detail(st.session_state.selected_task_id)
        
        # 添加返回按钮
        if st.button("返回任务列表"):
            st.session_state.selected_task_id = ""
            st.rerun()
    else:
        # 否则，显示任务列表
        st.markdown("---")
        st.subheader("任务列表")
        render_task_tabs()
    
    # 自动刷新页面
    # 注意：过于频繁的刷新可能会导致页面卡顿，谨慎使用
    if st.session_state.get("auto_refresh", False):
        st.markdown(f"""
        <script>
            setTimeout(function() {{
                window.location.reload();
            }}, {REFRESH_INTERVAL * 1000});
        </script>
        """, unsafe_allow_html=True)

# 运行主函数
if __name__ == "__main__":
    main() 