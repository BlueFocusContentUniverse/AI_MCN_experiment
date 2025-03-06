import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import datetime

from services.fish_audio_service import FishAudioService
from agents.script_analysis_agent import ScriptAnalysisAgent
from agents.material_search_agent import MaterialSearchAgent
from agents.editing_planning_agent import EditingPlanningAgent
from services.video_editing_service import VideoEditingService
from crewai import Task, Crew, Process

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
        
        # 2. 分析脚本，生成视频需求清单
        print("分析脚本，生成视频需求清单...")
        requirements = self._analyze_script(script, target_duration, style)
        
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
        audio_segments = self.fish_audio_service.generate_segments_audio(segments)
        
        return audio_segments
    
    def _analyze_script(self, script: str, target_duration: float, style: str) -> Dict[str, Any]:
        """分析脚本，生成视频需求清单"""
        # 创建脚本分析任务
        analyze_script_task = Task(
            description=f"""分析以下口播稿，生成视频需求清单：

{script}

目标视频时长：{target_duration}秒
视频风格：{style}

请详细分析每个段落需要的视觉元素、场景类型、情绪基调等。
输出应包含每个段落的具体需求，以便后续搜索匹配的视频素材。""",
            agent=self.script_analysis_agent,
            expected_output="详细的视频需求清单，包括每个段落需要的视觉元素、场景类型、情绪基调等"
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
        
        # 解析结果
        try:
            # 尝试解析JSON结果
            if isinstance(result, str):
                # 查找JSON部分
                import re
                json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    requirements = json.loads(json_str)
                else:
                    # 尝试直接解析
                    requirements = json.loads(result)
            else:
                requirements = result
                
            return requirements
        except Exception as e:
            print(f"解析脚本分析结果时出错: {e}")
            # 返回原始结果
            return {"raw_result": str(result)}
    
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
            expected_output="匹配的视频素材列表，包括每个素材的路径、基本信息和内容标签"
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
        
        # 解析结果
        try:
            # 尝试解析JSON结果
            if isinstance(result, str):
                # 查找JSON部分
                import re
                json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    materials = json.loads(json_str)
                else:
                    # 尝试直接解析
                    materials = json.loads(result)
            else:
                materials = result
                
            return materials
        except Exception as e:
            print(f"解析素材搜索结果时出错: {e}")
            # 返回原始结果
            return {"raw_result": str(result)}
    
    def _plan_editing(self, audio_segments: List[Dict[str, Any]], materials: Dict[str, Any]) -> Dict[str, Any]:
        """规划视频剪辑"""
        # 创建剪辑规划任务
        plan_editing_task = Task(
            description=f"""根据以下音频分段和可用素材，规划视频剪辑：

音频分段：
{json.dumps(audio_segments, ensure_ascii=False, indent=2)}

可用素材：
{json.dumps(materials, ensure_ascii=False, indent=2)}

请为每个音频分段选择最合适的视频素材，并规划精确的剪辑点。
输出应包含每个分段使用的素材路径、开始时间、结束时间和剪辑理由。""",
            agent=self.editing_planning_agent,
            expected_output="详细的剪辑规划，包括每个分段使用的素材和时间点"
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
        
        # 解析结果
        try:
            # 尝试解析JSON结果
            if isinstance(result, str):
                # 查找JSON部分
                import re
                json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    editing_plan = json.loads(json_str)
                else:
                    # 尝试直接解析
                    editing_plan = json.loads(result)
            else:
                editing_plan = result
            
            # 添加音频文件信息
            # 合并所有音频文件
            audio_files = [segment.get("audio_file") for segment in audio_segments if "audio_file" in segment]
            if audio_files:
                # 这里可以实现音频合并逻辑，或者直接使用第一个音频文件
                editing_plan["audio_file"] = audio_files[0]
                
            return editing_plan
        except Exception as e:
            print(f"解析剪辑规划结果时出错: {e}")
            # 返回原始结果
            return {"raw_result": str(result), "segments": []}
    
    def _execute_editing(self, editing_plan: Dict[str, Any], project_name: str) -> str:
        """执行剪辑"""
        # 最终输出文件
        output_file = os.path.join(self.final_dir, f"{project_name}.mp4")
        
        # 执行剪辑
        final_video = self.video_editing_service.execute_editing_plan(editing_plan, output_file)
        
        return final_video 