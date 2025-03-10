import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import datetime
import re

from services.fish_audio_service import FishAudioService
from agents.script_analysis_agent import ScriptAnalysisAgent
from agents.material_search_agent import MaterialSearchAgent
from agents.editing_planning_agent import EditingPlanningAgent
from services.video_editing_service import VideoEditingService
from crewai import Task, Crew, Process
from crewai.llm import LLM

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
        self.material_search_agent = MaterialSearchAgent.create()
        self.editing_planning_agent = EditingPlanningAgent.create()
        self.video_editing_service = VideoEditingService(output_dir=self.segments_dir)
        
        # self.llm = LLM(
        #     model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        #     api_key=os.environ.get('OPENAI_API_KEY'),
        #     base_url=os.environ.get('OPENAI_BASE_URL'),
        #     temperature=0.7,
        #     custom_llm_provider="openai",
        #     request_timeout=180  # 增加超时时间到180秒
        # )
    
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
    
    def produce_video(self, script: str, target_duration: float = 60.0, style: str = "汽车广告") -> Dict[str, Any]:
        """
        根据口播稿生产视频
        
        参数:
        script: 口播稿文本
        target_duration: 目标视频时长（秒）
        style: 视频风格
        
        返回:
        生产结果，包含最终视频路径和相关信息
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"video_{timestamp}"
        
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
        requirements = self._analyze_script(script, actual_duration, style)
        
        # 保存需求清单
        requirements_file = os.path.join(self.output_dir, f"{project_name}_requirements.json")
        with open(requirements_file, 'w', encoding='utf-8') as f:
            json.dump(requirements, f, ensure_ascii=False, indent=2)
        
        # 3. 搜索素材
        print("搜索匹配的视频素材...")
        materials = self._search_materials(requirements)
        
        # 保存素材信息
        materials_file = os.path.join(self.output_dir, f"{project_name}_materials.json")
        with open(materials_file, 'w', encoding='utf-8') as f:  
            json.dump(materials, f, ensure_ascii=False, indent=2)
            
        # 4. 规划剪辑
        print("规划视频剪辑...")
        editing_plan = self._plan_editing(audio_segments, materials)
        
        # 保存剪辑规划
        editing_plan_file = os.path.join(self.output_dir, f"{project_name}_editing_plan.json")
        with open(editing_plan_file, 'w', encoding='utf-8') as f:
            json.dump(editing_plan, f, ensure_ascii=False, indent=2)
        
        # 5. 执行剪辑
        print("执行视频剪辑...")
        final_video = self._execute_editing(editing_plan, project_name)
        
        # 返回结果
        result = {
            "project_name": project_name,
            "script": script,
            "audio_info": {
                "segments": audio_segments,
                "info_file": audio_info_file
            },
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
            "final_video": final_video
        }
        
        # 保存完整结果
        result_file = os.path.join(self.final_dir, f"{project_name}_result.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"视频生产完成: {final_video}")
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
    
    def _analyze_script(self, script: str, target_duration: float, style: str) -> Dict[str, Any]:
        """
        分析脚本，生成视频需求清单
        
        参数:
        script: 口播稿文本
        target_duration: 目标视频时长（秒），基于实际生成的音频时长
        style: 视频风格
        
        返回:
        视频需求清单
        """
        # 创建脚本分析任务
        analyze_script_task = Task(
            description=f"""分析以下口播稿，生成视频需求清单：

{script}

目标视频时长：{target_duration}秒（基于实际生成的音频时长）
视频风格：{style}

请详细分析每个段落需要的视觉元素、场景类型、情绪基调等。
输出应包含每个段落的具体需求，以便后续搜索匹配的视频素材。""",
            agent=self.script_analysis_agent,
            expected_output="详细的视频需求清单，包括每个段落需要的视觉元素、场景类型、情绪基调等的**严格json格式，json内禁止出现换行符！**"
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
        
        # 使用通用JSON解析方法
        return self._safe_parse_json(result, "_analyze_script")
    
    def _search_materials(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """搜索匹配的视频素材"""
        # 提取需求列表
        if "requirements" in requirements and isinstance(requirements["requirements"], list):
            req_list = requirements["requirements"]
        else:
            # 尝试从原始结果中提取
            req_list = [requirements]
        
        # 创建素材搜索任务
        search_materials_task = Task(
            description=f"""根据以下视频需求清单，搜索匹配的视频素材：

