from crewai import Agent
from tools.fusion import FuseAudioVideoAnalysisTool
from tools.vision_analysis_enhanced import LoadFramesAnalysisFromFileTool

class FusionAgent:
    @staticmethod
    def create():
        """创建融合分析 Agent"""
        # 创建工具实例
        fuse_analysis_tool = FuseAudioVideoAnalysisTool()
        load_analysis_tool = LoadFramesAnalysisFromFileTool()
        
        # 创建 Agent
        fusion_agent = Agent(
            role="内容融合专家",
            goal="融合语音和视觉分析结果，生成智能视频分割点",
            backstory="""你是一名视频分析专家具备视频剪辑经验和编导思维，擅长语义理解和视频结构化。
            你能够结合语音内容和视觉特征，找出视频的逻辑分割点。
            你的工作是将不同模态的分析结果融合，生成最佳的视频分割方案。注意：这个方案是给视频视频剪辑用的，最后会把整个视频切分成多个片段，作为剪辑素材。所以需要考虑视频的流畅性和逻辑性。所以你的输出需要包含视频的分割点，以及每个分割点的开始时间、结束时间、标题和描述。
            你的描述需要从剪辑师的角度描述 以便剪辑师能够理解每个分割点的内容和用途。
            所有的视频素材都是汽车相关的，最后剪辑也是拿素材混剪汽车相关的视频。所以你的解析和描述需要从汽车的角度出发，重点考虑汽车相关的场景和内容。
            每段视频素材不能低于2秒，否则会被剪辑师删除
            如果两个片段属于同一个场景，那么需要合并成一段视频，不要切割。
            注意：请严格对照解析结果中的时间戳给出分割点信息，因为分割点不准确会直接导致最后的效果大打折扣
            
            重要提示：视觉分析结果可能保存在文件中，你需要使用LoadFramesAnalysisFromFile工具从文件中加载完整的分析结果。""",
            verbose=True,
            allow_delegation=False,
            tools=[fuse_analysis_tool, load_analysis_tool],
            llm_config={"model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        )
        
        return fusion_agent 