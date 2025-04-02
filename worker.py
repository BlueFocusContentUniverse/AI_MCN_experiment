#!/usr/bin/env python3

import os
import sys
import time
import json
import argparse
import logging
from typing import Dict, Any
import threading
import traceback
import re
from crewai import Task, Crew, Process

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# 导入任务处理相关模块
from agents.requirement_parsing_agent import RequirementParsingAgent
from tools.ir_template_tool import IRTemplateTool
from services.ir_video_processor import IRVideoProcessor
# 替换为MongoDB任务管理服务
from streamlit_app.services.mongo_service import TaskManagerService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('worker.log')
    ]
)
logger = logging.getLogger(__name__)

class Worker:
    """工作机节点，负责从任务队列获取并处理任务"""
    
    def __init__(self, worker_id: str = None, output_dir: str = "./output"):
        """
        初始化工作机
        
        参数:
        worker_id: 工作机ID，如果不提供则使用主机名
        output_dir: 输出目录
        """
        # 设置工作机ID
        self.worker_id = worker_id or os.uname().nodename
        logger.info(f"工作机启动: {self.worker_id}")
        
        # 初始化输出目录
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化MongoDB任务管理器
        self.task_manager = TaskManagerService()
        logger.info("已初始化MongoDB任务管理器")
        
        # 初始化处理服务
        self.requirement_parser = RequirementParsingAgent.create()
        self.ir_processor = IRVideoProcessor(output_dir=output_dir)
        
        # 工作状态
        self.running = False
        self.current_task_id = None
        self.worker_thread = None
    
    def start(self):
        """启动工作机"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop)
            self.worker_thread.daemon = True
            self.worker_thread.start()
            logger.info("工作机线程已启动")
    
    def stop(self):
        """停止工作机"""
        if self.running:
            logger.info("正在停止工作机...")
            self.running = False
            if self.worker_thread:
                self.worker_thread.join(timeout=5)
            logger.info("工作机已停止")
    
    def _worker_loop(self):
        """工作循环，不断从队列获取任务并处理"""
        logger.info("开始工作循环")
        
        while self.running:
            try:
                # 获取任务
                task = self._get_next_task()
                
                if task:
                    # 更新当前任务ID
                    self.current_task_id = task["_id"]  # MongoDB使用_id字段
                    logger.info(f"开始处理任务: {self.current_task_id}")
                    
                    # 更新任务状态
                    self.task_manager.update_task_status(self.current_task_id, "processing")
                    
                    # 处理任务
                    result = self._process_task(task)
                    
                    # 更新任务结果
                    if result["success"]:
                        # 更新任务为已完成
                        self.task_manager.update_task_status(self.current_task_id, "completed", 100)
                        logger.info(f"任务处理成功: {self.current_task_id}")
                    else:
                        self.task_manager.update_task_status(self.current_task_id, "failed")
                        logger.error(f"任务处理失败: {self.current_task_id} - {result.get('error', '未知错误')}")
                    
                    # 清除当前任务ID
                    self.current_task_id = None
                    
                else:
                    # 没有任务，等待一段时间
                    logger.info("没有待处理任务，等待中...")
                    time.sleep(5)
            
            except Exception as e:
                logger.error(f"工作循环中出错: {str(e)}")
                traceback.print_exc()
                time.sleep(10)  # 出错后等待更长时间
    
    def _get_next_task(self) -> Dict[str, Any]:
        """获取下一个要处理的任务"""
        try:
            # 从MongoDB获取待处理任务
            pending_tasks = self.task_manager.get_tasks(status="pending")
            
            # 如果有任务，返回第一个
            if pending_tasks:
                # 按优先级排序（如果配置中有优先级字段）
                try:
                    pending_tasks.sort(key=lambda t: self._get_priority_value(t.get("config", {}).get("priority", "normal")))
                except Exception as e:
                    logger.warning(f"任务排序出错: {str(e)}")
            
                return pending_tasks[0]
            return None
            
        except Exception as e:
            logger.error(f"获取任务时出错: {str(e)}")
            return None
    
    def _process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务
        
        参数:
        task: 任务信息
        
        返回:
        处理结果
        """
        try:
            # 获取配置和任务参数
            config = task.get("config", {})
            
            # 从MongoDB任务配置中提取参数
            user_requirement = config.get("user_requirement", "")
            brands = config.get("brands", [])
            models = config.get("models", [])
            target_platforms = config.get("target_platforms", [])
            target_duration = config.get("target_duration", 60.0)
            
            if not user_requirement:
                return {
                    "success": False,
                    "error": "缺少用户需求"
                }
            
            # 更新进度
            self.task_manager.update_task_status(self.current_task_id, "processing", 10)
            
            # 1. 解析需求，生成IR
            logger.info("解析用户需求...")
            
            # 如果已有IR预览，直接使用
            if "ir_preview" in config:
                ir_data = config["ir_preview"]
                logger.info("使用预生成的IR")
            else:
                # 创建空IR数据
                ir_data = IRTemplateTool.generate_template(
                    brands=brands,
                    models=models,
                    target_duration=target_duration
                )
                
                # 设置用户输入
                ir_data["metadata"]["user_input"] = user_requirement

                # 调用需求解析Agent，使用Task+Crew执行模式
                try:
                    logger.info("调用需求解析Agent...")
                    
                    # 创建解析需求的任务
                    parse_requirement_task = Task(
                        description=f"""分析用户需求，生成标准化的视频制作中间表示(IR)。
                        
                        用户需求: {user_requirement}
                        
                        提供的内容:
                        - 品牌: {brands if brands else "未指定"}
                        - 品类: {models if models else "未指定"}
                        - 目标平台: {target_platforms if target_platforms else "未指定"}
                        - 目标时长: {target_duration}秒
                        
                        你需要分析这些需求，并生成一个完整的IR数据结构，这是一个JSON格式的标准数据结构，
                        必须包含以下所有主要部分:
                        
                        1. metadata（元数据）:
                           - project_id: 项目唯一标识符
                           - title: 项目标题
                           - created_at: 创建时间
                           - version: 版本号
                           - target_duration: 目标时长(秒)
                           - target_platforms: 目标平台数组
                           - brands: 品牌数组
                           - models: 品类数组
                           - style_keywords: 风格关键词数组
                           - target_audience: 目标受众
                           - user_input: 原始用户输入
                        
                        2. audio_design（音频设计）:
                           - voiceover: 配音设置，包含voice_settings和segments
                           - background_music: 背景音乐设置，包含tracks
                           - original_sound: 原始声音设置
                           - sound_effects: 音效设置
                           - audio_mix_strategy: 混音策略
                        
                        3. visual_structure（视觉结构）:
                           - segments: 视频分段数组，每个分段包含:
                             * id: 分段ID
                             * type: 分段类型(opening, body, closing等)
                             * start_time: 开始时间
                             * duration: 持续时间
                             * narration: 旁白设置
                             * visual_requirements: 视觉要求
                             * material_search_strategy: 素材搜索策略
                             * transition_in: 进入转场
                             * transition_out: 退出转场
                           - pacing_strategy: 节奏策略
                        
                        4. post_processing（后期处理）:
                           - color_grading_profile: 色彩校正配置文件
                           - aspect_ratio: 宽高比
                           - resolution: 分辨率
                           - subtitles: 字幕设置
                           - logo_overlay: Logo覆盖设置
                           - end_card: 结束卡片设置
                           - filters: 滤镜数组
                        
                        5. export_settings（导出设置）:
                           - formats: 导出格式数组
                           - quality_presets: 质量预设数组
                           - bitrate: 比特率
                        
                        对于不明确的部分，请根据汽车视频制作的最佳实践做出合理推断。
                        最终输出必须是一个有效的JSON对象，包含以上所有主要部分。
                        """,
                        expected_output="一个完整的、JSON格式的IR数据结构，包含所有必要的字段和详细信息，符合指定的五个主要部分的结构要求, 请直接返回JSON格式的IR数据,包裹在代码块里，不要包含任何其他文本或解释。",
                        agent=self.requirement_parser
                    )
                    
                    # 创建Crew
                    requirement_crew = Crew(
                        agents=[self.requirement_parser],
                        tasks=[parse_requirement_task],
                        verbose=True,
                        process=Process.sequential
                    )
                    
                    # 执行解析需求的任务
                    requirement_result = requirement_crew.kickoff()
                    output_text = str(requirement_result).strip()
                    
                    # 解析返回结果 - 尝试从返回的文本中提取JSON
                    try:
                        # 寻找JSON对象 - 可能被包围在```json和```之间，或者直接是一个JSON对象
                        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output_text, re.DOTALL)
                        if not json_match:
                            # 尝试直接匹配JSON对象
                            json_match = re.search(r'(\{.*\})', output_text, re.DOTALL)
                        
                        if json_match:
                            json_str = json_match.group(1)
                            parsed_ir = json.loads(json_str)
                            if parsed_ir and isinstance(parsed_ir, dict) and "metadata" in parsed_ir:
                                ir_data = parsed_ir
                                logger.info("需求解析完成，使用解析后的IR数据")
                            else:
                                logger.warning("解析到的IR数据不完整，将继续使用基础模板")
                        else:
                            logger.warning("Agent响应中未找到JSON格式的IR数据，将继续使用基础模板")
                            logger.debug(f"Agent响应内容: {requirement_result}")
                    except json.JSONDecodeError as json_err:
                        logger.error(f"IR数据JSON解析错误: {json_err}")
                        logger.debug(f"尝试解析的内容: {output_text}")
                        logger.warning("由于JSON解析错误，将继续使用基础模板")
                except Exception as agent_err:
                    logger.error(f"需求解析Agent执行错误: {agent_err}", exc_info=True)
                    logger.warning("由于Agent执行错误，将继续使用基础模板")

            # 更新进度
            self.task_manager.update_task_status(self.current_task_id, "processing", 20)
            
            # 2. 处理IR，生成视频
            logger.info("执行视频处理...")
            processing_result = self.ir_processor.process_ir(ir_data)
            
            # 更新进度
            self.task_manager.update_task_status(self.current_task_id, "processing", 90)
            
            # 3. 返回结果
            return {
                "success": processing_result.get("success", False),
                "project_id": processing_result.get("project_id", ""),
                "project_name": processing_result.get("project_name", ""),
                "final_video": processing_result.get("final_video", ""),
                "ir_file": processing_result.get("ir_file", ""),
                "error": processing_result.get("error", "")
            }
            
        except Exception as e:
            logger.error(f"处理任务时出错: {str(e)}")
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_priority_value(self, priority: str) -> int:
        """获取优先级数值"""
        if priority == "high":
            return 0
        elif priority == "normal":
            return 1
        else:  # low
            return 2

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="视频处理工作机")
    parser.add_argument("--worker-id", help="工作机ID")
    parser.add_argument("--output-dir", default="./output", help="输出目录")
    args = parser.parse_args()
    
    # 创建并启动工作机
    worker = Worker(worker_id=args.worker_id, output_dir=args.output_dir)
    worker.start()
    
    try:
        # 主线程保持运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在停止...")
        worker.stop()

if __name__ == "__main__":
    main() 