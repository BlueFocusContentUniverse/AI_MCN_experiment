#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import tempfile
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SegmentProcessor:
    """视频片段处理工具：提取、合并等操作"""
    
    def __init__(self, output_dir: str = None):
        """
        初始化视频片段处理工具
        
        参数:
        output_dir: 输出目录，如果不指定则使用临时目录
        """
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.temp_dir = tempfile.TemporaryDirectory()
            self.output_dir = Path(self.temp_dir.name)
        
        # 检查ffmpeg是否可用
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            raise RuntimeError("Error: FFmpeg is not installed or not in PATH. Please install FFmpeg.")
    
    def extract_segment(self, segment_info: Dict[str, Any], output_path: Optional[str] = None, keep_audio: bool = True) -> str:
        """
        提取视频片段
        
        参数:
        segment_info: 片段信息，包含segment_path或original_video_path、start_time、end_time等
        output_path: 输出文件路径，如果不指定则自动生成
        keep_audio: 是否保留原始音频
        
        返回:
        输出文件路径
        """
        # 确定输入文件路径
        input_path = segment_info.get("video_path")
        if not input_path or not os.path.exists(input_path):
            # 如果video_path不存在，尝试使用segment_path
            input_path = segment_info.get("segment_path")
            if not input_path or not os.path.exists(input_path):
                # 如果segment_path不存在，尝试使用original_video_path
                input_path = segment_info.get("original_video_path")
                if not input_path or not os.path.exists(input_path):
                    raise FileNotFoundError(f"视频文件不存在: {input_path}")
        
        # 确定输出文件路径
        if not output_path:
            segment_id = segment_info.get("segment_id", "unknown")
            # 保留原始文件名，只在前面添加segment_前缀，避免重命名导致路径混乱
            output_filename = f"segment_{segment_id}_{os.path.basename(input_path)}"
            output_path = str(self.output_dir / output_filename)
            
            # 记录原始路径到segment_info
            segment_info["original_path"] = input_path
            segment_info["extracted_path"] = output_path
        
        # 如果使用segment_path，并且是已经切好的片段，直接复制文件
        if input_path == segment_info.get("segment_path") and os.path.exists(input_path):
            logger.info(f"直接使用已切片的视频: {input_path}")
            # 复制文件
            with open(input_path, 'rb') as src, open(output_path, 'wb') as dst:
                dst.write(src.read())
            return output_path
        
        # 否则，使用ffmpeg提取片段
        start_time = float(segment_info.get("start_time", 0))
        end_time = float(segment_info.get("end_time", 0))
        duration = end_time - start_time
        
        if duration <= 0:
            raise ValueError(f"无效的时间范围: {start_time} - {end_time}")
        
        # 构建ffmpeg命令
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-ss', str(start_time),
            '-t', str(duration)
        ]
        
        # 根据keep_audio参数决定是否保留音频
        if keep_audio:
            # 保留音频，直接复制流
            cmd.extend([
                '-c:v', 'copy',
                '-c:a', 'copy'
            ])
        else:
            # 不保留音频，只复制视频流
            cmd.extend([
                '-c:v', 'copy',
                '-an'  # 禁用音频
            ])
        
        cmd.append(output_path)
        
        try:
            logger.info(f"提取视频片段: {start_time:.2f}s - {end_time:.2f}s -> {output_path} (保留音频: {keep_audio})")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"提取视频片段时出错: {e}")
            logger.error(f"错误输出: {e.stderr.decode() if e.stderr else 'None'}")
            raise
    
    def merge_segments(self, segment_paths: List[str], output_path: str, keep_audio: bool = True) -> str:
        """
        合并多个视频片段
        
        参数:
        segment_paths: 片段文件路径列表
        output_path: 输出文件路径
        keep_audio: 是否保留原始音频
        
        返回:
        输出文件路径
        """
        if not segment_paths:
            raise ValueError("没有提供视频片段")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # 验证所有视频片段是否存在并且可读
        valid_segment_paths = []
        for path in segment_paths:
            if not os.path.exists(path):
                logger.error(f"视频片段不存在: {path}")
                continue
                
            # 验证文件是否包含有效的视频流
            try:
                cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',  # 选择第一个视频流
                    '-show_entries', 'stream=codec_type',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and 'video' in result.stdout:
                    valid_segment_paths.append(path)
                    logger.info(f"有效的视频片段: {path}")
                else:
                    logger.error(f"无效的视频片段（未包含视频流）: {path}")
            except Exception as e:
                logger.error(f"检查视频片段时出错: {str(e)}")
                
        if not valid_segment_paths:
            raise ValueError("所有视频片段都无效")
            
        # 如果只有一个有效片段，直接复制而不是合并
        if len(valid_segment_paths) == 1:
            logger.info(f"只有一个有效片段，直接复制: {valid_segment_paths[0]} -> {output_path}")
            try:
                import shutil
                shutil.copy2(valid_segment_paths[0], output_path)
                return output_path
            except Exception as e:
                logger.error(f"复制单个片段时出错: {str(e)}")
                # 如果复制失败，尝试使用ffmpeg
                try:
                    subprocess.run([
                        'ffmpeg', '-y',
                        '-i', valid_segment_paths[0],
                        '-c', 'copy',
                        output_path
                    ], check=True)
                    return output_path
                except Exception as e2:
                    logger.error(f"使用ffmpeg复制单个片段时出错: {str(e2)}")
                    raise
        
        # 创建一个临时文件，包含所有要合并的文件
        concat_file = self.output_dir / "concat_list.txt"
        
        # 使用FFmpeg concat demuxer要求的格式
        with open(concat_file, 'w', encoding='utf-8') as f:
            for path in valid_segment_paths:
                # 仅使用简单的file路径格式
                f.write(f"file '{path}'\n")
        
        # 输出concat_list.txt内容以供调试
        logger.info(f"concat_list.txt 内容 ({len(valid_segment_paths)} 个有效片段):")
        with open(concat_file, 'r', encoding='utf-8') as f:
            for line in f:
                logger.info(f"  {line.strip()}")
        
        # 使用简单的ffmpeg命令合并视频
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            output_path
        ]
        
        try:
            logger.info(f"执行合并命令: {' '.join(ffmpeg_cmd)}")
            # 注意：切换到输出目录工作环境，确保路径能够正确解析
            process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
            logger.info("视频合并成功!")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"视频合并失败，错误码: {e.returncode}")
            logger.error(f"错误输出: {e.stderr}")
            
            # 如果合并失败，尝试单独复制第一个有效片段
            if valid_segment_paths:
                logger.info(f"合并失败，使用第一个有效片段: {valid_segment_paths[0]}")
                import shutil
                try:
                    shutil.copy2(valid_segment_paths[0], output_path)
                    return output_path
                except Exception as copy_e:
                    logger.error(f"复制单个片段时出错: {str(copy_e)}")
                    return valid_segment_paths[0]  # 直接返回原始路径
            else:
                raise ValueError("视频合并失败，且没有有效片段")
    
    def process_search_results(self, search_results: str, output_path: str, keep_audio: bool = True) -> str:
        """
        处理搜索结果，提取并合并视频片段
        
        参数:
        search_results: 搜索结果（JSON格式）
        output_path: 输出文件路径
        keep_audio: 是否保留原始音频
        
        返回:
        输出文件路径
        """
        # 解析搜索结果
        try:
            results = json.loads(search_results)
        except json.JSONDecodeError:
            raise ValueError("无效的搜索结果格式，应为JSON")
        
        if not results:
            raise ValueError("搜索结果为空")
        
        # 提取每个片段
        segment_paths = []
        for i, result in enumerate(results):
            try:
                segment_path = self.extract_segment(result, keep_audio=keep_audio)
                segment_paths.append(segment_path)
                logger.info(f"已提取片段 {i+1}/{len(results)}: {segment_path}")
            except Exception as e:
                logger.error(f"提取片段 {i+1}/{len(results)} 时出错: {str(e)}")
        
        if not segment_paths:
            raise ValueError("没有成功提取任何片段")
        
        # 合并所有片段
        return self.merge_segments(segment_paths, output_path, keep_audio=keep_audio)

# 如果直接运行此文件，则执行测试
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='处理视频片段')
    parser.add_argument('--input', type=str, required=True,
                        help='输入JSON文件路径，包含搜索结果')
    parser.add_argument('--output', type=str, required=True,
                        help='输出视频文件路径')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='输出目录，用于存放临时文件')
    parser.add_argument('--keep-audio', action='store_true', default=True,
                        help='是否保留原始音频')
    
    args = parser.parse_args()
    
    # 读取输入JSON文件
    with open(args.input, 'r', encoding='utf-8') as f:
        search_results = f.read()
    
    # 处理视频片段
    processor = SegmentProcessor(output_dir=args.output_dir)
    output_path = processor.process_search_results(search_results, args.output, keep_audio=args.keep_audio)
    
    print(f"处理完成，输出文件: {output_path}") 