from crewai import Agent, LLM
from typing import Type, List, Dict, Any, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool, tool
import os
import json
from tools.text_matching_tool import TextMatchingTool

class SegmentSearchInput(BaseModel):
    """片段搜索工具的输入模式"""
    query_text: str = Field(..., description="需要匹配的文本内容")
    limit: int = Field(5, description="最大返回数量")
    output_format: str = Field("json", description="输出格式，可选值：json, text")

class SegmentSearchTool(BaseTool):
    name: str = "SegmentSearch"
    description: str = "搜索与给定文本匹配的视频片段，并结构化输出"
    args_schema: Type[BaseModel] = SegmentSearchInput
    text_matching_tool: Optional[TextMatchingTool] = None
    
    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self):
        super().__init__()
        self.text_matching_tool = TextMatchingTool()
    
    def _run(self, query_text: str, limit: int = 10, output_format: str = "json") -> str:
        """
        搜索与给定文本匹配的视频片段，并结构化输出
        
        参数:
        query_text: 需要匹配的文本内容
        limit: 最大返回数量
        output_format: 输出格式，可选值：json, text
        
        返回:
        结构化的输出结果
        """
        try:
            # 调用文本匹配工具
            print(f"搜索文本: '{query_text}'")
            matching_results = self.text_matching_tool._run(query_text=query_text, limit=limit)
            
            if not matching_results:
                print("未找到匹配结果")
                return self._format_output([], output_format)
            
            print(f"找到 {len(matching_results)} 个匹配结果")
            
            # 提取需要的信息
            structured_results = []
            for result in matching_results:
                # 从segment_path中提取segment_id
                segment_path = result.get("video_path", "")
                segment_id = "unknown"
                
                # 尝试从路径中提取segment_id
                if "_segment_" in segment_path:
                    segment_id = segment_path.split("_segment_")[-1].split(".")[0]
                
                structured_result = {
                    "segment_id": segment_id,
                    "segment_path": segment_path,
                    "original_video_path": result.get("original_video_path", ""),
                    "text": result.get("text", ""),
                    "start_time": result.get("start_time", 0),
                    "end_time": result.get("end_time", 0),
                    "similarity_score": result.get("similarity_score", 0),
                    "matched_sentence": result.get("matched_sentence", ""),
                    "type": result.get("type", "quote")
                }
                structured_results.append(structured_result)
            
            # 格式化输出
            return self._format_output(structured_results, output_format)
            
        except Exception as e:
            print(f"搜索视频片段时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._format_output([], output_format)
    
    def _format_output(self, results: List[Dict[str, Any]], output_format: str) -> str:
        """格式化输出结果"""
        if output_format.lower() == "json":
            return json.dumps(results, ensure_ascii=False, indent=2)
        else:
            # 文本格式输出
            if not results:
                return "未找到匹配结果"
            
            text_output = f"找到 {len(results)} 个匹配结果:\n\n"
            for i, result in enumerate(results):
                text_output += f"结果 {i+1}:\n"
                text_output += f"  片段ID: {result['segment_id']}\n"
                text_output += f"  片段路径: {result['segment_path']}\n"
                text_output += f"  原始视频: {result['original_video_path']}\n"
                text_output += f"  文本内容: {result['text']}\n"
                text_output += f"  时间范围: {result['start_time']:.2f}s - {result['end_time']:.2f}s\n"
                
                # 安全处理相似度
                try:
                    similarity_score = float(result['similarity_score'])
                    text_output += f"  相似度: {similarity_score:.4f}\n"
                except (ValueError, TypeError):
                    text_output += f"  相似度: {result['similarity_score']}\n"
                
                text_output += f"  匹配句子: {result.get('matched_sentence', '')}\n"
                text_output += f"  类型: {result['type']}\n\n"
            
            return text_output

class SegmentSearchAgent:
    @staticmethod
    def create():
        """创建视频片段搜索 Agent"""
        # 创建工具实例
        segment_search_tool = SegmentSearchTool()
        
        # 创建 Agent
        segment_search_agent = Agent(
            role="视频片段搜索专家",
            goal="搜索与给定文本匹配的视频片段，并结构化输出",
            backstory="""你是一名专业的视频片段搜索专家，擅长根据文本内容查找最匹配的视频片段。
            你的工作是接收用户的文本查询，然后在视频库中找到与之最匹配的片段。
            你会考虑文本的语义相似度，确保找到的片段能够准确表达用户需要的内容。
            你会以结构化的方式输出结果，包括片段ID、视频路径、文本内容、时间范围等信息。
            你的输出将用于后续的视频编辑和合成工作，因此需要保证信息的准确性和完整性。""",
            verbose=True,
            allow_delegation=False,
            tools=[segment_search_tool],
            llm=LLM(
                model="gpt-4o-mini",
                api_key=os.environ.get('OPENAI_API_KEY'),
                base_url=os.environ.get('OPENAI_BASE_URL'),
                temperature=0.1,
                custom_llm_provider="openai"
            )
        )
        
        return segment_search_agent

# 如果直接运行此文件，则创建Agent并执行测试
if __name__ == "__main__":
    # 创建Agent
    agent = SegmentSearchAgent.create()
    
    # 测试查询
    test_query = "我们想要做什么事情,其实做人最重要 然后我们是一个什么样的人,就会有什么样的心态"
    
    # 执行任务
    result = agent.execute_task(f"搜索与以下文本匹配的视频片段，并以JSON格式输出结果：\n\n'{test_query}'")
    
    print("\n执行结果:")
    print(result) 