#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Any
from services.whisper_transcription import WhisperTranscriptionService

class VideoProcessor:
    """视频处理器：提取音频、转录和切片视频"""
    
    def __init__(self, input_dir: str, output_dir: str, json_file: str):
        """
        初始化视频处理器
        
        参数:
        input_dir: 输入视频目录
        output_dir: 输出切片目录
        json_file: 输出JSON文件路径
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.json_file = Path(json_file)
        self.transcription_service = WhisperTranscriptionService()
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保JSON文件所在目录存在
        self.json_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化或加载JSON数据
        if self.json_file.exists():
            with open(self.json_file, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        else:
            self.json_data = []
    
    def get_video_files(self) -> List[Path]:
        """获取输入目录中的所有视频文件"""
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        video_files = []
        
        for file in self.input_dir.iterdir():
            if file.is_file() and file.suffix.lower() in video_extensions:
                video_files.append(file)
        
        return video_files
    
    def process_video(self, video_path: Path) -> None:
        """
        处理单个视频：转录并切片
        
        参数:
        video_path: 视频文件路径
        """
        print(f"\n正在处理视频: {video_path.name}")
        
        # 检查是否已经处理过该视频
        video_abs_path = str(video_path.absolute())
        if any(item.get('video_path') == video_abs_path for item in self.json_data):
            print(f"视频 {video_path.name} 已经处理过，跳过")
            return
        
        try:
            # 转录视频
            print("开始转录视频...")
            transcription = self.transcription_service.transcribe_video(str(video_path), language="zh")
            
            segments = transcription.get('segments', [])
            if not segments:
                print(f"视频 {video_path.name} 没有可转录的内容，跳过")
                return
            
            # 为每个片段创建切片并保存信息
            for i, segment in enumerate(segments):
                # 处理不同格式的segment对象
                if isinstance(segment, dict):
                    segment_id = segment.get('id', i)
                    start_time = segment.get('start', 0)
                    end_time = segment.get('end', 0)
                    text = segment.get('text', '')
                else:
                    # 如果segment不是字典，尝试访问其属性
                    try:
                        segment_id = getattr(segment, 'id', i)
                        start_time = getattr(segment, 'start', 0)
                        end_time = getattr(segment, 'end', 0)
                        text = getattr(segment, 'text', '')
                    except Exception as e:
                        print(f"无法处理片段 {i}: {str(e)}")
                        continue
                
                if not text or not isinstance(text, str) or not text.strip():
                    continue
                
                # 创建切片文件名
                output_filename = f"{video_path.stem}_segment_{segment_id}{video_path.suffix}"
                output_path = self.output_dir / output_filename
                
                # 使用ffmpeg切片视频
                self._cut_video(video_path, output_path, start_time, end_time)
                
                # 保存信息到JSON
                segment_info = {
                    'id': segment_id,
                    'text': text,
                    'start_time': start_time,
                    'end_time': end_time,
                    'video_path': str(video_path.absolute()),
                    'segment_path': str(output_path.absolute())
                }
                
                self.json_data.append(segment_info)
                
                # 每处理一个片段就保存一次JSON，防止中途出错丢失数据
                self._save_json()
                
                print(f"已处理片段 {segment_id}: {text[:30]}...")
            
            print(f"视频 {video_path.name} 处理完成")
            
        except Exception as e:
            print(f"处理视频 {video_path.name} 时出错: {str(e)}")
    
    def _cut_video(self, input_path: Path, output_path: Path, start_time: float, end_time: float) -> None:
        """
        使用ffmpeg切片视频
        
        参数:
        input_path: 输入视频路径
        output_path: 输出视频路径
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        """
        duration = end_time - start_time
        
        cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-ss', str(start_time),
            '-t', str(duration),
            '-c:v', 'copy',
            '-c:a', 'copy',
            str(output_path)
        ]
        
        try:
            print(f"切片视频: {start_time:.2f}s - {end_time:.2f}s -> {output_path.name}")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"切片视频时出错: {e}")
            print(f"错误输出: {e.stderr.decode() if e.stderr else 'None'}")
            raise
    
    def _save_json(self) -> None:
        """保存JSON数据到文件"""
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(self.json_data, f, ensure_ascii=False, indent=2)
    
    def process_all_videos(self) -> None:
        """处理所有视频文件"""
        video_files = self.get_video_files()
        
        if not video_files:
            print(f"在 {self.input_dir} 中没有找到视频文件")
            return
        
        print(f"找到 {len(video_files)} 个视频文件，开始处理...")
        
        for video_file in video_files:
            self.process_video(video_file)
        
        print(f"所有视频处理完成，结果已保存到 {self.json_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='处理视频：提取音频、转录和切片')
    parser.add_argument('--input-dir', type=str, default='/home/jinpeng/multi-agent/李想公关',
                        help='输入视频目录')
    parser.add_argument('--output-dir', type=str, default='/home/jinpeng/multi-agent/segments',
                        help='输出切片目录')
    parser.add_argument('--json-file', type=str, default='/home/jinpeng/multi-agent/segments/segments_info.json',
                        help='输出JSON文件路径')
    
    args = parser.parse_args()
    
    processor = VideoProcessor(args.input_dir, args.output_dir, args.json_file)
    processor.process_all_videos()


if __name__ == '__main__':
    main() 