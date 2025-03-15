import os
import json
import subprocess
import tempfile
import shutil
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import datetime
from pydub import AudioSegment
import random

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
            
            # 复制到最终输出位置
            shutil.copy2(temp_output, output_file)
            
            print(f"成功创建视频片段: {output_file}")
            
            return output_file
    
    def get_video_info(self, video_path: str) -> Tuple[int, int, float]:
        """
        获取视频信息
        
        参数:
        video_path: 视频文件路径
        
        返回:
        (宽度, 高度, 时长)的元组
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # 使用ffprobe获取视频信息
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "json",
            video_path
        ]
        
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"Error getting video info: {process.stderr}")
        
        # 解析JSON输出
        info = json.loads(process.stdout)
        
        # 提取宽度、高度和时长
        width = int(info["streams"][0]["width"])
        height = int(info["streams"][0]["height"])
        
        # 有些视频可能没有duration字段，需要使用另一种方式获取
        if "duration" in info["streams"][0]:
            duration = float(info["streams"][0]["duration"])
        else:
            # 使用format获取duration
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video_path
            ]
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error getting video duration: {process.stderr}")
            
            format_info = json.loads(process.stdout)
            duration = float(format_info["format"]["duration"])
        
        print(f"原始视频信息 - 尺寸: {width}x{height}, 时长: {duration}秒")
        
        return width, height, duration
    
    def normalize_video(self, video_path: str, output_file: str, 
                        target_width: int = 1080, target_height: int = 1920, 
                        fps: int = 30) -> str:
        """
        标准化视频尺寸和帧率
        
        参数:
        video_path: 视频文件路径
        output_file: 输出文件路径
        target_width: 目标宽度
        target_height: 目标高度
        fps: 目标帧率
        
        返回:
        标准化后的视频文件路径
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 获取视频信息
        width, height, duration = self.get_video_info(video_path)
        print(f"原始视频信息 - 尺寸: {width}x{height}, 时长: {duration}秒")
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 临时输出文件
            temp_output = os.path.join(temp_dir, "temp_normalized.mp4")
            
            # 确定视频方向和适当的缩放策略
            is_landscape = width > height
            
            # 构建适当的滤镜命令
            if is_landscape:
                # 横屏视频 -> 竖屏输出
                # 先缩放到合适的高度，保持宽高比，然后居中裁剪到目标宽度
                filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
            else:
                # 竖屏视频 -> 竖屏输出
                # 正常缩放，保持宽高比
                filter_complex = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black"
            
            # 构建ffmpeg命令
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i", video_path,  # 输入文件
                "-r", str(fps),  # 帧率
                "-c:v", "libx264",  # 视频编码
                "-preset", "medium",  # 编码预设
                "-crf", "23",  # 质量
                "-c:a", "aac",  # 音频编码
                "-b:a", "128k",  # 音频比特率
                "-vf", filter_complex,  # 视频滤镜
                "-movflags", "+faststart",  # 优化MP4文件结构
                temp_output  # 临时输出文件
            ]
            
            print(f"执行FFmpeg命令 (标准化视频): {' '.join(cmd)}")
            
            # 执行命令
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                # 如果标准化失败，尝试使用更简单的方法
                print(f"标准化视频失败，尝试使用更简单的方法: {process.stderr}")
                
                # 简单的缩放方法，不保持宽高比
                simple_cmd = [
                    "ffmpeg",
                    "-y",  # 覆盖输出文件
                    "-i", video_path,  # 输入文件
                    "-r", str(fps),  # 帧率
                    "-c:v", "libx264",  # 视频编码
                    "-preset", "medium",  # 编码预设
                    "-crf", "23",  # 质量
                    "-c:a", "aac",  # 音频编码
                    "-b:a", "128k",  # 音频比特率
                    "-vf", f"scale={target_width}:{target_height}",  # 简单缩放
                    "-movflags", "+faststart",  # 优化MP4文件结构
                    temp_output  # 临时输出文件
                ]
                
                print(f"尝试简单缩放: {' '.join(simple_cmd)}")
                
                process = subprocess.run(
                    simple_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if process.returncode != 0:
                    # 如果仍然失败，直接复制原始视频
                    print(f"简单缩放也失败，直接使用原始视频: {process.stderr}")
                    shutil.copy2(video_path, output_file)
                    return output_file
            
            # 复制到最终输出位置
            shutil.copy2(temp_output, output_file)
            
            print(f"成功创建标准化视频: {output_file}")
            
            return output_file
    
    def concat_videos(self, video_files: List[str], output_file: str) -> str:
        """
        连接多个视频文件
        
        参数:
        video_files: 视频文件路径列表
        output_file: 输出文件路径
        
        返回:
        连接后的视频文件路径
        """
        if not video_files:
            raise ValueError("No video files to concatenate")
        
        if len(video_files) == 1:
            # 只有一个视频，直接复制
            shutil.copy2(video_files[0], output_file)
            return output_file
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建片段列表文件
            segments_file = os.path.join(temp_dir, "segments.txt")
            with open(segments_file, "w") as f:
                for video_path in video_files:
                    if not os.path.exists(video_path):
                        raise FileNotFoundError(f"Video file not found: {video_path}")
                    f.write(f"file '{video_path}'\n")
            
            # 构建ffmpeg命令
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "concat",  # 使用concat格式
                "-safe", "0",  # 允许不安全的文件路径
                "-i", segments_file,  # 输入片段列表
                "-c", "copy",  # 复制编码（不重新编码）
                output_file  # 输出文件
            ]
            
            print(f"执行FFmpeg命令 (连接视频): {' '.join(cmd)}")
            
            # 执行命令
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error concatenating videos: {process.stderr}")
            
            print(f"成功连接视频: {output_file}")
            
            return output_file
    
    def execute_editing_plan(self, editing_plan: Dict[str, Any], output_file: str) -> str:
        """
        执行剪辑规划，不应用转场效果
        
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
        
        # 获取音频分段信息
        audio_segments = editing_plan.get("audio_segments", [])
        audio_files = {}
        for audio_segment in audio_segments:
            if "segment_id" in audio_segment and "audio_file" in audio_segment:
                audio_files[str(audio_segment["segment_id"])] = audio_segment["audio_file"]
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 按segment_id分组
            segment_groups = {}
            for segment in segments:
                if "segment_id" not in segment:
                    print(f"警告: 分段缺少segment_id字段: {segment}")
                    continue
                
                segment_id = str(segment["segment_id"])
                if segment_id not in segment_groups:
                    segment_groups[segment_id] = []
                segment_groups[segment_id].append(segment)
            
            print(f"按segment_id分组后共有 {len(segment_groups)} 个分段组")
            
            # 处理每个分段组
            segments_with_audio = []
            
            for segment_id, segment_parts in segment_groups.items():
                print(f"处理分段组 {segment_id}，包含 {len(segment_parts)} 个部分")
                
                # 为每个分段创建一个子目录
                segment_dir = os.path.join(temp_dir, f"segment_{segment_id}")
                os.makedirs(segment_dir, exist_ok=True)
                
                # 处理分段内的视频片段
                processed_parts = []
                for j, part in enumerate(segment_parts):
                    if "video_path" not in part or "start_time" not in part or "end_time" not in part:
                        print(f"警告: 分段 {segment_id} 的第 {j+1} 个部分缺少必要字段: {part}")
                        continue
                    
                    # 剪切视频片段
                    part_output = os.path.join(segment_dir, f"part_{j+1}.mp4")
                    try:
                        part_file = self.cut_video_segment(
                            part["video_path"],
                            part["start_time"],
                            part["end_time"],
                            part_output
                        )
                        
                        # 标准化视频片段为竖屏1080p
                        normalized_part_output = os.path.join(segment_dir, f"normalized_part_{j+1}.mp4")
                        normalized_part_file = self.normalize_video(
                            part_file,
                            normalized_part_output,
                            target_width=1080,
                            target_height=1920,
                            fps=30
                        )
                        
                        processed_parts.append({
                            "part_id": j + 1,
                            "file_path": normalized_part_file,
                            "original": part
                        })
                        
                    except Exception as e:
                        print(f"处理分段 {segment_id} 的第 {j+1} 个部分时出错: {e}")
                        # 继续处理其他部分
                
                if not processed_parts:
                    print(f"警告: 分段 {segment_id} 没有成功处理的视频部分")
                    continue
                
                # 简单连接分段内的所有部分，不应用转场效果
                segment_concat = os.path.join(segment_dir, f"segment_{segment_id}_concat.mp4")
                parts_file = os.path.join(segment_dir, "parts.txt")
                with open(parts_file, "w") as f:
                    for part in processed_parts:
                        f.write(f"file '{part['file_path']}'\n")
                
                # 合并分段的所有部分
                concat_cmd = [
                    "ffmpeg",
                    "-y",  # 覆盖输出文件
                    "-f", "concat",  # 使用concat格式
                    "-safe", "0",  # 允许不安全的文件路径
                    "-i", parts_file,  # 输入片段列表
                    "-c", "copy",  # 复制编码（不重新编码）
                    segment_concat  # 输出文件
                ]
                
                print(f"执行FFmpeg命令 (简单连接分段 {segment_id} 的部分): {' '.join(concat_cmd)}")
                
                # 执行命令
                process = subprocess.run(
                    concat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if process.returncode != 0:
                    print(f"警告: 简单连接分段 {segment_id} 的部分时出错: {process.stderr}")
                    # 如果连接失败，使用第一个部分
                    segment_concat = processed_parts[0]["file_path"]
                
                # 为分段添加音频
                segment_with_audio = os.path.join(temp_dir, f"segment_{segment_id}_with_audio.mp4")
                
                # 检查是否有对应的音频文件
                audio_file = audio_files.get(segment_id)
                if audio_file and os.path.exists(audio_file):
                    print(f"为分段 {segment_id} 添加音频: {audio_file}")
                    
                    # 添加音频到视频
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", segment_concat,  # 视频输入
                        "-i", audio_file,  # 音频输入
                        "-map", "0:v:0",  # 使用第一个输入的视频流
                        "-map", "1:a:0",  # 使用第二个输入的音频流
                        "-c:v", "copy",  # 复制视频编码（不重新编码）
                        "-c:a", "aac",  # 音频编码
                        "-b:a", "192k",  # 音频比特率
                        "-shortest",  # 使用最短的输入长度
                        segment_with_audio
                    ]
                    
                    print(f"执行FFmpeg命令 (为分段 {segment_id} 添加音频): {' '.join(cmd)}")
                    
                    subprocess.run(cmd, check=True)
                    
                    # 添加到带音频的分段列表
                    segments_with_audio.append({
                        "segment_id": segment_id,
                        "file_path": segment_with_audio
                    })
                else:
                    print(f"警告: 分段 {segment_id} 没有对应的音频文件或文件不存在")
                    # 使用原始视频（没有音频）
                    segments_with_audio.append({
                        "segment_id": segment_id,
                        "file_path": segment_concat
                    })
            
            # 简单连接所有分段，不应用转场效果
            final_segments_file = os.path.join(temp_dir, "final_segments.txt")
            with open(final_segments_file, "w") as f:
                for segment in segments_with_audio:
                    f.write(f"file '{segment['file_path']}'\n")
            
            # 合并所有最终分段
            concat_cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "concat",  # 使用concat格式
                "-safe", "0",  # 允许不安全的文件路径
                "-i", final_segments_file,  # 输入片段列表
                "-c", "copy",  # 复制编码（不重新编码）
                output_file  # 输出文件
            ]
            
            print(f"执行FFmpeg命令 (合并所有最终分段): {' '.join(concat_cmd)}")
            
            # 执行命令
            process = subprocess.run(
                concat_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Error merging final video segments: {process.stderr}")
            
            return output_file 