from typing import Dict, Any, List
import json
import datetime
import uuid

class IRTemplateTool:
    """
    中间表示(IR)模板工具，用于生成和验证标准IR格式
    """
    
    @staticmethod
    def generate_template(brands: List[str] = None, models: List[str] = None, 
                          target_duration: float = 60.0) -> Dict[str, Any]:
        """
        生成标准IR模板，包含所有必要字段和默认值
        
        参数:
        brands: 品牌列表
        models: 车型列表
        target_duration: 目标时长
        
        返回:
        标准IR模板
        """
        # 生成唯一项目ID
        project_id = str(uuid.uuid4())
        
        # 创建当前时间戳
        timestamp = datetime.datetime.now().isoformat()
        
        # 构建元数据
        metadata = {
            "project_id": project_id,
            "title": f"汽车视频项目-{project_id[:8]}",
            "created_at": timestamp,
            "version": "1.0",
            "target_duration": target_duration,
            "target_platforms": ["微信", "抖音"],
            "brands": brands or [],
            "models": models or [],
            "style_keywords": ["专业", "现代", "高品质"],
            "target_audience": "汽车爱好者",
            "user_input": ""
        }
        
        # 构建音频设计
        audio_design = {
            "voiceover": {
                "enabled": True,
                "voice_settings": {
                    "reference_id": "a2b4d94fed4d4f0a82dfb17d11db8f35",
                    "mp3_bitrate": 128,
                    "chunk_length": 200, 
                    "latency_mode": "normal",
                    "audio_gain_db": 5,
                    "audio_cut": {
                        "enabled": True,
                        "threshold": -50,
                        "min_silence_len": 500,
                        "keep_silence": 0
                    }
                },
                "segments": [
                    {
                        "id": "voiceover_1",
                        "text": "这是默认口播文本，请替换为实际内容",
                        "position": "opening",
                        "timing": {
                            "start_time": 0.0,
                            "duration": None,
                            "sync_with_visual": True
                        },
                        "processing": {
                            "emphasis_words": [],
                            "pace": "normal",
                            "tone": "professional"
                        }
                    }
                ]
            },
            "background_music": {
                "enabled": True,
                "tracks": [
                    {
                        "id": "bgm_1",
                        "style": "现代企业",
                        "mood": "专业",
                        "segments": [
                            {
                                "start_time": 0,
                                "end_time": target_duration,
                                "volume": {
                                    "base": 0.3,
                                    "curve": [
                                        {"time": 0, "value": 0.3},
                                        {"time": target_duration * 0.9, "value": 0.2},
                                        {"time": target_duration, "value": 0}
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            "original_sound": {
                "enabled": False,
                "segments": []
            },
            "sound_effects": {
                "enabled": False,
                "effects": []
            },
            "audio_mix_strategy": {
                "voiceover_priority": "high",
                "ducking": {
                    "enabled": True,
                    "duck_amount": 0.6,
                    "duck_attack": 0.2,
                    "duck_release": 0.5
                }
            }
        }
        
        # 构建视觉结构
        visual_structure = {
            "segments": [
                {
                    "id": "segment_1",
                    "type": "opening",
                    "start_time": 0.0,
                    "duration": target_duration * 0.2,
                    "narration": {
                        "voiceover_id": "voiceover_1",
                        "use_original_audio": False,
                        "volume": 1.0
                    },
                    "visual_requirements": {
                        "scene_type": "车辆外观",
                        "shot_types": ["远景", "全景"],
                        "required_elements": ["车头", "车标"],
                        "mood": "专业",
                        "camera_movement": "稳定推进",
                        "color_grading": "标准",
                        "lighting": "明亮"
                    },
                    "material_search_strategy": {
                        "search_type": "vector",
                        "priority_brands": brands or [],
                        "priority_models": models or [],
                        "priority_tags": ["车头", "外观"],
                        "excluded_tags": ["室内"],
                        "matching_strategy": "semantic",
                        "minimum_match_score": 0.7,
                        "fallback_strategy": "keyword",
                        "weight_settings": {
                            "visual_similarity": 0.7,
                            "contextual_relevance": 0.2,
                            "technical_quality": 0.1
                        },
                        "segment_filters": {
                            "min_duration": 2.0,
                            "max_duration": None,
                            "preferred_aspect_ratio": "16:9",
                            "min_resolution": "1080p"
                        }
                    },
                    "transition_in": "淡入",
                    "transition_out": "切换"
                }
            ],
            "pacing_strategy": {
                "type": "balanced",
                "default_segment_duration": 3.0,
                "min_segment_duration": 2.0,
                "transition_duration": 0.5,
                "rhythm_pattern": ["medium", "medium", "medium"],
                "emphasis_points": []
            }
        }
        
        # 构建后期处理
        post_processing = {
            "color_grading_profile": "标准",
            "aspect_ratio": "16:9",
            "resolution": "1080p",
            "subtitles": {
                "enabled": True,
                "style": "简约白色",
                "position": "底部居中",
                "auto_generate": True,
                "font_size": 36,
                "background": {
                    "enabled": True,
                    "opacity": 0.5
                }
            },
            "logo_overlay": {
                "enabled": len(brands or []) > 0,
                "position": "右下角",
                "duration": "全程",
                "opacity": 0.8
            },
            "end_card": {
                "enabled": True,
                "duration": 3.0,
                "elements": ["品牌标志", "联系方式"]
            },
            "filters": []
        }
        
        # 构建导出设置
        export_settings = {
            "formats": ["mp4"],
            "quality_presets": ["high"],
            "bitrate": "8mbps"
        }
        
        # 组合完整IR
        ir_template = {
            "metadata": metadata,
            "audio_design": audio_design,
            "visual_structure": visual_structure,
            "post_processing": post_processing,
            "export_settings": export_settings
        }
        
        return ir_template
    
    @staticmethod
    def validate_ir(ir_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证IR数据的格式和必要字段
        
        参数:
        ir_data: 需要验证的IR数据
        
        返回:
        验证结果，包含是否有效和错误信息
        """
        # 检查主要部分是否存在
        required_sections = ["metadata", "audio_design", "visual_structure", "post_processing", "export_settings"]
        missing_sections = [section for section in required_sections if section not in ir_data]
        
        if missing_sections:
            return {
                "is_valid": False,
                "errors": f"缺少必要部分: {', '.join(missing_sections)}"
            }
        
        # TODO: 实现更详细的字段验证
        
        return {
            "is_valid": True,
            "errors": None
        }
    
    @staticmethod
    def merge_with_defaults(ir_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将用户提供的IR与默认模板合并，确保所有必要字段都存在
        
        参数:
        ir_data: 用户提供的IR数据
        
        返回:
        合并后的完整IR数据
        """
        # 获取默认模板
        default_template = IRTemplateTool.generate_template()
        
        # 递归合并函数
        def deep_merge(source, destination):
            for key, value in source.items():
                if key in destination:
                    if isinstance(value, dict) and isinstance(destination[key], dict):
                        deep_merge(value, destination[key])
                    else:
                        # 不覆盖目标中已有的值
                        pass
                else:
                    # 如果目标中没有该键，则添加
                    destination[key] = value
            return destination
        
        # 克隆用户IR并与默认模板合并
        merged_ir = json.loads(json.dumps(ir_data))  # 深拷贝
        deep_merge(default_template, merged_ir)
        
        return merged_ir 