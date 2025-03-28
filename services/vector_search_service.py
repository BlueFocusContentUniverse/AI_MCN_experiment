import numpy as np
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from bson import ObjectId
import hashlib
import json
from functools import lru_cache

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LSHIndex:
    """局部敏感哈希索引，用于快速近似向量搜索"""
    
    def __init__(self, dim=1536, bands=20, rows=4):
        """
        初始化LSH索引
        
        参数:
        dim: 向量维度
        bands: 哈希表数量
        rows: 每个band的行数
        """
        self.dim = dim
        self.bands = bands
        self.rows = rows
        self.hash_tables = [{} for _ in range(bands)]
        self.random_projections = self._generate_projections()
        logger.info(f"已初始化LSH索引: {bands}个哈希表, 每表{rows}行, 向量维度: {dim}")
    
    def _generate_projections(self) -> List[List[np.ndarray]]:
        """生成随机投影向量"""
        projections = []
        for i in range(self.bands):
            band_projections = []
            for j in range(self.rows):
                # 生成随机单位向量
                proj = np.random.randn(self.dim)
                proj = proj / np.linalg.norm(proj)
                band_projections.append(proj)
            projections.append(band_projections)
        return projections
    
    def hash_vector(self, vector: List[float]) -> List[int]:
        """计算向量的LSH哈希签名"""
        vector = np.array(vector)
        signatures = []
        
        for band_idx, band_projections in enumerate(self.random_projections):
            band_hashes = []
            for proj in band_projections:
                # 计算向量投影，大于0为1，否则为0
                h = 1 if np.dot(vector, proj) > 0 else 0
                band_hashes.append(h)
            
            # 将band_hashes转换为整数
            signature = 0
            for bit in band_hashes:
                signature = (signature << 1) | bit
            signatures.append(signature)
        
        return signatures
    
    def index_vectors(self, vectors_with_ids: List[Tuple[str, List[float]]]) -> None:
        """为多个向量建立索引"""
        for vector_id, vector in vectors_with_ids:
            self.index_vector(vector_id, vector)
        
        # 打印索引统计信息
        total_entries = sum(len(table) for table in self.hash_tables)
        logger.info(f"已完成向量索引构建，共 {len(vectors_with_ids)} 个向量, {total_entries} 个哈希表条目")
    
    def index_vector(self, vector_id: str, vector: List[float]) -> None:
        """将向量添加到索引"""
        signatures = self.hash_vector(vector)
        
        for band_idx, signature in enumerate(signatures):
            if signature not in self.hash_tables[band_idx]:
                self.hash_tables[band_idx][signature] = set()
            self.hash_tables[band_idx][signature].add(vector_id)
    
    def query(self, query_vector: List[float], threshold: int = 1) -> Set[str]:
        """查询与给定向量相似的向量ID"""
        signatures = self.hash_vector(query_vector)
        candidates = set()
        
        for band_idx, signature in enumerate(signatures):
            if signature in self.hash_tables[band_idx]:
                candidates.update(self.hash_tables[band_idx][signature])
        
        return candidates


