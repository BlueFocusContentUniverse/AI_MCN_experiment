import os
import json
import time
import re
from typing import Dict, Any, Optional, List
from services.whisper_transcription import WhisperTranscriptionService
from agents.vision_agent import VisionAgent
from agents.cinematography_agent import CinematographyAgent
from services.mongodb_service import MongoDBService
from crewai import Task, Crew, Process
import datetime
import logging
from services.embedding_service import EmbeddingService

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoInfoExtractor:
    """视频信息提取服务，整合语音、视觉和动态信息"""
    
    def __init__(self, output_dir: str = "./output", skip_mongodb: bool = False, special_requirements: str = ""):
        """
        初始化视频信息提取服务
        
        参数:
        output_dir: 输出目录
        skip_mongodb: 如果为True，则跳过MongoDB连接
        special_requirements: 用户指定的特殊需求，将添加到任务描述中
        """
        self.output_dir = output_dir
        self.special_requirements = special_requirements
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化服务和Agent
        self.transcription_service = WhisperTranscriptionService()
        self.vision_agent = VisionAgent.create()
        self.cinematography_agent = CinematographyAgent.create()
        self.embedding_service = EmbeddingService()  # 添加嵌入服务
        
        # 初始化MongoDB服务
        self.mongodb_service = None
        if not skip_mongodb:
            try:
                self.mongodb_service = MongoDBService()
                logger.info("MongoDB服务初始化成功")
            except Exception as e:
                logger.warning(f"MongoDB连接失败: {str(e)}")
                logger.warning("将跳过数据持久化到MongoDB")
    
    def extract_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        提取视频信息，包括语音、视觉和动态信息
        
        参数:
        video_path: 视频文件路径
        
        返回:
        完整的视频信息
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")
        
        # 检查是否已存在分析结果
        if self.mongodb_service:
            try:
                existing_info = self.mongodb_service.find_video_by_path(video_path)
                if existing_info:
                    logger.info(f"找到现有分析结果: {video_path}")
                    return existing_info
            except Exception as e:
                logger.error(f"查询MongoDB时出错: {str(e)}")
        
        # 1. 提取语音信息
        logger.info("提取语音信息...")
        transcription = self.transcription_service.transcribe_video(video_path)
        
        # 2. 提取视觉信息
        logger.info("提取视觉信息...")
        # 创建视觉分析任务
        special_req_text = f"\n\n用户特殊需求: {self.special_requirements}" if self.special_requirements else ""
        
        analyze_frames_task = Task(
            description=f"""从视频 {video_path} 中提取关键帧，并使用Gemini进行视觉内容分析。
            
            重要提示：你必须使用BatchProcessingFrames工具来处理视频，该工具会自动执行分批处理，确保所有帧都被分析。
            该工具会将完整的分析结果保存到文件中，并返回文件路径。
            
            使用均匀采样策略提取最多60帧，并分批处理(每批15帧)进行分析，确保覆盖整个视频。
            重点识别汽车相关场景、场景变化和关键视觉元素。
            
            在你的回复中，请确保包含结果文件的路径，这样下一个Agent就能使用这个文件路径。{special_req_text}""",
            expected_output="包含分析摘要和结果文件路径的JSON对象，确保明确指出结果文件的位置。",
            agent=self.vision_agent
        )
        
        # 创建视觉分析Crew
        vision_crew = Crew(
            agents=[self.vision_agent],
            tasks=[analyze_frames_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行视觉分析
        vision_result = vision_crew.kickoff(inputs={"video_path": video_path})
        
        # 解析视觉分析结果，获取帧分析文件路径
        frames_analysis_file = self._extract_file_path_from_result(vision_result)
        
        if not frames_analysis_file or not os.path.exists(frames_analysis_file):
            logger.error(f"无法从视觉分析获取有效的帧分析文件")
            # 创建一个空的帧分析文件，以便继续处理
            frames_analysis_file = self._create_empty_frames_analysis_file(video_path)
        
        # 3. 提取动态信息
        logger.info("提取电影摄影信息...")
        # 创建动态分析任务
        cinematography_task = Task(
            description=f"""分析视频 {video_path} 的运镜、色调、节奏等动态特征，并结合语音内容进行综合分析。
            
            使用LoadFramesAnalysisFromFile工具从文件 {frames_analysis_file} 加载帧分析结果，
            然后分析这些帧之间的关系，提取动态特征。
            
            语音内容摘要:
            {transcription.get('text', '无语音内容')[:1000]}...
            
            重点关注:
            1. 运镜技巧：识别推、拉、摇、移等镜头运动
            2. 色调变化：分析色彩搭配和色调随时间的变化
            3. 节奏感：评估剪辑节奏和视觉流动性
            4. 情绪表达：分析视觉元素如何传达情绪
            5. 汽车展示特点：分析汽车的动态展示方式和速度感表现
            6. 视听结合：分析视觉内容与语音内容的配合方式
            
            提供专业的电影摄影分析，使用行业术语。{special_req_text}""",
            expected_output="包含运镜、色调、节奏等动态特征分析的JSON对象，并包含视听结合分析。",
            agent=self.cinematography_agent
        )
        
        # 创建动态分析Crew
        cinematography_crew = Crew(
            agents=[self.cinematography_agent],
            tasks=[cinematography_task],
            verbose=True,
            process=Process.sequential
        )
        
        # 执行动态分析
        cinematography_result = cinematography_crew.kickoff(
            inputs={"frames_analysis_file": frames_analysis_file}
        )
        
        # 4. 整合所有信息
        logger.info("整合所有信息...")
        video_info = self._integrate_information(
            video_path=video_path,
            transcription=transcription,
            vision_result=vision_result,
            cinematography_result=cinematography_result,
            frames_analysis_file=frames_analysis_file
        )
        
        # 5. 保存到MongoDB
        logger.info("保存到MongoDB...")
        if self.mongodb_service:
            try:
                # 确保video_info包含所有必要的字段
                self._ensure_required_fields(video_info)
                # 添加日志，检查关键字段是否有内容
                logger.info(f"视频信息摘要: 视觉分析元素数: {sum(len(video_info['vision_analysis'].get(k, [])) for k in video_info['vision_analysis'] if isinstance(video_info['vision_analysis'].get(k), list))}")
                logger.info(f"视频信息摘要: 电影摄影分析元素数: {sum(len(video_info['cinematography_analysis'].get(k, [])) for k in video_info['cinematography_analysis'] if isinstance(video_info['cinematography_analysis'].get(k), list))}")
                doc_id = self.mongodb_service.save_video_info(video_info)
                logger.info(f"视频信息已保存到MongoDB，文档ID: {doc_id}")
            except Exception as e:
                logger.error(f"保存到MongoDB时出错: {str(e)}")
                logger.error(f"错误详情: {e.__class__.__name__}: {str(e)}")
                # 尝试保存到json文件作为备份
                error_file = os.path.join(self.output_dir, f"mongodb_error_{int(time.time())}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump({"error": str(e), "video_path": video_path}, f, ensure_ascii=False, indent=2)
        
        return video_info
    
    def _ensure_required_fields(self, video_info: Dict[str, Any]) -> None:
        """确保video_info包含所有必要的字段"""
        required_fields = {
            "video_path": str,
            "analysis_time": str,
            "brand": str,
            "transcription": dict,
            "vision_analysis": dict,
            "cinematography_analysis": dict
        }
        
        for field, field_type in required_fields.items():
            if field not in video_info:
                logger.warning(f"video_info缺少必要字段: {field}，添加默认值")
                if field_type == dict:
                    video_info[field] = {}
                elif field_type == list:
                    video_info[field] = []
                else:
                    video_info[field] = "未知"
            elif not isinstance(video_info[field], field_type):
                logger.warning(f"video_info字段类型不匹配: {field}，期望{field_type}，实际{type(video_info[field])}，转换为默认值")
                if field_type == dict:
                    video_info[field] = {}
                elif field_type == list:
                    video_info[field] = []
                else:
                    video_info[field] = str(video_info[field])
    
    def _create_empty_frames_analysis_file(self, video_path: str) -> str:
        """创建一个空的帧分析文件"""
        frames_analysis_dir = os.path.join(self.output_dir, "frames_analysis")
        os.makedirs(frames_analysis_dir, exist_ok=True)
        
        file_path = os.path.join(frames_analysis_dir, f"empty_frames_analysis_{int(time.time())}.json")
        
        empty_analysis = {
            "video_path": video_path,
            "frames_results": [],
            "note": "This is an empty analysis file created because the original analysis could not be processed"
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(empty_analysis, f, ensure_ascii=False, indent=2)
        
        logger.info(f"创建空的帧分析文件: {file_path}")
        return file_path
    
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
    
    def _extract_file_path_from_result(self, result: Any) -> str:
        """
        从结果中提取文件路径
        
        参数:
        result: 分析结果，可能是CrewOutput对象或其他类型
        
        返回:
        提取的文件路径，如果无法提取则返回空字符串
        """
        try:
            # 处理CrewOutput对象
            if hasattr(result, 'json_dict') and result.json_dict is not None:
                if 'frames_analysis_file' in result.json_dict:
                    return result.json_dict['frames_analysis_file']
                elif 'file_path' in result.json_dict:
                    return result.json_dict['file_path']
            
            # 尝试使用_safe_parse_json解析结果
            parsed_result = self._safe_parse_json(result, "_extract_file_path_from_result")
            
            # 从解析后的结果中查找文件路径
            if 'frames_analysis_file' in parsed_result:
                return parsed_result['frames_analysis_file']
            elif 'file_path' in parsed_result:
                return parsed_result['file_path']
            
            # 如果找不到文件路径，记录错误并返回空字符串
            logger.warning(f"无法从结果中提取文件路径: {parsed_result}")
            return ""
        except Exception as e:
            logger.error(f"提取文件路径时出错: {e}")
            return ""
    
    def _integrate_information(self, video_path: str, transcription: Dict[str, Any], 
                              vision_result: Any, cinematography_result: Any,
                              frames_analysis_file: str) -> Dict[str, Any]:
        """
        整合所有提取的信息
        
        参数:
        video_path: 视频文件路径
        transcription: 语音转写结果
        vision_result: 视觉分析结果
        cinematography_result: 电影摄影分析结果
        frames_analysis_file: 帧分析文件路径
        
        返回:
        整合后的视频信息
        """
        # 解析视觉分析结果
        vision_data = self._safe_parse_json(vision_result, "_integrate_information.vision")
        
        # 解析电影摄影分析结果
        cinematography_data = self._safe_parse_json(cinematography_result, "_integrate_information.cinematography")
        
        # 生成电影摄影分析的嵌入向量
        cinematography_text = ""
        if isinstance(cinematography_data, dict):
            cinematography_text = str(cinematography_data)
        elif isinstance(cinematography_data, str):
            cinematography_text = cinematography_data
        
        # 获取嵌入向量
        cinematography_embedding = None
        if cinematography_text:
            try:
                cinematography_embedding = self.embedding_service.get_embedding(cinematography_text)
                logger.info(f"成功生成电影摄影分析的嵌入向量，维度: {len(cinematography_embedding)}")
            except Exception as e:
                logger.error(f"生成嵌入向量时出错: {str(e)}")
        
        # 整合所有信息
        video_info = {
            "video_path": video_path,
            "analysis_time": datetime.datetime.now().isoformat(),
            "brand": " ",
            "transcription": transcription,
            "vision_analysis": vision_data,
            "cinematography_analysis": cinematography_data,
            "frames_analysis_file": frames_analysis_file
        }
        
        # 添加嵌入向量
        if cinematography_embedding:
            video_info["cinematography_embedding"] = cinematography_embedding
        
        return video_info
    
    def _extract_vision_summary(self, vision_result, frames_analysis) -> Dict[str, Any]:
        """提取视觉分析摘要"""
        try:
            # 初始化摘要
            summary = {
                "scene_types": [],
                "objects": [],
                "people": [],
                "actions": [],
                "car_features": [],
                "visual_style": []
            }
            
            # 如果frames_analysis中有数据，从中提取信息
            if frames_analysis and "frames_results" in frames_analysis:
                frames_results = frames_analysis["frames_results"]
                
                # 从每一帧中提取信息
                for frame in frames_results:
                    if isinstance(frame, dict):
                        # 场景类型
                        if "scene_type" in frame and frame["scene_type"]:
                            summary["scene_types"].append(frame["scene_type"])
                        
                        # 物体
                        if "main_objects" in frame and isinstance(frame["main_objects"], list):
                            summary["objects"].extend(frame["main_objects"])
                        
                        # 人物
                        if "人物" in frame and isinstance(frame["人物"], list):
                            summary["people"].extend(frame["人物"])
                        
                        # 动作
                        if "actions" in frame and isinstance(frame["actions"], list):
                            summary["actions"].extend(frame["actions"])
                        
                        # 汽车特征
                        if "car_elements" in frame:
                            if isinstance(frame["car_elements"], dict):
                                for key, value in frame["car_elements"].items():
                                    if isinstance(value, str) and value != "未知":
                                        summary["car_features"].append(f"{key}:{value}")
                            elif isinstance(frame["car_elements"], list):
                                summary["car_features"].extend(frame["car_elements"])
                        
                        # 视觉风格
                        if "visual_style" in frame and frame["visual_style"]:
                            summary["visual_style"].append(frame["visual_style"])
            
            # 尝试从vision_result中提取更多信息
            if vision_result:
                # 尝试将结果转换为字典
                if hasattr(vision_result, 'to_dict'):
                    result_dict = vision_result.to_dict()
                elif isinstance(vision_result, str):
                    # 尝试解析JSON字符串
                    try:
                        result_dict = json.loads(vision_result)
                    except:
                        # 如果不是有效的JSON，提取文本摘要
                        summary["text_summary"] = vision_result[:1000] + "..."
                        result_dict = {}
                else:
                    result_dict = vision_result
                
                # 从result_dict中提取标签
                summary.update(self._extract_tags_from_dict(result_dict))
            
            # 去重
            for key in summary:
                if isinstance(summary[key], list):
                    summary[key] = list(set(filter(None, summary[key])))
            
            return summary
        except Exception as e:
            logger.error(f"提取视觉摘要时出错: {str(e)}")
            return {"error": str(e)}
    
    def _extract_tags_from_dict(self, data: Dict[str, Any]) -> Dict[str, List[str]]:
        """从字典中提取标签"""
        tags = {
            "scene_types": [],
            "objects": [],
            "people": [],
            "actions": [],
            "car_features": [],
            "visual_style": []
        }
        
        # 递归搜索字典
        def search_dict(d, depth=0):
            if depth > 5:  # 限制递归深度
                return
            
            if isinstance(d, dict):
                for k, v in d.items():
                    # 场景类型
                    if any(keyword in k.lower() for keyword in ["scene", "环境", "场景"]):
                        if isinstance(v, str):
                            tags["scene_types"].append(v)
                        elif isinstance(v, list):
                            tags["scene_types"].extend([item for item in v if isinstance(item, str)])
                    
                    # 物体
                    if any(keyword in k.lower() for keyword in ["object", "物体", "元素"]):
                        if isinstance(v, str):
                            tags["objects"].append(v)
                        elif isinstance(v, list):
                            tags["objects"].extend([item for item in v if isinstance(item, str)])
                    
                    # 人物
                    if any(keyword in k.lower() for keyword in ["person", "people", "人", "人物"]):
                        if isinstance(v, str):
                            tags["people"].append(v)
                        elif isinstance(v, list):
                            tags["people"].extend([item for item in v if isinstance(item, str)])
                    
                    # 动作
                    if any(keyword in k.lower() for keyword in ["action", "activity", "动作", "活动"]):
                        if isinstance(v, str):
                            tags["actions"].append(v)
                        elif isinstance(v, list):
                            tags["actions"].extend([item for item in v if isinstance(item, str)])
                    
                    # 汽车特征
                    if any(keyword in k.lower() for keyword in ["car", "vehicle", "汽车", "车"]):
                        if isinstance(v, str):
                            tags["car_features"].append(v)
                        elif isinstance(v, list):
                            tags["car_features"].extend([item for item in v if isinstance(item, str)])
                    
                    # 视觉风格
                    if any(keyword in k.lower() for keyword in ["style", "visual", "风格", "视觉"]):
                        if isinstance(v, str):
                            tags["visual_style"].append(v)
                        elif isinstance(v, list):
                            tags["visual_style"].extend([item for item in v if isinstance(item, str)])
                    
                    # 递归搜索
                    search_dict(v, depth + 1)
            elif isinstance(d, list):
                for item in d:
                    search_dict(item, depth + 1)
        
        search_dict(data)
        return tags
    
    def _extract_keywords_from_text(self, text: str, keywords: List[str]) -> List[str]:
        """从文本中提取关键词"""
        found_keywords = []
        for keyword in keywords:
            if keyword in text:
                found_keywords.append(keyword)
        return found_keywords
    
    def _extract_cinematography_summary(self, cinematography_result) -> Dict[str, Any]:
        """提取电影摄影分析摘要"""
        try:
            # 初始化摘要
            summary = {
                "camera_movements": [],
                "color_palette": [],
                "rhythm": [],
                "mood": [],
                "car_presentation": [],
                "audio_visual_sync": []
            }
            
            # 处理CrewOutput对象
            if hasattr(cinematography_result, 'raw'):
                # 直接使用raw属性中的JSON字符串
                try:
                    # 尝试解析JSON
                    result_dict = json.loads(cinematography_result.raw)
                    logger.info(f"成功从CrewOutput.raw解析JSON")
                    
                    # 从解析后的字典中提取信息
                    # 运镜技巧
                    if "camerawork" in result_dict and "techniques" in result_dict["camerawork"]:
                        for technique in result_dict["camerawork"]["techniques"]:
                            if "type" in technique:
                                summary["camera_movements"].append(technique["type"])
                    
                    # 色调
                    if "color_tone" in result_dict and "variations" in result_dict["color_tone"]:
                        for variation in result_dict["color_tone"]["variations"]:
                            if "description" in variation:
                                summary["color_palette"].append(variation["description"])
                    
                    # 节奏
                    if "rhythm" in result_dict and "evaluation" in result_dict["rhythm"]:
                        for eval_item in result_dict["rhythm"]["evaluation"]:
                            if "characteristic" in eval_item:
                                summary["rhythm"].append(eval_item["characteristic"])
                    
                    # 情绪
                    if "emotion" in result_dict and "conveyance" in result_dict["emotion"]:
                        summary["mood"].append(result_dict["emotion"]["conveyance"])
                    
                    # 汽车展示
                    if "car_display" in result_dict and "features" in result_dict["car_display"]:
                        for feature in result_dict["car_display"]["features"]:
                            if "presentation" in feature:
                                summary["car_presentation"].append(feature["presentation"])
                    
                    # 视听结合
                    if "audio_visual_correlation" in result_dict and "analysis" in result_dict["audio_visual_correlation"]:
                        summary["audio_visual_sync"].append(result_dict["audio_visual_correlation"]["analysis"])
                    
                    # 保存原始JSON以备后用
                    summary["raw_json"] = cinematography_result.raw
                    
                    return summary
                except json.JSONDecodeError as e:
                    logger.warning(f"无法解析CrewOutput.raw为JSON: {str(e)}")
                    # 如果解析失败，将raw作为文本保存
                    summary["text_summary"] = cinematography_result.raw[:1000] + "..."
                    return summary
            
            # 如果不是CrewOutput对象，尝试其他方法提取信息
            # ... (保留原有的代码)
            
            return summary
        except Exception as e:
            logger.error(f"提取电影摄影摘要时出错: {str(e)}")
            return {"error": str(e)}
    
    def _extract_list_or_string(self, value) -> List[str]:
        """从值中提取列表或字符串"""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        elif isinstance(value, str):
            return [value]
        elif isinstance(value, dict):
            # 尝试从字典中提取值
            result = []
            for k, v in value.items():
                if isinstance(v, str):
                    result.append(v)
                elif isinstance(v, list):
                    result.extend([item for item in v if isinstance(item, str)])
            return result
        else:
            return []
    
    def _generate_multimodal_info(self, transcription: Dict[str, Any], 
                                 vision_summary: Dict[str, Any], 
                                 cinematography_summary: Dict[str, Any]) -> Dict[str, Any]:
        """生成多模态信息，整合语音和视觉"""
        # 提取关键词和主题
        keywords = []
        themes = []
        
        # 从转录中提取关键词
        if "text" in transcription and transcription["text"]:
            # 提取关键词
            text = transcription["text"].lower()
            car_keywords = ["汽车", "车", "驾驶", "行驶", "速度", "性能", "动力", "设计", "外观", "内饰"]
            for keyword in car_keywords:
                if keyword in text and keyword not in keywords:
                    keywords.append(keyword)
        
        # 从视觉分析中提取主题
        if "scene_types" in vision_summary and vision_summary["scene_types"]:
            themes.extend(vision_summary["scene_types"])
        
        if "car_features" in vision_summary and vision_summary["car_features"]:
            themes.append("汽车")
            keywords.extend(vision_summary["car_features"])
        
        # 从电影摄影分析中提取情绪和风格
        mood = []
        style = []
        
        if "mood" in cinematography_summary and cinematography_summary["mood"]:
            mood.extend(cinematography_summary["mood"])
        
        if "color_palette" in cinematography_summary and cinematography_summary["color_palette"]:
            style.extend(cinematography_summary["color_palette"])
        
        # 去重
        keywords = list(set(keywords))
        themes = list(set(themes))
        mood = list(set(mood))
        style = list(set(style))
        
        # 构建多模态信息
        multimodal_info = {
            "keywords": keywords,
            "themes": themes,
            "content_type": self._determine_content_type(transcription, vision_summary, cinematography_summary),
            "mood": mood if mood else self._determine_mood(transcription, vision_summary, cinematography_summary),
            "style": style,
            "suitable_for": self._determine_suitable_usage(transcription, vision_summary, cinematography_summary)
        }
        
        return multimodal_info
    
    def _determine_content_type(self, transcription: Dict[str, Any], 
                               vision_summary: Dict[str, Any], 
                               cinematography_summary: Dict[str, Any]) -> str:
        """确定内容类型"""
        # 检查是否有明确的内容类型标识
        if "car_features" in vision_summary and vision_summary["car_features"]:
            return "汽车展示"
        
        if "text" in transcription and transcription["text"]:
            text = transcription["text"].lower()
            if "广告" in text:
                return "汽车广告"
            elif "测评" in text or "评测" in text:
                return "汽车测评"
            elif "教程" in text or "指南" in text:
                return "驾驶教程"
        
        # 默认类型
        return "汽车相关视频"
    
    def _determine_mood(self, transcription: Dict[str, Any], 
                       vision_summary: Dict[str, Any], 
                       cinematography_summary: Dict[str, Any]) -> str:
        """确定情绪基调"""
        # 从电影摄影分析中提取情绪
        if "mood" in cinematography_summary and cinematography_summary["mood"]:
            if isinstance(cinematography_summary["mood"], list) and len(cinematography_summary["mood"]) > 0:
                return cinematography_summary["mood"][0]
            elif isinstance(cinematography_summary["mood"], str):
                return cinematography_summary["mood"]
        
        # 从转录中推断情绪
        if "text" in transcription and transcription["text"]:
            text = transcription["text"].lower()
            if any(word in text for word in ["激动", "兴奋", "惊喜", "震撼"]):
                return "激动"
            elif any(word in text for word in ["平静", "舒适", "安逸"]):
                return "平静"
            elif any(word in text for word in ["豪华", "奢侈", "高端"]):
                return "奢华"
            elif any(word in text for word in ["科技", "未来", "智能"]):
                return "科技感"
        
        # 默认情绪
        return "中性"
    
    def _determine_suitable_usage(self, transcription: Dict[str, Any], 
                                 vision_summary: Dict[str, Any], 
                                 cinematography_summary: Dict[str, Any]) -> List[str]:
        """确定适合的用途"""
        usages = ["汽车广告"]
        
        # 根据内容添加其他可能的用途
        if "text" in transcription and transcription["text"]:
            text = transcription["text"].lower()
            if "性能" in text or "动力" in text:
                usages.append("性能展示")
            if "设计" in text or "外观" in text:
                usages.append("设计展示")
            if "舒适" in text or "内饰" in text:
                usages.append("内饰展示")
            if "安全" in text:
                usages.append("安全特性展示")
        
        # 根据视觉内容添加用途
        if "car_features" in vision_summary:
            car_features = vision_summary["car_features"]
            if any(feature in ["前脸", "车身", "外观"] for feature in car_features):
                usages.append("外观展示")
            if any(feature in ["内饰", "座椅", "方向盘"] for feature in car_features):
                usages.append("内饰展示")
        
        # 根据电影摄影分析添加用途
        if "car_presentation" in cinematography_summary:
            car_presentation = cinematography_summary["car_presentation"]
            if any(presentation in ["动态展示", "速度感"] for presentation in car_presentation):
                usages.append("动态驾驶展示")
            if any(presentation in ["细节特写"] for presentation in car_presentation):
                usages.append("细节展示")
        
        # 去重
        return list(set(usages))
    
    def _generate_content_tags(self, transcription: Dict[str, Any], 
                              vision_summary: Dict[str, Any], 
                              cinematography_summary: Dict[str, Any]) -> List[str]:
        """生成内容标签，用于后续检索"""
        tags = []
        
        # 从转录中提取标签
        if "text" in transcription and transcription["text"]:
            text = transcription["text"].lower()
            # 汽车相关标签
            car_keywords = ["汽车", "车", "驾驶", "行驶", "速度", "性能", "动力", "设计", "外观", "内饰"]
            for keyword in car_keywords:
                if keyword in text and keyword not in tags:
                    tags.append(keyword)
        
        # 从视觉分析中提取标签
        for key in ["scene_types", "objects", "car_features"]:
            if key in vision_summary and vision_summary[key]:
                tags.extend(vision_summary[key])
        
        # 从电影摄影分析中提取标签
        for key in ["camera_movements", "color_palette", "mood", "car_presentation"]:
            if key in cinematography_summary and cinematography_summary[key]:
                tags.extend(cinematography_summary[key])
        
        # 去重
        return list(set(tags))