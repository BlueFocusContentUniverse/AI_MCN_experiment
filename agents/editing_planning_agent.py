from crewai import Agent, LLM
from typing import Type, List, Dict, Any, Union, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
from tools.vision_analysis_enhanced import LoadFramesAnalysisFromFileTool


class EditingPlanInput(BaseModel):
    """剪辑规划工具的输入模式"""
    segments: List[Dict[str, Any]] = Field(..., description="分段列表，可能是口播稿分段或视觉场景分段，每个分段包含文本/描述和时长")
    available_materials: Union[List[Dict[str, Any]], Dict[str, Any]] = Field(..., description="可用的视频素材列表或包含素材的字典")
    has_audio: bool = Field(True, description="是否有音频，True表示有口播，False表示纯视觉脚本")

class EditingPlanTool(BaseTool):
    name: str = "EditingPlan"
    description: str = "规划视频剪辑，为每个分段选择合适的视频素材"
    args_schema: Type[BaseModel] = EditingPlanInput
    
    def _run(self, segments: List[Dict[str, Any]], available_materials: Union[List[Dict[str, Any]], Dict[str, Any]], 
             has_audio: bool = True) -> dict:
        """
        规划视频剪辑，为每个分段选择合适的视频素材
        
        参数:
        segments: 分段列表，可能是口播稿分段或视觉场景分段
        available_materials: 可用的视频素材列表或包含素材的字典
        has_audio: 是否有音频，True表示有口播，False表示纯视觉脚本
        
        返回:
        剪辑规划，包括每个分段使用的素材和时间点
        """
        # 提取素材中的视频信息
        video_materials = []
        
        # 处理不同格式的素材数据
        if isinstance(available_materials, list):
            # 如果是列表，直接处理
            for material in available_materials:
                if isinstance(material, dict) and "video_path" in material:
                    video_materials.append({
                        "video_path": material.get("video_path", ""),
                        "similarity_score": material.get("similarity_score", 0),
                        "requirement": material.get("requirement", ""),
                        "shot_type": material.get("shot_type", ""),
                        "description": material.get("description", ""),
                        "duration": material.get("duration", 0),
                        "start_time": material.get("start_time", 0),
                        "end_time": material.get("end_time", 0)
                    })
        elif isinstance(available_materials, dict):
            # 如果是字典，尝试提取视频信息
            if "results" in available_materials:
                for result in available_materials.get("results", []):
                    # 对于material_search_agent返回的结构处理
                    if "matching_videos" in result and isinstance(result["matching_videos"], list):
                        for video in result["matching_videos"]:
                            # 检查是否有segments信息（从material_search_agent返回的结构）
                            if "segments" in video and isinstance(video["segments"], list):
                                for segment in video.get("segments", []):
                                    video_materials.append({
                                        "video_path": video.get("video_path", "") or video.get("_id", ""),
                                        "start_time": segment.get("start_time", 0),
                                        "end_time": segment.get("end_time", 0),
                                        "duration": segment.get("duration", 0),
                                        "shot_type": segment.get("shot_type", ""),
                                        "description": segment.get("description", ""),
                                        "match_reason": segment.get("match_reason", ""),
                                        "similarity_score": video.get("similarity_score", 0),
                                        "requirement": result.get("requirement", {}).get("description", "")
                                    })
                            else:
                                # 旧格式：视频本身是一个片段
                                video_materials.append({
                                    "video_path": video.get("video_path", ""),
                                    "similarity_score": video.get("similarity_score", 0),
                                    "requirement": result.get("requirement", {}).get("description", ""),
                                    "shot_type": video.get("shot_type", ""),
                                    "description": video.get("shot_description", "")
                                })
                    # 同时也处理直接包含视频信息的情况
                    elif "video_path" in result:
                        video_materials.append({
                            "video_path": result.get("video_path", ""),
                            "similarity_score": result.get("similarity_score", 0),
                            "requirement": result.get("requirement", {}).get("description", ""),
                            "shot_type": result.get("shot_type", ""),
                            "description": result.get("description", "")
                        })
            elif "matching_videos" in available_materials:
                for video in available_materials.get("matching_videos", []):
                    if "segments" in video:
                        # 新格式
                        for segment in video.get("segments", []):
                            video_materials.append({
                                "video_path": video.get("video_path", "") or video.get("file_path", ""),
                                "start_time": segment.get("start_time", 0),
                                "end_time": segment.get("end_time", 0),
                                "duration": segment.get("duration", 0),
                                "shot_type": segment.get("shot_type", ""),
                                "description": segment.get("description", ""),
                                "match_reason": segment.get("match_reason", ""),
                                "similarity_score": video.get("similarity_score", 0)
                            })
                    else:
                        # 旧格式
                        video_materials.append({
                            "video_path": video.get("video_path", ""),
                            "similarity_score": video.get("similarity_score", 0),
                            "shot_type": video.get("shot_type", ""),
                            "description": video.get("description", "")
                        })
            # 直接检查是否为示例数据格式
            elif "requirements_count" in available_materials and "results" in available_materials:
                print("检测到原始查询结果结构，尝试提取视频素材...")
                # 特殊处理JSON示例数据格式
                try:
                    for result in available_materials.get("results", []):
                        req_id = result.get("segment_id", "") or str(len(video_materials) + 1)  
                        for material in result.get("matched_materials", []):
                            video_materials.append({
                                "video_path": material.get("path", ""),
                                "material_id": material.get("material_id", ""),
                                "description": material.get("info", {}).get("description", ""),
                                "duration": material.get("info", {}).get("duration", 0),
                                "tags": material.get("info", {}).get("tags", []),
                                "requirement_id": req_id,
                                "start_time": 0,
                                "end_time": material.get("info", {}).get("duration", 0),
                                "similarity_score": 0.9
                            })
                    print(f"从示例数据中提取了 {len(video_materials)} 个视频素材")
                except Exception as e:
                    print(f"处理示例数据时出错: {str(e)}")
        
        # 如果没有提取到视频素材，打印警告
        if not video_materials:
            print(f"警告: 无法从available_materials提取视频素材。类型: {type(available_materials)}")
            # 尝试直接打印available_materials的内容以进行调试
            if isinstance(available_materials, dict):
                print("available_materials的键：", list(available_materials.keys()))
                
                # 尝试其他可能的键名
                possible_keys = ["data", "materials", "videos", "resources", "segments"]
                for key in possible_keys:
                    if key in available_materials:
                        print(f"尝试从'{key}'字段提取素材...")
                        materials = available_materials[key]
                        if isinstance(materials, list):
                            for material in materials:
                                if isinstance(material, dict) and "video_path" in material:
                                    video_materials.append(material)
            
            # 如果是简单的视频列表（只包含video_path和其他基本信息），直接使用
            if isinstance(available_materials, list) and all(isinstance(item, dict) and "video_path" in item for item in available_materials):
                video_materials = available_materials
        
        # 根据是否有音频选择不同的提示信息
        message = ""
        if has_audio:
            segment_type = "口播分段"
            message = f"""请为每个{segment_type}选择最合适的视频素材，并规划剪辑点。

步骤：
1. 分析每个素材的视频内容描述和属性（如shot_type、description等）
2. 基于素材描述信息选择最合适的视频片段
3. 为每个音频分段指定一个视频片段，包括:
   - video_path: 视频文件路径
   - start_time: 开始时间（秒）
   - end_time: 结束时间（秒）
   - reason: 选择该片段的理由

请确保你的回答包含一个完整的segments列表，每个segment对应一个音频分段，画面与音频内容需协调一致。
每段口播需要多段素材(每条素材2-10秒）进行组合剪辑呈现效果，适用于短视频平台的快节奏。"""
        else:
            segment_type = "视觉场景"
            message = f"""请为每个{segment_type}选择最合适的视频素材，并规划剪辑点。

步骤：
1. 分析每个素材的视频内容描述和属性（如shot_type、description等）
2. 基于素材描述信息选择最合适的视频片段
3. 为每个场景分段指定视频片段，包括:
   - video_path: 视频文件路径
   - start_time: 开始时间（秒）
   - end_time: 结束时间（秒）
   - reason: 选择该片段的理由

请确保你的回答包含一个完整的segments列表，每个segment对应一个视觉场景。
**重要**：视频片段的时长必须与场景要求的时长精确匹配，每个场景可以使用多个视频片段组合以达到所需时长。
每个视频片段的"end_time - start_time"应与场景的"duration"值匹配。
如果一个场景需要多个素材，所有素材的总时长应等于场景时长。

画面之间需要在镜头运镜、画面、色彩、节奏、内容上进行衔接，确保视频的连贯性和流畅性。"""

        # 修改返回格式，确保包含segments键
        return {
            "segments": segments,
            "available_materials": video_materials,
            "has_audio": has_audio,
            "message": message
        }

