import os
import io
import base64
from pathlib import Path
import datetime
import time
import uuid
import json
from typing import Dict, Any, List, Optional, Tuple

import httpx
import ormsgpack
from pydantic import BaseModel
from typing import Literal
from pydub import AudioSegment

class ServeReferenceAudio(BaseModel):
    audio: bytes
    text: str

class ServeTTSRequest(BaseModel):
    text: str
    chunk_length: int = 200
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 128
    references: list[ServeReferenceAudio] = []
    reference_id: Optional[str] = None
    normalize: bool = True
    latency: Literal["normal", "balanced"] = "normal"

class AudioCutConfig(BaseModel):
    threshold: int = -50
    min_silence_len: int = 500
    keep_silence: int = 0

class FishAudioService:
    def __init__(self, task_params=None, audio_output_dir=None):
        """初始化 Fish Audio 服务
        :param task_params: 任务参数字典，包含所有配置参数
        :param audio_output_dir: 音频输出目录
        """
        if task_params is None:
            task_params = {}

        # 从环境变量获取 API Key
        self.api_key = os.environ.get('FISH_AUDIO_API_KEY')
        if not self.api_key:
            raise ValueError("FISH_AUDIO_API_KEY environment variable is not set")
        
        # 确保输出目录存在
        self.audio_output_dir = audio_output_dir or "./audio_output"
        os.makedirs(self.audio_output_dir, exist_ok=True)
        
        self.api_url = "https://api.fish.audio/v1/tts"

        # 音频生成相关参数
        self.reference_id = task_params.get('reference_id', 'f829fe5e290e4dc69fc08aa00b6ca2a0')
        self.mp3_bitrate = task_params.get('mp3_bitrate', 128)
        self.chunk_length = task_params.get('chunk_length', 200)
        self.latency_mode = task_params.get('latency_mode', 'normal')
        
        # 音频剪切相关参数
        self.enable_audio_cut = task_params.get('enable_audio_cut', True)
        if self.enable_audio_cut:
            self.audio_cut_config = AudioCutConfig(
                threshold=task_params.get('audio_cut_threshold', -50),
                min_silence_len=task_params.get('audio_cut_min_silence_len', 500),
                keep_silence=task_params.get('audio_cut_keep_silence', 0)
            )
            from tools.tts_audio_editor import TTSAudioCutter
            self.audio_cutter = TTSAudioCutter(self.audio_cut_config)

        self.audio_gain_db = task_params.get('audio_gain_db', 5)

    def generate_audio(self, content: str, output_file: Optional[str] = None) -> Tuple[str, float]:
        """
        生成语音并保存到文件
        
        参数:
        content: 要转换的文本内容
        output_file: 输出音频文件路径，如果为None则自动生成
        
        返回:
        (生成的音频文件路径, 音频时长(秒))
        """
        if not content or not content.strip():
            raise ValueError("Error: Empty content")

        # 如果没有指定输出文件，则自动生成
        if not output_file:
            timestamp = int(datetime.datetime.now().timestamp())
            output_file = os.path.join(self.audio_output_dir, f"audio_{timestamp}.wav")

        request = ServeTTSRequest(
            text=content,
            format="mp3",  # 请求MP3格式
            reference_id=self.reference_id,
            mp3_bitrate=self.mp3_bitrate,
            chunk_length=self.chunk_length,
            latency=self.latency_mode
        )

        try:
            with (
                httpx.Client() as client,
                io.BytesIO() as buffer
            ):
                # 使用流式请求
                with client.stream(
                    "POST",
                    self.api_url,
                    content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
                    headers={
                        "authorization": f"Bearer {self.api_key}",
                        "content-type": "application/msgpack",
                    },
                    timeout=None
                ) as response:
                    response.raise_for_status()
                    total = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    # 将数据流式写入内存缓冲区
                    for chunk in response.iter_bytes():
                        buffer.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            progress = (downloaded / total) * 100
                            print(f"\r下载进度: {progress:.1f}%", end='', flush=True)
                    
                    if total:
                        print()  # 换行

                    # 将缓冲区指针重置到开始位置
                    buffer.seek(0)
                    
                    # 从内存缓冲区加载MP3音频并转换为WAV
                    try:
                        audio = AudioSegment.from_mp3(buffer)
                        
                        # 应用音频增益
                        if hasattr(self, 'audio_gain_db') and self.audio_gain_db != 0:
                            audio = audio.apply_gain(self.audio_gain_db)
                        
                        # 获取音频时长（毫秒）
                        duration_ms = len(audio)
                        
                        # 导出为WAV格式
                        audio.export(output_file, format="wav")
                        
                        print(f"保存音频文件到: {output_file}")

                        # 音频剪切处理
                        if self.enable_audio_cut:
                            output_path = Path(output_file)
                            temp_output = output_path.parent / f"{output_path.stem}_{uuid.uuid4()}.temp{output_path.suffix}"
                            
                            try:
                                os.rename(output_file, str(temp_output))
                                original_duration, cut_duration = self.audio_cutter.cut_audio(
                                    str(temp_output),
                                    output_file
                                )
                                # 更新时长为剪切后的时长
                                duration_ms = cut_duration * 1000
                            except Exception as e:
                                print(f"音频剪切失败: {e}")
                                if temp_output.exists():
                                    if Path(output_file).exists():
                                        Path(output_file).unlink()
                                    os.rename(str(temp_output), output_file)

                        return output_file, duration_ms / 1000  # 返回文件路径和时长（秒）

                    except Exception as e:
                        print(f"音频处理错误: {e}")
                        # 如果处理失败，尝试保存原始数据以供调试
                        debug_file = Path(output_file).with_suffix('.mp3.debug')
                        with open(debug_file, 'wb') as f:
                            buffer.seek(0)
                            f.write(buffer.read())
                        print(f"已保存原始数据到: {debug_file}")
                        raise

        except httpx.RequestError as e:
            raise Exception(f"请求错误: {e}")
        except Exception as e:
            raise Exception(f"错误: {e}")
    
    def generate_audio_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成多段语音
        
        参数:
        segments: 文本分段列表，每个分段是一个字典，包含'text'字段
        
        返回:
        包含音频文件路径和时长的分段列表
        """
        results = []
        
        for i, segment in enumerate(segments):
            if 'text' not in segment or not segment['text'].strip():
                print(f"跳过空文本分段 {i+1}")
                continue
                
            try:
                # 生成输出文件名
                timestamp = int(datetime.datetime.now().timestamp())
                output_file = os.path.join(self.audio_output_dir, f"segment_{i+1}_{timestamp}.wav")
                
                # 生成音频
                print(f"生成分段 {i+1} 的音频...")
                audio_file, duration = self.generate_audio(segment['text'], output_file)
                
                # 添加到结果
                result = segment.copy()
                result.update({
                    'audio_file': audio_file,
                    'duration': duration,
                    'segment_id': i + 1
                })
                results.append(result)
                
                print(f"分段 {i+1} 音频生成完成: {audio_file}, 时长: {duration:.2f}秒")
                
            except Exception as e:
                print(f"生成分段 {i+1} 音频时出错: {e}")
                # 添加错误信息
                result = segment.copy()
                result.update({
                    'error': str(e),
                    'segment_id': i + 1
                })
                results.append(result)
        
        return results
    
    def save_segments_info(self, segments: List[Dict[str, Any]], output_file: str) -> str:
        """
        保存分段信息到JSON文件
        
        参数:
        segments: 分段信息列表
        output_file: 输出文件路径
        
        返回:
        保存的文件路径
        """
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
        
        print(f"分段信息已保存到: {output_file}")
        return output_file 