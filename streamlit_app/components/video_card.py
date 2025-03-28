import streamlit as st
from typing import Dict, Any, List, Optional
import json

def generate_thumbnail_url(video_id: str, segment_id: str = None, timestamp: float = 0) -> str:
    """
    生成缩略图URL
    暂时使用占位图片，实际项目中应替换为真实缩略图URL生成逻辑
    
    参数:
    video_id: 视频ID
    segment_id: 片段ID
    timestamp: 时间戳
    
    返回:
    缩略图URL
    """
    return f"https://via.placeholder.com/320x180.png?text=Video+{video_id[:6]}"

def video_card(video: Dict[str, Any]) -> None:
    """
    显示视频卡片
    
    参数:
    video: 视频信息
    """
    # 获取基本信息
    video_id = video.get("_id", "")
    title = video.get("title", "未命名视频")
    
    # 获取元数据
    metadata = video.get("metadata", {})
    brand = metadata.get("brand", "未知品牌")
    video_type = metadata.get("video_type", "未知类型")
    
    # 获取文件信息
    file_info = video.get("file_info", {})
    duration = file_info.get("duration", 0)
    duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
    
    # 获取统计信息
    stats = video.get("stats", {})
    segment_count = stats.get("segment_count", 0)
    
    # 生成缩略图URL
    thumbnail_url = generate_thumbnail_url(video_id)
    
    # 显示卡片
    with st.container():
        # 缩略图和基本信息
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(thumbnail_url, use_container_width=True)
        
        with col2:
            st.markdown(f"### {title}")
            st.markdown(f"**品牌:** {brand}")
            st.markdown(f"**类型:** {video_type}")
            st.markdown(f"**时长:** {duration_str}")
            st.markdown(f"**片段数:** {segment_count}")
            
            # 查看详情按钮
            st.markdown(f"[查看详情](./results?video_id={video_id})")
        
        st.markdown("---")

def video_grid(videos: List[Dict[str, Any]], columns: int = 3) -> None:
    """
    显示视频网格
    
    参数:
    videos: 视频列表
    columns: 列数
    """
    # 如果没有视频，显示提示
    if not videos:
        st.info("没有找到符合条件的视频")
        return
    
    # 计算行数
    n_videos = len(videos)
    n_rows = (n_videos + columns - 1) // columns
    
    # 显示网格
    for i in range(n_rows):
        cols = st.columns(columns)
        for j in range(columns):
            idx = i * columns + j
            if idx < n_videos:
                with cols[j]:
                    compact_video_card(videos[idx])

def compact_video_card(video: Dict[str, Any]) -> None:
    """
    显示紧凑版视频卡片
    
    参数:
    video: 视频信息
    """
    # 获取基本信息
    video_id = video.get("_id", "")
    title = video.get("title", "未命名视频")
    
    # 获取元数据
    metadata = video.get("metadata", {})
    brand = metadata.get("brand", "未知品牌")
    
    # 获取文件信息
    file_info = video.get("file_info", {})
    duration = file_info.get("duration", 0)
    duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
    
    # 生成缩略图URL
    thumbnail_url = generate_thumbnail_url(video_id)
    
    # 显示卡片
    st.image(thumbnail_url, use_container_width=True)
    st.markdown(f"**{title}**")
    st.markdown(f"{brand} | {duration_str}")
    st.markdown(f"[查看详情](./results?video_id={video_id})")

