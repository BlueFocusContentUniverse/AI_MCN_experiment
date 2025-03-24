import os
import json
import datetime
import tempfile
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
import re
import subprocess

from crewai import Task, Crew, Process
from crewai.llm import LLM

from agents.script_parsing_agent import ScriptParsingAgent
from agents.material_search_agent import MaterialSearchAgent
from agents.editing_planning_agent import EditingPlanningAgent
from services.video_editing_service import VideoEditingService
from services.segment_search_service import SegmentSearchService
from tools.subtitle_tool import SubtitleTool
from services.fish_audio_service import FishAudioService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuoteMatchingVideoService:
    """基于原话匹配和画面匹配的视频剪辑服务"""
    
    def __init__(self, output_dir: str = "./output"):
        """
        初始化服务
        
        参数:
        output_dir: 输出目录
        """
        # 确保 output_dir 是绝对路径
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 创建子目录
        self.segments_dir = os.path.join(self.output_dir, "segments")
        self.final_dir = os.path.join(self.output_dir, "final")
        
        os.makedirs(self.segments_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        
        # 初始化Agent和服务
        self.script_parsing_agent = ScriptParsingAgent.create()
        self.material_search_agent = MaterialSearchAgent.create()
        self.editing_planning_agent = EditingPlanningAgent.create()
        self.video_editing_service = VideoEditingService(output_dir=self.segments_dir)
        
        # 初始化字幕工具
        self.subtitle_tool = SubtitleTool()
        
        # 添加token使用记录
        self.token_usage_records = []
        
        # 设置LLM
        self.llm = LLM(
            model="gemini-1.5-pro",
            api_key=os.environ.get('OPENAI_API_KEY'),
            base_url=os.environ.get('OPENAI_BASE_URL'),
            temperature=0.1,
            custom_llm_provider="openai",
            request_timeout=180  # 增加超时时间到180秒
        )
        
        # 添加FishAudioService
        self.audio_dir = os.path.join(self.output_dir, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)
        self.fish_audio_service = FishAudioService(audio_output_dir=self.audio_dir)
        
        # 添加SegmentSearchService
        self.segment_search_service = SegmentSearchService(output_dir=self.output_dir)
    
    def _ensure_absolute_path(self, path: str) -> str:
        """确保路径是绝对路径"""
        if path is None or not path:
            return ""
        if os.path.isabs(path):
            return path
        # 从环境变量获取基础目录，如果没有设置，使用默认值
        base_dir = os.environ.get('VIDEO_BASE_DIR', '/path/to/videos')
        return os.path.join(base_dir, path)
    
    def produce_video(self, script: str, special_requirements: str = "") -> Dict[str, Any]:
        """
        根据脚本生产视频
        
        参数:
        script: 脚本文本，包含需要原话匹配的部分和画面匹配的部分
        special_requirements: 特殊需求，将添加到任务描述中
        
        返回:
        生产结果，包含最终视频路径和相关信息
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"quote_video_{timestamp}"
        
        try:
            # 1. 解析脚本，区分原话匹配和画面匹配
            logger.info("解析脚本...")
            parsed_script = self._parse_script(script, special_requirements)
            print(parsed_script)
            
            # 保存解析结果
            parsed_script_file = os.path.join(self.output_dir, f"{project_name}_parsed_script.json")
            with open(parsed_script_file, 'w', encoding='utf-8') as f:
                json.dump(parsed_script, f, ensure_ascii=False, indent=2)
            
            # 2. 搜索素材
            logger.info("搜索匹配的视频素材...")
            materials = self._search_materials(parsed_script, special_requirements)
            
            # 保存素材信息
            materials_file = os.path.join(self.output_dir, f"{project_name}_materials.json")
            with open(materials_file, 'w', encoding='utf-8') as f:
                json.dump(materials, f, ensure_ascii=False, indent=2)
            
            # 3. 规划剪辑
            logger.info("规划视频剪辑...")
            editing_plan = self._plan_editing(materials, special_requirements)
            
            # 保存剪辑规划
            editing_plan_file = os.path.join(self.output_dir, f"{project_name}_editing_plan.json")
            with open(editing_plan_file, 'w', encoding='utf-8') as f:
                json.dump(editing_plan, f, ensure_ascii=False, indent=2)
            
            # 4. 执行剪辑，拼接所有片段
            logger.info("执行视频剪辑...")
            final_video = self._execute_editing(editing_plan, project_name)
            
            # # 5. 添加字幕
            # logger.info("添加字幕...")
            # final_video_with_subtitles = self._add_subtitles(final_video, editing_plan, project_name)
            
            # 返回结果
            result = {
                "project_name": project_name,
                "script": script,
                "parsed_script": {
                    "data": parsed_script,
                    "file": parsed_script_file
                },
                "materials": {
                    "data": materials,
                    "file": materials_file
                },
                "editing_plan": {
                    "data": editing_plan,
                    "file": editing_plan_file
                },
                "final_video": final_video,
                "token_usage_records": self.token_usage_records
            }
            
            # 保存完整结果
            result_file = os.path.join(self.final_dir, f"{project_name}_result.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"视频生产完成: {final_video}")
            return result
            
        except Exception as e:
            logger.error(f"视频生产过程中出错: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "project_name": project_name,
                "script": script
            }
    
    def _parse_script(self, script: str, special_requirements: str = "") -> Dict[str, Any]:
        """
        解析脚本，区分原话匹配和画面匹配
        
        参数:
        script: 脚本文本
        special_requirements: 特殊需求
        
        返回:
        解析后的脚本结构
        """
        # 创建脚本解析任务
        parse_script_task = Task(
            description=f"""请解析以下脚本，区分需要原话匹配的部分和需要画面匹配的部分：

{script}

原话匹配部分通常是括号内的内容，例如：（这是原话）
画面匹配部分是其他所有内容。

请输出结构化的解析结果，包含每个片段的类型、内容等信息。


特殊需求: {special_requirements}输出的json内禁止出现换行！！！""",
            agent=self.script_parsing_agent,
            expected_output="""解析后的脚本结构，包含每个片段的类型、内容等信息
            "segments": [
                        {
                            "segment_id": 1,
                            "type": "quote", 原话匹配类型为"quote"，画面匹配类型为"visual"
                            "content": "需要匹配的内容",
                            "description": "额外描述信息"
                        }
                    ]"""
        )
        
        # 创建Crew并执行任务
        script_parsing_crew = Crew(
            agents=[self.script_parsing_agent],
            tasks=[parse_script_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行解析
        result = script_parsing_crew.kickoff()
        
        # 记录token使用情况
        self._record_token_usage(result, "脚本解析")
        
        # 使用通用JSON解析方法
        return self._safe_parse_json(result, "_parse_script")
    
    def _search_materials(self, parsed_script: Dict[str, Any], special_requirements: str = "") -> Dict[str, Any]:
        """
        搜索匹配的视频素材
        
        参数:
        parsed_script: 解析后的脚本结构
        special_requirements: 特殊需求
        
        返回:
        匹配的视频素材
        """
        segments = []
        
        # 处理解析JSON失败的情况
        if "error" in parsed_script and "raw_output" in parsed_script:
            logger.warning(f"解析JSON失败，尝试从raw_output中提取: {parsed_script['error']}")
            raw_output = parsed_script["raw_output"]
            
            try:
                # 尝试直接解析raw_output
                cleaned_output = raw_output.strip()
                segments_data = json.loads(cleaned_output)
                if "segments" in segments_data and isinstance(segments_data["segments"], list):
                    segments = segments_data["segments"]
                    logger.info(f"成功从raw_output中提取到 {len(segments)} 个片段")
                else:
                    logger.warning("从raw_output中提取的数据没有segments字段")
            except json.JSONDecodeError:
                logger.warning("无法解析raw_output为JSON，尝试使用正则表达式提取")
                
                # 使用正则表达式提取segment信息
                segment_pattern = r'"segment_id":\s*(\d+),\s*"type":\s*"(quote|visual)",\s*"content":\s*"([^"]+)",\s*"description":\s*"([^"]+)"'
                matches = re.findall(segment_pattern, raw_output)
                
                if matches:
                    logger.info(f"使用正则表达式提取到 {len(matches)} 个片段")
                    for match in matches:
                        segment_id, segment_type, content, description = match
                        segments.append({
                            "segment_id": int(segment_id),
                            "type": segment_type,
                            "content": content,
                            "description": description
                        })
                else:
                    logger.warning("使用正则表达式也无法提取片段信息")
        else:
            # 正常情况，从parsed_script中提取segments
            if "segments" in parsed_script and isinstance(parsed_script["segments"], list):
                segments = parsed_script["segments"]
            else:
                # 尝试从原始结果中提取
                segments = [parsed_script]
        
        # 如果仍然没有提取到segments，返回空列表
        if not segments:
            logger.warning("无法提取片段信息，返回空列表")
            return {"segments": []}
        
        results = []
        quote_segments = []   # 用于存储quote类型的素材
        visual_segments = []  # 用于存储visual类型的素材
        
        # 分别处理每个片段
        for i, segment in enumerate(segments):
            segment_id = segment.get("segment_id", i + 1)
            segment_type = segment.get("type", "visual")  # 默认为画面匹配
            quote_text = segment.get("content", "")
            
            if not quote_text:
                logger.warning(f"片段 {segment_id} 没有内容，跳过")
                continue
            
            # 根据片段类型分别处理
            if segment_type == "quote":
                # 原话匹配部分
                logger.info(f"为原话匹配片段 {segment_id} 搜索视频: {quote_text}")
                
                # 使用SegmentSearchService查找匹配的视频片段
                search_result = self.segment_search_service.search_and_process(
                    query_text=quote_text,
                    limit=10,
                    threshold=0.1,
                    keep_audio=True
                )
                
                # 检查是否成功
                if "error" in search_result:
                    error_message = search_result.get("error", "未知错误")
                    logger.error(f"搜索素材时出错: {error_message}")
                    # 注意：这里不要覆盖整个result变量，只记录错误信息
                    quote_error = {"error": error_message}
                    # 可以将错误信息添加到结果中，但不覆盖整个result
                    results.append({"type": "quote", "error": error_message})
                else:
                    # 提取最终视频路径和处理过的片段路径
                    final_video = search_result.get("final_video", "")
                    segment_paths = search_result.get("segment_paths", [])
                    original_to_extracted_map = search_result.get("original_to_extracted_map", {})
                    
                    logger.info(f"搜索成功，最终视频: {final_video}")
                    logger.info(f"处理了 {len(segment_paths)} 个片段")
                    
                    # 如果有原始视频和提取视频的映射关系，保存这些信息
                    if original_to_extracted_map:
                        logger.info(f"找到 {len(original_to_extracted_map)} 个原始视频到提取视频的映射")
                        
                        original_paths = list(original_to_extracted_map.keys())
                        extracted_paths = list(original_to_extracted_map.values())
                        
                        if original_paths and extracted_paths:
                            # 创建一个引用结果项
                            quote_result = {
                                "segment_id": f"quote_{len(quote_segments) + 1}",
                                "type": "quote",
                                "content": quote_text,
                                "final_video": final_video,  # 最终合并的视频
                                "video_path": segment_paths[0] if segment_paths else "",  # 保存第一个片段作为备用
                                "original_paths": original_paths,  # 保存所有原始视频路径
                                "extracted_paths": extracted_paths  # 保存所有提取的片段路径
                            }
                            quote_segments.append(quote_result)
                            results.append(quote_result)
                    elif final_video and os.path.exists(final_video):
                        # 如果没有映射关系但有最终视频，直接使用最终视频
                        quote_result = {
                            "segment_id": f"quote_{len(quote_segments) + 1}",
                            "type": "quote",
                            "content": quote_text,
                            "final_video": final_video,  # 最终视频
                            "video_path": segment_paths[0] if segment_paths else "",  # 第一个片段作为备用
                            "original_paths": [],  # 没有原始路径信息
                            "extracted_paths": segment_paths  # 所有片段路径
                        }
                        quote_segments.append(quote_result)
                        results.append(quote_result)
                    else:
                        # 如果没有有效的视频，记录错误
                        logger.error(f"未找到有效的视频文件: final_video={final_video}, 存在={os.path.exists(final_video) if final_video else False}")
                        error_message = "未找到有效的视频文件"
                        # 注意：这里不要覆盖整个result变量，只记录错误信息
                        quote_error = {"error": error_message}
                        # 可以将错误信息添加到结果中，但不覆盖整个result
                        results.append({"type": "quote", "error": error_message})
                    
                # 记录token使用情况
                self._record_token_usage(search_result, step_name="引用素材搜索")
            else:
                # 画面匹配部分
                logger.info(f"为画面匹配片段 {segment_id} 生成口播音频: {quote_text}")
                
                try:
                    # 生成音频文件名
                    audio_file = os.path.join(self.audio_dir, f"segment_{segment_id}.wav")
                    
                    # 生成音频
                    audio_file, duration = self.fish_audio_service.generate_audio(quote_text, audio_file)
                    logger.info(f"生成口播音频成功，时长: {duration}秒")
                    
                    # 构建需求描述
                    description = segment.get("description", "")
                    requirement = {
                        "segment_id": segment_id,
                        "description": quote_text + " " + description,
                        "scene_type": segment.get("scene_type", ""),
                        "mood": segment.get("mood", ""),
                        "duration": duration  # 添加时长需求
                    }
                    
                    # 使用MaterialSearchTool查找匹配的视频素材
                    from agents.material_search_agent import MaterialSearchTool
                    material_search_tool = MaterialSearchTool()
                    search_results = material_search_tool._run(requirements=[requirement], limit_per_requirement=5)
                    
                    if search_results and "results" in search_results and search_results["results"]:
                        # 获取匹配的视频
                        matching_videos = []
                        for result in search_results["results"]:
                            if result.get("requirement", {}).get("segment_id") == segment_id:
                                matching_videos = result.get("matching_videos", [])
                                break
                        
                        if matching_videos:
                            # 添加结果
                            result = {
                                "segment_id": segment_id,
                                "type": "visual",
                                "content": quote_text,
                                "audio_file": audio_file,
                                "audio_duration": duration,
                                "matching_videos": matching_videos
                            }
                            results.append(result)
                            visual_segments.append(result)  # 添加到visual类型列表
                        else:
                            logger.warning(f"画面匹配片段 {segment_id} 没有找到匹配的视频素材")
                    else:
                        logger.warning(f"画面匹配片段 {segment_id} 没有找到匹配的视频素材")
                
                except Exception as e:
                    logger.error(f"处理画面匹配片段时出错: {str(e)}", exc_info=True)
        
        # 最终返回结果包含所有素材类型
        final_result = {
            "segments": results,            # 保持原有结构以兼容现有代码
            "quote_segments": quote_segments,  # 添加quote类型的素材
            "visual_segments": visual_segments  # 添加visual类型的素材
        }
        
        logger.info(f"素材搜索完成，找到 {len(quote_segments)} 个quote素材，{len(visual_segments)} 个visual素材")
        return final_result
    
    def _plan_editing(self, materials: Dict[str, Any], special_requirements: str = "") -> Dict[str, Any]:
        """
        规划视频剪辑
        
        参数:
        materials: 搜索到的素材信息
        special_requirements: 特殊需求
        
        返回:
        剪辑规划
        """
        # 只为visual类型的素材创建剪辑规划
        visual_materials = {"segments": materials.get("visual_segments", [])}
        
        # 创建剪辑规划任务
        plan_editing_task = Task(
            description=f"""根据以下素材信息，规划视频剪辑：

{json.dumps(visual_materials, ensure_ascii=False, indent=2)}

请为每个素材规划具体的剪辑方案，包括：
1. 画面匹配部分：选择合适的视频片段，根据口播音频时长剪辑，替换原音频

每个分段可以使用多个视频素材，特别是画面匹配部分需要根据内容变化和节奏感选择2-5个片段组合。
每个片段的时长控制在2-10秒之间，适合短视频平台。

特殊需求: {special_requirements}""",
            agent=self.editing_planning_agent,
            expected_output="""详细的剪辑规划，包括每个分段使用的素材、时间点和剪辑方式
            请包含以下信息：
1. 每个音频分段对应的视频素材路径
2. 视频的开始和结束时间点
3. 选择该片段的理由
4. 每段口播需要多段素材(**每条素材必须长于2秒！！！**)进行组合剪辑呈现效果，但如果口播内容较少（不超过6秒），则只需要一条素材即可。
5. 不同的口播视频节奏不同，请根据口播视频的节奏进行剪辑，不要给用户带来不好的观感。
6. 请确保剪辑视频的连贯性和流畅性，不要给用户带来不好的观感。
 output format：{
    "segments": [
        {
            "segment_id": "1",
            "video_path": "video1.mp4",
            "start_time": 0.0,
            "end_time": 10.0,
            "reason": "选择这段视频的原因"
        },
        {
            "segment_id": "1",
            "video_path": "video2.mp4",
            "start_time": 25.0,
            "end_time": 35.0,
            "reason": "选择这段视频的原因"
        },
        {
            "segment_id": "2",
            "video_path": "video3.mp4",
            "start_time": 40.0,
            "end_time": 50.0,
            "reason": "选择这段视频的原因"
        }
    ]
}，请务必按照**output format**输出，不要输出任何多余信息，否则我的代码无法解析，**output format**内禁止出现换行符！"""
        )
        
        # 创建Crew并执行任务
        editing_planning_crew = Crew(
            agents=[self.editing_planning_agent],
            tasks=[plan_editing_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行规划
        result = editing_planning_crew.kickoff()
        
        # 记录token使用情况
        self._record_token_usage(result, "剪辑规划")
        
        # 使用通用JSON解析方法
        editing_plan = self._safe_parse_json(result, "_plan_editing")
        
        # 添加原始素材信息到编辑计划中
        editing_plan["original_materials"] = materials
        editing_plan["quote_segments"] = materials.get("quote_segments", [])
        
        # 返回规划结果
        return editing_plan
    
    def _normalize_audio(self, input_file: str, output_file: str) -> str:
        """
        标准化音频音量，使所有片段的音量保持一致水平
        
        参数:
        input_file: 输入视频文件
        output_file: 输出视频文件
        
        返回:
        处理后的文件路径
        """
        logger.info(f"标准化音频音量: {input_file} -> {output_file}")
        try:
            # 先检查视频是否有音频流
            check_audio_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_file
            ]
            result = subprocess.run(check_audio_cmd, capture_output=True, text=True)
            
            # 如果没有音频流，直接复制视频文件
            if result.returncode != 0 or not result.stdout.strip():
                logger.warning(f"未检测到音频流: {input_file}，跳过音频标准化")
                # 简单复制文件到输出路径
                copy_cmd = [
                    "ffmpeg", "-y",
                    "-i", input_file,
                    "-c", "copy",
                    output_file
                ]
                subprocess.run(copy_cmd, check=True, capture_output=True, text=True)
                return output_file
            
            # 先分析音频
            probe_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-select_streams", "a:0", 
                "-show_entries", "stream=codec_name,channels,sample_rate,bit_rate", 
                "-of", "json", 
                input_file
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                audio_info = json.loads(result.stdout)
                logger.info(f"音频信息: {audio_info}")
            
            # 标准化音频命令 - 统一使用固定的音频参数
            cmd = [
                "ffmpeg", "-y",
                "-i", input_file,
                "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=summary", 
                "-c:v", "copy",            # 复制视频流不重新编码
                "-c:a", "aac",             # 统一使用AAC编码器
                "-b:a", "192k",            # 统一比特率
                "-ar", "48000",            # 统一采样率
                "-ac", "2",                # 统一为立体声
                output_file
            ]
            
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode == 0:
                logger.info(f"音频音量标准化成功: {output_file}")
                return output_file
            else:
                logger.error(f"音频标准化失败: {process.stderr}")
                # 如果标准化失败，尝试直接转码而不做音量标准化
                logger.info("尝试直接转码而不做音量标准化...")
                simple_cmd = [
                    "ffmpeg", "-y",
                    "-i", input_file,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "48000",
                    "-ac", "2",
                    output_file
                ]
                try:
                    subprocess.run(simple_cmd, check=True)
                    logger.info(f"简单转码成功: {output_file}")
                    return output_file
                except Exception as e:
                    logger.error(f"简单转码失败: {str(e)}")
                    return input_file
        except Exception as e:
            logger.error(f"音频音量标准化失败: {str(e)}")
            # 如果失败，返回原始文件
            return input_file
    
    def _execute_editing(self, editing_plan: Dict[str, Any], project_name: str) -> str:
        """
        执行视频剪辑，按照original_materials中的segments顺序处理并合并视频片段
        
        参数:
        editing_plan: 剪辑规划
        project_name: 项目名称
        
        返回:
        最终视频文件路径
        """
        # 创建临时目录
        temp_dir = os.path.join(self.output_dir, f"temp_{project_name}")
        os.makedirs(temp_dir, exist_ok=True)
        
        # 创建处理后的片段列表
        processed_video_segments = []
        
        try:
            # 获取原始片段顺序
            if "original_materials" not in editing_plan or "segments" not in editing_plan["original_materials"]:
                logger.error("剪辑规划中缺少original_materials.segments")
                raise ValueError("剪辑规划中缺少original_materials.segments")
                
            original_segments = editing_plan["original_materials"]["segments"]
            logger.info(f"从original_materials中获取到 {len(original_segments)} 个原始片段")
            
            # 获取quote_segments和visual_segments的引用
            quote_segments = editing_plan.get("quote_segments", [])
            segments = editing_plan.get("segments", [])  # visual类型的素材
            
            # 创建segment_id到素材的映射，方便查找
            quote_map = {str(q.get("segment_id", "")): q for q in quote_segments}
            visual_map = {}
            
            # 对visual类型的素材按segment_id分组
            for segment in segments:
                segment_id = str(segment.get("segment_id", "0"))
                if segment_id not in visual_map:
                    visual_map[segment_id] = []
                visual_map[segment_id].append(segment)
            
            # 1. 按照原始片段顺序处理每个片段
            for segment in original_segments:
                segment_id = str(segment.get("segment_id", "0"))
                segment_type = segment.get("type", "visual")  # 默认为visual类型
                content = segment.get("content", "")
                
                logger.info(f"处理原始片段 {segment_id}，类型: {segment_type}")
                
                # 根据类型区分处理方法
                if segment_type == "quote":
                    # 查找对应的quote素材
                    quote_segment = quote_map.get(segment_id)
                    if not quote_segment:
                        logger.warning(f"未找到对应的quote素材: {segment_id}")
                        continue
                    
                    # 获取final_video路径
                    final_video = self._ensure_absolute_path(quote_segment.get("final_video", ""))
                    
                    if not final_video or not os.path.exists(final_video):
                        logger.warning(f"Quote片段 {segment_id} 的final_video路径无效: {final_video}")
                        
                        # 尝试使用备用video_path
                        video_path = self._ensure_absolute_path(quote_segment.get("video_path", ""))
                        if video_path and os.path.exists(video_path):
                            logger.info(f"使用备用video_path: {video_path}")
                            final_video = video_path
                        else:
                            logger.error(f"Quote片段 {segment_id} 没有可用的视频文件")
                            continue
                    
                    # 获取视频时长
                    try:
                        probe_cmd = [
                            "ffprobe",
                            "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            final_video
                        ]
                        duration = float(subprocess.check_output(probe_cmd).decode().strip())
                    except Exception as e:
                        logger.error(f"获取Quote视频时长时出错: {str(e)}")
                        duration = 5.0  # 使用默认值
                    
                    # 对视频进行标准化处理：先标准化尺寸，再标准化音频
                    try:
                        # 1. 尺寸标准化
                        normalized_video_path = os.path.join(temp_dir, f"normalized_size_{segment_id}.mp4")
                        final_video = self.video_editing_service.normalize_video(
                            final_video,
                            normalized_video_path,
                            target_width=1080,
                            target_height=1920,
                            fps=30
                        )
                        logger.info(f"Quote片段 {segment_id} 尺寸标准化完成: {final_video}")
                        
                        # 2. 音频音量标准化
                        normalized_audio_path = os.path.join(temp_dir, f"normalized_audio_{segment_id}.mp4")
                        final_video = self._normalize_audio(final_video, normalized_audio_path)
                        logger.info(f"Quote片段 {segment_id} 音频标准化完成: {final_video}")
                    except Exception as e:
                        logger.error(f"标准化Quote片段 {segment_id} 时出错: {str(e)}")
                        # 继续使用原始视频
                    
                    # 添加到处理后的片段列表，记录在original_segments中的索引位置
                    processed_video_segments.append({
                        "file_path": final_video,
                        "segment_id": segment_id,
                        "text": content,
                        "duration": duration,
                        "type": "quote",
                        "original_index": original_segments.index(segment)  # 记录在原始列表中的位置
                    })
                    
                    logger.info(f"Quote片段 {segment_id} 处理完成，使用视频: {final_video}")
                
                else:  # visual类型
                    # 查找对应的visual素材
                    visual_parts = visual_map.get(segment_id, [])
                    if not visual_parts:
                        logger.warning(f"未找到对应的visual素材: {segment_id}")
                        continue
                    
                    logger.info(f"为Visual片段 {segment_id} 处理 {len(visual_parts)} 个部分")
                    
                    # 处理每个部分
                    segment_parts = []
                    for j, part in enumerate(visual_parts):
                        video_path = part.get("video_path", "")
                        start_time = float(part.get("start_time", 0))
                        end_time = float(part.get("end_time", 0))
                        
                        # 确保视频路径是绝对路径
                        video_path = self._ensure_absolute_path(video_path)
                        
                        if not video_path or not os.path.exists(video_path):
                            logger.warning(f"Visual片段 {segment_id} 的部分 {j+1} 视频路径无效: {video_path}")
                            continue
                        
                        # 确保时长合理
                        if end_time - start_time < 1.0:
                            logger.warning(f"片段 {segment_id} 的部分 {j+1} 时长过短，调整为至少1秒")
                            end_time = start_time + 1.0
                        
                        try:
                            # 为每个部分创建输出文件
                            part_output = os.path.join(temp_dir, f"segment_{segment_id}_part_{j+1}.mp4")
                            
                            # 视频类型始终替换原音频
                            keep_audio = False
                            
                            # 剪切视频
                            self.video_editing_service.cut_video_segment(
                                video_path=video_path,
                                start_time=start_time,
                                end_time=end_time,
                                output_file=part_output,
                                keep_audio=keep_audio  # 始终不保留原音频
                            )
                            
                            segment_parts.append({
                                "file_path": part_output,
                                "part_id": j + 1
                            })
                            
                        except Exception as e:
                            logger.error(f"处理Visual片段 {segment_id} 的部分 {j+1} 时出错: {str(e)}")
                    
                    if not segment_parts:
                        logger.warning(f"Visual片段 {segment_id} 没有成功处理的部分")
                        continue
                    
                    # 合并分段内的所有部分
                    if len(segment_parts) > 1:
                        # 创建片段列表文件
                        parts_file = os.path.join(temp_dir, f"segment_{segment_id}_parts.txt")
                        
                        # 确保目录存在
                        os.makedirs(os.path.dirname(parts_file), exist_ok=True)
                        
                        with open(parts_file, "w") as f:
                            for part in segment_parts:
                                # 使用绝对路径，确保ffmpeg能找到文件
                                absolute_path = os.path.abspath(part['file_path'])
                                f.write(f"file '{absolute_path}'\n")
                        
                        # 合并输出文件
                        segment_output = os.path.join(temp_dir, f"segment_{segment_id}.mp4")
                        
                        # 使用ffmpeg合并片段，使用绝对路径
                        concat_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f", "concat",
                            "-safe", "0",
                            "-i", os.path.abspath(parts_file),  # 使用绝对路径
                            "-c", "copy",
                            os.path.abspath(segment_output)  # 使用绝对路径
                        ]
                        
                        try:
                            # 直接执行命令，不切换工作目录
                            subprocess.run(concat_cmd, check=True)
                            logger.info(f"Visual片段 {segment_id} 的多个部分已合并")
                        except Exception as e:
                            logger.error(f"合并Visual片段 {segment_id} 的多个部分时出错: {str(e)}")
                            # 如果合并失败，使用第一个片段
                            if segment_parts:
                                segment_output = segment_parts[0]["file_path"]
                                logger.info(f"使用第一个部分作为备用: {segment_output}")
                            else:
                                continue
                    else:
                        # 只有一个部分，直接使用
                        segment_output = segment_parts[0]["file_path"]
                    
                    # 查找对应的音频文件
                    audio_file = None
                    
                    # 从original_materials中查找音频文件
                    for audio_segment in original_segments:
                        if str(audio_segment.get("segment_id", "")) == segment_id:
                            audio_file = self._ensure_absolute_path(audio_segment.get("audio_file", ""))
                            break
                    
                    # 如果没找到，尝试从audio_segments中查找
                    if not audio_file and "audio_segments" in editing_plan:
                        for audio_segment in editing_plan["audio_segments"]:
                            if str(audio_segment.get("segment_id", "")) == segment_id:
                                audio_file = self._ensure_absolute_path(audio_segment.get("audio_file", ""))
                                break
                    
                    logger.info(f"为Visual片段 {segment_id} 找到的音频文件: {audio_file}")
                    
                    # 添加音频到视频
                    if audio_file and os.path.exists(audio_file):
                        segment_with_audio = os.path.join(temp_dir, f"segment_{segment_id}_with_audio.mp4")
                        
                        logger.info(f"为Visual片段 {segment_id} 添加音频: {audio_file}")
                        
                        # 合并视频和音频
                        audio_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", segment_output,      # 视频输入
                            "-i", audio_file,          # 音频输入
                            "-map", "0:v:0",           # 使用第一个输入的视频流
                            "-map", "1:a:0",           # 使用第二个输入的音频流
                            "-c:v", "copy",            # 复制视频编码
                            "-c:a", "aac",             # 音频编码
                            "-b:a", "192k",            # 音频比特率
                            "-shortest",               # 使用最短的输入长度
                            segment_with_audio
                        ]
                        
                        try:
                            subprocess.run(audio_cmd, check=True)
                            final_segment_output = segment_with_audio
                            logger.info(f"成功为Visual片段 {segment_id} 添加音频")
                        except Exception as e:
                            logger.error(f"为Visual片段 {segment_id} 添加音频时出错: {str(e)}")
                            final_segment_output = segment_output
                    else:
                        logger.warning(f"Visual片段 {segment_id} 没有对应的音频文件或文件不存在")
                        final_segment_output = segment_output
                    
                    # 对视频进行标准化处理：先标准化尺寸，再标准化音频
                    try:
                        # 1. 尺寸标准化
                        normalized_video_path = os.path.join(temp_dir, f"normalized_size_{segment_id}.mp4")
                        final_segment_output = self.video_editing_service.normalize_video(
                            final_segment_output,
                            normalized_video_path,
                            target_width=1080,
                            target_height=1920,
                            fps=30
                        )
                        logger.info(f"Visual片段 {segment_id} 尺寸标准化完成: {final_segment_output}")
                        
                        # 2. 音频音量标准化
                        normalized_audio_path = os.path.join(temp_dir, f"normalized_audio_{segment_id}.mp4")
                        final_segment_output = self._normalize_audio(final_segment_output, normalized_audio_path)
                        logger.info(f"Visual片段 {segment_id} 音频标准化完成: {final_segment_output}")
                    except Exception as e:
                        logger.error(f"标准化Visual片段 {segment_id} 时出错: {str(e)}")
                        # 继续使用原始视频
                    
                    # 获取音频时长
                    audio_duration = None
                    for audio_segment in original_segments:
                        if str(audio_segment.get("segment_id", "")) == segment_id:
                            audio_duration = audio_segment.get("audio_duration")
                            break
                    
                    # 添加处理后的分段到列表
                    processed_video_segments.append({
                        "file_path": final_segment_output,
                        "segment_id": segment_id,
                        "text": content,
                        "duration": audio_duration if audio_duration else None,
                        "type": "visual",
                        "original_index": original_segments.index(segment)  # 记录在原始列表中的位置
                    })
            
            # 2. 按照原始片段顺序排序处理后的片段（使用在original_segments中的索引位置）
            processed_video_segments.sort(key=lambda x: x.get("original_index", 999))
            
            logger.info("按照原始素材顺序排序后的处理片段:")
            for i, segment in enumerate(processed_video_segments):
                logger.info(f"  {i+1}. {segment.get('type')} 片段 {segment.get('segment_id')} - {os.path.basename(segment.get('file_path', ''))}")
            
            if not processed_video_segments:
                logger.error("处理后没有有效的视频片段，无法生成最终视频")
                raise ValueError("没有有效的视频片段")
            
            # 3. 合并所有处理后的片段
            logger.info(f"开始合并 {len(processed_video_segments)} 个处理后的片段")
            
            # 输出文件路径
            output_file = os.path.join(self.final_dir, f"{project_name}_final.mp4")
            
            # 如果只有一个片段，直接复制
            if len(processed_video_segments) == 1:
                logger.info(f"只有一个有效片段，直接复制: {processed_video_segments[0]['file_path']} -> {output_file}")
                try:
                    import shutil
                    shutil.copy2(processed_video_segments[0]['file_path'], output_file)
                    return output_file
                except Exception as e:
                    logger.error(f"复制单个片段时出错: {str(e)}")
                    return processed_video_segments[0]['file_path']
            
            # 确保所有片段文件都存在且有效
            valid_segments = []
            for segment in processed_video_segments:
                file_path = segment['file_path']
                if os.path.exists(file_path):
                    # 验证文件包含有效的视频流
                    try:
                        cmd = [
                            'ffprobe',
                            '-v', 'error',
                            '-select_streams', 'v:0',  # 选择第一个视频流
                            '-show_entries', 'stream=codec_type',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            file_path
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0 and 'video' in result.stdout:
                            valid_segments.append(segment)
                            logger.info(f"有效的视频片段: {file_path}, 类型: {segment.get('type')}, ID: {segment.get('segment_id')}")
                        else:
                            logger.warning(f"无效的视频片段（未包含视频流）: {file_path}")
                    except Exception as e:
                        logger.error(f"检查视频片段时出错: {str(e)}")
                else:
                    logger.warning(f"片段文件不存在: {file_path}")
            
            if not valid_segments:
                logger.error("没有有效的视频片段，无法生成最终视频")
                raise ValueError("没有有效的视频片段")
            
            # 确保valid_segments保持与processed_video_segments相同的顺序
            logger.info("最终合并顺序:")
            for i, segment in enumerate(valid_segments):
                logger.info(f"  {i+1}. {segment.get('type')} 片段 {segment.get('segment_id')} - {os.path.basename(segment.get('file_path', ''))}")
            
            # 创建concat文件
            segments_file = os.path.join(temp_dir, "segments.txt")
            
            with open(segments_file, "w") as f:
                for segment in valid_segments:
                    # 使用绝对路径，并处理特殊字符
                    abs_path = os.path.abspath(segment['file_path']).replace("'", "\\'").replace("\\", "\\\\")
                    f.write(f"file '{abs_path}'\n")
            
            # 使用ffmpeg合并片段
            logger.info(f"使用concat demuxer合并 {len(valid_segments)} 个视频片段")
            
            # 修改合并命令，使用更可靠的方式处理音频
            concat_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', segments_file,
                '-fflags', '+genpts',        # 强制生成新的时间戳
                '-vsync', '1',               # 重新同步视频
                '-async', '1',               # 重新同步音频
                '-c:v', 'libx264',           # 使用libx264编码器重新编码视频
                '-c:a', 'aac',               # 使用AAC编码器统一音频编码
                '-b:a', '192k',              # 统一音频比特率
                '-ar', '48000',              # 统一音频采样率
                '-ac', '2',                  # 统一为立体声
                output_file
            ]
            
            try:
                # 执行前先检查所有片段的音频信息
                logger.info("检查所有片段的音频信息:")
                for i, segment in enumerate(valid_segments):
                    file_path = segment['file_path']
                    try:
                        probe_cmd = [
                            "ffprobe", 
                            "-v", "error", 
                            "-select_streams", "a:0", 
                            "-show_entries", "stream=codec_name,channels,sample_rate,bit_rate", 
                            "-of", "json", 
                            file_path
                        ]
                        result = subprocess.run(probe_cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            audio_info = json.loads(result.stdout)
                            logger.info(f"片段 {i+1}: {os.path.basename(file_path)} - 音频信息: {audio_info}")
                        else:
                            logger.warning(f"片段 {i+1}: {os.path.basename(file_path)} - 无法获取音频信息")
                    except Exception as e:
                        logger.error(f"检查片段 {i+1} 音频信息时出错: {str(e)}")
                
                # 执行合并命令
                process = subprocess.run(concat_cmd, capture_output=True, text=True)
                if process.returncode == 0:
                    logger.info(f"成功合并视频片段: {output_file}")
                else:
                    logger.error(f"合并失败，错误输出: {process.stderr}")
                    # 尝试备选方法 - 使用复杂的过滤器链
                    logger.info("尝试使用filter_complex方法进行合并...")
                    
                    # 构建filter_complex命令
                    complex_cmd = ['ffmpeg', '-y']
                    
                    # 添加所有输入文件
                    for segment in valid_segments:
                        complex_cmd.extend(['-i', segment['file_path']])
                    
                    # 构建filter_complex表达式
                    filter_expr = ""
                    for i in range(len(valid_segments)):
                        filter_expr += f"[{i}:v:0][{i}:a:0]"
                    
                    filter_expr += f"concat=n={len(valid_segments)}:v=1:a=1[outv][outa]"
                    
                    # 添加过滤器和输出选项
                    complex_cmd.extend([
                        '-filter_complex', filter_expr,
                        '-map', '[outv]',
                        '-map', '[outa]',
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-ar', '48000',
                        '-ac', '2',
                        output_file
                    ])
                    
                    # 执行备选命令
                    try:
                        subprocess.run(complex_cmd, check=True)
                        logger.info(f"使用filter_complex成功合并视频片段: {output_file}")
                    except Exception as e:
                        logger.error(f"使用filter_complex合并失败: {str(e)}")
                        # 如果仍然失败，使用第一个有效片段
                        logger.info(f"由于所有合并方法都失败，使用第一个有效片段作为结果: {valid_segments[0]['file_path']}")
                        return valid_segments[0]['file_path']
                
                # 为后续添加字幕做准备
                subtitle_segments = []
                current_time = 0.0
                
                for segment in valid_segments:
                    if segment.get("text"):
                        # 获取视频时长
                        try:
                            probe_cmd = [
                                "ffprobe",
                                "-v", "error",
                                "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1",
                                segment["file_path"]
                            ]
                            
                            duration = float(subprocess.check_output(probe_cmd).decode().strip())
                        except Exception as e:
                            logger.error(f"获取视频时长时出错: {str(e)}")
                            duration = segment.get("duration", 5.0)  # 使用默认值或预设的值
                        
                        subtitle_segments.append({
                            "start": current_time,
                            "end": current_time + duration,
                            "text": segment["text"]
                        })
                        
                        current_time += duration
                    else:
                        # 如果没有文本，仍需计算时长
                        try:
                            probe_cmd = [
                                "ffprobe",
                                "-v", "error",
                                "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1",
                                segment["file_path"]
                            ]
                            duration = float(subprocess.check_output(probe_cmd).decode().strip())
                            current_time += duration
                        except Exception as e:
                            logger.error(f"获取无文本视频时长时出错: {str(e)}")
                            # 使用默认值
                            current_time += segment.get("duration", 5.0)
                
                # 保存字幕信息
                subtitle_info_file = os.path.join(temp_dir, "subtitle_info.json")
                with open(subtitle_info_file, "w", encoding="utf-8") as f:
                    json.dump(subtitle_segments, f, ensure_ascii=False, indent=2)
                
                return output_file
            
            except subprocess.CalledProcessError as e:
                logger.error(f"合并视频片段失败: {e.stderr}")
                
                # 如果合并失败，使用第一个有效片段
                logger.info(f"由于合并失败，使用第一个有效片段作为结果: {valid_segments[0]['file_path']}")
                return valid_segments[0]['file_path']
                
        except Exception as e:
            logger.error(f"执行视频剪辑时出错: {str(e)}", exc_info=True)
            
            # 如果有已处理的片段，返回第一个
            if processed_video_segments:
                logger.info(f"由于错误，使用第一个处理过的片段作为结果: {processed_video_segments[0]['file_path']}")
                return processed_video_segments[0]['file_path']
            else:
                raise
    
    def _add_subtitles(self, video_path: str, processed_segments: List[Dict[str, Any]], project_name: str) -> str:
        """
        添加字幕到视频
        
        参数:
        video_path: 视频文件路径
        processed_segments: 处理后的片段列表
        project_name: 项目名称
        
        返回:
        添加字幕后的视频文件路径
        """
        temp_dir = os.path.join(self.output_dir, f"temp_{project_name}")
        subtitle_info_file = os.path.join(temp_dir, "subtitle_info.json")
        
        # 检查字幕信息文件是否存在
        if os.path.exists(subtitle_info_file):
            # 读取字幕信息
            with open(subtitle_info_file, "r", encoding="utf-8") as f:
                subtitle_segments = json.load(f)
        else:
            # 重新生成字幕信息
            subtitle_segments = []
            current_time = 0.0
            
            # 按segment_id排序
            sorted_segments = sorted(processed_segments, key=lambda x: x.get("segment_id", 0))
            
            for segment in sorted_segments:
                if "text" not in segment or not segment["text"].strip():
                    # 计算时长
                    if "audio_duration" in segment:
                        duration = segment["audio_duration"]
                    else:
                        duration = segment["end_time"] - segment["start_time"]
                    
                    current_time += duration
                    continue
                
                # 计算时长
                if "audio_duration" in segment:
                    duration = segment["audio_duration"]
                else:
                    duration = segment["end_time"] - segment["start_time"]
                
                # 获取文本
                text = segment["text"]
                
                # 计算每个字符的平均时长
                chars_count = len(text)
                time_per_char = duration / chars_count if chars_count > 0 else 0
                
                # 定义中文标点符号列表
                punctuation_marks = ['。', '！', '？', '；', '，',  '!', '?', ';', ',']
                
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
                        sub_start = current_time + last_cut * time_per_char
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
                    subtitle_segments.append({
                        "start": current_time,
                        "end": current_time + duration,
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
                    subtitle_segments.extend(final_segments)
                
                # 更新当前时间
                current_time += duration
        
        if not subtitle_segments:
            logger.warning("没有有效的字幕信息，将不添加字幕")
            return video_path
        
        # 保存字幕信息到文件，方便调试
        with open(subtitle_info_file, "w", encoding="utf-8") as f:
            json.dump(subtitle_segments, f, ensure_ascii=False, indent=2)
        
        # 生成SRT文件
        srt_file = os.path.join(self.output_dir, f"{project_name}_subtitles.srt")
        self.subtitle_tool.generate_srt_file(subtitle_segments, srt_file)
        
        # 添加字幕到视频
        output_file = os.path.join(self.final_dir, f"{project_name}_with_subtitles.mp4")
        
        try:
            result = self.subtitle_tool.add_subtitles(video_path, srt_file, output_file)
            return result
        except Exception as e:
            logger.error(f"添加字幕时出错: {str(e)}")
            return video_path
    
    def _record_token_usage(self, result: Any, step_name: str) -> None:
        """记录token使用情况"""
        if hasattr(result, 'usage') and result.usage:
            usage = result.usage
            self.token_usage_records.append({
                "step": step_name,
                "timestamp": datetime.datetime.now().isoformat(),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            })
    
    def _safe_parse_json(self, result: Any, method_name: str = "未知方法") -> Dict[str, Any]:
        """安全地解析JSON结果，处理各种错误情况"""
        try:
            # 如果已经是字典类型，直接返回
            if isinstance(result, dict):
                return result
            
            # 检查是否为CrewOutput类型（通过属性判断）
            if hasattr(result, 'json_dict') and result.json_dict is not None:
                return result.json_dict
            # elif hasattr(result, 'to_dict') and callable(result.to_dict):
            #     return result.to_dict()
            
            # 如果是字符串，尝试解析
            if isinstance(result, str):
                # 先清理结果
                cleaned_result = result.strip()  # 去除首尾空格
                cleaned_result = re.sub(r"[\x00-\x1F\x7F]", "", cleaned_result)  # 去掉非法控制字符
                
                # 查找JSON部分
                json_match = re.search(r'```json\n(.*?)\n```', cleaned_result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    return json.loads(json_str)
                else:
                    # 尝试直接解析为JSON
                    cleaned_result = re.sub(r"^```|```$", "", cleaned_result).strip()  # 去掉其他可能的代码块标记
                    return json.loads(cleaned_result)
            
            # 处理可能有raw属性的对象（如CrewOutput）
            if hasattr(result, 'raw'):
                try:
                    cleaned_raw = result.raw.strip()
                    cleaned_raw = re.sub(r"[\x00-\x1F\x7F]", "", cleaned_raw)
                    cleaned_raw = re.sub(r"^```json|^```|```$", "", cleaned_raw).strip()
                    return json.loads(cleaned_raw)
                except (json.JSONDecodeError, AttributeError):
                    # 如果raw不能解析为JSON，返回包含raw的字典
                    if isinstance(result.raw, str):
                        return {"error": "无法解析JSON", "raw_output": result.raw}
            
            # 如果都失败了，返回一个错误字典
            return {"error": "无法解析结果", "raw_output": str(result)}
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ {method_name} JSON解析失败: {e}")
            
            # 尝试从结果中提取可用的原始文本
            raw_output = str(result)
            if hasattr(result, 'raw'):
                raw_output = str(result.raw)
            elif hasattr(result, 'final_answer'):
                raw_output = str(result.final_answer)
            
            # 清理原始输出，确保是有效的字符串
            raw_output = re.sub(r"[\x00-\x1F\x7F]", "", raw_output)
            
            return {"error": f"JSON解析错误: {str(e)}", "raw_output": raw_output}
        except Exception as e:
            logger.error(f"❌ {method_name} 处理结果时出错: {e}")
            return {"error": f"处理错误: {str(e)}", "raw_output": str(result)}
