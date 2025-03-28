import os
import streamlit as st
import sys
import datetime
import time
import shutil
import uuid

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from streamlit_app.config import (
    APP_NAME, UPLOAD_DIR, DEFAULT_BRANDS, PROCESSING_OPTIONS, MAX_UPLOAD_SIZE
)
from streamlit_app.services.mongo_service import TaskManagerService
from streamlit_app.utils.video_processor import VideoProcessorService

# 设置页面配置
st.set_page_config(
    page_title=f"上传视频 - {APP_NAME}",
    page_icon="📤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化服务
task_manager = TaskManagerService()
video_processor = VideoProcessorService()

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

def save_uploaded_file(uploaded_file, task_dir):
    """保存上传的文件到指定目录"""
    file_path = os.path.join(task_dir, uploaded_file.name)
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return file_path

def handle_file_upload():
    """处理文件上传"""
    # 创建表单
    with st.form("upload_form"):
        st.title("📤 上传视频")
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        
        # 显示任务名称输入框
        task_name = st.text_input("任务名称", f"视频解析任务 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 文件上传控件
        uploaded_files = st.file_uploader("选择视频文件", type=["mp4", "avi", "mov", "mkv"], accept_multiple_files=True)
        
        # 任务配置
        col1, col2 = st.columns(2)
        
        with col1:
            # 获取现有品牌列表（从数据库动态获取）
            existing_brands = task_manager.get_brands()
            brand_list = sorted(existing_brands) if existing_brands else []
            
            # 品牌选择
            brand = st.selectbox("品牌", [""] + brand_list, index=0)
            brand_input = st.text_input("其他品牌", "", help="如果上面的下拉框中没有你需要的品牌，请在这里输入")
            
            # 使用输入的品牌（如果有）
            if brand_input:
                brand = brand_input
                # 添加提示，说明将保存这个新品牌
                st.info(f"将使用新品牌: {brand_input}（任务完成后会自动保存到品牌列表）")
        
        with col2:
            # 型号输入
            model = st.text_input("产品型号", "")
        
        # 特殊需求
        special_requirements = st.text_area("特殊需求", "", help="请输入对视频解析的特殊要求，如需要关注的内容、分析重点等")
        
        # 高级选项
        with st.expander("高级选项", expanded=False):
            options = {}
            for key, option in PROCESSING_OPTIONS.items():
                options[key] = st.checkbox(
                    option["label"], 
                    value=option["default"],
                    help=option["description"]
                )
        
        # 提交按钮
        submit_button = st.form_submit_button("开始解析")
        
        if submit_button:
            if not uploaded_files:
                st.error("请上传至少一个视频文件")
                return
            
            # 验证文件大小
            for uploaded_file in uploaded_files:
                if uploaded_file.size > MAX_UPLOAD_SIZE:
                    st.error(f"文件 {uploaded_file.name} 超过最大允许大小 ({MAX_UPLOAD_SIZE / 1024 / 1024} MB)")
                    return
            
            # 创建任务目录
            task_dir = os.path.join(UPLOAD_DIR, task_id)
            os.makedirs(task_dir, exist_ok=True)
            
            # 保存上传的文件
            video_paths = []
            with st.spinner("正在保存上传的文件..."):
                for uploaded_file in uploaded_files:
                    file_path = save_uploaded_file(uploaded_file, task_dir)
                    video_paths.append({
                        "file_name": uploaded_file.name,
                        "file_path": file_path
                    })
            
            # 创建任务配置
            config = {
                "brand": brand,
                "model": model,
                "special_requirements": special_requirements,
                "options": options
            }
            
            # 创建任务
            try:
                with st.spinner("正在创建解析任务..."):
                    task_id = task_manager.create_task(task_name, video_paths, config)
                    
                    # 启动处理
                    video_processor.start_processing(task_id)
                
                # 显示成功消息
                st.success(f"任务创建成功！任务ID: {task_id}")
                
                # 显示链接到任务页面
                st.markdown(f"[查看任务状态](./tasks?task_id={task_id})")
                
            except Exception as e:
                st.error(f"创建任务失败: {str(e)}")
                
                # 清理任务目录
                try:
                    shutil.rmtree(task_dir)
                except:
                    pass

def main():
    # 添加调试信息（可以在开发阶段查看，后期可移除）
    with st.expander("调试信息", expanded=False):
        try:
            brands = task_manager.get_brands()
            st.write(f"从数据库获取的品牌: {brands}")
            
            # 检查MongoDB连接状态
            try:
                collections = task_manager.db.list_collection_names()
                st.write(f"MongoDB连接状态: 正常")
                st.write(f"可用的集合: {collections}")
            except Exception as db_e:
                st.error(f"MongoDB连接错误: {str(db_e)}")
            
            # 显示当前配置
            st.write("当前配置信息:")
            st.json({
                "DEFAULT_BRANDS": DEFAULT_BRANDS,
                "UPLOAD_DIR": UPLOAD_DIR,
                "MAX_UPLOAD_SIZE": f"{MAX_UPLOAD_SIZE / (1024*1024):.2f} MB",
                "MONGODB_DB": os.environ.get('MONGODB_DB', '未设置')
            })
            
        except Exception as e:
            st.error(f"获取调试信息时出错: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    
    # 显示上传表单
    handle_file_upload()
    
    # 显示最近的任务
    st.markdown("---")
    st.header("最近的任务")
    
    try:
        # 获取最近的5个任务
        recent_tasks = task_manager.get_tasks(limit=5)
        
        if not recent_tasks:
            st.info("没有找到任务")
        else:
            for task in recent_tasks:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.markdown(f"**{task.get('task_name', '未命名任务')}**")
                
                with col2:
                    st.markdown(f"{task.get('total_videos', 0)} 个视频")
                
                with col3:
                    st.markdown(f"{task.get('status', '未知')}")
                
                with col4:
                    st.markdown(f"[查看详情](./_tasks?task_id={task.get('_id')})")
                
                st.markdown("---")
    
    except Exception as e:
        st.error(f"获取任务列表时出错: {str(e)}")

# 运行主函数
if __name__ == "__main__":
    main() 