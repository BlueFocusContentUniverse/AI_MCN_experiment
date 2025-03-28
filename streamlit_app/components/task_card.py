import streamlit as st
from typing import Dict, Any, Callable
import datetime
from streamlit_app.components.status_badge import status_badge

def format_datetime(dt_str: str) -> str:
    """格式化日期时间字符串"""
    try:
        # 检查是否已经是datetime对象
        if isinstance(dt_str, datetime.datetime):
            dt = dt_str
        else:
            # 解析ISO格式字符串
            dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        # 如果解析失败，返回原始字符串
        return str(dt_str)

def task_card(task: Dict[str, Any], on_cancel: Callable = None, on_restart: Callable = None) -> None:
    """
    显示任务卡片
    
    参数:
    task: 任务信息
    on_cancel: 取消任务的回调函数
    on_restart: 重启任务的回调函数
    """
    with st.container():
        # 使用列布局
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            # 任务标题和ID
            st.markdown(f"### {task.get('task_name', '未命名任务')}")
            st.markdown(f"**ID:** `{task.get('_id', '')}`")
            
            # 任务时间
            created_at = format_datetime(task.get("created_at", ""))
            updated_at = format_datetime(task.get("updated_at", ""))
            st.markdown(f"**创建时间:** {created_at}")
            st.markdown(f"**更新时间:** {updated_at}")
        
        with col2:
            # 状态
            st.markdown("**状态:**")
            status_badge(task.get("status", "未知"))
            
            # 进度
            progress = task.get("progress", 0)
            st.progress(progress / 100)
            st.markdown(f"**进度:** {progress}%")
        
        with col3:
            # 视频信息
            total = task.get("total_videos", 0)
            processed = task.get("processed_videos", 0)
            failed = task.get("failed_videos", 0)
            
            st.markdown(f"**总视频数:** {total}")
            st.markdown(f"**已处理:** {processed}")
            
            if failed > 0:
                st.markdown(f"**失败:** {failed}", unsafe_allow_html=True)
            
            # 操作按钮
            if task.get("status") in ["pending", "processing"]:
                if on_cancel:
                    if st.button("取消任务", key=f"cancel_{task['_id']}"):
                        on_cancel(task["_id"])
            
            elif task.get("status") in ["failed", "canceled"] and on_restart:
                if st.button("重新启动", key=f"restart_{task['_id']}"):
                    on_restart(task["_id"])
        
        # 任务配置
        with st.expander("任务配置"):
            config = task.get("config", {})
            
            st.markdown(f"**品牌:** {config.get('brand', '未指定')}")
            st.markdown(f"**型号:** {config.get('model', '未指定')}")
            
            if "special_requirements" in config and config["special_requirements"]:
                st.markdown("**特殊需求:**")
                st.text_area("", config["special_requirements"], disabled=True, height=100, key=f"req_{task['_id']}")
            
            # 显示处理选项
            if "options" in config:
                st.markdown("**处理选项:**")
                for key, value in config["options"].items():
                    st.markdown(f"- {key}: {value}")
        
        # 视频列表
        with st.expander("视频列表"):
            videos = task.get("videos", [])
            
            if not videos:
                st.markdown("无视频")
            else:
                for i, video in enumerate(videos):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"**{i+1}. {video.get('file_name', '未知文件')}**")
                    
                    with col2:
                        status_badge(video.get("status", "未知"))
                    
                    with col3:
                        if video.get("video_id"):
                            st.markdown(f"[查看结果](./results?video_id={video.get('video_id')})")
                    
                    # 如果有错误信息，显示错误
                    if video.get("error"):
                        st.markdown(f"**错误:** {video.get('error')}")
                    
                    st.markdown("---")
        
        # 分隔线
        st.markdown("---")

def compact_task_card(task: Dict[str, Any]) -> None:
    """
    显示紧凑版任务卡片
    
    参数:
    task: 任务信息
    """
    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
    
    with col1:
        st.markdown(f"**{task.get('task_name', '未命名任务')}**  \n`{task.get('_id', '')[:8]}...`")
    
    with col2:
        created_at = format_datetime(task.get("created_at", ""))
        st.markdown(f"{created_at}")
    
    with col3:
        status = task.get("status", "未知")
        st.markdown(f"<div style='text-align: center'>{status}</div>", unsafe_allow_html=True)
    
    with col4:
        progress = task.get("progress", 0)
        st.progress(progress / 100)
    
    with col5:
        total = task.get("total_videos", 0)
        processed = task.get("processed_videos", 0)
        st.markdown(f"{processed}/{total}")
    