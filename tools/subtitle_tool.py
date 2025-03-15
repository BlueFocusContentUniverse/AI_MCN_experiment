import os
import json
import subprocess
import platform
import traceback
from typing import List, Dict, Any
import httpx
import ormsgpack


class FishSpeechRecognizer:
    """Fish Audio 语音识别服务"""
    
    def __init__(self):
        """初始化 Fish Audio ASR 服务"""
        self.api_key = os.environ.get('FISH_AUDIO_API_KEY')
        
        if not self.api_key:
            raise ValueError("请设置 Fish Audio api key")
        
        self.api_url = "https://api.fish.audio/v1/asr"
    
    def transcribe_audio(self, audio_file_path: str):
        """同步调用 Fish Audio ASR API 进行音频转写"""
        try:
            # 读取音频文件
            with open(audio_file_path, "rb") as audio_file:
                audio_data = audio_file.read()
            
            # 准备请求数据
            request_data = {
                "audio": audio_data,
                "language": "zh",  # 指定语言为中文
                "ignore_timestamps": False  # 获取精确时间戳
            }
            
            # 发送请求
            with httpx.Client() as client:
                response = client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/msgpack",
                    },
                    content=ormsgpack.packb(request_data),
                    timeout=None  # 对于长音频，可能需要较长时间
                )
                
                # 检查响应状态
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                
                print("Fish Audio ASR 响应:", result)
                return result
                
        except Exception as e:
            raise RuntimeError(f"Fish Audio ASR API 调用失败: {str(e)}")
    
    def transcribe_video_audio(self, audio_path: str, output_dir: str):
        """处理音频文件并保存结果"""
        try:
            # 直接转写音频
            transcription = self.transcribe_audio(audio_path)
            print("Transcription type:", type(transcription))  # 添加调试信息
            
            # 初始化结果列表
            simplified_segments = []
            
            # 处理音频开始的静音部分
            if 'segments' in transcription and len(transcription['segments']) > 0:
                first_segment = transcription['segments'][0]
                if first_segment['start'] > 0:
                    simplified_segments.append({
                        "start": 0,
                        "end": first_segment['start'],
                        "text": ""
                    })
            
            # 定义中文标点符号列表
            punctuation_marks = ['。', '！', '？', '；', '，',  '!', '?', ';', ',']
            
            # 处理所有segments和它们之间的间隔
            for i, segment in enumerate(transcription['segments']):
                text = segment['text']
                start_time = segment['start']
                end_time = segment['end']
                duration = end_time - start_time
                
                # 如果文本为空，直接添加原始segment
                if not text.strip():
                    simplified_segments.append({
                        "start": start_time,
                        "end": end_time,
                        "text": text
                    })
                    continue
                
                # 计算每个字符的平均时长
                chars_count = len(text)
                time_per_char = duration / chars_count if chars_count > 0 else 0
                
                # 根据标点符号拆分文本
                sub_segments = []
                last_cut = 0
                
                # 查找所有标点符号位置
                for j, char in enumerate(text):
                    if char in punctuation_marks or j == len(text) - 1:
                        # 如果是最后一个字符且不是标点，需要包含这个字符
                        end_idx = j + 1
                        sub_text = text[last_cut:end_idx]
                        
                        # 计算这部分文本的时长和时间戳
                        sub_duration = len(sub_text) * time_per_char
                        sub_start = start_time + last_cut * time_per_char
                        sub_end = sub_start + sub_duration
                        
                        # 添加到子segments列表
                        sub_segments.append({
                            "start": sub_start,
                            "end": sub_end,
                            "text": sub_text
                        })
                        
                        # 更新下一段的起始位置
                        last_cut = end_idx
                
                # 如果没有找到任何标点符号，使用原始segment
                if not sub_segments:
                    simplified_segments.append({
                        "start": start_time,
                        "end": end_time,
                        "text": text
                    })
                else:
                    # 按字数限制进行二次分割
                    final_segments = []
                    max_chars = 15  # 最大字符数限制
                    
                    for sub_seg in sub_segments:
                        sub_text = sub_seg["text"]
                        sub_start = sub_seg["start"]
                        sub_end = sub_seg["end"]
                        
                        # 如果文本长度超过限制，进行分割
                        if len(sub_text) > max_chars:
                            # 计算分割点（尽量在中间位置）
                            mid_point = len(sub_text) // 2
                            
                            # 分割文本
                            first_part = sub_text[:mid_point]
                            second_part = sub_text[mid_point:]
                            
                            # 计算每部分的时间戳
                            first_duration = len(first_part) * time_per_char
                            first_end = sub_start + first_duration
                            
                            # 添加两部分到最终列表
                            final_segments.append({
                                "start": sub_start,
                                "end": first_end,
                                "text": first_part
                            })
                            final_segments.append({
                                "start": first_end,
                                "end": sub_end,
                                "text": second_part
                            })
                        else:
                            # 文本长度在限制内，直接添加
                            final_segments.append(sub_seg)
                    
                    # 添加所有处理后的子segments
                    simplified_segments.extend(final_segments)
                
                # 检查与下一个segment之间是否有间隔
                if i < len(transcription['segments']) - 1:
                    next_segment = transcription['segments'][i + 1]
                    if next_segment['start'] > segment['end']:
                        simplified_segments.append({
                            "start": segment['end'],
                            "end": next_segment['start'],
                            "text": ""
                        })
            
            # 处理最后一个segment之后的静音部分
            if transcription['segments']:
                last_segment = transcription['segments'][-1]
                if last_segment['end'] < transcription['duration']:
                    simplified_segments.append({
                        "start": last_segment['end'],
                        "end": transcription['duration'],
                        "text": ""
                    })
            
            # 保存转写结果
            audio_name = os.path.splitext(os.path.basename(audio_path))[0]
            output_path = os.path.join(output_dir, f"{audio_name}_fish_analysis_results.json")
            
            # 同步写入 JSON 文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(simplified_segments, f, ensure_ascii=False, indent=2)
            
            return simplified_segments
        except Exception as e:
            raise RuntimeError(f"处理音频失败: {str(e)}")


