#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import datetime
import logging
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from crewai import Task, Crew, Process
from crewai.llm import LLM

from agents.segment_search_agent import SegmentSearchAgent
from tools.segment_processor import SegmentProcessor

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SegmentSearchService:
    """视频片段搜索服务，使用Agent Task调用SegmentSearchAgent"""
    
    def __init__(self, output_dir: str = "./output"):
        """
        初始化服务
        
        参数:
        output_dir: 输出目录
        """
        # 确保 output_dir 是绝对路径
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 创建子目录
        self.segments_dir = os.path.join(self.output_dir, "segments")
        self.final_dir = os.path.join(self.output_dir, "final")
        
        os.makedirs(self.segments_dir, exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)
        
        # 初始化Agent
        self.segment_search_agent = SegmentSearchAgent.create()
        
        # 初始化处理器
        self.segment_processor = SegmentProcessor(output_dir=self.segments_dir)
        
        # 添加token使用记录
        self.token_usage_records = []
        
        # 设置LLM
        self.llm = LLM(
            model="gemini-1.5-pro",
            api_key=os.environ.get('OPENAI_API_KEY'),
            base_url=os.environ.get('OPENAI_BASE_URL'),
            temperature=0.1,
            custom_llm_provider="openai",
            request_timeout=180  # 增加超时时间到180秒
        )
    
    def search_and_process(self, query_text: str, limit: int = 5, threshold: float = 0.1, keep_audio: bool = True) -> Dict[str, Any]:
        """
        搜索与给定文本匹配的视频片段并处理
        
        参数:
        query_text: 需要匹配的文本内容
        limit: 最大返回数量
        threshold: 相似度阈值，低于此值的结果将被过滤
        keep_audio: 是否保留原始音频
        
        返回:
        处理结果，包含最终视频路径和相关信息
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = f"segment_search_{timestamp}"
        
        try:
            # 1. 创建搜索任务
            logger.info(f"搜索文本: '{query_text}'")
            search_task = Task(
                description=f"""搜索与以下文本匹配的视频片段，并以JSON格式输出结果：

'{query_text}'

请确保结果包含以下信息：
1. 片段ID
2. 视频路径
3. 文本内容
4. 时间范围

CoT:
1. 首先，根据query_text，搜索匹配的视频片段,注意返回的片段数量是大于query_text本身需要的。
2. 然后，根据query_text，从返回的片段中，选择符合query_text的片段，其他片段都删除。
3. 最后，按照query_text的顺序返回匹配的视频片段。

