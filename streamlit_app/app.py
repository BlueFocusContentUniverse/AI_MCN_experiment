import os
import streamlit as st
import sys

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from streamlit_app.config import APP_NAME

# 设置页面配置
st.set_page_config(
    page_title=APP_NAME,
    page_icon="🎬",
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

# 主页内容
def main():
    # 页面标题
    st.title(f"🎬 {APP_NAME}")
    
    # 简介
    st.markdown("""
    欢迎使用视频解析平台，本系统可以自动分析视频内容，提取关键信息，为你的视频制作提供帮助。
    
    请通过左侧边栏进行导航，选择所需功能。
    """)
    
    # 主要功能简介
    st.subheader("主要功能")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📤 上传视频")
        st.markdown("""
        上传视频文件进行解析，支持批量上传。
        可以设置品牌、型号和特殊需求等参数。
        """)
        st.markdown("[前往上传](./upload)", unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 🔍 任务监控")
        st.markdown("""
        查看所有解析任务的状态和进度。
        可以取消、重启或删除任务。
        """)
        st.markdown("[查看任务](./tasks)", unsafe_allow_html=True)
    
    with col3:
        st.markdown("### 📊 解析结果")
        st.markdown("""
        浏览已解析的视频结果。
        查看视频分段、主题分析和关键事件等信息。
        """)
        st.markdown("[浏览结果](./results)", unsafe_allow_html=True)
    
    # 系统信息
    st.markdown("---")
    st.subheader("系统信息")
    
    # 这里可以添加一些系统状态信息，如MongoDB连接状态、已解析视频数量等
    try:
        from streamlit_app.services.mongo_service import TaskManagerService
        task_manager = TaskManagerService()
        
        # 安全获取任务数量
        try:
            # 首先检查是否有count_tasks方法
            if hasattr(task_manager, 'count_tasks'):
                pending_count = task_manager.count_tasks("pending")
                processing_count = task_manager.count_tasks("processing")
                completed_count = task_manager.count_tasks("completed")
            else:
                # 如果没有，使用替代方法
                pending_count = len(task_manager.get_tasks(status="pending"))
                processing_count = len(task_manager.get_tasks(status="processing"))
                completed_count = len(task_manager.get_tasks(status="completed"))
        except Exception as count_error:
            st.error(f"获取任务统计信息时出错: {str(count_error)}")
            pending_count = processing_count = completed_count = "N/A"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("待处理任务", pending_count)
        
        with col2:
            st.metric("处理中任务", processing_count)
        
        with col3:
            st.metric("已完成任务", completed_count)
        
        with col4:
            # 获取视频总数
            try:
                videos_collection = task_manager.db["videos"]
                video_count = videos_collection.count_documents({})
                st.metric("已解析视频", video_count)
            except Exception as video_count_error:
                st.error(f"获取视频统计数据时出错: {str(video_count_error)}")
                st.metric("已解析视频", "N/A")
            
    except Exception as e:
        st.error(f"获取系统信息时出错: {str(e)}")
        st.info("请确保MongoDB服务已启动且连接信息正确")

# 运行主函数
if __name__ == "__main__":
    main() 