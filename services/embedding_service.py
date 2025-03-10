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