def video_segment_timeline(segments: List[Dict[str, Any]]) -> None:
    """
    显示视频片段时间线
    
    参数:
    segments: 片段列表
    """
    if not segments:
        st.info("没有找到视频片段")
        return
    
    try:
        # 对片段按开始时间排序
        segments = sorted(segments, key=lambda x: x.get("start_time", 0))
        
        # 计算总时长
        total_duration = segments[-1].get("end_time", 0) if segments else 0
        
        # 如果总时长为0或显著小于1，可能是数据问题
        if total_duration < 1:
            st.warning("视频片段总时长异常：不到1秒。可能是数据格式问题。")
            # 尝试寻找其他可能的时间字段
            alt_start_fields = ["start", "start_seconds", "begin"]
            alt_end_fields = ["end", "end_seconds", "finish"]
            
            for segment in segments:
                for start_field in alt_start_fields:
                    if start_field in segment and segment[start_field] is not None:
                        segment["start_time"] = float(segment[start_field])
                        break
                
                for end_field in alt_end_fields:
                    if end_field in segment and segment[end_field] is not None:
                        segment["end_time"] = float(segment[end_field])
                        break
            
            # 重新排序和计算总时长
            segments = sorted(segments, key=lambda x: x.get("start_time", 0))
            total_duration = segments[-1].get("end_time", 0) if segments else 0
            
            if total_duration < 1:
                st.error("即使尝试其他字段，视频片段总时长仍然异常。")
                
                # 提供手动设置总时长的选项
                manual_duration = st.number_input("手动设置视频总时长（秒）", value=60.0, step=5.0)
                if manual_duration > 0:
                    total_duration = manual_duration
                else:
                    return
                    
        # 显示调试信息
        st.write(f"总时长: {total_duration:.2f}秒")
        
        # 添加最小间距（片段之间的空隙百分比）
        MIN_GAP_PERCENT = 1.5
        
        # 计算片段之间的最小间距（秒）
        min_gap_seconds = (total_duration * MIN_GAP_PERCENT) / 100
        
        # 调整重叠的片段
        for i in range(1, len(segments)):
            prev_end = segments[i-1].get("end_time", 0)
            curr_start = segments[i].get("start_time", 0)
            
            # 如果当前片段与前一个片段重叠或间距过小
            if curr_start < prev_end + min_gap_seconds:
                # 调整为前一个片段结束时间加上最小间距
                segments[i]["start_time"] = prev_end + min_gap_seconds
                
                # 确保结束时间仍然大于开始时间
                if segments[i]["start_time"] >= segments[i].get("end_time", 0):
                    segments[i]["end_time"] = segments[i]["start_time"] + 0.5  # 至少0.5秒长度
        
        # 显示时间线和事件处理
        st.markdown("### 视频片段时间线")
        
        # 添加交互说明
        st.markdown("""
        <div style="margin-bottom: 10px; font-size: 14px; color: #666;">
            <i>提示: 将鼠标悬停在时间线上的片段可查看详细信息。点击片段可直接查看对应详情。</i>
        </div>
        """, unsafe_allow_html=True)
        
        # 使用HTML创建时间线
        html = """
        <style>
        .timeline-container {
            width: 100%;
            height: 60px;
            background-color: #f0f2f6;
            position: relative;
            margin-bottom: 20px;
            border-radius: 5px;
            overflow: hidden;
        }
        .timeline-segment {
            position: absolute;
            height: 50px;
            top: 5px;
            background-color: #4CAF50;
            opacity: 0.8;
            border-radius: 5px;
            border: 1px solid rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
            z-index: 1;
        }
        .timeline-segment:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        .timeline-gap {
            position: absolute;
            height: 60px;
            background-color: rgba(255,0,0,0.1);
            z-index: 0;
        }
        .timeline-marker {
            position: absolute;
            top: 60px;
            width: 1px;
            height: 5px;
            background-color: #333;
        }
        .timeline-marker-text {
            position: absolute;
            top: 65px;
            font-size: 9px;
            color: #666;
            transform: translateX(-50%);
        }
        </style>
        <div class="timeline-container">
        """
        
        # 添加时间标记
        for i in range(0, int(total_duration) + 1, max(1, int(total_duration // 10))):
            marker_percent = (i / total_duration) * 100
            html += f"""
            <div class="timeline-marker" style="left: {marker_percent}%;"></div>
            <div class="timeline-marker-text" style="left: {marker_percent}%;">{i}s</div>
            """
            
        # 添加片段间的间隙标识
        for i in range(1, len(segments)):
            prev_end = segments[i-1].get("end_time", 0)
            curr_start = segments[i].get("start_time", 0)
            
            if curr_start > prev_end:
                gap_start_percent = (prev_end / total_duration) * 100
                gap_width_percent = ((curr_start - prev_end) / total_duration) * 100
                
                html += f"""
                <div class="timeline-gap" style="left: {gap_start_percent}%; width: {gap_width_percent}%;"></div>
                """
        
        # 添加片段
        for i, segment in enumerate(segments):
            start_time = segment.get("start_time", 0)
            end_time = segment.get("end_time", 0)
            duration = end_time - start_time
            
            # 如果持续时间小于0，调整为至少0.1秒
            if duration <= 0:
                end_time = start_time + 0.1
                duration = 0.1
            
            # 计算位置和宽度
            left_percent = (start_time / total_duration) * 100
            width_percent = (duration / total_duration) * 100
            
            # 限制宽度不超过100%且不小于0.5%
            width_percent = min(100 - left_percent, max(0.5, width_percent))
            
            # 获取片段类型
            shot_type = segment.get("shot_type", "未知")
            
            # 根据片段类型设置颜色
            color = "#4CAF50"  # 默认颜色
            if "近景" in shot_type or "特写" in shot_type:
                color = "#2196F3"  # 蓝色
            elif "远景" in shot_type:
                color = "#FFC107"  # 黄色
            elif "中景" in shot_type:
                color = "#9C27B0"  # 紫色
            
            # 添加片段到时间线
            html += f"""
            <div class="timeline-segment" style="left: {left_percent}%; width: {width_percent}%; background-color: {color};"
                 title="{shot_type} ({start_time:.1f}s - {end_time:.1f}s)">
                {i+1}
            </div>
            """
        
        html += """
        </div>
        """
        
        # 添加JavaScript交互
        html += """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            // 获取所有时间线片段
            const segments = document.querySelectorAll('.timeline-segment');
            
            // 为每个片段添加点击事件
            segments.forEach(segment => {
                segment.addEventListener('click', function() {
                    // 获取片段编号（内部文本）
                    const segmentId = this.innerText.trim();
                    
                    // 使用Streamlit的selectbox控件，查找id包含"selectbox"的元素
                    const selectbox = document.querySelector('select[data-testid="stSelectbox"]');
                    if (selectbox) {
                        // 设置选择框的值为片段编号
                        selectbox.value = segmentId;
                        
                        // 触发change事件通知Streamlit
                        const event = new Event('change', { bubbles: true });
                        selectbox.dispatchEvent(event);
                    }
                });
            });
        });
        </script>
        """
        
        # 先渲染HTML时间线，再显示表格
        st.markdown(html, unsafe_allow_html=True)
        
        # 显示每个片段的信息表格
        st.markdown("### 片段信息汇总")
        
        # 创建表格
        segments_table = []
        for i, segment in enumerate(segments):
            start_time = segment.get("start_time", 0)
            end_time = segment.get("end_time", 0)
            duration = end_time - start_time
            segments_table.append({
                "编号": i+1,
                "开始时间": f"{start_time:.1f}s",
                "结束时间": f"{end_time:.1f}s", 
                "持续时间": f"{duration:.1f}s",
                "类型": segment.get("shot_type", "未知")
            })
        
        # 显示表格
        st.table(segments_table)
        
        # 显示片段详情
        with st.expander("视频片段详情", expanded=True):
            # 添加一个选择器，让用户可以选择查看特定片段
            selected_segment_idx = st.selectbox(
                "选择要查看的片段",
                options=range(1, len(segments) + 1),
                format_func=lambda x: f"片段 {x} ({segments[x-1].get('start_time', 0):.1f}s - {segments[x-1].get('end_time', 0):.1f}s)",
            )
            
            # 展示选中片段的详细信息
            if selected_segment_idx:
                segment = segments[selected_segment_idx - 1]
                start_time = segment.get("start_time", 0)
                end_time = segment.get("end_time", 0)
                shot_type = segment.get("shot_type", "未知")
                shot_description = segment.get("shot_description", "")
                
                # 使用卡片样式展示片段
                st.markdown(f"""
                <div style="padding: 1rem; border: 1px solid #e0e0e0; border-radius: 5px; margin-bottom: 1rem;">
                    <h3 style="margin-top: 0;">片段 {selected_segment_idx}</h3>
                    <p><strong>时间范围:</strong> {start_time:.1f}s - {end_time:.1f}s (时长: {end_time-start_time:.1f}s)</p>
                    <p><strong>类型:</strong> {shot_type}</p>
                    <p><strong>描述:</strong> {shot_description}</p>
                </div>
                """, unsafe_allow_html=True)
                
                # 使用标签页展示详细属性
                tab1, tab2, tab3 = st.tabs(["视觉元素", "电影语言", "音频分析"])
                
                with tab1:
                    visual_elements = segment.get("visual_elements", {})
                    if visual_elements:
                        for key, value in visual_elements.items():
                            if value:
                                st.markdown(f"**{key}:** {value}")
                    else:
                        st.info("无视觉元素数据")
                
                with tab2:
                    cinematic_language = segment.get("cinematic_language", {})
                    if cinematic_language:
                        for key, value in cinematic_language.items():
                            if value:
                                st.markdown(f"**{key}:** {value}")
                    else:
                        st.info("无电影语言数据")
                
                with tab3:
                    audio_analysis = segment.get("audio_analysis", {})
                    if audio_analysis:
                        for key, value in audio_analysis.items():
                            if value:
                                st.markdown(f"**{key}:** {value}")
                    else:
                        st.info("无音频分析数据")
    
    except Exception as e:
        st.error(f"显示视频片段时间线时出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def video_detail_view(video: Dict[str, Any], segments: List[Dict[str, Any]]) -> None:
    """
    显示视频详细信息
    
    参数:
    video: 视频信息
    segments: 视频片段列表
    """
    # 获取基本信息
    video_id = video.get("_id", "")
    title = video.get("title", "未命名视频")
    
    # 获取元数据
    metadata = video.get("metadata", {})
    brand = metadata.get("brand", "未知品牌")
    video_type = metadata.get("video_type", "未知类型")
    tags = metadata.get("tags", [])
    
    # 获取文件信息
    file_info = video.get("file_info", {})
    path = file_info.get("path", "")
    duration = file_info.get("duration", 0)
    duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
    
    # 调试信息 - 显示视频结构
    with st.expander("视频数据结构", expanded=False):
        # 移除可能的大字段，如嵌入向量
        debug_video = video.copy()
        if "embeddings" in debug_video:
            debug_video["embeddings"] = "... [向量数据已省略] ..."
        if "vision_analysis" in debug_video:
            debug_video["vision_analysis"] = "... [视觉分析数据已省略] ..."
        if "transcription" in debug_video:
            debug_video["transcription"] = "... [转录数据已省略] ..."
        st.json(debug_video)
    
    # 调试信息 - 显示片段结构
    with st.expander("片段数据结构", expanded=False):
        st.write(f"找到 {len(segments)} 个片段")
        if segments:
            # 显示第一个片段的结构
            first_segment = segments[0].copy()
            if "embeddings" in first_segment:
                first_segment["embeddings"] = "... [向量数据已省略] ..."
            st.json(first_segment)
    
    # 显示标题和基本信息
    st.title(title)
    st.markdown(f"**ID:** `{video_id}`")
    
    # 显示主要信息
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 基本信息")
        st.markdown(f"**品牌:** {brand}")
        st.markdown(f"**类型:** {video_type}")
        st.markdown(f"**时长:** {duration_str}")
        
        if tags:
            st.markdown("**标签:**")
            for tag in tags:
                st.markdown(f"- {tag}")
    
    with col2:
        st.markdown("### 内容概览")
        content_overview = video.get("content_overview", {})
        
        for key, value in content_overview.items():
            if value:
                st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
    
    with col3:
        st.markdown("### 总体分析")
        overall_analysis = video.get("overall_analysis", {})
        
        for key, value in overall_analysis.items():
            if value:
                st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
    
    # 显示片段时间线
    st.markdown("---")
    if segments:
        video_segment_timeline(segments)
    else:
        st.warning("没有找到视频片段数据")
    
    # 显示主题分析
    st.markdown("---")
    st.markdown("### 主题分析")
    
    theme_analysis = video.get("theme_analysis", {})
    
    if theme_analysis:
        col1, col2 = st.columns(2)
        
        with col1:
            for key, value in list(theme_analysis.items())[:len(theme_analysis)//2]:
                if value:
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
        
        with col2:
            for key, value in list(theme_analysis.items())[len(theme_analysis)//2:]:
                if value:
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
    else:
        st.info("无主题分析数据")
    
    # 显示强调分析
    st.markdown("---")
    st.markdown("### 重点内容分析")
    
    emphasis_analysis = video.get("emphasis_analysis", {})
    
    if emphasis_analysis:
        for key, value in emphasis_analysis.items():
            if value:
                st.markdown(f"**{key.replace('_', ' ').title()}:**")
                if isinstance(value, list):
                    for item in value:
                        st.markdown(f"- {item}")
                else:
                    st.markdown(f"{value}")
    else:
        st.info("无重点内容分析数据")
    
    # 显示关键事件
    st.markdown("---")
    st.markdown("### 关键事件")
    
    # 优先从视频中获取关键事件
    key_events = video.get("key_events", [])
    
    # 备选方案：如果视频中没有关键事件，尝试从片段中提取
    if not key_events and segments:
        # 从片段中收集关键事件
        for segment in segments:
            segment_events = segment.get("key_events", [])
            if segment_events:
                key_events.extend(segment_events)
    
    # 备选方案：从cinematography_analysis中提取
    if not key_events and "cinematography_analysis" in video:
        cinematography_events = video.get("cinematography_analysis", {}).get("key_events", [])
        if cinematography_events:
            key_events = cinematography_events
    
    # 备选方案：从key_events_analysis中提取
    if not key_events and "key_events_analysis" in video:
        key_events_analysis = video.get("key_events_analysis", [])
        if key_events_analysis:
            key_events = key_events_analysis
    
    # 备选方案：尝试其他可能的字段名
    if not key_events:
        possible_fields = [
            "events", "highlights", "key_moments", "significant_events", 
            "important_moments", "critical_points", "emphasis_analysis.key_events"
        ]
        
        for field in possible_fields:
            # 处理嵌套字段
            if "." in field:
                parts = field.split(".")
                data = video
                valid_path = True
                for part in parts:
                    if part in data:
                        data = data[part]
                    else:
                        valid_path = False
                        break
                
                if valid_path and isinstance(data, list):
                    key_events = data
                    break
            # 处理普通字段
            elif field in video and isinstance(video[field], list):
                key_events = video[field]
                break
    
    if key_events:
        # 按时间戳排序
        key_events.sort(key=lambda x: x.get("timestamp", 0))
        
        for event in key_events:
            timestamp = event.get("timestamp", 0)
            event_description = event.get("event_description", "")
            importance = event.get("importance_level", "")
            
            col1, col2, col3 = st.columns([1, 4, 1])
            
            with col1:
                st.markdown(f"**{timestamp:.1f}s**")
            
            with col2:
                st.markdown(event_description)
            
            with col3:
                if importance == "high":
                    st.markdown("⭐⭐⭐")
                elif importance == "medium":
                    st.markdown("⭐⭐")
                elif importance == "low":
                    st.markdown("⭐")
    else:
        st.info("无关键事件数据") 