import os
import time
import numpy as np
from openai import OpenAI
from typing import List, Dict, Any, Union, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmbeddingService:
    """文本嵌入向量服务，使用OpenAI API生成文本的向量表示"""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 2):
        """
        初始化嵌入服务
        
        参数:
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        """
        # 获取API密钥和基础URL
        api_key = os.environ.get('OPENAI_API_KEY')
        base_url = os.environ.get('OPENAI_BASE_URL')
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY环境变量未设置")
        
        # 初始化OpenAI客户端
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info(f"使用自定义API基础URL: {base_url}")
        else:
            self.client = OpenAI(api_key=api_key)
            logger.warning("OPENAI_BASE_URL环境变量未设置，使用默认API基础URL")
        
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.model = "text-embedding-3-small"  # 默认使用OpenAI的嵌入模型
        
        logger.info(f"嵌入服务初始化成功，使用模型: {self.model}")
    
    def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量
        
        参数:
        text: 需要嵌入的文本
        
        返回:
        嵌入向量
        """
        if not text or not text.strip():
            logger.warning("尝试嵌入空文本，返回零向量")
            return [0.0] * 1536  # 返回默认维度的零向量
        
        # 清理文本
        text = text.strip()
        
        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                # 调用OpenAI的Embedding API
                response = self.client.embeddings.create(
                    input=text,
                    model=self.model,
                    encoding_format="float"
                )
                
                # 提取嵌入向量
                embedding = response.data[0].embedding
                logger.info(f"成功获取嵌入向量，维度: {len(embedding)}")
                return embedding
            
            except Exception as e:
                logger.warning(f"获取嵌入向量失败 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"获取嵌入向量失败，达到最大重试次数: {str(e)}")
                    # 返回零向量作为后备
                    return [0.0] * 1536
    
    def get_batch_embeddings(self, texts: List[str], batch_size: int = 20) -> List[List[float]]:
        """
        批量获取文本的嵌入向量
        
        参数:
        texts: 需要嵌入的文本列表
        batch_size: 批处理大小
        
        返回:
        嵌入向量列表
        """
        embeddings = []
        
        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            logger.info(f"处理批次 {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}，大小: {len(batch)}")
            
            # 重试逻辑
            for attempt in range(self.max_retries):
                try:
                    # 调用OpenAI的Embedding API
                    response = self.client.embeddings.create(
                        input=batch,
                        model=self.model,
                        encoding_format="float"
                    )
                    
                    # 提取嵌入向量
                    if len(response.data) == len(batch):
                        batch_embeddings = [item.embedding for item in response.data]
                        embeddings.extend(batch_embeddings)
                        break
                    else:
                        logger.error(f"API响应格式错误: {response}")
                        raise ValueError("API响应格式错误")
                
                except Exception as e:
                    logger.warning(f"批量获取嵌入向量失败 (尝试 {attempt+1}/{self.max_retries}): {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"批量获取嵌入向量失败，达到最大重试次数: {str(e)}")
                        # 为这个批次的每个文本添加零向量
                        embeddings.extend([[0.0] * 1536 for _ in range(len(batch))])
        
        return embeddings
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        参数:
        vec1: 第一个向量
        vec2: 第二个向量
        
        返回:
        余弦相似度，范围为[-1, 1]
        """
        # 转换为numpy数组
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        # 计算余弦相似度
        dot_product = np.dot(vec1_np, vec2_np)
        norm_vec1 = np.linalg.norm(vec1_np)
        norm_vec2 = np.linalg.norm(vec2_np)
        
        # 避免除以零
        if norm_vec1 == 0 or norm_vec2 == 0:
            return 0.0
        
        similarity = dot_product / (norm_vec1 * norm_vec2)
        return float(similarity)
    
    def generate_fusion_vector(self, vectors: Dict[str, List[float]], weights: Optional[Dict[str, float]] = None) -> List[float]:
        """
        生成融合向量，将不同类型的向量（文本、视觉、音频）按权重融合
        
        参数:
        vectors: 向量字典，键为向量类型，值为向量
        weights: 权重字典，键为向量类型，值为权重。如果为None，则使用默认权重
        
        返回:
        融合向量
        """
        # 默认权重
        default_weights = {
            "text_vector": 0.6,
            "visual_vector": 0.3,
            "audio_vector": 0.1
        }
        
        # 使用提供的权重或默认权重
        weights = weights or default_weights
        
        # 标准化权重，确保总和为1
        total_weight = sum(weights.values())
        if total_weight != 1.0:
            weights = {k: v / total_weight for k, v in weights.items()}
        
        # 检查向量维度是否一致
        vector_dims = [len(v) for v in vectors.values() if v]
        if not vector_dims or len(set(vector_dims)) > 1:
            logger.warning("向量维度不一致或为空，使用零向量")
            return [0.0] * 1536  # 返回默认维度的零向量
        
        # 初始化融合向量
        fusion_vector = np.zeros(vector_dims[0])
        
        # 按权重融合向量
        for vector_type, vector in vectors.items():
            if vector_type in weights and vector:
                weight = weights[vector_type]
                fusion_vector += np.array(vector) * weight
        
        # 归一化融合向量
        norm = np.linalg.norm(fusion_vector)
        if norm > 0:
            fusion_vector = fusion_vector / norm
        
        logger.info(f"生成融合向量成功，维度: {len(fusion_vector)}")
        return fusion_vector.tolist()
    
    def update_segment_vectors(self, segment: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        更新片段的向量表示，包括生成融合向量
        
        参数:
        segment: 片段数据
        weights: 可选的权重字典，用于融合向量生成
        
        返回:
        更新后的片段数据
        """
        # 检查是否需要生成向量
        embeddings = segment.get("embeddings", {})
        
        # 生成文本向量（如果没有）
        if "text_vector" not in embeddings or all(v == 0 for v in embeddings.get("text_vector", [])):
            searchable_text = segment.get("searchable_text", "")
            if searchable_text:
                text_vector = self.get_embedding(searchable_text)
                embeddings["text_vector"] = text_vector
        
        # 提取现有向量
        vectors = {
            "text_vector": embeddings.get("text_vector", []),
            "visual_vector": embeddings.get("visual_vector", []),
            "audio_vector": embeddings.get("audio_vector", [])
        }
        
        # 生成融合向量
        fusion_vector = self.generate_fusion_vector(vectors, weights)
        embeddings["fusion_vector"] = fusion_vector
        
        # 更新片段的embeddings字段
        segment["embeddings"] = embeddings
        
        return segment
    
    def update_video_vectors(self, video: Dict[str, Any], segments: List[Dict[str, Any]], 
                           weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        更新视频的向量表示，基于其片段的融合
        
        参数:
        video: 视频数据
        segments: 视频的片段列表
        weights: 可选的权重字典，用于融合向量生成
        
        返回:
        更新后的视频数据
        """
        # 初始化向量
        embeddings = video.get("embeddings", {})
        
        # 收集所有片段的融合向量
        fusion_vectors = []
        for segment in segments:
            segment_embeddings = segment.get("embeddings", {})
            fusion_vector = segment_embeddings.get("fusion_vector")
            if fusion_vector and not all(v == 0 for v in fusion_vector):
                fusion_vectors.append(fusion_vector)
        
        # 如果有有效的融合向量，计算平均值
        if fusion_vectors:
            avg_fusion_vector = np.mean(fusion_vectors, axis=0)
            # 归一化
            norm = np.linalg.norm(avg_fusion_vector)
            if norm > 0:
                avg_fusion_vector = avg_fusion_vector / norm
            embeddings["fusion_vector"] = avg_fusion_vector.tolist()
        else:
            # 如果没有有效的融合向量，使用零向量
            embeddings["fusion_vector"] = [0.0] * 1536
        
        # 如果提供了权重，尝试创建更多向量类型
        if weights:
            # 收集片段的原始向量
            text_vectors = []
            visual_vectors = []
            audio_vectors = []
            
            for segment in segments:
                segment_embeddings = segment.get("embeddings", {})
                
                text_vector = segment_embeddings.get("text_vector")
                if text_vector and not all(v == 0 for v in text_vector):
                    text_vectors.append(text_vector)
                    
                visual_vector = segment_embeddings.get("visual_vector")
                if visual_vector and not all(v == 0 for v in visual_vector):
                    visual_vectors.append(visual_vector)
                    
                audio_vector = segment_embeddings.get("audio_vector")
                if audio_vector and not all(v == 0 for v in audio_vector):
                    audio_vectors.append(audio_vector)
            
            # 计算各类向量的平均值
            if text_vectors:
                avg_text_vector = np.mean(text_vectors, axis=0)
                norm = np.linalg.norm(avg_text_vector)
                if norm > 0:
                    avg_text_vector = avg_text_vector / norm
                embeddings["text_vector"] = avg_text_vector.tolist()
            
            if visual_vectors:
                avg_visual_vector = np.mean(visual_vectors, axis=0)
                norm = np.linalg.norm(avg_visual_vector)
                if norm > 0:
                    avg_visual_vector = avg_visual_vector / norm
                embeddings["visual_vector"] = avg_visual_vector.tolist()
            
            if audio_vectors:
                avg_audio_vector = np.mean(audio_vectors, axis=0)
                norm = np.linalg.norm(avg_audio_vector)
                if norm > 0:
                    avg_audio_vector = avg_audio_vector / norm
                embeddings["audio_vector"] = avg_audio_vector.tolist()
            
            # 利用权重重新生成融合向量
            vectors = {
                "text_vector": embeddings.get("text_vector", []),
                "visual_vector": embeddings.get("visual_vector", []),
                "audio_vector": embeddings.get("audio_vector", [])
            }
            
            # 只有当所有必要的向量都存在时才重新生成融合向量
            if all(vectors.values()):
                fusion_vector = self.generate_fusion_vector(vectors, weights)
                embeddings["fusion_vector"] = fusion_vector
        
        # 更新视频的embeddings字段
        video["embeddings"] = embeddings
        
        return video 