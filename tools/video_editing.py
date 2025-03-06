import os
import json
import tempfile
import subprocess
import shutil
from typing import Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool

class VideoEditingInput(BaseModel):
    """视频编辑工具的输入模式"""
    video_path: str = Field(..., description="视频文件的路径")
    segments: List[Dict[str, Any]] = Field(..., description="分段信息列表，每个分段包含start/start_time和end/end_time")
    output_dir: str = Field(..., description="输出目录")

class SplitVideoBySegmentsTool(BaseTool):
    name: str = "SplitVideoBySegments"
    description: str = "使用FFmpeg根据分段信息切割视频，支持start/end或start_time/end_time格式"
    args_schema: Type[BaseModel] = VideoEditingInput
    
    def _run(self, video_path: str, segments: List[Dict[str, Any]], output_dir: str) -> dict:
        """
        使用FFmpeg根据分段信息切割视频
        
        参数:
        video_path: 视频文件路径
        segments: 分段信息列表，支持start/end或start_time/end_time格式
        output_dir: 输出目录
        
        返回:
        切割后的视频文件信息
        """
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            # 检查ffmpeg是否可用
            try:
                subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                return "Error: FFmpeg is not installed or not in PATH. Please install FFmpeg."
            
            # 获取视频信息
            probe_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,r_frame_rate,duration",
                "-of", "json",
                video_path
            ]
            
            probe_result = subprocess.run(
                probe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if probe_result.returncode != 0:
                print(f"Warning: Could not get video info: {probe_result.stderr}")
                video_info = {}
            else:
                try:
                    video_info = json.loads(probe_result.stdout)
                    print(f"Video info: {json.dumps(video_info, indent=2)}")
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse video info: {probe_result.stdout}")
                    video_info = {}
            
            # 打印完整的分段数据用于调试
            print(f"Received segments: {json.dumps(segments, indent=2)}")
            
            # 切割视频
            output_files = []
            
            for i, segment in enumerate(segments):
                # 兼容两种时间格式：start/end 和 start_time/end_time
                start_time = segment.get("start", segment.get("start_time", 0))
                end_time = segment.get("end", segment.get("end_time", 0))
                title = segment.get("title", f"Segment {i+1}")
                
                print(f"Processing segment {i+1}: {json.dumps(segment, indent=2)}")
                print(f"Extracted times: start={start_time}, end={end_time}")
                
                # 安全处理文件名
                safe_title = "".join([c if c.isalnum() or c in [' ', '_', '-'] else '_' for c in title])
                safe_title = safe_title.strip().replace(' ', '_')
                
                # 输出文件路径
                output_file = os.path.join(output_dir, f"{i+1:02d}_{safe_title}.mp4")
                
                # 计算持续时间
                duration = float(end_time) - float(start_time)
                
                if duration <= 0:
                    print(f"Warning: Invalid segment duration for segment {i+1}: {duration} seconds. Skipping.")
                    continue
                
                print(f"Processing segment {i+1}: start={start_time}, end={end_time}, duration={duration}")
                
                # 创建临时目录用于处理
                temp_dir = tempfile.mkdtemp()
                temp_output = os.path.join(temp_dir, "temp_output.mp4")
                
                try:
                    # 使用FFmpeg切割视频 - 使用更可靠的参数
                    cmd = [
                        "ffmpeg",
                        "-y",  # 覆盖输出文件
                        "-ss", str(start_time),  # 开始时间
                        "-i", video_path,  # 输入文件
                        "-t", str(duration),  # 持续时间
                        "-c:v", "libx264",  # 视频编码
                        "-preset", "medium",  # 编码预设
                        "-crf", "23",  # 质量因子
                        "-c:a", "aac",  # 音频编码
                        "-b:a", "128k",  # 音频比特率
                        "-avoid_negative_ts", "1",  # 避免负时间戳
                        "-async", "1",  # 音频同步
                        "-vsync", "1",  # 视频同步
                        "-movflags", "+faststart",  # 优化MP4文件结构
                        temp_output  # 临时输出文件
                    ]
                    
                    print(f"FFmpeg command: {' '.join(cmd)}")
                    
                    # 执行命令
                    process = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    if process.returncode != 0:
                        print(f"Warning: Error cutting segment {i+1}:")
                        print(f"Command: {' '.join(cmd)}")
                        print(f"Error: {process.stderr}")
                        continue
                    
                    # 验证输出文件是否有效
                    validate_cmd = [
                        "ffprobe",
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=codec_type",
                        "-of", "json",
                        temp_output
                    ]
                    
                    validate_result = subprocess.run(
                        validate_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    if validate_result.returncode != 0:
                        print(f"Warning: Generated segment {i+1} is invalid: {validate_result.stderr}")
                        continue
                    
                    # 复制到最终输出位置
                    shutil.copy2(temp_output, output_file)
                    
                    output_files.append({
                        "segment_id": i + 1,
                        "title": title,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": duration,
                        "file_path": output_file
                    })
                    
                    print(f"Successfully created segment {i+1}: {output_file}")
                    
                finally:
                    # 清理临时目录
                    shutil.rmtree(temp_dir, ignore_errors=True)
            
            if not output_files:
                return "Error: No valid segments were created. Check the segment times and video format."
            
            return {
                "output_files": output_files,
                "total_segments": len(output_files),
                "output_directory": output_dir,
                "video_info": video_info
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f"Error splitting video: {str(e)}\n\nDetails:\n{error_details}" 