注意，你返回的结果必须按照query_text的顺序返回，不要打乱顺序。**过滤掉不匹配的片段。**json 内禁止出现换行！！""",
                agent=self.segment_search_agent,
                expected_output="""JSON格式的搜索结果，包含匹配的视频片段信息
                [
                  {
                    "segment_id": "片段ID",
                    "video_path": "视频路径",
                    "text": "文本内容",
                    "start_time": "开始时间",
                    "end_time": "结束时间",
                    "similarity_score": "相似度分数"
                  }
                ]""",
                output_file=os.path.join(self.output_dir, f"{project_name}_search_result.json")
            )
            
            # 创建Crew并执行任务
            search_crew = Crew(
                agents=[self.segment_search_agent],
                tasks=[search_task],
                verbose=True,
                process=Process.sequential
            )
            
            # 执行搜索
            search_result = search_crew.kickoff()
            
            # 记录token使用情况
            self._record_token_usage(search_result, "片段搜索")
            
            # 2. 解析搜索结果
            logger.info("解析搜索结果...")
            parsed_result = self._parse_search_result(search_result)
            
            # 保存搜索结果
            search_result_file = os.path.join(self.output_dir, f"{project_name}_search_result.json")
            # with open(search_result_file, 'w', encoding='utf-8') as f:
            #     json.dump(parsed_result, f, ensure_ascii=False, indent=2)
            
            # 不再进行相似度过滤
            
            if not parsed_result:
                logger.warning("没有找到符合条件的匹配结果")
                return {
                    "project_name": project_name,
                    "query_text": query_text,
                    "error": "没有找到符合条件的匹配结果",
                    "search_result_file": search_result_file
                }
            
            # 3. 处理视频片段
            logger.info("处理视频片段...")
            segment_paths = []
            original_to_extracted_map = {}  # 存储原始路径到对应可用片段的映射
            
            for i, result in enumerate(parsed_result):
                try:
                    # 直接使用video_path而不进行额外的提取操作
                    video_path = result.get("video_path", "")
                    
                    if not video_path or not os.path.exists(video_path):
                        logger.warning(f"片段 {i+1}/{len(parsed_result)} 路径无效或不存在: {video_path}")
                        continue
                        
                    # 直接使用原视频路径
                    segment_paths.append(video_path)
                    
                    # 对于映射，使用相同的路径(因为我们不再提取)
                    original_to_extracted_map[video_path] = video_path
                    result["extracted_path"] = video_path  # 为保持一致性
                    
                    logger.info(f"使用片段 {i+1}/{len(parsed_result)}: {os.path.basename(video_path)}")
                    logger.info(f"  文本: {result.get('text', '')}")
                    # 确保similarity_score是浮点数
                    try:
                        similarity_score = float(result.get('similarity_score', 0))
                        logger.info(f"  相似度: {similarity_score:.4f}")
                    except (ValueError, TypeError):
                        logger.info(f"  相似度: {result.get('similarity_score', 0)}")
                except Exception as e:
                    logger.error(f"处理片段 {i+1}/{len(parsed_result)} 时出错: {str(e)}")
            
            if not segment_paths:
                logger.warning("没有找到任何有效的视频片段")
                return {
                    "project_name": project_name,
                    "query_text": query_text,
                    "error": "没有找到任何有效的视频片段",
                    "search_result_file": search_result_file
                }
            
            # 4. 合并所有片段
            output_file = os.path.join(self.final_dir, f"{project_name}_final.mp4")
            try:
                # 如果只有一个片段，直接复制
                if len(segment_paths) == 1:
                    logger.info(f"只有一个片段，直接复制到 {output_file}")
                    import shutil
                    shutil.copy2(segment_paths[0], output_file)
                    final_video = output_file
                    logger.info(f"复制完成: {final_video}")
                else:
                    # 多个片段，尝试合并
                    logger.info(f"开始合并 {len(segment_paths)} 个视频片段到 {output_file}")
                    
                    # 记录所有片段路径供调试
                    for i, path in enumerate(segment_paths):
                        logger.info(f"  片段 {i+1}: {path} (存在: {os.path.exists(path)})")
                    
                    # 使用segment_processor合并片段
                    final_video = self.segment_processor.merge_segments(segment_paths, output_file, keep_audio=keep_audio)
                    logger.info(f"合并完成: {final_video}")
                
                logger.info(f"处理完成，输出文件: {final_video}")
            except Exception as e:
                logger.error(f"处理视频片段时出错: {str(e)}", exc_info=True)
                
                # 如果出现错误，但至少有一个片段，则直接使用第一个片段作为结果
                if segment_paths:
                    logger.info(f"由于处理出错，使用第一个片段作为结果: {segment_paths[0]}")
                    # 复制第一个片段到输出文件
                    import shutil
                    try:
                        shutil.copy2(segment_paths[0], output_file)
                        final_video = output_file
                        logger.info(f"已复制单个片段到: {final_video}")
                    except Exception as copy_e:
                        logger.error(f"复制单个片段时出错: {str(copy_e)}")
                        final_video = segment_paths[0]  # 直接使用原片段路径
                else:
                    # 如果没有任何片段，则创建一个错误提示
                    logger.error("没有任何可用片段，无法生成结果视频")
                    raise ValueError("没有有效视频片段可供处理")
            
            # 返回结果
            result = {
                "project_name": project_name,
                "query_text": query_text,
                "search_result": {
                    "data": parsed_result,
                    "file": search_result_file
                },
                "segment_paths": segment_paths,
                "original_to_extracted_map": original_to_extracted_map,  # 添加映射关系
                "final_video": final_video,
                "token_usage_records": self.token_usage_records
            }
            
            # 保存完整结果
            result_file = os.path.join(self.final_dir, f"{project_name}_result.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            return result
            
        except Exception as e:
            logger.error(f"搜索和处理过程中出错: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "project_name": project_name,
                "query_text": query_text
            }
    
    def _clean_text_for_json_parsing(self, text: str) -> str:
        """清理文本以便于JSON解析"""
        # 去除非法控制字符
        cleaned_text = re.sub(r"[\x00-\x1F\x7F]", "", text)
        # 去除首尾空白
        cleaned_text = cleaned_text.strip()
        return cleaned_text
    
    def _extract_json_from_text(self, text: str) -> List[Dict[str, Any]]:
        """尝试多种方式从文本中提取JSON"""
        # 清理文本
        cleaned_text = self._clean_text_for_json_parsing(text)
        
        # 1. 尝试找出代码块中的JSON
        json_code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned_text, re.DOTALL)
        if json_code_match:
            code_content = json_code_match.group(1).strip()
            try:
                parsed = json.loads(code_content)
                if isinstance(parsed, list) and len(parsed) > 0:
                    logger.info(f"从代码块中成功提取JSON数组，包含 {len(parsed)} 个项目")
                    return parsed
            except json.JSONDecodeError:
                logger.info("代码块内容不是有效JSON，继续尝试其他方法")
        
        # 2. 尝试直接解析清理后的文本
        try:
            if cleaned_text.startswith('[') and cleaned_text.endswith(']'):
                parsed = json.loads(cleaned_text)
                if isinstance(parsed, list) and len(parsed) > 0:
                    logger.info(f"直接解析清理后的文本成功，找到 {len(parsed)} 个项目")
                    return parsed
        except json.JSONDecodeError:
            logger.info("清理后的文本不是有效JSON，继续尝试其他方法")
        
        # 3. 尝试使用正则表达式从文本中提取JSON数组
        # 这里复用增强的正则提取方法
        return self._extract_json_with_regex(cleaned_text)
    
    def _extract_json_with_regex(self, text: str) -> List[Dict[str, Any]]:
        """使用多种正则表达式策略尝试提取JSON"""
        logger.info("使用增强的正则表达式策略提取JSON")
        
        # 尝试匹配格式化良好的JSON数组
        patterns = [
            # 标准JSON数组
            r'\[\s*\{\s*"segment_id".*?\}\s*\]',
            # 包含转义字符的JSON
            r'\[\s*\{(?:[^{}]|(?:\{[^{}]*\}))*\}\s*\]',
            # 更宽松的模式，匹配包含大括号的数组
            r'\[\s*\{[\s\S]*?\}\s*(?:,\s*\{[\s\S]*?\}\s*)*\]',
            # 非常宽松的模式，尝试匹配任何可能的JSON数组
            r'\[[\s\S]*?\]'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.DOTALL)
            for match in matches:
                json_str = match.group(0)
                try:
                    # 清理提取的JSON字符串
                    cleaned_json = self._clean_text_for_json_parsing(json_str)
                    parsed = json.loads(cleaned_json)
                    if isinstance(parsed, list) and len(parsed) > 0 and all(isinstance(item, dict) for item in parsed):
                        logger.info(f"使用模式 '{pattern}' 成功提取到JSON数组，包含 {len(parsed)} 个项目")
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        # 如果无法找到完整的JSON数组，尝试逐个提取JSON对象
        segment_patterns = [
            # 原始的严格模式
            r'\{\s*"segment_id"\s*:\s*"([^"]+)"\s*,\s*"video_path"\s*:\s*"([^"]+)"\s*,\s*"text"\s*:\s*"([^"]+)"\s*,\s*"start_time"\s*:\s*([0-9.]+)\s*,\s*"end_time"\s*:\s*([0-9.]+)\s*,\s*"similarity_score"\s*:\s*([0-9.]+)\s*\}',
            # 更宽松的模式，处理字段顺序不同的情况
            r'\{\s*(?:"segment_id"\s*:\s*"([^"]+)"|"video_path"\s*:\s*"([^"]+)"|"text"\s*:\s*"([^"]+)"|"start_time"\s*:\s*([0-9.]+)|"end_time"\s*:\s*([0-9.]+)|"similarity_score"\s*:\s*([0-9.]+))(?:\s*,\s*(?:"segment_id"\s*:\s*"([^"]+)"|"video_path"\s*:\s*"([^"]+)"|"text"\s*:\s*"([^"]+)"|"start_time"\s*:\s*([0-9.]+)|"end_time"\s*:\s*([0-9.]+)|"similarity_score"\s*:\s*([0-9.]+)))*\s*\}'
        ]
        
        for pattern in segment_patterns:
            segment_matches = re.finditer(pattern, text, re.DOTALL)
            segments = []
            
            if pattern == segment_patterns[0]:  # 使用原始的严格模式
                for match in segment_matches:
                    segment_id, video_path, text, start_time, end_time, similarity_score = match.groups()
                    segments.append({
                        "segment_id": segment_id,
                        "video_path": video_path,
                        "text": text,
                        "start_time": float(start_time),
                        "end_time": float(end_time),
                        "similarity_score": float(similarity_score)
                    })
            else:
                # 对于更宽松的模式，直接尝试解析每个匹配的对象
                for match in segment_matches:
                    try:
                        # 清理提取的JSON对象
                        cleaned_obj = self._clean_text_for_json_parsing(match.group(0))
                        obj = json.loads(cleaned_obj)
                        if isinstance(obj, dict) and "segment_id" in obj:
                            segments.append(obj)
                    except json.JSONDecodeError:
                        continue
            
            if segments:
                logger.info(f"使用模式 '{pattern}' 成功提取到 {len(segments)} 个片段")
                return segments
        
        # 最后的尝试：查找任何可能是JSON对象的文本并尝试解析
        object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.finditer(object_pattern, text, re.DOTALL)
        
        segments = []
        for match in matches:
            try:
                # 清理提取的JSON对象
                cleaned_obj = self._clean_text_for_json_parsing(match.group(0))
                obj = json.loads(cleaned_obj)
                if isinstance(obj, dict) and "segment_id" in obj:
                    segments.append(obj)
            except json.JSONDecodeError:
                continue
        
        if segments:
            logger.info(f"使用通用对象模式成功提取到 {len(segments)} 个片段")
            return segments
        
        return []

    def _parse_search_result(self, result: Any) -> List[Dict[str, Any]]:
        """解析搜索结果"""
        try:
            # 保存原始结果用于调试
            debug_file = os.path.join(self.output_dir, f"search_result_debug_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(debug_file, 'w', encoding='utf-8') as f:
                if hasattr(result, 'raw'):
                    f.write(result.raw)
                else:
                    f.write(str(result))
            
            logger.info(f"原始结果已保存到: {debug_file}")
            
            # 1. 检查是否为字典类型
            if isinstance(result, dict):
                if "segment_id" in result or "segments" in result:
                    logger.info("结果已经是包含片段信息的字典")
                    return [result] if "segment_id" in result else result.get("segments", [])
            
            # 2. 检查CrewOutput的json_dict属性
            if hasattr(result, 'json_dict') and result.json_dict is not None:
                logger.info("从result.json_dict获取结果")
                if isinstance(result.json_dict, list):
                    return result.json_dict
                elif isinstance(result.json_dict, dict):
                    if "segments" in result.json_dict:
                        return result.json_dict.get("segments", [])
                    elif "segment_id" in result.json_dict:
                        return [result.json_dict]
                    
            # 3. 如果是CrewOutput对象
            if hasattr(result, 'raw'):
                raw_text = result.raw
                
                # 尝试从raw_text中提取JSON
                segments = self._extract_json_from_text(raw_text)
                if segments:
                    return segments
                
                # 尝试查找Final Answer部分
                final_answer_match = re.search(r'## Final Answer:?\s*([\s\S]*?)(?:\n##|\Z)', raw_text, re.DOTALL)
                if final_answer_match:
                    final_answer = final_answer_match.group(1).strip()
                    logger.info(f"找到Final Answer: {final_answer[:100]}...")
                    
                    # 尝试从Final Answer中提取JSON
                    segments = self._extract_json_from_text(final_answer)
                    if segments:
                        return segments
            
            # 4. 如果是字符串，尝试提取JSON
            if isinstance(result, str):
                segments = self._extract_json_from_text(result)
                if segments:
                    return segments
            
            # 5. 尝试从调试文件中读取
            try:
                with open(debug_file, 'r', encoding='utf-8') as f:
                    debug_content = f.read().strip()
                    segments = self._extract_json_from_text(debug_content)
                    if segments:
                        logger.info("从调试文件中成功提取JSON")
                        return segments
            except Exception as e:
                logger.warning(f"从调试文件解析JSON失败: {str(e)}")
            
            # 如果都失败了，返回空列表
            logger.warning("无法解析搜索结果，返回空列表")
            return []
            
        except Exception as e:
            logger.error(f"解析搜索结果时出错: {str(e)}", exc_info=True)
            
            # 保存原始结果用于调试
            debug_file = os.path.join(self.output_dir, f"search_result_debug_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(str(result))
            
            logger.info(f"错误情况下的原始结果已保存到: {debug_file}")
            
            return []
    
    def _record_token_usage(self, result: Any, step_name: str) -> None:
        """记录token使用情况"""
        if hasattr(result, 'usage') and result.usage:
            usage = result.usage
            self.token_usage_records.append({
                "step": step_name,
                "timestamp": datetime.datetime.now().isoformat(),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            })

# 如果直接运行此文件，则执行测试
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='搜索与给定文本匹配的视频片段并处理')
    parser.add_argument('--query', type=str, required=True,
                        help='需要匹配的文本内容')
    parser.add_argument('--limit', type=int, default=5,
                        help='最大返回数量')
    parser.add_argument('--threshold', type=float, default=0.1,
                        help='相似度阈值，低于此值的结果将被过滤')
    parser.add_argument('--output-dir', type=str, default="./output",
                        help='输出目录')
    parser.add_argument('--keep-audio', action='store_true',
                        help='是否保留原始音频')
    
    args = parser.parse_args()
    
    # 创建服务并执行搜索和处理
    service = SegmentSearchService(output_dir=args.output_dir)
    result = service.search_and_process(
        query_text=args.query,
        limit=args.limit,
        threshold=args.threshold,
        keep_audio=args.keep_audio
    )
    
    # 打印结果
    if "error" in result:
        print(f"错误: {result['error']}")
    else:
        print(f"处理完成，输出文件: {result['final_video']}")
        print(f"总共合并了 {len(result['segment_paths'])} 个视频片段") 