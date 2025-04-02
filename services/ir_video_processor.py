import os
import json
import logging
import time
import uuid
import copy # Import copy for deep copying
import re
import subprocess
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime

from services.enhanced_material_matching_service import EnhancedMaterialMatchingService
from services.fish_audio_service import FishAudioService
from services.video_editing_service import VideoEditingService
from services.mongodb_service import MongoDBService
from tools.ir_template_tool import IRTemplateTool

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IRVideoProcessor:
    """基于中间表示(IR)的视频处理器，负责执行完整的视频生成流程"""
    
    def __init__(self, output_dir: str = "./output"):
        """
        初始化IR视频处理器
        
        参数:
        output_dir: 输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建子目录
        self.audio_dir = os.path.join(output_dir, "audio")
        self.segments_dir = os.path.join(output_dir, "segments")
        self.final_dir = os.path.join(output_dir, "final")
        self.temp_dir = os.path.join(output_dir, "temp")
        
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.segments_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 初始化服务组件
        self.material_matcher = EnhancedMaterialMatchingService()
        self.fish_audio_service = FishAudioService(audio_output_dir=self.audio_dir)
        self.video_editing_service = VideoEditingService(output_dir=self.segments_dir)
        self.mongodb_service = MongoDBService()
        
        # 初始化token使用记录
        self.token_usage_records = []
    
    def validate_ir(self, ir_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证IR数据是否有效
        
        参数:
        ir_data: IR数据
        
        返回:
        验证结果
        """
        validation_result = IRTemplateTool.validate_ir(ir_data)
        
        if not validation_result["is_valid"]:
            logger.error(f"IR验证失败: {validation_result['errors']}")
            return validation_result
        
        logger.info("IR验证成功")
        return validation_result
    
    def process_ir(self, ir_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理IR数据，生成视频
        
        参数:
        ir_data: IR数据
        
        返回:
        处理结果
        """
        # 生成项目ID和时间戳
        project_id = ir_data.get("metadata", {}).get("project_id")
        if not project_id:
            project_id = str(uuid.uuid4())
            ir_data["metadata"]["project_id"] = project_id
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"ir_video_{project_id}_{timestamp}"
        
        logger.info(f"开始处理项目: {project_name}")
        
        # 验证IR
        validation_result = self.validate_ir(ir_data)
        if not validation_result["is_valid"]:
            return {
                "success": False,
                "error": validation_result["errors"],
                "project_id": project_id
            }
        
        # 确保IR完整性
        ir_data = IRTemplateTool.merge_with_defaults(ir_data)
        
        # 保存IR数据
        ir_file = os.path.join(self.temp_dir, f"{project_name}_ir.json")
        with open(ir_file, 'w', encoding='utf-8') as f:
            json.dump(ir_data, f, ensure_ascii=False, indent=2)
        
        try:
            # 1. 处理口播
            logger.info("处理口播...")
            voiceover_result = self._process_voiceover(ir_data, project_name)
            
            # 2. 搜索素材
            logger.info("搜索匹配素材...")
            materials_result = self._search_materials(ir_data, project_name)
            
            # 3. 规划剪辑
            logger.info("规划剪辑...")
            editing_plan = self._create_editing_plan(ir_data, voiceover_result, materials_result, project_name)
            
            # 4. 执行剪辑
            logger.info("执行剪辑...")
            final_video = self._execute_editing(editing_plan, project_name)
            
            # 5. 后期处理
            logger.info("执行后期处理...")
            processed_video = self._apply_post_processing(final_video, ir_data, project_name)
            
            # 确保所有结果对象都是有效的，防止 None 错误
            if not processed_video:
                logger.warning("后期处理返回的视频路径为空，使用原始视频")
                processed_video = final_video or ""
                
            safe_voiceover_result = voiceover_result if isinstance(voiceover_result, dict) else {}
            safe_materials_result = materials_result if isinstance(materials_result, dict) else {}
            safe_editing_plan = editing_plan if isinstance(editing_plan, dict) else {}
            
            # 构建结果
            result = {
                "success": bool(processed_video),  # 只有当有最终视频时才认为成功
                "project_id": project_id,
                "project_name": project_name,
                "ir_file": ir_file,
                "final_video": processed_video,
                "voiceover_result": safe_voiceover_result,
                "materials_result": safe_materials_result,
                "editing_plan": safe_editing_plan
            }
            
            # 保存完整结果
            result_file = os.path.join(self.final_dir, f"{project_name}_result.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"项目处理完成: {project_name}")
            return result
            
        except Exception as e:
            logger.error(f"处理IR时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": str(e),
                "project_id": project_id,
                "project_name": project_name,
                "ir_file": ir_file
            }
    
    def _process_voiceover(self, ir_data: Dict[str, Any], project_name: str) -> Dict[str, Any]:
        """
        处理口播部分
        
        参数:
        ir_data: IR数据
        project_name: 项目名称
        
        返回:
        口播处理结果
        """
        logger.info("处理口播...")
        
        # 获取口播配置
        audio_design = ir_data.get("audio_design", {})
        voiceover_config = audio_design.get("voiceover", {})
        
        # 如果未启用口播，则返回空结果
        if not voiceover_config.get("enabled", True):
            logger.info("口播功能未启用，跳过")
            return {
                "enabled": False,
                "segments": []
            }
        
        # 获取口播段落
        voiceover_segments = voiceover_config.get("segments", [])
        if not voiceover_segments:
            logger.warning("口播配置中没有段落，跳过")
            return {
                "enabled": True,
                "segments": []
            }
        
        # 获取语音设置
        voice_settings = voiceover_config.get("voice_settings", {})
        
        # 准备口播段落
        fish_audio_segments = []
        for i, segment in enumerate(voiceover_segments):
            segment_id = segment.get("id", f"auto_segment_{i+1}")
            text = segment.get("text", "").strip()
            
            if not text:
                logger.warning(f"段落 {segment_id} 没有文本内容，跳过")
                continue
            
            fish_audio_segments.append({
                "segment_id": segment_id,
                "text": text,
                "position": segment.get("position", ""),
                "timing": segment.get("timing", {})
            })
        
        # 生成音频
        try:
            # 配置Fish Audio服务
            self.fish_audio_service.reference_id = voice_settings.get("reference_id", self.fish_audio_service.reference_id)
            self.fish_audio_service.mp3_bitrate = voice_settings.get("mp3_bitrate", self.fish_audio_service.mp3_bitrate)
            self.fish_audio_service.chunk_length = voice_settings.get("chunk_length", self.fish_audio_service.chunk_length)
            self.fish_audio_service.latency_mode = voice_settings.get("latency_mode", self.fish_audio_service.latency_mode)
            self.fish_audio_service.audio_gain_db = voice_settings.get("audio_gain_db", self.fish_audio_service.audio_gain_db)
            
            # 配置音频剪切
            audio_cut = voice_settings.get("audio_cut", {})
            self.fish_audio_service.enable_audio_cut = audio_cut.get("enabled", self.fish_audio_service.enable_audio_cut)
            if self.fish_audio_service.enable_audio_cut:
                self.fish_audio_service.audio_cut_config.threshold = audio_cut.get("threshold", self.fish_audio_service.audio_cut_config.threshold)
                self.fish_audio_service.audio_cut_config.min_silence_len = audio_cut.get("min_silence_len", self.fish_audio_service.audio_cut_config.min_silence_len)
                self.fish_audio_service.audio_cut_config.keep_silence = audio_cut.get("keep_silence", self.fish_audio_service.audio_cut_config.keep_silence)
            
            # 生成音频段落
            audio_segments = self.fish_audio_service.generate_audio_segments(fish_audio_segments)
            
            # 保存段落信息
            audio_info_file = os.path.join(self.audio_dir, f"{project_name}_audio_info.json")
            self.fish_audio_service.save_segments_info(audio_segments, audio_info_file)
            
            # 计算总时长
            total_duration = sum(segment.get("duration", 0) for segment in audio_segments if "duration" in segment)
            logger.info(f"口播总时长: {total_duration:.2f}秒")
            
            # 构建结果
            result = {
                "enabled": True,
                "total_duration": total_duration,
                "segments": audio_segments,
                "info_file": audio_info_file
            }
            
            return result
            
        except Exception as e:
            logger.error(f"生成口播音频时出错: {str(e)}")
            raise
    
    def _search_materials(self, ir_data: Dict[str, Any], project_name: str) -> Dict[str, Any]:
        """
        搜索匹配素材 - 采用两阶段方法：
        1. 使用向量搜索筛选初步候选素材（仅过滤brand和model）
        2. 使用评分机制从候选素材中选择最终素材
        
        参数:
        ir_data: IR数据
        project_name: 项目名称
        
        返回:
        素材搜索结果
        """
        logger.info("搜索视频素材...")
        
        # 获取视频段落
        visual_structure = ir_data.get("visual_structure", {})
        segments = visual_structure.get("segments", [])
        
        if not segments:
            logger.warning("视频结构中没有段落，无法搜索素材")
            return {
                "segments": [],
                "count": 0
            }
        
        # 第一阶段：为每个段落预筛选候选素材
        segment_candidates = []
        
        # 处理每个段落
        for i, segment in enumerate(segments):
            segment_id = segment.get("id", f"segment_{i+1}")
            segment_type = segment.get("type", "generic")
            
            logger.info(f"处理段落 {segment_id}，类型: {segment_type}")
            
            # 处理 visual_requirements 可能是列表的情况
            if "visual_requirements" in segment and isinstance(segment["visual_requirements"], list):
                logger.warning(f"段落 {segment_id} 的 visual_requirements 是列表类型，转换为字典")
                
                # 将列表转换为字典格式
                visual_req_dict = {}
                for item in segment["visual_requirements"]:
                    if isinstance(item, dict) and "key" in item and "value" in item:
                        visual_req_dict[item["key"]] = item["value"]
                    
                segment["visual_requirements"] = visual_req_dict
            
            # 添加brand和model信息到搜索策略中
            if "material_search_strategy" not in segment:
                segment["material_search_strategy"] = {}
            
            # 确保material_search_strategy是字典
            if isinstance(segment["material_search_strategy"], str):
                search_type = segment["material_search_strategy"]
                segment["material_search_strategy"] = {"search_type": "embedding"}
            
            # 提取车型和品牌信息
            brand = segment.get("brand", "")
            model = segment.get("model", "")
            
            # 保存到搜索策略中
            if brand:
                segment["material_search_strategy"]["priority_brands"] = [brand]
            
            if model:
                segment["material_search_strategy"]["priority_models"] = [model]
                
            try:
                # 获取段落候选素材
                candidate_materials = self._find_candidate_materials(segment)
                
                if candidate_materials:
                    segment_candidates.append({
                        "segment_id": segment_id,
                        "segment_index": i,
                        "segment_type": segment_type,
                        "materials": candidate_materials
                    })
                else:
                    logger.warning(f"段落 {segment_id} 没有找到候选素材")
            
            except Exception as e:
                logger.error(f"处理段落 {segment_id} 搜索素材时出错: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info(f"完成素材搜索，共处理 {len(segments)} 个段落，找到 {len(segment_candidates)} 个有候选素材的段落")
        
        # 第二阶段：选择最终素材
        final_selections = self._select_final_materials(segment_candidates, ir_data)
        
        # 保存搜索结果
        materials_file = os.path.join(self.temp_dir, f"{project_name}_materials.json")
        with open(materials_file, 'w', encoding='utf-8') as f:
            json.dump(final_selections, f, ensure_ascii=False, indent=2)
        
        return final_selections
    
    def _find_candidate_materials(self, segment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        为单个段落查找候选素材，使用向量搜索
        
        参数:
        segment: 段落信息
        
        返回:
        候选素材列表
        """
        segment_id = segment.get("id", "unknown")
        candidate_materials = []
        
        logger.info(f"段落 {segment_id}: 执行向量搜索...")
        
        # 准备搜索条件，只保留 brand 和 model
        search_segment = copy.deepcopy(segment)
        
        # 确保material_search_strategy是字典
        if isinstance(search_segment.get("material_search_strategy"), str):
            search_type = search_segment["material_search_strategy"]
            search_segment["material_search_strategy"] = {"search_type": "embedding"}
        elif "material_search_strategy" not in search_segment:
            search_segment["material_search_strategy"] = {"search_type": "embedding"}
        else:
            # 设置为向量搜索
            search_segment["material_search_strategy"]["search_type"] = "embedding"
        
        # 执行向量搜索
        matching_materials = self.material_matcher.search_materials_for_segment(search_segment, limit=10)
        
        if matching_materials:
            # 添加前缀标记
            for material in matching_materials:
                material["match_type"] = "embedding"
            candidate_materials.extend(matching_materials)
            logger.info(f"段落 {segment_id}: 向量搜索找到 {len(matching_materials)} 个素材")
        
        # 如果没有找到素材，使用占位符
        if not candidate_materials:
            logger.warning(f"段落 {segment_id}: 向量搜索未找到素材，使用占位符")
            placeholder_material = {
                "_id": "placeholder",
                "video_path": "/home/jinpeng/multi-agent/素材/通用素材/风景.mp4",
                "title": "占位符视频",
                "duration": 10.0,
                "brand": "通用",
                "ranking_score": 0.1,
                "match_type": "placeholder"
            }
            candidate_materials.append(placeholder_material)
        
        return candidate_materials
    
    def _select_final_materials(self, segment_candidates: List[Dict[str, Any]], ir_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从候选素材中选择最终素材
        
        参数:
        segment_candidates: 段落候选素材信息
        ir_data: IR数据
        
        返回:
        最终选择的素材列表
        """
        logger.info("从候选素材中选择最终素材...")
        
        # 获取视频段落信息
        visual_structure = ir_data.get("visual_structure", {})
        segments = visual_structure.get("segments", [])
        
        # 创建段落ID到段落信息的映射
        segments_map = {segment.get("id", f"segment_{i+1}"): segment 
                      for i, segment in enumerate(segments)}
        
        final_selections = []
        
        for segment_info in segment_candidates:
            segment_id = segment_info.get("segment_id", "")
            segment_index = segment_info.get("segment_index", 0)
            segment_type = segment_info.get("segment_type", "")
            candidates = segment_info.get("materials", [])
            
            # 从原始段落获取时长信息
            segment_duration = 0
            if segment_id in segments_map:
                segment_duration = segments_map[segment_id].get("duration", 0)
            
            # 初步过滤 - 确保素材时长至少为段落时长的80%
            if segment_duration > 0:
                suitable_candidates = []
                for material in candidates:
                    # 对于占位符或随机素材，直接保留
                    if material.get("match_type") in ["placeholder", "random"]:
                        suitable_candidates.append(material)
                    else:
                        # 获取素材时长
                        material_duration = material.get("duration", 0)
                        
                        # 如果时长足够，加入候选
                        if material_duration >= segment_duration * 0.8:
                            suitable_candidates.append(material)
                
                # 如果有足够时长的素材，使用它们；否则使用全部素材
                if suitable_candidates:
                    filtered_candidates = suitable_candidates
                else:
                    filtered_candidates = candidates
            else:
                # 没有时长要求，使用全部素材
                filtered_candidates = candidates
            
            # 素材评分和排序
            scored_candidates = []
            
            for material in filtered_candidates:
                # 基础分 - 从material中获取
                base_score = material.get("ranking_score", material.get("similarity_score", 0.5))
                
                # 匹配类型加分 - 不同类型的素材有不同权重
                match_type = material.get("match_type", "")
                match_type_score = {
                    "embedding": 0.5,
                    "random": 0.2,
                    "placeholder": 0.1
                }.get(match_type, 0.3)
                
                # 计算最终分数
                final_score = base_score * 0.7 + match_type_score * 0.3
                
                # 添加到评分列表
                scored_candidates.append({
                    "material": material,
                    "score": final_score
                })
            
            # 按评分降序排序
            scored_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            # 选择最多两个最高评分的素材
            top_materials = [item["material"] for item in scored_candidates[:2]]
            
            # 记录日志
            if top_materials:
                logger.info(f"段落 {segment_id}: 选择了 {len(top_materials)} 个素材")
                for i, material in enumerate(top_materials):
                    match_type = material.get("match_type", "unknown")
                    video_path = material.get("video_path", "")
                    score = scored_candidates[i]["score"] if i < len(scored_candidates) else 0
                    logger.info(f"  素材 {i+1}: 类型={match_type}, 评分={score:.2f}, 路径={os.path.basename(video_path)}")
            else:
                logger.warning(f"段落 {segment_id}: 没有选择任何素材")
            
            # 添加到最终结果
            final_selections.append({
                "segment_id": segment_id,
                "segment_type": segment_type,
                "segment_index": segment_index,
                "count": len(top_materials),
                "materials": top_materials
            })
        
        # 按段落索引排序
        final_selections.sort(key=lambda x: x.get("segment_index", 0))
        
        # 构建结果
        result = {
            "segments": final_selections,
            "count": sum(item["count"] for item in final_selections)
        }
        
        return result
    
    def _create_editing_plan(self, ir_data: Dict[str, Any], voiceover_result: Dict[str, Any], 
                           materials_result: Dict[str, Any], project_name: str) -> Dict[str, Any]:
        """
        创建剪辑计划
        
        参数:
        ir_data: IR数据
        voiceover_result: 口播处理结果
        materials_result: 素材搜索结果
        project_name: 项目名称
        
        返回:
        剪辑计划
        """
        logger.info("创建剪辑计划...")
        
        # 获取视频段落
        visual_structure = ir_data.get("visual_structure", {})
        segments = visual_structure.get("segments", [])
        
        # 获取口播段落
        voiceover_segments = voiceover_result.get("segments", [])
        
        # 构建两种映射：基于segment_id的映射和基于index的映射（作为备用）
        voiceover_map = {segment["segment_id"]: segment for segment in voiceover_segments if "segment_id" in segment}
        voiceover_index_map = {str(i+1): segment for i, segment in enumerate(voiceover_segments)}
        
        # 获取素材结果
        segment_materials = materials_result.get("segments", [])
        materials_map = {sm["segment_id"]: sm for sm in segment_materials if "segment_id" in sm}
        
        # 创建剪辑项
        editing_items = []
        
        for i, segment in enumerate(segments):
            segment_id = segment.get("id", "")
            segment_type = segment.get("type", "")
            segment_duration = segment.get("duration", 0)
            
            # 获取口播信息
            narration = segment.get("narration", {})
            
            # 检查narration是否为字符串，将其转换为字典
            if isinstance(narration, str):
                logger.warning(f"段落 {segment_id} 的narration字段是字符串而不是字典: '{narration}'")
                # 使用字符串作为narration_text，创建一个新的字典
                narration = {"text": narration}
            
            voiceover_id = narration.get("voiceover_id", "")
            use_original_audio = narration.get("use_original_audio", False)
            
            # 获取对应的口播段落（尝试多种匹配方式）
            voiceover_segment = {}
            
            # 1. 首先尝试使用voiceover_id进行精确匹配
            if voiceover_id and voiceover_id in voiceover_map:
                voiceover_segment = voiceover_map[voiceover_id]
                logger.info(f"段落 {segment_id}: 通过voiceover_id '{voiceover_id}'找到对应口播")
            
            # 2. 尝试使用segment_id进行匹配（假设segment_id和口播的segment_id可能一致）
            elif segment_id in voiceover_map:
                voiceover_segment = voiceover_map[segment_id]
                logger.info(f"段落 {segment_id}: 通过segment_id匹配找到对应口播")
            
            # 3. 尝试使用数字顺序匹配（如果段落ID包含数字）
            elif re.search(r'\d+', segment_id):
                # 提取段落ID中的数字
                numbers = re.findall(r'\d+', segment_id)
                if numbers and numbers[0] in voiceover_index_map:
                    voiceover_segment = voiceover_index_map[numbers[0]]
                    logger.info(f"段落 {segment_id}: 通过提取数字 '{numbers[0]}' 找到对应口播")
            
            # 4. 尝试使用索引位置匹配
            elif str(i+1) in voiceover_index_map:
                voiceover_segment = voiceover_index_map[str(i+1)]
                logger.info(f"段落 {segment_id}: 通过索引位置 '{i+1}' 找到对应口播")
            
            else:
                logger.warning(f"段落 {segment_id}: 无法找到对应口播段落")
            
            voiceover_duration = voiceover_segment.get("duration", 0)
            audio_file = voiceover_segment.get("audio_file", "")
            
            # 决定片段时长（以口播时长为准，如无口播则使用IR中的时长）
            if voiceover_duration > 0:
                effective_duration = voiceover_duration
            else:
                effective_duration = segment_duration
            
            # 确保有一个有效的时长
            if effective_duration <= 0:
                effective_duration = 5.0  # 默认5秒
                logger.warning(f"段落 {segment_id} 没有有效的时长，使用默认值 {effective_duration} 秒")
            
            # 获取匹配的素材
            matched_materials = []
            if segment_id in materials_map:
                materials_data = materials_map[segment_id]
                matched_materials = materials_data.get("materials", [])
            
            # 筛选出时长足够的素材，或者选择最佳（即使可能不够长）
            best_material = None
            video_duration = 0 # 初始化视频时长
            
            if not matched_materials:
                logger.warning(f"段落 {segment_id} 没有找到任何匹配的素材，将跳过此段落。")
                continue # 跳过这个 segment 的处理

            # 尝试找到时长足够的素材
            found_suitable_material = False
            for material in matched_materials:
                # 获取素材信息 - 处理从数据库检索到的对象结构
                # 1. 直接的视频路径（如果有）
                video_path = material.get("video_path", "")
                
                # 2. 从文件信息字段中获取（MongoDB可能存储在不同字段）
                if not video_path and "file_info" in material:
                    video_path = material.get("file_info", {}).get("path", "")
                
                # 3. 如果是视频片段，可能需要从关联的视频对象获取
                if not video_path and "video_id" in material:
                    try:
                        # 获取关联视频对象
                        video_obj = self.mongodb_service.videos.find_one({"_id": material["video_id"]})
                        if video_obj:
                            video_path = video_obj.get("file_info", {}).get("path", "")
                    except Exception as e:
                        logger.error(f"获取关联视频时出错: {str(e)}")
                
                if not video_path:
                    logger.warning(f"素材缺少视频路径，跳过: {material.get('_id', '未知ID')}")
                    continue
                
                # 更新素材中的视频路径字段，确保后续处理正确
                material["video_path"] = video_path
                
                # 处理视频片段信息 - 获取合适的起始和结束时间
                start_time = material.get("start_time", 0)
                end_time = material.get("end_time", 0)
                
                # 如果是视频片段，可能有特定的开始和结束时间
                if "segment_start_time" in material:
                    start_time = material.get("segment_start_time", 0)
                if "segment_end_time" in material:
                    end_time = material.get("segment_end_time", 0)
                
                # 如果没有明确的段落起止时间，使用完整视频
                if end_time <= start_time:
                    # 获取视频时长
                    current_video_duration = material.get("duration", 0)
                    if current_video_duration <= 0 and os.path.exists(video_path):
                        try:
                            _, _, current_video_duration = self.video_editing_service.get_video_info(video_path)
                            material["duration"] = current_video_duration  # 更新素材字典
                        except Exception as e:
                            logger.error(f"获取视频时长时出错: {str(e)}")
                            current_video_duration = 0
                    
                    end_time = current_video_duration
                else:
                    # 已有明确的片段时间
                    current_video_duration = end_time - start_time
                
                # 更新素材中的片段信息
                material["start_time"] = start_time
                material["end_time"] = end_time
                material["segment_duration"] = current_video_duration

                # 检查时长是否满足需求
                if current_video_duration >= effective_duration:
                    best_material = material
                    video_duration = current_video_duration
                    found_suitable_material = True
                    logger.info(f"段落 {segment_id}: 找到时长足够的素材 {os.path.basename(video_path)} ({current_video_duration:.2f}s >= {effective_duration:.2f}s)")
                    break # 找到合适的就停止搜索

            # 如果没有找到时长足够的，使用第一个（评分最高的）素材，并记录警告
            if not found_suitable_material and matched_materials:
                # 再次处理第一个素材，确保所有必要字段都已填充
                best_material = matched_materials[0]
                
                # 确保视频路径存在
                video_path = best_material.get("video_path", "")
                if not video_path and "file_info" in best_material:
                    video_path = best_material.get("file_info", {}).get("path", "")
                    best_material["video_path"] = video_path
                
                # 获取和设置片段时间
                start_time = best_material.get("start_time", 0)
                end_time = best_material.get("end_time", 0)
                
                if "segment_start_time" in best_material:
                    start_time = best_material.get("segment_start_time", 0)
                    best_material["start_time"] = start_time
                if "segment_end_time" in best_material:
                    end_time = best_material.get("segment_end_time", 0)
                    best_material["end_time"] = end_time
                
                # 如果没有明确的片段时间，获取完整视频时长
                if end_time <= start_time and os.path.exists(video_path):
                    try:
                        _, _, video_duration = self.video_editing_service.get_video_info(video_path)
                        best_material["duration"] = video_duration
                        end_time = video_duration
                        best_material["end_time"] = end_time
                    except Exception as e:
                        logger.error(f"获取首选视频时长时出错: {str(e)}")
                        video_duration = 0
                else:
                    # 使用已有的片段时长
                    video_duration = end_time - start_time
                
                best_material["segment_duration"] = video_duration
                
                if video_duration < effective_duration:
                    logger.warning(f"段落 {segment_id}: 未找到时长足够的素材。将使用最佳匹配素材 {os.path.basename(video_path)}，但其时长 ({video_duration:.2f}s) 短于所需时长 ({effective_duration:.2f}s)。")
                else:
                    logger.info(f"段落 {segment_id}: 使用首选素材 {os.path.basename(video_path)} ({video_duration:.2f}s >= {effective_duration:.2f}s)")
            
            # 如果 best_material 仍然为空，尝试使用占位符视频
            if best_material is None:
                placeholder_path = "/home/jinpeng/multi-agent/素材/通用素材/风景.mp4"  # 使用通用素材作为占位符
                if os.path.exists(placeholder_path):
                    video_duration = 10.0  # 默认假设10秒
                    try:
                        _, _, video_duration = self.video_editing_service.get_video_info(placeholder_path)
                    except Exception:
                        pass  # 使用默认时长
                    
                    best_material = {
                        "_id": "placeholder",
                        "video_path": placeholder_path,
                        "start_time": 0,
                        "end_time": video_duration,
                        "duration": video_duration,
                        "segment_duration": video_duration
                    }
                    logger.warning(f"段落 {segment_id}: 使用占位符视频 {os.path.basename(placeholder_path)}")
                else:
                    logger.error(f"段落 {segment_id}: 无法找到合适素材，且占位符视频不存在。跳过此段落。")
                    continue
            
            # --- 后续逻辑使用选定的 best_material ---
            video_path = best_material.get("video_path", "")
            
            # 获取视频分段的开始和结束时间
            start_time = best_material.get("start_time", 0)
            end_time = best_material.get("end_time", 0)
            
            # 验证视频文件是否存在
            if not os.path.exists(video_path):
                logger.error(f"段落 {segment_id}: 视频文件不存在: {video_path}")
                continue
            
            # 确定实际可用的视频时长
            available_duration = end_time - start_time
            
            # 视频太短，使用整个片段
            if available_duration < effective_duration:
                actual_duration = available_duration
                logger.warning(f"段落 {segment_id}: 视频片段时长 ({available_duration:.2f}s) 小于所需时长 ({effective_duration:.2f}s)，将使用整个视频片段")
            else:
                # 视频足够长，使用需要的时长
                actual_duration = effective_duration

            # 创建剪辑项
            editing_item = {
                "segment_id": segment_id,
                "type": segment_type,
                "start_time": 0.0,  # 将在剪辑时确定
                "duration": actual_duration,
                "video_path": video_path,
                "video_start_time": start_time,  # 使用段落开始时间
                "video_end_time": start_time + actual_duration,  # 使用段落结束时间
                "audio_file": audio_file if not use_original_audio else "",
                "use_original_audio": use_original_audio,
                "keep_original_audio": use_original_audio,  # 添加保留原始音频标志
                "audio_volume": narration.get("volume", 1.0),
                "transition_in": segment.get("transition_in", ""),
                "transition_out": segment.get("transition_out", ""),
                "similarity_score": best_material.get("similarity_score", best_material.get("ranking_score", 0.0))
            }
            
            editing_items.append(editing_item)
        
        # 整理剪辑计划
        editing_plan = {
            "segments": editing_items,
            "audio_design": ir_data.get("audio_design", {}),
            "post_processing": ir_data.get("post_processing", {})
        }
        
        # 保存剪辑计划
        plan_file = os.path.join(self.temp_dir, f"{project_name}_editing_plan.json")
        with open(plan_file, 'w', encoding='utf-8') as f:
            json.dump(editing_plan, f, ensure_ascii=False, indent=2)
        
        editing_plan["plan_file"] = plan_file
        
        return editing_plan
    
    def _execute_editing(self, editing_plan: Dict[str, Any], project_name: str) -> str:
        """
        执行视频剪辑
        
        参数:
        editing_plan: 剪辑计划
        project_name: 项目名称
        
        返回:
        生成的视频文件路径
        """
        logger.info("执行视频剪辑...")
        
        # 检查编辑计划是否为 None 或是否有有效的段
        if editing_plan is None:
            logger.error("编辑计划为空，无法执行剪辑")
            return ""
        
        if "segments" not in editing_plan or not editing_plan["segments"]:
            logger.error("编辑计划中没有有效的段，无法执行剪辑")
            return ""
        
        # 设置输出和临时文件路径
        output_file = os.path.join(self.final_dir, f"{project_name}.mp4")
        temp_dir = os.path.join(self.temp_dir, f"{project_name}_edit_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        segments = editing_plan.get("segments", [])
        audio_design = editing_plan.get("audio_design", {})
        
        logger.info(f"开始处理 {len(segments)} 个视频段落")
        
        try:
            # 1. 处理每个段落，生成临时视频片段
            segment_files = self._process_segments(segments, temp_dir)
            
            if not segment_files:
                logger.error("没有生成有效的视频片段，无法完成剪辑")
                return ""
                
            # 2. 拼接视频片段，添加背景音乐和音效
            final_video = self._combine_segments_with_audio(
                segment_files, 
                output_file, 
                audio_design,
                project_name
            )
            
            logger.info(f"剪辑完成，输出文件: {final_video}")
            return final_video
            
        except Exception as e:
            logger.error(f"视频剪辑过程中出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return ""
    
    def _process_segments(self, segments: List[Dict[str, Any]], temp_dir: str) -> List[Dict[str, Any]]:
        """
        处理每个视频段落，生成临时视频片段
        
        参数:
        segments: 段落列表
        temp_dir: 临时文件目录
        
        返回:
        处理后的段落信息列表，包含临时文件路径
        """
        processed_segments = []
        
        # 标准分辨率配置 - 竖屏1080p (9:16)
        target_width = 1080
        target_height = 1920
        
        for i, segment in enumerate(segments):
            segment_id = segment.get("segment_id", f"segment_{i+1}")
            logger.info(f"处理视频段落 {segment_id}...")
            
            # 获取段落信息
            video_path = segment.get("video_path", "")
            video_start_time = segment.get("video_start_time", 0)
            video_end_time = segment.get("video_end_time", 0)
            segment_duration = segment.get("duration", 0)
            audio_file = segment.get("audio_file", "")
            use_original_audio = segment.get("use_original_audio", False)
            audio_volume = segment.get("audio_volume", 1.0)
            
            # 验证视频文件
            if not video_path or not os.path.exists(video_path):
                logger.error(f"段落 {segment_id} 视频文件不存在: {video_path}")
                continue
                
            # 创建临时文件名
            temp_video = os.path.join(temp_dir, f"{segment_id}_cut.mp4")
            temp_audio_video = os.path.join(temp_dir, f"{segment_id}_with_audio.mp4")
            final_segment = os.path.join(temp_dir, f"{segment_id}_final.mp4")
            
            try:
                # 1. 从原视频中切出指定时间段
                self._cut_video_segment(
                    video_path, 
                    temp_video, 
                    video_start_time, 
                    segment_duration
                )
                
                # 2. 调整视频分辨率和裁剪
                normalized_video = os.path.join(temp_dir, f"{segment_id}_normalized.mp4")
                self._normalize_video_resolution(
                    temp_video, 
                    normalized_video, 
                    target_width, 
                    target_height
                )
                
                # 3. 处理音频
                if audio_file and os.path.exists(audio_file) and not use_original_audio:
                    # 添加指定音频
                    self._add_audio_to_video(
                        normalized_video, 
                        audio_file, 
                        temp_audio_video, 
                        audio_volume,
                        keep_original=use_original_audio
                    )
                    segment_output = temp_audio_video
                else:
                    # 保持原始音频或无音频
                    segment_output = normalized_video
                
                # 4. 应用过渡效果（简单实现，可以根据需要扩展）
                transition_in = segment.get("transition_in", "")
                transition_out = segment.get("transition_out", "")
                
                if transition_in or transition_out:
                    self._apply_transitions(
                        segment_output,
                        final_segment,
                        transition_in,
                        transition_out
                    )
                else:
                    # 无过渡效果，直接使用之前的输出
                    final_segment = segment_output
                
                # 添加到处理后的段落列表
                processed_segments.append({
                    "segment_id": segment_id,
                    "original_segment": segment,
                    "output_file": final_segment,
                    "duration": segment_duration
                })
                
                logger.info(f"段落 {segment_id} 处理完成，输出: {final_segment}")
                
            except Exception as e:
                logger.error(f"处理段落 {segment_id} 时出错: {str(e)}")
                # 继续处理下一个段落
        
        return processed_segments
    
    def _combine_segments_with_audio(
        self, 
        segment_files: List[Dict[str, Any]], 
        output_file: str, 
        audio_design: Dict[str, Any],
        project_name: str
    ) -> str:
        """
        拼接视频片段并添加背景音乐
        
        参数:
        segment_files: 段落文件信息列表
        output_file: 最终输出文件路径
        audio_design: 音频设计信息
        project_name: 项目名称
        
        返回:
        最终视频文件路径
        """
        if not segment_files:
            logger.error("没有视频片段可拼接")
            return ""
        
        # 临时文件路径
        temp_dir = os.path.dirname(segment_files[0]["output_file"])
        concat_list_file = os.path.join(temp_dir, f"{project_name}_concat_list.txt")
        combined_video = os.path.join(temp_dir, f"{project_name}_combined.mp4")
        
        # 1. 创建视频片段列表文件
        with open(concat_list_file, 'w', encoding='utf-8') as f:
            for segment in segment_files:
                f.write(f"file '{os.path.abspath(segment['output_file'])}'\n")
        
        # 2. 拼接视频片段
        try:
            # 使用ffmpeg的concat协议拼接视频
            concat_cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', concat_list_file,
                '-c', 'copy',
                combined_video
            ]
            subprocess.run(concat_cmd, check=True)
            logger.info(f"视频片段拼接完成: {combined_video}")
        except subprocess.CalledProcessError as e:
            logger.error(f"拼接视频片段时出错: {e}")
            return ""
        
        # 3. 处理背景音乐
        background_music = audio_design.get("background_music", {})
        if background_music.get("enabled", False):
            # 获取第一个音乐曲目
            tracks = background_music.get("tracks", [])
            if tracks:
                first_track = tracks[0]
                music_path = first_track.get("file_path", "")
                volume = first_track.get("volume", 0.3)  # 默认音量为30%
                
                if music_path and os.path.exists(music_path):
                    try:
                        # 添加背景音乐
                        self._add_background_music(
                            combined_video,
                            music_path,
                            output_file,
                            volume
                        )
                        logger.info(f"已添加背景音乐: {music_path}")
                        return output_file
                    except Exception as e:
                        logger.error(f"添加背景音乐时出错: {str(e)}")
                        # 失败后使用无背景音乐的视频
                        import shutil
                        shutil.copy(combined_video, output_file)
                        return output_file
        
        # 如果没有背景音乐或处理失败，直接使用拼接后的视频
        import shutil
        shutil.copy(combined_video, output_file)
        return output_file
    
    def _cut_video_segment(self, input_video: str, output_video: str, start_time: float, duration: float) -> None:
        """
        从视频中剪切指定时间段
        
        参数:
        input_video: 输入视频路径
        output_video: 输出视频路径
        start_time: 开始时间（秒）
        duration: 时长（秒）
        """
        try:
            # 使用ffmpeg剪切视频
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-i', input_video,
                '-t', str(duration),
                '-c:v', 'libx264', '-c:a', 'aac',
                '-strict', 'experimental',
                '-b:a', '192k',
                output_video
            ]
            subprocess.run(cmd, check=True)
            logger.info(f"视频切片完成: {output_video}")
        except subprocess.CalledProcessError as e:
            logger.error(f"剪切视频时出错: {e}")
            raise
    
    def _normalize_video_resolution(self, input_video: str, output_video: str, target_width: int, target_height: int) -> None:
        """
        归一化视频分辨率为指定尺寸（竖屏1080p）
        
        参数:
        input_video: 输入视频路径
        output_video: 输出视频路径
        target_width: 目标宽度
        target_height: 目标高度
        """
        try:
            # 先获取视频信息
            video_info_cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,display_aspect_ratio',
                '-of', 'json', input_video
            ]
            
            video_info = subprocess.check_output(video_info_cmd).decode('utf-8')
            video_info = json.loads(video_info)
            
            stream = video_info.get('streams', [{}])[0]
            width = stream.get('width', 0)
            height = stream.get('height', 0)
            
            if width <= 0 or height <= 0:
                logger.error(f"无法获取视频尺寸: {input_video}")
                # 失败时复制原视频
                import shutil
                shutil.copy(input_video, output_video)
                return
            
            # 计算缩放和裁剪参数
            source_aspect = width / height
            target_aspect = target_width / target_height
            
            if abs(source_aspect - target_aspect) < 0.01:  # 近似相同的宽高比
                # 直接缩放
                scale_filter = f'scale={target_width}:{target_height}'
            elif source_aspect > target_aspect:  # 源视频更宽
                # 高度优先缩放，然后裁剪宽度
                scale_w = int(target_height * source_aspect)
                scale_filter = f'scale={scale_w}:{target_height},crop={target_width}:{target_height}:(iw-{target_width})/2:0'
            else:  # 源视频更高
                # 宽度优先缩放，然后裁剪高度
                scale_h = int(target_width / source_aspect)
                scale_filter = f'scale={target_width}:{scale_h},crop={target_width}:{target_height}:0:(ih-{target_height})/2'
            
            # 执行视频转换
            cmd = [
                'ffmpeg', '-y',
                '-i', input_video,
                '-vf', scale_filter,
                '-c:v', 'libx264', '-crf', '23',
                '-preset', 'medium',
                '-c:a', 'copy',
                output_video
            ]
            
            subprocess.run(cmd, check=True)
            logger.info(f"视频分辨率归一化完成: {output_video}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"归一化视频分辨率时出错: {e}")
            # 失败时复制原视频
            import shutil
            shutil.copy(input_video, output_video)
        except Exception as e:
            logger.error(f"归一化视频分辨率时发生异常: {str(e)}")
            # 失败时复制原视频
            import shutil
            shutil.copy(input_video, output_video)
    
    def _add_audio_to_video(self, video_file: str, audio_file: str, output_file: str, volume: float = 1.0, keep_original: bool = False) -> None:
        """
        将音频添加到视频
        
        参数:
        video_file: 视频文件路径
        audio_file: 音频文件路径
        output_file: 输出文件路径
        volume: 音频音量
        keep_original: 是否保留原始音频
        """
        try:
            # 构建ffmpeg命令
            audio_options = []
            
            if keep_original:
                # 保留原始音频，添加新音频，调整音量
                audio_filter = f'[1:a]volume={volume}[a1];[0:a][a1]amix=inputs=2:duration=first[a]'
                audio_options = ['-filter_complex', audio_filter, '-map', '0:v', '-map', '[a]']
            else:
                # 替换原始音频
                audio_options = ['-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', f'volume={volume}']
            
            cmd = [
                'ffmpeg', '-y',
                '-i', video_file,
                '-i', audio_file
            ] + audio_options + [output_file]
            
            subprocess.run(cmd, check=True)
            logger.info(f"添加音频完成: {output_file}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"添加音频时出错: {e}")
            # 失败时复制原视频
            import shutil
            shutil.copy(video_file, output_file)
    
    def _apply_transitions(self, input_video: str, output_video: str, transition_in: str, transition_out: str) -> None:
        """
        应用视频转场效果（简化实现）
        
        参数:
        input_video: 输入视频路径
        output_video: 输出视频路径
        transition_in: 进入转场类型
        transition_out: 退出转场类型
        """
        # 转场效果映射
        transition_filters = {
            "fade": "fade=t=in:st=0:d=1,fade=t=out:st={out_start}:d=1",
            "crossfade": "fade=t=in:st=0:d=0.5,fade=t=out:st={out_start}:d=0.5",
            "slide": "fade=t=in:st=0:d=0.8,fade=t=out:st={out_start}:d=0.8"
            # 可以添加更多转场效果
        }
        
        try:
            # 获取视频时长
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'json', input_video
            ]
            
            duration_info = subprocess.check_output(duration_cmd).decode('utf-8')
            duration_info = json.loads(duration_info)
            duration = float(duration_info.get('format', {}).get('duration', 0))
            
            # 设置基本转场
            filter_complex = []
            
            # 入场转场
            if transition_in and transition_in in transition_filters:
                t_in = transition_filters[transition_in].split(',')[0]
                filter_complex.append(t_in)
            
            # 出场转场
            if transition_out and transition_out in transition_filters and duration > 2:
                t_out = transition_filters[transition_out].split(',')[1].format(out_start=max(0, duration-1))
                filter_complex.append(t_out)
            
            # 如果有转场效果，应用它们
            if filter_complex:
                filter_str = ','.join(filter_complex)
                cmd = [
                    'ffmpeg', '-y',
                    '-i', input_video,
                    '-vf', filter_str,
                    '-c:a', 'copy',
                    output_video
                ]
                
                subprocess.run(cmd, check=True)
                logger.info(f"添加转场效果完成: {output_video}")
            else:
                # 无转场效果，复制原视频
                import shutil
                shutil.copy(input_video, output_video)
                
        except subprocess.CalledProcessError as e:
            logger.error(f"应用转场效果时出错: {e}")
            # 失败时复制原视频
            import shutil
            shutil.copy(input_video, output_video)
        except Exception as e:
            logger.error(f"应用转场效果时发生异常: {str(e)}")
            # 失败时复制原视频
            import shutil
            shutil.copy(input_video, output_video)
    
    def _add_background_music(self, video_file: str, music_file: str, output_file: str, volume: float = 0.3) -> None:
        """
        添加背景音乐到视频
        
        参数:
        video_file: 视频文件路径
        music_file: 音乐文件路径
        output_file: 输出文件路径
        volume: 音乐音量（0-1）
        """
        try:
            # 获取视频时长
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'json', video_file
            ]
            
            duration_info = subprocess.check_output(duration_cmd).decode('utf-8')
            duration_info = json.loads(duration_info)
            video_duration = float(duration_info.get('format', {}).get('duration', 0))
            
            # 添加背景音乐，循环播放直到视频结束
            cmd = [
                'ffmpeg', '-y',
                '-i', video_file,
                '-stream_loop', '-1', '-i', music_file,  # 循环播放音乐
                '-filter_complex', 
                f'[1:a]volume={volume},atrim=0:{video_duration}[a1];[0:a][a1]amix=inputs=2:duration=first[a]',
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                '-shortest',  # 最短结束
                output_file
            ]
            
            subprocess.run(cmd, check=True)
            logger.info(f"添加背景音乐完成: {output_file}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"添加背景音乐时出错: {e}")
            # 失败时复制原视频
            import shutil
            shutil.copy(video_file, output_file)
        except Exception as e:
            logger.error(f"添加背景音乐时发生异常: {str(e)}")
            # 失败时复制原视频
            import shutil
            shutil.copy(video_file, output_file)
    
    def _apply_post_processing(self, video_file: str, ir_data: Dict[str, Any], project_name: str) -> str:
        """
        应用后期处理
        
        参数:
        video_file: 视频文件路径
        ir_data: IR数据
        project_name: 项目名称
        
        返回:
        处理后的视频文件路径
        """
        logger.info("应用后期处理...")
        
        # 检查视频文件是否有效
        if not video_file or not os.path.exists(video_file):
            logger.error(f"视频文件不存在或无效: {video_file}")
            return ""
        
        # 检查IR数据是否有效
        if ir_data is None:
            logger.error("IR数据为空，无法应用后期处理")
            return video_file  # 返回原始视频文件
        
        # 获取后期处理配置
        post_processing = ir_data.get("post_processing", {}) or {}
        
        # 获取字幕配置
        subtitles_config = post_processing.get("subtitles", {}) or {}
        enable_subtitles = subtitles_config.get("enabled", False)
        
        # 应用字幕（如果启用）
        if enable_subtitles:
            logger.info("添加字幕...")
            # 这里应该调用字幕处理工具，但暂时省略
            # processed_video = self._add_subtitles(video_file, ir_data, project_name)
            processed_video = video_file  # 暂时跳过字幕处理
        else:
            processed_video = video_file
        
        # 其他后期处理（如滤镜、标志等）
        # 暂时省略，后续可以实现
        
        return processed_video 