class EditingPlanningAgent:
    @staticmethod
    def create():
        """创建剪辑规划 Agent"""
        # 创建工具实例
        editing_plan_tool = EditingPlanTool()
        
        # 创建 Agent
        editing_planning_agent = Agent(
            role="视频剪辑规划专家",
            goal="规划视频剪辑，为每个内容分段选择合适的视频素材",
            backstory="""你是一名资深的视频剪辑师和创意总监，擅长规划视频剪辑流程。
            你熟悉各种剪辑技巧和视觉语言，能够将文本内容与视觉素材完美结合。
            你的工作是为每个内容分段选择最合适的视频素材，并规划精确的剪辑点，
            确保最终的视频在视听上协调一致，能够有效传达信息和情感。

            对于有口播的视频：
            - 你需要确保视觉内容与口播内容协调一致
            - 每段口播需要多段素材(每条素材2-10秒）进行组合剪辑呈现效果，适用于短视频平台的快节奏
            - 保证素材的总时长与口播的时长相匹配

            对于纯视觉脚本的视频：
            - 你需要根据场景描述和情感基调选择最匹配的视频素材
            - 保证素材的时长与场景要求的时长相匹配
            - 确保视觉风格的一致性和叙事流畅性

            无论哪种类型，你都需要确保:
            - 画面之间在镜头运镜、画面、色彩、节奏、内容上进行衔接
            - 视频具有连贯性和流畅性，不给用户带来不好的观感
            - 根据内容选择最合适的剪辑节奏和风格""",
            use_system_prompt=False,
            verbose=True,
            allow_delegation=False,
            tools=[editing_plan_tool],
            llm=LLM(
                model="gemini-1.5-pro",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai",
                timeout=180
            )
        )
        
        return editing_planning_agent 