class VectorSearchService:
    """向量搜索服务，实现应用层向量相似度计算"""
    
    def __init__(self, mongodb_service):
        """
        初始化向量搜索服务
        
        参数:
        mongodb_service: MongoDB服务实例
        """
        self.mongodb_service = mongodb_service
        self.lsh_indices = {}  # 存储不同类型的LSH索引
        self.vector_cache = {}  # 向量缓存
        self.query_cache = {}  # 查询结果缓存
        self.cache_hits = 0
        self.cache_misses = 0
        self.query_count = 0
    
    def build_lsh_index(self, collection_name: str, vector_field: str, refresh: bool = False) -> None:
        """
        构建LSH索引
        
        参数:
        collection_name: 集合名称（videos 或 video_segments）
        vector_field: 向量字段路径，如 "embeddings.text_vector"
        refresh: 是否强制刷新索引
        """
        index_key = f"{collection_name}_{vector_field}"
        
        # 如果已存在且不需要刷新，则跳过
        if index_key in self.lsh_indices and not refresh:
            logger.info(f"使用现有LSH索引: {index_key}")
            return
        
        logger.info(f"开始构建LSH索引: {index_key}")
        start_time = time.time()
        
        # 创建新索引
        lsh_index = LSHIndex()
        
        # 确定字段路径
        field_parts = vector_field.split('.')
        
        # 从数据库加载向量
        collection = getattr(self.mongodb_service.db, collection_name)
        projection = {field_parts[0]: 1}
        
        # 分批查询
        batch_size = 100
        cursor = collection.find({}, projection)
        
        vectors_with_ids = []
        batch_count = 0
        processed_count = 0
        
        for doc in cursor:
            # 提取向量
            vector = doc
            for part in field_parts:
                if isinstance(vector, dict) and part in vector:
                    vector = vector[part]
                else:
                    vector = None
                    break
            
            # 如果存在有效向量，添加到索引
            if vector and isinstance(vector, list) and len(vector) > 0:
                vectors_with_ids.append((str(doc["_id"]), vector))
                processed_count += 1
            
            # 批处理，避免内存溢出
            if len(vectors_with_ids) >= batch_size:
                lsh_index.index_vectors(vectors_with_ids)
                vectors_with_ids = []
                batch_count += 1
                logger.info(f"已处理 {batch_count * batch_size} 个向量")
        
        # 处理最后一批
        if vectors_with_ids:
            lsh_index.index_vectors(vectors_with_ids)
        
        # 缓存索引
        self.lsh_indices[index_key] = lsh_index
        elapsed_time = time.time() - start_time
        logger.info(f"LSH索引构建完成: {index_key}, 处理了 {processed_count} 个向量, 耗时 {elapsed_time:.2f} 秒")
    
    def get_vector(self, doc: Dict[str, Any], field_path: str) -> Optional[List[float]]:
        """
        从文档中获取向量
        
        参数:
        doc: 文档对象
        field_path: 向量字段路径

        返回:
        向量或None
        """
        # 尝试从缓存获取
        cache_key = f"{doc['_id']}_{field_path}"
        if cache_key in self.vector_cache:
            return self.vector_cache[cache_key]
        
        # 从文档中提取
        parts = field_path.split('.')
        value = doc
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        
        # 缓存并返回
        if isinstance(value, list) and len(value) > 0:
            self.vector_cache[cache_key] = value
            return value
        
        return None
    
    def rebuild_vector(self, vector_chunks: Dict[str, List[float]]) -> List[float]:
        """
        从分块向量重建完整向量
        
        参数:
        vector_chunks: 分块存储的向量

        返回:
        重建的完整向量
        """
        result = []
        
        # 检查是否为分块存储
        if not vector_chunks:
            return []
            
        # 检查是否为旧格式（非分块）
        if isinstance(vector_chunks, list):
            return vector_chunks
            
        # 按顺序合并向量块
        for i in range(1, 13):  # 假设12个块
            chunk_key = f"chunk_{i}"
            if chunk_key in vector_chunks:
                result.extend(vector_chunks[chunk_key])
        
        # 如果没有块格式，尝试直接使用
        if not result and isinstance(vector_chunks, dict):
            for key, value in vector_chunks.items():
                if isinstance(value, list) and len(value) > 0:
                    if len(value) == 1536:  # 完整向量
                        return value
                    result.extend(value)
        
        return result
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算两个向量的余弦相似度
        
        参数:
        vec1: 第一个向量
        vec2: 第二个向量

        返回:
        余弦相似度，范围[-1, 1]
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
    
    def batch_cosine_similarity(self, query_vector: List[float], 
                              candidate_vectors: List[Tuple[str, List[float]]], 
                              batch_size: int = 100) -> List[Tuple[str, float]]:
        """
        分批计算余弦相似度
        
        参数:
        query_vector: 查询向量
        candidate_vectors: 候选向量列表，每项为(id, vector)
        batch_size: 批处理大小

        返回:
        相似度结果列表，按相似度降序排序
        """
        results = []
        query_vector = np.array(query_vector)
        query_norm = np.linalg.norm(query_vector)
        
        # 分批处理
        for i in range(0, len(candidate_vectors), batch_size):
            batch = candidate_vectors[i:i+batch_size]
            batch_ids = [v[0] for v in batch]
            batch_vectors = [np.array(v[1]) for v in batch]
            
            # 计算正规化因子
            batch_norms = [np.linalg.norm(v) for v in batch_vectors]
            
            # 计算点积
            similarities = []
            for j, vector in enumerate(batch_vectors):
                if batch_norms[j] == 0 or query_norm == 0:
                    sim = 0
                else:
                    # 计算余弦相似度
                    sim = np.dot(query_vector, vector) / (query_norm * batch_norms[j])
                similarities.append((batch_ids[j], sim))
            
            results.extend(similarities)
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def search_similar_vectors(self, query_vector: List[float], 
                             collection_name: str,
                             vector_field: str,
                             pre_filter: Optional[Dict[str, Any]] = None,
                             limit: int = 10) -> List[Dict[str, Any]]:
        """
        查找与查询向量相似的文档
        
        参数:
        query_vector: 查询向量
        collection_name: 集合名称
        vector_field: 向量字段路径
        pre_filter: 预过滤条件
        limit: 返回文档数量限制

        返回:
        相似文档列表
        """
        self.query_count += 1
        
        # 生成查询缓存键
        query_hash = hashlib.md5(
            (str(query_vector[:10]) + collection_name + vector_field + 
             json.dumps(pre_filter or {}, sort_keys=True)).encode()
        ).hexdigest()
        
        # 检查查询缓存
        if query_hash in self.query_cache:
            self.cache_hits += 1
            return self.query_cache[query_hash]
        
        self.cache_misses += 1
        
        # 确保LSH索引存在
        index_key = f"{collection_name}_{vector_field}"
        if index_key not in self.lsh_indices:
            self.build_lsh_index(collection_name, vector_field)
        
        # 使用LSH索引找到候选集
        lsh_index = self.lsh_indices[index_key]
        candidate_ids = lsh_index.query(query_vector)
        
        if not candidate_ids:
            logger.warning(f"LSH查询未找到候选集: {collection_name}, {vector_field}")
            return []
        
        # 将字符串ID转换为ObjectId
        object_ids = [ObjectId(id_str) for id_str in candidate_ids]
        
        # 构建MongoDB查询
        query = {"_id": {"$in": object_ids}}
        if pre_filter:
            # 合并预过滤条件
            for key, value in pre_filter.items():
                query[key] = value
        
        # 查询MongoDB
        collection = getattr(self.mongodb_service.db, collection_name)
        candidates = list(collection.find(query))
        
        if len(candidates) < 5 and pre_filter:
            # 放宽条件，只保留ID过滤
            candidates = list(collection.find({"_id": {"$in": object_ids}}))
        
        # 提取向量并计算相似度
        candidate_vectors = []
        for doc in candidates:
            vector = self.get_vector(doc, vector_field)
            if vector:
                candidate_vectors.append((str(doc["_id"]), vector))
        
        # 计算相似度
        if not candidate_vectors:
            logger.warning(f"未找到有效的向量: {collection_name}, {vector_field}")
            return []
            
        similarities = self.batch_cosine_similarity(query_vector, candidate_vectors)
        
        # 保留分数最高的结果
        top_ids = [ObjectId(s[0]) for s in similarities[:limit*2]]  # 获取更多候选以备筛选
        
        # 获取完整文档
        top_docs = list(collection.find({"_id": {"$in": top_ids}}))
        
        # 添加相似度分数
        for doc in top_docs:
            doc_id_str = str(doc["_id"])
            for id_str, score in similarities:
                if id_str == doc_id_str:
                    doc["vector_score"] = score
                    break
        
        # 按相似度排序
        top_docs.sort(key=lambda x: x.get("vector_score", 0), reverse=True)
        
        result = top_docs[:limit]
        
        # 缓存查询结果
        self.query_cache[query_hash] = result
        
        # 如果缓存太大，清理最旧的项
        if len(self.query_cache) > 1000:
            oldest_key = next(iter(self.query_cache))
            del self.query_cache[oldest_key]
        
        return result
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        返回:
        缓存统计
        """
        return {
            "query_count": self.query_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": self.cache_hits / max(1, self.query_count),
            "vector_cache_size": len(self.vector_cache),
            "query_cache_size": len(self.query_cache),
            "lsh_indices": list(self.lsh_indices.keys())
        }
    
    def clear_caches(self) -> None:
        """清空所有缓存"""
        self.vector_cache.clear()
        self.query_cache.clear()
        logger.info("已清空向量和查询缓存") 