import os
import cv2
import tempfile
import base64
import openai
from PIL import Image
import io
import numpy as np
from typing import Optional, Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import json
import time
from pathlib import Path


class VideoFrameExtractionInput(BaseModel):
    """视频帧提取工具的输入模式"""
    video_path: str = Field(..., description="视频文件的路径")
    frame_interval: int = Field(1, description="提取帧的时间间隔（秒）")
    max_frames: int = Field(60, description="最大提取帧数")
    sampling_strategy: str = Field("uniform", description="采样策略: uniform(均匀采样整个视频), front_loaded(前部密集采样)")

class FrameAnalysisInput(BaseModel):
    """帧分析工具的输入模式"""
    frame_paths: List[str] = Field(..., description="帧图像路径列表")
    batch_size: int = Field(15, description="每批处理的最大帧数")

class VisionAnalysisTools:
    
    @staticmethod
    def setup_openai():
        """设置 OpenAI API"""
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        base_url = os.environ.get('OPENAI_BASE_URL')
        if not base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        return openai.Client(api_key=api_key, base_url=base_url)
    
    @staticmethod
    def encode_image(image_path):
        """将图像编码为 base64 字符串"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

class ExtractVideoFramesTool(BaseTool):
    name: str = "ExtractVideoFrames"
    description: str = "从视频中提取关键帧用于分析，支持均匀采样和前部密集采样"
    args_schema: Type[BaseModel] = VideoFrameExtractionInput
    
    def _run(self, video_path: str, frame_interval: int = 5, max_frames: int = 60, sampling_strategy: str = "uniform") -> dict:
        """
        从视频中提取关键帧
        
        参数:
        video_path: 视频文件路径
        frame_interval: 提取帧的时间间隔（秒）
        max_frames: 最大提取帧数
        sampling_strategy: 采样策略: uniform(均匀采样整个视频), front_loaded(前部密集采样)
        
        返回:
        提取的帧路径和时间戳
        """
        if not os.path.exists(video_path):
            return f"Error: Video file not found: {video_path}"
        
        try:
            # 创建临时目录存储帧
            temp_dir = tempfile.mkdtemp()
            
            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return f"Error: Could not open video: {video_path}"
            
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            
            # 根据采样策略确定帧位置
            frame_positions = []
            
            if sampling_strategy.lower() == "uniform":
                # 均匀采样整个视频
                if max_frames >= total_frames:
                    # 如果请求的帧数超过视频总帧数，则降低采样率
                    step = 1
                else:
                    # 计算均匀采样的步长
                    step = total_frames / max_frames
                
                # 生成均匀分布的帧位置
                frame_positions = [int(i * step) for i in range(min(max_frames, total_frames))]
                
            elif sampling_strategy.lower() == "front_loaded":
                # 前部密集采样 (前半部分占用70%的采样点)
                front_frames = int(max_frames * 0.7)
                back_frames = max_frames - front_frames
                
                # 前半部分密集采样
                if front_frames > 0:
                    front_step = (total_frames // 2) / front_frames
                    frame_positions.extend([int(i * front_step) for i in range(front_frames)])
                
                # 后半部分稀疏采样
                if back_frames > 0:
                    back_step = (total_frames - total_frames // 2) / back_frames
                    frame_positions.extend([int(total_frames // 2 + i * back_step) for i in range(back_frames)])
            else:
                # 默认使用基于间隔的采样
                frame_step = int(fps * frame_interval)
                frame_positions = list(range(0, total_frames, frame_step))[:max_frames]
            
            # 提取帧
            frames_info = []
            
            for frame_count, frame_position in enumerate(frame_positions):
                # 设置帧位置
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
                
                # 读取帧
                ret, frame = cap.read()
                if not ret:
                    continue
                
                # 计算时间戳
                timestamp = frame_position / fps
                
                # 保存帧
                frame_path = os.path.join(temp_dir, f"frame_{frame_count:03d}_{timestamp:.2f}s.jpg")
                cv2.imwrite(frame_path, frame)
                
                # 记录帧信息
                frames_info.append({
                    "frame_id": frame_count,
                    "path": frame_path,
                    "timestamp": timestamp,
                    "timestamp_formatted": f"{int(timestamp // 60):02d}:{timestamp % 60:06.3f}"
                })
            
            cap.release()
            
            return {
                "frames": frames_info,
                "total_frames_extracted": len(frames_info),
                "video_duration": duration,
                "temp_directory": temp_dir
            }
            
        except Exception as e:
            return f"Error extracting frames: {str(e)}"

class AnalyzeVideoFramesTool(BaseTool):
    name: str = "AnalyzeVideoFrames"
    description: str = "分析视频帧内容，识别场景、物体、人物和活动"
    
    def __init__(self):
        super().__init__()
        # 设置API（使用类变量而不是实例属性）
        self._api_key = os.environ.get('OPENAI_API_KEY')
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self._base_url = os.environ.get('OPENAI_BASE_URL')
        if not self._base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        # 设置代理（如果需要）
        proxy_url = os.environ.get('HTTP_PROXY')
        self._http_client = None
        if proxy_url:
            import httpx
            self._http_client = httpx.Client(proxies={"http://": proxy_url, "https://": proxy_url})
        
        # 初始化OpenAI客户端
        self._client = openai.Client(
            api_key=self._api_key, 
            base_url=self._base_url,
            http_client=self._http_client
        )
    
    def _run(self, frame_paths: List[str], batch_size: int = 15) -> dict:
        """
        分析视频帧内容
        
        参数:
        frame_paths: 帧图像路径列表
        batch_size: 每批处理的最大帧数
        
        返回:
        分析结果
        """
        try:
            # 使用类变量
            client = self._client
            
            # 强制限制批处理大小，确保不超过模型限制
            if batch_size > 15:
                print(f"警告: 批处理大小 {batch_size} 超过推荐值 15，已自动调整")
                batch_size = 15
            
            # 分批处理帧
            all_frames_analysis = []
            
            # 计算需要处理的批次数
            num_batches = (len(frame_paths) + batch_size - 1) // batch_size
            
            print(f"总共需要处理 {len(frame_paths)} 帧，分为 {num_batches} 批")
            
            for batch_idx in range(num_batches):
                # 获取当前批次的帧
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(frame_paths))
                current_batch = frame_paths[start_idx:end_idx]
                
                print(f"处理第 {batch_idx + 1}/{num_batches} 批帧，共 {len(current_batch)} 帧")
                print(f"当前批次帧范围: {start_idx} 到 {end_idx-1}")
                
                # 构建批量请求
                batch_content = []
                batch_timestamps = []
                
                # 添加提示文本
                batch_content.append({
                    "type": "text", 
                    "text": """分析以下视频帧的内容。对于每一帧，请提供以下信息:
                    1. 主要内容: 描述帧中的主要对象、人物和活动
                    2. 视觉特征: 分析构图、光线、颜色和视觉风格
                    3. 场景类型: 判断这是什么类型的场景（如对话场景、动作场景、过渡场景等）
                    4. 场景变化: 判断这个场景变化和上一帧相比是否属于同一个场景
                    
                    请按顺序分析每一帧，并清晰标明是哪一帧的分析结果。
                    """
                })
                
                # 添加所有图片
                for frame_path in current_batch:
                    # 获取文件名（用于识别）
                    filename = os.path.basename(frame_path)
                    
                    # 提取时间戳（从文件名）
                    timestamp = None
                    if "_" in filename and "s.jpg" in filename:
                        try:
                            timestamp = float(filename.split("_")[-1].replace("s.jpg", ""))
                        except:
                            pass
                    
                    batch_timestamps.append({
                        "path": frame_path,
                        "filename": filename,
                        "timestamp": timestamp
                    })
                    
                    # 编码图片
                    base64_image = VisionAnalysisTools.encode_image(frame_path)
                    
                    # 添加到批次内容
                    batch_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    })
                
                # 发送批量请求
                print(f"发送批量请求，包含 {len(current_batch)} 张图片")
                
                response = client.chat.completions.create(
                    model="gemini-1.5-flash",
                    messages=[
                        {"role": "system", "content": "你是一名专业的视频分析师，擅长分析视频帧内容。请为每一帧提供详细分析，并清晰标明是哪一帧的分析结果。输出结果必须是一个标准的JSON字符串，可以直接使用JSON.parse来解析成json格式。使用json代码块包裹"},
                        {"role": "user", "content": batch_content}
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )
                
                # 解析批量响应
                batch_response = response.choices[0].message.content
                
                # 尝试将响应分配给各个帧
                frame_analyses = self._parse_batch_response(batch_response, batch_timestamps)
                
                # 将当前批次的分析结果添加到总结果中
                all_frames_analysis.extend(frame_analyses)
                
                # 打印当前批次处理完成信息
                print(f"批次 {batch_idx + 1}/{num_batches} 处理完成，已分析 {len(all_frames_analysis)}/{len(frame_paths)} 帧")
            
            return {
                "frames_analysis": all_frames_analysis,
                "total_frames_analyzed": len(all_frames_analysis),
                "batches_processed": num_batches
            }
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return f"Error analyzing frames: {str(e)}\n\nDetails:\n{error_details}"
    
    def _parse_batch_response(self, batch_response: str, batch_timestamps: List[Dict]) -> List[Dict]:
        """
        解析批量响应，将其分配给各个帧
        
        参数:
        batch_response: 模型返回的批量响应文本
        batch_timestamps: 批次中各帧的时间戳信息
        
        返回:
        各帧的分析结果列表
        """
        frame_analyses = []
        
        try:
            # 尝试通过帧号或时间戳标记来分割响应
            # 这是一个简单的实现，可能需要根据实际响应格式进行调整
            
            # 首先尝试查找"帧1"、"帧2"等标记
            frame_markers = []
            for i in range(1, len(batch_timestamps) + 1):
                markers = [
                    f"帧 {i}",
                    f"帧{i}",
                    f"Frame {i}",
                    f"Frame{i}",
                    f"图片 {i}",
                    f"图片{i}",
                    f"Image {i}",
                    f"Image{i}"
                ]
                for marker in markers:
                    if marker in batch_response:
                        frame_markers.append((i-1, marker, batch_response.find(marker)))
            
            # 按照在响应中的位置排序标记
            frame_markers.sort(key=lambda x: x[2])
            
            # 如果找到了足够的标记，按标记分割响应
            if len(frame_markers) >= len(batch_timestamps):
                for i in range(len(frame_markers)):
                    frame_idx = frame_markers[i][0]
                    start_pos = frame_markers[i][2]
                    
                    # 确定结束位置
                    if i < len(frame_markers) - 1:
                        end_pos = frame_markers[i+1][2]
                    else:
                        end_pos = len(batch_response)
                    
                    # 提取分析文本
                    analysis_text = batch_response[start_pos:end_pos].strip()
                    
                    # 添加到结果
                    frame_analyses.append({
                        "frame_path": batch_timestamps[frame_idx]["path"],
                        "timestamp": batch_timestamps[frame_idx]["timestamp"],
                        "analysis": analysis_text
                    })
            else:
                # 如果没有找到足够的标记，尝试平均分割响应
                print("警告: 无法通过标记分割批量响应，尝试平均分割")
                
                # 简单地将响应平均分配给各帧
                total_length = len(batch_response)
                segment_length = total_length // len(batch_timestamps)
                
                for i, frame_info in enumerate(batch_timestamps):
                    start_pos = i * segment_length
                    end_pos = start_pos + segment_length if i < len(batch_timestamps) - 1 else total_length
                    
                    analysis_text = batch_response[start_pos:end_pos].strip()
                    
                    frame_analyses.append({
                        "frame_path": frame_info["path"],
                        "timestamp": frame_info["timestamp"],
                        "analysis": analysis_text,
                        "warning": "自动分割响应，可能不准确"
                    })
                
                # 同时保存完整响应，以便手动检查
                frame_analyses.append({
                    "frame_path": "batch_complete_response",
                    "timestamp": None,
                    "analysis": batch_response,
                    "is_complete_response": True
                })
        
        except Exception as e:
            print(f"解析批量响应时出错: {str(e)}")
            
            # 出错时，将完整响应作为一个条目返回
            frame_analyses.append({
                "frame_path": "batch_error",
                "timestamp": None,
                "analysis": batch_response,
                "error": str(e),
                "is_error_response": True
            })
        
        return frame_analyses

class BatchProcessingFramesTool(BaseTool):
    name: str = "BatchProcessingFrames"
    description: str = "从视频中提取帧并批量处理分析"
    
    def __init__(self):
        super().__init__()
        # 设置OpenAI API
        self._api_key = os.environ.get('OPENAI_API_KEY')
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self._base_url = os.environ.get('OPENAI_BASE_URL')
        if not self._base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")
        
        # 设置代理（如果需要）
        proxy_url = os.environ.get('HTTP_PROXY')
        self._http_client = None
        if proxy_url:
            import httpx
            self._http_client = httpx.Client(proxies={"http://": proxy_url, "https://": proxy_url})
        
        # 初始化OpenAI客户端
        self._client = openai.Client(
            api_key=self._api_key, 
            base_url=self._base_url,
            http_client=self._http_client
        )
        
        # 创建输出目录
        self._output_dir = os.path.join("./output", "frames_analysis")
        os.makedirs(self._output_dir, exist_ok=True)
    
    # ... existing code ...

    def _run(self, video_path: str, max_frames: int = 60, batch_size: int = 15) -> Dict[str, Any]:
        """
        从视频中提取帧并批量处理分析
        
        参数:
        video_path: 视频文件路径
        max_frames: 最大提取帧数
        batch_size: 每批处理的帧数
        
        返回:
        分析结果，包含每帧的分析和结果文件路径
        """
        print(f"开始处理视频: {video_path}")
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        try:
            # 打开视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频: {video_path}")
            
            # 获取视频信息
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            print(f"视频信息: 总帧数={total_frames}, FPS={fps}, 时长={duration:.2f}秒")
            
            # 计算采样间隔
            if total_frames <= max_frames:
                step = 1
                actual_frames = total_frames
            else:
                step = total_frames // max_frames
                actual_frames = max_frames
            
            print(f"将提取 {actual_frames} 帧，采样间隔: {step}")
            
            # 提取帧
            frames = []
            frame_times = []
            
            for i in range(0, total_frames, step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if not ret:
                    print(f"警告: 无法读取帧 {i}")
                    continue
                
                # 转换为RGB（OpenCV使用BGR）
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                
                # 记录时间点
                time_sec = i / fps if fps > 0 else 0
                frame_times.append(time_sec)

                if len(frames) >= max_frames:
                    break
            
            cap.release()
            
            print(f"成功提取 {len(frames)} 帧")
            
            # 批量处理
            all_results = []
            
            for batch_start in range(0, len(frames), batch_size):
                batch_end = min(batch_start + batch_size, len(frames))
                batch_frames = frames[batch_start:batch_end]
                batch_times = frame_times[batch_start:batch_end]
                
                print(f"处理批次 {batch_start//batch_size + 1}/{(len(frames)-1)//batch_size + 1}, 帧 {batch_start}-{batch_end-1}")
                
                # 使用OpenAI分析批次
                batch_results = self._analyze_batch(batch_frames, batch_times)
                all_results.extend(batch_results)
                
                # 短暂暂停，避免API限制
                time.sleep(1)
            
            # 保存结果到文件
            result_file = os.path.join(self._output_dir, f"frames_analysis_{Path(video_path).stem}_{int(time.time())}.json")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(result_file), exist_ok=True)
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "video_path": video_path,
                    "total_frames": total_frames,
                    "fps": fps,
                    "duration": duration,
                    "frames_analyzed": len(frames),
                    "frames_results": all_results
                }, f, ensure_ascii=False, indent=2)
            
            print(f"分析结果已保存到: {result_file}")
            
            return {
                "status": "success",
                "frames_count": len(frames),
                "result_file": result_file
            }
        except Exception as e:
            print(f"处理视频时出错: {str(e)}")
            
            # 尝试创建一个最小的结果文件，以便后续处理可以继续
            try:
                error_result_file = os.path.join(self._output_dir, f"error_frames_analysis_{Path(video_path).stem}_{int(time.time())}.json")
                
                # 确保目录存在
                os.makedirs(os.path.dirname(error_result_file), exist_ok=True)
                
                with open(error_result_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "video_path": video_path,
                        "error": str(e),
                        "frames_results": []
                    }, f, ensure_ascii=False, indent=2)
                
                print(f"错误信息已保存到: {error_result_file}")
                
                return {
                    "status": "error",
                    "error": str(e),
                    "result_file": error_result_file
                }
            except Exception as save_error:
                print(f"保存错误信息时出错: {str(save_error)}")
                raise e
    
    def _analyze_batch(self, frames: List[Any], times: List[float]) -> List[Dict[str, Any]]:
        """分析一批帧"""
        results = []
        
        try:
            # 构建提示
            prompt = """分析这些视频帧，提供以下信息:
            1. 场景类型和环境描述
            2. 主要物体和元素
            3. 人物（如果有）
            4. 动作和活动
            5. 情绪和氛围
            6. 展示产品相关元素（如果有）
            7. 视觉风格和摄影特点
            8. 画面中的文字和字幕信息
            9. 画面中的品牌信息（如果有）
            
            以JSON格式返回，每帧一个对象，包裹在json代码块中，不要任何多余信息，否则无法解析。"""
            
            # 准备消息内容
            content = [{"type": "text", "text": prompt}]
            
            # 添加图像
            for frame in frames:
                # 将numpy数组转换为PIL图像
                pil_image = Image.fromarray(frame)
                
                # 调整图像大小，避免过大
                max_size = 1024
                if pil_image.width > max_size or pil_image.height > max_size:
                    ratio = min(max_size / pil_image.width, max_size / pil_image.height)
                    new_width = int(pil_image.width * ratio)
                    new_height = int(pil_image.height * ratio)
                    pil_image = pil_image.resize((new_width, new_height))
                
                # 将PIL图像转换为字节流
                buffer = io.BytesIO()
                pil_image.save(buffer, format="JPEG")
                image_bytes = buffer.getvalue()
                
                # 编码为base64
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                
                # 添加到内容
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })
            
            # 发送请求到OpenAI
            response = self._client.chat.completions.create(
                model="gemini-1.5-flash",  # 或使用其他支持视觉的模型
                messages=[
                    {"role": "system", "content": "你是一名专业的视频分析师，擅长分析视频帧内容。请以JSON格式返回分析结果。请务必输出json格式，不要输出其他格式，包裹在json代码块中。不要任何多余信息，否则无法解析。"},
                    {"role": "user", "content": content}
                ],
                max_tokens=4000,
                temperature=0.1
            )
            
            # 解析响应
            try:
                # 获取响应文本
                content = response.choices[0].message.content
                
                # 尝试多种方式提取和解析JSON
                parsed_results = None
                
                # 方法1: 查找JSON代码块
                import re
                json_patterns = [
                    r'```json\n(.*?)\n```',  # 标准markdown JSON块
                    r'```\n(.*?)\n```',       # 无类型markdown代码块
                    r'```(.*?)```',           # 无换行的markdown代码块
                    r'{[\s\S]*}',             # 查找最外层的大括号内容
                    r'\[[\s\S]*\]'            # 查找最外层的方括号内容
                ]
                
                for pattern in json_patterns:
                    json_match = re.search(pattern, content, re.DOTALL)
                    if json_match:
                        try:
                            # 检查匹配组的数量
                            if len(json_match.groups()) > 0:
                                json_str = json_match.group(1)
                            else:
                                # 如果没有捕获组，使用整个匹配
                                json_str = json_match.group(0)
                            
                            parsed_results = json.loads(json_str)
                            print(f"成功使用模式 '{pattern}' 解析JSON")
                            break
                        except (json.JSONDecodeError, IndexError) as e:
                            print(f"使用模式 '{pattern}' 解析JSON失败: {str(e)}")
                            continue
                
                # 方法2: 尝试直接解析整个内容
                if parsed_results is None:
                    try:
                        parsed_results = json.loads(content)
                        print("成功直接解析整个内容为JSON")
                    except json.JSONDecodeError:
                        pass
                
                # 方法3: 尝试修复并解析可能被截断的JSON
                if parsed_results is None:
                    try:
                        # 尝试修复常见的JSON截断问题
                        fixed_content = content
                        # 如果以逗号结尾，移除它
                        fixed_content = re.sub(r',\s*$', '', fixed_content)
                        # 如果缺少结束括号，添加它们
                        if fixed_content.count('[') > fixed_content.count(']'):
                            fixed_content += ']' * (fixed_content.count('[') - fixed_content.count(']'))
                        if fixed_content.count('{') > fixed_content.count('}'):
                            fixed_content += '}' * (fixed_content.count('{') - fixed_content.count('}'))
                        
                        parsed_results = json.loads(fixed_content)
                        print("成功通过修复JSON格式解析内容")
                    except json.JSONDecodeError:
                        pass
                
                # 如果所有方法都失败，记录详细错误并创建简单结果
                if parsed_results is None:
                    print(f"无法解析JSON响应，将创建简单结果")
                    print(f"原始响应内容: {content[:]}...")
                    
                    # 创建简单结果
                    for i, time_val in enumerate(times):
                        results.append({
                            "time": time_val,
                            "error": "无法解析模型响应",
                            "raw_content_sample": content[:] + "..." if i == 0 else "见第一帧"
                        })
                    return results
                
                # 确保结果是列表
                if not isinstance(parsed_results, list):
                    if isinstance(parsed_results, dict):
                        if "frames" in parsed_results:
                            parsed_results = parsed_results["frames"]
                        else:
                            parsed_results = [parsed_results]
                
                # 添加时间信息
                for i, result in enumerate(parsed_results):
                    if i < len(times):
                        result["time"] = times[i]
                    results.append(result)
                
            except Exception as parse_error:
                print(f"解析OpenAI响应时出错: {str(parse_error)}")
                # print(f"原始响应的前500个字符: {content[:500]}...")
                
                # 创建简单结果
                for i, time_val in enumerate(times):
                    results.append({
                        "time": time_val,
                        "error": f"解析错误: {str(parse_error)}",
                        "raw_content_sample": content[:] + "..." if i == 0 else "见第一帧"
                    })
        
        except Exception as e:
            print(f"调用OpenAI API时出错: {str(e)}")
            
            # 创建错误结果
            for time_val in times:
                results.append({
                    "time": time_val,
                    "error": f"OpenAI API错误: {str(e)}"
                })
        
        return results



class LoadFramesAnalysisFromFileTool(BaseTool):
    name: str = "LoadFramesAnalysisFromFile"
    description: str = "从文件加载帧分析结果"
    
    def _run(self, file_path: str) -> Dict[str, Any]:
        """
        从文件加载帧分析结果
        
        参数:
        file_path: 帧分析结果文件路径
        
        返回:
        帧分析结果
        """
        print(f"加载帧分析结果: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Frames analysis file not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"成功加载帧分析结果，包含 {len(data.get('frames_results', []))} 帧")
            return data
            
        except Exception as e:
            print(f"加载帧分析结果时出错: {str(e)}")
            raise 