class SubtitleTool:
    """视频字幕处理工具"""
    
    def __init__(self, font_dir: str = None):
        """
        初始化字幕处理工具
        
        参数:
        font_dir: 字体目录，默认为项目根目录下的fonts文件夹
        """
        if font_dir is None:
            # 默认字体目录
            self.font_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
        else:
            self.font_dir = font_dir
            
        os.makedirs(self.font_dir, exist_ok=True)
        
        # 初始化语音识别器
        self.recognizer = FishSpeechRecognizer()
    
    def extract_audio_from_video(self, video_path: str, audio_path: str) -> None:
        """
        从视频中提取音频
        
        参数:
        video_path: 视频文件路径
        audio_path: 输出音频文件路径
        """
        try:
            print(f"从视频中提取音频: {video_path} -> {audio_path}")
            
            # 使用ffmpeg提取音频
            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                audio_path
            ]
            
            subprocess.run(cmd, check=True)
            print("音频提取完成")
            
        except Exception as e:
            raise RuntimeError(f"从视频提取音频失败: {str(e)}")
    
    def generate_srt_file(self, segments: List[Dict[str, Any]], output_file: str) -> None:
        """
        生成SRT字幕文件
        
        参数:
        segments: 音频分段信息
        output_file: 输出SRT文件路径
        """
        try:
            print(f"生成SRT字幕文件: {output_file}")
            
            # 将segments转换为字幕格式
            subtitle_entries = []
            subtitle_index = 1
            
            for segment in segments:
                if not segment.get('text') or segment['text'].isspace():
                    continue
                    
                # 生成字幕条目
                entry = {
                    'index': subtitle_index,
                    'start': self._format_time(float(segment['start'])),
                    'end': self._format_time(float(segment['end'])),
                    'text': segment['text']
                }
                subtitle_entries.append(entry)
                subtitle_index += 1
            
            # 写入SRT文件
            with open(output_file, 'w', encoding='utf-8') as f:
                for entry in subtitle_entries:
                    f.write(f"{entry['index']}\n")
                    f.write(f"{entry['start']} --> {entry['end']}\n")
                    f.write(f"{entry['text']}\n\n")
                    
            print(f"SRT文件生成完成，共{len(subtitle_entries)}条字幕")
            
        except Exception as e:
            raise RuntimeError(f"生成SRT文件失败: {str(e)}")
    
    def _format_time(self, seconds: float) -> str:
        """
        将秒数格式化为SRT时间格式 (HH:MM:SS,mmm)
        
        参数:
        seconds: 秒数
        
        返回:
        格式化的时间字符串
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
    
    def add_subtitles(self, video_file: str, subtitle_file: str, output_file: str, 
                      font_name: str = '文悦新青年体 (须授权)', 
                      font_size: int = 14,
                      primary_colour: str = '#00F7FB',
                      outline_colour: str = '#000000',
                      margin_v: int = 120,
                      outline: int = 1,
                      spacing: int = 1) -> str:
        """
        为视频添加字幕
        
        参数:
        video_file: 视频文件路径
        subtitle_file: SRT字幕文件路径
        output_file: 输出视频文件路径
        font_name: 字体名称
        font_size: 字体大小
        primary_colour: 主要颜色（十六进制）
        outline_colour: 轮廓颜色（十六进制）
        margin_v: 垂直边距
        outline: 轮廓宽度
        spacing: 字符间距
        
        返回:
        添加字幕后的视频文件路径
        """
        try:
            print(f"为视频添加字幕: {video_file}")
            
            # 处理Windows路径
            subtitle_path = subtitle_file
            if platform.system() == "Windows":
                subtitle_path = subtitle_path.replace("\\", "\\\\\\\\")
                subtitle_path = subtitle_path.replace(":", "\\\\:")
            
            # 转换颜色格式
            primary_colour_ffmpeg = f"&H{primary_colour[1:]}&"
            outline_colour_ffmpeg = f"&H{outline_colour[1:]}&"
            
            # 构建字幕滤镜
            vf_text = (
                f"subtitles={subtitle_path}:fontsdir={self.font_dir}:"
                f"force_style='Fontname={font_name},Fontsize={font_size},"
                f"PrimaryColour={primary_colour_ffmpeg},OutlineColour={outline_colour_ffmpeg},"
                f"MarginV={margin_v},Outline={outline},Spacing={spacing}'"
            )
            
            # 构建FFmpeg命令
            cmd = [
                'ffmpeg',
                '-i', video_file,
                '-vf', vf_text,
                '-c:a', 'copy',
                '-y',
                output_file
            ]
            
            print("执行命令: " + " ".join(cmd))
            subprocess.run(cmd, check=True)
            print(f"字幕添加完成: {output_file}")
            
            return output_file
            
        except Exception as e:
            print(f"添加字幕失败: {str(e)}")
            traceback.print_exc()
            return video_file  # 如果失败，返回原始视频文件路径
    
    def process_video_with_subtitles(self, video_file: str, output_dir: str, output_filename: str = None) -> str:
        """
        处理视频并添加字幕（完整流程）
        
        参数:
        video_file: 视频文件路径
        output_dir: 输出目录
        output_filename: 输出文件名（不含扩展名），默认使用原文件名加上"_subtitled"
        
        返回:
        添加字幕后的视频文件路径
        """
        try:
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 设置输出文件名
            if output_filename is None:
                base_name = os.path.splitext(os.path.basename(video_file))[0]
                output_filename = f"{base_name}_subtitled"
            
            # 设置临时文件和最终输出文件路径
            audio_file = os.path.join(output_dir, f"{output_filename}_audio.wav")
            srt_file = os.path.join(output_dir, f"{output_filename}.srt")
            final_video = os.path.join(output_dir, f"{output_filename}.mp4")
            
            # 1. 从视频中提取音频
            print("步骤1: 从视频中提取音频...")
            self.extract_audio_from_video(video_file, audio_file)
            
            # 2. 使用Fish Speech Recognizer进行音频转写
            print("步骤2: 转写音频...")
            segments = self.recognizer.transcribe_video_audio(audio_file, output_dir)
            
            # 3. 生成SRT文件
            print("步骤3: 生成SRT字幕文件...")
            self.generate_srt_file(segments, srt_file)
            
            # 4. 添加字幕到视频
            print("步骤4: 为视频添加字幕...")
            result = self.add_subtitles(video_file, srt_file, final_video)
            
            print(f"视频字幕处理完成: {result}")
            return result
            
        except Exception as e:
            print(f"处理视频字幕时出错: {str(e)}")
            traceback.print_exc()
            return video_file  # 如果失败，返回原始视频文件路径 