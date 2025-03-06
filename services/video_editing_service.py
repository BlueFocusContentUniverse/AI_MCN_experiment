import os
import json
import subprocess
import tempfile
import shutil
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import datetime
from pydub import AudioSegment

class VideoEditingService:
    """视频剪辑服务，执行视频剪切和拼接"""
    
    def __init__(self, output_dir: str = "./output"):
        """
        初始化视频剪辑服务
        
        参数:
        output_dir: 输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 检查ffmpeg是否可用
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            raise RuntimeError("Error: FFmpeg is not installed or not in PATH. Please install FFmpeg.")
    
    def cut_video_segment(self, video_path: str, start_time: float, end_time: float, 
                          output_file: Optional[str] = None) -> str:
        """
        剪切视频片段
        
        参数:
        video_path: 视频文件路径
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        output_file: 输出文件路径，如果为None则自动生成
        
        返回:
        剪切后的视频文件路径
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # 如果没有指定输出文件，则自动生成
        if not output_file:
            timestamp = int(datetime.datetime.now().timestamp())
            output_file = os.path.join(self.output_dir, f"segment_{timestamp}.mp4")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 计算持续时间
        duration = end_time - start_time
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 临时输出文件
            temp_output = os.path.join(temp_dir, "temp_segment.mp4")
            
            # 构建ffmpeg命令
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-ss", str(start_time),  # 开始时间
                "-i", video_path,  # 输入文件
                "-t", str(duration),  # 持续时间
                "-c:v", "libx264",  # 视频编码
                "-preset", "medium",  # 编码预设
                "-crf", "23",  # 质量
                "-c:a", "aac",  # 音频编码
                "-b:a", "128k",  # 音频比特率
                "-avoid_negative_ts", "1",  # 避免负时间戳
                "-async", "1",  # 音频同步
                "-vsync", "1",  # 视频同步
                "-movflags", "+faststart",  # 优化MP4文件结构
                temp_output  # 临时输出文件
            ]
            
            print(f"执行FFmpeg命令: {' '.join(cmd)}")
            
            # 执行命令
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error cutting video segment: {process.stderr}")
            
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
                raise RuntimeError(f"Generated segment is invalid: {validate_result.stderr}")
            
            # 复制到最终输出位置
            shutil.copy2(temp_output, output_file)
            
            print(f"成功创建视频片段: {output_file}")
            
            return output_file
    
    def merge_audio_video(self, video_segments: List[Dict[str, Any]], 
                         audio_file: str, output_file: str) -> str:
        """
        合并音频和视频片段
        
        参数:
        video_segments: 视频片段列表，每个片段包含文件路径
        audio_file: 音频文件路径
        output_file: 输出文件路径
        
        返回:
        合并后的视频文件路径
        """
        if not video_segments:
            raise ValueError("No video segments provided")
        
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建片段列表文件
            segments_file = os.path.join(temp_dir, "segments.txt")
            with open(segments_file, "w") as f:
                for segment in video_segments:
                    if "file_path" not in segment:
                        raise ValueError(f"Missing file_path in segment: {segment}")
                    
                    video_path = segment["file_path"]
                    if not os.path.exists(video_path):
                        raise FileNotFoundError(f"Video segment not found: {video_path}")
                    
                    f.write(f"file '{video_path}'\n")
            
            # 临时合并的视频文件（无音频）
            temp_video = os.path.join(temp_dir, "temp_merged_video.mp4")
            
            # 合并视频片段
            concat_cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "concat",  # 使用concat格式
                "-safe", "0",  # 允许不安全的文件路径
                "-i", segments_file,  # 输入片段列表
                "-c", "copy",  # 复制编码（不重新编码）
                temp_video  # 临时输出文件
            ]
            
            print(f"执行FFmpeg命令 (合并视频): {' '.join(concat_cmd)}")
            
            # 执行命令
            process = subprocess.run(
                concat_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error merging video segments: {process.stderr}")
            
            # 合并视频和音频
            merge_cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i", temp_video,  # 输入视频
                "-i", audio_file,  # 输入音频
                "-map", "0:v:0",  # 使用第一个输入的视频流
                "-map", "1:a:0",  # 使用第二个输入的音频流
                "-c:v", "copy",  # 复制视频编码
                "-c:a", "aac",  # 音频编码
                "-b:a", "192k",  # 音频比特率
                "-shortest",  # 使用最短的输入长度
                output_file  # 最终输出文件
            ]
            
            print(f"执行FFmpeg命令 (合并音视频): {' '.join(merge_cmd)}")
            
            # 执行命令
            process = subprocess.run(
                merge_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error merging audio and video: {process.stderr}")
            
            print(f"成功创建最终视频: {output_file}")
            
            return output_file
    
    def execute_editing_plan(self, editing_plan: Dict[str, Any], output_file: str) -> str:
        """
        执行剪辑规划
        
        参数:
        editing_plan: 剪辑规划，包括每个分段使用的素材和时间点
        output_file: 输出文件路径
        
        返回:
        最终视频文件路径
        """
        if "segments" not in editing_plan:
            raise ValueError("Missing segments in editing plan")
        
        segments = editing_plan["segments"]
        if not segments:
            raise ValueError("No segments in editing plan")
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 处理每个分段
            processed_segments = []
            
            for i, segment in enumerate(segments):
                if "video_path" not in segment or "start_time" not in segment or "end_time" not in segment:
                    raise ValueError(f"Missing required fields in segment {i+1}: {segment}")
                
                # 剪切视频片段
                segment_output = os.path.join(temp_dir, f"segment_{i+1}.mp4")
                try:
                    segment_file = self.cut_video_segment(
                        segment["video_path"],
                        segment["start_time"],
                        segment["end_time"],
                        segment_output
                    )
                    
                    processed_segments.append({
                        "segment_id": i + 1,
                        "file_path": segment_file,
                        "original": segment
                    })
                    
                except Exception as e:
                    print(f"处理分段 {i+1} 时出错: {e}")
                    # 继续处理其他分段
            
            if not processed_segments:
                raise RuntimeError("No segments were successfully processed")
            
            # 如果有音频文件，合并音频和视频
            if "audio_file" in editing_plan and editing_plan["audio_file"]:
                audio_file = editing_plan["audio_file"]
                if os.path.exists(audio_file):
                    return self.merge_audio_video(processed_segments, audio_file, output_file)
            
            # 否则，只合并视频片段
            segments_file = os.path.join(temp_dir, "segments.txt")
            with open(segments_file, "w") as f:
                for segment in processed_segments:
                    f.write(f"file '{segment['file_path']}'\n")
            
            # 合并视频片段
            concat_cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "concat",  # 使用concat格式
                "-safe", "0",  # 允许不安全的文件路径
                "-i", segments_file,  # 输入片段列表
                "-c", "copy",  # 复制编码（不重新编码）
                output_file  # 最终输出文件
            ]
            
            print(f"执行FFmpeg命令 (合并视频): {' '.join(concat_cmd)}")
            
            # 执行命令
            process = subprocess.run(
                concat_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error merging video segments: {process.stderr}")
            
            print(f"成功创建最终视频: {output_file}")
            
            return output_file 