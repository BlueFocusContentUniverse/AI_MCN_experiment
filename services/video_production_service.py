import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import datetime
import re
import subprocess
import platform
import traceback
import shutil
import time

from services.fish_audio_service import FishAudioService
from agents.script_analysis_agent import ScriptAnalysisAgent
from agents.material_search_agent import MaterialSearchAgent
from agents.editing_planning_agent import EditingPlanningAgent
from services.video_editing_service import VideoEditingService
from tools.subtitle_tool import SubtitleTool
from crewai import Task, Crew, Process
from crewai.llm import LLM
from services.material_matching_service import MaterialMatchingService

class VideoProductionService:
    """视频生产服务，整合口播稿、音频生成和视频剪辑"""
    
    def __init__(self, output_dir: str = "./output"):
        """
        初始化视频生产服务
        
        参数:
        output_dir: 输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建子目录
        self.audio_dir = os.path.join(output_dir, "audio")
        self.segments_dir = os.path.join(output_dir, "segments")
        self.final_dir = os.path.join(output_dir, "final")
        
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.segments_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        
        # 初始化服务和Agent
        self.fish_audio_service = FishAudioService(audio_output_dir=self.audio_dir)
        self.script_analysis_agent = ScriptAnalysisAgent.create()
        self.material_search_agent = self._init_material_search_agent()
        self.editing_planning_agent = EditingPlanningAgent.create()
        self.video_editing_service = VideoEditingService(output_dir=self.segments_dir)
        
        # 初始化字幕工具
        self.subtitle_tool = SubtitleTool()
        
        # 添加token使用记录
        self.token_usage_records = []
        
        # self.llm = LLM(
        #     model="gemini-1.5-pro",
        #     api_key=os.environ.get('OPENAI_API_KEY'),
        #     base_url=os.environ.get('OPENAI_BASE_URL'),
        #     temperature=0.7,
        #     custom_llm_provider="openai",
        #     request_timeout=180  # 增加超时时间到180秒
        # )
        
        self.material_matcher = MaterialMatchingService()
    
    def _safe_parse_json(self, result: Any, method_name: str = "未知方法") -> Dict[str, Any]:
        """
        安全地解析JSON结果，处理各种错误情况
        
        参数:
        result: 需要解析的结果
        method_name: 调用方法名称，用于日志
        
        返回:
        解析后的字典或包含原始结果的错误字典
        """
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
                # cleaned_result = result.strip()  # 去除首尾空格
                # cleaned_result = re.sub(r"[\x00-\x1F\x7F]", "", cleaned_result)  # 去掉非法控制字符
                
                # 查找JSON部分
                json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    return json.loads(json_str)
                else:
                    # 尝试直接解析为JSON
                    cleaned_result = re.sub(r"^```|```$", "", result).strip()  # 去掉其他可能的代码块标记
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
            print(f"❌ {method_name} JSON解析失败: {e}")
            
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
            print(f"❌ {method_name} 处理结果时出错: {e}")
            return {"error": f"处理错误: {str(e)}", "raw_output": str(result)}
    
    def _record_token_usage(self, result, task_name: str):
        """
        记录CrewOutput中的token_usage信息
        
        参数:
        result: CrewOutput对象
        task_name: 任务名称
        """
        try:
            # 检查result是否有token_usage属性
            if hasattr(result, 'token_usage') and result.token_usage:
                usage_record = {
                    "task_name": task_name,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "token_usage": result.token_usage
                }
                
                # 将字典转换为可序列化的格式
                if isinstance(usage_record["token_usage"], dict):
                    # 已经是字典，不需要转换
                    pass
                else:
                    # 尝试转换为字典
                    try:
                        usage_record["token_usage"] = usage_record["token_usage"].dict()
                    except AttributeError:
                        # 如果没有dict方法，尝试使用__dict__
                        usage_record["token_usage"] = vars(usage_record["token_usage"])
                
                # 添加到记录列表
                self.token_usage_records.append(usage_record)
                print(f"已记录 {task_name} 的token使用情况: {usage_record['token_usage']}")
            else:
                print(f"警告: {task_name} 的结果中没有token_usage信息")
        except Exception as e:
            print(f"记录token使用情况时出错: {str(e)}")
    
    def produce_video(self, script: str, target_duration: float = 60.0, style: str = "短视频", 
                    special_requirements: str = "", script_type: str = "voiceover") -> Dict[str, Any]:
        """
        根据脚本生产视频
        
        参数:
        script: 脚本文本
        target_duration: 目标视频时长（秒）
        style: 视频风格
        special_requirements: 特殊需求，将添加到任务描述中
        script_type: 脚本类型，"voiceover"表示口播稿，"visual"表示纯视觉脚本
        
        返回:
        生产结果，包含最终视频路径和相关信息
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"video_{timestamp}"
        
        # 根据脚本类型选择不同的处理路径
        if script_type == "voiceover":
            # 1. 生成音频
            print("生成语音...")
            audio_segments = self._generate_audio_segments(script)
            
            # 保存音频分段信息
            audio_info_file = os.path.join(self.audio_dir, f"{project_name}_audio_info.json")
            self.fish_audio_service.save_segments_info(audio_segments, audio_info_file)
            
            # 计算实际音频总时长
            actual_duration = sum(segment.get("duration", 0) for segment in audio_segments if "duration" in segment)
            print(f"实际音频总时长: {actual_duration:.2f}秒")
            
            # 2. 分析脚本，使用实际音频时长作为目标时长
            print("分析脚本，生成视频需求清单...")
            requirements = self._analyze_script(script, actual_duration, style, special_requirements)
            
            has_audio = True
        else:  # script_type == "visual"
            # 处理纯视觉脚本
            print("解析视觉脚本...")
            segments = self._parse_visual_script(script, target_duration, style)
            
            # 使用解析结果作为需求
            requirements = {
                "requirements": segments
            }
            
            # 创建虚拟音频分段（无实际音频）
            audio_segments = []
            for segment in segments:
                audio_segment = {
                    "segment_id": segment.get("segment_id", 0),
                    "text": segment.get("content", ""),
                    "duration": segment.get("duration", 0),
                    "start_time": segment.get("start_time", 0),
                    "end_time": segment.get("end_time", 0),
                    "audio_file": None  # 无实际音频文件
                }
                audio_segments.append(audio_segment)
                
            audio_info_file = None  # 无音频文件信息
            has_audio = False
        
        # 保存需求清单
        requirements_file = os.path.join(self.output_dir, f"{project_name}_requirements.json")
        with open(requirements_file, 'w', encoding='utf-8') as f:
            json.dump(requirements, f, ensure_ascii=False, indent=2)
        
        # 3. 搜索素材
        print("搜索匹配的视频素材...")
        materials = self._search_materials(requirements, special_requirements)
        
        # 保存素材信息
        materials_file = os.path.join(self.output_dir, f"{project_name}_materials.json")
        with open(materials_file, 'w', encoding='utf-8') as f:  
            json.dump(materials, f, ensure_ascii=False, indent=2)
            
        # 4. 规划剪辑
        print("规划视频剪辑...")
        editing_plan = self._plan_editing(audio_segments, materials, special_requirements, has_audio=has_audio)
        
        # 保存剪辑规划
        editing_plan_file = os.path.join(self.output_dir, f"{project_name}_editing_plan.json")
        with open(editing_plan_file, 'w', encoding='utf-8') as f:
            json.dump(editing_plan, f, ensure_ascii=False, indent=2)
        
        # 5. 执行剪辑
        print("执行视频剪辑...")
        final_video = self._execute_editing(editing_plan, project_name)
        
        # 6. 仅在有音频的情况下考虑添加字幕
        if has_audio:
            # 添加字幕（当前注释掉）
            # final_video_with_subtitles = self._add_subtitles_to_video(final_video, project_name)
            final_video_with_subtitles = final_video
        else:
            final_video_with_subtitles = final_video
        
        # 构建结果，根据不同脚本类型调整结构
        result = {
            "project_name": project_name,
            "script": script,
            "script_type": script_type,
            "requirements": {
                "data": requirements,
                "file": requirements_file
            },
            "materials": {
                "data": materials,
                "file": materials_file
            },
            "editing_plan": {
                "data": editing_plan,
                "file": editing_plan_file
            },
            "final_video": final_video_with_subtitles,
            "token_usage_records": self.token_usage_records  # 添加token使用记录
        }
        
        # 仅在有音频情况下添加音频信息
        if has_audio:
            result["audio_info"] = {
                "segments": audio_segments,
                "info_file": audio_info_file
            }
        
        # 保存完整结果
        result_file = os.path.join(self.final_dir, f"{project_name}_result.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 保存token使用记录到单独的文件
        token_usage_file = os.path.join(self.final_dir, f"{project_name}_token_usage.json")
        with open(token_usage_file, 'w', encoding='utf-8') as f:
            json.dump(self.token_usage_records, f, ensure_ascii=False, indent=2)
        
        print(f"视频生产完成: {final_video_with_subtitles}")
        return result
    
    def _generate_audio_segments(self, script: str) -> List[Dict[str, Any]]:
        """生成音频分段"""
        # 简单分段处理，可以根据实际需求扩展
        segments = []
        
        # 按段落分割
        paragraphs = [p.strip() for p in script.split('\n') if p.strip()]
        
        for i, paragraph in enumerate(paragraphs):
            segments.append({
                "segment_id": i + 1,
                "text": paragraph
            })
        
        # 生成音频
        audio_segments = self.fish_audio_service.generate_audio_segments(segments)
        
        return audio_segments
    
    def _analyze_script(self, script: str, target_duration: float, style: str, special_requirements: str = "") -> Dict[str, Any]:
        """
        分析脚本，生成视频需求清单
        
        参数:
        script: 口播稿文本
        target_duration: 目标视频时长（秒），基于实际生成的音频时长
        style: 视频风格
        special_requirements: 特殊需求，将添加到任务描述中
        
        返回:
        视频需求清单
        """
        # 添加特殊需求到描述中
        special_req_text = f"\n\n特殊需求: {special_requirements}" if special_requirements else ""
        
        # 创建脚本分析任务
        analyze_script_task = Task(
            description=f"""分析以下口播稿，生成视频需求清单：

{script}

目标视频时长：{target_duration}秒（基于实际生成的音频时长）
视频风格：{style}{special_req_text}

请详细分析每个段落需要的视觉元素、场景类型、情绪基调等。
输出应包含每个段落的具体需求，以便后续搜索匹配的视频素材。""",
            agent=self.script_analysis_agent,
            expected_output="""详细的视频需求清单，包括每个段落需要的视觉元素、场景类型、情绪基调等的**严格json格式，json内禁止出现换行符！**
            输出为json格式以便下一个Agent可以拿到结果并处理，json内禁止出现换行符！
            输出格式{
                "requirements": [
                    {
                        "segment_id": "1",
                        "text": "段落文本",
                        "visual_elements": "视觉元素",
                        "scene_type": "场景类型",
                        "description": "描述"
                    }
                ]
            }""",

        )
        
        # 创建Crew并执行任务
        script_analysis_crew = Crew(
            agents=[self.script_analysis_agent],
            tasks=[analyze_script_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行分析
        result = script_analysis_crew.kickoff()
        
        # 记录token使用情况
        self._record_token_usage(result, "脚本分析")
        
        # 使用通用JSON解析方法
        return self._safe_parse_json(result, "_analyze_script")
    
    def _init_material_search_agent(self):
        """初始化素材搜索Agent的占位符方法（已不再使用Agent，改为直接调用Tool）"""
        print("素材搜索已切换为直接工具调用，不再使用Agent...")
        # 返回None，因为在搜索函数中我们不再使用这个agent
        return None
    
    def _search_materials(self, requirements: Dict[str, Any], special_requirements: str = "") -> Dict[str, Any]:
        """搜索匹配的视频素材"""
        print("\n" + "="*50)
        print("开始执行素材搜索...")
        
        # 提取需求列表
        if "requirements" in requirements and isinstance(requirements["requirements"], list):
            req_list = requirements["requirements"]
        else:
            # 尝试从原始结果中提取
            req_list = [requirements]
        
        print(f"共有 {len(req_list)} 个需求项需要搜索匹配素材")
        
        try:
            print("直接使用MaterialSearchTool搜索素材...")
            start_time = time.time()
            
            # 设置环境变量用于故障排除，确保在数据库搜索失败时提供备选方案
            if 'ENABLE_MOCK_DATA' not in os.environ:
                os.environ['ENABLE_MOCK_DATA'] = 'true'
                print("已启用示例数据功能，用于数据库搜索失败时提供备选方案")
            
            # 初始化MaterialSearchTool
            from agents.material_search_agent import MaterialSearchTool
            material_search_tool = MaterialSearchTool()
            
            # 设置每个需求的素材数量限制
            limit_per_requirement = 2
            
            # 特殊需求处理 - 添加到需求描述中
            if special_requirements:
                for req in req_list:
                    if "description" in req:
                        req["description"] = f"{req['description']} ({special_requirements})"
                    else:
                        req["description"] = special_requirements
            
            # 直接调用MaterialSearchTool的_run方法
            result = material_search_tool._run(
                requirements=req_list,
                limit_per_requirement=limit_per_requirement
            )
            
            duration = time.time() - start_time
            print(f"素材搜索完成，耗时 {duration:.2f} 秒")
            
            print(f"解析结果: 找到 {len(result.get('results', []))} 个匹配结果")
            print("="*50 + "\n")
            
            return result
            
        except Exception as e:
            print(f"素材搜索出错: {str(e)}")
            print(traceback.format_exc())
            print("="*50 + "\n")
            
            # 返回空结果
            return {
                "error": f"素材搜索出错: {str(e)}",
                "requirements_count": len(req_list),
                "results": []
            }
    
    def _parse_visual_script(self, script: str, target_duration: float, style: str) -> List[Dict[str, Any]]:
        """
        解析纯视觉脚本，生成场景分段
        
        参数:
        script: 视觉脚本文本
        target_duration: 目标视频时长（秒）
        style: 视频风格
        
        返回:
        场景分段列表
        """
        from agents.script_parsing_agent import ScriptParsingAgent
        
        # 创建脚本解析任务
        parse_script_task = Task(
            description=f"""解析以下视频脚本，识别场景并分配时长：

{script}

目标总时长：{target_duration}秒
视频风格：{style}

请将脚本分解为独立场景，并为每个场景分配合理的时长，确保总时长接近目标时长。
请详细描述每个场景的视觉需求、情感基调和场景类型。""",
            agent=ScriptParsingAgent.create(),
            expected_output="""JSON格式的场景分段列表，包含每个场景的描述、时长和视觉需求，**严格json格式，包裹在json代码块中，json内禁止出现换行符！**禁止输出其他信息
            output format：
            ```json
            {
                "segments": [
                    {
                        "segment_id": "1",
                        "content": "场景描述内容",
                        "text": "场景内容文本",
                        "description": "详细场景描述",
                        "start_time": 0, 
                        "end_time": 10, 
                        "duration": 10,
                        "emotion": "场景情感基调",
                        "scene_type": "场景类型（产品展示/功能演示/场景氛围等）"
                    }
                ]
            }
            ```
            """
        )
        
        # 创建Crew并执行任务
        script_parsing_crew = Crew(
            agents=[ScriptParsingAgent.create()],
            tasks=[parse_script_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行解析
        result = script_parsing_crew.kickoff()
        output_text = str(result).strip()

        
        # 记录token使用情况
        self._record_token_usage(result, "视觉脚本解析")
        
        # 使用通用JSON解析方法
        parsed_result = self._safe_parse_json(output_text, "_parse_visual_script")
        # 提取分段
        segments = []
        if "segments" in parsed_result:
            segments = parsed_result["segments"]
            
            # 为每个分段添加requirements格式需要的字段
            for segment in segments:
                # 确保有segment_id
                if "segment_id" not in segment:
                    segment["segment_id"] = len(segments)
                    
                # 将content转换为text
                if "content" in segment and "text" not in segment:
                    segment["text"] = segment["content"]
                elif "text" in segment and "content" not in segment:
                    segment["content"] = segment["text"]
                    
                # 处理视觉元素
                if "visual_elements" in segment and isinstance(segment["visual_elements"], list):
                    segment["visual_elements"] = ", ".join(segment["visual_elements"])
                    
                # 确保有描述字段
                if "description" not in segment:
                    segment["description"] = segment.get("content", "")
                    
                # 确保有场景类型
                if "scene_type" not in segment:
                    segment["scene_type"] = segment.get("scene_type", "未知")
        
        return segments
        
    def _plan_editing(self, audio_segments: List[Dict[str, Any]], materials: Any, special_requirements: str = "", has_audio: bool = True) -> Dict[str, Any]:
        """
        规划视频剪辑
        
        参数:
        audio_segments: 音频分段数据（或虚拟分段数据）
        materials: 视频素材信息
        special_requirements: 特殊需求
        has_audio: 是否包含实际音频
        
        返回:
        剪辑规划
        """
        # 简化分段数据，保留必要信息
        simplified_segments = []
        for segment in audio_segments:
            simplified_segment = {
                "segment_id": segment.get("segment_id", ""),
                "text": segment.get("text", ""),
                "duration": segment.get("duration", 0),
                "audio_file": segment.get("audio_file", "")
            }
            simplified_segments.append(simplified_segment)
        
        # 添加特殊需求和音频标志到描述中
        special_req_text = f"\n\n特殊需求: {special_requirements}" if special_requirements else ""
        audio_flag_text = "" if has_audio else "\n\n注意：此视频没有对应音频，请仅安排视觉内容的剪辑顺序和时长。"
        
        # 创建剪辑规划任务，根据是否有音频调整描述
        plan_editing_task = Task(
            description=f"""规划视频剪辑任务：

1. {'音频' if has_audio else '场景'}分段信息：
- 共有{len(simplified_segments)}个{'音频' if has_audio else '场景'}分段
- 每个分段包含ID、{'文本内容' if has_audio else '场景描述'}和时长

2. 可用视频素材：
- 请从以下材料中提取视频信息
- 每个视频素材包含路径 (video_path) 和相关的片段信息 (来自 video_segment 表)。

你的任务是为每个{'音频' if has_audio else '场景'}分段选择最合适的视频素材，并规划剪辑点。
视频素材信息已经包含了必要的场景、内容描述，请直接利用这些信息进行规划。{special_req_text}{audio_flag_text}

{'音频' if has_audio else '场景'}分段详情：
{json.dumps(simplified_segments, ensure_ascii=False)}

视频素材信息：
{materials}

请确保为每个分段选择合适的视频片段，{'使视觉内容与音频内容协调一致' if has_audio else '按照场景要求匹配适当的视频内容'}。""",
            agent=self.editing_planning_agent,
            expected_output="""详细的剪辑规划，包括每个分段使用的素材和时间点。
请包含以下信息：
1. 每个分段对应的视频素材路径
2. 视频的开始和结束时间点
3. 选择该片段的理由
4. 每段内容需要多段素材(**每条素材必须长于2秒！！！**)进行组合剪辑呈现效果，但如果内容较少（不超过6秒），则只需要一条素材即可。
5. 不同场景节奏不同，请根据内容节奏进行剪辑，不要给用户带来不好的观感。
6. 请确保剪辑视频的连贯性和流畅性，不要给用户带来不好的观感。
7. 禁止使用重复的素材片段，在选取素材时，注意素材在视频中的位置，比如说越靠近结束的素材越适合放在视频末尾，开头时间段的素材往往适合放在开头。
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
        }
    ]
}，请务必按照**output format**输出，不要输出任何多余信息，否则我的代码无法解析，**output format**内禁止出现换行符！视频素材总时长必须匹配分段总时长！！！"""
        )
        
        # 创建Crew并执行任务
        editing_planning_crew = Crew(
            agents=[self.editing_planning_agent],
            tasks=[plan_editing_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行规划，添加重试机制
        max_retries = 3
        retry_delay = 2  # 秒
        result = None
        
        for attempt in range(max_retries):
            try:
                # 执行规划
                result = editing_planning_crew.kickoff()
                
                # 记录token使用情况
                self._record_token_usage(result, "剪辑规划")
                
                # 如果成功，跳出循环
                break
            except ValueError as e:
                # 检查是否是空响应错误
                if "Invalid response from LLM call - None or empty" in str(e):
                    print(f"⚠️ LLM返回空响应，尝试 {attempt + 1}/{max_retries}。等待 {retry_delay} 秒后重试...")
                    if attempt < max_retries - 1:  # 如果不是最后一次尝试
                        import time
                        time.sleep(retry_delay)
                    else:
                        print("❌ 多次尝试后仍然失败，将使用基本编辑计划。")
                        # 创建一个基本的编辑计划
                        result = {
                            "segments": [],
                            "error": "LLM多次返回空响应，无法生成编辑计划"
                        }
                        # 为每个分段创建一个基本的编辑计划项
                        for i, segment in enumerate(simplified_segments):
                            # 尝试从材料中获取第一个可用的视频
                            video_path = "placeholder.mp4"  # 默认占位符
                            try:
                                # 尝试从materials中提取第一个视频路径
                                if isinstance(materials, dict):
                                    # 尝试从results中提取
                                    if "results" in materials:
                                        for result in materials["results"]:
                                            if "matching_videos" in result and len(result["matching_videos"]) > 0:
                                                first_video = result["matching_videos"][0]
                                                if "video_path" in first_video:
                                                    video_path = first_video["video_path"]
                                                    break
                                # 尝试从materials中提取
                                elif "materials" in materials:
                                    if isinstance(materials["materials"], list) and len(materials["materials"]) > 0:
                                        first_material = materials["materials"][0]
                                        if "video_path" in first_material:
                                            video_path = first_material["video_path"]
                            except Exception:
                                pass  # 如果提取失败，使用默认占位符
                                
                            result["segments"].append({
                                "segment_id": str(segment.get("segment_id", i+1)),
                                "video_path": video_path,
                                "start_time": 0.0,
                                "end_time": segment.get("duration", 10.0),
                                "reason": "由于LLM响应失败，自动生成的基本编辑计划"
                            })
                else:
                    # 如果是其他错误，记录并重新抛出
                    print(f"❌ 执行编辑规划时出错: {str(e)}")
                    raise
        
        # 处理结果
        raw_output = ""
        if result:
            if hasattr(result, 'raw'):
                raw_output = result.raw
            else:
                raw_output = str(result)
        
        # 创建基本结构
        editing_plan = {
            "segments": [],
            "audio_segments": simplified_segments if has_audio else []
        }
        
        # 如果result是字典且已包含segments，直接使用
        if isinstance(result, dict) and "segments" in result:
            editing_plan["segments"] = result["segments"]
            if "error" in result:
                editing_plan["error"] = result["error"]
            # 修改字段名称
            for segment in editing_plan["segments"]:
                if "start_time" in segment and "video_start_time" not in segment:
                    segment["video_start_time"] = segment["start_time"]
                if "end_time" in segment and "video_end_time" not in segment:
                    segment["video_end_time"] = segment["end_time"]
            return editing_plan
        
        # 尝试解析JSON部分
        try:
            # 尝试多种模式匹配JSON
            json_patterns = [
                r'```json\n(.*?)\n```',  # 标准JSON代码块
                r'```\n(.*?)\n```',       # 无语言标识的代码块
                r'{[\s\S]*?"segments"[\s\S]*?}',  # 直接查找包含segments的JSON对象
            ]
            
            parsed_data = None
            for pattern in json_patterns:
                json_match = re.search(pattern, raw_output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1) if '(' in pattern else json_match.group(0)
                    try:
                        parsed_data = json.loads(json_str)
                        if "segments" in parsed_data:
                            editing_plan["segments"] = parsed_data["segments"]
                            print(f"成功从模式 {pattern} 提取到 {len(parsed_data['segments'])} 个分段")
                            break
                    except Exception as e:
                        print(f"解析模式 {pattern} 失败: {str(e)}")
                        continue
            
            # 如果上述方法都失败，尝试提取所有可能的JSON对象
            if not parsed_data or "segments" not in parsed_data or not editing_plan["segments"]:
                print("尝试提取所有可能的JSON对象...")
                # 查找所有可能的JSON对象
                potential_jsons = re.findall(r'{.*?}', raw_output, re.DOTALL)
                for json_str in potential_jsons:
                    try:
                        data = json.loads(json_str)
                        if "segments" in data:
                            editing_plan["segments"] = data["segments"]
                            print(f"从潜在JSON对象中提取到 {len(data['segments'])} 个分段")
                            break
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"JSON解析过程中出错: {str(e)}")
        
        # 如果仍然没有提取到segments，尝试手动解析
        if not editing_plan["segments"]:
            print("尝试手动解析输出...")
            # 保存原始输出
            editing_plan["raw_output"] = raw_output
            
            # 尝试查找segment_id、video_path、start_time和end_time模式
            segment_pattern = r'"segment_id"\s*:\s*"?(\d+)"?,\s*"video_path"\s*:\s*"([^"]+)",\s*"start_time"\s*:\s*(\d+\.?\d*),\s*"end_time"\s*:\s*(\d+\.?\d*)'
            segment_matches = re.findall(segment_pattern, raw_output)
            
            if segment_matches:
                print(f"通过正则表达式找到 {len(segment_matches)} 个分段")
                for match in segment_matches:
                    segment_id, video_path, start_time, end_time = match
                    # 创建同时具有start_time/end_time和video_start_time/video_end_time字段的分段
                    start_time_float = float(start_time)
                    end_time_float = float(end_time)
                    segment = {
                        "segment_id": segment_id,
                        "video_path": video_path,
                        "start_time": start_time_float,
                        "end_time": end_time_float,
                        "video_start_time": start_time_float,  # 添加video_start_time字段
                        "video_end_time": end_time_float,      # 添加video_end_time字段
                        "reason": "通过正则表达式提取，无理由信息"
                    }
                    editing_plan["segments"].append(segment)
        
        # 如果仍然没有segments，打印警告
        if not editing_plan["segments"]:
            print("警告: 无法从输出中提取segments信息")
            print("原始输出前200个字符:")
            print(raw_output[:200])
        else:
            print(f"最终提取到 {len(editing_plan['segments'])} 个分段")
        
        # 为所有分段添加video_start_time和video_end_time字段
        for segment in editing_plan["segments"]:
            if "start_time" in segment and "video_start_time" not in segment:
                segment["video_start_time"] = segment["start_time"]
            if "end_time" in segment and "video_end_time" not in segment:
                segment["video_end_time"] = segment["end_time"]
        
        return editing_plan
    
    def _execute_editing(self, editing_plan: Dict[str, Any], project_name: str) -> str:
        """执行剪辑"""
        # 最终输出文件
        output_file = os.path.join(self.final_dir, f"{project_name}.mp4")
        
        # 验证编辑计划
        if "segments" not in editing_plan or not editing_plan["segments"]:
            print("警告: 编辑计划中没有分段，创建空视频")
            # 创建一个简单的空视频
            from moviepy.editor import ColorClip
            color_clip = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=3)
            color_clip.write_videofile(output_file, fps=30)
            return output_file
        
        # 验证所有分段是否包含必要的字段
        for segment in editing_plan["segments"]:
            # 确保segment_id和video_path存在
            if "segment_id" not in segment:
                segment["segment_id"] = "unknown"
            if "video_path" not in segment:
                print(f"警告: 分段 {segment.get('segment_id', 'unknown')} 缺少video_path字段")
                continue
                
            # 确保有视频开始和结束时间
            if "video_start_time" not in segment:
                if "start_time" in segment:
                    segment["video_start_time"] = segment["start_time"]
                else:
                    segment["video_start_time"] = 0.0
                    print(f"警告: 为分段 {segment.get('segment_id', 'unknown')} 添加默认video_start_time=0.0")
                    
            if "video_end_time" not in segment:
                if "end_time" in segment:
                    segment["video_end_time"] = segment["end_time"]
                else:
                    # 尝试获取视频时长
                    try:
                        from moviepy.editor import VideoFileClip
                        clip = VideoFileClip(segment["video_path"])
                        segment["video_end_time"] = clip.duration
                        clip.close()
                        print(f"警告: 为分段 {segment.get('segment_id', 'unknown')} 添加从视频获取的默认video_end_time={segment['video_end_time']}")
                    except Exception as e:
                        segment["video_end_time"] = 10.0  # 默认10秒
                        print(f"警告: 为分段 {segment.get('segment_id', 'unknown')} 添加默认video_end_time=10.0")
        
        # 执行剪辑
        final_video = self.video_editing_service.execute_editing_plan(editing_plan, output_file)
        
        return final_video
    
    def _add_subtitles_to_video(self, video_file: str, project_name: str) -> str:
        """
        为视频添加字幕
        
        参数:
        video_file: 视频文件路径
        project_name: 项目名称
        
        返回:
        添加字幕后的视频文件路径
        """
        try:
            print("开始处理音频并添加字幕...")
            
            # 设置输出文件名
            output_filename = f"{project_name}_with_subtitles"
            
            # 使用SubtitleTool处理视频并添加字幕
            final_video = self.subtitle_tool.process_video_with_subtitles(
                video_file=video_file,
                output_dir=self.final_dir,
                output_filename=output_filename
            )
            
            return final_video
            
        except Exception as e:
            print(f"添加字幕时出错: {str(e)}")
            traceback.print_exc()  # 打印详细的错误堆栈
            # 如果出错，返回原始视频
            return video_file

    def match_script_to_materials(self, script: str) -> dict:
        """
        将脚本匹配到可用的视频素材，使用基于向量搜索的智能匹配
        
        参数:
        script: 脚本文本
        
        返回:
        匹配结果，包含分镜表和每个场景的匹配片段
        """
        try:
            # 使用智能匹配服务执行匹配
            match_results = self.material_matcher.match_script_to_video(script)
            return match_results
        except Exception as e:
            logger.error(f"匹配脚本到素材时出错: {str(e)}")
            raise


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
            import httpx
            import ormsgpack
            
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