{json.dumps(req_list, ensure_ascii=False, indent=2)}

请为每个需求找到最匹配的视频素材，考虑场景类型、视觉元素、情绪基调等因素。
每个需求返回最多5个匹配的素材。""",
            agent=self.material_search_agent,
            expected_output="匹配的视频素材列表，包括每个素材的路径、基本信息和内容标签、帧分析结果的文件路径（frames_analysis_file）的**严格json格式，json内禁止出现换行符！**，不要输出任何多余信息，否则我的代码无法解析"
        )
        
        # 创建Crew并执行任务
        material_search_crew = Crew(
            agents=[self.material_search_agent],
            tasks=[search_materials_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行搜索
        result = material_search_crew.kickoff()
        
        # 使用通用JSON解析方法
        return self._safe_parse_json(result, "_search_materials")
    
    def _plan_editing(self, audio_segments: List[Dict[str, Any]], materials: Any) -> Dict[str, Any]:
        """规划视频剪辑"""
        # 简化音频分段数据，只保留必要信息
        simplified_audio_segments = []
        for segment in audio_segments:
            simplified_segment = {
                "segment_id": segment.get("segment_id", ""),
                "text": segment.get("text", ""),
                "duration": segment.get("duration", 0),
                "audio_file": segment.get("audio_file", "")
            }
            simplified_audio_segments.append(simplified_segment)
        
        # 创建剪辑规划任务，使用更简洁的描述
        plan_editing_task = Task(
            description=f"""规划视频剪辑任务：

1. 音频分段信息：
- 共有{len(simplified_audio_segments)}个音频分段
- 每个分段包含ID、文本内容和时长

2. 可用视频素材：
- 请从以下材料中提取视频信息
- 每个视频素材都有视频路径(video_path)和帧分析文件路径(frames_analysis_file)

你的任务是为每个音频分段选择最合适的视频素材，并规划剪辑点。
请使用LoadFramesAnalysisFromFile工具加载每个素材的帧分析结果，了解视频内容。

音频分段详情：
{json.dumps(simplified_audio_segments, ensure_ascii=False)}

视频素材信息：
{materials}

请确保为每个音频分段选择合适的视频片段，使视觉内容与音频内容协调一致。""",
            agent=self.editing_planning_agent,
            expected_output="""详细的剪辑规划，包括每个分段使用的素材和时间点。
请包含以下信息：
1. 每个音频分段对应的视频素材路径
2. 视频的开始和结束时间点
3. 选择该片段的理由
4. 每段口播需要多段素材(每条素材2-10秒）进行组合剪辑呈现效果，适用于短视频平台
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
        
        # 执行规划，添加重试机制
        max_retries = 3
        retry_delay = 2  # 秒
        result = None
        
        for attempt in range(max_retries):
            try:
                # 执行规划
                result = editing_planning_crew.kickoff()
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
                        # 为每个音频分段创建一个基本的编辑计划项
                        for i, segment in enumerate(simplified_audio_segments):
                            # 尝试从材料中获取第一个可用的视频
                            video_path = "placeholder.mp4"  # 默认占位符
                            try:
                                # 尝试从materials中提取第一个视频路径
                                if isinstance(materials, dict) and "materials" in materials:
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
            "audio_segments": simplified_audio_segments
        }
        
        # 如果result是字典且已包含segments，直接使用
        if isinstance(result, dict) and "segments" in result:
            editing_plan["segments"] = result["segments"]
            if "error" in result:
                editing_plan["error"] = result["error"]
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
                    segment = {
                        "segment_id": segment_id,
                        "video_path": video_path,
                        "start_time": float(start_time),
                        "end_time": float(end_time),
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
        
        return editing_plan
    
    def _execute_editing(self, editing_plan: Dict[str, Any], project_name: str) -> str:
        """执行剪辑"""
        # 最终输出文件
        output_file = os.path.join(self.final_dir, f"{project_name}.mp4")
        
        # 执行剪辑
        final_video = self.video_editing_service.execute_editing_plan(editing_plan, output_file)
        
        return final_video 