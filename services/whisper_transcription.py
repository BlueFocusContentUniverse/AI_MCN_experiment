import os
import json
import tempfile
import subprocess
from typing import Dict, Any, Optional
import httpx
from openai import OpenAI

class WhisperTranscriptionService:
    """使用Whisper API进行视频语音转录的服务"""
    
    def __init__(self):
        """初始化Whisper转录服务"""
        # 设置 OpenAI API
        self.api_key = os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self.base_url = os.environ.get('OPENAI_BASE_URL')
        if not self.base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        # 设置代理（如果需要）
        proxy_url = os.environ.get('HTTP_PROXY')
        self.http_client = None
        if proxy_url:
            self.http_client = httpx.Client(proxies={"http://": proxy_url, "https://": proxy_url})
        
        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=self.api_key, 
            base_url=self.base_url,
            http_client=self.http_client
        )
        
        # 检查ffmpeg是否可用
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            raise RuntimeError("Error: FFmpeg is not installed or not in PATH. Please install FFmpeg.")
    
    def extract_audio_from_video(self, video_path: str) -> Optional[str]:
        """
        从视频中提取音频
        
        参数:
        video_path: 视频文件路径
        
        返回:
        临时音频文件路径，如果没有音频则返回None
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        audio_path = video_path.rsplit(".", 1)[0] + ".wav"
        
        # 首先获取视频时长
        duration_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video_path}"'
        duration_process = subprocess.Popen(
            duration_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        duration_output, _ = duration_process.communicate()
        total_duration = float(duration_output.decode().strip())
        
        # 使用 progress 参数显示处理进度
        cmd = (
            f'ffmpeg -y -hwaccel auto -i "{video_path}" '
            f'-vn -acodec pcm_s16le -ar 16000 -ac 1 '
            f'-threads 0 -progress pipe:1 "{audio_path}"'
        )
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            line = line.decode().strip()
            if line.startswith('out_time_ms='):
                current_time = int(line.split('=')[1]) / 1000000  # 转换为秒
                progress = (current_time / total_duration) * 100
                print(f'\r处理进度: {progress:.1f}%', end='')
        
        process.wait()
        print('\n音频提取完成')
        
        return audio_path
    
    def transcribe_video(self, video_path: str, language: str = "zh") -> Dict[str, Any]:
        """
        转录视频中的语音
        
        参数:
        video_path: 视频文件路径
        language: 视频主要语言，例如：zh, en, ja
        
        返回:
        转录结果，包含文本和时间戳
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        try:
            # 尝试直接使用视频文件
            print("尝试直接转录视频...")
            try:
                with open(video_path, "rb") as video_file:
                    response = self.client.audio.transcriptions.create(
                        model="whisper",
                        file=video_file,
                        language=language,
                        response_format="verbose_json"
                    )
                    
                    # 提取结果
                    transcription = {
                        "text": response.text,
                        "segments": []
                    }
                    
                    # 提取分段信息
                    for segment in response.segments:
                        transcription["segments"].append({
                            "id": segment.id,
                            "start": segment.start,
                            "end": segment.end,
                            "text": segment.text
                        })
                    
                    print(f"视频直接转录完成，共 {len(transcription['segments'])} 个分段")
                    return transcription
                    
            except Exception as direct_error:
                print(f"直接转录视频失败: {str(direct_error)}，尝试提取音频...")
                
                # 如果直接转录失败，尝试提取音频
                audio_path = self.extract_audio_from_video(video_path)
                
                # 如果没有音频，返回空结果
                if audio_path is None:
                    print("视频没有音频，返回空转录结果")
                    return {
                        "text": "",
                        "segments": [],
                        "no_audio": True
                    }
                
                # 打开音频文件
                with open(audio_path, "rb") as audio_file:
                    # 转录视频
                    print("开始转录提取的音频...")
                    response = self.client.audio.transcriptions.create(
                        model="whisper",
                        file=audio_file,
                        language=language,
                        response_format="verbose_json"
                    )
                
                # 清理临时音频文件
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
                
                # 提取结果
                transcription = {
                    "text": response.text,
                    "segments": []
                }
                
                # 提取分段信息
                for segment in response.segments:
                    transcription["segments"].append({
                        "id": segment.id,
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text
                    })
                
                print(f"音频转录完成，共 {len(transcription['segments'])} 个分段")
                return transcription
                
        except Exception as e:
            raise Exception(f"Error transcribing video: {str(e)}") 