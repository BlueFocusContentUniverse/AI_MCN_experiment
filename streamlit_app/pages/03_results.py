import os
import streamlit as st
import sys
from datetime import datetime, timedelta
import logging
from bson import ObjectId

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from streamlit_app.config import APP_NAME
from streamlit_app.services.mongo_service import TaskManagerService
from streamlit_app.components.video_card import video_card, video_grid, video_detail_view

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置页面配置
st.set_page_config(
    page_title=f"解析结果 - {APP_NAME}",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化服务
task_manager = TaskManagerService()

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

def show_video_list():
    """显示视频列表"""
    st.title("📊 视频解析结果")
    
    # 默认使用过去30天到今天的时间范围
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # 调试模式选项
    debug_mode = st.sidebar.checkbox("调试模式", value=False)
    show_all = st.sidebar.checkbox("显示所有视频(忽略筛选条件)", value=False)
    
    if debug_mode:
        st.sidebar.info("调试模式已启用，将显示更多技术信息")
    
    # 强制显示所有视频选项
    force_show_all = st.sidebar.button("一键显示所有视频")
    
    if force_show_all:
        show_all = True
    
    # 筛选器
    with st.expander("筛选条件", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 品牌筛选
            try:
                existing_brands = task_manager.get_brands()
                if debug_mode:
                    st.write(f"找到品牌: {existing_brands}")
            except Exception as e:
                if debug_mode:
                    st.error(f"获取品牌列表失败: {str(e)}")
                existing_brands = []
            
            brand = st.selectbox("品牌", ["所有品牌"] + existing_brands)
        
        with col2:
            # 型号筛选（简单起见，这里使用文本输入）
            model = st.text_input("产品型号")
        
        with col3:
            # 日期范围筛选 - 默认为过去30天到今天
            date_range = st.date_input(
                "日期范围",
                [thirty_days_ago, today]
            )
    
    # 创建筛选条件
    filters = {}
    
    if not show_all:
        if brand and brand != "所有品牌":
            filters["brand"] = brand
        
        if model:
            filters["model"] = model
        
        if len(date_range) >= 2:
            date_from, date_to = date_range[0], date_range[1]
            filters["date_from"] = datetime.combine(date_from, datetime.min.time())
            filters["date_to"] = datetime.combine(date_to, datetime.max.time())
    
    # 调试信息显示
    if debug_mode:
        st.write("### 调试信息")
        st.write(f"筛选条件: {filters}")
        st.write(f"MongoDB连接信息: {task_manager.db.name if hasattr(task_manager, 'db') else '无法获取'}")
        
        # 获取集合列表
        if hasattr(task_manager, 'db'):
            try:
                collections = task_manager.db.list_collection_names()
                st.write(f"数据库集合: {collections}")
                
                # 显示videos集合中的文档数量
                if 'videos' in collections:
                    video_count = task_manager.db.videos.count_documents({})
                    st.write(f"videos集合中的文档数量: {video_count}")
                    
                    # 显示一条视频记录样本
                    if video_count > 0:
                        sample_video = task_manager.db.videos.find_one({})
                        st.write("视频记录样本:")
                        st.json({k: str(v) if k == '_id' else v for k, v in sample_video.items()})
            except Exception as e:
                st.error(f"获取数据库信息时出错: {str(e)}")
    
    # 获取视频列表
    try:
        videos = []
        
        if debug_mode:
            st.write("正在查询视频...")
        
        if show_all:
            # 在show_all模式下直接从数据库查询视频
            try:
                # 直接从videos集合获取所有记录
                direct_videos = list(task_manager.db.videos.find().limit(50))
                # 转换ObjectId为字符串
                for video in direct_videos:
                    video["_id"] = str(video["_id"])
                    videos.append(video)
                if debug_mode:
                    st.write(f"直接查询返回 {len(videos)} 个结果")
            except Exception as direct_err:
                if debug_mode:
                    st.error(f"直接查询失败: {str(direct_err)}")
                # 如果直接查询失败，回退到使用get_video_results方法
                videos = task_manager.get_video_results({})
        else:
            # 使用get_video_results方法查询视频
            videos = task_manager.get_video_results(filters)
            
        if debug_mode:
            st.write(f"查询返回 {len(videos) if videos else 0} 个结果")
        
        if not videos:
            st.info("没有找到符合条件的视频")
            
            # 在调试模式下尝试查询所有视频
            if debug_mode:
                try:
                    all_videos = task_manager.get_video_results({})
                    st.write(f"数据库中共有 {len(all_videos) if all_videos else 0} 个视频记录")
                    
                    # 直接尝试从videos集合获取所有记录
                    try:
                        direct_videos = list(task_manager.db.videos.find().limit(20))
                        if direct_videos:
                            st.write(f"通过直接查询找到 {len(direct_videos)} 个视频记录")
                            st.write("### 直接从数据库查询到的视频记录")
                            for i, video in enumerate(direct_videos):
                                with st.expander(f"视频 {i+1}: {video.get('title', '未命名')}"):
                                    # 将ObjectId转换为字符串以便显示
                                    video_copy = {k: (str(v) if k == '_id' else v) for k, v in video.items()}
                                    st.json(video_copy)
                            
                            # 提供选项直接使用这些视频记录
                            if st.button("使用这些视频记录"):
                                # 转换ObjectId为字符串
                                converted_videos = []
                                for video in direct_videos:
                                    video["_id"] = str(video["_id"])
                                    converted_videos.append(video)
                                
                                # 重置视频列表
                                videos = converted_videos
                                st.success(f"已加载 {len(videos)} 个视频记录")
                                # 不要在这里rerun，让下面的代码继续执行
                    except Exception as direct_err:
                        st.error(f"直接查询视频记录时出错: {str(direct_err)}")
                
                except Exception as e:
                    st.error(f"尝试获取所有视频时出错: {str(e)}")
            
            # 如果仍然没有视频数据，返回
            if not videos:
                return
        
        # 显示视频数量
        st.subheader(f"找到 {len(videos)} 个视频")
        
        # 显示视频网格
        video_grid(videos, columns=3)
        
    except Exception as e:
        st.error(f"获取视频列表时出错: {str(e)}")
        if debug_mode:
            import traceback
            st.code(traceback.format_exc())

def show_video_detail(video_id):
    """显示视频详情"""
    try:
        # 获取视频信息
        videos_collection = task_manager.db["videos"]
        video = videos_collection.find_one({"_id": video_id})
        
        if not video:
            st.error(f"未找到视频: {video_id}")
            return
        
        # 尝试不同的片段集合名称
        possible_segment_collections = ["video_segments", "segments", "video_segment", "segment"]
        segments = []
        
        # 获取所有集合列表，查找可能包含segment的集合
        collections = task_manager.db.list_collection_names()
        st.sidebar.info(f"数据库中的集合: {', '.join(collections)}")
        
        segment_collections = [coll for coll in collections if "segment" in coll.lower()]
        if segment_collections:
            possible_segment_collections = segment_collections + possible_segment_collections
        
        # 尝试从每个可能的集合中获取片段
        for collection_name in possible_segment_collections:
            if collection_name in collections:
                st.sidebar.info(f"尝试从'{collection_name}'集合获取片段...")
                
                # 尝试多种ID格式
                id_formats = [
                    video_id,  # 原始ObjectId
                    str(video_id),  # 字符串ID
                ]
                
                # 如果视频文档中有"_id"字段，也尝试使用它
                if "_id" in video:
                    id_formats.append(video["_id"])
                
                # 尝试每种ID格式
                for id_format in id_formats:
                    try:
                        segment_query = {"video_id": id_format}
                        st.sidebar.info(f"使用查询: {segment_query}")
                        found_segments = list(task_manager.db[collection_name].find(segment_query).sort("start_time", 1))
                        
                        if found_segments:
                            segments = found_segments
                            st.sidebar.success(f"在'{collection_name}'集合中使用'{id_format}'格式的ID找到 {len(segments)} 个片段")
                            break
                    except Exception as e:
                        st.sidebar.error(f"使用ID格式'{id_format}'查询失败: {str(e)}")
                
                if segments:
                    break
        
        # 如果仍然没有找到片段，尝试使用cindematography_analysis中的片段
        if not segments and "cinematography_analysis" in video and "segments" in video["cinematography_analysis"]:
            st.sidebar.info("从cinematography_analysis中获取片段...")
            segments = video["cinematography_analysis"]["segments"]
            st.sidebar.success(f"从cinematography_analysis中找到 {len(segments)} 个片段")
        
        # 如果还是没有找到片段，提供一个选项从原始JSON中提取
        if not segments:
            st.sidebar.error("无法找到视频片段")
            
            if st.sidebar.button("从原始视频数据中提取片段"):
                try:
                    # 显示视频数据结构，辅助用户选择
                    with st.expander("视频数据结构", expanded=True):
                        # 移除可能的大字段，如嵌入向量
                        debug_video = video.copy()
                        if "embeddings" in debug_video:
                            debug_video["embeddings"] = "... [向量数据已省略] ..."
                        if "vision_analysis" in debug_video:
                            debug_video["vision_analysis"] = "... [视觉分析数据已省略] ..."
                        if "transcription" in debug_video:
                            debug_video["transcription"] = "... [转录数据已省略] ..."
                        st.json(debug_video)
                    
                    # 提供选项自定义路径
                    custom_path = st.sidebar.text_input("输入包含片段数据的路径 (例如: cinematography_analysis.segments)", "cinematography_analysis.segments")
                    
                    if custom_path and st.sidebar.button("提取片段数据"):
                        # 解析路径
                        path_parts = custom_path.split('.')
                        
                        # 从视频数据中提取
                        data = video
                        for part in path_parts:
                            if part in data:
                                data = data[part]
                            else:
                                st.sidebar.error(f"路径'{custom_path}'不存在")
                                break
                        
                        # 如果成功提取到列表数据
                        if isinstance(data, list):
                            segments = data
                            st.sidebar.success(f"成功从'{custom_path}'提取到 {len(segments)} 个片段")
                        else:
                            st.sidebar.error(f"路径'{custom_path}'未指向列表数据")
                
                except Exception as e:
                    st.sidebar.error(f"提取片段数据时出错: {str(e)}")
        
        # 调试信息
        st.sidebar.info(f"最终获取到 {len(segments)} 个视频片段")
        
        # 显示视频详情视图
        video_detail_view(video, segments)
        
        # 添加返回按钮
        if st.button("返回视频列表"):
            st.query_params.clear()
            st.rerun()
            
    except Exception as e:
        st.error(f"显示视频详情时出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def main():
    # 获取URL参数
    query_params = st.query_params
    
    # 检查是否有视频ID参数
    if "video_id" in query_params:
        try:
            video_id = ObjectId(query_params["video_id"])
            show_video_detail(video_id)
        except Exception as e:
            st.error(f"无效的视频ID: {query_params['video_id']}, 错误: {str(e)}")
            show_video_list()
    else:
        show_video_list()

# 运行主函数
if __name__ == "__main__":
    main() 