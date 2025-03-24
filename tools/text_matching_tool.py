from crewai.tools import BaseTool, tool
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
import os
import json
import re
from difflib import SequenceMatcher
import jieba
import numpy as np
from collections import defaultdict

class TextMatchingInput(BaseModel):
    """文本匹配工具的输入模式"""
    query_text: str = Field(..., description="需要匹配的文本内容")
    limit: int = Field(5, description="最大返回数量")

class TextMatchingTool(BaseTool):
    name: str = "TextMatching"
    description: str = "在数据库中查找与给定文本最匹配的视频片段"
    args_schema: Type[BaseModel] = TextMatchingInput
    
    # 添加必要的字段
    json_file_path: str = Field(default="", description="segments JSON文件路径")
    segments: List[Dict[str, Any]] = Field(default_factory=list, description="加载的segments数据")
    
    model_config = {"arbitrary_types_allowed": True}  # 允许任意类型
    
    def __init__(self):
        super().__init__()
        # 设置JSON文件路径
        self.json_file_path = os.environ.get('SEGMENTS_JSON_PATH', '/home/jinpeng/multi-agent/segments/segments_info.json')
        # 加载segments数据
        self._load_segments()
    
    def _load_segments(self):
        """加载segments数据"""
        try:
            if os.path.exists(self.json_file_path):
                with open(self.json_file_path, 'r', encoding='utf-8') as f:
                    self.segments = json.load(f)
                print(f"已加载 {len(self.segments)} 个视频片段")
            else:
                print(f"警告: segments文件不存在: {self.json_file_path}")
                self.segments = []
        except Exception as e:
            print(f"加载segments文件时出错: {str(e)}")
            self.segments = []
    
    def _ensure_absolute_path(self, path: str) -> str:
        """确保路径是绝对路径"""
        if not path:
            return path
        if os.path.isabs(path):
            return path
        # 从环境变量获取基础目录，如果没有设置，使用默认值
        base_dir = os.environ.get('VIDEO_BASE_DIR', '/home/jinpeng/multi-agent')
        return os.path.join(base_dir, path)
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        # 使用SequenceMatcher计算相似度
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _split_text(self, text: str) -> List[str]:
        """将长文本分割成句子"""
        # 使用标点符号分割文本
        sentences = re.split(r'[，。！？,.!?;；\n]+', text)
        # 过滤空句子
        return [s.strip() for s in sentences if s.strip()]
    
    def _get_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """从文本中提取关键词"""
        try:
            # 使用jieba分词
            words = jieba.lcut(text)
            # 过滤停用词和单字词
            filtered_words = [w for w in words if len(w) > 1]
            # 返回前top_n个词
            return filtered_words[:top_n]
        except:
            # 如果jieba不可用，简单地按空格分割
            words = text.split()
            return words[:top_n]
    
    def _run(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        在JSON文件中查找与给定文本最匹配的视频片段
        
        参数:
        query_text: 需要匹配的文本内容
        limit: 最大返回数量
        
        返回:
        匹配的视频片段列表
        """
        try:
            # 确保segments已加载
            if not self.segments:
                self._load_segments()
                if not self.segments:
                    return []
            
            # 将查询文本分割成句子
            query_sentences = self._split_text(query_text)
            
            # 如果没有有效的句子，尝试提取关键词
            if not query_sentences:
                query_sentences = [query_text]
            
            # 对每个句子计算与所有segment的相似度
            all_matches = []
            
            # 记录每个视频的最佳匹配分数
            video_scores = defaultdict(float)
            
            # 对每个查询句子
            for sentence in query_sentences:
                if len(sentence) < 3:  # 忽略过短的句子
                    continue
                    
                # 计算与每个segment的相似度
                for segment in self.segments:
                    segment_text = segment.get("text", "")
                    if not segment_text:
                        continue
                    
                    # 计算相似度
                    similarity_score = self._calculate_similarity(sentence, segment_text)
                    
                    # 如果相似度大于阈值，添加到结果中
                    if similarity_score > 0.1:  # 设置一个较高的阈值，确保匹配质量
                        match = {
                            "segment": segment,
                            "similarity_score": similarity_score,
                            "matched_sentence": sentence
                        }
                        all_matches.append(match)
                        
                        # 更新视频的最佳匹配分数
                        video_path = segment.get("video_path", "")
                        if video_path and similarity_score > video_scores[video_path]:
                            video_scores[video_path] = similarity_score
            
            # 如果没有找到足够的匹配，降低阈值再次尝试
            if len(all_matches) < limit:
                # 提取查询文本的关键词
                keywords = self._get_keywords(query_text)
                
                for keyword in keywords:
                    if len(keyword) < 2:  # 忽略过短的关键词
                        continue
                        
                    for segment in self.segments:
                        segment_text = segment.get("text", "")
                        if not segment_text:
                            continue
                        
                        # 如果关键词在segment文本中
                        if keyword in segment_text:
                            # 计算相似度
                            similarity_score = 0.3  # 设置一个基础分数
                            
                            match = {
                                "segment": segment,
                                "similarity_score": similarity_score,
                                "matched_sentence": keyword
                            }
                            
                            # 检查是否已经添加过这个segment
                            if not any(m["segment"].get("segment_path") == segment.get("segment_path") for m in all_matches):
                                all_matches.append(match)
                                
                                # 更新视频的最佳匹配分数
                                video_path = segment.get("video_path", "")
                                if video_path and similarity_score > video_scores[video_path]:
                                    video_scores[video_path] = similarity_score
            
            # 按相似度排序
            all_matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # 去重：确保每个视频只选择最佳匹配的片段
            unique_matches = []
            seen_segments = set()
            
            for match in all_matches:
                segment_path = match["segment"].get("segment_path", "")
                if segment_path and segment_path not in seen_segments:
                    unique_matches.append(match)
                    seen_segments.add(segment_path)
            
            # 取前limit个结果
            top_results = unique_matches[:limit]
            
            # 格式化结果
            formatted_results = []
            for result in top_results:
                segment = result["segment"]
                
                # 获取视频路径并确保是绝对路径
                video_path = segment.get("video_path", "")
                segment_path = segment.get("segment_path", "")
                
                absolute_video_path = self._ensure_absolute_path(video_path)
                absolute_segment_path = self._ensure_absolute_path(segment_path)
                
                formatted_result = {
                    "video_path": absolute_segment_path,  # 使用切片后的视频路径
                    "original_video_path": absolute_video_path,  # 原始视频路径
                    "start_time": segment.get("start_time", 0),
                    "end_time": segment.get("end_time", 0),
                    "text": segment.get("text", ""),
                    "similarity_score": result["similarity_score"],
                    "matched_sentence": result.get("matched_sentence", ""),
                    "type": "quote"  # 标记为原话匹配类型
                }
                formatted_results.append(formatted_result)
            
            return formatted_results
        
        except Exception as e:
            print(f"文本匹配时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return [] 